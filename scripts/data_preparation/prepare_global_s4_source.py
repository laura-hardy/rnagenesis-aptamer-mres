#!/usr/bin/env python3
"""Prepare one cleaned source for the future corpus-wide S4 merge.

Selects CHECKPOINT-1-authorised canonical rows and writes an exact subset
handoff CSV. Does not normalise targets, assign UniProt/family, score evidence,
apply leakage, deduplicate, cluster, or begin CHECKPOINT-2 / S5.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    CorpusSchemaError,
    write_corpus_csv_atomic,
)
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402

REQUIRED_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "source_key",
        "canonical_input",
        "resolution_manifest",
        "authorised_ids_input",
        "authorisation_field",
        "expected_authorised_records",
        "global_s4_handoff_output",
    }
)

FORBIDDEN_MUTATION_FIELDS: frozenset[str] = frozenset(
    {
        "target_name",
        "target_type",
        "target_type_source",
        "target_uniprot",
        "target_family",
        "target_pfam",
        "pdb_id",
        "binding_evidence_type",
        "binding_evidence_score",
        "affinity_value",
        "affinity_unit",
        "affinity_type",
        "near_duplicate_family_id",
        "cluster_id",
        "is_cluster_representative",
        "partition",
    }
)

HANDOFF_CLOSED_STATEMENT = (
    "AptaBase is ready to be retrieved as one input to the future corpus-wide "
    "S4 merge."
)

TARGET_EVIDENCE_BOUNDARY_LINES: tuple[str, ...] = (
    "target_name remains unresolved",
    "target_type remains unresolved",
    "protein/non-protein filtering not performed",
    "Kd/Affinity evidence not scored",
    "leakage not applied",
    "global deduplication not performed",
    "balancing not performed",
    "partitioning not performed",
)

SEQUENCE_BEARING_HANDOFF_EXTRAS: frozenset[str] = frozenset(
    {
        "utexas_aptamer_sequence",
        "sequence_raw",
        "sequence_full",
        "sequence_core",
        "aptamer_sequence",
        "riboaptamer_sequence",
    }
)


class GlobalS4HandoffError(ValueError):
    """Hard failure while preparing a global-S4 source handoff."""


@dataclass(frozen=True)
class HandoffStats:
    """Aggregate-only handoff counters."""

    source_key: str
    s3_records: int
    resolution_records: int
    authorised_ids: int
    handoff_records: int
    unique_handoff_ids: int
    target_specific_present: int | None
    target_specific_missing: int | None
    category_observations: Mapping[str, int]


@dataclass(frozen=True)
class HandoffResult:
    """Paths and aggregates from one handoff run."""

    source_key: str
    stats: HandoffStats
    output_csv: Path
    output_summary: Path
    integrity_ok: bool


def assert_no_legacy_cleaner_import() -> None:
    forbidden = {
        "aptabase_cleaning",
        "scripts.data_preparation.aptabase_cleaning",
    }
    for name in forbidden:
        if name in sys.modules:
            raise GlobalS4HandoffError(
                "legacy AptaBase cleaner must not be imported by global-S4 handoff"
            )


def _resolve_under_repo(repo_root: Path, path: Path | str) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _relative_display(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
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


def _read_csv(path: Path, *, label: str) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise GlobalS4HandoffError(f"{label} CSV has no header: {path.name}")
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        for key, value in list(row.items()):
            row[key] = "" if value is None else value
        if "record_id" in row and not (row.get("record_id") or "").strip():
            raise GlobalS4HandoffError(f"{label} row {index} has blank record_id")
    return rows


def _unique_ids(rows: Sequence[Mapping[str, str]], *, label: str) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        record_id = (row.get("record_id") or "").strip()
        if not record_id:
            raise GlobalS4HandoffError(f"{label} row {index} has blank record_id")
        if record_id in seen:
            raise GlobalS4HandoffError(
                f"{label} contains duplicate record_id={record_id!r}"
            )
        seen.add(record_id)
        ids.append(record_id)
    return ids


def load_source_config(path: Path) -> dict[str, Any]:
    """Load and validate one global-S4 source handoff config."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GlobalS4HandoffError(f"Invalid JSON config: {path}") from exc
    if not isinstance(payload, dict):
        raise GlobalS4HandoffError(f"Config root must be an object: {path}")
    missing = sorted(REQUIRED_CONFIG_KEYS - set(payload))
    if missing:
        raise GlobalS4HandoffError(
            f"Config missing required keys: {', '.join(missing)}"
        )
    source_key = payload.get("source_key")
    if not isinstance(source_key, str) or not source_key.strip():
        raise GlobalS4HandoffError("source_key must be a nonempty string")
    expected = payload.get("expected_authorised_records")
    if not isinstance(expected, int) or expected < 0:
        raise GlobalS4HandoffError(
            "expected_authorised_records must be a non-negative integer"
        )
    auth_field = payload.get("authorisation_field")
    if not isinstance(auth_field, str) or not auth_field.strip():
        raise GlobalS4HandoffError("authorisation_field must be a nonempty string")
    for key in (
        "canonical_input",
        "resolution_manifest",
        "authorised_ids_input",
        "global_s4_handoff_output",
    ):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise GlobalS4HandoffError(f"{key} must be a nonempty string path")
        if value.startswith("/") or (len(value) > 2 and value[1] == ":"):
            raise GlobalS4HandoffError(f"{key} must be a repo-relative path")
    return payload


def _assert_output_allowed(repo_root: Path, output_path: Path) -> Path:
    resolved = _resolve_under_repo(repo_root, output_path)
    interim_root = (repo_root / "data" / "interim").resolve()
    try:
        resolved.relative_to(interim_root)
    except ValueError as exc:
        raise GlobalS4HandoffError(
            "Handoff output must lie beneath data/interim/: " f"{output_path}"
        ) from exc
    raw_root = (repo_root / "data" / "raw").resolve()
    try:
        resolved.relative_to(raw_root)
    except ValueError:
        pass
    else:
        raise GlobalS4HandoffError(
            f"Refusing to write handoff under data/raw/: {output_path}"
        )
    return resolved


def _select_authorised_resolutions(
    resolutions: Sequence[Mapping[str, str]],
    *,
    authorisation_field: str,
) -> list[dict[str, str]]:
    if authorisation_field not in (resolutions[0] if resolutions else {}):
        # Still validate empty case separately.
        if resolutions:
            raise GlobalS4HandoffError(
                f"Resolution manifest missing authorisation field "
                f"{authorisation_field!r}"
            )
    selected: list[dict[str, str]] = []
    for row in resolutions:
        if authorisation_field not in row:
            raise GlobalS4HandoffError(
                f"Resolution row missing authorisation field {authorisation_field!r}"
            )
        flag = (row.get(authorisation_field) or "").strip()
        if flag not in {"true", "false"}:
            raise GlobalS4HandoffError(
                f"{authorisation_field} must be lowercase true/false; got {flag!r}"
            )
        if flag != "true":
            continue
        resolved = (row.get("resolved_decision") or "").strip()
        status = (row.get("checkpoint1_resolution_status") or "").strip()
        if resolved != "accept":
            raise GlobalS4HandoffError(
                f"Authorised record {row.get('record_id')!r} has "
                f"resolved_decision={resolved!r}; expected accept"
            )
        if status != "approved_for_s4":
            raise GlobalS4HandoffError(
                f"Authorised record {row.get('record_id')!r} has "
                f"checkpoint1_resolution_status={status!r}; expected approved_for_s4"
            )
        selected.append(dict(row))
    return selected


def _align_authorised_id_sets(
    *,
    authorised_resolutions: Sequence[Mapping[str, str]],
    authorised_id_rows: Sequence[Mapping[str, str]],
) -> set[str]:
    res_ids = _unique_ids(authorised_resolutions, label="authorised resolutions")
    file_ids = _unique_ids(authorised_id_rows, label="authorised-ID file")
    if set(res_ids) != set(file_ids):
        missing = sorted(set(res_ids) - set(file_ids))
        extra = sorted(set(file_ids) - set(res_ids))
        parts: list[str] = []
        if missing:
            parts.append(f"missing_from_id_file={missing[:5]}")
        if extra:
            parts.append(f"extra_in_id_file={extra[:5]}")
        raise GlobalS4HandoffError(
            "Authorised resolution IDs disagree with authorised-ID file; "
            + "; ".join(parts)
        )
    return set(file_ids)


def _select_canonical_subset(
    canonical_rows: Sequence[Mapping[str, str]],
    authorised_id_set: set[str],
) -> list[dict[str, str]]:
    """Return authorised rows in S3 canonical order (exact unchanged subset)."""
    canon_ids = _unique_ids(canonical_rows, label="S3 canonical")
    canon_set = set(canon_ids)
    missing = sorted(authorised_id_set - canon_set)
    if missing:
        raise GlobalS4HandoffError(
            "Authorised IDs missing from S3 canonical: " + ", ".join(missing[:5])
        )
    selected = [
        dict(row)
        for row in canonical_rows
        if row["record_id"] in authorised_id_set
    ]
    if len(selected) != len(authorised_id_set):
        raise GlobalS4HandoffError(
            "Canonical subset size disagrees with authorised ID set"
        )
    return selected


def _assert_exact_subset_fields(
    handoff_rows: Sequence[Mapping[str, str]],
    canonical_rows: Sequence[Mapping[str, str]],
) -> None:
    by_id = {row["record_id"]: row for row in canonical_rows}
    for row in handoff_rows:
        source = by_id[row["record_id"]]
        for column in CORPUS_COLUMNS:
            if row.get(column, "") != source.get(column, ""):
                raise GlobalS4HandoffError(
                    f"Handoff mutated field {column!r} for {row['record_id']!r}"
                )
        for field_name in FORBIDDEN_MUTATION_FIELDS:
            if row.get(field_name, "") != source.get(field_name, ""):
                raise GlobalS4HandoffError(
                    f"Handoff must not alter field {field_name!r}"
                )


def _join_handoff_source_metadata(
    *,
    repo_root: Path,
    config: Mapping[str, Any],
    handoff_rows: list[dict[str, str]],
) -> list[str]:
    """Join configured sequence-safe source-metadata fields onto handoff rows."""
    extra_raw = config.get("handoff_extra_fields")
    if extra_raw in (None, [], ()):
        return []
    if not isinstance(extra_raw, list) or not all(
        isinstance(item, str) and item.strip() for item in extra_raw
    ):
        raise GlobalS4HandoffError(
            "handoff_extra_fields must be a list of nonempty strings"
        )
    extra_fields = [item.strip() for item in extra_raw]
    forbidden = [
        name
        for name in extra_fields
        if name in SEQUENCE_BEARING_HANDOFF_EXTRAS or name in CORPUS_COLUMNS
    ]
    if forbidden:
        raise GlobalS4HandoffError(
            "handoff_extra_fields must not repeat corpus columns or "
            f"sequence-bearing sidecar fields: {forbidden}"
        )
    target_meta = config.get("target_metadata")
    sidecar_rel = ""
    if isinstance(target_meta, dict):
        sidecar_rel = str(target_meta.get("source_metadata_path") or "").strip()
    if not sidecar_rel:
        sidecar_rel = str(config.get("source_metadata_path") or "").strip()
    if not sidecar_rel:
        raise GlobalS4HandoffError(
            "handoff_extra_fields requires source_metadata_path"
        )
    sidecar_path = _resolve_under_repo(repo_root, sidecar_rel)
    if not sidecar_path.is_file():
        raise GlobalS4HandoffError(
            f"Missing source-metadata sidecar for handoff: {sidecar_path.name}"
        )
    sidecar_rows = _read_csv(sidecar_path, label="source-metadata sidecar")
    sidecar_by_id = {row["record_id"]: row for row in sidecar_rows}
    for row in handoff_rows:
        record_id = row["record_id"]
        if record_id not in sidecar_by_id:
            raise GlobalS4HandoffError(
                f"Authorised handoff record missing from source metadata: {record_id}"
            )
        meta = sidecar_by_id[record_id]
        for field_name in extra_fields:
            if field_name not in meta:
                raise GlobalS4HandoffError(
                    f"Source-metadata sidecar missing handoff field {field_name!r}"
                )
            row[field_name] = meta.get(field_name) or ""
    return extra_fields


def build_handoff_summary(
    *,
    repo_root: Path,
    result: HandoffResult,
    config: Mapping[str, Any],
) -> str:
    stats = result.stats
    lines = [
        f"# {stats.source_key} global-S4 handoff summary",
        "",
        "## Totals",
        "",
        f"- source = `{stats.source_key}`",
        f"- S3 records = `{stats.s3_records}`",
        f"- CHECKPOINT-1 authorised = `{stats.authorised_ids}`",
        f"- global-S4 handoff records = `{stats.handoff_records}`",
    ]
    if stats.target_specific_present is not None:
        lines.append(
            f"- target_specific present = `{stats.target_specific_present}`"
        )
    if stats.target_specific_missing is not None:
        lines.append(
            f"- target_specific missing = `{stats.target_specific_missing}`"
        )
    if stats.category_observations:
        lines.extend(["", "## Observed source target_general categories", ""])
        for key, count in stats.category_observations.items():
            lines.append(f"- `{key}` = `{count}`")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- No target normalisation, target eligibility, evidence eligibility,",
            "  deduplication or clustering has been applied to this handoff.",
            "- Category counts are source observations only, not final decisions.",
            f"- Output: `{_relative_display(result.output_csv, repo_root)}`",
            "",
        ]
    )
    emit_boundary = bool(config.get("emit_target_evidence_boundary")) or (
        stats.source_key == "utexas"
    )
    if emit_boundary:
        lines.extend(["## Target/evidence boundary", ""])
        for item in TARGET_EVIDENCE_BOUNDARY_LINES:
            lines.append(f"- {item}")
        lines.append("")
    extra_fields = config.get("handoff_extra_fields")
    if isinstance(extra_fields, list) and extra_fields:
        lines.extend(
            [
                "## Source-metadata fields joined onto the handoff",
                "",
            ]
        )
        for field_name in extra_fields:
            lines.append(f"- `{field_name}`")
        target_meta = config.get("target_metadata")
        sidecar = ""
        if isinstance(target_meta, dict):
            sidecar = str(target_meta.get("source_metadata_path") or "")
        if sidecar:
            lines.append(f"- source-metadata linkage: `{sidecar}`")
        lines.append("")
    statement = config.get("handoff_ready_statement")
    if isinstance(statement, str) and statement.strip():
        lines.append(statement.strip())
    elif stats.source_key == "aptabase":
        lines.append(HANDOFF_CLOSED_STATEMENT)
    else:
        lines.append(
            f"{stats.source_key} is ready to be retrieved as one input to the "
            "future corpus-wide S4 merge."
        )
    lines.append("")
    return "\n".join(lines)


def prepare_global_s4_source(
    *,
    source_config: Path,
    repo_root: Path | None = None,
    verify_input_integrity: bool = True,
) -> HandoffResult:
    """Materialise one source's exact authorised subset for future global S4."""
    assert_no_legacy_cleaner_import()
    root = repo_root or find_repo_root()
    config_path = _resolve_under_repo(root, source_config)
    if not config_path.exists():
        raise GlobalS4HandoffError(f"Unknown source config: {source_config}")
    config = load_source_config(config_path)

    canonical_path = _resolve_under_repo(root, config["canonical_input"])
    resolution_path = _resolve_under_repo(root, config["resolution_manifest"])
    authorised_ids_path = _resolve_under_repo(root, config["authorised_ids_input"])
    output_csv = _assert_output_allowed(root, config["global_s4_handoff_output"])
    summary_rel = config.get("global_s4_handoff_summary")
    if isinstance(summary_rel, str) and summary_rel.strip():
        output_summary = _assert_output_allowed(root, summary_rel)
    else:
        output_summary = output_csv.with_name(
            output_csv.stem.replace("_input", "_handoff_summary") + ".md"
        )
        if output_summary == output_csv:
            output_summary = output_csv.with_name(
                output_csv.stem + "_handoff_summary.md"
            )
        output_summary = _assert_output_allowed(root, output_summary)

    for path in (canonical_path, resolution_path, authorised_ids_path):
        try:
            path.resolve().relative_to((root / "data" / "raw").resolve())
        except ValueError:
            continue
        raise GlobalS4HandoffError(
            f"Global-S4 handoff must not read raw source data: {path}"
        )

    before_hashes = {
        "canonical": sha256_file(canonical_path),
        "resolutions": sha256_file(resolution_path),
        "authorised_ids": sha256_file(authorised_ids_path),
    }

    canonical_rows = _read_csv(canonical_path, label="S3 canonical")
    resolution_rows = _read_csv(resolution_path, label="CHECKPOINT-1 resolutions")
    authorised_id_rows = _read_csv(authorised_ids_path, label="authorised-ID file")

    canon_ids = _unique_ids(canonical_rows, label="S3 canonical")
    resolution_ids = _unique_ids(resolution_rows, label="CHECKPOINT-1 resolutions")
    if set(canon_ids) != set(resolution_ids):
        missing = sorted(set(canon_ids) - set(resolution_ids))
        extra = sorted(set(resolution_ids) - set(canon_ids))
        parts: list[str] = []
        if missing:
            parts.append(f"missing_resolution={missing[:5]}")
        if extra:
            parts.append(f"extra_resolution={extra[:5]}")
        raise GlobalS4HandoffError(
            "S3 canonical and resolution ID sets disagree; " + "; ".join(parts)
        )

    authorised_resolutions = _select_authorised_resolutions(
        resolution_rows,
        authorisation_field=str(config["authorisation_field"]),
    )
    authorised_id_set = _align_authorised_id_sets(
        authorised_resolutions=authorised_resolutions,
        authorised_id_rows=authorised_id_rows,
    )
    expected = int(config["expected_authorised_records"])
    if len(authorised_id_set) != expected:
        raise GlobalS4HandoffError(
            f"Expected {expected} authorised records; got {len(authorised_id_set)}"
        )

    handoff_rows = _select_canonical_subset(canonical_rows, authorised_id_set)
    if len(handoff_rows) != expected:
        raise GlobalS4HandoffError(
            f"Expected {expected} handoff rows; got {len(handoff_rows)}"
        )
    unique_ids = _unique_ids(handoff_rows, label="handoff output")
    if set(unique_ids) != authorised_id_set:
        raise GlobalS4HandoffError(
            "Handoff record IDs must exactly equal the authorised-ID set"
        )
    expected_order = [
        row["record_id"]
        for row in canonical_rows
        if row["record_id"] in authorised_id_set
    ]
    if unique_ids != expected_order:
        raise GlobalS4HandoffError(
            "Handoff record order must preserve S3 canonical order"
        )
    _assert_exact_subset_fields(handoff_rows, canonical_rows)

    extra_columns = _join_handoff_source_metadata(
        repo_root=root,
        config=config,
        handoff_rows=handoff_rows,
    )

    # Ensure we did not invent later-stage values.
    for row in handoff_rows:
        for field_name in FORBIDDEN_MUTATION_FIELDS:
            # Values may already be empty from S3; they must stay equal to S3.
            _ = row.get(field_name, "")

    target_meta = config.get("target_metadata")
    specific_present: int | None = None
    specific_missing: int | None = None
    if isinstance(target_meta, dict):
        present = target_meta.get("specific_target_present_in_authorised_records")
        missing = target_meta.get("specific_target_missing_in_authorised_records")
        if isinstance(present, int):
            specific_present = present
        if isinstance(missing, int):
            specific_missing = missing

    observations = config.get("provisional_source_observations")
    category_observations: dict[str, int] = {}
    if isinstance(observations, dict):
        for key, value in observations.items():
            if not isinstance(key, str):
                raise GlobalS4HandoffError(
                    "provisional_source_observations keys must be strings"
                )
            if not isinstance(value, int):
                raise GlobalS4HandoffError(
                    "provisional_source_observations values must be integers"
                )
            category_observations[key] = value

    stats = HandoffStats(
        source_key=str(config["source_key"]),
        s3_records=len(canonical_rows),
        resolution_records=len(resolution_rows),
        authorised_ids=len(authorised_id_set),
        handoff_records=len(handoff_rows),
        unique_handoff_ids=len(unique_ids),
        target_specific_present=specific_present,
        target_specific_missing=specific_missing,
        category_observations=category_observations,
    )

    try:
        if extra_columns:
            write_corpus_csv_atomic(
                output_csv,
                handoff_rows,
                columns=list(CORPUS_COLUMNS) + extra_columns,
            )
        else:
            write_corpus_csv_atomic(output_csv, handoff_rows)
    except CorpusSchemaError as exc:
        raise GlobalS4HandoffError(str(exc)) from exc

    result = HandoffResult(
        source_key=stats.source_key,
        stats=stats,
        output_csv=output_csv,
        output_summary=output_summary,
        integrity_ok=False,
    )
    summary_text = build_handoff_summary(
        repo_root=root, result=result, config=config
    )
    abs_root = str(root.resolve())
    if abs_root in summary_text:
        raise GlobalS4HandoffError(
            "Handoff summary must not contain absolute repository paths"
        )
    _write_text_atomic(output_summary, summary_text)

    if verify_input_integrity:
        after_hashes = {
            "canonical": sha256_file(canonical_path),
            "resolutions": sha256_file(resolution_path),
            "authorised_ids": sha256_file(authorised_ids_path),
        }
        if after_hashes != before_hashes:
            raise GlobalS4HandoffError(
                "Input artefacts were modified during global-S4 handoff"
            )

    return HandoffResult(
        source_key=stats.source_key,
        stats=stats,
        output_csv=output_csv,
        output_summary=output_summary,
        integrity_ok=True,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare one CHECKPOINT-1-authorised source subset for the future "
            "corpus-wide S4 merge. Does not normalise targets or begin "
            "CHECKPOINT-2 / S5."
        )
    )
    parser.add_argument(
        "--source-config",
        type=Path,
        required=True,
        help="Repo-relative global-S4 source config JSON",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detected)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.repo_root or find_repo_root()
    result = prepare_global_s4_source(
        source_config=args.source_config,
        repo_root=root,
    )
    print(
        f"global-S4 handoff ready: source={result.source_key} "
        f"rows={result.stats.handoff_records}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GlobalS4HandoffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

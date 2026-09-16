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
        "aptamerbase_sequence",
        "ncbi_nuc_origin_residues",
        "aptadb_interaction_sequence",
        "aptadb_aptamer_sequence",
        "aptaindex_sequence",
        "sequence",
    }
)

VALUE_COUNT_KEY_PREFIX = "vc:"
SOURCE_METADATA_COUNT_PREFIXES: tuple[str, ...] = (
    "unique_",
    "nonempty_",
    "true_",
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
        # AptaDB's closed CHECKPOINT-1 manifest records status/authorisation
        # without a separate resolved_decision column. Blank is accepted
        # only when checkpoint1_resolution_status is already approved_for_s4.
        if resolved not in {"", "accept"}:
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


@dataclass(frozen=True)
class MetadataJoinSpec:
    """One source-metadata CSV joined onto handoff rows by record_id."""

    path: Path
    fields: tuple[str, ...]
    aliases: Mapping[str, str]
    label: str


def _sidecar_metadata_path(
    repo_root: Path, config: Mapping[str, Any]
) -> Path | None:
    extra_raw = config.get("handoff_extra_fields")
    if extra_raw in (None, [], ()):
        return None
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
    return _resolve_under_repo(repo_root, sidecar_rel)


def _parse_string_list(raw: Any, *, label: str) -> list[str]:
    if raw in (None, [], ()):
        return []
    if not isinstance(raw, list) or not all(
        isinstance(item, str) and item.strip() for item in raw
    ):
        raise GlobalS4HandoffError(f"{label} must be a list of nonempty strings")
    return [item.strip() for item in raw]


def _parse_alias_map(raw: Any, *, label: str) -> dict[str, str]:
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise GlobalS4HandoffError(
            f"{label} must be an object mapping field names to output columns"
        )
    aliases: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise GlobalS4HandoffError(f"{label} keys must be nonempty strings")
        if not isinstance(value, str) or not value.strip():
            raise GlobalS4HandoffError(
                f"{label} values must be nonempty strings"
            )
        aliases[key.strip()] = value.strip()
    return aliases


def _assert_repo_relative_path(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GlobalS4HandoffError(f"{label} must be a nonempty string path")
    if value.startswith("/") or (len(value) > 2 and value[1] == ":"):
        raise GlobalS4HandoffError(f"{label} must be a repo-relative path")
    return value.strip()


def _parse_additional_metadata_joins(
    repo_root: Path, config: Mapping[str, Any]
) -> list[MetadataJoinSpec]:
    raw = config.get("additional_source_metadata_joins")
    if raw in (None, [], ()):
        return []
    if not isinstance(raw, list):
        raise GlobalS4HandoffError(
            "additional_source_metadata_joins must be a list of objects"
        )
    specs: list[MetadataJoinSpec] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise GlobalS4HandoffError(
                f"additional_source_metadata_joins[{index}] must be an object"
            )
        path_rel = _assert_repo_relative_path(
            str(item.get("path") or ""),
            label=f"additional_source_metadata_joins[{index}].path",
        )
        fields = tuple(
            _parse_string_list(
                item.get("fields"),
                label=f"additional_source_metadata_joins[{index}].fields",
            )
        )
        if not fields:
            raise GlobalS4HandoffError(
                f"additional_source_metadata_joins[{index}].fields must be nonempty"
            )
        aliases = _parse_alias_map(
            item.get("aliases"),
            label=f"additional_source_metadata_joins[{index}].aliases",
        )
        specs.append(
            MetadataJoinSpec(
                path=_resolve_under_repo(repo_root, path_rel),
                fields=fields,
                aliases=aliases,
                label=f"additional source-metadata join {index}",
            )
        )
    return specs


def _all_metadata_join_specs(
    repo_root: Path, config: Mapping[str, Any]
) -> list[MetadataJoinSpec]:
    specs: list[MetadataJoinSpec] = []
    extra_fields = _parse_string_list(
        config.get("handoff_extra_fields"), label="handoff_extra_fields"
    )
    if extra_fields:
        sidecar_path = _sidecar_metadata_path(repo_root, config)
        if sidecar_path is None:
            raise GlobalS4HandoffError(
                "handoff_extra_fields requires source_metadata_path"
            )
        specs.append(
            MetadataJoinSpec(
                path=sidecar_path,
                fields=tuple(extra_fields),
                aliases=_parse_extra_field_aliases(config),
                label="source-metadata sidecar",
            )
        )
    specs.extend(_parse_additional_metadata_joins(repo_root, config))
    return specs


def _watched_metadata_paths(repo_root: Path, config: Mapping[str, Any]) -> list[Path]:
    return [spec.path for spec in _all_metadata_join_specs(repo_root, config)]


def _parse_extra_field_aliases(config: Mapping[str, Any]) -> dict[str, str]:
    return _parse_alias_map(
        config.get("handoff_extra_field_aliases"),
        label="handoff_extra_field_aliases",
    )


def _extra_output_name(sidecar_field: str, aliases: Mapping[str, str]) -> str:
    return aliases.get(sidecar_field, sidecar_field)


def _index_metadata_rows(
    path: Path, *, label: str
) -> dict[str, dict[str, str]]:
    if not path.is_file():
        raise GlobalS4HandoffError(
            f"Missing source-metadata sidecar for handoff: {path.name}"
        )
    rows = _read_csv(path, label=label)
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        record_id = (row.get("record_id") or "").strip()
        if not record_id:
            raise GlobalS4HandoffError(f"{label} row has blank record_id")
        if record_id in by_id:
            raise GlobalS4HandoffError(
                f"{label} contains duplicate record_id={record_id!r}"
            )
        by_id[record_id] = row
    return by_id


def _join_one_metadata_spec(
    *,
    spec: MetadataJoinSpec,
    handoff_rows: list[dict[str, str]],
    seen_output: set[str],
) -> list[str]:
    output_columns: list[str] = []
    for sidecar_field in spec.fields:
        output_name = _extra_output_name(sidecar_field, spec.aliases)
        if sidecar_field in SEQUENCE_BEARING_HANDOFF_EXTRAS or (
            output_name in SEQUENCE_BEARING_HANDOFF_EXTRAS
        ):
            raise GlobalS4HandoffError(
                "handoff_extra_fields must not repeat corpus columns or "
                f"sequence-bearing sidecar fields: {[sidecar_field]}"
            )
        if output_name in CORPUS_COLUMNS:
            raise GlobalS4HandoffError(
                f"Handoff extra {sidecar_field!r} would overwrite corpus "
                f"column {output_name!r}; provide handoff_extra_field_aliases"
            )
        if output_name in seen_output:
            raise GlobalS4HandoffError(
                f"Handoff extra output column {output_name!r} is duplicated"
            )
        seen_output.add(output_name)
        output_columns.append(output_name)
    by_id = _index_metadata_rows(spec.path, label=spec.label)
    for row in handoff_rows:
        record_id = row["record_id"]
        if record_id not in by_id:
            raise GlobalS4HandoffError(
                f"Authorised handoff record missing from source metadata: {record_id}"
            )
        meta = by_id[record_id]
        for sidecar_field in spec.fields:
            if sidecar_field not in meta:
                raise GlobalS4HandoffError(
                    f"{spec.label} missing handoff field {sidecar_field!r}"
                )
            output_name = _extra_output_name(sidecar_field, spec.aliases)
            row[output_name] = meta.get(sidecar_field) or ""
    return output_columns


def _join_handoff_source_metadata(
    *,
    repo_root: Path,
    config: Mapping[str, Any],
    handoff_rows: list[dict[str, str]],
) -> list[str]:
    """Join configured sequence-safe source-metadata fields onto handoff rows."""
    join_key = str(config.get("physical_row_join_key") or "record_id").strip()
    if join_key != "record_id":
        raise GlobalS4HandoffError("physical_row_join_key must be record_id")
    specs = _all_metadata_join_specs(repo_root, config)
    if not specs:
        return []
    output_columns: list[str] = []
    seen_output: set[str] = set()
    for spec in specs:
        output_columns.extend(
            _join_one_metadata_spec(
                spec=spec,
                handoff_rows=handoff_rows,
                seen_output=seen_output,
            )
        )
    return output_columns


def _assert_required_nonempty_fields(
    rows: Sequence[Mapping[str, str]],
    fields: Sequence[str],
) -> None:
    for field_name in fields:
        for row in rows:
            if not (row.get(field_name) or "").strip():
                raise GlobalS4HandoffError(
                    f"Handoff field {field_name!r} is required and nonempty; "
                    f"blank on {row.get('record_id')!r}"
                )


def _assert_required_empty_fields(
    rows: Sequence[Mapping[str, str]],
    fields: Sequence[str],
) -> None:
    for field_name in fields:
        for row in rows:
            if (row.get(field_name) or "").strip():
                raise GlobalS4HandoffError(
                    f"Canonical field {field_name!r} must remain empty on "
                    f"handoff for {row.get('record_id')!r}"
                )


def _provenance_counts(
    config: Mapping[str, Any],
    handoff_rows: Sequence[Mapping[str, str]],
) -> dict[str, int]:
    """Derive sequence-free provenance counters requested by source config."""
    spec = config.get("handoff_summary_provenance_counts")
    if not isinstance(spec, dict) or not spec:
        return {}
    counts: dict[str, int] = {}
    blank_field = spec.get("source_family_blank_field")
    if isinstance(blank_field, str) and blank_field.strip():
        true_val = str(spec.get("source_family_blank_true_value") or "true")
        counts["materialised_singletons"] = sum(
            1
            for row in handoff_rows
            if (row.get(blank_field) or "") == true_val
        )
    family_field = spec.get("source_nonblank_family_field")
    if isinstance(family_field, str) and family_field.strip():
        counts["source_nonblank_family_rows"] = sum(
            1
            for row in handoff_rows
            if (row.get(family_field) or "").strip()
        )
    group_field = spec.get("primary_experiment_group_field")
    if isinstance(group_field, str) and group_field.strip():
        groups = {
            (row.get(group_field) or "").strip()
            for row in handoff_rows
            if (row.get(group_field) or "").strip()
        }
        counts["distinct_primary_experiment_groups"] = len(groups)
    trim_value = spec.get("trim_status_value")
    if isinstance(trim_value, str) and trim_value.strip():
        counts["trim_status_matches"] = sum(
            1
            for row in handoff_rows
            if (row.get("trim_status") or "") == trim_value
        )
    if spec.get("report_t_to_u_applied"):
        counts["t_to_u_applied"] = sum(
            1
            for row in handoff_rows
            if (row.get("t_to_u_applied") or "") == "true"
        )
    if spec.get("report_duplicate_sequence_identities"):
        full_counts: dict[str, int] = {}
        core_counts: dict[str, int] = {}
        for row in handoff_rows:
            full = row.get("sequence_full") or ""
            core = row.get("sequence_core") or ""
            if full:
                full_counts[full] = full_counts.get(full, 0) + 1
            if core:
                core_counts[core] = core_counts.get(core, 0) + 1
        dup_full = {value: n for value, n in full_counts.items() if n > 1}
        dup_core = {value: n for value, n in core_counts.items() if n > 1}
        counts["duplicate_sequence_full_values"] = len(dup_full)
        counts["duplicate_sequence_full_records"] = sum(dup_full.values())
        counts["duplicate_sequence_core_values"] = len(dup_core)
        counts["duplicate_sequence_core_records"] = sum(dup_core.values())
    unique_fields = _parse_string_list(
        spec.get("unique_count_fields"), label="unique_count_fields"
    )
    for field_name in unique_fields:
        values = {
            (row.get(field_name) or "").strip()
            for row in handoff_rows
            if (row.get(field_name) or "").strip()
        }
        counts[f"unique_{field_name}"] = len(values)
    duplicate_fields = _parse_string_list(
        spec.get("duplicate_group_fields"), label="duplicate_group_fields"
    )
    for field_name in duplicate_fields:
        tallies: dict[str, int] = {}
        for row in handoff_rows:
            value = (row.get(field_name) or "").strip()
            if not value:
                continue
            tallies[value] = tallies.get(value, 0) + 1
        dup = {value: n for value, n in tallies.items() if n > 1}
        counts[f"duplicate_{field_name}_groups"] = len(dup)
        counts[f"duplicate_{field_name}_rows"] = sum(dup.values())
    nonempty_fields = _parse_string_list(
        spec.get("nonempty_count_fields"), label="nonempty_count_fields"
    )
    for field_name in nonempty_fields:
        counts[f"nonempty_{field_name}"] = sum(
            1
            for row in handoff_rows
            if (row.get(field_name) or "").strip()
        )
    true_fields = _parse_string_list(
        spec.get("true_value_count_fields"), label="true_value_count_fields"
    )
    for field_name in true_fields:
        counts[f"true_{field_name}"] = sum(
            1
            for row in handoff_rows
            if (row.get(field_name) or "").strip() == "true"
        )
    value_fields = _parse_string_list(
        spec.get("value_count_fields"), label="value_count_fields"
    )
    for field_name in value_fields:
        field_tallies: dict[str, int] = {}
        for row in handoff_rows:
            value = (row.get(field_name) or "").strip() or "(blank)"
            field_tallies[value] = field_tallies.get(value, 0) + 1
        for value, n in sorted(field_tallies.items()):
            counts[f"{VALUE_COUNT_KEY_PREFIX}{field_name}:{value}"] = n
    return counts


def _is_source_metadata_count_key(key: str) -> bool:
    if key.startswith("duplicate_sequence_"):
        return False
    if key.startswith(SOURCE_METADATA_COUNT_PREFIXES):
        return True
    return key.startswith("duplicate_")


def _source_metadata_count_label(key: str) -> str:
    if key.startswith("unique_"):
        return f"unique {key[len('unique_'):].replace('_', ' ')}"
    if key.startswith("nonempty_"):
        return f"nonempty {key[len('nonempty_'):].replace('_', ' ')}"
    if key.startswith("true_"):
        return f"true {key[len('true_'):].replace('_', ' ')}"
    if key.startswith("duplicate_") and key.endswith("_groups"):
        field = key[len("duplicate_") : -len("_groups")]
        return f"duplicated {field.replace('_', ' ')} groups"
    if key.startswith("duplicate_") and key.endswith("_rows"):
        field = key[len("duplicate_") : -len("_rows")]
        return f"rows in duplicated {field.replace('_', ' ')} groups"
    return key.replace("_", " ")


def build_handoff_summary(
    *,
    repo_root: Path,
    result: HandoffResult,
    config: Mapping[str, Any],
    provenance_counts: Mapping[str, int] | None = None,
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
    provenance = dict(provenance_counts or {})
    custom_labels_raw = config.get("handoff_summary_count_labels")
    custom_labels = (
        custom_labels_raw if isinstance(custom_labels_raw, dict) else {}
    )
    labels = {
        "materialised_singletons": "materialised singletons",
        "source_nonblank_family_rows": "source-nonblank family rows",
        "distinct_primary_experiment_groups": (
            "distinct primary experiment groups"
        ),
        "trim_status_matches": "reviewed trimmed records",
        "t_to_u_applied": "T-transcribed records",
        "duplicate_sequence_full_values": "duplicate sequence_full values",
        "duplicate_sequence_full_records": (
            "records sharing a duplicate sequence_full"
        ),
        "duplicate_sequence_core_values": "duplicate sequence_core values",
        "duplicate_sequence_core_records": (
            "records sharing a duplicate sequence_core"
        ),
    }
    for key, value in custom_labels.items():
        if isinstance(key, str) and isinstance(value, str) and value.strip():
            labels[key] = value.strip()
    core_counts = {
        key: count
        for key, count in provenance.items()
        if not key.startswith(VALUE_COUNT_KEY_PREFIX)
        and not _is_source_metadata_count_key(key)
    }
    if core_counts:
        lines.extend(["", "## Authorised-lane provenance counts", ""])
        for key, count in core_counts.items():
            label = labels.get(key, key.replace("_", " "))
            lines.append(f"- {label} = `{count}`")
        if "duplicate_sequence_full_values" in core_counts:
            lines.append(
                "- diagnostic only — no deduplication performed"
            )
    technical_counts: dict[str, dict[str, int]] = {}
    for key, count in provenance.items():
        if not key.startswith(VALUE_COUNT_KEY_PREFIX):
            continue
        remainder = key[len(VALUE_COUNT_KEY_PREFIX) :]
        field_name, _, value = remainder.partition(":")
        if not field_name or not value:
            continue
        technical_counts.setdefault(field_name, {})[value] = count
    if technical_counts:
        lines.extend(["", "## Authorised-lane technical observations", ""])
        for field_name, value_counts in technical_counts.items():
            for value, count in value_counts.items():
                lines.append(f"- `{field_name}` `{value}` = `{count}`")
        lines.append("- derived from the authorised applied subset")
    source_meta_counts = {
        key: count
        for key, count in provenance.items()
        if _is_source_metadata_count_key(key)
    }
    if source_meta_counts or bool(
        config.get("emit_source_metadata_only_disclaimer")
    ):
        lines.extend(
            [
                "",
                "## SOURCE METADATA ONLY — NOT CANONICAL TARGET/EVIDENCE DECISIONS",
                "",
            ]
        )
        for key, count in source_meta_counts.items():
            label = labels.get(key, _source_metadata_count_label(key))
            lines.append(f"- {label} = `{count}`")
        lines.append(
            "- These are source metadata observations only. They are not "
            "canonical target names, UniProt, PDB, evidence scores, or "
            "deduplication decisions."
        )
        if "duplicate_aptamerbase_id_groups" in source_meta_counts:
            lines.append(
                "- duplicated Freebase IDs are diagnostic only — physical "
                "rows were not collapsed"
            )
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
    additional_joins = config.get("additional_source_metadata_joins")
    has_primary_extras = isinstance(extra_fields, list) and extra_fields
    has_additional = isinstance(additional_joins, list) and additional_joins
    if has_primary_extras or has_additional:
        aliases = _parse_extra_field_aliases(config)
        lines.extend(
            [
                "## Source-metadata fields joined onto the handoff",
                "",
            ]
        )
        if has_primary_extras:
            for field_name in extra_fields:
                output_name = _extra_output_name(str(field_name), aliases)
                if output_name != field_name:
                    lines.append(f"- `{field_name}` → `{output_name}`")
                else:
                    lines.append(f"- `{field_name}`")
            target_meta = config.get("target_metadata")
            sidecar = ""
            if isinstance(target_meta, dict):
                sidecar = str(target_meta.get("source_metadata_path") or "")
            if sidecar:
                lines.append(f"- source-metadata linkage: `{sidecar}`")
        if has_additional:
            for item in additional_joins:
                if not isinstance(item, dict):
                    continue
                item_aliases = _parse_alias_map(
                    item.get("aliases"), label="additional join aliases"
                )
                for field_name in item.get("fields") or []:
                    if not isinstance(field_name, str):
                        continue
                    output_name = _extra_output_name(field_name, item_aliases)
                    if output_name != field_name:
                        lines.append(f"- `{field_name}` → `{output_name}`")
                    else:
                        lines.append(f"- `{field_name}`")
                extra_path = str(item.get("path") or "").strip()
                if extra_path:
                    lines.append(
                        f"- additional source-metadata linkage: `{extra_path}`"
                    )
        lines.append("")
    enrichment = config.get("future_enrichment_join")
    if isinstance(enrichment, dict) and enrichment:
        lines.extend(["## Future source-metadata join key", ""])
        join_path = str(enrichment.get("join_path") or "").strip()
        if join_path:
            lines.append(f"- {join_path}")
        freebase_field = str(
            enrichment.get("source_freebase_id_field") or ""
        ).strip()
        if freebase_field:
            lines.append(
                f"- Freebase ID field: `{freebase_field}` "
                "(source provenance / future source-metadata join key)"
            )
        physical_key = str(
            enrichment.get("physical_row_key") or "record_id"
        ).strip()
        lines.append(f"- physical-row reconciliation key: `{physical_key}`")
        not_list = enrichment.get("freebase_id_is_not")
        if isinstance(not_list, list) and not_list:
            rendered = ", ".join(
                f"`{item}`" if isinstance(item, str) else str(item)
                for item in not_list
            )
            lines.append(f"- Freebase ID is not: {rendered}")
        lines.append("")
    prereqs = config.get("future_global_s4_prerequisites")
    if isinstance(prereqs, list) and prereqs:
        lines.extend(["## Future global-S4 prerequisites", ""])
        for note in prereqs:
            if isinstance(note, str) and note.strip():
                lines.append(f"- {note.strip()}")
        lines.append("")
    extra_notes = config.get("handoff_summary_additional_notes")
    if isinstance(extra_notes, list) and extra_notes:
        lines.extend(["## authorised_for_s4 meaning", ""])
        for note in extra_notes:
            if isinstance(note, str) and note.strip():
                lines.append(f"- {note.strip()}")
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

    metadata_paths = _watched_metadata_paths(root, config)
    watched_paths = [
        canonical_path,
        resolution_path,
        authorised_ids_path,
        *metadata_paths,
    ]
    for path in watched_paths:
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
    for index, meta_path in enumerate(metadata_paths):
        if not meta_path.is_file():
            raise GlobalS4HandoffError(
                f"Missing source-metadata sidecar for handoff: {meta_path.name}"
            )
        key = "source_metadata" if index == 0 else f"source_metadata_{index}"
        before_hashes[key] = sha256_file(meta_path)

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
    _assert_exact_subset_fields(handoff_rows, canonical_rows)
    _assert_required_nonempty_fields(
        handoff_rows,
        _parse_string_list(
            config.get("required_nonempty_handoff_fields"),
            label="required_nonempty_handoff_fields",
        ),
    )
    _assert_required_empty_fields(
        handoff_rows,
        _parse_string_list(
            config.get("require_empty_canonical_fields"),
            label="require_empty_canonical_fields",
        ),
    )

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

    quoting = csv.QUOTE_MINIMAL
    if any("\r" in (value or "") for row in handoff_rows for value in row.values()):
        # AptaIndex (and any other CR-bearing extras) must match S1/S2/S3
        # QUOTE_ALL so bare CR cannot split physical rows on disk.
        quoting = csv.QUOTE_ALL
    try:
        if extra_columns:
            write_corpus_csv_atomic(
                output_csv,
                handoff_rows,
                columns=list(CORPUS_COLUMNS) + extra_columns,
                quoting=quoting,
            )
        else:
            write_corpus_csv_atomic(output_csv, handoff_rows, quoting=quoting)
    except CorpusSchemaError as exc:
        raise GlobalS4HandoffError(str(exc)) from exc
    written_ids = _unique_ids(
        _read_csv(output_csv, label="handoff output"),
        label="handoff output",
    )
    if written_ids != unique_ids:
        raise GlobalS4HandoffError(
            "Handoff CSV did not round-trip the authorised record_id order"
        )

    result = HandoffResult(
        source_key=stats.source_key,
        stats=stats,
        output_csv=output_csv,
        output_summary=output_summary,
        integrity_ok=False,
    )
    provenance_counts = _provenance_counts(config, handoff_rows)
    summary_text = build_handoff_summary(
        repo_root=root,
        result=result,
        config=config,
        provenance_counts=provenance_counts,
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
        for index, meta_path in enumerate(metadata_paths):
            key = "source_metadata" if index == 0 else f"source_metadata_{index}"
            after_hashes[key] = sha256_file(meta_path)
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

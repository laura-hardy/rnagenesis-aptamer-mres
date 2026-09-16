#!/usr/bin/env python3
"""Combine authorised source-local global-S4 handoffs into one pre-S4 input.

Row-preserving concatenation in explicit configured source order. Does not
merge records, collapse sequences, canonicalise targets, assign evidence,
apply leakage, or begin CHECKPOINT-2 / S5.
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

SEQ_LEAK_RE_PATTERN = r"[ACGTUacgtu]{20,}"

REQUIRED_COMBINED_KEYS: frozenset[str] = frozenset(
    {
        "contract_id",
        "expected_combined_records",
        "output_csv",
        "output_summary",
        "contributing_sources",
    }
)

REQUIRED_SOURCE_POINTER_KEYS: frozenset[str] = frozenset(
    {
        "source_key",
        "expected_authorised_records",
        "global_s4_handoff_output",
    }
)


class CombinedInputError(ValueError):
    """Hard failure while combining global-S4 source handoffs."""


@dataclass(frozen=True)
class ContributingSource:
    """One positive-count source in configured combination order."""

    source_key: str
    source_config: str
    expected_records: int
    record_id_prefix: str
    require_redistribution_status: str | None
    principal_extra_fields: tuple[str, ...]


@dataclass(frozen=True)
class ZeroAuthorisedSource:
    """Closed source that must not contribute fabricated rows."""

    source_key: str
    expected_records: int
    status: str


@dataclass(frozen=True)
class SourceBlock:
    """Loaded handoff rows for one contributing source."""

    spec: ContributingSource
    rows: tuple[dict[str, str], ...]
    extras: tuple[str, ...]
    path: Path
    sha256: str
    start_row: int
    end_row: int


@dataclass(frozen=True)
class CombinedResult:
    """Paths and aggregates from one combination run."""

    combined_rows: int
    unique_ids: int
    extra_columns: tuple[str, ...]
    output_csv: Path
    output_summary: Path
    output_manifest: Path | None
    csv_sha256: str
    summary_sha256: str
    manifest_sha256: str | None
    input_hashes: Mapping[str, str]
    source_boundaries: Mapping[str, Mapping[str, int]]


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


def _assert_repo_relative(value: str, *, key: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CombinedInputError(f"{key} must be a nonempty string path")
    if value.startswith("/") or (len(value) > 2 and value[1] == ":"):
        raise CombinedInputError(f"{key} must be a repo-relative path")


def _assert_output_allowed(repo_root: Path, output_path: Path | str) -> Path:
    _assert_repo_relative(str(output_path), key="output path")
    resolved = _resolve_under_repo(repo_root, output_path)
    interim_root = (repo_root / "data" / "interim").resolve()
    try:
        resolved.relative_to(interim_root)
    except ValueError as exc:
        raise CombinedInputError(
            f"Combined output must lie beneath data/interim/: {output_path}"
        ) from exc
    raw_root = (repo_root / "data" / "raw").resolve()
    try:
        resolved.relative_to(raw_root)
    except ValueError:
        pass
    else:
        raise CombinedInputError(
            f"Refusing to write combined input under data/raw/: {output_path}"
        )
    ready_root = (repo_root / "data" / "interim" / "global_s4_ready").resolve()
    try:
        resolved.relative_to(ready_root)
    except ValueError:
        pass
    else:
        raise CombinedInputError(
            "Combined input must not be written under "
            f"data/interim/global_s4_ready/: {output_path}"
        )
    return resolved


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


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CombinedInputError(f"Invalid JSON {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise CombinedInputError(f"{label} root must be an object: {path}")
    return payload


def _parse_string_list(raw: Any, *, label: str) -> list[str]:
    if raw in (None, [], ()):
        return []
    if not isinstance(raw, list):
        raise CombinedInputError(f"{label} must be a list of strings")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise CombinedInputError(f"{label} entries must be nonempty strings")
        values.append(item)
    return values


def _load_source_pointer(path: Path) -> dict[str, Any]:
    payload = _read_json(path, label="source handoff config")
    missing = sorted(REQUIRED_SOURCE_POINTER_KEYS - set(payload))
    if missing:
        raise CombinedInputError(
            f"Source config missing required keys: {', '.join(missing)}"
        )
    source_key = payload.get("source_key")
    if not isinstance(source_key, str) or not source_key.strip():
        raise CombinedInputError("source_key must be a nonempty string")
    expected = payload.get("expected_authorised_records")
    if not isinstance(expected, int) or expected < 0:
        raise CombinedInputError(
            "expected_authorised_records must be a non-negative integer"
        )
    handoff = payload.get("global_s4_handoff_output")
    _assert_repo_relative(str(handoff), key="global_s4_handoff_output")
    return payload


def _parse_contributing_source(item: Any, *, index: int) -> ContributingSource:
    if not isinstance(item, dict):
        raise CombinedInputError(
            f"contributing_sources[{index}] must be an object"
        )
    source_key = item.get("source_key")
    if not isinstance(source_key, str) or not source_key.strip():
        raise CombinedInputError(
            f"contributing_sources[{index}].source_key must be a nonempty string"
        )
    source_config = item.get("source_config")
    _assert_repo_relative(str(source_config), key="source_config")
    expected = item.get("expected_records")
    if not isinstance(expected, int) or expected <= 0:
        raise CombinedInputError(
            f"contributing_sources[{index}].expected_records must be a "
            "positive integer"
        )
    prefix = item.get("record_id_prefix")
    if not isinstance(prefix, str) or not prefix.strip():
        raise CombinedInputError(
            f"contributing_sources[{index}].record_id_prefix must be a "
            "nonempty string"
        )
    required_status = item.get("require_redistribution_status")
    if required_status is not None:
        if not isinstance(required_status, str) or not required_status.strip():
            raise CombinedInputError(
                f"contributing_sources[{index}].require_redistribution_status "
                "must be a nonempty string when present"
            )
    extras = tuple(
        _parse_string_list(
            item.get("principal_extra_fields"),
            label=f"contributing_sources[{index}].principal_extra_fields",
        )
    )
    return ContributingSource(
        source_key=source_key,
        source_config=str(source_config),
        expected_records=expected,
        record_id_prefix=prefix,
        require_redistribution_status=(
            required_status.strip() if isinstance(required_status, str) else None
        ),
        principal_extra_fields=extras,
    )


def _parse_zero_authorised(item: Any, *, index: int) -> ZeroAuthorisedSource:
    if not isinstance(item, dict):
        raise CombinedInputError(
            f"zero_authorised_sources[{index}] must be an object"
        )
    source_key = item.get("source_key")
    if not isinstance(source_key, str) or not source_key.strip():
        raise CombinedInputError(
            f"zero_authorised_sources[{index}].source_key must be a nonempty string"
        )
    expected = item.get("expected_records", 0)
    if expected != 0:
        raise CombinedInputError(
            f"zero_authorised_sources[{index}].expected_records must be 0"
        )
    if item.get("contribute_rows") is True:
        raise CombinedInputError(
            f"zero_authorised_sources[{index}] must not contribute rows"
        )
    status = str(item.get("status") or "ready_zero_authorised")
    return ZeroAuthorisedSource(
        source_key=source_key,
        expected_records=0,
        status=status,
    )


def load_combined_config(path: Path) -> dict[str, Any]:
    """Load and validate the tracked combined-input contract."""
    payload = _read_json(path, label="combined-input config")
    missing = sorted(REQUIRED_COMBINED_KEYS - set(payload))
    if missing:
        raise CombinedInputError(
            f"Combined config missing required keys: {', '.join(missing)}"
        )
    expected = payload.get("expected_combined_records")
    if not isinstance(expected, int) or expected <= 0:
        raise CombinedInputError(
            "expected_combined_records must be a positive integer"
        )
    sources_raw = payload.get("contributing_sources")
    if not isinstance(sources_raw, list) or not sources_raw:
        raise CombinedInputError(
            "contributing_sources must be a nonempty list in configured order"
        )
    sources = [
        _parse_contributing_source(item, index=index)
        for index, item in enumerate(sources_raw)
    ]
    keys = [spec.source_key for spec in sources]
    if len(keys) != len(set(keys)):
        raise CombinedInputError("contributing_sources keys must be unique")
    zero_raw = payload.get("zero_authorised_sources") or []
    if not isinstance(zero_raw, list):
        raise CombinedInputError("zero_authorised_sources must be a list")
    zeros = [
        _parse_zero_authorised(item, index=index)
        for index, item in enumerate(zero_raw)
    ]
    zero_keys = [item.source_key for item in zeros]
    if len(zero_keys) != len(set(zero_keys)):
        raise CombinedInputError("zero_authorised_sources keys must be unique")
    overlap = sorted(set(keys) & set(zero_keys))
    if overlap:
        raise CombinedInputError(
            "source cannot be both contributing and zero-authorised: "
            + ", ".join(overlap)
        )
    total = sum(spec.expected_records for spec in sources)
    if total != expected:
        raise CombinedInputError(
            f"Sum of contributing expected_records ({total}) != "
            f"expected_combined_records ({expected})"
        )
    payload["_parsed_sources"] = sources
    payload["_parsed_zeros"] = zeros
    return payload


def _read_handoff_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise CombinedInputError(f"Missing required source handoff: {path.name}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise CombinedInputError(f"Handoff CSV has no header: {path.name}")
        fieldnames = list(reader.fieldnames)
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        for key, value in list(row.items()):
            row[key] = "" if value is None else value
        if not (row.get("record_id") or "").strip():
            raise CombinedInputError(
                f"{path.name} row {index} has blank record_id"
            )
    return fieldnames, rows


def _split_handoff_columns(fieldnames: Sequence[str], *, label: str) -> list[str]:
    expected = list(CORPUS_COLUMNS)
    actual = list(fieldnames)
    if actual[: len(expected)] != expected:
        raise CombinedInputError(
            f"{label} canonical columns must match CORPUS_COLUMNS in order"
        )
    extras = actual[len(expected) :]
    seen: set[str] = set()
    for column in extras:
        if column in CORPUS_COLUMNS:
            raise CombinedInputError(
                f"{label} extra {column!r} collides with a canonical column; "
                "refusing to combine"
            )
        if column in seen:
            raise CombinedInputError(
                f"{label} repeats extra column {column!r}"
            )
        seen.add(column)
    return extras


def _union_extra_columns(
    blocks: Sequence[tuple[str, Sequence[str]]],
) -> list[str]:
    seen = set(CORPUS_COLUMNS)
    extras: list[str] = []
    for source_key, source_extras in blocks:
        for column in source_extras:
            if column in CORPUS_COLUMNS:
                raise CombinedInputError(
                    f"Source {source_key} extra {column!r} collides with a "
                    "canonical column; refusing to combine"
                )
            if column in seen:
                raise CombinedInputError(
                    f"Incompatible extra-column collision: {column!r} already "
                    f"present when reading source {source_key}"
                )
            seen.add(column)
            extras.append(column)
    return extras


def _nonempty_count(rows: Sequence[Mapping[str, str]], field: str) -> int:
    return sum(1 for row in rows if (row.get(field) or "").strip())


def _value_counts(
    rows: Sequence[Mapping[str, str]], field: str
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = (row.get(field) or "").strip() or "(blank)"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _duplication_diagnostic(
    rows: Sequence[Mapping[str, str]],
    source_order: Sequence[str],
) -> dict[str, Any]:
    core_counts: dict[str, int] = {}
    core_sources: dict[str, set[str]] = {}
    for row in rows:
        core = row.get("sequence_core") or ""
        if not core:
            continue
        core_counts[core] = core_counts.get(core, 0) + 1
        source = (row.get("source_db") or "").strip()
        core_sources.setdefault(core, set()).add(source)
    repeated = {value: n for value, n in core_counts.items() if n > 1}
    pair_counts: dict[str, int] = {}
    for left_index, left in enumerate(source_order):
        for right in source_order[left_index + 1 :]:
            shared = 0
            for sources in core_sources.values():
                if left in sources and right in sources:
                    shared += 1
            pair_counts[f"{left}|{right}"] = shared
    return {
        "label": "diagnostic only — no cross-source deduplication performed",
        "duplicate_sequence_core_values": len(repeated),
        "rows_participating": sum(repeated.values()),
        "source_pair_shared_sequence_core_values": pair_counts,
    }


def _assert_no_sequence_leak(text: str, *, label: str) -> None:
    import re

    if re.search(SEQ_LEAK_RE_PATTERN, text):
        raise CombinedInputError(
            f"{label} must not contain biological sequence strings"
        )


def _load_source_block(
    *,
    repo_root: Path,
    spec: ContributingSource,
    start_row: int,
) -> SourceBlock:
    config_path = _resolve_under_repo(repo_root, spec.source_config)
    if not config_path.is_file():
        raise CombinedInputError(
            f"Missing source handoff config: {spec.source_config}"
        )
    pointer = _load_source_pointer(config_path)
    if pointer["source_key"] != spec.source_key:
        raise CombinedInputError(
            f"Combined source_key {spec.source_key!r} disagrees with "
            f"{spec.source_config} source_key {pointer['source_key']!r}"
        )
    expected_authorised = int(pointer["expected_authorised_records"])
    if expected_authorised != spec.expected_records:
        raise CombinedInputError(
            f"{spec.source_key} expected_records {spec.expected_records} "
            f"disagrees with source config {expected_authorised}"
        )
    handoff_rel = str(pointer["global_s4_handoff_output"])
    handoff_path = _resolve_under_repo(repo_root, handoff_rel)
    fieldnames, rows = _read_handoff_csv(handoff_path)
    extras = _split_handoff_columns(
        fieldnames, label=f"{spec.source_key} handoff"
    )
    if len(rows) != spec.expected_records:
        raise CombinedInputError(
            f"{spec.source_key} handoff has {len(rows)} rows; expected "
            f"{spec.expected_records}"
        )
    for field_name in spec.principal_extra_fields:
        if field_name not in extras:
            raise CombinedInputError(
                f"{spec.source_key} principal extra {field_name!r} is absent "
                "from the source handoff"
            )
    ids: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        record_id = row["record_id"]
        if record_id in seen:
            raise CombinedInputError(
                f"{spec.source_key} duplicate record_id={record_id!r}"
            )
        seen.add(record_id)
        ids.append(record_id)
        if not record_id.startswith(spec.record_id_prefix):
            raise CombinedInputError(
                f"{spec.source_key} record_id {record_id!r} lacks prefix "
                f"{spec.record_id_prefix!r}"
            )
        if (row.get("source_db") or "") != spec.source_key:
            raise CombinedInputError(
                f"{spec.source_key} row {record_id!r} has source_db="
                f"{row.get('source_db')!r}"
            )
        required_status = spec.require_redistribution_status
        if required_status is not None:
            actual_status = row.get("redistribution_status") or ""
            if actual_status != required_status:
                raise CombinedInputError(
                    f"{spec.source_key} row {record_id!r} has "
                    f"redistribution_status={actual_status!r}; expected "
                    f"{required_status!r}"
                )
    end_row = start_row + len(rows) - 1
    return SourceBlock(
        spec=spec,
        rows=tuple(rows),
        extras=tuple(extras),
        path=handoff_path,
        sha256=sha256_file(handoff_path),
        start_row=start_row,
        end_row=end_row,
    )


def _build_combined_rows(
    blocks: Sequence[SourceBlock],
    extra_columns: Sequence[str],
    empty_canonical: Sequence[str],
) -> list[dict[str, str]]:
    combined: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for block in blocks:
        for source_row in block.rows:
            record_id = source_row["record_id"]
            if record_id in seen_ids:
                raise CombinedInputError(
                    f"Cross-source record_id collision: {record_id!r}"
                )
            seen_ids.add(record_id)
            row: dict[str, str] = {}
            for column in CORPUS_COLUMNS:
                row[column] = source_row.get(column, "")
            for column in extra_columns:
                row[column] = source_row.get(column, "")
            for column in CORPUS_COLUMNS:
                if row[column] != source_row.get(column, ""):
                    raise CombinedInputError(
                        f"Canonical field {column!r} mutated for {record_id!r}"
                    )
            for column in empty_canonical:
                if (row.get(column) or "").strip():
                    raise CombinedInputError(
                        f"Canonical field {column!r} must remain empty on "
                        f"{record_id!r}"
                    )
            combined.append(row)
    return combined


def _completeness_report(
    rows: Sequence[Mapping[str, str]],
    fields: Sequence[str],
    source_order: Sequence[str],
) -> dict[str, Any]:
    global_counts = {
        field: {
            "populated": _nonempty_count(rows, field),
            "empty": len(rows) - _nonempty_count(rows, field),
        }
        for field in fields
    }
    by_source: dict[str, dict[str, dict[str, int]]] = {}
    for source_key in source_order:
        source_rows = [
            row for row in rows if (row.get("source_db") or "") == source_key
        ]
        by_source[source_key] = {
            field: {
                "populated": _nonempty_count(source_rows, field),
                "empty": len(source_rows) - _nonempty_count(source_rows, field),
            }
            for field in fields
        }
    return {"global": global_counts, "by_source": by_source}


def _principal_extra_report(
    rows: Sequence[Mapping[str, str]],
    blocks: Sequence[SourceBlock],
) -> dict[str, dict[str, dict[str, int]]]:
    report: dict[str, dict[str, dict[str, int]]] = {}
    for block in blocks:
        source_rows = [
            row
            for row in rows
            if (row.get("source_db") or "") == block.spec.source_key
        ]
        field_counts: dict[str, dict[str, int]] = {}
        for field in block.spec.principal_extra_fields:
            populated = _nonempty_count(source_rows, field)
            field_counts[field] = {
                "populated": populated,
                "empty": len(source_rows) - populated,
            }
        report[block.spec.source_key] = field_counts
    return report


def build_combined_summary(
    *,
    repo_root: Path,
    config: Mapping[str, Any],
    result_paths: Mapping[str, str],
    blocks: Sequence[SourceBlock],
    extra_columns: Sequence[str],
    combined_rows: Sequence[Mapping[str, str]],
    csv_sha256: str,
    input_hashes: Mapping[str, str],
    duplication: Mapping[str, Any],
    completeness: Mapping[str, Any],
    principal_extras: Mapping[str, Mapping[str, Mapping[str, int]]],
) -> str:
    zeros: Sequence[ZeroAuthorisedSource] = config["_parsed_zeros"]
    lines = [
        "# Combined global-S4 input summary",
        "",
        "Sequence-safe report of the corpus-wide pre-S4 concatenation.",
        "No biological sequences. Row-preserving union; no merge.",
        "",
        "## Totals",
        "",
        f"- combined records = `{len(combined_rows)}`",
        f"- unique record_id = `{len({row['record_id'] for row in combined_rows})}`",
        "- duplicate record_id = `0`",
        "- cross-source record_id collisions = `0`",
        f"- canonical columns = `{len(CORPUS_COLUMNS)}`",
        f"- source-extra columns = `{len(extra_columns)}`",
        "",
        "## Contributing sources",
        "",
    ]
    for block in blocks:
        lines.append(
            f"- `{block.spec.source_key}` = `{len(block.rows)}` rows "
            f"`{block.start_row}-{block.end_row}`"
        )
    lines.extend(["", "## Zero-authorised sources", ""])
    if zeros:
        for item in zeros:
            lines.append(
                f"- `{item.source_key}` = `0` ({item.status}; no rows fabricated)"
            )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Schema",
            "",
            "- canonical columns occupy the live `CORPUS_COLUMNS` order",
            "- source extras follow configured source order, preserving each",
            "  handoff's extra-column order",
            "- extras are empty on rows from other sources",
            "",
            "### Source-extra columns",
            "",
        ]
    )
    if extra_columns:
        for column in extra_columns:
            lines.append(f"- `{column}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Canonical-field completeness", "", "### Global", ""])
    global_counts = completeness["global"]
    for field, counts in global_counts.items():
        lines.append(
            f"- `{field}` populated = `{counts['populated']}` empty = "
            f"`{counts['empty']}`"
        )
    lines.extend(["", "### By source", ""])
    for source_key, fields in completeness["by_source"].items():
        lines.append(f"- `{source_key}`")
        for field, counts in fields.items():
            lines.append(
                f"  - `{field}` populated = `{counts['populated']}` empty = "
                f"`{counts['empty']}`"
            )
    lines.extend(
        [
            "",
            "## Source-extra completeness (principal metadata only)",
            "",
            "Counts only. Source extras are provenance, not canonical S4 decisions.",
            "",
        ]
    )
    for source_key, fields in principal_extras.items():
        lines.append(f"- `{source_key}`")
        if not fields:
            lines.append("  - no source-specific extra columns in the handoff")
            continue
        for field, counts in fields.items():
            lines.append(
                f"  - `{field}` populated = `{counts['populated']}` empty = "
                f"`{counts['empty']}`"
            )
    redistribution = _value_counts(combined_rows, "redistribution_status")
    lines.extend(["", "## Redistribution status", "", "### Global", ""])
    for value, count in redistribution.items():
        lines.append(f"- `{value}` = `{count}`")
    lines.extend(["", "### By source", ""])
    for block in blocks:
        source_rows = [
            row
            for row in combined_rows
            if (row.get("source_db") or "") == block.spec.source_key
        ]
        counts = _value_counts(source_rows, "redistribution_status")
        rendered = ", ".join(f"`{value}` = `{count}`" for value, count in counts.items())
        lines.append(f"- `{block.spec.source_key}`: {rendered}")
    lines.extend(
        [
            "",
            "## Duplication diagnostic",
            "",
            f"- {duplication['label']}",
            "- duplicate sequence_core values = "
            f"`{duplication['duplicate_sequence_core_values']}`",
            "- rows participating = "
            f"`{duplication['rows_participating']}`",
        ]
    )
    pair_counts = duplication["source_pair_shared_sequence_core_values"]
    nonzero_pairs = {key: n for key, n in pair_counts.items() if n}
    if nonzero_pairs:
        lines.append("- source-pair shared sequence_core values:")
        for key, count in nonzero_pairs.items():
            lines.append(f"  - `{key}` = `{count}`")
    else:
        lines.append("- source-pair shared sequence_core values = `0`")
    lines.extend(
        [
            "",
            "## Scientific boundary",
            "",
            "- target extraction not started",
            "- target dictionary not built",
            "- evidence not assigned",
            "- affinity not canonicalised",
            "- leakage not applied",
            "- CHECKPOINT-2 not started",
            "- non-protein/evidence routing not applied",
            "- cross-source deduplication not performed",
            "- NCBI/ENA not merged",
            "- clustering/balancing/partitioning not performed",
            "- contributing_sources remains the source-local handoff value",
            "- corroboration_count was not increased",
            "",
            "## Outputs",
            "",
            f"- combined CSV = `{result_paths['output_csv']}`",
            f"- summary = `{result_paths['output_summary']}`",
        ]
    )
    if result_paths.get("output_manifest"):
        lines.append(f"- manifest = `{result_paths['output_manifest']}`")
    lines.extend(["", "## Hashes", "", "### Source handoffs", ""])
    for source_key, digest in input_hashes.items():
        lines.append(f"- `{source_key}` = `{digest}`")
    lines.extend(
        [
            "",
            "### Combined CSV",
            "",
            f"- sha256 = `{csv_sha256}`",
            "",
        ]
    )
    text = "\n".join(lines) + "\n"
    _assert_no_sequence_leak(text, label="combined summary")
    abs_root = str(repo_root.resolve())
    if abs_root in text:
        raise CombinedInputError(
            "Combined summary must not contain absolute repository paths"
        )
    return text


def _build_manifest(
    *,
    config: Mapping[str, Any],
    blocks: Sequence[SourceBlock],
    extra_columns: Sequence[str],
    combined_rows: Sequence[Mapping[str, str]],
    result_paths: Mapping[str, str],
    csv_sha256: str,
    summary_sha256: str,
    input_hashes: Mapping[str, str],
    duplication: Mapping[str, Any],
    completeness: Mapping[str, Any],
    principal_extras: Mapping[str, Mapping[str, Mapping[str, int]]],
) -> dict[str, Any]:
    zeros: Sequence[ZeroAuthorisedSource] = config["_parsed_zeros"]
    return {
        "contract_id": config.get("contract_id"),
        "combination_mode": config.get("combination_mode"),
        "combined_records": len(combined_rows),
        "unique_record_id": len({row["record_id"] for row in combined_rows}),
        "duplicate_record_id": 0,
        "cross_source_record_id_collisions": 0,
        "canonical_column_count": len(CORPUS_COLUMNS),
        "source_extra_column_count": len(extra_columns),
        "source_extra_columns": list(extra_columns),
        "contributing_sources": [
            {
                "source_key": block.spec.source_key,
                "records": len(block.rows),
                "start_row": block.start_row,
                "end_row": block.end_row,
                "handoff_sha256": block.sha256,
            }
            for block in blocks
        ],
        "zero_authorised_sources": [
            {
                "source_key": item.source_key,
                "records": 0,
                "status": item.status,
                "rows_fabricated": False,
            }
            for item in zeros
        ],
        "completeness": completeness,
        "principal_extra_completeness": principal_extras,
        "redistribution_status": _value_counts(
            combined_rows, "redistribution_status"
        ),
        "duplication_diagnostic": duplication,
        "paths": result_paths,
        "hashes": {
            "source_handoffs": dict(input_hashes),
            "combined_csv": csv_sha256,
            "combined_summary": summary_sha256,
        },
        "scientific_boundary": config.get("scientific_boundary") or {},
    }


def combine_global_s4_input(
    *,
    combined_config: Path,
    repo_root: Path | None = None,
) -> CombinedResult:
    """Concatenate configured source handoffs into one pre-S4 input."""
    root = repo_root or find_repo_root()
    config_path = _resolve_under_repo(root, combined_config)
    config = load_combined_config(config_path)
    sources: Sequence[ContributingSource] = config["_parsed_sources"]
    output_csv = _assert_output_allowed(root, config["output_csv"])
    output_summary = _assert_output_allowed(root, config["output_summary"])
    manifest_rel = config.get("output_manifest")
    output_manifest = (
        _assert_output_allowed(root, str(manifest_rel))
        if manifest_rel
        else None
    )
    empty_canonical = _parse_string_list(
        config.get("must_remain_empty_canonical_fields"),
        label="must_remain_empty_canonical_fields",
    )
    completeness_fields = _parse_string_list(
        config.get("completeness_fields"),
        label="completeness_fields",
    )

    blocks: list[SourceBlock] = []
    next_start = 1
    before_hashes: dict[str, str] = {}
    for spec in sources:
        block = _load_source_block(
            repo_root=root, spec=spec, start_row=next_start
        )
        blocks.append(block)
        before_hashes[spec.source_key] = block.sha256
        next_start = block.end_row + 1

    extra_columns = _union_extra_columns(
        [(block.spec.source_key, block.extras) for block in blocks]
    )
    expected_total = int(config["expected_combined_records"])
    total_rows = sum(len(block.rows) for block in blocks)
    if total_rows != expected_total:
        raise CombinedInputError(
            f"Combined row count {total_rows} != expected {expected_total}"
        )

    combined_rows = _build_combined_rows(blocks, extra_columns, empty_canonical)
    if len(combined_rows) != expected_total:
        raise CombinedInputError(
            f"Combined output has {len(combined_rows)} rows; expected "
            f"{expected_total}"
        )
    unique_ids = [row["record_id"] for row in combined_rows]
    if len(unique_ids) != len(set(unique_ids)):
        raise CombinedInputError("Combined record_id values are not unique")

    quoting = csv.QUOTE_MINIMAL
    if any("\r" in (value or "") for row in combined_rows for value in row.values()):
        quoting = csv.QUOTE_ALL
    try:
        write_corpus_csv_atomic(
            output_csv,
            combined_rows,
            columns=list(CORPUS_COLUMNS) + extra_columns,
            quoting=quoting,
        )
    except CorpusSchemaError as exc:
        raise CombinedInputError(str(exc)) from exc

    written_fields, written_rows = _read_handoff_csv(output_csv)
    if written_fields != list(CORPUS_COLUMNS) + extra_columns:
        raise CombinedInputError(
            "Combined CSV header does not match canonical-plus-extra contract"
        )
    if [row["record_id"] for row in written_rows] != unique_ids:
        raise CombinedInputError(
            "Combined CSV did not round-trip configured record_id order"
        )
    written_by_id = {row["record_id"]: row for row in written_rows}
    for block in blocks:
        for source_row in block.rows:
            written = written_by_id[source_row["record_id"]]
            for column in CORPUS_COLUMNS:
                if written.get(column, "") != source_row.get(column, ""):
                    raise CombinedInputError(
                        f"Combined CSV mutated canonical {column!r} for "
                        f"{source_row['record_id']!r}"
                    )
            for column in block.extras:
                if written.get(column, "") != source_row.get(column, ""):
                    raise CombinedInputError(
                        f"Combined CSV mutated extra {column!r} for "
                        f"{source_row['record_id']!r}"
                    )

    after_hashes = {
        block.spec.source_key: sha256_file(block.path) for block in blocks
    }
    if after_hashes != before_hashes:
        raise CombinedInputError(
            "Source handoff CSVs were modified during combination"
        )

    source_order = [block.spec.source_key for block in blocks]
    duplication = _duplication_diagnostic(written_rows, source_order)
    completeness = _completeness_report(
        written_rows, completeness_fields, source_order
    )
    principal_extras = _principal_extra_report(written_rows, blocks)
    csv_sha256 = sha256_file(output_csv)
    result_paths = {
        "output_csv": _relative_display(output_csv, root),
        "output_summary": _relative_display(output_summary, root),
    }
    if output_manifest is not None:
        result_paths["output_manifest"] = _relative_display(output_manifest, root)

    summary_text = build_combined_summary(
        repo_root=root,
        config=config,
        result_paths=result_paths,
        blocks=blocks,
        extra_columns=extra_columns,
        combined_rows=written_rows,
        csv_sha256=csv_sha256,
        input_hashes=before_hashes,
        duplication=duplication,
        completeness=completeness,
        principal_extras=principal_extras,
    )
    _write_text_atomic(output_summary, summary_text)
    summary_sha256 = sha256_file(output_summary)

    manifest_sha256 = None
    if output_manifest is not None:
        manifest = _build_manifest(
            config=config,
            blocks=blocks,
            extra_columns=extra_columns,
            combined_rows=written_rows,
            result_paths=result_paths,
            csv_sha256=csv_sha256,
            summary_sha256=summary_sha256,
            input_hashes=before_hashes,
            duplication=duplication,
            completeness=completeness,
            principal_extras=principal_extras,
        )
        manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        _assert_no_sequence_leak(manifest_text, label="combined manifest")
        _write_text_atomic(output_manifest, manifest_text)
        manifest_sha256 = sha256_file(output_manifest)

    boundaries = {
        block.spec.source_key: {
            "start_row": block.start_row,
            "end_row": block.end_row,
            "records": len(block.rows),
        }
        for block in blocks
    }
    return CombinedResult(
        combined_rows=len(written_rows),
        unique_ids=len(set(unique_ids)),
        extra_columns=tuple(extra_columns),
        output_csv=output_csv,
        output_summary=output_summary,
        output_manifest=output_manifest,
        csv_sha256=csv_sha256,
        summary_sha256=summary_sha256,
        manifest_sha256=manifest_sha256,
        input_hashes=before_hashes,
        source_boundaries=boundaries,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Concatenate authorised source-local global-S4 handoffs into one "
            "pre-S4 input. Does not merge, deduplicate, or begin S4/S5."
        )
    )
    parser.add_argument(
        "--combined-config",
        type=Path,
        required=True,
        help="Repo-relative combined-input contract JSON",
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
    result = combine_global_s4_input(
        combined_config=args.combined_config,
        repo_root=root,
    )
    print(
        f"combined global-S4 input ready: rows={result.combined_rows} "
        f"unique_ids={result.unique_ids} extras={len(result.extra_columns)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CombinedInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

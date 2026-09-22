"""GLOBAL S7D — final corpus assembly, diagnostics, reporting, and validation.

S7D copies frozen S7A/S7B/S7C artefacts, concatenates authoritative parked and
rejection lanes, writes TRAIN-only ``corpus_final.txt``, and re-runs integrity
gates. It does not choose identities, change the 3% cap, change clusters,
reassign splits, promote E5, or start modelling.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from adapters.s4_scientific_common import ScientificProposalError, write_json_atomic, write_text_atomic
from adapters.s4_leakage_proposal import load_leakage_resources, propose_leakage
from adapters.s5_exact_dedup import scientific_identity_id, sequence_core_sha256
from adapters.s5_validate_exact_dedup import scan_paths_for_sequence_leak, scan_text_for_sequence_leak
from adapters.s7_partition import (
    assign_length_regimes,
    jsonable,
    load_frozen_s6_gmm,
    semantic_cluster_set_hash,
    semantic_identity_set_hash,
)
from adapters.target_extraction_common import SEQ_LEAK_RE
from common.corpus_schema import write_corpus_csv_atomic
from common.eligibility import match_target_leakage
from common.leakage_matching import IDENTITY_THRESHOLD, global_edit_identity

S7DFinalBuildError = ScientificProposalError

TRAIN_LABEL = "TRAIN"
VALIDATION_LABEL = "VALIDATION"
REF_LABEL = "REF"
EVAL_LABEL = "EVAL"
ROLE_LABELS: tuple[str, ...] = (TRAIN_LABEL, VALIDATION_LABEL, REF_LABEL, EVAL_LABEL)
PRIMARY_PARTITIONS: frozenset[str] = frozenset({"FT", "REF", "EVAL"})
SCIENTIFIC_PAYLOAD_NAMES: tuple[str, ...] = (
    "corpus_final.csv",
    "corpus_final.txt",
    "ft_train.csv",
    "ft_validation.csv",
    "ref.csv",
    "eval.csv",
    "ft_split_assignment.csv",
    "parked_ssdna.csv",
    "parked_non_protein_targets.csv",
    "parked_evidence_e5.csv",
    "evaluation_references.csv",
    "rejected_all.csv",
)
AUDIT_PAYLOAD_NAMES: tuple[str, ...] = (
    "parked_inventory.csv",
    "corpus_report.md",
    "corpus_manifest.json",
)
PARKED_INVENTORY_COLUMNS: tuple[str, ...] = (
    "source",
    "stage",
    "route",
    "grain",
    "row_count",
    "authoritative_source_path",
    "authoritative_source_sha256",
    "consolidated_output",
    "final_disposition",
    "sequence_bearing",
    "not_consolidated_reason",
)
CONSOLIDATED_DISPOSITIONS: frozenset[str] = frozenset(
    {
        "consolidated_parked_ssdna",
        "consolidated_parked_non_protein",
        "consolidated_parked_e5",
    }
)
RETAINED_DISPOSITION = "retained_in_source_level_park"
E5_DIAGNOSTIC_CLUSTER_STATEMENT = (
    "235 E5D diagnostic cluster units is a counterfactual diagnostic quantity "
    "produced by the documented E5 diagnostic procedure. It is not the exact "
    "number of S5 clusters that would result from admitting E5. The diagnostic "
    "did not rerun the frozen MMseqs S5 clustering pipeline and could not apply "
    "ENA family must-links because usable E5 family metadata were unavailable. "
    "Actual E5 admission would require a new scientific corpus revision, "
    "re-running applicable deduplication/clustering, target capping, and all "
    "downstream splits."
)
BYTE_COPY_OUTPUTS: tuple[str, ...] = (
    "corpus_final.csv",
    "ft_train.csv",
    "ft_validation.csv",
    "ref.csv",
    "eval.csv",
    "ft_split_assignment.csv",
    "evaluation_references.csv",
)
CANONICAL_SEQUENCE_FIELDS: tuple[str, ...] = (
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "sequence_length_full",
    "sequence_length_core",
    "alphabet_as_reported",
    "t_to_u_applied",
    "molecule_type",
    "chemistry",
)
REJECTION_LEADING_COLUMNS: tuple[str, ...] = (
    "s7d_source",
    "s7d_source_lane",
    "s7d_authoritative_input_path",
    "s7d_input_sha256",
    "stage",
    "rejection_reason",
    "record_id",
    "source_db",
    "scientific_identity_id",
    "cluster_id",
    "canonical_target_name",
)


def _blank(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _resolve(root: Path, relative: str | Path) -> Path:
    return (root / str(relative)).resolve()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_csv_with_fields(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _copy_bytes(src: Path, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return _sha256_file(dest)


def _write_csv(path: Path, rows: Sequence[Mapping[str, str]], columns: Sequence[str]) -> None:
    write_corpus_csv_atomic(path, rows, columns=list(columns))


def _union_columns(leading: Sequence[str], field_groups: Sequence[Sequence[str]]) -> list[str]:
    ordered = list(leading)
    seen = set(ordered)
    for fields in field_groups:
        for column in fields:
            if column not in seen:
                seen.add(column)
                ordered.append(column)
    return ordered


def _row_with_columns(row: Mapping[str, str], columns: Sequence[str]) -> dict[str, str]:
    return {column: row.get(column, "") for column in columns}


def _assert_hash(path: Path, expected: str | None, *, label: str) -> str:
    observed = _sha256_file(path)
    if expected and observed != expected:
        raise S7DFinalBuildError(
            f"{label} SHA-256 mismatch: expected {expected}, got {observed}"
        )
    return observed


def _git_ls_files_data(root: Path) -> str:
    return subprocess.check_output(["git", "ls-files", "data"], cwd=root, text=True).strip()


def _git_head(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def assert_git_ls_files_data_empty(root: Path) -> None:
    tracked = _git_ls_files_data(root)
    if tracked:
        raise S7DFinalBuildError("git ls-files data is not empty")


def assert_under_processed(root: Path, path: Path) -> None:
    relative = path.resolve().relative_to(root.resolve())
    if relative.parts[:2] != ("data", "processed"):
        raise S7DFinalBuildError("S7D sequence-bearing outputs must remain under data/processed/")


def assert_no_sequence_leak(text: str, *, label: str) -> None:
    if SEQ_LEAK_RE.search(text or ""):
        raise S7DFinalBuildError(f"{label} must not contain biological sequence strings")


def verify_frozen_file(spec: Mapping[str, Any], root: Path, *, verify_hashes: bool) -> dict[str, str]:
    path = _resolve(root, spec["path"])
    if not path.is_file():
        raise S7DFinalBuildError(f"frozen input missing: {spec['path']}")
    observed = _sha256_file(path)
    expected = spec.get("sha256")
    if verify_hashes and expected and observed != expected:
        raise S7DFinalBuildError(
            f"frozen hash mismatch for {spec['path']}: expected {expected}, got {observed}"
        )
    return {"path": spec["path"], "sha256": observed, "matched": (not expected) or observed == expected}


def count_identities(rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    identities = [_blank(row.get("scientific_identity_id")) for row in rows]
    if any(not item for item in identities):
        raise S7DFinalBuildError("blank scientific_identity_id in frozen corpus")
    if len(set(identities)) != len(identities):
        raise S7DFinalBuildError("duplicate scientific_identity_id in frozen corpus")
    cores = {_blank(row.get("sequence_core")) for row in rows}
    clusters = {_blank(row.get("cluster_id")) for row in rows}
    targets = {_blank(row.get("canonical_target_name")) for row in rows}
    if "" in cores or "" in clusters or "" in targets:
        raise S7DFinalBuildError("blank core, cluster_id, or canonical target in frozen corpus")
    return {
        "n_scientific_identities": len(identities),
        "n_distinct_sequence_core": len(cores),
        "n_final_clusters": len(clusters),
        "n_canonical_targets": len(targets),
    }


def verify_semantic_freeze(
    rows: Sequence[Mapping[str, str]],
    spec: Mapping[str, Any],
    *,
    label: str,
    verify_hashes: bool,
) -> dict[str, str]:
    identity_hash = semantic_identity_set_hash(rows)
    cluster_hash = semantic_cluster_set_hash(rows)
    expected_identity = spec.get("identity_set_hash")
    expected_cluster = spec.get("cluster_set_hash")
    if verify_hashes and expected_identity and identity_hash != expected_identity:
        raise S7DFinalBuildError(f"{label} identity-set hash mismatch")
    if verify_hashes and expected_cluster and cluster_hash != expected_cluster:
        raise S7DFinalBuildError(f"{label} cluster-set hash mismatch")
    return {
        "identity_set_hash": identity_hash,
        "cluster_set_hash": cluster_hash,
        "identity_matched": (not expected_identity) or identity_hash == expected_identity,
        "cluster_matched": (not expected_cluster) or cluster_hash == expected_cluster,
    }


def role_rows(
    *,
    train_rows: Sequence[Mapping[str, str]],
    validation_rows: Sequence[Mapping[str, str]],
    ref_rows: Sequence[Mapping[str, str]],
    eval_rows: Sequence[Mapping[str, str]],
) -> dict[str, list[dict[str, str]]]:
    return {
        TRAIN_LABEL: [dict(row) for row in train_rows],
        VALIDATION_LABEL: [dict(row) for row in validation_rows],
        REF_LABEL: [dict(row) for row in ref_rows],
        EVAL_LABEL: [dict(row) for row in eval_rows],
    }


def build_corpus_final_txt(train_rows: Sequence[Mapping[str, str]]) -> list[str]:
    """Distinct TRAIN sequence_core values in first-occurrence order."""
    lines: list[str] = []
    seen: set[str] = set()
    for row in train_rows:
        core = row.get("sequence_core") or ""
        if not core:
            raise S7DFinalBuildError("frozen TRAIN row is missing sequence_core")
        if core in seen:
            continue
        seen.add(core)
        lines.append(core)
    return lines


def write_corpus_final_txt(path: Path, lines: Sequence[str]) -> str:
    text = "\n".join(lines)
    if lines:
        text += "\n"
    write_text_atomic(path, text)
    return _sha256_file(path)


def training_text_gates(
    lines: Sequence[str],
    *,
    train_rows: Sequence[Mapping[str, str]],
    validation_rows: Sequence[Mapping[str, str]],
    ref_rows: Sequence[Mapping[str, str]],
    eval_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    train_cores = {row.get("sequence_core") or "" for row in train_rows}
    train_cores.discard("")
    line_set = set(lines)
    if line_set != train_cores:
        raise S7DFinalBuildError("corpus_final.txt core set is not frozen TRAIN sequence_core")
    if len(lines) != len(line_set):
        raise S7DFinalBuildError("corpus_final.txt contains duplicate lines")
    validation_cores = {row.get("sequence_core") or "" for row in validation_rows}
    ref_cores = {row.get("sequence_core") or "" for row in ref_rows}
    eval_cores = {row.get("sequence_core") or "" for row in eval_rows}
    validation_hit = sorted(line_set & validation_cores)
    ref_hit = sorted(line_set & ref_cores)
    eval_hit = sorted(line_set & eval_cores)
    if validation_hit or ref_hit or eval_hit:
        raise S7DFinalBuildError("corpus_final.txt contains non-TRAIN cores")
    return {
        "line_count": len(lines),
        "distinct_sequences": len(line_set),
        "duplicate_lines": 0,
        "validation_contamination": 0,
        "ref_contamination": 0,
        "eval_contamination": 0,
        "source": "frozen_ft_train_only",
    }


def _canonical_by_id(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.is_file():
        return {}
    rows = _read_csv(path)
    return {_blank(row.get("record_id")): row for row in rows if _blank(row.get("record_id"))}


def assemble_parked_ssdna(
    sources: Sequence[Mapping[str, Any]],
    root: Path,
    *,
    verify_hashes: bool,
) -> tuple[list[str], list[dict[str, str]], list[dict[str, Any]]]:
    inventory: list[dict[str, Any]] = []
    prepared: list[tuple[list[str], list[dict[str, str]]]] = []
    for spec in sources:
        path = _resolve(root, spec["path"])
        observed = _assert_hash(
            path, spec.get("sha256") if verify_hashes else None, label=spec["source"]
        )
        fields, rows = _read_csv_with_fields(path)
        molecule_filter = spec.get("molecule_type_filter")
        if molecule_filter:
            allowed = {str(item) for item in molecule_filter}
            rows = [row for row in rows if _blank(row.get("molecule_type")) in allowed]
        canonical_rel = spec.get("canonical_path")
        canonical = _canonical_by_id(_resolve(root, canonical_rel) if canonical_rel else None)
        enriched: list[dict[str, str]] = []
        for row in rows:
            copied = dict(row)
            record_id = _blank(copied.get("record_id"))
            donor = canonical.get(record_id, {})
            for field in CANONICAL_SEQUENCE_FIELDS:
                if not _blank(copied.get(field)) and field in donor:
                    copied[field] = donor[field]
            copied["s7d_source"] = spec["source"]
            copied["s7d_source_lane"] = "checkpoint1_parked_ssdna"
            copied["s7d_authoritative_input_path"] = spec["path"]
            copied["s7d_input_sha256"] = observed
            if "source_db" not in copied or not _blank(copied.get("source_db")):
                copied["source_db"] = spec["source"]
            enriched.append(copied)
        extra_fields = [field for field in CANONICAL_SEQUENCE_FIELDS if field not in fields]
        prepared.append((list(fields) + extra_fields, enriched))
        inventory.append(
            {
                "source": spec["source"],
                "authoritative_input_path": spec["path"],
                "input_sha256": observed,
                "rows": len(enriched),
                "molecule_type_filter": molecule_filter,
            }
        )
    columns = _union_columns(
        (
            "s7d_source",
            "s7d_source_lane",
            "s7d_authoritative_input_path",
            "s7d_input_sha256",
            "record_id",
            "source_db",
        ),
        [fields for fields, _rows in prepared],
    )
    out_rows = [_row_with_columns(row, columns) for _fields, rows in prepared for row in rows]
    return columns, out_rows, inventory


def assemble_filtered_relationship_lane(
    spec: Mapping[str, Any],
    root: Path,
    *,
    verify_hashes: bool,
    lane: str,
) -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    path = _resolve(root, spec["path"])
    observed = _assert_hash(path, spec.get("sha256") if verify_hashes else None, label=lane)
    fields, rows = _read_csv_with_fields(path)
    filter_field = spec.get("filter_field")
    filter_value = spec.get("filter_value")
    if filter_field:
        rows = [row for row in rows if _blank(row.get(filter_field)) == str(filter_value)]
    leading = (
        "s7d_source",
        "s7d_source_lane",
        "s7d_authoritative_input_path",
        "s7d_input_sha256",
    )
    columns = _union_columns(leading, [fields])
    out_rows: list[dict[str, str]] = []
    for row in rows:
        copied = dict(row)
        copied["s7d_source"] = spec.get("source") or _blank(row.get("source_db")) or "global_s4"
        copied["s7d_source_lane"] = spec.get("lane") or lane
        copied["s7d_authoritative_input_path"] = spec["path"]
        copied["s7d_input_sha256"] = observed
        out_rows.append(_row_with_columns(copied, columns))
    inventory = {
        "source": spec.get("source") or "global_s4",
        "authoritative_input_path": spec["path"],
        "input_sha256": observed,
        "rows": len(out_rows),
        "lane": spec.get("lane") or lane,
        "filter_field": filter_field,
        "filter_value": filter_value,
    }
    return columns, out_rows, inventory


def assemble_parked_non_protein(
    sources: Sequence[Mapping[str, Any]],
    root: Path,
    *,
    verify_hashes: bool,
) -> tuple[list[str], list[dict[str, str]], list[dict[str, Any]]]:
    prepared: list[tuple[list[str], list[dict[str, str]]]] = []
    inventory: list[dict[str, Any]] = []
    for spec in sources:
        columns, rows, info = assemble_filtered_relationship_lane(
            spec, root, verify_hashes=verify_hashes, lane="parked_non_protein"
        )
        prepared.append((columns, rows))
        inventory.append(info)
    union = _union_columns(
        (
            "s7d_source",
            "s7d_source_lane",
            "s7d_authoritative_input_path",
            "s7d_input_sha256",
        ),
        [fields for fields, _rows in prepared],
    )
    out_rows = [_row_with_columns(row, union) for _fields, rows in prepared for row in rows]
    return union, out_rows, inventory


def _lane_rows_match(row: Mapping[str, str], filters: Sequence[Mapping[str, Any]]) -> bool:
    for item in filters:
        field = str(item["field"])
        observed = _blank(row.get(field))
        op = str(item.get("op") or "eq")
        if op == "eq":
            if observed != str(item.get("value", "")):
                return False
        elif op == "neq":
            if observed == str(item.get("value", "")):
                return False
        else:
            raise S7DFinalBuildError(f"unsupported parked-inventory filter op: {op}")
    return True


def count_parked_inventory_lane(
    spec: Mapping[str, Any],
    root: Path,
    *,
    verify_hashes: bool,
) -> dict[str, str]:
    path = _resolve(root, spec["path"])
    observed = _assert_hash(
        path, spec.get("sha256") if verify_hashes else None, label=f"parked inventory {spec.get('source')}"
    )
    fields, rows = _read_csv_with_fields(path)
    matched = [row for row in rows if _lane_rows_match(row, spec.get("filters") or [])]
    distinct_field = spec.get("distinct_field")
    if distinct_field:
        count = len(
            {
                _blank(row.get(str(distinct_field)))
                for row in matched
                if _blank(row.get(str(distinct_field)))
            }
        )
    else:
        count = len(matched)
    expected = spec.get("expected_row_count")
    if expected is not None and int(count) != int(expected):
        raise S7DFinalBuildError(
            f"parked inventory {spec.get('source')}/{spec.get('route')}/{spec.get('grain')}: "
            f"expected {expected} rows, got {count}"
        )
    disposition = str(spec.get("final_disposition") or "")
    if disposition not in CONSOLIDATED_DISPOSITIONS and disposition != RETAINED_DISPOSITION:
        raise S7DFinalBuildError(
            f"parked inventory {spec.get('source')}/{spec.get('route')} has unknown disposition"
        )
    consolidated = str(spec.get("consolidated_output") or "")
    if disposition in CONSOLIDATED_DISPOSITIONS and not consolidated:
        raise S7DFinalBuildError(
            f"parked inventory {spec.get('source')}/{spec.get('route')} is consolidated but has no output"
        )
    if disposition == RETAINED_DISPOSITION and consolidated:
        raise S7DFinalBuildError(
            f"parked inventory {spec.get('source')}/{spec.get('route')} cannot be both retained and consolidated"
        )
    seq_cols = [field for field in fields if "sequence" in field.lower()]
    sequence_bearing = spec.get("sequence_bearing")
    if sequence_bearing is None:
        sequence_bearing = "yes" if seq_cols else "no"
    else:
        sequence_bearing = "yes" if sequence_bearing in {True, "yes"} else "no"
    return {
        "source": str(spec["source"]),
        "stage": str(spec["stage"]),
        "route": str(spec["route"]),
        "grain": str(spec["grain"]),
        "row_count": str(count),
        "authoritative_source_path": str(spec["path"]),
        "authoritative_source_sha256": observed,
        "consolidated_output": consolidated,
        "final_disposition": disposition,
        "sequence_bearing": sequence_bearing,
        "not_consolidated_reason": str(spec.get("not_consolidated_reason") or ""),
    }


def assemble_parked_inventory(
    lanes: Sequence[Mapping[str, Any]],
    root: Path,
    *,
    verify_hashes: bool,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if not lanes:
        summary = {
            "parked_lanes_inventoried": 0,
            "parked_lanes_consolidated": 0,
            "parked_lanes_retained_source_level_only": 0,
            "unaccounted_parked_lanes": 0,
            "lanes": [],
        }
        return [], summary
    rows = [
        count_parked_inventory_lane(spec, root, verify_hashes=verify_hashes) for spec in lanes
    ]
    n_consolidated = sum(1 for row in rows if row["final_disposition"] in CONSOLIDATED_DISPOSITIONS)
    n_retained = sum(1 for row in rows if row["final_disposition"] == RETAINED_DISPOSITION)
    unaccounted = len(rows) - n_consolidated - n_retained
    if unaccounted != 0:
        raise S7DFinalBuildError("unaccounted parked lanes are not zero")
    summary = {
        "parked_lanes_inventoried": len(rows),
        "parked_lanes_consolidated": n_consolidated,
        "parked_lanes_retained_source_level_only": n_retained,
        "unaccounted_parked_lanes": 0,
        "lanes": [
            {
                "source": row["source"],
                "stage": row["stage"],
                "route": row["route"],
                "grain": row["grain"],
                "row_count": int(row["row_count"]),
                "authoritative_input_sha256": row["authoritative_source_sha256"],
                "consolidated_final_output": row["consolidated_output"] or None,
                "final_disposition": row["final_disposition"],
            }
            for row in rows
        ],
    }
    return rows, summary


def assemble_evaluation_references(
    spec: Mapping[str, Any],
    root: Path,
    dest: Path,
    *,
    verify_hashes: bool,
) -> tuple[str, list[dict[str, str]]]:
    src = _resolve(root, spec["path"])
    observed = _assert_hash(
        src, spec.get("sha256") if verify_hashes else None, label="evaluation_references"
    )
    copied = _copy_bytes(src, dest)
    if copied != observed:
        raise S7DFinalBuildError("evaluation_references byte-copy hash drifted")
    return copied, _read_csv(dest)


def assemble_replication_dataset_a(
    spec: Mapping[str, Any],
    root: Path,
    dest: Path,
) -> dict[str, Any]:
    parked_path = _resolve(root, spec["parked_path"])
    canonical_path = _resolve(root, spec["canonical_path"])
    parked_ids = {
        _blank(row.get("record_id"))
        for row in _read_csv(parked_path)
        if _blank(row.get("record_id"))
    }
    fields, canonical_rows = _read_csv_with_fields(canonical_path)
    selected = [row for row in canonical_rows if _blank(row.get("record_id")) in parked_ids]
    if len(selected) != len(parked_ids):
        raise S7DFinalBuildError(
            "Dataset A replication row count does not match parked AptaDiff A IDs"
        )
    _write_csv(dest, selected, fields)
    return {
        "enabled": True,
        "rows": len(selected),
        "schema_note": spec.get("schema_note") or "",
        "sha256": _sha256_file(dest),
        "source": spec.get("source"),
        "role": "replication_comparability_only",
        "part_of_primary_rna_corpus": False,
        "contributes_to_corpus_final_txt": False,
        "entered_s4_s5_primary_scientific_identities": False,
        "train_validation_ref_eval_member": False,
    }


def _rejection_from_ids(
    path: Path,
    *,
    source: str,
    stage: str,
    lane: str,
    input_sha: str,
    relative: str,
    resolution_path: Path | None,
) -> tuple[list[str], list[dict[str, str]]]:
    rows = _read_csv(path)
    resolution: dict[str, dict[str, str]] = {}
    if resolution_path is not None and resolution_path.is_file():
        resolution = {
            _blank(row.get("record_id")): row
            for row in _read_csv(resolution_path)
            if _blank(row.get("record_id"))
        }
    out: list[dict[str, str]] = []
    for row in rows:
        record_id = _blank(row.get("record_id"))
        resolved = resolution.get(record_id, {})
        out.append(
            {
                "s7d_source": source,
                "s7d_source_lane": lane,
                "s7d_authoritative_input_path": relative,
                "s7d_input_sha256": input_sha,
                "stage": stage,
                "rejection_reason": (
                    _blank(row.get("rejection_reason"))
                    or _blank(resolved.get("checkpoint1_resolution_status"))
                    or _blank(row.get("checkpoint1_resolution_status"))
                    or "rejected_after_checkpoint1"
                ),
                "record_id": record_id,
                "source_db": _blank(row.get("source_db")) or source,
                "scientific_identity_id": "",
                "cluster_id": "",
                "canonical_target_name": _blank(row.get("canonical_target_name")),
                "rejection_detail": _blank(row.get("review_action") or resolved.get("review_action")),
            }
        )
    return list(REJECTION_LEADING_COLUMNS) + ["rejection_detail"], out


def assemble_rejected_all(
    *,
    rejection_sources: Sequence[Mapping[str, Any]],
    s4_rows: Sequence[Mapping[str, str]],
    s4_path: str,
    s4_sha: str,
    s4_routes: Sequence[str],
    pre_cap_rows: Sequence[Mapping[str, str]],
    post_cap_rows: Sequence[Mapping[str, str]],
    root: Path,
    verify_hashes: bool,
) -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    prepared: list[tuple[list[str], list[dict[str, str]]]] = []
    inventory: list[dict[str, Any]] = []
    for spec in rejection_sources:
        path = _resolve(root, spec["path"])
        observed = _assert_hash(
            path, spec.get("sha256") if verify_hashes else None, label=spec["source"]
        )
        fields, rows = _read_csv_with_fields(path)
        if "rejection_reason" in fields or "stage" in fields:
            enriched = []
            for row in rows:
                copied = dict(row)
                copied["s7d_source"] = spec["source"]
                copied["s7d_source_lane"] = "checkpoint1_applied_rejection"
                copied["s7d_authoritative_input_path"] = spec["path"]
                copied["s7d_input_sha256"] = observed
                copied["stage"] = _blank(copied.get("stage")) or spec.get("stage") or "CHECKPOINT-1"
                copied["source_db"] = _blank(copied.get("source_db")) or spec["source"]
                enriched.append(copied)
            extra = [
                "s7d_source",
                "s7d_source_lane",
                "s7d_authoritative_input_path",
                "s7d_input_sha256",
                "stage",
            ]
            prepared.append((extra + fields, enriched))
            inventory.append(
                {
                    "source": spec["source"],
                    "path": spec["path"],
                    "sha256": observed,
                    "rows": len(enriched),
                    "lane": "checkpoint1_applied_rejection",
                }
            )
        else:
            resolution_rel = spec.get("resolution_path")
            id_fields, id_rows = _rejection_from_ids(
                path,
                source=spec["source"],
                stage=str(spec.get("stage") or "CHECKPOINT-1"),
                lane="checkpoint1_rejected_ids",
                input_sha=observed,
                relative=spec["path"],
                resolution_path=_resolve(root, resolution_rel) if resolution_rel else None,
            )
            prepared.append((id_fields, id_rows))
            inventory.append(
                {
                    "source": spec["source"],
                    "path": spec["path"],
                    "sha256": observed,
                    "rows": len(id_rows),
                    "lane": "checkpoint1_rejected_ids",
                }
            )

    s4_reject_rows: list[dict[str, str]] = []
    wanted = {str(item) for item in s4_routes}
    for row in s4_rows:
        route = _blank(row.get("s4_route"))
        outcome = _blank(row.get("source_record_outcome") or row.get("audit_class") or route)
        if route not in wanted and outcome not in wanted:
            continue
        copied = dict(row)
        copied["s7d_source"] = _blank(row.get("source_db")) or "global_s4"
        copied["s7d_source_lane"] = "global_s4_exclusion"
        copied["s7d_authoritative_input_path"] = s4_path
        copied["s7d_input_sha256"] = s4_sha
        copied["stage"] = "S4"
        copied["rejection_reason"] = route or outcome
        s4_reject_rows.append(copied)
    if s4_reject_rows:
        prepared.append((list(s4_reject_rows[0].keys()), s4_reject_rows))
        inventory.append(
            {
                "source": "global_s4",
                "path": s4_path,
                "sha256": s4_sha,
                "rows": len(s4_reject_rows),
                "lane": "global_s4_exclusion",
            }
        )

    retained = {_blank(row.get("scientific_identity_id")) for row in post_cap_rows}
    cap_rows: list[dict[str, str]] = []
    for row in pre_cap_rows:
        identity = _blank(row.get("scientific_identity_id"))
        if identity in retained:
            continue
        cap_rows.append(
            {
                "s7d_source": _blank(row.get("source_db")),
                "s7d_source_lane": "s7a_target_cap",
                "s7d_authoritative_input_path": "data/interim/deduplicated/corpus_clustered_final.csv",
                "s7d_input_sha256": "",
                "stage": "S7A",
                "rejection_reason": "target_cap_subsample",
                "record_id": _blank(row.get("record_id")),
                "source_db": _blank(row.get("source_db")),
                "scientific_identity_id": identity,
                "cluster_id": _blank(row.get("cluster_id")),
                "canonical_target_name": _blank(row.get("canonical_target_name")),
            }
        )
    if cap_rows:
        prepared.append((list(REJECTION_LEADING_COLUMNS), cap_rows))
        inventory.append(
            {
                "source": "s7a_target_cap",
                "path": "data/interim/deduplicated/corpus_clustered_final.csv",
                "sha256": "",
                "rows": len(cap_rows),
                "lane": "s7a_target_cap",
            }
        )

    columns = _union_columns(REJECTION_LEADING_COLUMNS, [fields for fields, _rows in prepared])
    out_rows = [_row_with_columns(row, columns) for _fields, rows in prepared for row in rows]
    return columns, out_rows, {"sources": inventory, "n_rows": len(out_rows)}


def target_counts(rows: Sequence[Mapping[str, str]]) -> Counter[str]:
    return Counter(_blank(row.get("canonical_target_name")) for row in rows)


def target_cap_audit(
    rows: Sequence[Mapping[str, str]],
    *,
    max_fraction: float,
    expected: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    n = len(rows)
    counts = target_counts(rows)
    if n == 0:
        raise S7DFinalBuildError("corpus_final.csv is empty")
    max_name, max_count = counts.most_common(1)[0]
    share = max_count / n
    if share > max_fraction:
        raise S7DFinalBuildError("final target cap exceeded")
    payload = {
        "n": n,
        "n_targets": len(counts),
        "max_target_name": max_name,
        "max_target_count": max_count,
        "max_target_share": share,
        "ngf_count": counts.get("NGF", 0),
        "ngf_share": counts.get("NGF", 0) / n,
        "ok": True,
    }
    if expected:
        if expected.get("max_target_count") not in {None, max_count}:
            raise S7DFinalBuildError("max target count drifted from expected")
        if expected.get("max_target_name") not in {None, "", max_name}:
            raise S7DFinalBuildError("max target name drifted from expected")
        if expected.get("ngf_count") not in {None, payload["ngf_count"]}:
            raise S7DFinalBuildError("NGF count drifted from expected")
    return payload


def identity_schema_audit(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    counts = count_identities(rows)
    evidence = Counter(_blank(row.get("evidence_level")) for row in rows)
    target_types = Counter(_blank(row.get("target_type")) for row in rows)
    partitions = Counter(_blank(row.get("partition")) for row in rows)
    invalid_partition = [value for value in partitions if value not in PRIMARY_PARTITIONS]
    missing_cluster = sum(1 for row in rows if not _blank(row.get("cluster_id")))
    e5 = evidence.get("E5", 0)
    non_protein = sum(1 for row in rows if _blank(row.get("target_type")) != "protein")
    if missing_cluster:
        raise S7DFinalBuildError("missing cluster_id in corpus_final.csv")
    if invalid_partition:
        raise S7DFinalBuildError("invalid partition in corpus_final.csv")
    if e5:
        raise S7DFinalBuildError("E5 present in corpus_final.csv")
    if non_protein:
        raise S7DFinalBuildError("non-protein records present in corpus_final.csv")
    return {
        **counts,
        "duplicate_scientific_identity_id": 0,
        "missing_cluster_id": 0,
        "invalid_partition": 0,
        "E5": e5,
        "non_protein": non_protein,
        "partition_counts": dict(partitions),
        "evidence": dict(evidence),
        "target_types": dict(target_types),
    }


def split_leakage_audit(roles: Mapping[str, Sequence[Mapping[str, str]]]) -> dict[str, Any]:
    cluster_sets = {
        label: {_blank(row.get("cluster_id")) for row in rows} for label, rows in roles.items()
    }
    core_sets = {
        label: {_blank(row.get("sequence_core")) for row in rows} for label, rows in roles.items()
    }
    identity_sets = {
        label: {_blank(row.get("scientific_identity_id")) for row in rows}
        for label, rows in roles.items()
    }
    crossings: list[str] = []
    labels = list(ROLE_LABELS)
    for i, left in enumerate(labels):
        for right in labels[i + 1 :]:
            if cluster_sets[left] & cluster_sets[right]:
                crossings.append(f"cluster:{left}x{right}")
            if core_sets[left] & core_sets[right]:
                crossings.append(f"core:{left}x{right}")
            if identity_sets[left] & identity_sets[right]:
                crossings.append(f"identity:{left}x{right}")
    if crossings:
        raise S7DFinalBuildError("split leakage: " + ", ".join(crossings))
    combined = [identity for label in labels for identity in identity_sets[label]]
    if len(combined) != len(set(combined)):
        raise S7DFinalBuildError("scientific identity duplication across final roles")
    return {
        "cluster_crossings": 0,
        "core_crossings": 0,
        "identity_duplication": 0,
        "role_identities": {label: len(identity_sets[label]) for label in labels},
        "role_clusters": {label: len(cluster_sets[label]) for label in labels},
        "role_cores": {label: len(core_sets[label]) for label in labels},
        "sum_identities": len(combined),
        "sum_clusters": sum(len(cluster_sets[label]) for label in labels),
        "sum_cores": sum(len(core_sets[label]) for label in labels),
    }


def evaluation_leakage_audit(
    rows: Sequence[Mapping[str, str]],
    *,
    exclusion_set: Path,
    alias_csv: Path,
) -> dict[str, Any]:
    index, rules = load_leakage_resources(exclusion_set=exclusion_set, alias_csv=alias_csv)
    exact = 0
    ge90 = 0
    target_alias = 0
    for row in rows:
        payload = propose_leakage(
            row,
            index=index,
            rules=rules,
            target_texts=[
                _blank(row.get("canonical_target_name")),
                _blank(row.get("target_name")),
                _blank(row.get("target_name_raw")),
            ],
        )
        kind = payload.get("sequence_match_kind") or ""
        if kind == "exact":
            exact += 1
        elif kind == "identity_ge_0.90":
            ge90 += 1
        if payload.get("target_alias_match") == "true":
            target_alias += 1
        if match_target_leakage(
            [
                _blank(row.get("canonical_target_name")),
                _blank(row.get("target_name")),
                _blank(row.get("target_name_raw")),
            ],
            rules,
        ):
            if payload.get("target_alias_match") != "true":
                target_alias += 1
    if exact or ge90 or target_alias:
        raise S7DFinalBuildError("evaluation-reference leakage detected in corpus_final")
    return {
        "exact_evaluation_reference_leakage": 0,
        "identity_ge_90_evaluation_reference_leakage": 0,
        "excluded_target_aliases_in_primary": 0,
        "ok": True,
    }


def evidence_by_role(
    roles: Mapping[str, Sequence[Mapping[str, str]]]
) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for label, rows in roles.items():
        counts = Counter(_blank(row.get("evidence_level")) for row in rows)
        out[label] = {level: int(counts.get(level, 0)) for level in ("E2", "E3", "E4", "E5")}
    return out


def source_by_role(
    roles: Mapping[str, Sequence[Mapping[str, str]]]
) -> dict[str, dict[str, int]]:
    return {
        label: dict(Counter(_blank(row.get("source_db")) for row in rows))
        for label, rows in roles.items()
    }


def length_by_role(
    roles: Mapping[str, Sequence[Mapping[str, str]]],
    core_regimes: Mapping[str, str],
) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for label, rows in roles.items():
        cores = {_blank(row.get("sequence_core")) for row in rows}
        cores.discard("")
        counts = Counter(core_regimes[core] for core in cores)
        out[label] = {"short": int(counts.get("short", 0)), "long": int(counts.get("long", 0))}
    return out


def chemistry_counts(rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    return dict(Counter(_blank(row.get("chemistry")) or "unknown" for row in rows))


def family_diagnostic(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    counts = Counter(_blank(row.get("target_family")) or "unknown" for row in rows)
    n = len(rows)
    unknown = counts.get("unknown", 0)
    return {
        "role": "secondary diagnostic only; not used for S7B/S7C optimisation",
        "n_identities": n,
        "n_unknown_family": unknown,
        "unknown_family_fraction": (unknown / n) if n else 0.0,
        "n_known_family": n - unknown,
        "counts": dict(counts.most_common()),
    }


def provenance_audit(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    redistribution = Counter(_blank(row.get("redistribution_status")) or "unknown" for row in rows)
    attested = Counter(
        _blank(row.get("independently_attested_by_permissive_source")) or "unknown"
        for row in rows
    )
    corroboration = Counter(_blank(row.get("corroboration_count")) or "0" for row in rows)
    return {
        "redistribution_status": dict(redistribution),
        "independently_attested_by_permissive_source": dict(attested),
        "corroboration_count": dict(corroboration),
        "legal_conclusion": "none — aggregate provenance only",
        "sequence_bearing_files_public": False,
    }


def _diagnostic_cluster_id(cores: Sequence[str]) -> str:
    payload = "\x1f".join(sorted(sequence_core_sha256(core) for core in cores))
    return "E5D_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _identity_ge_threshold(left: str, right: str, threshold: float) -> bool:
    if not left or not right:
        return False
    denom = max(len(left), len(right))
    if denom == 0:
        return False
    if abs(len(left) - len(right)) / denom > (1.0 - threshold):
        return False
    return global_edit_identity(left, right) >= threshold


def e5_inclusion_diagnostic(
    *,
    e5_rows: Sequence[Mapping[str, str]],
    pre_cap_rows: Sequence[Mapping[str, str]],
    post_cap_rows: Sequence[Mapping[str, str]],
    core_regimes: Mapping[str, str],
    combined_rows: Sequence[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Counterfactual E5 diagnostic. Does not change the frozen corpus."""
    relationship_n = len(e5_rows)
    record_ids = {_blank(row.get("record_id")) for row in e5_rows}
    identity_ids = []
    for row in e5_rows:
        core = row.get("sequence_core") or ""
        target = _blank(row.get("canonical_target_name"))
        identity_ids.append(scientific_identity_id(core, target))
    distinct_identities = set(identity_ids)
    cores = {row.get("sequence_core") or "" for row in e5_rows}
    cores.discard("")
    targets = {_blank(row.get("canonical_target_name")) for row in e5_rows}
    sources = Counter(_blank(row.get("source_db")) for row in e5_rows)
    e5_length = {"short": 0, "long": 0, "unassigned": 0}
    for core in cores:
        label = core_regimes.get(core)
        if label in {"short", "long"}:
            e5_length[label] += 1
        else:
            e5_length["unassigned"] += 1

    pre_ids = {_blank(row.get("scientific_identity_id")) for row in pre_cap_rows}
    post_ids = {_blank(row.get("scientific_identity_id")) for row in post_cap_rows}
    pre_cores = {row.get("sequence_core") or "" for row in pre_cap_rows}
    post_cores = {row.get("sequence_core") or "" for row in post_cap_rows}
    post_core_to_cluster = defaultdict(set)
    for row in post_cap_rows:
        post_core_to_cluster[row.get("sequence_core") or ""].add(_blank(row.get("cluster_id")))

    exact_duplicate_identities = distinct_identities & post_ids
    exact_duplicate_pre_cap = distinct_identities & pre_ids
    novel_identities = distinct_identities - post_ids
    exact_core_attach = cores & post_cores
    novel_cores = cores - post_cores

    family_attach: set[str] = set()
    family_unresolved = False
    if combined_rows:
        family_by_record = {
            _blank(row.get("record_id")): _blank(row.get("near_duplicate_family_id"))
            for row in combined_rows
            if _blank(row.get("near_duplicate_family_id"))
        }
        frozen_family_to_cluster: dict[str, set[str]] = defaultdict(set)
        for row in post_cap_rows:
            family = _blank(row.get("near_duplicate_family_id"))
            if family:
                frozen_family_to_cluster[family].add(_blank(row.get("cluster_id")))
        for row in e5_rows:
            family = family_by_record.get(_blank(row.get("record_id")), "")
            if family and family in frozen_family_to_cluster:
                family_attach.add(row.get("sequence_core") or "")
        if not any(_blank(row.get("near_duplicate_family_id")) for row in combined_rows[:1]) and not family_by_record:
            family_unresolved = True
    else:
        family_unresolved = True

    attached_90: dict[str, str] = {}
    additional_units: list[set[str]] = []
    remaining = sorted(novel_cores - exact_core_attach)
    frozen_core_cluster = {
        core: sorted(cluster_ids)[0]
        for core, cluster_ids in post_core_to_cluster.items()
        if core and cluster_ids
    }
    frozen_by_length: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for frozen_core, cluster_id in frozen_core_cluster.items():
        frozen_by_length[len(frozen_core)].append((cluster_id, frozen_core))
    for core in remaining:
        hits: list[tuple[str, str]] = []
        for length, candidates in frozen_by_length.items():
            if abs(len(core) - length) / max(len(core), length) > (1.0 - IDENTITY_THRESHOLD):
                continue
            for cluster_id, frozen_core in candidates:
                if _identity_ge_threshold(core, frozen_core, IDENTITY_THRESHOLD):
                    hits.append((cluster_id, frozen_core))
        if hits:
            hits.sort()
            attached_90[core] = hits[0][0]
    leftover = [core for core in remaining if core not in attached_90]
    parent = {core: core for core in leftover}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for i, left in enumerate(leftover):
        for right in leftover[i + 1 :]:
            if _identity_ge_threshold(left, right, IDENTITY_THRESHOLD):
                a, b = find(left), find(right)
                if a != b:
                    parent[b] = a
    grouped: dict[str, set[str]] = defaultdict(set)
    for core in leftover:
        grouped[find(core)].add(core)
    additional_units = list(grouped.values())
    diagnostic_cluster_ids = [
        _diagnostic_cluster_id(sorted(group)) for group in additional_units
    ]

    n_post = len(post_cap_rows)
    n_novel = len(novel_identities)
    counterfactual_n = n_post + n_novel
    would_need_cap_rerun = False
    if counterfactual_n:
        # Conservative: adding novel E5 identities changes the denominator and
        # can change every target share, so the frozen 3% cap would need rerun.
        would_need_cap_rerun = n_novel > 0
    splits_invalid = n_novel > 0 or bool(attached_90) or bool(exact_core_attach - cores)

    return {
        "e5_promoted": False,
        "frozen_corpus_changed": False,
        "counterfactual_only": True,
        "statement": (
            "This is a counterfactual diagnostic only. E5 remains excluded and "
            "no frozen split changes. " + E5_DIAGNOSTIC_CLUSTER_STATEMENT
        ),
        "e5_relationship_rows": relationship_n,
        "e5_source_record_count": len(record_ids),
        "e5_exact_identities": len(distinct_identities),
        "e5_distinct_cores": len(cores),
        "e5_targets_represented": len(targets),
        "e5_source_distribution": dict(sources),
        "e5_length_regime_cores": e5_length,
        "e5_length_regime_note": (
            "Assigned with the frozen S6 GMM where a core length is available; "
            "unassigned cores were never given a primary-corpus regime."
        ),
        "overlap": {
            "exact_identities_in_post_cap": len(exact_duplicate_identities),
            "exact_identities_in_pre_cap": len(exact_duplicate_pre_cap),
            "novel_identities": n_novel,
            "exact_cores_in_post_cap": len(exact_core_attach),
            "novel_cores": len(novel_cores),
        },
        "cluster_diagnostic": {
            "method": (
                "exact core match to frozen S5 clusters; 90% global-edit identity "
                "attachment of remaining E5 cores to frozen cores; leftover E5 "
                "cores grouped among themselves at the same 90% threshold with "
                "separate E5D_ diagnostic IDs. This is not a MMseqs recluster and "
                "does not rewrite frozen S5C_ cluster IDs. "
                + E5_DIAGNOSTIC_CLUSTER_STATEMENT
            ),
            "diagnostic_cluster_units_are_counterfactual": True,
            "diagnostic_cluster_units_are_not_future_s5_clusters": True,
            "e5_cores_attaching_by_exact_core": len(exact_core_attach),
            "e5_cores_attaching_by_90pct_identity": len(attached_90),
            "e5_additional_diagnostic_cluster_units": len(additional_units),
            "ena_family_must_link_cores": len(family_attach),
            "ena_family_must_link_unresolved": family_unresolved,
            "diagnostic_cluster_id_prefix": "E5D_",
            "diagnostic_cluster_ids": diagnostic_cluster_ids,
            "frozen_cluster_ids_overwritten": False,
        },
        "counterfactual_impact": {
            "corpus_size_if_novel_identities_added": counterfactual_n,
            "delta_identities": n_novel,
            "evidence_mix": "E5 would enter a currently E2-E4-only primary corpus",
            "target_distribution": (
                f"{len(targets)} E5 canonical targets would be added or inflated; "
                "target cap shares would change because the identity denominator "
                "would change"
            ),
            "source_distribution": dict(sources),
            "split_units": (
                f"{len(additional_units)} additional diagnostic cluster units among "
                "novel E5 cores, plus attachments onto existing frozen clusters"
            ),
            "target_cap_would_need_rerun": would_need_cap_rerun,
            "frozen_ft_ref_eval_would_become_invalid": True if n_novel else splits_invalid,
        },
    }


def sequence_safety_audit(
    *,
    root: Path,
    scan_paths: Sequence[str],
) -> dict[str, Any]:
    new_leaks: list[str] = []
    historical_leaks: list[str] = []
    for rel in scan_paths:
        path = _resolve(root, rel)
        if not path.is_file():
            continue
        current = scan_text_for_sequence_leak(path.read_text(encoding="utf-8"))
        historical = False
        try:
            blob = subprocess.check_output(
                ["git", "show", f"origin/main:{rel}"],
                cwd=root,
                text=True,
                stderr=subprocess.DEVNULL,
            )
            historical = scan_text_for_sequence_leak(blob)
        except subprocess.CalledProcessError:
            historical = False
        if current and not historical:
            new_leaks.append(rel)
        elif current and historical:
            historical_leaks.append(rel)
    if new_leaks:
        raise S7DFinalBuildError(
            "new S7D tracked sequence leaks: " + ", ".join(new_leaks)
        )
    return {
        "n_paths_scanned": len(scan_paths),
        "new_s7d_tracked_sequence_leaks": 0,
        "preexisting_historical_matches_on_origin_main": len(historical_leaks),
        "historical_match_paths": historical_leaks,
    }


def evaluation_reference_summary(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    molecule = Counter(_blank(row.get("molecule_type")) for row in rows)
    label = Counter(_blank(row.get("evaluation_label") or row.get("evaluation_role")) for row in rows)
    targets = Counter(_blank(row.get("target_name")) for row in rows)
    sources = Counter(_blank(row.get("source_key") or row.get("contributing_sources")) for row in rows)
    return {
        "rows": len(rows),
        "molecule_type": dict(molecule),
        "evaluation_label": dict(label),
        "targets": dict(targets),
        "source_or_provenance_groups": dict(sources),
        "distinct_from_eval_partition": (
            "EVAL is the generic held-out corpus partition. "
            "evaluation_references.csv holds target-specific NDM-1/KPC-2/"
            "carbapenemase positive/control references for biological grounding "
            "and leakage exclusion."
        ),
    }


def rejection_breakdown(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    return {
        "n_rows": len(rows),
        "by_stage": dict(Counter(_blank(row.get("stage")) for row in rows)),
        "by_reason": dict(Counter(_blank(row.get("rejection_reason")) for row in rows)),
        "by_source": dict(
            Counter(_blank(row.get("s7d_source") or row.get("source_db")) for row in rows)
        ),
    }


def source_funnel(
    *,
    metadata_paths: Sequence[str],
    root: Path,
    s4_summary_rows: Sequence[Mapping[str, str]],
    pre_cap_rows: Sequence[Mapping[str, str]],
    post_cap_rows: Sequence[Mapping[str, str]],
    roles: Mapping[str, Sequence[Mapping[str, str]]],
) -> list[dict[str, Any]]:
    meta_by_source: dict[str, dict[str, Any]] = {}
    for rel in metadata_paths:
        path = _resolve(root, rel)
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        key = str(payload.get("source_key") or payload.get("source") or path.stem)
        meta_by_source[key] = payload
    s4_by_source: dict[str, dict[str, int]] = defaultdict(dict)
    for row in s4_summary_rows:
        if _blank(row.get("grain")) != "source_record":
            continue
        source = _blank(row.get("source_db"))
        if source in {"", "all"}:
            continue
        s4_by_source[source][_blank(row.get("category"))] = int(row.get("n") or 0)
    pre_source = Counter(_blank(row.get("source_db")) for row in pre_cap_rows)
    post_source = Counter(_blank(row.get("source_db")) for row in post_cap_rows)
    role_source = source_by_role(roles)
    sources = sorted(
        set(meta_by_source)
        | set(s4_by_source)
        | set(pre_source)
        | set(post_source)
        | {src for counts in role_source.values() for src in counts}
    )
    table: list[dict[str, Any]] = []
    for source in sources:
        meta = meta_by_source.get(source, {})
        table.append(
            {
                "source": source,
                "grain_notes": (
                    "CHECKPOINT-1 counts are source-record grain; S4 routes mix "
                    "source-record and relationship grain; S5/S7 counts are "
                    "scientific-identity grain. These are not interchangeable."
                ),
                "checkpoint1_total_or_source_records": meta.get("total_records")
                or meta.get("source_records")
                or meta.get("source_denominator")
                or meta.get("source_rows"),
                "checkpoint1_authorised_for_s4": meta.get("authorised_for_s4")
                or meta.get("technically_eligible"),
                "checkpoint1_parked_ssdna": meta.get("parked_ssdna")
                or meta.get("final_parked_ssdna"),
                "checkpoint1_rejected": meta.get("technical_rejects_after_review")
                or meta.get("final_rejected")
                or meta.get("resolved_reject")
                or meta.get("technical_rejects"),
                "s4_source_record_routes": dict(s4_by_source.get(source, {})),
                "s5_scientific_identities_pre_cap": int(pre_source.get(source, 0)),
                "s7a_retained_identities": int(post_source.get(source, 0)),
                "s7a_removed_identities": int(pre_source.get(source, 0))
                - int(post_source.get(source, 0)),
                "TRAIN": int(role_source.get(TRAIN_LABEL, {}).get(source, 0)),
                "VALIDATION": int(role_source.get(VALIDATION_LABEL, {}).get(source, 0)),
                "REF": int(role_source.get(REF_LABEL, {}).get(source, 0)),
                "EVAL": int(role_source.get(EVAL_LABEL, {}).get(source, 0)),
            }
        )
    return table


def _fmt_share(count: int, n: int) -> str:
    if n == 0:
        return "0"
    return f"{count} / {n} = {count / n:.10f}"


def build_corpus_report(payload: Mapping[str, Any]) -> str:
    cap = payload["target_cap"]
    schema = payload["schema"]
    roles = payload["role_table"]
    txt = payload["corpus_final_txt"]
    evidence = payload["evidence"]
    length = payload["length"]
    sources = payload["source"]
    e5 = payload["e5_diagnostic"]
    leakage = payload["leakage"]
    split = payload["split_leakage"]
    parked = payload["parked"]
    lines = [
        "# Final RNA aptamer corpus report (S7D)",
        "",
        "Sequence-safe aggregate report. No nucleotide strings.",
        "",
        "S7D is assembly, diagnostic, reporting and validation only.",
        "Frozen S7A/S7B/S7C splits were not recalculated.",
        "",
        "## 1. Final headline counts",
        "",
        f"- identities = `{schema['n_scientific_identities']}`",
        f"- distinct sequence_core = `{schema['n_distinct_sequence_core']}`",
        f"- clusters = `{schema['n_final_clusters']}`",
        f"- canonical targets = `{schema['n_canonical_targets']}`",
        f"- max target share = `{_fmt_share(cap['max_target_count'], cap['n'])}` (`{cap['max_target_name']}`)",
        f"- E2/E3/E4/E5 = `{evidence['corpus'].get('E2', 0)}` / `{evidence['corpus'].get('E3', 0)}` / `{evidence['corpus'].get('E4', 0)}` / `{evidence['corpus'].get('E5', 0)}`",
        "",
        "## 2. S7A target-cap before/after",
        "",
        "- pre-cap identities = `1281`; post-cap = `1173`",
        "- pre-cap max target = NGF at `131 / 1281`",
        f"- post-cap max target = `{cap['max_target_name']}` at `{_fmt_share(cap['max_target_count'], cap['n'])}`",
        f"- post-cap NGF = `{_fmt_share(cap['ngf_count'], cap['n'])}`",
        "- removed identities = `108` from two NGF target-pure clusters",
        "",
        "## 3. Final target distribution",
        "",
        f"- distinct canonical targets = `{cap['n_targets']}`",
        f"- maximum share = `{cap['max_target_share']:.10f}` <= `0.03`",
        "",
        "## 4. FT/REF/EVAL split",
        "",
        "| partition | identities |",
        "| --- | ---: |",
        f"| FT | {schema['partition_counts'].get('FT', 0)} |",
        f"| REF | {schema['partition_counts'].get('REF', 0)} |",
        f"| EVAL | {schema['partition_counts'].get('EVAL', 0)} |",
        "",
        "Top-level `partition` remains FT/REF/EVAL. TRAIN/VALIDATION is a subordinate FT split.",
        "",
        "## 5. TRAIN/VALIDATION split",
        "",
        "| role | clusters | identities | cores | targets represented | SHA256 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for label in ROLE_LABELS:
        item = roles[label]
        lines.append(
            f"| {label} | {item['clusters']} | {item['identities']} | {item['cores']} | {item['targets_represented']} | `{item['sha256']}` |"
        )
    lines.extend(
        [
            "",
            "## 6. Evidence distribution",
            "",
            f"- corpus E2/E3/E4/E5 = `{evidence['corpus'].get('E2', 0)}` / `{evidence['corpus'].get('E3', 0)}` / `{evidence['corpus'].get('E4', 0)}` / `{evidence['corpus'].get('E5', 0)}`",
        ]
    )
    for label in ROLE_LABELS:
        item = evidence["by_role"][label]
        lines.append(
            f"- {label} E2/E3/E4 = `{item.get('E2', 0)}` / `{item.get('E3', 0)}` / `{item.get('E4', 0)}`"
        )
    lines.extend(
        [
            "",
            "## 7. Source distribution",
            "",
            "Identity-grain `source_db`. `contributing_sources` is not expanded.",
            "",
        ]
    )
    all_sources = sorted({src for counts in sources["by_role"].values() for src in counts} | set(sources["corpus"]))
    header = "| source | corpus | TRAIN | VALIDATION | REF | EVAL |"
    lines.append(header)
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for src in all_sources:
        lines.append(
            "| {src} | {c} | {t} | {v} | {r} | {e} |".format(
                src=src,
                c=sources["corpus"].get(src, 0),
                t=sources["by_role"].get(TRAIN_LABEL, {}).get(src, 0),
                v=sources["by_role"].get(VALIDATION_LABEL, {}).get(src, 0),
                r=sources["by_role"].get(REF_LABEL, {}).get(src, 0),
                e=sources["by_role"].get(EVAL_LABEL, {}).get(src, 0),
            )
        )
    lines.extend(
        [
            "",
            "## 8. Short/long regime distribution",
            "",
            f"- corpus short/long cores = `{length['corpus'].get('short', 0)}` / `{length['corpus'].get('long', 0)}`",
            "- frozen S6 two-component GMM; not refit",
        ]
    )
    for label in ROLE_LABELS:
        item = length["by_role"][label]
        lines.append(f"- {label} short/long = `{item.get('short', 0)}` / `{item.get('long', 0)}`")
    family = payload["family"]
    lines.extend(
        [
            "",
            "## 9. Chemistry distribution",
            "",
        ]
    )
    for name, count in payload["chemistry"].items():
        lines.append(f"- `{name}` = `{count}`")
    lines.extend(
        [
            "",
            "## 10. Target-family diagnostic",
            "",
            family["role"],
            f"- unknown-family identities = `{family['n_unknown_family']}` / `{family['n_identities']}` = `{family['unknown_family_fraction']:.4f}`",
            "- no final data change results from this diagnostic",
            "",
            "## 11. Corroboration / provenance / licensing",
            "",
            f"- redistribution_status = `{payload['provenance']['redistribution_status']}`",
            f"- independently_attested_by_permissive_source = `{payload['provenance']['independently_attested_by_permissive_source']}`",
            f"- corroboration_count = `{payload['provenance']['corroboration_count']}`",
            "- No legal conclusion is made.",
            "- Sequence-bearing corpus files remain local/ignored and are not intended for public GitHub publication.",
            "",
            "## 12. E5 counterfactual diagnostic",
            "",
            e5["statement"],
            f"- E5 relationship rows = `{e5['e5_relationship_rows']}`",
            f"- E5 source-record count = `{e5['e5_source_record_count']}`",
            f"- exact identities = `{e5['e5_exact_identities']}`",
            f"- distinct cores = `{e5['e5_distinct_cores']}`",
            f"- targets represented = `{e5['e5_targets_represented']}`",
            f"- exact identity overlap with post-cap = `{e5['overlap']['exact_identities_in_post_cap']}`",
            f"- novel identities = `{e5['overlap']['novel_identities']}`",
            f"- exact cores attaching to frozen clusters = `{e5['cluster_diagnostic']['e5_cores_attaching_by_exact_core']}`",
            f"- >=90% diagnostic attachments = `{e5['cluster_diagnostic']['e5_cores_attaching_by_90pct_identity']}`",
            f"- additional diagnostic cluster units = `{e5['cluster_diagnostic']['e5_additional_diagnostic_cluster_units']}`",
            E5_DIAGNOSTIC_CLUSTER_STATEMENT,
            f"- target cap would need rerun if admitted = `{e5['counterfactual_impact']['target_cap_would_need_rerun']}`",
            f"- frozen FT/REF/EVAL would become invalid if admitted = `{e5['counterfactual_impact']['frozen_ft_ref_eval_would_become_invalid']}`",
            "- E5 promoted = no",
            "- frozen corpus changed = no",
            "",
            "## 13. Evaluation-reference summary",
            "",
            payload["evaluation_references"]["distinct_from_eval_partition"],
            f"- rows = `{payload['evaluation_references']['rows']}`",
            f"- molecule_type = `{payload['evaluation_references']['molecule_type']}`",
            f"- evaluation_label = `{payload['evaluation_references']['evaluation_label']}`",
            f"- targets = `{payload['evaluation_references']['targets']}`",
            "",
            "## 14. Source funnel",
            "",
            "Grain differences are labelled. Source-record, relationship, and scientific-identity counts are not interchangeable.",
            "",
        ]
    )
    for row in payload["source_funnel"]:
        lines.append(
            f"- `{row['source']}`: CP1 authorised/eligible `{row['checkpoint1_authorised_for_s4']}`; "
            f"S5 pre-cap identities `{row['s5_scientific_identities_pre_cap']}`; "
            f"S7A retained `{row['s7a_retained_identities']}`; "
            f"TRAIN/VAL/REF/EVAL `{row['TRAIN']}` / `{row['VALIDATION']}` / `{row['REF']}` / `{row['EVAL']}`"
        )
    lines.extend(
        [
            "",
            "## 15. Rejection / parking summary",
            "",
            f"- parked_ssdna rows = `{parked['ssdna']['rows']}`",
            f"- parked_non_protein rows = `{parked['non_protein']['rows']}`",
            f"- parked_evidence_e5 rows = `{parked['e5']['rows']}`",
            f"- rejected_all rows = `{payload['rejection']['n_rows']}`",
            f"- rejected by stage = `{payload['rejection']['by_stage']}`",
            f"- rejected by reason = `{payload['rejection']['by_reason']}`",
            "- Parked records are not classified as rejected.",
            "",
            "## 16. Parked-data completeness and grain",
            "",
            "The three consolidated parked CSVs represent the three principal reusable park classes defined by the governing corpus plan: ssDNA, non-protein targets, and E5 evidence. Additional source-specific unresolved parks may exist. Those are deliberately not coerced into ssDNA, non-protein, or E5 categories. They remain preserved in frozen source/checkpoint artefacts. `parked_inventory.csv` indexes all such lanes. Counts at different grains must not be summed as if they were equivalent.",
            "",
            f"- parked lanes inventoried = `{payload['parked_inventory']['parked_lanes_inventoried']}`",
            f"- parked lanes consolidated = `{payload['parked_inventory']['parked_lanes_consolidated']}`",
            f"- parked lanes retained source-level only = `{payload['parked_inventory']['parked_lanes_retained_source_level_only']}`",
            f"- unaccounted parked lanes = `{payload['parked_inventory']['unaccounted_parked_lanes']}`",
            "",
            "| source | stage | route | grain | rows | disposition |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for row in payload["parked_inventory"]["lanes"]:
        lines.append(
            "| {source} | {stage} | {route} | {grain} | {rows} | {disp} |".format(
                source=row["source"],
                stage=row["stage"],
                route=row["route"],
                grain=row["grain"],
                rows=row["row_count"],
                disp=row["final_disposition"]
                if row["final_disposition"] == RETAINED_DISPOSITION
                else row["consolidated_final_output"],
            )
        )
    replication = payload.get("replication_dataset_a") or {}
    lines.extend(
        [
            "",
            "## 17. Dataset A replication-file role",
            "",
            "`corpus_replication_datasetA.csv` is a separate replication/comparability artefact. It is not part of the primary RNA TRAIN/VALIDATION/REF/EVAL corpus. It does not contribute to `corpus_final.txt`. Its source lane remained outside S4/S5 primary scientific identities.",
            f"- enabled = `{bool(replication.get('enabled'))}`",
            f"- rows = `{replication.get('rows', 0)}`",
            f"- part of primary RNA corpus = `{replication.get('part_of_primary_rna_corpus', False)}`",
            f"- contributes to corpus_final.txt = `{replication.get('contributes_to_corpus_final_txt', False)}`",
            "",
            "## 18. Leakage audit",
            "",
            f"- exact evaluation-reference leakage = `{leakage['exact_evaluation_reference_leakage']}`",
            f"- >=90% evaluation-reference leakage = `{leakage['identity_ge_90_evaluation_reference_leakage']}`",
            f"- excluded target aliases in primary = `{leakage['excluded_target_aliases_in_primary']}`",
            f"- cluster crossings = `{split['cluster_crossings']}`",
            f"- core crossings = `{split['core_crossings']}`",
            f"- identity duplication = `{split['identity_duplication']}`",
            "",
            "## 19. Final integrity gates",
            "",
            f"- corpus_final rows unique identities = `{schema['n_scientific_identities']}`",
            f"- E5 in primary = `{schema['E5']}`",
            f"- non-protein in primary = `{schema['non_protein']}`",
            f"- max target share <= 0.03 = `{cap['ok']}`",
            f"- corpus_final.txt lines = `{txt['line_count']}` from frozen TRAIN only",
            f"- VALIDATION/REF/EVAL contamination of training text = `{txt['validation_contamination']}` / `{txt['ref_contamination']}` / `{txt['eval_contamination']}`",
            "",
            "## 20. Frozen output hashes",
            "",
        ]
    )
    for name, digest in payload["output_hashes"].items():
        lines.append(f"- `{name}` = `{digest}`")
    lines.extend(
        [
            "",
            "## 21. Explicit modelling roles",
            "",
            "- TRAIN -> RNAGenesis fitting",
            "- VALIDATION -> training/model-development decisions",
            "- REF -> AptaRank/reference calibration",
            "- EVAL -> final held-out evaluation",
            "",
            "Model fine-tuning has not started. REF calibration has not started. EVAL evaluation has not started.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def expected_count_guard(observed: Mapping[str, Any], expected: Mapping[str, Any], *, label: str) -> None:
    for key, wanted in expected.items():
        if isinstance(wanted, Mapping):
            got = observed.get(key) or {}
            for inner_key, inner_wanted in wanted.items():
                if int(got.get(inner_key, 0)) != int(inner_wanted):
                    raise S7DFinalBuildError(
                        f"{label} {key}.{inner_key}: expected {inner_wanted}, got {got.get(inner_key, 0)}"
                    )
        elif wanted is not None and observed.get(key) != wanted:
            raise S7DFinalBuildError(f"{label} {key}: expected {wanted}, got {observed.get(key)}")


def _role_summary(rows: Sequence[Mapping[str, str]], sha256: str) -> dict[str, Any]:
    counts = count_identities(rows)
    return {
        "clusters": counts["n_final_clusters"],
        "identities": counts["n_scientific_identities"],
        "cores": counts["n_distinct_sequence_core"],
        "targets_represented": counts["n_canonical_targets"],
        "sha256": sha256,
    }


def run_s7d_final_build(
    *,
    config: Mapping[str, Any],
    repo_root: Path,
    output_dir: Path | None = None,
    verify_hashes: bool = True,
    enforce_expected_counts: bool = True,
    write_outputs: bool = True,
    run_sequence_safety: bool = True,
) -> dict[str, Any]:
    root = repo_root
    dest = output_dir or _resolve(root, config["output_dir"])
    diagnostics_dir = dest / "diagnostics" / "e5_inclusion"
    if write_outputs:
        assert_under_processed(root, dest)
        dest.mkdir(parents=True, exist_ok=True)
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
    git_repo = (root / ".git").exists()
    if verify_hashes and git_repo:
        assert_git_ls_files_data_empty(root)
        expected_head = str(config.get("repository_head_baseline") or "")
        if expected_head and _git_head(root) != expected_head:
            raise S7DFinalBuildError("repository HEAD does not match S7D baseline")

    frozen = config["frozen_inputs"]
    frozen_hashes = {
        key: verify_frozen_file(spec, root, verify_hashes=verify_hashes)
        for key, spec in frozen.items()
    }

    post_cap_path = _resolve(root, frozen["s7a_post_cap"]["path"])
    partitioned_path = _resolve(root, frozen["s7b_partitioned"]["path"])
    train_path = _resolve(root, frozen["s7c_train"]["path"])
    validation_path = _resolve(root, frozen["s7c_validation"]["path"])
    ref_path = _resolve(root, frozen["s7b_ref"]["path"])
    eval_path = _resolve(root, frozen["s7b_eval"]["path"])
    assignment_path = _resolve(root, frozen["s7c_assignment"]["path"])
    pre_cap_path = _resolve(root, frozen["s5_pre_cap_corpus"]["path"])
    s4_rel_path = _resolve(root, frozen["s4_reviewed_relationships"]["path"])
    s4_audit_path = _resolve(root, frozen["s4_parked_audit"]["path"])
    s4_summary_path = _resolve(root, frozen["s4_routing_summary"]["path"])
    combined_path = _resolve(root, frozen["s4_combined_input"]["path"])

    post_cap_rows = _read_csv(post_cap_path)
    partitioned_rows = _read_csv(partitioned_path)
    train_rows = _read_csv(train_path)
    validation_rows = _read_csv(validation_path)
    ref_rows = _read_csv(ref_path)
    eval_rows = _read_csv(eval_path)
    pre_cap_rows = _read_csv(pre_cap_path)
    s4_rows = _read_csv(s4_rel_path)
    s4_audit_rows = _read_csv(s4_audit_path)
    s4_summary_rows = _read_csv(s4_summary_path)
    combined_rows = _read_csv(combined_path) if combined_path.is_file() else []

    post_cap_counts = count_identities(post_cap_rows)
    partitioned_counts = count_identities(partitioned_rows)
    if post_cap_counts != partitioned_counts:
        raise S7DFinalBuildError("S7A post-cap and S7B partitioned identity/core/cluster/target counts drifted")
    if enforce_expected_counts:
        expected_counts = config.get("expected_counts") or {}
        for key in (
            "n_scientific_identities",
            "n_distinct_sequence_core",
            "n_final_clusters",
            "n_canonical_targets",
        ):
            if key in expected_counts and post_cap_counts[key] != expected_counts[key]:
                raise S7DFinalBuildError(
                    f"frozen post-cap {key}: expected {expected_counts[key]}, got {post_cap_counts[key]}"
                )

    train_freeze = verify_semantic_freeze(
        train_rows, frozen["s7c_train"], label="TRAIN", verify_hashes=verify_hashes
    )
    validation_freeze = verify_semantic_freeze(
        validation_rows, frozen["s7c_validation"], label="VALIDATION", verify_hashes=verify_hashes
    )
    ref_freeze = verify_semantic_freeze(
        ref_rows, frozen["s7b_ref"], label="REF", verify_hashes=verify_hashes
    )
    eval_freeze = verify_semantic_freeze(
        eval_rows, frozen["s7b_eval"], label="EVAL", verify_hashes=verify_hashes
    )

    gmm_path = _resolve(root, config["length_regime"]["s6_bimodality_json"])
    gmm = load_frozen_s6_gmm(json.loads(gmm_path.read_text(encoding="utf-8")))
    expected_gmm = config.get("expected_s6_gmm2") or {}
    if verify_hashes and expected_gmm:
        for field in ("means", "variances", "weights"):
            if [float(v) for v in gmm[field]] != [float(v) for v in expected_gmm[field]]:
                raise S7DFinalBuildError(f"frozen S6 GMM {field} mismatch")
    core_regimes = assign_length_regimes(partitioned_rows, gmm)

    txt_lines = build_corpus_final_txt(train_rows)
    txt_gates = training_text_gates(
        txt_lines,
        train_rows=train_rows,
        validation_rows=validation_rows,
        ref_rows=ref_rows,
        eval_rows=eval_rows,
    )
    if enforce_expected_counts:
        expected_txt = int((config.get("expected_counts") or {}).get("n_train_cores") or 0)
        if expected_txt and txt_gates["line_count"] != expected_txt:
            raise S7DFinalBuildError(
                f"corpus_final.txt line count: expected {expected_txt}, got {txt_gates['line_count']}"
            )

    ssdna_cols, ssdna_rows, ssdna_inventory = assemble_parked_ssdna(
        config.get("parked_ssdna_sources") or [], root, verify_hashes=verify_hashes
    )
    nonprot_cols, nonprot_rows, nonprot_inventory = assemble_parked_non_protein(
        config.get("parked_non_protein_sources") or [], root, verify_hashes=verify_hashes
    )
    e5_cols, e5_rows, e5_inventory = assemble_filtered_relationship_lane(
        config["parked_e5_source"],
        root,
        verify_hashes=verify_hashes,
        lane="park_evidence_e5",
    )
    inventory_rows, inventory_summary = assemble_parked_inventory(
        config.get("parked_inventory_lanes") or [],
        root,
        verify_hashes=verify_hashes,
    )
    if enforce_expected_counts and not inventory_summary["parked_lanes_inventoried"]:
        raise S7DFinalBuildError("parked inventory is empty")

    e5_ids = {_blank(row.get("record_id")) for row in e5_rows}
    e5_cores = {row.get("sequence_core") or "" for row in e5_rows}
    primary_ids = {_blank(row.get("record_id")) for row in partitioned_rows}
    primary_cores = {row.get("sequence_core") or "" for row in partitioned_rows}
    if e5_ids & primary_ids:
        raise S7DFinalBuildError("E5 record_id leaked into corpus_final")
    if {core for core in e5_cores if core} & primary_cores:
        # exact core overlap is scientifically possible and is a diagnostic,
        # but E5 rows themselves must not be in the primary tables.
        pass
    if any(_blank(row.get("evidence_level")) == "E5" for row in partitioned_rows):
        raise S7DFinalBuildError("E5 promoted into corpus_final")
    if any(_blank(row.get("target_type")) != "protein" for row in partitioned_rows):
        raise S7DFinalBuildError("non-protein promoted into corpus_final")

    e5_diag_regimes = dict(core_regimes)
    if e5_rows:
        try:
            e5_diag_regimes.update(assign_length_regimes(e5_rows, gmm))
        except Exception:
            # E5 length assignment is diagnostic-only; leave unassigned if lengths are unusable.
            pass
    e5_diagnostic = e5_inclusion_diagnostic(
        e5_rows=e5_rows,
        pre_cap_rows=pre_cap_rows,
        post_cap_rows=post_cap_rows,
        core_regimes=e5_diag_regimes,
        combined_rows=combined_rows,
    )

    s4_exclusion_rows = [
        row
        for row in s4_audit_rows
        if _blank(row.get("audit_class")) in set(config.get("s4_rejection_routes") or [])
        or _blank(row.get("s4_route")) in set(config.get("s4_rejection_routes") or [])
    ]
    reject_cols, reject_rows, reject_inventory = assemble_rejected_all(
        rejection_sources=config.get("rejection_sources") or [],
        s4_rows=s4_exclusion_rows,
        s4_path=frozen["s4_parked_audit"]["path"],
        s4_sha=frozen_hashes["s4_parked_audit"]["sha256"],
        s4_routes=config.get("s4_rejection_routes") or [],
        pre_cap_rows=pre_cap_rows,
        post_cap_rows=post_cap_rows,
        root=root,
        verify_hashes=verify_hashes,
    )

    output_hashes: dict[str, str] = {}
    eval_ref_rows: list[dict[str, str]] = []
    replication_info: dict[str, Any] | None = None
    if write_outputs:
        output_hashes["corpus_final.csv"] = _copy_bytes(partitioned_path, dest / "corpus_final.csv")
        if verify_hashes and output_hashes["corpus_final.csv"] != frozen_hashes["s7b_partitioned"]["sha256"]:
            raise S7DFinalBuildError("corpus_final.csv is not a byte copy of corpus_partitioned.csv")
        output_hashes["ft_train.csv"] = _copy_bytes(train_path, dest / "ft_train.csv")
        output_hashes["ft_validation.csv"] = _copy_bytes(validation_path, dest / "ft_validation.csv")
        output_hashes["ref.csv"] = _copy_bytes(ref_path, dest / "ref.csv")
        output_hashes["eval.csv"] = _copy_bytes(eval_path, dest / "eval.csv")
        output_hashes["ft_split_assignment.csv"] = _copy_bytes(
            assignment_path, dest / "ft_split_assignment.csv"
        )
        for name, key in (
            ("ft_train.csv", "s7c_train"),
            ("ft_validation.csv", "s7c_validation"),
            ("ref.csv", "s7b_ref"),
            ("eval.csv", "s7b_eval"),
            ("ft_split_assignment.csv", "s7c_assignment"),
        ):
            if verify_hashes and output_hashes[name] != frozen_hashes[key]["sha256"]:
                raise S7DFinalBuildError(f"{name} is not a byte copy of the frozen authority")
        output_hashes["corpus_final.txt"] = write_corpus_final_txt(dest / "corpus_final.txt", txt_lines)
        _write_csv(dest / "parked_ssdna.csv", ssdna_rows, ssdna_cols)
        _write_csv(dest / "parked_non_protein_targets.csv", nonprot_rows, nonprot_cols)
        _write_csv(dest / "parked_evidence_e5.csv", e5_rows, e5_cols)
        _write_csv(dest / "rejected_all.csv", reject_rows, reject_cols)
        output_hashes["parked_ssdna.csv"] = _sha256_file(dest / "parked_ssdna.csv")
        output_hashes["parked_non_protein_targets.csv"] = _sha256_file(
            dest / "parked_non_protein_targets.csv"
        )
        output_hashes["parked_evidence_e5.csv"] = _sha256_file(dest / "parked_evidence_e5.csv")
        output_hashes["rejected_all.csv"] = _sha256_file(dest / "rejected_all.csv")
        _write_csv(dest / "parked_inventory.csv", inventory_rows, PARKED_INVENTORY_COLUMNS)
        output_hashes["parked_inventory.csv"] = _sha256_file(dest / "parked_inventory.csv")
        assert_no_sequence_leak(
            (dest / "parked_inventory.csv").read_text(encoding="utf-8"),
            label="parked_inventory.csv",
        )
        eval_sha, eval_ref_rows = assemble_evaluation_references(
            config["evaluation_references"],
            root,
            dest / "evaluation_references.csv",
            verify_hashes=verify_hashes,
        )
        output_hashes["evaluation_references.csv"] = eval_sha
        if config.get("replication_dataset_a", {}).get("enabled"):
            replication_info = assemble_replication_dataset_a(
                config["replication_dataset_a"],
                root,
                dest / "corpus_replication_datasetA.csv",
            )
            output_hashes["corpus_replication_datasetA.csv"] = replication_info["sha256"]
    else:
        eval_ref_rows = _read_csv(_resolve(root, config["evaluation_references"]["path"]))

    final_rows = partitioned_rows
    schema = identity_schema_audit(final_rows)
    cap = target_cap_audit(
        final_rows,
        max_fraction=float(config.get("max_target_fraction") or 0.03),
        expected=config.get("expected_counts") if enforce_expected_counts else None,
    )
    roles = role_rows(
        train_rows=train_rows,
        validation_rows=validation_rows,
        ref_rows=ref_rows,
        eval_rows=eval_rows,
    )
    split = split_leakage_audit(roles)
    if enforce_expected_counts:
        expected_counts = config.get("expected_counts") or {}
        mapping = {
            "n_train": (TRAIN_LABEL, "identities"),
            "n_validation": (VALIDATION_LABEL, "identities"),
            "n_ref": (REF_LABEL, "identities"),
            "n_eval": (EVAL_LABEL, "identities"),
            "n_train_clusters": (TRAIN_LABEL, "clusters"),
            "n_validation_clusters": (VALIDATION_LABEL, "clusters"),
            "n_ref_clusters": (REF_LABEL, "clusters"),
            "n_eval_clusters": (EVAL_LABEL, "clusters"),
            "n_train_cores": (TRAIN_LABEL, "cores"),
            "n_validation_cores": (VALIDATION_LABEL, "cores"),
            "n_ref_cores": (REF_LABEL, "cores"),
            "n_eval_cores": (EVAL_LABEL, "cores"),
        }
        role_counts = {
            TRAIN_LABEL: count_identities(train_rows),
            VALIDATION_LABEL: count_identities(validation_rows),
            REF_LABEL: count_identities(ref_rows),
            EVAL_LABEL: count_identities(eval_rows),
        }
        lookup = {
            "identities": "n_scientific_identities",
            "clusters": "n_final_clusters",
            "cores": "n_distinct_sequence_core",
        }
        for key, (label, kind) in mapping.items():
            if key in expected_counts and role_counts[label][lookup[kind]] != expected_counts[key]:
                raise S7DFinalBuildError(
                    f"{label} {kind}: expected {expected_counts[key]}, got {role_counts[label][lookup[kind]]}"
                )
        if split["sum_identities"] != expected_counts.get("n_scientific_identities", split["sum_identities"]):
            raise S7DFinalBuildError("TRAIN+VALIDATION+REF+EVAL identities do not sum to corpus_final")
        if split["sum_clusters"] != expected_counts.get("n_final_clusters", split["sum_clusters"]):
            raise S7DFinalBuildError("TRAIN+VALIDATION+REF+EVAL clusters do not sum to corpus_final")

    leakage = evaluation_leakage_audit(
        final_rows,
        exclusion_set=_resolve(root, config["leakage_exclusion_set"]),
        alias_csv=_resolve(root, config["leakage_target_aliases"]),
    )
    evidence_roles = evidence_by_role(roles)
    corpus_evidence = Counter(_blank(row.get("evidence_level")) for row in final_rows)
    if enforce_expected_counts:
        expected_evidence = config.get("expected_evidence") or {}
        if expected_evidence.get("corpus"):
            expected_count_guard(
                {"E2": corpus_evidence.get("E2", 0), "E3": corpus_evidence.get("E3", 0), "E4": corpus_evidence.get("E4", 0), "E5": corpus_evidence.get("E5", 0)},
                expected_evidence["corpus"],
                label="corpus evidence",
            )
        for label in ROLE_LABELS:
            if expected_evidence.get(label):
                expected_count_guard(evidence_roles[label], expected_evidence[label], label=f"{label} evidence")

    source_roles = source_by_role(roles)
    corpus_source = dict(Counter(_blank(row.get("source_db")) for row in final_rows))
    if enforce_expected_counts:
        expected_source = config.get("expected_source_identities") or {}
        if expected_source.get("corpus"):
            expected_count_guard(corpus_source, expected_source["corpus"], label="corpus source")
        for label in ROLE_LABELS:
            if expected_source.get(label):
                expected_count_guard(source_roles[label], expected_source[label], label=f"{label} source")

    length_roles = length_by_role(roles, core_regimes)
    corpus_length = Counter(core_regimes.values())
    if enforce_expected_counts:
        expected_length = config.get("expected_length_regime_cores") or {}
        if expected_length.get("corpus"):
            expected_count_guard(dict(corpus_length), expected_length["corpus"], label="corpus length")
        for label in ROLE_LABELS:
            if expected_length.get(label):
                expected_count_guard(length_roles[label], expected_length[label], label=f"{label} length")

    family = family_diagnostic(final_rows)
    provenance = provenance_audit(final_rows)
    chemistry = chemistry_counts(final_rows)
    eval_summary = evaluation_reference_summary(eval_ref_rows)
    reject_summary = rejection_breakdown(reject_rows)
    funnel = source_funnel(
        metadata_paths=config.get("checkpoint_metadata_for_funnel") or [],
        root=root,
        s4_summary_rows=s4_summary_rows,
        pre_cap_rows=pre_cap_rows,
        post_cap_rows=post_cap_rows,
        roles=roles,
    )
    safety = {"n_paths_scanned": 0, "new_s7d_tracked_sequence_leaks": 0}
    if run_sequence_safety:
        safety = sequence_safety_audit(root=root, scan_paths=config.get("sequence_safety_scan_paths") or [])
    if verify_hashes and git_repo:
        assert_git_ls_files_data_empty(root)

    role_table = {
        TRAIN_LABEL: {
            **_role_summary(train_rows, output_hashes.get("ft_train.csv", frozen_hashes["s7c_train"]["sha256"])),
            **train_freeze,
        },
        VALIDATION_LABEL: {
            **_role_summary(
                validation_rows,
                output_hashes.get("ft_validation.csv", frozen_hashes["s7c_validation"]["sha256"]),
            ),
            **validation_freeze,
        },
        REF_LABEL: {
            **_role_summary(ref_rows, output_hashes.get("ref.csv", frozen_hashes["s7b_ref"]["sha256"])),
            **ref_freeze,
        },
        EVAL_LABEL: {
            **_role_summary(eval_rows, output_hashes.get("eval.csv", frozen_hashes["s7b_eval"]["sha256"])),
            **eval_freeze,
        },
    }
    parked_summary = {
        "ssdna": {
            "rows": len(ssdna_rows),
            "distinct_record_ids": len({_blank(row.get("record_id")) for row in ssdna_rows}),
            "sources": sorted({_blank(row.get("s7d_source")) for row in ssdna_rows}),
            "inventory": ssdna_inventory,
            "sha256": output_hashes.get("parked_ssdna.csv", ""),
        },
        "non_protein": {
            "rows": len(nonprot_rows),
            "distinct_record_ids": len({_blank(row.get("record_id")) for row in nonprot_rows}),
            "target_type": dict(Counter(_blank(row.get("target_type")) for row in nonprot_rows)),
            "source": dict(
                Counter(_blank(row.get("s7d_source") or row.get("source_db")) for row in nonprot_rows)
            ),
            "inventory": nonprot_inventory,
            "sha256": output_hashes.get("parked_non_protein_targets.csv", ""),
        },
        "e5": {
            "rows": len(e5_rows),
            "distinct_record_ids": len({_blank(row.get("record_id")) for row in e5_rows}),
            "inventory": e5_inventory,
            "sha256": output_hashes.get("parked_evidence_e5.csv", ""),
        },
    }
    report_payload = {
        "target_cap": cap,
        "schema": schema,
        "role_table": role_table,
        "corpus_final_txt": {**txt_gates, "sha256": output_hashes.get("corpus_final.txt", "")},
        "evidence": {"corpus": dict(corpus_evidence), "by_role": evidence_roles},
        "length": {"corpus": dict(corpus_length), "by_role": length_roles},
        "source": {"corpus": corpus_source, "by_role": source_roles},
        "chemistry": chemistry,
        "family": family,
        "provenance": provenance,
        "e5_diagnostic": e5_diagnostic,
        "evaluation_references": eval_summary,
        "source_funnel": funnel,
        "parked": parked_summary,
        "rejection": reject_summary,
        "leakage": leakage,
        "split_leakage": split,
        "output_hashes": output_hashes,
        "parked_inventory": inventory_summary,
        "replication_dataset_a": replication_info or {
            "enabled": False,
            "part_of_primary_rna_corpus": False,
            "contributes_to_corpus_final_txt": False,
        },
    }
    report = build_corpus_report(report_payload)
    assert_no_sequence_leak(report, label="corpus_report.md")
    output_rel = Path(str(config.get("output_dir") or "data/processed"))
    inventory_rel = str(output_rel / "parked_inventory.csv")
    manifest = {
        "ok": True,
        "build_stage": "S7D",
        "build_date": config.get("build_date"),
        "repository_head_baseline": config.get("repository_head_baseline"),
        "repository_head": _git_head(root) if git_repo else "",
        "governing_plan_version": config.get("governing_plan_version"),
        "source_registry": config.get("source_registry"),
        "source_registry_sha256": (
            _sha256_file(_resolve(root, config["source_registry"]))
            if _resolve(root, str(config.get("source_registry") or "")).is_file()
            else ""
        ),
        "target_cap": 0.03,
        "frozen_input_hashes": frozen_hashes,
        "s7a_frozen_hashes": {"corpus_post_cap.csv": frozen_hashes["s7a_post_cap"]["sha256"]},
        "s7b_frozen_hashes": {
            "corpus_partitioned.csv": frozen_hashes["s7b_partitioned"]["sha256"],
            "ft.csv": frozen_hashes["s7b_ft"]["sha256"],
            "ref.csv": frozen_hashes["s7b_ref"]["sha256"],
            "eval.csv": frozen_hashes["s7b_eval"]["sha256"],
        },
        "s7c_frozen_hashes": {
            "ft_train.csv": frozen_hashes["s7c_train"]["sha256"],
            "ft_validation.csv": frozen_hashes["s7c_validation"]["sha256"],
            "ft_split_assignment.csv": frozen_hashes["s7c_assignment"]["sha256"],
        },
        "s4_frozen_hashes": {
            "reviewed_relationships": frozen_hashes["s4_reviewed_relationships"]["sha256"],
            "reviewed_dictionary": frozen_hashes["s4_reviewed_dictionary"]["sha256"],
            "record_map": frozen_hashes["s4_record_map"]["sha256"],
            "parked_audit": frozen_hashes["s4_parked_audit"]["sha256"],
            "routing_summary": frozen_hashes["s4_routing_summary"]["sha256"],
            "combined_input": frozen_hashes["s4_combined_input"]["sha256"],
        },
        "s5_frozen_hashes": {"corpus_clustered_final.csv": frozen_hashes["s5_pre_cap_corpus"]["sha256"]},
        "ref_eval_freeze_hashes": {
            "REF": ref_freeze,
            "EVAL": eval_freeze,
        },
        "train_validation_freeze_hashes": {
            "TRAIN": train_freeze,
            "VALIDATION": validation_freeze,
        },
        "partition_counts": schema["partition_counts"],
        "train_validation_counts": {
            "TRAIN": role_table[TRAIN_LABEL],
            "VALIDATION": role_table[VALIDATION_LABEL],
        },
        "sequence_length_regime_provenance": {
            "source": "frozen_s6_two_component_gmm",
            "assignment_method": gmm["assignment_method"],
            "refit": False,
            "means": gmm["means"],
            "weights": gmm["weights"],
        },
        "seeds_deterministic_settings": {
            "s7d_recalculates_splits": False,
            "corpus_final_txt_order": config.get("corpus_final_txt_order"),
        },
        "output_paths": {name: str(output_rel / name) for name in output_hashes},
        "output_hashes": output_hashes,
        "e5_diagnostic_status": {
            "e5_promoted": False,
            "frozen_corpus_changed": False,
            "counterfactual_only": True,
            "relationship_rows": e5_diagnostic["e5_relationship_rows"],
            "exact_identities": e5_diagnostic["e5_exact_identities"],
            "distinct_cores": e5_diagnostic["e5_distinct_cores"],
            "exact_core_attachments": e5_diagnostic["cluster_diagnostic"][
                "e5_cores_attaching_by_exact_core"
            ],
            "identity_ge_90_diagnostic_attachments": e5_diagnostic["cluster_diagnostic"][
                "e5_cores_attaching_by_90pct_identity"
            ],
            "e5d_diagnostic_cluster_units": e5_diagnostic["cluster_diagnostic"][
                "e5_additional_diagnostic_cluster_units"
            ],
            "e5d_diagnostic_cluster_units_are_counterfactual": True,
            "e5d_diagnostic_cluster_units_are_not_future_s5_clusters": True,
            "statement": e5_diagnostic["statement"],
        },
        "leakage_gate_results": leakage,
        "split_leakage_gate_results": split,
        "sequence_safety_results": safety,
        "pre_publication_history_audit_required": True,
        "replication_dataset_a": replication_info,
        "parked_inventory_path": inventory_rel,
        "parked_inventory_sha256": output_hashes.get("parked_inventory.csv", ""),
        "parked_inventory": inventory_summary,
        "parked": parked_summary,
        "rejection": reject_summary,
        "model_fine_tuning_started": False,
        "ref_calibration_started": False,
        "eval_evaluation_started": False,
    }
    if write_outputs:
        write_text_atomic(dest / "corpus_report.md", report)
        write_json_atomic(dest / "corpus_manifest.json", jsonable(manifest))
        assert_no_sequence_leak(
            (dest / "corpus_manifest.json").read_text(encoding="utf-8"),
            label="corpus_manifest.json",
        )
        write_json_atomic(diagnostics_dir / "e5_inclusion_impact.json", jsonable(e5_diagnostic))
        output_hashes["corpus_report.md"] = _sha256_file(dest / "corpus_report.md")
        output_hashes["corpus_manifest.json"] = _sha256_file(dest / "corpus_manifest.json")
        if verify_hashes and git_repo:
            assert_git_ls_files_data_empty(root)
    return {
        "ok": True,
        "output_dir": str(dest),
        "output_hashes": output_hashes,
        "frozen_hashes": frozen_hashes,
        "schema": schema,
        "target_cap": cap,
        "role_table": role_table,
        "corpus_final_txt": report_payload["corpus_final_txt"],
        "evidence": report_payload["evidence"],
        "length": report_payload["length"],
        "source": report_payload["source"],
        "chemistry": chemistry,
        "family": family,
        "provenance": provenance,
        "e5_diagnostic": e5_diagnostic,
        "evaluation_references": eval_summary,
        "parked": parked_summary,
        "parked_inventory": inventory_summary,
        "rejection": reject_summary,
        "source_funnel": funnel,
        "leakage": leakage,
        "split_leakage": split,
        "sequence_safety": safety,
        "replication_dataset_a": replication_info,
        "manifest": manifest,
        "report": report,
        "determinism_payloads": SCIENTIFIC_PAYLOAD_NAMES,
    }

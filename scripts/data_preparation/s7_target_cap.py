#!/usr/bin/env python3
"""GLOBAL S7A — 3% whole-cluster target-cap preview and application.

Reads the frozen final S5 clustered corpus. Preview mode emits sequence-free
audit artefacts. Apply mode writes the authoritative post-cap/pre-partition
corpus under ignored ``data/``. Does not write corpus_final, populate
partition, promote E5, rewrite S4/S5/S6, commit, or push.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s4_scientific_common import (  # noqa: E402
    ScientificProposalError,
    write_json_atomic,
    write_text_atomic,
)
from adapters.s5_validate_exact_dedup import scan_paths_for_sequence_leak  # noqa: E402
from adapters.s7_target_cap import (  # noqa: E402
    ACTIVE_MAX_TARGET_FRACTION,
    APPLY_MODE,
    COLLATERAL_SIDECAR_COLUMNS,
    PREVIEW_MODE,
    REMOVED_CLUSTER_COLUMNS,
    TARGET_DISTRIBUTION_COLUMNS,
    TRACE_COLUMNS,
    S7TargetCapError,
    approval_parity_mismatches,
    assert_no_sequence_leak,
    assert_not_forbidden_output_path,
    build_application_report,
    build_preview_report,
    collateral_sidecar_rows,
    compare_target_cap_results,
    enforce_application_config,
    enforce_preview_config,
    format_share_value,
    identity_share,
    independent_post_cap_invariants,
    independent_target_distribution,
    input_unmutated,
    parse_fraction,
    preview_application_parity_mismatches,
    project_identity_rows,
    removed_cluster_rows,
    retained_corpus_rows,
    select_target_cap,
)
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402

DEFAULT_CONFIG = Path("config/global_s7a_target_cap.json")
PREVIEW_OUTPUT_NAMES: dict[str, str] = {
    "removal_trace_csv": "s7a_target_cap_removal_trace.csv",
    "removed_clusters_csv": "s7a_removed_clusters.csv",
    "target_distribution_csv": "s7a_post_cap_target_distribution.csv",
    "collateral_sidecar_csv": "s7a_mixed_cluster_collateral.csv",
    "preview_report_md": "s7a_target_cap_preview_report.md",
    "preview_manifest_json": "s7a_target_cap_preview_manifest.json",
}
APPLICATION_OUTPUT_NAMES: dict[str, str] = {
    "corpus_post_cap_csv": "corpus_post_cap.csv",
    "removal_trace_csv": "s7a_target_cap_removal_trace.csv",
    "removed_clusters_csv": "s7a_removed_clusters.csv",
    "target_distribution_csv": "s7a_post_cap_target_distribution.csv",
    "collateral_sidecar_csv": "s7a_mixed_cluster_collateral.csv",
    "report_md": "s7a_target_cap_report.md",
    "manifest_json": "s7a_target_cap_manifest.json",
}
DETERMINISTIC_PAYLOAD_KEYS: tuple[str, ...] = (
    "corpus_post_cap_csv",
    "removal_trace_csv",
    "removed_clusters_csv",
    "target_distribution_csv",
    "collateral_sidecar_csv",
)
PREVIEW_ARTEFACT_NAMES: tuple[str, ...] = (
    "s7a_target_cap_removal_trace.csv",
    "s7a_removed_clusters.csv",
    "s7a_post_cap_target_distribution.csv",
    "s7a_mixed_cluster_collateral.csv",
    "s7a_target_cap_preview_report.md",
    "s7a_target_cap_preview_manifest.json",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_csv_with_fields(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        return fieldnames, list(reader)


def _resolve(root: Path, relative: str) -> Path:
    return (root / relative).resolve()


def _payload_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_git_ls_files_data_empty(root: Path) -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "data"], cwd=root, text=True
    ).strip()
    if tracked:
        raise S7TargetCapError("git ls-files data is not empty")


def _assert_under_ignored_data(root: Path, path: Path) -> None:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise S7TargetCapError(
            "sequence-bearing S7A corpus is outside the repository"
        ) from exc
    if relative.parts[0] != "data":
        raise S7TargetCapError(
            "sequence-bearing S7A corpus must remain under ignored data/"
        )
    if "processed" in relative.parts:
        raise S7TargetCapError("S7A must not write under data/processed/")


def _write_csv(path: Path, rows: Sequence[Mapping[str, str]], columns: Sequence[str]) -> None:
    assert_not_forbidden_output_path(path)
    for row in rows:
        for key, value in row.items():
            if key in {"sequence_raw", "sequence_full", "sequence_core"}:
                raise S7TargetCapError(f"{path.name} must not contain sequence columns")
            assert_no_sequence_leak(str(value), label=f"{path.name}:{key}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _load_simple_yaml_scalars(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped or ":" not in stripped:
            continue
        key, raw = stripped.split(":", 1)
        values[key.strip()] = raw.strip()
    return values


def _s6_expected_corpus_hash(root: Path, s6_config_rel: str) -> tuple[str, str]:
    s6 = json.loads(_resolve(root, s6_config_rel).read_text(encoding="utf-8"))
    spec = s6["expected_s5_final_hashes"]["corpus_clustered_final_csv"]
    return spec[0], spec[1]


def _verify_frozen_s5_final_hashes(root: Path, s6_config_rel: str) -> dict[str, str]:
    s6 = json.loads(_resolve(root, s6_config_rel).read_text(encoding="utf-8"))
    observed: dict[str, str] = {}
    for name, spec in s6["expected_s5_final_hashes"].items():
        rel, digest = spec[0], spec[1]
        got = sha256_file(_resolve(root, rel))
        if got != digest:
            raise S7TargetCapError(
                f"frozen S5 {name} SHA-256 mismatch: expected {digest}, got {got}"
            )
        observed[name] = got
    return observed


def _verify_input_invariants(rows: Sequence[Mapping[str, str]], expected: Mapping[str, int]) -> dict[str, int]:
    identities = [row["scientific_identity_id"] for row in rows]
    if len(identities) != len(set(identities)):
        raise S7TargetCapError("input scientific_identity_id values are not unique")
    observed = {
        "n_scientific_identities": len(rows),
        "n_distinct_sequence_core": len({row["sequence_core"] for row in rows}),
        "n_final_clusters": len({row["cluster_id"] for row in rows}),
        "n_canonical_targets": len({row["canonical_target_name"] for row in rows}),
    }
    for key, wanted in expected.items():
        if observed.get(key) != wanted:
            raise S7TargetCapError(f"{key}: expected {wanted}, got {observed.get(key)}")
    if any((row.get("partition") or "").strip() for row in rows):
        raise S7TargetCapError("input partition values must all be blank")
    evidence = Counter((row.get("evidence_level") or "").strip() for row in rows)
    if evidence.get("E5", 0) != 0:
        raise S7TargetCapError("input E5 count must remain zero")
    types = { (row.get("target_type") or "").strip() for row in rows }
    if types != {"protein"}:
        raise S7TargetCapError(f"input target types must all be protein, got {sorted(types)}")
    if any(not (row.get("cluster_id") or "").strip() for row in rows):
        raise S7TargetCapError("input cluster_id values must all be populated")
    return observed


def _load_cap_config(root: Path, config_path: Path) -> tuple[dict[str, Any], Decimal]:
    config = json.loads(_resolve(root, str(config_path)).read_text(encoding="utf-8"))
    yaml_values = _load_simple_yaml_scalars(_resolve(root, config["curation_config"]))
    yaml_fraction = parse_fraction(yaml_values["MAX_TARGET_FRACTION"])
    config_fraction = parse_fraction(config["max_target_fraction"])
    if yaml_fraction != config_fraction or yaml_fraction != ACTIVE_MAX_TARGET_FRACTION:
        raise S7TargetCapError(
            "curation_config.yaml and S7A config max_target_fraction must both be 0.03"
        )
    if yaml_values.get("TRAINING_SEQUENCE_COLUMN") != "sequence_core":
        raise S7TargetCapError("TRAINING_SEQUENCE_COLUMN must be sequence_core")
    return config, config_fraction


def _hash_preview_dir(preview_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in PREVIEW_ARTEFACT_NAMES:
        path = preview_dir / name
        if not path.is_file():
            raise S7TargetCapError(f"reviewed preview artefact missing: {name}")
        hashes[name] = _payload_hash(path)
    return hashes


def _write_application_payloads(
    *,
    output_dir: Path,
    fieldnames: Sequence[str],
    retained_rows: Sequence[Mapping[str, str]],
    corpus_rows: Sequence[Mapping[str, str]],
    result: Any,
    independent_rows: Sequence[Mapping[str, str]],
    include_sequence_bearing: bool,
    repo_root: Path | None = None,
) -> dict[str, Path]:
    output_paths = {key: output_dir / name for key, name in APPLICATION_OUTPUT_NAMES.items()}
    for key, path in output_paths.items():
        if key == "corpus_post_cap_csv" and not include_sequence_bearing:
            continue
        assert_not_forbidden_output_path(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    if include_sequence_bearing:
        corpus_path = output_paths["corpus_post_cap_csv"]
        if repo_root is not None:
            _assert_under_ignored_data(repo_root, corpus_path)
        write_corpus_csv_atomic(corpus_path, retained_rows, columns=list(fieldnames))
    _write_csv(
        output_paths["removal_trace_csv"],
        [step.as_row() for step in result.steps],
        TRACE_COLUMNS,
    )
    _write_csv(
        output_paths["removed_clusters_csv"],
        removed_cluster_rows(corpus_rows, result),
        REMOVED_CLUSTER_COLUMNS,
    )
    _write_csv(
        output_paths["target_distribution_csv"],
        independent_rows,
        TARGET_DISTRIBUTION_COLUMNS,
    )
    _write_csv(
        output_paths["collateral_sidecar_csv"],
        collateral_sidecar_rows(result),
        COLLATERAL_SIDECAR_COLUMNS,
    )
    return output_paths


def run_s7a_target_cap_preview(
    *,
    config_path: Path,
    repo_root: Path | None = None,
    verify_hashes: bool = True,
    enforce_expected_counts: bool = True,
    repeat_for_determinism: bool = True,
    write_outputs: bool = True,
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config, config_fraction = _load_cap_config(root, config_path)
    enforce_preview_config(config)

    s6_rel = ""
    s6_digest = ""
    if verify_hashes:
        s6_rel, s6_digest = _s6_expected_corpus_hash(root, config["s6_config"])
        if s6_rel != config["authoritative_corpus"]:
            raise S7TargetCapError(
                "S7A corpus path must match the frozen S6 authoritative corpus"
            )
        if s6_digest != config["expected_input_sha256"]:
            raise S7TargetCapError(
                "S7A expected_input_sha256 must match the frozen S6 S5 hash"
            )

    corpus_path = _resolve(root, config["authoritative_corpus"])
    input_sha = sha256_file(corpus_path)
    if verify_hashes and input_sha != config["expected_input_sha256"]:
        raise S7TargetCapError(
            f"frozen S5 SHA-256 mismatch: expected {config['expected_input_sha256']}, got {input_sha}"
        )
    if verify_hashes:
        _assert_git_ls_files_data_empty(root)

    corpus_rows = _read_csv(corpus_path)
    snapshot = [dict(row) for row in corpus_rows]
    expected = config.get("expected_input_counts") if enforce_expected_counts else None
    if expected:
        _verify_input_invariants(corpus_rows, expected)
    else:
        _verify_input_invariants(
            corpus_rows,
            {
                "n_scientific_identities": len(corpus_rows),
                "n_distinct_sequence_core": len({row["sequence_core"] for row in corpus_rows}),
                "n_final_clusters": len({row["cluster_id"] for row in corpus_rows}),
                "n_canonical_targets": len({row["canonical_target_name"] for row in corpus_rows}),
            },
        )

    target_counts = Counter(row["canonical_target_name"] for row in corpus_rows)
    pre_cap_max_target, pre_cap_max_count = max(
        target_counts.items(), key=lambda item: (item[1], -len(item[0]), item[0])
    )
    pre_cap_max_share = identity_share(pre_cap_max_count, len(corpus_rows))

    first = select_target_cap(corpus_rows, max_target_fraction=config_fraction)
    if repeat_for_determinism:
        second = select_target_cap(
            list(reversed(list(corpus_rows))),
            max_target_fraction=config_fraction,
        )
        compare_target_cap_results(first, second)
    if not input_unmutated(corpus_rows, snapshot):
        raise S7TargetCapError("S7A mutated input corpus rows")
    if verify_hashes and sha256_file(corpus_path) != input_sha:
        raise S7TargetCapError("S7A mutated the frozen S5 input file")

    retained_rows = [
        row
        for row in corpus_rows
        if row["scientific_identity_id"] in set(first.retained_identity_ids)
    ]
    independent_rows = independent_target_distribution(retained_rows)
    independent_max_formatted = independent_rows[0]["share"] if independent_rows else format_share_value(Decimal("0"))
    if independent_max_formatted != format_share_value(first.max_target_share):
        raise S7TargetCapError("independent final max share disagrees with selection loop")
    other_target_exceeded = any(
        step.trigger_target != pre_cap_max_target for step in first.steps
    )

    output_dir = _resolve(root, config["output_dir"])
    output_paths = {key: output_dir / name for key, name in PREVIEW_OUTPUT_NAMES.items()}
    for path in output_paths.values():
        assert_not_forbidden_output_path(path)

    output_hashes: dict[str, str] = {}
    if write_outputs:
        _write_csv(
            output_paths["removal_trace_csv"],
            [step.as_row() for step in first.steps],
            TRACE_COLUMNS,
        )
        _write_csv(
            output_paths["removed_clusters_csv"],
            removed_cluster_rows(corpus_rows, first),
            REMOVED_CLUSTER_COLUMNS,
        )
        _write_csv(
            output_paths["target_distribution_csv"],
            independent_rows,
            TARGET_DISTRIBUTION_COLUMNS,
        )
        _write_csv(
            output_paths["collateral_sidecar_csv"],
            collateral_sidecar_rows(first),
            COLLATERAL_SIDECAR_COLUMNS,
        )
        report = build_preview_report(
            input_sha256=input_sha,
            result=first,
            pre_cap_max_target=pre_cap_max_target,
            pre_cap_max_share=pre_cap_max_share,
            distribution_rows=independent_rows,
            other_target_exceeded_after_reduction=other_target_exceeded,
        )
        write_text_atomic(output_paths["preview_report_md"], report)
        for key, path in output_paths.items():
            if key == "preview_manifest_json":
                continue
            output_hashes[key] = _payload_hash(path)

        scan_paths = [
            _resolve(root, rel) for rel in config.get("sequence_safety_scan_paths", [])
        ]
        leaked = scan_paths_for_sequence_leak(scan_paths)
        if leaked:
            raise S7TargetCapError(
                "sequence leak in tracked S7A files: " + ", ".join(leaked)
            )
        manifest = {
            "ok": True,
            "milestone": config["milestone"],
            "mode": "preview",
            "write_authoritative_capped_corpus": False,
            "scientific_target_cap_applied": False,
            "partition_assigned": False,
            "input_path": config["authoritative_corpus"],
            "input_sha256": input_sha,
            "max_target_fraction": "0.03",
            "denominator_semantics": config["denominator_semantics"],
            "cap_unit": config["cap_unit"],
            "training_sequence_column": config["training_sequence_column"],
            "pre_cap": {
                "n_scientific_identities": first.input_n_identities,
                "n_distinct_sequence_core": first.input_n_cores,
                "n_final_clusters": first.input_n_clusters,
                "n_canonical_targets": first.input_n_targets,
                "max_target": pre_cap_max_target,
                "max_target_share": format_share_value(pre_cap_max_share),
            },
            "preview": {
                "n_removal_steps": len(first.steps),
                "n_clusters_removed": len(first.removed_cluster_ids),
                "n_identities_removed": len(first.removed_identity_ids),
                "n_sequence_cores_removed": first.input_n_cores - first.output_n_cores,
                "n_scientific_identities": first.output_n_identities,
                "n_distinct_sequence_core": first.output_n_cores,
                "n_final_clusters": first.output_n_clusters,
                "n_canonical_targets": first.output_n_targets,
                "max_target": first.max_target_name,
                "max_target_share": format_share_value(first.max_target_share),
                "cap_gate": "PASS" if first.cap_gate_pass else "FAIL",
                "n_pure_clusters_removed": first.n_pure_clusters_removed,
                "n_mixed_clusters_removed": first.n_mixed_clusters_removed,
                "n_collateral_identities_removed": first.n_collateral_identities_removed,
                "other_target_exceeded_3pct_after_denominator_reduction": other_target_exceeded,
            },
            "removal_steps": [step.as_row() for step in first.steps],
            "output_hashes": output_hashes,
            "sequence_safety": {
                "n_paths_scanned": len(scan_paths),
                "n_leaks": 0,
            },
            "determinism_ok": True,
        }
        write_json_atomic(output_paths["preview_manifest_json"], manifest)
        output_hashes["preview_manifest_json"] = _payload_hash(
            output_paths["preview_manifest_json"]
        )
        if verify_hashes:
            _assert_git_ls_files_data_empty(root)
            if sha256_file(corpus_path) != input_sha:
                raise S7TargetCapError("frozen S5 input hash changed after preview")

    projected = project_identity_rows(corpus_rows)
    return {
        "ok": True,
        "input_sha256": input_sha,
        "pre_cap_max_target": pre_cap_max_target,
        "pre_cap_max_share": format_share_value(pre_cap_max_share),
        "result": first,
        "distribution_rows": independent_rows,
        "other_target_exceeded_after_reduction": other_target_exceeded,
        "output_paths": {key: str(path) for key, path in output_paths.items()},
        "output_hashes": output_hashes,
        "n_projected_identities": len(projected),
        "determinism_ok": True,
        "cap_gate": "PASS" if first.cap_gate_pass else "FAIL",
    }


def run_s7a_target_cap_apply(
    *,
    config_path: Path,
    repo_root: Path | None = None,
    verify_hashes: bool = True,
    enforce_expected_counts: bool = True,
    repeat_for_determinism: bool = True,
    write_outputs: bool = True,
    require_preview_parity: bool = True,
    require_approval_parity: bool = True,
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config, config_fraction = _load_cap_config(root, config_path)
    enforce_application_config(config)

    preview_dir = _resolve(root, config["preview_output_dir"])
    output_dir = _resolve(root, config["output_dir"])
    if preview_dir.resolve() == output_dir.resolve():
        raise S7TargetCapError(
            "S7A application must not write to the reviewed preview directory"
        )

    preview_hashes = _hash_preview_dir(preview_dir)
    approval: dict[str, Any] | None = None
    approval_rel = str(config.get("approval_record") or "")
    if approval_rel:
        approval = json.loads(_resolve(root, approval_rel).read_text(encoding="utf-8"))
        expected_preview_hashes = approval.get("reviewed_preview_hashes") or {}
        if expected_preview_hashes and dict(expected_preview_hashes) != preview_hashes:
            raise S7TargetCapError(
                "reviewed preview artefacts have changed since human approval"
            )
        if approval.get("usage", {}).get("used_for_cluster_selection") is True:
            raise S7TargetCapError(
                "approval record must not be configured as a cluster-selection input"
            )
    elif require_approval_parity:
        raise S7TargetCapError("S7A application requires an approval record")

    frozen_s5_hashes: dict[str, str] = {}
    if verify_hashes:
        s6_rel, s6_digest = _s6_expected_corpus_hash(root, config["s6_config"])
        if s6_rel != config["authoritative_corpus"]:
            raise S7TargetCapError(
                "S7A corpus path must match the frozen S6 authoritative corpus"
            )
        if s6_digest != config["expected_input_sha256"]:
            raise S7TargetCapError(
                "S7A expected_input_sha256 must match the frozen S6 S5 hash"
            )
        frozen_s5_hashes = _verify_frozen_s5_final_hashes(root, config["s6_config"])
        _assert_git_ls_files_data_empty(root)

    corpus_path = _resolve(root, config["authoritative_corpus"])
    input_sha = sha256_file(corpus_path)
    if verify_hashes and input_sha != config["expected_input_sha256"]:
        raise S7TargetCapError(
            f"frozen S5 SHA-256 mismatch: expected {config['expected_input_sha256']}, got {input_sha}"
        )
    if approval and approval.get("frozen_input_sha256") not in {"", None}:
        if approval["frozen_input_sha256"] != input_sha:
            raise S7TargetCapError("approval frozen_input_sha256 does not match live S5 input")

    fieldnames, corpus_rows = _read_csv_with_fields(corpus_path)
    snapshot = [dict(row) for row in corpus_rows]
    expected = config.get("expected_input_counts") if enforce_expected_counts else None
    if expected:
        _verify_input_invariants(corpus_rows, expected)
    else:
        _verify_input_invariants(
            corpus_rows,
            {
                "n_scientific_identities": len(corpus_rows),
                "n_distinct_sequence_core": len({row["sequence_core"] for row in corpus_rows}),
                "n_final_clusters": len({row["cluster_id"] for row in corpus_rows}),
                "n_canonical_targets": len({row["canonical_target_name"] for row in corpus_rows}),
            },
        )

    target_counts = Counter(row["canonical_target_name"] for row in corpus_rows)
    pre_cap_max_target, pre_cap_max_count = max(
        target_counts.items(), key=lambda item: (item[1], -len(item[0]), item[0])
    )
    pre_cap_max_share = identity_share(pre_cap_max_count, len(corpus_rows))

    # Selection is derived only from the frozen S5 rows and the cap policy.
    first = select_target_cap(corpus_rows, max_target_fraction=config_fraction)
    if repeat_for_determinism:
        second = select_target_cap(
            list(reversed(list(corpus_rows))),
            max_target_fraction=config_fraction,
        )
        compare_target_cap_results(first, second)
    if not input_unmutated(corpus_rows, snapshot):
        raise S7TargetCapError("S7A mutated input corpus rows")
    if verify_hashes and sha256_file(corpus_path) != input_sha:
        raise S7TargetCapError("S7A mutated the frozen S5 input file")

    preview_trace = _read_csv(preview_dir / PREVIEW_OUTPUT_NAMES["removal_trace_csv"])
    preview_manifest = json.loads(
        (preview_dir / PREVIEW_OUTPUT_NAMES["preview_manifest_json"]).read_text(
            encoding="utf-8"
        )
    )
    preview_summary = preview_manifest.get("preview") or {}
    parity_mismatches = preview_application_parity_mismatches(
        preview_step_rows=preview_trace,
        application=first,
        preview_summary=preview_summary,
    )
    if require_preview_parity and parity_mismatches:
        raise S7TargetCapError(
            "preview/application semantic mismatches: " + "; ".join(parity_mismatches)
        )
    approval_mismatches: list[str] = []
    if approval is not None:
        approval_mismatches = approval_parity_mismatches(first, approval)
        if require_approval_parity and approval_mismatches:
            raise S7TargetCapError(
                "approval/application semantic mismatches: "
                + "; ".join(approval_mismatches)
            )

    retained_rows = retained_corpus_rows(corpus_rows, first.retained_identity_ids)
    independent_rows = independent_target_distribution(retained_rows)
    independent_max_formatted = (
        independent_rows[0]["share"] if independent_rows else format_share_value(Decimal("0"))
    )
    if independent_max_formatted != format_share_value(first.max_target_share):
        raise S7TargetCapError("independent final max share disagrees with selection loop")
    other_target_exceeded = any(
        step.trigger_target != pre_cap_max_target for step in first.steps
    )
    independent = independent_post_cap_invariants(
        input_rows=corpus_rows,
        retained_rows=retained_rows,
        result=first,
        max_target_fraction=config_fraction,
    )

    output_paths = {key: output_dir / name for key, name in APPLICATION_OUTPUT_NAMES.items()}
    output_hashes: dict[str, str] = {}
    determinism_ok = True
    if write_outputs:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        if repeat_for_determinism:
            with tempfile.TemporaryDirectory(
                prefix="s7a_apply_a_", dir=str(output_dir.parent)
            ) as first_dir, tempfile.TemporaryDirectory(
                prefix="s7a_apply_b_", dir=str(output_dir.parent)
            ) as second_dir:
                first_paths = _write_application_payloads(
                    output_dir=Path(first_dir),
                    fieldnames=fieldnames,
                    retained_rows=retained_rows,
                    corpus_rows=corpus_rows,
                    result=first,
                    independent_rows=independent_rows,
                    include_sequence_bearing=True,
                    repo_root=root,
                )
                second_paths = _write_application_payloads(
                    output_dir=Path(second_dir),
                    fieldnames=fieldnames,
                    retained_rows=retained_rows,
                    corpus_rows=corpus_rows,
                    result=first,
                    independent_rows=independent_rows,
                    include_sequence_bearing=True,
                    repo_root=root,
                )
                for key in DETERMINISTIC_PAYLOAD_KEYS:
                    if _payload_hash(first_paths[key]) != _payload_hash(second_paths[key]):
                        raise S7TargetCapError(
                            f"S7A application payload {key} is not byte-identical across reruns"
                        )
        written_paths = _write_application_payloads(
            output_dir=output_dir,
            fieldnames=fieldnames,
            retained_rows=retained_rows,
            corpus_rows=corpus_rows,
            result=first,
            independent_rows=independent_rows,
            include_sequence_bearing=True,
            repo_root=root,
        )
        reloaded = _read_csv(written_paths["corpus_post_cap_csv"])
        independent = independent_post_cap_invariants(
            input_rows=corpus_rows,
            retained_rows=reloaded,
            result=first,
            max_target_fraction=config_fraction,
        )
        payload_hashes = {
            key: _payload_hash(written_paths[key]) for key in DETERMINISTIC_PAYLOAD_KEYS
        }
        report = build_application_report(
            input_sha256=input_sha,
            result=first,
            pre_cap_max_target=pre_cap_max_target,
            pre_cap_max_share=pre_cap_max_share,
            distribution_rows=independent_rows,
            other_target_exceeded_after_reduction=other_target_exceeded,
            preview_hashes=preview_hashes,
            output_hashes=payload_hashes,
            parity_mismatches=parity_mismatches,
            independent=independent,
            determinism_ok=determinism_ok,
        )
        write_text_atomic(written_paths["report_md"], report)
        scan_paths = [
            _resolve(root, rel) for rel in config.get("sequence_safety_scan_paths", [])
        ]
        leaked = scan_paths_for_sequence_leak(scan_paths)
        if leaked:
            raise S7TargetCapError(
                "sequence leak in tracked S7A files: " + ", ".join(leaked)
            )
        manifest = {
            "ok": True,
            "milestone": config["milestone"],
            "mode": APPLY_MODE,
            "write_authoritative_capped_corpus": True,
            "scientific_target_cap_applied": True,
            "partition_assigned": False,
            "s7b_started": False,
            "approval_record": approval_rel,
            "approval_used_for_cluster_selection": False,
            "input_path": config["authoritative_corpus"],
            "input_sha256": input_sha,
            "frozen_s5_final_hashes_ok": bool(frozen_s5_hashes) or not verify_hashes,
            "max_target_fraction": "0.03",
            "denominator_semantics": config["denominator_semantics"],
            "cap_unit": config["cap_unit"],
            "training_sequence_column": config["training_sequence_column"],
            "preview_dir": config["preview_output_dir"],
            "preview_hashes": preview_hashes,
            "preview_application_semantic_mismatches": parity_mismatches,
            "n_preview_application_semantic_mismatches": len(parity_mismatches),
            "approval_parity_mismatches": approval_mismatches,
            "pre_cap": {
                "n_scientific_identities": first.input_n_identities,
                "n_distinct_sequence_core": first.input_n_cores,
                "n_final_clusters": first.input_n_clusters,
                "n_canonical_targets": first.input_n_targets,
                "max_target": pre_cap_max_target,
                "max_target_share": format_share_value(pre_cap_max_share),
            },
            "application": {
                "n_removal_steps": len(first.steps),
                "n_clusters_removed": len(first.removed_cluster_ids),
                "n_identities_removed": len(first.removed_identity_ids),
                "n_sequence_cores_removed": first.input_n_cores - first.output_n_cores,
                "n_scientific_identities": first.output_n_identities,
                "n_distinct_sequence_core": first.output_n_cores,
                "n_final_clusters": first.output_n_clusters,
                "n_canonical_targets": first.output_n_targets,
                "max_target": first.max_target_name,
                "max_target_share": format_share_value(first.max_target_share),
                "cap_gate": "PASS" if first.cap_gate_pass else "FAIL",
                "n_pure_clusters_removed": first.n_pure_clusters_removed,
                "n_mixed_clusters_removed": first.n_mixed_clusters_removed,
                "n_collateral_identities_removed": first.n_collateral_identities_removed,
                "other_target_exceeded_3pct_after_denominator_reduction": other_target_exceeded,
                "evidence_counts": independent["evidence_counts"],
                "source_counts": independent["source_counts"],
                "chemistry_counts": independent["chemistry_counts"],
                "target_type_counts": independent["target_type_counts"],
            },
            "removal_steps": [step.as_row() for step in first.steps],
            "output_hashes": payload_hashes,
            "sequence_safety": {
                "n_paths_scanned": len(scan_paths),
                "n_leaks": 0,
            },
            "determinism_ok": determinism_ok,
        }
        write_json_atomic(written_paths["manifest_json"], manifest)
        output_hashes = dict(payload_hashes)
        output_hashes["report_md"] = _payload_hash(written_paths["report_md"])
        output_hashes["manifest_json"] = _payload_hash(written_paths["manifest_json"])
        post_preview_hashes = _hash_preview_dir(preview_dir)
        if post_preview_hashes != preview_hashes:
            raise S7TargetCapError("S7A application overwrote the reviewed preview artefacts")
        if verify_hashes:
            _assert_git_ls_files_data_empty(root)
            if sha256_file(corpus_path) != input_sha:
                raise S7TargetCapError("frozen S5 input hash changed after application")
        output_paths = written_paths

    return {
        "ok": True,
        "input_sha256": input_sha,
        "pre_cap_max_target": pre_cap_max_target,
        "pre_cap_max_share": format_share_value(pre_cap_max_share),
        "result": first,
        "distribution_rows": independent_rows,
        "other_target_exceeded_after_reduction": other_target_exceeded,
        "output_paths": {key: str(path) for key, path in output_paths.items()},
        "output_hashes": output_hashes,
        "preview_hashes": preview_hashes,
        "parity_mismatches": parity_mismatches,
        "approval_mismatches": approval_mismatches,
        "independent": independent,
        "determinism_ok": determinism_ok,
        "cap_gate": "PASS" if first.cap_gate_pass else "FAIL",
        "approval_used_for_cluster_selection": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="S7A 3% target-cap preview / application")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--skip-expected-counts",
        action="store_true",
        help="Do not enforce live S5 regression counts (synthetic use only)",
    )
    parser.add_argument(
        "--skip-hash-gate",
        action="store_true",
        help="Do not verify frozen S5 SHA-256 (synthetic use only)",
    )
    parser.add_argument(
        "--skip-determinism-repeat",
        action="store_true",
        help="Select once (not authorised for the live scientific freeze)",
    )
    args = parser.parse_args()
    root = find_repo_root()
    config = json.loads(_resolve(root, str(args.config)).read_text(encoding="utf-8"))
    mode = str(config.get("mode") or "").strip()
    try:
        if mode == PREVIEW_MODE:
            result = run_s7a_target_cap_preview(
                config_path=args.config,
                enforce_expected_counts=not args.skip_expected_counts,
                verify_hashes=not args.skip_hash_gate,
                repeat_for_determinism=not args.skip_determinism_repeat,
            )
            payload_result = result["result"]
            print(
                json.dumps(
                    {
                        "ok": True,
                        "mode": PREVIEW_MODE,
                        "input_sha256": result["input_sha256"],
                        "n_scientific_identities_in": payload_result.input_n_identities,
                        "n_scientific_identities_preview": payload_result.output_n_identities,
                        "n_removal_steps": len(payload_result.steps),
                        "n_clusters_removed": len(payload_result.removed_cluster_ids),
                        "max_target_share": format_share_value(payload_result.max_target_share),
                        "cap_gate": result["cap_gate"],
                        "scientific_target_cap_applied": False,
                        "determinism_ok": result["determinism_ok"],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if mode == APPLY_MODE:
            result = run_s7a_target_cap_apply(
                config_path=args.config,
                enforce_expected_counts=not args.skip_expected_counts,
                verify_hashes=not args.skip_hash_gate,
                repeat_for_determinism=not args.skip_determinism_repeat,
            )
            payload_result = result["result"]
            print(
                json.dumps(
                    {
                        "ok": True,
                        "mode": APPLY_MODE,
                        "input_sha256": result["input_sha256"],
                        "n_scientific_identities_in": payload_result.input_n_identities,
                        "n_scientific_identities_retained": payload_result.output_n_identities,
                        "n_removal_steps": len(payload_result.steps),
                        "n_clusters_removed": len(payload_result.removed_cluster_ids),
                        "max_target_share": format_share_value(payload_result.max_target_share),
                        "cap_gate": result["cap_gate"],
                        "scientific_target_cap_applied": True,
                        "partition_assigned": False,
                        "s7b_started": False,
                        "n_preview_application_semantic_mismatches": len(
                            result["parity_mismatches"]
                        ),
                        "approval_used_for_cluster_selection": False,
                        "determinism_ok": result["determinism_ok"],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        raise S7TargetCapError(f"S7A mode must be preview or apply, got {mode!r}")
    except (S7TargetCapError, ScientificProposalError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""GLOBAL S7B — whole-cluster FT/REF/EVAL assignment preview and application.

Preview mode writes sequence-free dry-run artefacts. Apply mode rederives
the same assignment from frozen S7A input, writes the authoritative
partitioned corpus under ignored ``data/interim/s7b_partition/``, and
freezes REF/EVAL. Does not write corpus_final, create an FT
train/validation split, rewrite S5/S6/S7A, begin S7C, commit, or push.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s4_scientific_common import (  # noqa: E402
    write_json_atomic,
    write_text_atomic,
)
from adapters.s5_validate_exact_dedup import scan_paths_for_sequence_leak  # noqa: E402
from adapters.s7_partition import (  # noqa: E402
    APPLY_MODE,
    CLUSTER_ASSIGNMENT_COLUMNS,
    CLUSTER_PREVIEW_COLUMNS,
    CORE_SUMMARY_COLUMNS,
    DIVERGENCE_COLUMNS,
    EVIDENCE_DISTRIBUTION_COLUMNS,
    FAMILY_DIAGNOSTIC_COLUMNS,
    FREEZE_DATE,
    FREEZE_REASON,
    IDENTITY_SUMMARY_COLUMNS,
    LENGTH_DISTRIBUTION_COLUMNS,
    PREVIEW_MODE,
    SOURCE_DISTRIBUTION_COLUMNS,
    TARGET_DISTRIBUTION_COLUMNS,
    S7PartitionError,
    approval_parity_mismatches,
    assert_no_sequence_leak,
    assert_not_forbidden_output_path,
    assign_length_regimes,
    assignment_from_partitioned_rows,
    build_application_report,
    build_application_tables,
    build_cluster_features,
    build_freeze_record,
    build_preview_report,
    build_preview_tables,
    derive_integer_quotas,
    enforce_application_config,
    evaluate_random_baselines,
    family_jsd_by_partition,
    independent_distribution_counts,
    independent_partition_invariants,
    input_unmutated,
    integrity_gates,
    jsonable,
    load_frozen_s6_gmm,
    partition_subset_rows,
    populate_partition_on_corpus,
    preview_application_parity_mismatches,
    score_assignment,
    select_preview_assignment,
    semantic_cluster_set_hash,
    semantic_identity_set_hash,
    states_from_assignment,
    target_representation_diagnostics,
    verify_frozen_identities,
)
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402

DEFAULT_CONFIG = Path("config/global_s7b_partition.json")
PREVIEW_OUTPUT_NAMES: dict[str, str] = {
    "cluster_partition_preview_csv": "cluster_partition_preview.csv",
    "partition_identity_summary_csv": "partition_identity_summary.csv",
    "partition_core_summary_csv": "partition_core_summary.csv",
    "partition_target_distribution_csv": "partition_target_distribution.csv",
    "partition_evidence_distribution_csv": "partition_evidence_distribution.csv",
    "partition_length_regime_distribution_csv": "partition_length_regime_distribution.csv",
    "partition_source_distribution_csv": "partition_source_distribution.csv",
    "partition_target_family_diagnostic_csv": "partition_target_family_diagnostic.csv",
    "partition_divergence_metrics_csv": "partition_divergence_metrics.csv",
    "preview_report_md": "s7b_partition_preview_report.md",
    "preview_manifest_json": "s7b_partition_preview_manifest.json",
}
PREVIEW_ARTEFACT_NAMES: tuple[str, ...] = tuple(PREVIEW_OUTPUT_NAMES.values())
APPLICATION_OUTPUT_NAMES: dict[str, str] = {
    "corpus_partitioned_csv": "corpus_partitioned.csv",
    "cluster_partition_assignment_csv": "cluster_partition_assignment.csv",
    "ft_csv": "ft.csv",
    "ref_csv": "ref.csv",
    "eval_csv": "eval.csv",
    "partition_identity_summary_csv": "partition_identity_summary.csv",
    "partition_core_summary_csv": "partition_core_summary.csv",
    "partition_target_distribution_csv": "partition_target_distribution.csv",
    "partition_evidence_distribution_csv": "partition_evidence_distribution.csv",
    "partition_length_regime_distribution_csv": "partition_length_regime_distribution.csv",
    "partition_source_distribution_csv": "partition_source_distribution.csv",
    "partition_target_family_diagnostic_csv": "partition_target_family_diagnostic.csv",
    "partition_divergence_metrics_csv": "partition_divergence_metrics.csv",
    "report_md": "s7b_partition_report.md",
    "manifest_json": "s7b_partition_manifest.json",
}
DETERMINISTIC_PAYLOAD_NAMES: tuple[str, ...] = (
    "corpus_partitioned.csv",
    "cluster_partition_assignment.csv",
    "ft.csv",
    "ref.csv",
    "eval.csv",
    "partition_identity_summary.csv",
    "partition_core_summary.csv",
    "partition_target_distribution.csv",
    "partition_evidence_distribution.csv",
    "partition_length_regime_distribution.csv",
    "partition_source_distribution.csv",
    "partition_target_family_diagnostic.csv",
    "partition_divergence_metrics.csv",
)
TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "cluster_partition_preview.csv": CLUSTER_PREVIEW_COLUMNS,
    "cluster_partition_assignment.csv": CLUSTER_ASSIGNMENT_COLUMNS,
    "partition_identity_summary.csv": IDENTITY_SUMMARY_COLUMNS,
    "partition_core_summary.csv": CORE_SUMMARY_COLUMNS,
    "partition_target_distribution.csv": TARGET_DISTRIBUTION_COLUMNS,
    "partition_evidence_distribution.csv": EVIDENCE_DISTRIBUTION_COLUMNS,
    "partition_length_regime_distribution.csv": LENGTH_DISTRIBUTION_COLUMNS,
    "partition_source_distribution.csv": SOURCE_DISTRIBUTION_COLUMNS,
    "partition_target_family_diagnostic.csv": FAMILY_DIAGNOSTIC_COLUMNS,
    "partition_divergence_metrics.csv": DIVERGENCE_COLUMNS,
}


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
        raise S7PartitionError("git ls-files data is not empty")


def _assert_under_ignored_data(root: Path, path: Path) -> None:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise S7PartitionError("S7B preview path is outside the repository") from exc
    if relative.parts[0] != "data":
        raise S7PartitionError("S7B preview artefacts must remain under ignored data/")
    if "processed" in relative.parts:
        raise S7PartitionError("S7B preview must not write under data/processed/")


def _write_csv(path: Path, rows: Sequence[Mapping[str, str]], columns: Sequence[str]) -> None:
    assert_not_forbidden_output_path(path)
    for row in rows:
        for key, value in row.items():
            if key in {"sequence_raw", "sequence_full", "sequence_core"}:
                raise S7PartitionError(f"{path.name} must not contain sequence columns")
            assert_no_sequence_leak(str(value), label=f"{path.name}:{key}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _hash_preview_dir(preview_dir: Path) -> dict[str, str]:
    if not preview_dir.is_dir():
        raise S7PartitionError("reviewed preview directory is missing")
    hashes: dict[str, str] = {}
    for path in sorted(preview_dir.iterdir()):
        if path.is_file():
            hashes[path.name] = _payload_hash(path)
    missing = [name for name in PREVIEW_ARTEFACT_NAMES if name not in hashes]
    if missing:
        raise S7PartitionError(
            "reviewed preview artefact missing: " + ", ".join(missing)
        )
    return hashes


def _verify_s7a_artefact_hashes(root: Path, config: Mapping[str, Any]) -> dict[str, str]:
    expected = config.get("expected_s7a_artefact_hashes") or {}
    observed: dict[str, str] = {}
    for relative, digest in expected.items():
        path = _resolve(root, str(relative))
        got = sha256_file(path)
        if got != digest:
            raise S7PartitionError(
                f"frozen S7A artefact {relative} SHA-256 mismatch: expected {digest}, got {got}"
            )
        observed[str(relative)] = got
    return observed


def _preview_assignment_from_csv(path: Path) -> dict[str, str]:
    rows = _read_csv(path)
    assignment: dict[str, str] = {}
    for row in rows:
        cluster_id = str(row.get("cluster_id") or "").strip()
        label = str(row.get("proposed_partition") or row.get("partition") or "").strip()
        if not cluster_id or not label:
            raise S7PartitionError("preview assignment row is missing cluster_id or partition")
        if cluster_id in assignment:
            raise S7PartitionError("preview assignment repeats a cluster_id")
        assignment[cluster_id] = label
    return assignment


def _preview_tables_from_dir(preview_dir: Path) -> dict[str, list[dict[str, str]]]:
    tables: dict[str, list[dict[str, str]]] = {}
    for name in TABLE_COLUMNS:
        if name == "cluster_partition_assignment.csv":
            continue
        path = preview_dir / name
        if path.is_file():
            tables[name] = _read_csv(path)
    return tables


def _derive_s7b_assignment(
    *,
    corpus_rows: Sequence[Mapping[str, str]],
    config: Mapping[str, Any],
    gmm: Mapping[str, Any],
    expected_counts: Mapping[str, int] | None,
    repeat_for_determinism: bool,
    run_random_baseline: bool,
) -> dict[str, Any]:
    snapshot = [dict(row) for row in corpus_rows]
    observed = verify_frozen_identities(corpus_rows, expected_counts)
    core_regimes = assign_length_regimes(corpus_rows, gmm)
    n_short = sum(1 for label in core_regimes.values() if label == "short")
    n_long = sum(1 for label in core_regimes.values() if label == "long")
    if n_short + n_long != observed["n_distinct_sequence_core"]:
        raise S7PartitionError("length-regime assignment does not cover every retained core")
    features, space = build_cluster_features(corpus_rows, core_regimes)
    if space.n_clusters != observed["n_final_clusters"]:
        raise S7PartitionError("cluster feature count drifted from input")
    fractions = config.get("partition_fractions") or {"FT": 0.80, "REF": 0.10, "EVAL": 0.10}
    quota_candidates = derive_integer_quotas(space.n_clusters, fractions)
    max_passes = int(config.get("local_search_max_passes") or 10_000)
    raw_evals = config.get("local_search_max_evals")
    raw_seconds = config.get("local_search_max_seconds")
    max_evals = None if raw_evals in (None, "") else int(raw_evals)
    max_seconds = None if raw_seconds in (None, "") else float(raw_seconds)
    progress = bool(config.get("local_search_progress", False))
    progress_every = int(config.get("local_search_progress_every") or 5_000)
    search_kwargs = {
        "max_passes": max_passes,
        "max_evals": max_evals,
        "max_seconds": max_seconds,
        "progress": progress,
        "progress_every": progress_every,
    }
    selected = select_preview_assignment(
        features, space, quota_candidates, **search_kwargs
    )
    if repeat_for_determinism:
        reversed_features, reversed_space = build_cluster_features(
            list(reversed(list(corpus_rows))), core_regimes
        )
        again = select_preview_assignment(
            reversed_features,
            reversed_space,
            quota_candidates,
            **search_kwargs,
        )
        if again["assignment"] != selected["assignment"]:
            raise S7PartitionError("S7B assignment depends on input row order")
        if again["comparison_tuple"] != selected["comparison_tuple"]:
            raise S7PartitionError("S7B comparison tuple depends on input row order")
    assignment = selected["assignment"]
    quotas = selected["quotas"]
    score = selected["score"]
    integrity = integrity_gates(corpus_rows, assignment, features, quotas)
    if integrity["E5"] != 0 or integrity["non_protein"] != 0:
        raise S7PartitionError("S7B introduced E5 or non-protein records")
    states = states_from_assignment(assignment, features, space)
    family_js = family_jsd_by_partition(states, space)
    target_diag = target_representation_diagnostics(corpus_rows, assignment)
    tables = build_preview_tables(
        features=features,
        space=space,
        assignment=assignment,
        score=score,
        family_js=family_js,
    )
    random_diag = None
    if run_random_baseline:
        seeds = [int(seed) for seed in config.get("random_baseline_seeds", [])]
        if seeds:
            random_diag = evaluate_random_baselines(features, space, quotas, seeds)
    if not input_unmutated(corpus_rows, snapshot):
        raise S7PartitionError("S7B mutated input corpus rows")
    return {
        "observed": observed,
        "core_regimes": core_regimes,
        "n_short": n_short,
        "n_long": n_long,
        "features": features,
        "space": space,
        "quota_candidates": quota_candidates,
        "selected": selected,
        "assignment": assignment,
        "quotas": quotas,
        "score": score,
        "integrity": integrity,
        "family_js": family_js,
        "target_diag": target_diag,
        "tables": tables,
        "random_diag": random_diag,
    }


def _write_application_payloads(
    *,
    output_dir: Path,
    fieldnames: Sequence[str],
    partitioned_rows: Sequence[Mapping[str, str]],
    tables: Mapping[str, Sequence[Mapping[str, str]]],
    repo_root: Path | None = None,
) -> dict[str, Path]:
    output_paths = {key: output_dir / name for key, name in APPLICATION_OUTPUT_NAMES.items()}
    for path in output_paths.values():
        assert_not_forbidden_output_path(path)
    if repo_root is not None:
        _assert_under_ignored_data(repo_root, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_corpus_csv_atomic(
        output_paths["corpus_partitioned_csv"],
        partitioned_rows,
        columns=list(fieldnames),
    )
    for label, key in (("FT", "ft_csv"), ("REF", "ref_csv"), ("EVAL", "eval_csv")):
        write_corpus_csv_atomic(
            output_paths[key],
            partition_subset_rows(partitioned_rows, label),
            columns=list(fieldnames),
        )
    for name, rows in tables.items():
        if name not in TABLE_COLUMNS:
            continue
        _write_csv(output_dir / name, rows, TABLE_COLUMNS[name])
    return output_paths


def enforce_preview_config(config: Mapping[str, Any]) -> None:
    mode = str(config.get("mode") or "").strip()
    if mode != PREVIEW_MODE:
        raise S7PartitionError(f"S7B mode must be preview, got {mode!r}")
    if config.get("write_authoritative_partitioned_corpus") is True:
        raise S7PartitionError("S7B preview must not write an authoritative partitioned corpus")
    if config.get("freeze_ref") is True or config.get("freeze_eval") is True:
        raise S7PartitionError("S7B preview must not freeze REF/EVAL")
    does_not = {str(item) for item in config.get("does_not", [])}
    required = {
        "write_authoritative_partitioned_corpus",
        "write_corpus_final",
        "freeze_ref",
        "freeze_eval",
        "populate_partition_on_s7a_input",
        "create_train_validation_split",
        "promote_e5",
        "promote_non_protein",
    }
    missing = sorted(required - does_not)
    if missing:
        raise S7PartitionError(f"S7B config.does_not missing required exclusions: {missing}")


def _expected_gmm_matches(config: Mapping[str, Any], gmm: Mapping[str, Any]) -> None:
    expected = config.get("expected_s6_gmm2")
    if not expected:
        return
    for field in ("means", "variances", "weights"):
        got = [float(v) for v in gmm[field]]
        wanted = [float(v) for v in expected[field]]
        if got != wanted:
            raise S7PartitionError(f"frozen S6 GMM {field} mismatch")


def run_s7b_partition_preview(
    *,
    config_path: Path,
    repo_root: Path | None = None,
    verify_hashes: bool = True,
    enforce_expected_counts: bool = True,
    repeat_for_determinism: bool = True,
    write_outputs: bool = True,
    run_random_baseline: bool = True,
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config = json.loads(_resolve(root, str(config_path)).read_text(encoding="utf-8"))
    enforce_preview_config(config)

    corpus_path = _resolve(root, config["authoritative_corpus"])
    input_sha = sha256_file(corpus_path)
    if verify_hashes and input_sha != config["expected_input_sha256"]:
        raise S7PartitionError(
            f"frozen S7A SHA-256 mismatch: expected {config['expected_input_sha256']}, got {input_sha}"
        )
    if verify_hashes:
        _assert_git_ls_files_data_empty(root)

    fieldnames, corpus_rows = _read_csv_with_fields(corpus_path)
    snapshot = [dict(row) for row in corpus_rows]
    gmm_path = _resolve(root, config["length_regime"]["s6_bimodality_json"])
    gmm_payload = json.loads(gmm_path.read_text(encoding="utf-8"))
    gmm = load_frozen_s6_gmm(gmm_payload)
    if verify_hashes:
        _expected_gmm_matches(config, gmm)
    derived = _derive_s7b_assignment(
        corpus_rows=corpus_rows,
        config=config,
        gmm=gmm,
        expected_counts=(config.get("expected_input_counts") if enforce_expected_counts else None),
        repeat_for_determinism=repeat_for_determinism,
        run_random_baseline=run_random_baseline,
    )
    observed = derived["observed"]
    n_short = derived["n_short"]
    n_long = derived["n_long"]
    features = derived["features"]
    space = derived["space"]
    quota_candidates = derived["quota_candidates"]
    selected = derived["selected"]
    assignment = derived["assignment"]
    quotas = derived["quotas"]
    score = derived["score"]
    integrity = derived["integrity"]
    family_js = derived["family_js"]
    target_diag = derived["target_diag"]
    tables = derived["tables"]
    random_diag = derived["random_diag"]
    if not input_unmutated(corpus_rows, snapshot):
        raise S7PartitionError("S7B mutated input corpus rows")
    if verify_hashes and sha256_file(corpus_path) != input_sha:
        raise S7PartitionError("S7B mutated the frozen S7A input file")

    output_dir = _resolve(root, config["output_dir"])
    output_paths = {key: output_dir / name for key, name in PREVIEW_OUTPUT_NAMES.items()}
    output_hashes: dict[str, str] = {}
    if write_outputs:
        if verify_hashes:
            _assert_under_ignored_data(root, output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, rows in tables.items():
            path = output_dir / name
            _write_csv(path, rows, TABLE_COLUMNS[name])
            output_hashes[name] = _payload_hash(path)
        report = build_preview_report(
            input_sha256=input_sha,
            observed=observed,
            gmm=gmm,
            n_short=n_short,
            n_long=n_long,
            quota_candidates=[item.as_tuple for item in quota_candidates],
            selected_quotas=quotas,
            score=score,
            family_js=family_js,
            tables=tables,
            target_diag=target_diag,
            integrity=integrity,
            random_diag=random_diag,
            n_accepted_swaps=int(selected["n_accepted_swaps"]),
            n_local_search_passes=int(selected["n_local_search_passes"]),
            local_search_converged=bool(selected["local_search_converged"]),
            greedy_o1=float(selected["greedy_score"].o1),
        )
        write_text_atomic(output_paths["preview_report_md"], report)
        scan_paths = [
            _resolve(root, rel) for rel in config.get("sequence_safety_scan_paths", [])
        ]
        leaked = scan_paths_for_sequence_leak(scan_paths)
        if leaked:
            raise S7PartitionError(
                "sequence leak in tracked S7B files: " + ", ".join(leaked)
            )
        manifest = {
            "ok": True,
            "milestone": config["milestone"],
            "mode": PREVIEW_MODE,
            "ref_frozen": False,
            "eval_frozen": False,
            "authoritative_partitioned_corpus_written": False,
            "ft_train_validation_split": False,
            "s7a_input_mutated": False,
            "input_path": config["authoritative_corpus"],
            "input_sha256": input_sha,
            "observed_input_counts": observed,
            "length_regime": {
                "assignment_method": gmm["assignment_method"],
                "s6_bimodality_json": config["length_regime"]["s6_bimodality_json"],
                "s6_bimodality_sha256": sha256_file(gmm_path),
                "means": list(gmm["means"]),
                "weights": list(gmm["weights"]),
                "n_short_cores": n_short,
                "n_long_cores": n_long,
                "refit_on_post_cap": False,
            },
            "quota_candidates": [list(item.as_tuple) for item in quota_candidates],
            "selected_quotas": {
                "n_FT": quotas.n_FT,
                "n_REF": quotas.n_REF,
                "n_EVAL": quotas.n_EVAL,
            },
            "objective": score.as_dict(),
            "greedy_O1": float(selected["greedy_score"].o1),
            "n_accepted_swaps": int(selected["n_accepted_swaps"]),
            "n_local_search_passes": int(selected["n_local_search_passes"]),
            "local_search_converged": bool(selected["local_search_converged"]),
            "integrity": integrity,
            "target_representation": jsonable(
                {
                    key: value
                    for key, value in target_diag.items()
                    if key != "top_targets"
                }
            ),
            "top_targets": jsonable(target_diag["top_targets"]),
            "family_diagnostic": {
                "role": "secondary diagnostic — not optimisation objective",
                "J_family": family_js,
                "D_family": max(family_js.values()),
            },
            "random_baseline_diagnostic": jsonable(random_diag) if random_diag else None,
            "output_hashes": output_hashes,
            "sequence_safety": {
                "n_paths_scanned": len(scan_paths),
                "n_leaks": 0,
            },
            "determinism_ok": True,
        }
        write_json_atomic(output_paths["preview_manifest_json"], manifest)
        output_hashes["s7b_partition_preview_report.md"] = _payload_hash(
            output_paths["preview_report_md"]
        )
        output_hashes["s7b_partition_preview_manifest.json"] = _payload_hash(
            output_paths["preview_manifest_json"]
        )
        if verify_hashes:
            _assert_git_ls_files_data_empty(root)
            if sha256_file(corpus_path) != input_sha:
                raise S7PartitionError("frozen S7A input hash changed after preview")

    return {
        "ok": True,
        "input_sha256": input_sha,
        "observed": observed,
        "n_short_cores": n_short,
        "n_long_cores": n_long,
        "quota_candidates": [item.as_tuple for item in quota_candidates],
        "selected_quotas": quotas,
        "assignment": assignment,
        "score": score,
        "family_js": family_js,
        "integrity": integrity,
        "target_diag": target_diag,
        "random_diag": random_diag,
        "tables": tables,
        "output_paths": {key: str(path) for key, path in output_paths.items()},
        "output_hashes": output_hashes,
        "n_accepted_swaps": int(selected["n_accepted_swaps"]),
        "n_local_search_passes": int(selected["n_local_search_passes"]),
        "n_evals": int(selected["n_evals"]),
        "n_exact_evals": int(selected["n_exact_evals"]),
        "search_elapsed_seconds": float(selected["search_elapsed_seconds"]),
        "local_search_converged": bool(selected["local_search_converged"]),
        "greedy_o1": float(selected["greedy_score"].o1),
        "quota_search_stats": [
            {
                "quotas": list(item["quotas"].as_tuple),
                "n_passes": int(item["n_local_search_passes"]),
                "n_evals": int(item["n_evals"]),
                "n_exact_evals": int(item["n_exact_evals"]),
                "n_accepted_swaps": int(item["n_accepted_swaps"]),
                "elapsed_seconds": float(item["search_elapsed_seconds"]),
                "converged": bool(item["local_search_converged"]),
                "O1": float(item["score"].o1),
            }
            for item in selected.get("all_quota_results") or []
        ],
        "features": features,
        "space": space,
        "gmm": gmm,
    }


def run_s7b_partition_apply(
    *,
    config_path: Path,
    repo_root: Path | None = None,
    verify_hashes: bool = True,
    enforce_expected_counts: bool = True,
    repeat_for_determinism: bool = True,
    write_outputs: bool = True,
    require_preview_parity: bool = True,
    require_approval_parity: bool = True,
    run_random_baseline: bool = False,
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config = json.loads(_resolve(root, str(config_path)).read_text(encoding="utf-8"))
    enforce_application_config(config)

    preview_dir = _resolve(root, config["preview_output_dir"])
    output_dir = _resolve(root, config["output_dir"])
    if preview_dir.resolve() == output_dir.resolve():
        raise S7PartitionError(
            "S7B application must not write to the reviewed preview directory"
        )

    preview_hashes = _hash_preview_dir(preview_dir)
    approval: dict[str, Any] | None = None
    approval_rel = str(config.get("approval_record") or "")
    if approval_rel:
        approval = json.loads(_resolve(root, approval_rel).read_text(encoding="utf-8"))
        expected_preview_hashes = approval.get("reviewed_preview_hashes") or {}
        if expected_preview_hashes and dict(expected_preview_hashes) != preview_hashes:
            raise S7PartitionError(
                "reviewed preview artefacts have changed since human approval"
            )
        usage = approval.get("usage") or {}
        if usage.get("used_for_scientific_assignment") is True:
            raise S7PartitionError(
                "approval record must not be configured as a scientific-assignment input"
            )
        if approval.get("review_status") != "approved_for_application_and_freeze":
            raise S7PartitionError(
                "S7B approval review_status is not approved_for_application_and_freeze"
            )
    elif require_approval_parity:
        raise S7PartitionError("S7B application requires an approval record")

    frozen_s7a_hashes: dict[str, str] = {}
    if verify_hashes:
        frozen_s7a_hashes = _verify_s7a_artefact_hashes(root, config)
        _assert_git_ls_files_data_empty(root)

    corpus_path = _resolve(root, config["authoritative_corpus"])
    input_sha = sha256_file(corpus_path)
    if verify_hashes and input_sha != config["expected_input_sha256"]:
        raise S7PartitionError(
            f"frozen S7A SHA-256 mismatch: expected {config['expected_input_sha256']}, got {input_sha}"
        )
    if approval and approval.get("frozen_input_sha256") not in {"", None}:
        if approval["frozen_input_sha256"] != input_sha:
            raise S7PartitionError("approval frozen_input_sha256 does not match live S7A input")

    fieldnames, corpus_rows = _read_csv_with_fields(corpus_path)
    snapshot = [dict(row) for row in corpus_rows]
    gmm_path = _resolve(root, config["length_regime"]["s6_bimodality_json"])
    gmm_payload = json.loads(gmm_path.read_text(encoding="utf-8"))
    gmm = load_frozen_s6_gmm(gmm_payload)
    if verify_hashes:
        _expected_gmm_matches(config, gmm)

    # Scientific assignment is derived only from frozen S7A rows and the
    # tested optimiser. Approval/preview labels are not inputs here.
    derived = _derive_s7b_assignment(
        corpus_rows=corpus_rows,
        config=config,
        gmm=gmm,
        expected_counts=(config.get("expected_input_counts") if enforce_expected_counts else None),
        repeat_for_determinism=repeat_for_determinism,
        run_random_baseline=run_random_baseline,
    )
    if not input_unmutated(corpus_rows, snapshot):
        raise S7PartitionError("S7B mutated input corpus rows")
    if verify_hashes and sha256_file(corpus_path) != input_sha:
        raise S7PartitionError("S7B mutated the frozen S7A input file")

    assignment = derived["assignment"]
    quotas = derived["quotas"]
    score = derived["score"]
    features = derived["features"]
    selected = derived["selected"]
    preview_assignment = _preview_assignment_from_csv(
        preview_dir / "cluster_partition_preview.csv"
    )
    preview_manifest = json.loads(
        (preview_dir / "s7b_partition_preview_manifest.json").read_text(encoding="utf-8")
    )
    preview_tables = _preview_tables_from_dir(preview_dir)
    preview_summary = preview_manifest.get("selected_quotas") or {}
    parity = preview_application_parity_mismatches(
        preview_assignment=preview_assignment,
        application_assignment=assignment,
        preview_quotas=preview_summary,
        application_quotas=quotas,
        preview_tables=preview_tables,
        application_tables=derived["tables"],
        preview_objective=preview_manifest.get("objective") or {},
        application_score=score,
        preview_target_diag=preview_manifest.get("target_representation"),
        application_target_diag=derived["target_diag"],
        preview_family_js=(preview_manifest.get("family_diagnostic") or {}).get("J_family"),
        application_family_js=derived["family_js"],
    )
    if require_preview_parity and parity["semantic_mismatches_total"]:
        raise S7PartitionError(
            "preview/application semantic mismatches: " + "; ".join(parity["mismatches"])
        )
    approval_mismatches: list[str] = []
    if approval is not None:
        approval_mismatches = approval_parity_mismatches(
            assignment=assignment,
            features=features,
            quotas=quotas,
            score=score,
            approval=approval,
        )
        if require_approval_parity and approval_mismatches:
            raise S7PartitionError(
                "approval/application semantic mismatches: "
                + "; ".join(approval_mismatches)
            )

    application_tables = build_application_tables(
        features=features,
        space=derived["space"],
        assignment=assignment,
        score=score,
        family_js=derived["family_js"],
    )
    partitioned_rows = populate_partition_on_corpus(corpus_rows, assignment, fieldnames)

    output_paths = {key: output_dir / name for key, name in APPLICATION_OUTPUT_NAMES.items()}
    output_hashes: dict[str, str] = {}
    independent: dict[str, Any] = {}
    distribution_counts: dict[str, Any] = {}
    freeze_payload: dict[str, Any] | None = None
    determinism_ok = True
    ref_identity_hash = ""
    ref_cluster_hash = ""
    eval_identity_hash = ""
    eval_cluster_hash = ""
    if write_outputs:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        if repeat_for_determinism:
            with tempfile.TemporaryDirectory(
                prefix="s7b_apply_a_", dir=str(output_dir.parent)
            ) as first_dir, tempfile.TemporaryDirectory(
                prefix="s7b_apply_b_", dir=str(output_dir.parent)
            ) as second_dir:
                _write_application_payloads(
                    output_dir=Path(first_dir),
                    fieldnames=fieldnames,
                    partitioned_rows=partitioned_rows,
                    tables=application_tables,
                    repo_root=root,
                )
                _write_application_payloads(
                    output_dir=Path(second_dir),
                    fieldnames=fieldnames,
                    partitioned_rows=partitioned_rows,
                    tables=application_tables,
                    repo_root=root,
                )
                for name in DETERMINISTIC_PAYLOAD_NAMES:
                    first_file = Path(first_dir) / name
                    second_file = Path(second_dir) / name
                    if _payload_hash(first_file) != _payload_hash(second_file):
                        raise S7PartitionError(
                            f"S7B application payload {name} is not byte-identical across reruns"
                        )
        written_paths = _write_application_payloads(
            output_dir=output_dir,
            fieldnames=fieldnames,
            partitioned_rows=partitioned_rows,
            tables=application_tables,
            repo_root=root,
        )
        reloaded_partitioned = _read_csv(written_paths["corpus_partitioned_csv"])
        reloaded_ft = _read_csv(written_paths["ft_csv"])
        reloaded_ref = _read_csv(written_paths["ref_csv"])
        reloaded_eval = _read_csv(written_paths["eval_csv"])
        reloaded_assignment_rows = _read_csv(
            written_paths["cluster_partition_assignment_csv"]
        )
        independent = independent_partition_invariants(
            input_rows=corpus_rows,
            partitioned_rows=reloaded_partitioned,
            ft_rows=reloaded_ft,
            ref_rows=reloaded_ref,
            eval_rows=reloaded_eval,
            assignment_rows=reloaded_assignment_rows,
            fieldnames=fieldnames,
        )
        if independent["partition_blank"] or independent["invalid_partition_labels"]:
            raise S7PartitionError("authoritative partition labels are blank or invalid")
        if independent["E5"] or independent["non_protein"]:
            raise S7PartitionError("authoritative corpus introduced E5 or non-protein records")
        if independent["field_changes_excluding_partition"]:
            raise S7PartitionError("S7B changed frozen scientific fields other than partition")
        distribution_counts = independent_distribution_counts(
            reloaded_partitioned, derived["core_regimes"]
        )
        reloaded_assignment = assignment_from_partitioned_rows(reloaded_partitioned)
        if reloaded_assignment != assignment:
            raise S7PartitionError("reloaded corpus_partitioned assignment drifted")
        blanked = [{**row, "partition": ""} for row in reloaded_partitioned]
        independent_features, independent_space = build_cluster_features(
            blanked, derived["core_regimes"]
        )
        independent_score = score_assignment(
            reloaded_assignment, independent_features, independent_space
        )
        if independent_score.as_dict() != score.as_dict():
            raise S7PartitionError(
                "independently recomputed objective disagrees with derivation"
            )
        ref_identity_hash = semantic_identity_set_hash(reloaded_ref)
        ref_cluster_hash = semantic_cluster_set_hash(reloaded_ref)
        eval_identity_hash = semantic_identity_set_hash(reloaded_eval)
        eval_cluster_hash = semantic_cluster_set_hash(reloaded_eval)
        payload_hashes = {
            name: _payload_hash(output_dir / name) for name in DETERMINISTIC_PAYLOAD_NAMES
        }
        report = build_application_report(
            input_sha256=input_sha,
            observed=derived["observed"],
            gmm=gmm,
            n_short=derived["n_short"],
            n_long=derived["n_long"],
            selected_quotas=quotas,
            score=score,
            family_js=derived["family_js"],
            tables=application_tables,
            target_diag=derived["target_diag"],
            integrity=derived["integrity"],
            independent=independent,
            preview_hashes=preview_hashes,
            output_hashes=payload_hashes,
            parity=parity,
            n_accepted_swaps=int(selected["n_accepted_swaps"]),
            n_local_search_passes=int(selected["n_local_search_passes"]),
            local_search_converged=bool(selected["local_search_converged"]),
            greedy_o1=float(selected["greedy_score"].o1),
            freeze_date=str(config.get("freeze_date") or FREEZE_DATE),
            ref_identity_set_hash=ref_identity_hash,
            eval_identity_set_hash=eval_identity_hash,
            determinism_ok=determinism_ok,
        )
        write_text_atomic(written_paths["report_md"], report)
        freeze_rel = str(config.get("freeze_record") or "")
        freeze_path = _resolve(root, freeze_rel) if freeze_rel else None
        freeze_payload = build_freeze_record(
            input_sha256=input_sha,
            preview_assignment_sha256=preview_hashes["cluster_partition_preview.csv"],
            authoritative_assignment_sha256=payload_hashes["cluster_partition_assignment.csv"],
            quotas=quotas,
            independent=independent,
            output_hashes=payload_hashes,
            ref_identity_set_hash=ref_identity_hash,
            ref_cluster_set_hash=ref_cluster_hash,
            eval_identity_set_hash=eval_identity_hash,
            eval_cluster_set_hash=eval_cluster_hash,
            score=score,
            semantic_mismatches_total=int(parity["semantic_mismatches_total"]),
            freeze_date=str(config.get("freeze_date") or FREEZE_DATE),
            freeze_reason=str(config.get("freeze_reason") or FREEZE_REASON),
        )
        if freeze_path is not None:
            write_json_atomic(freeze_path, freeze_payload)
            assert_no_sequence_leak(
                freeze_path.read_text(encoding="utf-8"),
                label=freeze_path.name,
            )
        scan_paths = [
            _resolve(root, rel) for rel in config.get("sequence_safety_scan_paths", [])
        ]
        leaked = scan_paths_for_sequence_leak(scan_paths)
        if leaked:
            raise S7PartitionError(
                "sequence leak in tracked S7B files: " + ", ".join(leaked)
            )
        manifest = {
            "ok": True,
            "milestone": config["milestone"],
            "mode": APPLY_MODE,
            "ref_frozen": True,
            "eval_frozen": True,
            "authoritative_partitioned_corpus_written": True,
            "ft_assigned": True,
            "ft_train_validation_split": False,
            "s7c_started": False,
            "s7a_input_mutated": False,
            "approval_record": approval_rel,
            "approval_used_for_scientific_assignment": False,
            "freeze_record": freeze_rel,
            "freeze_date": str(config.get("freeze_date") or FREEZE_DATE),
            "freeze_reason": str(config.get("freeze_reason") or FREEZE_REASON),
            "input_path": config["authoritative_corpus"],
            "input_sha256": input_sha,
            "frozen_s7a_artefact_hashes_ok": bool(frozen_s7a_hashes) or not verify_hashes,
            "preview_dir": config["preview_output_dir"],
            "preview_hashes": preview_hashes,
            "preview_application_semantic_mismatches": parity["mismatches"],
            "n_preview_application_semantic_mismatches": parity["semantic_mismatches_total"],
            "cluster_assignments_compared": parity["cluster_assignments_compared"],
            "cluster_assignment_mismatches": parity["cluster_assignment_mismatches"],
            "aggregate_statistical_mismatches": parity["aggregate_statistical_mismatches"],
            "objective_mismatches": parity["objective_mismatches"],
            "approval_parity_mismatches": approval_mismatches,
            "observed_input_counts": derived["observed"],
            "length_regime": {
                "assignment_method": gmm["assignment_method"],
                "s6_bimodality_json": config["length_regime"]["s6_bimodality_json"],
                "s6_bimodality_sha256": sha256_file(gmm_path),
                "means": list(gmm["means"]),
                "weights": list(gmm["weights"]),
                "n_short_cores": derived["n_short"],
                "n_long_cores": derived["n_long"],
                "refit_on_post_cap": False,
            },
            "selected_quotas": {
                "n_FT": quotas.n_FT,
                "n_REF": quotas.n_REF,
                "n_EVAL": quotas.n_EVAL,
            },
            "objective": score.as_dict(),
            "greedy_O1": float(selected["greedy_score"].o1),
            "n_accepted_swaps": int(selected["n_accepted_swaps"]),
            "n_local_search_passes": int(selected["n_local_search_passes"]),
            "local_search_converged": bool(selected["local_search_converged"]),
            "integrity": derived["integrity"],
            "independent": jsonable(independent),
            "independent_distributions": jsonable(distribution_counts),
            "target_representation": jsonable(
                {
                    key: value
                    for key, value in derived["target_diag"].items()
                    if key != "top_targets"
                }
            ),
            "family_diagnostic": {
                "role": "secondary diagnostic — not optimisation objective",
                "J_family": derived["family_js"],
                "D_family": max(derived["family_js"].values()),
            },
            "ref_freeze": {
                "frozen": True,
                "file_sha256": payload_hashes["ref.csv"],
                "semantic_identity_set_hash": ref_identity_hash,
                "semantic_cluster_set_hash": ref_cluster_hash,
            },
            "eval_freeze": {
                "frozen": True,
                "file_sha256": payload_hashes["eval.csv"],
                "semantic_identity_set_hash": eval_identity_hash,
                "semantic_cluster_set_hash": eval_cluster_hash,
            },
            "output_hashes": payload_hashes,
            "sequence_safety": {
                "n_paths_scanned": len(scan_paths),
                "n_leaks": 0,
            },
            "determinism_ok": determinism_ok,
            "independence_rule": freeze_payload["independence_rule"] if freeze_payload else {},
        }
        write_json_atomic(written_paths["manifest_json"], manifest)
        output_hashes = dict(payload_hashes)
        output_hashes["s7b_partition_report.md"] = _payload_hash(written_paths["report_md"])
        output_hashes["s7b_partition_manifest.json"] = _payload_hash(
            written_paths["manifest_json"]
        )
        post_preview_hashes = _hash_preview_dir(preview_dir)
        if post_preview_hashes != preview_hashes:
            raise S7PartitionError(
                "S7B application overwrote the reviewed preview artefacts"
            )
        if verify_hashes:
            _assert_git_ls_files_data_empty(root)
            if sha256_file(corpus_path) != input_sha:
                raise S7PartitionError("frozen S7A input hash changed after application")
        output_paths = written_paths

    return {
        "ok": True,
        "input_sha256": input_sha,
        "observed": derived["observed"],
        "assignment": assignment,
        "selected_quotas": quotas,
        "score": score,
        "family_js": derived["family_js"],
        "integrity": derived["integrity"],
        "target_diag": derived["target_diag"],
        "output_paths": {key: str(path) for key, path in output_paths.items()},
        "output_hashes": output_hashes,
        "preview_hashes": preview_hashes,
        "parity": parity,
        "approval_mismatches": approval_mismatches,
        "independent": independent,
        "independent_distributions": distribution_counts,
        "determinism_ok": determinism_ok,
        "approval_used_for_scientific_assignment": False,
        "ref_frozen": True,
        "eval_frozen": True,
        "ref_identity_set_hash": ref_identity_hash,
        "ref_cluster_set_hash": ref_cluster_hash,
        "eval_identity_set_hash": eval_identity_hash,
        "eval_cluster_set_hash": eval_cluster_hash,
        "freeze_record": freeze_payload,
        "n_accepted_swaps": int(selected["n_accepted_swaps"]),
        "n_local_search_passes": int(selected["n_local_search_passes"]),
        "local_search_converged": bool(selected["local_search_converged"]),
        "greedy_o1": float(selected["greedy_score"].o1),
        "features": features,
        "space": derived["space"],
        "gmm": gmm,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="S7B FT/REF/EVAL partition preview / application"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--skip-expected-counts",
        action="store_true",
        help="Do not enforce live S7A regression counts (synthetic use only)",
    )
    parser.add_argument(
        "--skip-hash-gate",
        action="store_true",
        help="Do not verify frozen S7A SHA-256 (synthetic use only)",
    )
    parser.add_argument(
        "--skip-determinism-repeat",
        action="store_true",
        help="Optimise once (not authorised for the live scientific preview)",
    )
    parser.add_argument(
        "--skip-random-baseline",
        action="store_true",
        help="Skip the diagnostic random whole-cluster baseline",
    )
    args = parser.parse_args()
    root = find_repo_root()
    config = json.loads(_resolve(root, str(args.config)).read_text(encoding="utf-8"))
    mode = str(config.get("mode") or "").strip()
    try:
        if mode == PREVIEW_MODE:
            result = run_s7b_partition_preview(
                config_path=args.config,
                enforce_expected_counts=not args.skip_expected_counts,
                verify_hashes=not args.skip_hash_gate,
                repeat_for_determinism=not args.skip_determinism_repeat,
                run_random_baseline=not args.skip_random_baseline,
            )
            quotas = result["selected_quotas"]
            score = result["score"]
            print(
                json.dumps(
                    {
                        "ok": True,
                        "mode": PREVIEW_MODE,
                        "input_sha256": result["input_sha256"],
                        "n_scientific_identities": result["observed"]["n_scientific_identities"],
                        "n_distinct_sequence_core": result["observed"]["n_distinct_sequence_core"],
                        "n_final_clusters": result["observed"]["n_final_clusters"],
                        "n_short_cores": result["n_short_cores"],
                        "n_long_cores": result["n_long_cores"],
                        "quota_candidates": [list(item) for item in result["quota_candidates"]],
                        "selected_quotas": {
                            "n_FT": quotas.n_FT,
                            "n_REF": quotas.n_REF,
                            "n_EVAL": quotas.n_EVAL,
                        },
                        "O1": score.o1,
                        "O3": score.o3,
                        "n_accepted_swaps": result["n_accepted_swaps"],
                        "n_local_search_passes": result["n_local_search_passes"],
                        "n_evals": result["n_evals"],
                        "n_exact_evals": result["n_exact_evals"],
                        "search_elapsed_seconds": result["search_elapsed_seconds"],
                        "local_search_converged": result["local_search_converged"],
                        "hit_max_passes": not result["local_search_converged"],
                        "quota_search_stats": result["quota_search_stats"],
                        "ref_frozen": False,
                        "eval_frozen": False,
                        "authoritative_partitioned_corpus_written": False,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if mode == APPLY_MODE:
            result = run_s7b_partition_apply(
                config_path=args.config,
                enforce_expected_counts=not args.skip_expected_counts,
                verify_hashes=not args.skip_hash_gate,
                repeat_for_determinism=not args.skip_determinism_repeat,
            )
            quotas = result["selected_quotas"]
            score = result["score"]
            parity = result["parity"]
            print(
                json.dumps(
                    {
                        "ok": True,
                        "mode": APPLY_MODE,
                        "input_sha256": result["input_sha256"],
                        "n_scientific_identities": result["observed"]["n_scientific_identities"],
                        "n_distinct_sequence_core": result["observed"]["n_distinct_sequence_core"],
                        "n_final_clusters": result["observed"]["n_final_clusters"],
                        "selected_quotas": {
                            "n_FT": quotas.n_FT,
                            "n_REF": quotas.n_REF,
                            "n_EVAL": quotas.n_EVAL,
                        },
                        "O1": score.o1,
                        "O3": score.o3,
                        "n_preview_application_semantic_mismatches": parity[
                            "semantic_mismatches_total"
                        ],
                        "approval_used_for_scientific_assignment": False,
                        "ref_frozen": True,
                        "eval_frozen": True,
                        "authoritative_partitioned_corpus_written": True,
                        "ft_train_validation_split": False,
                        "s7c_started": False,
                        "determinism_ok": result["determinism_ok"],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        raise S7PartitionError(f"S7B mode must be preview or apply, got {mode!r}")
    except S7PartitionError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""GLOBAL S7C — FT-only train/validation split preview and application.

Preview mode writes sequence-free artefacts under ignored
``data/interim/s7c_ft_split_preview_v2/``. Apply mode rederives the same
v2 assignment from frozen ``ft.csv``, writes authoritative TRAIN and
VALIDATION corpus files under ignored ``data/interim/s7c_ft_split/``,
and freezes both subsets. Does not overwrite preserved previews, mutate
``ft.csv``, touch REF/EVAL, write corpus_final, or start fine-tuning.
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
from adapters.s7_ft_train_validation import (  # noqa: E402
    APPLICATION_TABLE_NAMES,
    APPLY_MODE,
    FROZEN_FT_SHA256,
    FREEZE_DATE,
    FREEZE_REASON,
    PREVIEW_MODE,
    S7CSplitError,
    S7C_PLACEMENT_LABELS,
    S7C_REPORT_LABELS,
    S7C_OBJECTIVE_PROFILE,
    TABLE_COLUMNS,
    TRAIN_LABEL,
    VALIDATION_LABEL,
    assignment_from_ft_split_rows,
    assert_application_dir_not_preview,
    assert_not_forbidden_s7c_apply_output_path,
    assert_not_forbidden_s7c_output_path,
    assert_preview_dir_not_protected,
    assert_ref_eval_matches_expected,
    assert_ref_eval_unchanged,
    assign_length_regimes,
    blank_partition_copy,
    build_cluster_features,
    build_s7c_application_report,
    build_s7c_application_tables,
    build_s7c_freeze_record,
    build_s7c_preview_report,
    build_s7c_preview_tables,
    derive_integer_quota_pairs,
    enforce_s7c_application_config,
    enforce_s7c_preview_config,
    evaluate_random_baselines,
    family_jsd_by_partition,
    frozen_ref_eval_expected,
    ft_split_subset_rows,
    independent_s7c_distribution_counts,
    independent_s7c_invariants,
    input_unmutated,
    jsonable_s7c,
    populate_ft_split_on_ft_rows,
    s7c_approval_parity_mismatches,
    s7c_integrity_gates,
    s7c_preview_application_parity_mismatches,
    s7c_target_diagnostics,
    score_s7c_assignment,
    select_s7c_assignment,
    snapshot_ref_eval_freeze,
    verify_ft_split_input,
)
from adapters.s7_partition import (  # noqa: E402
    assert_no_sequence_leak,
    load_frozen_s6_gmm,
    semantic_cluster_set_hash,
    semantic_identity_set_hash,
    states_from_assignment,
)
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402

DEFAULT_CONFIG = Path("config/global_s7c_ft_train_validation.json")
PREVIEW_OUTPUT_NAMES: dict[str, str] = {
    "cluster_ft_split_preview_csv": "cluster_ft_split_preview.csv",
    "train_identity_summary_csv": "train_identity_summary.csv",
    "validation_identity_summary_csv": "validation_identity_summary.csv",
    "train_core_summary_csv": "train_core_summary.csv",
    "validation_core_summary_csv": "validation_core_summary.csv",
    "target_distribution_csv": "target_distribution.csv",
    "evidence_distribution_csv": "evidence_distribution.csv",
    "length_regime_distribution_csv": "length_regime_distribution.csv",
    "source_distribution_csv": "source_distribution.csv",
    "target_family_diagnostic_csv": "target_family_diagnostic.csv",
    "divergence_metrics_csv": "divergence_metrics.csv",
    "absolute_deviation_metrics_csv": "absolute_deviation_metrics.csv",
    "preview_report_md": "s7c_ft_split_preview_report.md",
    "preview_manifest_json": "s7c_ft_split_preview_manifest.json",
}
PREVIEW_ARTEFACT_NAMES: tuple[str, ...] = tuple(PREVIEW_OUTPUT_NAMES.values())
APPLICATION_OUTPUT_NAMES: dict[str, str] = {
    "ft_split_assignment_csv": "ft_split_assignment.csv",
    "ft_train_csv": "ft_train.csv",
    "ft_validation_csv": "ft_validation.csv",
    "train_identity_summary_csv": "train_identity_summary.csv",
    "validation_identity_summary_csv": "validation_identity_summary.csv",
    "train_core_summary_csv": "train_core_summary.csv",
    "validation_core_summary_csv": "validation_core_summary.csv",
    "target_distribution_csv": "target_distribution.csv",
    "evidence_distribution_csv": "evidence_distribution.csv",
    "length_regime_distribution_csv": "length_regime_distribution.csv",
    "source_distribution_csv": "source_distribution.csv",
    "target_family_diagnostic_csv": "target_family_diagnostic.csv",
    "divergence_metrics_csv": "divergence_metrics.csv",
    "absolute_deviation_metrics_csv": "absolute_deviation_metrics.csv",
    "report_md": "s7c_ft_split_report.md",
    "manifest_json": "s7c_ft_split_manifest.json",
}
DETERMINISTIC_PAYLOAD_NAMES: tuple[str, ...] = (
    "ft_split_assignment.csv",
    "ft_train.csv",
    "ft_validation.csv",
    "train_identity_summary.csv",
    "validation_identity_summary.csv",
    "train_core_summary.csv",
    "validation_core_summary.csv",
    "target_distribution.csv",
    "evidence_distribution.csv",
    "length_regime_distribution.csv",
    "source_distribution.csv",
    "target_family_diagnostic.csv",
    "divergence_metrics.csv",
    "absolute_deviation_metrics.csv",
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
        raise S7CSplitError("git ls-files data is not empty")


def _assert_under_ignored_data(root: Path, path: Path) -> None:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise S7CSplitError("S7C preview path is outside the repository") from exc
    if relative.parts[0] != "data":
        raise S7CSplitError("S7C preview artefacts must remain under ignored data/")
    if "processed" in relative.parts:
        raise S7CSplitError("S7C preview must not write under data/processed/")


def _write_csv(path: Path, rows: Sequence[Mapping[str, str]], columns: Sequence[str]) -> None:
    assert_not_forbidden_s7c_output_path(path)
    for row in rows:
        for key, value in row.items():
            if key in {"sequence_raw", "sequence_full", "sequence_core"}:
                raise S7CSplitError(f"{path.name} must not contain sequence columns")
            assert_no_sequence_leak(str(value), label=f"{path.name}:{key}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _expected_gmm_matches(config: Mapping[str, Any], gmm: Mapping[str, Any]) -> None:
    expected = config.get("expected_s6_gmm2")
    if not expected:
        return
    for field in ("means", "variances", "weights"):
        got = [float(v) for v in gmm[field]]
        wanted = [float(v) for v in expected[field]]
        if got != wanted:
            raise S7CSplitError(f"frozen S6 GMM {field} mismatch")


def _hash_dir_files(directory: Path) -> dict[str, str]:
    if not directory.is_dir():
        raise S7CSplitError(f"directory is missing: {directory}")
    return {
        path.name: _payload_hash(path)
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def _hash_preview_dir(preview_dir: Path) -> dict[str, str]:
    hashes = _hash_dir_files(preview_dir)
    missing = [name for name in PREVIEW_ARTEFACT_NAMES if name not in hashes]
    if missing:
        raise S7CSplitError(
            "reviewed preview artefact missing: " + ", ".join(missing)
        )
    return hashes


def _preview_assignment_from_csv(path: Path) -> dict[str, str]:
    rows = _read_csv(path)
    assignment: dict[str, str] = {}
    for row in rows:
        cluster_id = str(row.get("cluster_id") or "").strip()
        label = str(row.get("proposed_ft_split") or row.get("ft_split") or "").strip()
        if not cluster_id or not label:
            raise S7CSplitError("preview assignment row is missing cluster_id or ft_split")
        if cluster_id in assignment:
            raise S7CSplitError("preview assignment repeats a cluster_id")
        assignment[cluster_id] = label
    return assignment


def _preview_tables_from_dir(preview_dir: Path) -> dict[str, list[dict[str, str]]]:
    tables: dict[str, list[dict[str, str]]] = {}
    for name in TABLE_COLUMNS:
        if name in {"ft_split_assignment.csv"}:
            continue
        path = preview_dir / name
        if path.is_file():
            tables[name] = _read_csv(path)
    return tables


def _write_apply_table_csv(
    path: Path, rows: Sequence[Mapping[str, str]], columns: Sequence[str]
) -> None:
    assert_not_forbidden_s7c_apply_output_path(path)
    for row in rows:
        for key, value in row.items():
            if key in {"sequence_raw", "sequence_full", "sequence_core"}:
                raise S7CSplitError(f"{path.name} must not contain sequence columns")
            assert_no_sequence_leak(str(value), label=f"{path.name}:{key}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _derive_s7c_assignment(
    *,
    ft_rows: Sequence[Mapping[str, str]],
    config: Mapping[str, Any],
    gmm: Mapping[str, Any],
    expected_counts: Mapping[str, int] | None,
    repeat_for_determinism: bool,
    run_random_baseline: bool,
    ref_cluster_ids: Sequence[str] | None = None,
    eval_cluster_ids: Sequence[str] | None = None,
    ref_identity_ids: Sequence[str] | None = None,
    eval_identity_ids: Sequence[str] | None = None,
    enforce_expected_counts: bool = True,
) -> dict[str, Any]:
    snapshot = [dict(row) for row in ft_rows]
    observed = verify_ft_split_input(
        ft_rows,
        expected_counts,
        ref_cluster_ids=ref_cluster_ids,
        eval_cluster_ids=eval_cluster_ids,
        ref_identity_ids=ref_identity_ids,
        eval_identity_ids=eval_identity_ids,
    )
    core_regimes = assign_length_regimes(ft_rows, gmm)
    n_short = sum(1 for label in core_regimes.values() if label == "short")
    n_long = sum(1 for label in core_regimes.values() if label == "long")
    expected_length = config.get("expected_length_regime_cores") or {}
    if enforce_expected_counts and expected_length:
        if n_short != int(expected_length.get("short", n_short)):
            raise S7CSplitError(
                f"FT short cores: expected {expected_length.get('short')}, got {n_short}"
            )
        if n_long != int(expected_length.get("long", n_long)):
            raise S7CSplitError(
                f"FT long cores: expected {expected_length.get('long')}, got {n_long}"
            )
    if n_short + n_long != observed["n_distinct_sequence_core"]:
        raise S7CSplitError("length-regime assignment does not cover every FT core")
    expected_evidence = config.get("expected_evidence") or {}
    if enforce_expected_counts and expected_evidence:
        observed_evidence = Counter(row.get("evidence_level", "").strip() for row in ft_rows)
        for level, wanted in expected_evidence.items():
            if observed_evidence.get(level, 0) != int(wanted):
                raise S7CSplitError(
                    f"FT {level}: expected {wanted}, got {observed_evidence.get(level, 0)}"
                )
    expected_sources = config.get("expected_source_identities") or {}
    if enforce_expected_counts and expected_sources:
        observed_sources = Counter(row.get("source_db", "").strip() for row in ft_rows)
        for source, wanted in expected_sources.items():
            if observed_sources.get(source, 0) != int(wanted):
                raise S7CSplitError(
                    f"FT source {source}: expected {wanted}, got {observed_sources.get(source, 0)}"
                )
    working = blank_partition_copy(ft_rows)
    features, space = build_cluster_features(working, core_regimes)
    if space.n_clusters != observed["n_final_clusters"]:
        raise S7CSplitError("cluster feature count drifted from FT input")
    fractions = config.get("split_fractions") or {"TRAIN": 0.90, "VALIDATION": 0.10}
    quota_candidates = derive_integer_quota_pairs(space.n_clusters, fractions)
    max_passes = int(config.get("local_search_max_passes") or 10_000)
    # Scientific assignment is derived only from frozen FT rows and the
    # tested v2 optimiser. Approval/preview labels are not inputs here.
    selected = select_s7c_assignment(
        features, space, quota_candidates, max_passes=max_passes
    )
    if repeat_for_determinism:
        reversed_features, reversed_space = build_cluster_features(
            list(reversed(working)), core_regimes
        )
        again = select_s7c_assignment(
            reversed_features,
            reversed_space,
            quota_candidates,
            max_passes=max_passes,
        )
        if again["assignment"] != selected["assignment"]:
            raise S7CSplitError("S7C assignment depends on input row order")
        if again["comparison_tuple"] != selected["comparison_tuple"]:
            raise S7CSplitError("S7C comparison tuple depends on input row order")
    assignment = selected["assignment"]
    quotas = selected["quotas"]
    score = selected["score"]
    integrity = s7c_integrity_gates(
        ft_rows,
        assignment,
        features,
        quotas,
        ref_cluster_ids=ref_cluster_ids,
        eval_cluster_ids=eval_cluster_ids,
        ref_identity_ids=ref_identity_ids,
        eval_identity_ids=eval_identity_ids,
    )
    if integrity["E5"] != 0 or integrity["non_protein"] != 0:
        raise S7CSplitError("S7C introduced E5 or non-protein records")
    if integrity["ref_clusters_in_split"] or integrity["eval_clusters_in_split"]:
        raise S7CSplitError("REF/EVAL clusters leaked into the FT split")
    if integrity["ref_identities_in_split"] or integrity["eval_identities_in_split"]:
        raise S7CSplitError("REF/EVAL identities leaked into the FT split")
    if integrity["top_level_partition_altered"]:
        raise S7CSplitError("S7C altered the top-level partition field")
    family_js = family_jsd_by_partition(
        states_from_assignment(
            assignment, features, space, partition_labels=S7C_REPORT_LABELS
        ),
        space,
        partition_labels=S7C_REPORT_LABELS,
    )
    target_diag = s7c_target_diagnostics(ft_rows, assignment)
    tables = build_s7c_preview_tables(
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
            random_diag = evaluate_random_baselines(
                features,
                space,
                quotas,
                seeds,
                partition_labels=S7C_REPORT_LABELS,
                objective_profile=S7C_OBJECTIVE_PROFILE,
            )
    if not input_unmutated(ft_rows, snapshot):
        raise S7CSplitError("S7C mutated FT input rows")
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
    annotated_rows: Sequence[Mapping[str, str]],
    output_fields: Sequence[str],
    tables: Mapping[str, Sequence[Mapping[str, str]]],
    repo_root: Path | None = None,
) -> dict[str, Path]:
    output_paths = {key: output_dir / name for key, name in APPLICATION_OUTPUT_NAMES.items()}
    for path in output_paths.values():
        assert_not_forbidden_s7c_apply_output_path(path)
    if repo_root is not None:
        _assert_under_ignored_data(repo_root, output_dir)
        assert_application_dir_not_preview(output_dir, repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_corpus_csv_atomic(
        output_paths["ft_train_csv"],
        ft_split_subset_rows(annotated_rows, TRAIN_LABEL),
        columns=list(output_fields),
    )
    write_corpus_csv_atomic(
        output_paths["ft_validation_csv"],
        ft_split_subset_rows(annotated_rows, VALIDATION_LABEL),
        columns=list(output_fields),
    )
    for name in APPLICATION_TABLE_NAMES:
        rows = tables[name]
        _write_apply_table_csv(output_dir / name, rows, TABLE_COLUMNS[name])
    return output_paths


def _load_ref_eval_snapshot(
    *,
    ref_path: Path,
    eval_path: Path,
    expected: Mapping[str, Any],
) -> Any:
    ref_rows = _read_csv(ref_path)
    eval_rows = _read_csv(eval_path)
    snapshot = snapshot_ref_eval_freeze(
        ref_rows,
        eval_rows,
        ref_sha256=sha256_file(ref_path),
        eval_sha256=sha256_file(eval_path),
    )
    assert_ref_eval_matches_expected(snapshot, expected)
    return snapshot


def run_s7c_ft_split_preview(
    *,
    config_path: Path,
    repo_root: Path | None = None,
    verify_hashes: bool = True,
    enforce_expected_counts: bool = True,
    repeat_for_determinism: bool = True,
    write_outputs: bool = True,
    run_random_baseline: bool = True,
    verify_ref_eval_freeze: bool = True,
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config = json.loads(_resolve(root, str(config_path)).read_text(encoding="utf-8"))
    enforce_s7c_preview_config(config)

    ft_path = _resolve(root, config["ft_csv"])
    ref_path = _resolve(root, config["ref_csv"])
    eval_path = _resolve(root, config["eval_csv"])
    input_sha = sha256_file(ft_path)
    expected_ft_sha = config.get("expected_ft_sha256") or FROZEN_FT_SHA256
    if verify_hashes and input_sha != expected_ft_sha:
        raise S7CSplitError(
            f"frozen FT SHA-256 mismatch: expected {expected_ft_sha}, got {input_sha}"
        )
    if verify_hashes:
        _assert_git_ls_files_data_empty(root)

    freeze_expected = frozen_ref_eval_expected(config)
    before_snapshot = None
    if verify_ref_eval_freeze:
        before_snapshot = _load_ref_eval_snapshot(
            ref_path=ref_path, eval_path=eval_path, expected=freeze_expected
        )

    fieldnames, ft_rows = _read_csv_with_fields(ft_path)
    snapshot_rows = [dict(row) for row in ft_rows]
    ref_rows = _read_csv(ref_path) if verify_ref_eval_freeze else []
    eval_rows = _read_csv(eval_path) if verify_ref_eval_freeze else []
    ref_cluster_ids = (
        before_snapshot.ref_cluster_ids if before_snapshot is not None else set()
    )
    eval_cluster_ids = (
        before_snapshot.eval_cluster_ids if before_snapshot is not None else set()
    )
    ref_identity_ids = (
        before_snapshot.ref_identity_ids if before_snapshot is not None else set()
    )
    eval_identity_ids = (
        before_snapshot.eval_identity_ids if before_snapshot is not None else set()
    )

    if "partition" not in fieldnames:
        raise S7CSplitError("FT input is missing the partition column")

    gmm_path = _resolve(root, config["length_regime"]["s6_bimodality_json"])
    gmm_payload = json.loads(gmm_path.read_text(encoding="utf-8"))
    gmm = load_frozen_s6_gmm(gmm_payload)
    if verify_hashes:
        _expected_gmm_matches(config, gmm)

    derived = _derive_s7c_assignment(
        ft_rows=ft_rows,
        config=config,
        gmm=gmm,
        expected_counts=(config.get("expected_input_counts") if enforce_expected_counts else None),
        repeat_for_determinism=repeat_for_determinism,
        run_random_baseline=run_random_baseline,
        ref_cluster_ids=ref_cluster_ids,
        eval_cluster_ids=eval_cluster_ids,
        ref_identity_ids=ref_identity_ids,
        eval_identity_ids=eval_identity_ids,
        enforce_expected_counts=enforce_expected_counts,
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
    if not input_unmutated(ft_rows, snapshot_rows):
        raise S7CSplitError("S7C mutated FT input rows")
    if verify_hashes and sha256_file(ft_path) != input_sha:
        raise S7CSplitError("S7C mutated the frozen FT input file")

    output_dir = _resolve(root, config["preview_output_dir"])
    assert_preview_dir_not_protected(output_dir, root)
    output_paths = {key: output_dir / name for key, name in PREVIEW_OUTPUT_NAMES.items()}
    output_hashes: dict[str, str] = {}
    after_snapshot = before_snapshot
    if write_outputs:
        if verify_hashes:
            _assert_under_ignored_data(root, output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, rows in tables.items():
            path = output_dir / name
            _write_csv(path, rows, TABLE_COLUMNS[name])
            output_hashes[name] = _payload_hash(path)
        ref_eval_before_payload = jsonable_s7c(before_snapshot) if before_snapshot else {}
        if verify_ref_eval_freeze:
            after_snapshot = _load_ref_eval_snapshot(
                ref_path=ref_path, eval_path=eval_path, expected=freeze_expected
            )
            assert_ref_eval_unchanged(before_snapshot, after_snapshot)
        ref_eval_after_payload = jsonable_s7c(after_snapshot) if after_snapshot else {}
        report = build_s7c_preview_report(
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
            greedy_o1=float(selected["greedy_score"].r1),
            ref_eval_before=ref_eval_before_payload,
            ref_eval_after=ref_eval_after_payload,
        )
        write_text_atomic(output_paths["preview_report_md"], report)
        scan_paths = [
            _resolve(root, rel) for rel in config.get("sequence_safety_scan_paths", [])
        ]
        leaked = scan_paths_for_sequence_leak(scan_paths)
        if leaked:
            raise S7CSplitError(
                "sequence leak in tracked S7C files: " + ", ".join(leaked)
            )
        manifest = {
            "ok": True,
            "milestone": config["milestone"],
            "mode": PREVIEW_MODE,
            "ft_train_frozen": False,
            "ft_validation_frozen": False,
            "authoritative_train_validation_written": False,
            "ref_frozen": True,
            "eval_frozen": True,
            "ref_changed": False,
            "eval_changed": False,
            "model_fine_tuning_started": False,
            "ft_input_mutated": False,
            "top_level_partition_altered": False,
            "input_path": config["ft_csv"],
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
                "n_TRAIN": quotas.n_TRAIN,
                "n_VALIDATION": quotas.n_VALIDATION,
            },
            "objective": score.as_dict(),
            "objective_profile": S7C_OBJECTIVE_PROFILE,
            "greedy_R1": float(selected["greedy_score"].r1),
            "greedy_O1_jsd_diagnostic": float(selected["greedy_score"].o1),
            "n_accepted_swaps": int(selected["n_accepted_swaps"]),
            "n_local_search_passes": int(selected["n_local_search_passes"]),
            "local_search_converged": bool(selected["local_search_converged"]),
            "integrity": jsonable_s7c(integrity),
            "target_representation": jsonable_s7c(
                {
                    key: value
                    for key, value in target_diag.items()
                    if key != "top_targets"
                }
            ),
            "top_targets": jsonable_s7c(target_diag["top_targets"]),
            "family_diagnostic": {
                "role": "secondary diagnostic — not optimisation objective",
                "J_family": family_js,
                "D_family": max(family_js.values()),
            },
            "random_baseline_diagnostic": jsonable_s7c(random_diag) if random_diag else None,
            "ref_eval_before": ref_eval_before_payload,
            "ref_eval_after": ref_eval_after_payload,
            "output_hashes": output_hashes,
            "sequence_safety": {
                "n_paths_scanned": len(scan_paths),
                "n_leaks": 0,
            },
            "determinism_ok": True,
            "placement_labels": list(S7C_PLACEMENT_LABELS),
            "report_labels": list(S7C_REPORT_LABELS),
        }
        write_json_atomic(output_paths["preview_manifest_json"], manifest)
        output_hashes["s7c_ft_split_preview_report.md"] = _payload_hash(
            output_paths["preview_report_md"]
        )
        output_hashes["s7c_ft_split_preview_manifest.json"] = _payload_hash(
            output_paths["preview_manifest_json"]
        )
        if verify_hashes:
            _assert_git_ls_files_data_empty(root)
            if sha256_file(ft_path) != input_sha:
                raise S7CSplitError("frozen FT input hash changed after preview")
        if verify_ref_eval_freeze:
            final_snapshot = _load_ref_eval_snapshot(
                ref_path=ref_path, eval_path=eval_path, expected=freeze_expected
            )
            assert_ref_eval_unchanged(before_snapshot, final_snapshot)
            after_snapshot = final_snapshot

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
        "local_search_converged": bool(selected["local_search_converged"]),
        "greedy_o1": float(selected["greedy_score"].r1),
        "objective_profile": S7C_OBJECTIVE_PROFILE,
        "features": features,
        "space": space,
        "gmm": gmm,
        "ref_eval_before": before_snapshot,
        "ref_eval_after": after_snapshot,
        "ft_fieldnames": fieldnames,
        "unused_labels": (TRAIN_LABEL, VALIDATION_LABEL),
        "ref_rows_loaded": len(ref_rows),
        "eval_rows_loaded": len(eval_rows),
    }


def run_s7c_ft_split_apply(
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
    verify_ref_eval_freeze: bool = True,
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config = json.loads(_resolve(root, str(config_path)).read_text(encoding="utf-8"))
    enforce_s7c_application_config(config)

    preview_dir = _resolve(root, config["preview_output_dir"])
    output_dir = _resolve(root, config["output_dir"])
    if preview_dir.resolve() == output_dir.resolve():
        raise S7CSplitError(
            "S7C application must not write to the reviewed preview directory"
        )
    assert_application_dir_not_preview(output_dir, root)
    assert_preview_dir_not_protected(output_dir, root)

    v1_preview_dir = config.get("v1_preview_dir")
    v1_copy_dir = config.get("v1_preview_historical_copy")
    v1_hashes_before = (
        _hash_dir_files(_resolve(root, str(v1_preview_dir)))
        if v1_preview_dir
        else {}
    )
    v1_copy_hashes_before = (
        _hash_dir_files(_resolve(root, str(v1_copy_dir)))
        if v1_copy_dir
        else {}
    )
    preview_hashes = _hash_preview_dir(preview_dir)
    approval: dict[str, Any] | None = None
    approval_rel = str(config.get("approval_record") or "")
    if approval_rel:
        approval = json.loads(_resolve(root, approval_rel).read_text(encoding="utf-8"))
        assert_no_sequence_leak(
            _resolve(root, approval_rel).read_text(encoding="utf-8"),
            label=Path(approval_rel).name,
        )
        v2 = approval.get("v2") or {}
        expected_preview_hashes = (
            v2.get("reviewed_preview_hashes") or approval.get("reviewed_preview_hashes") or {}
        )
        if expected_preview_hashes and dict(expected_preview_hashes) != preview_hashes:
            raise S7CSplitError(
                "reviewed v2 preview artefacts have changed since human approval"
            )
        usage = v2.get("usage") or approval.get("usage") or {}
        if usage.get("used_for_scientific_assignment") is True:
            raise S7CSplitError(
                "approval record must not be configured as a scientific-assignment input"
            )
        if v2.get("review_status") != "approved_for_application_and_freeze":
            raise S7CSplitError(
                "S7C v2 approval review_status is not approved_for_application_and_freeze"
            )
        v1 = approval.get("v1") or {}
        if v1.get("review_status") not in {"not_approved", "rejected"}:
            raise S7CSplitError("S7C approval must record v1 as not approved")
    elif require_approval_parity:
        raise S7CSplitError("S7C application requires an approval record")

    ft_path = _resolve(root, config["ft_csv"])
    ref_path = _resolve(root, config["ref_csv"])
    eval_path = _resolve(root, config["eval_csv"])
    input_sha = sha256_file(ft_path)
    expected_ft_sha = config.get("expected_ft_sha256") or FROZEN_FT_SHA256
    if verify_hashes and input_sha != expected_ft_sha:
        raise S7CSplitError(
            f"frozen FT SHA-256 mismatch: expected {expected_ft_sha}, got {input_sha}"
        )
    if verify_hashes:
        _assert_git_ls_files_data_empty(root)
    approved_ft_sha = None
    if approval is not None:
        approved_ft_sha = (approval.get("v2") or {}).get("frozen_ft_sha256") or approval.get(
            "frozen_ft_sha256"
        )
        if approved_ft_sha not in {"", None} and approved_ft_sha != input_sha:
            raise S7CSplitError("approval frozen_ft_sha256 does not match live FT input")

    freeze_expected = frozen_ref_eval_expected(config)
    before_snapshot = None
    if verify_ref_eval_freeze:
        before_snapshot = _load_ref_eval_snapshot(
            ref_path=ref_path, eval_path=eval_path, expected=freeze_expected
        )

    fieldnames, ft_rows = _read_csv_with_fields(ft_path)
    snapshot_rows = [dict(row) for row in ft_rows]
    ref_rows = _read_csv(ref_path)
    eval_rows = _read_csv(eval_path)
    ref_cluster_ids = before_snapshot.ref_cluster_ids if before_snapshot is not None else set()
    eval_cluster_ids = before_snapshot.eval_cluster_ids if before_snapshot is not None else set()
    ref_identity_ids = before_snapshot.ref_identity_ids if before_snapshot is not None else set()
    eval_identity_ids = before_snapshot.eval_identity_ids if before_snapshot is not None else set()
    if "partition" not in fieldnames:
        raise S7CSplitError("FT input is missing the partition column")

    gmm_path = _resolve(root, config["length_regime"]["s6_bimodality_json"])
    gmm_payload = json.loads(gmm_path.read_text(encoding="utf-8"))
    gmm = load_frozen_s6_gmm(gmm_payload)
    if verify_hashes:
        _expected_gmm_matches(config, gmm)

    derived = _derive_s7c_assignment(
        ft_rows=ft_rows,
        config=config,
        gmm=gmm,
        expected_counts=(config.get("expected_input_counts") if enforce_expected_counts else None),
        repeat_for_determinism=repeat_for_determinism,
        run_random_baseline=run_random_baseline,
        ref_cluster_ids=ref_cluster_ids,
        eval_cluster_ids=eval_cluster_ids,
        ref_identity_ids=ref_identity_ids,
        eval_identity_ids=eval_identity_ids,
        enforce_expected_counts=enforce_expected_counts,
    )
    if not input_unmutated(ft_rows, snapshot_rows):
        raise S7CSplitError("S7C mutated FT input rows")
    if verify_hashes and sha256_file(ft_path) != input_sha:
        raise S7CSplitError("S7C mutated the frozen FT input file")

    assignment = derived["assignment"]
    quotas = derived["quotas"]
    score = derived["score"]
    features = derived["features"]
    selected = derived["selected"]
    preview_assignment = _preview_assignment_from_csv(
        preview_dir / "cluster_ft_split_preview.csv"
    )
    preview_manifest = json.loads(
        (preview_dir / "s7c_ft_split_preview_manifest.json").read_text(encoding="utf-8")
    )
    preview_tables = _preview_tables_from_dir(preview_dir)
    preview_summary = preview_manifest.get("selected_quotas") or {}
    parity = s7c_preview_application_parity_mismatches(
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
        raise S7CSplitError(
            "preview/application semantic mismatches: " + "; ".join(parity["mismatches"])
        )
    approval_mismatches: list[str] = []
    if approval is not None:
        approval_mismatches = s7c_approval_parity_mismatches(
            assignment=assignment,
            features=features,
            quotas=quotas,
            score=score,
            target_diag=derived["target_diag"],
            approval=approval,
        )
        if require_approval_parity and approval_mismatches:
            raise S7CSplitError(
                "approval/application semantic mismatches: "
                + "; ".join(approval_mismatches)
            )

    application_tables = build_s7c_application_tables(
        features=features,
        space=derived["space"],
        assignment=assignment,
        score=score,
        family_js=derived["family_js"],
    )
    annotated_rows, output_fields = populate_ft_split_on_ft_rows(
        ft_rows, assignment, fieldnames
    )

    output_paths = {key: output_dir / name for key, name in APPLICATION_OUTPUT_NAMES.items()}
    output_hashes: dict[str, str] = {}
    independent: dict[str, Any] = {}
    distribution_counts: dict[str, Any] = {}
    freeze_payload: dict[str, Any] | None = None
    determinism_ok = True
    train_identity_hash = ""
    train_cluster_hash = ""
    validation_identity_hash = ""
    validation_cluster_hash = ""
    after_snapshot = before_snapshot
    if write_outputs:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        if repeat_for_determinism:
            with tempfile.TemporaryDirectory(
                prefix="s7c_apply_a_", dir=str(output_dir.parent)
            ) as first_dir, tempfile.TemporaryDirectory(
                prefix="s7c_apply_b_", dir=str(output_dir.parent)
            ) as second_dir:
                _write_application_payloads(
                    output_dir=Path(first_dir),
                    annotated_rows=annotated_rows,
                    output_fields=output_fields,
                    tables=application_tables,
                    repo_root=root,
                )
                _write_application_payloads(
                    output_dir=Path(second_dir),
                    annotated_rows=annotated_rows,
                    output_fields=output_fields,
                    tables=application_tables,
                    repo_root=root,
                )
                for name in DETERMINISTIC_PAYLOAD_NAMES:
                    first_file = Path(first_dir) / name
                    second_file = Path(second_dir) / name
                    if _payload_hash(first_file) != _payload_hash(second_file):
                        raise S7CSplitError(
                            f"S7C application payload {name} is not byte-identical across reruns"
                        )
        written_paths = _write_application_payloads(
            output_dir=output_dir,
            annotated_rows=annotated_rows,
            output_fields=output_fields,
            tables=application_tables,
            repo_root=root,
        )
        reloaded_train = _read_csv(written_paths["ft_train_csv"])
        reloaded_validation = _read_csv(written_paths["ft_validation_csv"])
        reloaded_assignment_rows = _read_csv(written_paths["ft_split_assignment_csv"])
        reloaded_annotated = list(reloaded_train) + list(reloaded_validation)
        # Restore source FT row order for field-preservation comparison.
        by_id = {
            row["scientific_identity_id"]: row for row in reloaded_annotated
        }
        reloaded_in_ft_order = [
            by_id[row["scientific_identity_id"]] for row in ft_rows
        ]
        independent = independent_s7c_invariants(
            input_rows=ft_rows,
            annotated_rows=reloaded_in_ft_order,
            train_rows=reloaded_train,
            validation_rows=reloaded_validation,
            assignment_rows=reloaded_assignment_rows,
            fieldnames=fieldnames,
            ref_rows=ref_rows,
            eval_rows=eval_rows,
        )
        if independent["ft_split_blank"] or independent["invalid_ft_split_labels"]:
            raise S7CSplitError("authoritative ft_split labels are blank or invalid")
        if independent["E5"] or independent["non_protein"]:
            raise S7CSplitError("authoritative FT split introduced E5 or non-protein records")
        if independent["field_changes_excluding_ft_split"]:
            raise S7CSplitError("S7C changed frozen scientific fields other than ft_split")
        if independent["non_ft_partition"]:
            raise S7CSplitError("S7C altered top-level partition on train/validation files")
        distribution_counts = independent_s7c_distribution_counts(
            reloaded_in_ft_order, derived["core_regimes"]
        )
        reloaded_assignment = assignment_from_ft_split_rows(reloaded_in_ft_order)
        if reloaded_assignment != assignment:
            raise S7CSplitError("reloaded train/validation assignment drifted")
        independent_score = score_s7c_assignment(
            reloaded_assignment, derived["features"], derived["space"]
        )
        if independent_score.as_dict() != score.as_dict():
            raise S7CSplitError(
                "independently recomputed objective disagrees with derivation"
            )
        train_identity_hash = semantic_identity_set_hash(reloaded_train)
        train_cluster_hash = semantic_cluster_set_hash(reloaded_train)
        validation_identity_hash = semantic_identity_set_hash(reloaded_validation)
        validation_cluster_hash = semantic_cluster_set_hash(reloaded_validation)
        payload_hashes = {
            name: _payload_hash(output_dir / name) for name in DETERMINISTIC_PAYLOAD_NAMES
        }
        if verify_ref_eval_freeze:
            after_snapshot = _load_ref_eval_snapshot(
                ref_path=ref_path, eval_path=eval_path, expected=freeze_expected
            )
            assert_ref_eval_unchanged(before_snapshot, after_snapshot)
        ref_eval_before_payload = jsonable_s7c(before_snapshot) if before_snapshot else {}
        ref_eval_after_payload = jsonable_s7c(after_snapshot) if after_snapshot else {}
        report = build_s7c_application_report(
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
            greedy_r1=float(selected["greedy_score"].r1),
            freeze_date=str(config.get("freeze_date") or FREEZE_DATE),
            train_identity_set_hash=train_identity_hash,
            validation_identity_set_hash=validation_identity_hash,
            ref_eval_before=ref_eval_before_payload,
            ref_eval_after=ref_eval_after_payload,
            determinism_ok=determinism_ok,
        )
        write_text_atomic(written_paths["report_md"], report)
        freeze_rel = str(config.get("freeze_record") or "")
        freeze_path = _resolve(root, freeze_rel) if freeze_rel else None
        freeze_payload = build_s7c_freeze_record(
            input_sha256=input_sha,
            preview_assignment_sha256=preview_hashes["cluster_ft_split_preview.csv"],
            preview_manifest_sha256=preview_hashes["s7c_ft_split_preview_manifest.json"],
            authoritative_assignment_sha256=payload_hashes["ft_split_assignment.csv"],
            quotas=quotas,
            independent=independent,
            output_hashes=payload_hashes,
            train_identity_set_hash=train_identity_hash,
            train_cluster_set_hash=train_cluster_hash,
            validation_identity_set_hash=validation_identity_hash,
            validation_cluster_set_hash=validation_cluster_hash,
            ref_snapshot=ref_eval_after_payload or ref_eval_before_payload,
            eval_snapshot=ref_eval_after_payload or ref_eval_before_payload,
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
            raise S7CSplitError(
                "sequence leak in tracked S7C files: " + ", ".join(leaked)
            )
        manifest = {
            "ok": True,
            "milestone": config["milestone"],
            "mode": APPLY_MODE,
            "ft_train_frozen": True,
            "ft_validation_frozen": True,
            "authoritative_train_validation_written": True,
            "ref_frozen": True,
            "eval_frozen": True,
            "ref_changed": False,
            "eval_changed": False,
            "model_fine_tuning_started": False,
            "s7d_started": False,
            "ft_input_mutated": False,
            "top_level_partition_altered": False,
            "approval_record": approval_rel,
            "approval_used_for_scientific_assignment": False,
            "freeze_record": freeze_rel,
            "freeze_date": str(config.get("freeze_date") or FREEZE_DATE),
            "freeze_reason": str(config.get("freeze_reason") or FREEZE_REASON),
            "input_path": config["ft_csv"],
            "input_sha256": input_sha,
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
                "n_TRAIN": quotas.n_TRAIN,
                "n_VALIDATION": quotas.n_VALIDATION,
            },
            "objective": score.as_dict(),
            "objective_profile": S7C_OBJECTIVE_PROFILE,
            "greedy_R1": float(selected["greedy_score"].r1),
            "n_accepted_swaps": int(selected["n_accepted_swaps"]),
            "n_local_search_passes": int(selected["n_local_search_passes"]),
            "local_search_converged": bool(selected["local_search_converged"]),
            "integrity": jsonable_s7c(derived["integrity"]),
            "independent": jsonable_s7c(independent),
            "independent_distributions": jsonable_s7c(distribution_counts),
            "target_representation": jsonable_s7c(
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
            "train_freeze": {
                "frozen": True,
                "file_sha256": payload_hashes["ft_train.csv"],
                "semantic_identity_set_hash": train_identity_hash,
                "semantic_cluster_set_hash": train_cluster_hash,
            },
            "validation_freeze": {
                "frozen": True,
                "file_sha256": payload_hashes["ft_validation.csv"],
                "semantic_identity_set_hash": validation_identity_hash,
                "semantic_cluster_set_hash": validation_cluster_hash,
            },
            "ref_eval_before": ref_eval_before_payload,
            "ref_eval_after": ref_eval_after_payload,
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
        output_hashes["s7c_ft_split_report.md"] = _payload_hash(written_paths["report_md"])
        output_hashes["s7c_ft_split_manifest.json"] = _payload_hash(
            written_paths["manifest_json"]
        )
        post_preview_hashes = _hash_preview_dir(preview_dir)
        if post_preview_hashes != preview_hashes:
            raise S7CSplitError(
                "S7C application overwrote the reviewed v2 preview artefacts"
            )
        if v1_preview_dir:
            if _hash_dir_files(_resolve(root, str(v1_preview_dir))) != v1_hashes_before:
                raise S7CSplitError("S7C application overwrote the preserved v1 preview")
        if v1_copy_dir:
            if _hash_dir_files(_resolve(root, str(v1_copy_dir))) != v1_copy_hashes_before:
                raise S7CSplitError("S7C application overwrote the preserved v1 historical copy")
        if verify_hashes:
            _assert_git_ls_files_data_empty(root)
            if sha256_file(ft_path) != input_sha:
                raise S7CSplitError("frozen FT input hash changed after application")
        if verify_ref_eval_freeze:
            final_snapshot = _load_ref_eval_snapshot(
                ref_path=ref_path, eval_path=eval_path, expected=freeze_expected
            )
            assert_ref_eval_unchanged(before_snapshot, final_snapshot)
            after_snapshot = final_snapshot
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
        "ft_train_frozen": True,
        "ft_validation_frozen": True,
        "train_identity_set_hash": train_identity_hash,
        "train_cluster_set_hash": train_cluster_hash,
        "validation_identity_set_hash": validation_identity_hash,
        "validation_cluster_set_hash": validation_cluster_hash,
        "freeze_record": freeze_payload,
        "n_accepted_swaps": int(selected["n_accepted_swaps"]),
        "n_local_search_passes": int(selected["n_local_search_passes"]),
        "local_search_converged": bool(selected["local_search_converged"]),
        "greedy_o1": float(selected["greedy_score"].r1),
        "features": features,
        "space": derived["space"],
        "gmm": gmm,
        "ref_eval_before": before_snapshot,
        "ref_eval_after": after_snapshot,
        "n_short_cores": derived["n_short"],
        "n_long_cores": derived["n_long"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="S7C FT train/validation split preview / application"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--skip-expected-counts",
        action="store_true",
        help="Do not enforce live FT regression counts (synthetic use only)",
    )
    parser.add_argument(
        "--skip-hash-gate",
        action="store_true",
        help="Do not verify frozen FT SHA-256 (synthetic use only)",
    )
    parser.add_argument(
        "--skip-determinism-repeat",
        action="store_true",
        help="Optimise once (not authorised for the live scientific run)",
    )
    parser.add_argument(
        "--skip-random-baseline",
        action="store_true",
        help="Skip the diagnostic random whole-cluster baseline",
    )
    parser.add_argument(
        "--skip-ref-eval-freeze",
        action="store_true",
        help="Do not verify frozen REF/EVAL hashes (synthetic use only)",
    )
    args = parser.parse_args()
    root = find_repo_root()
    config = json.loads(_resolve(root, str(args.config)).read_text(encoding="utf-8"))
    mode = str(config.get("mode") or "").strip()
    try:
        if mode == PREVIEW_MODE:
            result = run_s7c_ft_split_preview(
                config_path=args.config,
                enforce_expected_counts=not args.skip_expected_counts,
                verify_hashes=not args.skip_hash_gate,
                repeat_for_determinism=not args.skip_determinism_repeat,
                run_random_baseline=not args.skip_random_baseline,
                verify_ref_eval_freeze=not args.skip_ref_eval_freeze,
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
                            "n_TRAIN": quotas.n_TRAIN,
                            "n_VALIDATION": quotas.n_VALIDATION,
                        },
                        "R1": score.r1,
                        "R3": score.r3,
                        "O1_jsd_diagnostic": score.o1,
                        "O3_jsd_diagnostic": score.o3,
                        "authoritative_train_validation_written": False,
                        "ft_train_frozen": False,
                        "ft_validation_frozen": False,
                        "ref_changed": False,
                        "eval_changed": False,
                        "model_fine_tuning_started": False,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if mode == APPLY_MODE:
            result = run_s7c_ft_split_apply(
                config_path=args.config,
                enforce_expected_counts=not args.skip_expected_counts,
                verify_hashes=not args.skip_hash_gate,
                repeat_for_determinism=not args.skip_determinism_repeat,
                verify_ref_eval_freeze=not args.skip_ref_eval_freeze,
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
                            "n_TRAIN": quotas.n_TRAIN,
                            "n_VALIDATION": quotas.n_VALIDATION,
                        },
                        "R1": score.r1,
                        "R3": score.r3,
                        "n_preview_application_semantic_mismatches": parity[
                            "semantic_mismatches_total"
                        ],
                        "approval_used_for_scientific_assignment": False,
                        "authoritative_train_validation_written": True,
                        "ft_train_frozen": True,
                        "ft_validation_frozen": True,
                        "ref_changed": False,
                        "eval_changed": False,
                        "model_fine_tuning_started": False,
                        "s7d_started": False,
                        "determinism_ok": result["determinism_ok"],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        raise S7CSplitError(f"S7C mode must be preview or apply, got {mode!r}")
    except S7CSplitError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

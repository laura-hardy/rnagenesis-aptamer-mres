#!/usr/bin/env python3
"""GLOBAL S5E — leakage-safe final cluster construction + S5 closure.

Unions frozen S5C MMseqs clusters with trusted real multi-member ENA
family must-links. Does not rerun MMseqs, select CD-HIT, overwrite
S5A/S5C artefacts, balance, partition, commit, or push.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s4_scientific_common import (  # noqa: E402
    ScientificProposalError,
    assert_no_sequence_leak,
    write_json_atomic,
    write_text_atomic,
)
from adapters.s5_final_clustering import (  # noqa: E402
    CLUSTER_SUMMARY_FINAL_COLUMNS,
    CLUSTER_UNION_PROVENANCE_COLUMNS,
    CLUSTERS_FINAL_COLUMNS,
    CORPUS_CLUSTERED_FINAL_COLUMNS,
    FAMILY_CONTAINMENT_COLUMNS,
    FROZEN_CORPUS_DEDUP_NAME,
    MUST_LINK_COHORT_COLUMNS,
    S5FinalClusteringError,
    assemble_final_clustering,
    assert_not_frozen_s5_path,
    build_overlap_report,
    compare_final_runs,
    enforce_authorised_parameters,
)
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402

DEFAULT_CONFIG = Path("config/global_s5e_final_clustering.json")
SCIENTIFIC_MANIFEST_KEYS: tuple[str, ...] = (
    "ok",
    "milestone",
    "base_sequence_clustering_method",
    "base_sequence_clustering_parameters",
    "family_constraint_source",
    "family_constraint_semantics",
    "materialised_singletons_as_cannot_link",
    "cd_hit_fallback_tested",
    "cd_hit_selected",
    "s5d_decision_historical",
    "s5d_interpretation_superseded",
    "n_mmseqs_clusters",
    "n_final_clusters",
    "n_scientific_identities",
    "n_distinct_sequence_core",
    "n_must_link_families_contained",
    "n_must_link_families",
    "determinism_ok",
    "s5_closed",
    "cluster_id_convention",
    "representative_convention",
    "output_hashes",
    "diagnostics",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _resolve(root: Path, relative: str) -> Path:
    return (root / relative).resolve()


def _payload_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_hashes(root: Path, expected: Mapping[str, Sequence[str]]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for name, spec in expected.items():
        rel, digest = spec
        path = _resolve(root, rel)
        got = sha256_file(path)
        observed[name] = got
        if got != digest:
            raise S5FinalClusteringError(
                f"{name} SHA-256 mismatch: expected {digest}, got {got}"
            )
    return observed


def _assert_git_ls_files_data_empty(root: Path) -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "data"], cwd=root, text=True
    ).strip()
    if tracked:
        raise S5FinalClusteringError("git ls-files data is not empty")


def _scientific_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in SCIENTIFIC_MANIFEST_KEYS if key in payload}


def run_s5e_final_clustering(
    *,
    config_path: Path,
    repo_root: Path | None = None,
    verify_hashes: bool = True,
    enforce_expected_counts: bool = True,
    repeat_for_determinism: bool = True,
    write_outputs: bool = True,
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config = json.loads(_resolve(root, str(config_path)).read_text(encoding="utf-8"))
    enforce_authorised_parameters(config)
    s4_hashes: dict[str, str] = {}
    s5a_hashes: dict[str, str] = {}
    s5c_hashes: dict[str, str] = {}
    if verify_hashes:
        s4_hashes = _verify_hashes(root, config["expected_s4_hashes"])
        s5a_hashes = _verify_hashes(root, config["expected_s5a_hashes"])
        s5c_hashes = _verify_hashes(root, config["expected_s5c_hashes"])
        _assert_git_ls_files_data_empty(root)

    frozen_dedup = _resolve(root, config["corpus_dedup_csv"])
    if frozen_dedup.name != FROZEN_CORPUS_DEDUP_NAME:
        raise S5FinalClusteringError("S5E must read frozen corpus_dedup.csv")
    output_dir = _resolve(root, config["output_dir"])
    output_paths: dict[str, Path] = {
        "clusters_final_tsv": output_dir / "clusters_final.tsv",
        "corpus_clustered_final_csv": output_dir / "corpus_clustered_final.csv",
        "cluster_summary_final_csv": output_dir / "cluster_summary_final.csv",
        "cluster_union_provenance_csv": output_dir / "cluster_union_provenance.csv",
        "family_containment_csv": output_dir / "s5e_ena_must_link_containment.csv",
        "must_link_cohort_csv": output_dir / "s5e_ena_must_link_cohort.csv",
        "overlap_report_md": output_dir / "overlap_report.md",
        "manifest_json": output_dir / "s5_final_clustering_manifest.json",
    }
    for path in output_paths.values():
        assert_not_frozen_s5_path(path)

    corpus_rows = _read_csv(frozen_dedup)
    membership_rows = _read_csv(_resolve(root, config["membership_csv"]))
    mmseqs_cluster_rows = _read_csv(_resolve(root, config["mmseqs_clusters_tsv"]))
    mmseqs_clustered = _read_csv(_resolve(root, config["mmseqs_corpus_clustered_csv"]))
    overlap_matrix = _read_csv(_resolve(root, config["overlap_matrix_csv"]))
    expected = config.get("expected_counts") if enforce_expected_counts else None

    first = assemble_final_clustering(
        corpus_rows=corpus_rows,
        mmseqs_cluster_rows=mmseqs_cluster_rows,
        membership_rows=membership_rows,
        mmseqs_clustered_corpus=mmseqs_clustered,
        expected_counts=expected,
        shuffle_seed=None,
    )
    if repeat_for_determinism:
        second = assemble_final_clustering(
            corpus_rows=list(reversed(list(corpus_rows))),
            mmseqs_cluster_rows=list(reversed(list(mmseqs_cluster_rows))),
            membership_rows=list(reversed(list(membership_rows))),
            mmseqs_clustered_corpus=list(reversed(list(mmseqs_clustered))),
            expected_counts=expected,
            shuffle_seed=7,
        )
        compare_final_runs(first, second)

    result = first
    report = build_overlap_report(
        result.diagnostics,
        overlap_matrix=overlap_matrix,
        s4_hashes=s4_hashes,
        s5a_hashes=s5a_hashes,
        s5c_hashes=s5c_hashes,
    )
    assert_no_sequence_leak(report, label="overlap_report.md")

    output_hashes: dict[str, str] = {}
    if write_outputs:
        write_corpus_csv_atomic(
            output_paths["clusters_final_tsv"],
            result.clusters_final,
            columns=CLUSTERS_FINAL_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["corpus_clustered_final_csv"],
            result.clustered_corpus,
            columns=CORPUS_CLUSTERED_FINAL_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["cluster_summary_final_csv"],
            result.cluster_summary,
            columns=CLUSTER_SUMMARY_FINAL_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["cluster_union_provenance_csv"],
            result.union_provenance,
            columns=CLUSTER_UNION_PROVENANCE_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["family_containment_csv"],
            result.family_containment,
            columns=FAMILY_CONTAINMENT_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["must_link_cohort_csv"],
            result.must_link_cohort,
            columns=MUST_LINK_COHORT_COLUMNS,
        )
        write_text_atomic(output_paths["overlap_report_md"], report)
        csv_hash_names = (
            "clusters_final_tsv",
            "corpus_clustered_final_csv",
            "cluster_summary_final_csv",
            "cluster_union_provenance_csv",
            "family_containment_csv",
            "must_link_cohort_csv",
        )
        csv_hashes = {
            name: _payload_hash(output_paths[name]) for name in csv_hash_names
        }
        report_with_hashes = build_overlap_report(
            result.diagnostics,
            overlap_matrix=overlap_matrix,
            s4_hashes=s4_hashes,
            s5a_hashes=s5a_hashes,
            s5c_hashes=s5c_hashes,
            output_hashes=csv_hashes,
        )
        assert_no_sequence_leak(report_with_hashes, label="overlap_report.md")
        write_text_atomic(output_paths["overlap_report_md"], report_with_hashes)
        output_hashes = {
            name: _payload_hash(path)
            for name, path in output_paths.items()
            if name != "manifest_json"
        }
        ena = result.diagnostics["ena_must_link"]
        manifest = {
            "ok": True,
            "milestone": config["milestone"],
            "base_sequence_clustering_method": "mmseqs",
            "base_sequence_clustering_parameters": (
                "--min-seq-id 0.9 -c 0.8 --cov-mode 1 -s 7.5"
            ),
            "family_constraint_source": "ena.near_duplicate_family_id",
            "family_constraint_semantics": "positive_must_link_only",
            "materialised_singletons_as_cannot_link": False,
            "cd_hit_fallback_tested": True,
            "cd_hit_selected": False,
            "s5d_decision_historical": (
                "NO-GO — GROUND-TRUTH / 90%-RULE CONTRADICTION"
            ),
            "s5d_interpretation_superseded": True,
            "s5d_findings": {
                "mmseqs_16_family_containment": 8,
                "cdhit_16_family_containment": 11,
                "ena_families_are_not_global_90_percent_ground_truth": True,
                "ena_families_are_positive_must_link_only": True,
            },
            "n_mmseqs_clusters": result.diagnostics["n_mmseqs_clusters"],
            "n_final_clusters": result.diagnostics["n_final_clusters"],
            "n_scientific_identities": result.diagnostics["n_scientific_identities"],
            "n_distinct_sequence_core": result.diagnostics["n_distinct_sequence_core"],
            "n_must_link_families": ena["n_must_link_families"],
            "n_must_link_families_contained": ena["n_must_link_families_contained"],
            "determinism_ok": True,
            "s5_closed": True,
            "s4_hashes": s4_hashes,
            "s5a_hashes": s5a_hashes,
            "s5c_candidate_hashes": s5c_hashes,
            "cluster_id_convention": result.diagnostics["cluster_id_convention"],
            "representative_convention": result.diagnostics["representative_convention"],
            "output_hashes": output_hashes,
            "diagnostics": {
                key: value
                for key, value in result.diagnostics.items()
                if key != "largest_clusters"
            },
        }
        write_json_atomic(output_paths["manifest_json"], manifest)
        output_hashes["manifest_json"] = _payload_hash(output_paths["manifest_json"])

        if repeat_for_determinism:
            rerun = assemble_final_clustering(
                corpus_rows=corpus_rows,
                mmseqs_cluster_rows=mmseqs_cluster_rows,
                membership_rows=membership_rows,
                mmseqs_clustered_corpus=mmseqs_clustered,
                expected_counts=expected,
                shuffle_seed=13,
            )
            compare_final_runs(result, rerun)
            if _payload_hash(output_paths["clusters_final_tsv"]) != output_hashes[
                "clusters_final_tsv"
            ]:
                raise S5FinalClusteringError("clusters_final.tsv changed after write")

    if verify_hashes:
        s4_after = _verify_hashes(root, config["expected_s4_hashes"])
        s5a_after = _verify_hashes(root, config["expected_s5a_hashes"])
        s5c_after = _verify_hashes(root, config["expected_s5c_hashes"])
        if s4_after != s4_hashes:
            raise S5FinalClusteringError("S4 hashes changed during S5E")
        if s5a_after != s5a_hashes:
            raise S5FinalClusteringError("S5A freeze hashes changed during S5E")
        if s5c_after != s5c_hashes:
            raise S5FinalClusteringError("S5C candidate hashes changed during S5E")
        _assert_git_ls_files_data_empty(root)

    return {
        "ok": True,
        "s5_closed": True,
        "diagnostics": result.diagnostics,
        "s4_hashes": s4_hashes,
        "s5a_hashes": s5a_hashes,
        "s5c_hashes": s5c_hashes,
        "output_paths": {name: str(path) for name, path in output_paths.items()},
        "output_hashes": output_hashes,
        "determinism_ok": True,
        "scientific_manifest": _scientific_manifest(
            {
                "ok": True,
                "milestone": config["milestone"],
                "base_sequence_clustering_method": "mmseqs",
                "base_sequence_clustering_parameters": (
                    "--min-seq-id 0.9 -c 0.8 --cov-mode 1 -s 7.5"
                ),
                "family_constraint_source": "ena.near_duplicate_family_id",
                "family_constraint_semantics": "positive_must_link_only",
                "materialised_singletons_as_cannot_link": False,
                "cd_hit_fallback_tested": True,
                "cd_hit_selected": False,
                "s5d_decision_historical": (
                    "NO-GO — GROUND-TRUTH / 90%-RULE CONTRADICTION"
                ),
                "s5d_interpretation_superseded": True,
                "n_mmseqs_clusters": result.diagnostics["n_mmseqs_clusters"],
                "n_final_clusters": result.diagnostics["n_final_clusters"],
                "n_scientific_identities": result.diagnostics["n_scientific_identities"],
                "n_distinct_sequence_core": result.diagnostics["n_distinct_sequence_core"],
                "n_must_link_families_contained": result.diagnostics["ena_must_link"][
                    "n_must_link_families_contained"
                ],
                "n_must_link_families": result.diagnostics["ena_must_link"][
                    "n_must_link_families"
                ],
                "determinism_ok": True,
                "s5_closed": True,
                "cluster_id_convention": result.diagnostics["cluster_id_convention"],
                "representative_convention": result.diagnostics[
                    "representative_convention"
                ],
                "output_hashes": output_hashes,
                "diagnostics": result.diagnostics,
            }
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="S5E leakage-safe final cluster construction"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--skip-expected-counts",
        action="store_true",
        help="Do not enforce live S5A/S5C regression counts (synthetic use only)",
    )
    parser.add_argument(
        "--skip-hash-gate",
        action="store_true",
        help="Do not verify frozen S4/S5A/S5C hashes (synthetic use only)",
    )
    parser.add_argument(
        "--skip-determinism-repeat",
        action="store_true",
        help="Assemble once (not authorised for the live scientific freeze)",
    )
    args = parser.parse_args()
    try:
        result = run_s5e_final_clustering(
            config_path=args.config,
            enforce_expected_counts=not args.skip_expected_counts,
            verify_hashes=not args.skip_hash_gate,
            repeat_for_determinism=not args.skip_determinism_repeat,
        )
    except (S5FinalClusteringError, ScientificProposalError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "s5_closed": result["s5_closed"],
                "n_scientific_identities": result["diagnostics"]["n_scientific_identities"],
                "n_distinct_sequence_core": result["diagnostics"][
                    "n_distinct_sequence_core"
                ],
                "n_mmseqs_clusters": result["diagnostics"]["n_mmseqs_clusters"],
                "n_final_clusters": result["diagnostics"]["n_final_clusters"],
                "n_must_link_families_contained": result["diagnostics"]["ena_must_link"][
                    "n_must_link_families_contained"
                ],
                "determinism_ok": result["determinism_ok"],
                "output_hashes": result["output_hashes"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

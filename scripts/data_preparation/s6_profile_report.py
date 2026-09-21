#!/usr/bin/env python3
"""GLOBAL S6 — pre-balancing corpus profile + CHECKPOINT-3 preparation.

Reads the frozen final S5 clustered corpus and writes a supervisor-facing
profile. Does not balance, apply a target cap, assign FT/REF/EVAL,
populate partition, drop rows, rewrite S4/S5, commit, or start S7.
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
    write_json_atomic,
    write_text_atomic,
)
from adapters.s5_validate_exact_dedup import scan_paths_for_sequence_leak  # noqa: E402
from adapters.s6_profile import (  # noqa: E402
    CANDIDATE_FRACTIONS,
    S6ProfileError,
    assemble_profile,
    assert_no_sequence_leak,
    assert_not_frozen_s5_path,
    compare_assemblies,
    enforce_authorised_config,
)
from adapters.s6_profile_render import (  # noqa: E402
    build_corpus_profile_report,
    build_figure_pack_supervisor,
    write_checkpoint3_package,
    write_figures,
    write_profile_tables,
)
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402

DEFAULT_CONFIG = Path("config/global_s6_profile.json")


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
            raise S6ProfileError(f"{name} SHA-256 mismatch: expected {digest}, got {got}")
    return observed


def _assert_git_ls_files_data_empty(root: Path) -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "data"], cwd=root, text=True
    ).strip()
    if tracked:
        raise S6ProfileError("git ls-files data is not empty")


def run_s6_profile(
    *,
    config_path: Path,
    repo_root: Path | None = None,
    verify_hashes: bool = True,
    enforce_expected_counts: bool = True,
    repeat_for_determinism: bool = True,
    write_outputs: bool = True,
    write_figures_flag: bool = True,
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config = json.loads(_resolve(root, str(config_path)).read_text(encoding="utf-8"))
    enforce_authorised_config(config)
    s4_hashes: dict[str, str] = {}
    s5a_hashes: dict[str, str] = {}
    s5_final_hashes: dict[str, str] = {}
    if verify_hashes:
        s4_hashes = _verify_hashes(root, config["expected_s4_hashes"])
        s5a_hashes = _verify_hashes(root, config["expected_s5a_hashes"])
        s5_final_hashes = _verify_hashes(root, config["expected_s5_final_hashes"])
        _assert_git_ls_files_data_empty(root)

    corpus_path = _resolve(root, config["authoritative_corpus"])
    corpus_rows = _read_csv(corpus_path)
    cluster_summary_rows = _read_csv(_resolve(root, config["cluster_summary_final_csv"]))
    union_rows = _read_csv(_resolve(root, config["cluster_union_provenance_csv"]))
    membership_rows = _read_csv(_resolve(root, config["membership_csv"]))
    overlap_rows = _read_csv(_resolve(root, config["overlap_matrix_csv"]))
    clusters_final_rows = _read_csv(_resolve(root, config["clusters_final_tsv"]))
    expected = config.get("expected_counts") if enforce_expected_counts else None
    fractions = tuple(
        float(v)
        for v in config.get("candidate_max_target_fractions", list(CANDIDATE_FRACTIONS))
    )
    if not fractions:
        fractions = CANDIDATE_FRACTIONS

    first = assemble_profile(
        corpus_rows,
        cluster_summary_rows=cluster_summary_rows,
        union_provenance_rows=union_rows,
        membership_rows=membership_rows,
        overlap_matrix_rows=overlap_rows,
        clusters_final_rows=clusters_final_rows,
        expected_counts=expected,
        candidate_fractions=fractions,
    )
    if repeat_for_determinism:
        second = assemble_profile(
            list(reversed(list(corpus_rows))),
            cluster_summary_rows=list(reversed(list(cluster_summary_rows))),
            union_provenance_rows=list(reversed(list(union_rows))),
            membership_rows=list(reversed(list(membership_rows))),
            overlap_matrix_rows=list(reversed(list(overlap_rows))),
            clusters_final_rows=list(reversed(list(clusters_final_rows))),
            expected_counts=expected,
            candidate_fractions=fractions,
        )
        compare_assemblies(first, second)

    assembly = first
    report = build_corpus_profile_report(
        assembly,
        s4_hashes=s4_hashes,
        s5a_hashes=s5a_hashes,
        s5_final_hashes=s5_final_hashes,
    )
    assert_no_sequence_leak(report, label="corpus_profile_report.md")

    output_hashes: dict[str, str] = {}
    output_paths: dict[str, str] = {}
    if write_outputs:
        report_path = _resolve(root, config["output_report_md"])
        profile_dir = _resolve(root, config["profile_dir"])
        figures_dir = _resolve(root, config["figures_dir"])
        checkpoint_dir = _resolve(root, config["checkpoint3_dir"])
        manifest_path = _resolve(root, config["manifest_json"])
        for path in (report_path, manifest_path):
            assert_not_frozen_s5_path(path)
        write_text_atomic(report_path, report)
        table_paths = write_profile_tables(assembly, profile_dir)
        checkpoint_paths = write_checkpoint3_package(assembly, checkpoint_dir)
        figure_paths: dict[str, str] = {}
        if write_figures_flag:
            figure_paths = write_figures(assembly, figures_dir)
        pack_rel = config.get(
            "output_figure_pack_md", "data/interim/deduplicated/figure_pack_supervisor.md"
        )
        pack_path = _resolve(root, pack_rel)
        assert_not_frozen_s5_path(pack_path)
        write_text_atomic(pack_path, build_figure_pack_supervisor(assembly))
        supervisor_rel = config.get("output_supervisor_briefing_md")
        supervisor_path = None
        if supervisor_rel:
            supervisor_path = _resolve(root, supervisor_rel)
            assert_not_frozen_s5_path(supervisor_path)
            write_text_atomic(supervisor_path, report)
        output_paths = {
            "corpus_profile_report.md": str(report_path),
            "figure_pack_supervisor.md": str(pack_path),
            "manifest_json": str(manifest_path),
            **{name: str(path) for name, path in table_paths.items()},
            **{name: str(path) for name, path in checkpoint_paths.items()},
            **figure_paths,
        }
        if supervisor_path is not None:
            output_paths["corpus_profile_report_supervisor.md"] = str(supervisor_path)
        hashed_names = [
            "corpus_profile_report.md",
            "checkpoint3_summary.md",
            "checkpoint3_decisions.csv",
            "target_profile.csv",
            "target_family_profile.csv",
            "candidate_cap_impact.csv",
            "candidate_cap_overrepresented_targets.csv",
            "length_profile.csv",
            "nucleotide_composition.csv",
            "cluster_profile.csv",
            "source_profile.csv",
            "evidence_profile.csv",
            "licensing_profile.csv",
            "source_length_regime_summary.csv",
            "core_full_length_comparison.csv",
            "figure_pack_supervisor.md",
            "headline.json",
            "diversity_metrics.json",
            "bimodality.json",
            "scientific_payload.json",
        ]
        for name in hashed_names:
            rel = output_paths.get(name)
            if rel:
                output_hashes[name] = _payload_hash(Path(rel))
        scan_paths = [
            _resolve(root, rel) for rel in config.get("sequence_safety_scan_paths", [])
        ]
        scan_paths = [path for path in scan_paths if path.exists()]
        leaked = scan_paths_for_sequence_leak(scan_paths)
        if leaked:
            raise S6ProfileError("sequence leak in tracked S6 files: " + ", ".join(leaked))
        manifest = {
            "ok": True,
            "milestone": config["milestone"],
            "principal_grain": config["principal_grain"],
            "n_scientific_identities": assembly.headline["n_scientific_identities"],
            "n_distinct_sequence_core": assembly.headline["n_distinct_sequence_core"],
            "n_final_clusters": assembly.headline["n_final_clusters"],
            "n_canonical_targets": assembly.headline["n_canonical_targets"],
            "checkpoint3_prepared": True,
            "checkpoint3_decided": False,
            "balancing_applied": False,
            "target_cap_applied": False,
            "s7_started": False,
            "partition_populated": False,
            "s7_cluster_selection_specified": assembly.headline[
                "s7_cluster_selection_specified"
            ],
            "emergency_trigger_met": assembly.headline["emergency_trigger_met"],
            "bimodality_conclusion_core": assembly.headline["bimodality_conclusion_core"],
            "s4_hashes": s4_hashes,
            "s5a_hashes": s5a_hashes,
            "s5_final_hashes": s5_final_hashes,
            "output_hashes": output_hashes,
            "n_checkpoint3_decisions": len(assembly.checkpoint3_decisions),
            "checkpoint3_ids": [row["decision_id"] for row in assembly.checkpoint3_decisions],
            "sequence_safety": {
                "n_paths_scanned": len(scan_paths),
                "n_leaks": 0,
            },
        }
        write_json_atomic(manifest_path, json.loads(json.dumps(manifest)))
        output_hashes["manifest_json"] = _payload_hash(manifest_path)
        if repeat_for_determinism:
            rerun = assemble_profile(
                corpus_rows,
                cluster_summary_rows=cluster_summary_rows,
                union_provenance_rows=union_rows,
                membership_rows=membership_rows,
                overlap_matrix_rows=overlap_rows,
                clusters_final_rows=clusters_final_rows,
                expected_counts=expected,
                candidate_fractions=fractions,
            )
            compare_assemblies(assembly, rerun)
            if _payload_hash(report_path) != output_hashes["corpus_profile_report.md"]:
                raise S6ProfileError("corpus_profile_report.md changed after write")

    if verify_hashes:
        s4_after = _verify_hashes(root, config["expected_s4_hashes"])
        s5a_after = _verify_hashes(root, config["expected_s5a_hashes"])
        s5_after = _verify_hashes(root, config["expected_s5_final_hashes"])
        if s4_after != s4_hashes:
            raise S6ProfileError("S4 hashes changed during S6")
        if s5a_after != s5a_hashes:
            raise S6ProfileError("S5A freeze hashes changed during S6")
        if s5_after != s5_final_hashes:
            raise S6ProfileError("final S5 freeze hashes changed during S6")
        _assert_git_ls_files_data_empty(root)

    return {
        "ok": True,
        "headline": assembly.headline,
        "assertions": assembly.assertions,
        "s4_hashes": s4_hashes,
        "s5a_hashes": s5a_hashes,
        "s5_final_hashes": s5_final_hashes,
        "output_paths": output_paths,
        "output_hashes": output_hashes,
        "checkpoint3_ids": [row["decision_id"] for row in assembly.checkpoint3_decisions],
        "determinism_ok": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="S6 pre-balancing corpus profile")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--skip-expected-counts",
        action="store_true",
        help="Do not enforce live S5 regression counts (synthetic use only)",
    )
    parser.add_argument(
        "--skip-hash-gate",
        action="store_true",
        help="Do not verify frozen S4/S5 hashes (synthetic use only)",
    )
    parser.add_argument(
        "--skip-determinism-repeat",
        action="store_true",
        help="Assemble once (not authorised for the live scientific freeze)",
    )
    parser.add_argument(
        "--skip-figures",
        action="store_true",
        help="Skip PNG figures (tables and markdown still written)",
    )
    args = parser.parse_args()
    try:
        result = run_s6_profile(
            config_path=args.config,
            enforce_expected_counts=not args.skip_expected_counts,
            verify_hashes=not args.skip_hash_gate,
            repeat_for_determinism=not args.skip_determinism_repeat,
            write_figures_flag=not args.skip_figures,
        )
    except (S6ProfileError, ScientificProposalError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "n_scientific_identities": result["headline"]["n_scientific_identities"],
                "n_distinct_sequence_core": result["headline"]["n_distinct_sequence_core"],
                "n_final_clusters": result["headline"]["n_final_clusters"],
                "n_canonical_targets": result["headline"]["n_canonical_targets"],
                "checkpoint3_ids": result["checkpoint3_ids"],
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

#!/usr/bin/env python3
"""S5C 90% sequence-identity clustering.

Clusters the frozen exact-deduplicated primary corpus on ``sequence_core``
with MMseqs2. Does not overwrite the S5A freeze, run CD-HIT, balance
targets, assign FT/REF/EVAL, or begin S6/S7.
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
from adapters.s5_sequence_clustering import (  # noqa: E402
    CLUSTER_SUMMARY_COLUMNS,
    CLUSTER_TSV_COLUMNS,
    CORPUS_CLUSTERED_COLUMNS,
    ENA_FAMILY_DIAGNOSTIC_COLUMNS,
    FROZEN_CORPUS_DEDUP_NAME,
    IDENTITY_AUDIT_COLUMNS,
    SEQUENCE_IDENTITY_MAP_COLUMNS,
    SEQUENCE_INPUT_COLUMNS,
    S5SequenceClusteringError,
    assemble_clustering,
    assert_not_corpus_dedup_path,
    compare_cluster_runs,
    discover_mmseqs_environment,
    enforce_authorised_parameters,
    interpret_rna_u_preflight,
    parse_mmseqs_cluster_tsv,
    preflight_synthetic_sequences,
    project_unique_sequence_cores,
    render_fasta,
    run_mmseqs_easy_cluster,
    build_s5c_report,
)
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402

DEFAULT_CONFIG = Path("config/global_s5c_sequence_clustering.json")


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
            raise S5SequenceClusteringError(
                f"{name} SHA-256 mismatch: expected {digest}, got {got}"
            )
    return observed


def _assert_git_ls_files_data_empty(root: Path) -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "data"],
        cwd=root,
        text=True,
    ).strip()
    if tracked:
        raise S5SequenceClusteringError("git ls-files data is not empty")


def _write_fasta(path: Path, text: str) -> None:
    assert_not_corpus_dedup_path(path)
    write_text_atomic(path, text)


def _run_rna_u_preflight(
    *,
    work_dir: Path,
    mmseqs_bin: str,
    min_seq_id: float,
    coverage: float,
    cov_mode: int,
    sensitivity: float,
    threads: int,
) -> dict[str, Any]:
    sequences = preflight_synthetic_sequences()
    fasta_path = work_dir / "rna_u_preflight.fasta"
    lines = []
    for seq_id, sequence in sequences.items():
        lines.append(f">{seq_id}")
        lines.append(sequence)
    write_text_atomic(fasta_path, "\n".join(lines) + "\n")
    result = run_mmseqs_easy_cluster(
        fasta_path=fasta_path,
        output_prefix=work_dir / "rna_u_preflight_out",
        tmp_dir=work_dir / "rna_u_preflight_tmp",
        min_seq_id=min_seq_id,
        coverage=coverage,
        cov_mode=cov_mode,
        sensitivity=sensitivity,
        threads=threads,
        mmseqs_bin=mmseqs_bin,
    )
    pairs = parse_mmseqs_cluster_tsv(
        result["cluster_tsv_text"],
        input_sequence_ids=list(sequences),
    )
    interpretation = interpret_rna_u_preflight(pairs)
    interpretation["command"] = result["command"]
    interpretation["database_type_nucleotide"] = "Database type: Nucleotide" in (
        result["stdout"] + result["stderr"]
    )
    interpretation["accepts_acgu_fasta"] = (
        result["returncode"] == 0 and interpretation["database_type_nucleotide"]
    )
    interpretation["go"] = bool(
        interpretation["accepts_acgu_fasta"]
        and interpretation["identical_u_sequences_cluster"]
        and interpretation["near_identical_u_sequences_cluster"]
        and interpretation["u_treated_as_valid_nucleotide"]
        and interpretation["distant_sequence_not_clustered_with_u_pair"]
        and not interpretation["input_transcoded_u_to_t"]
        and not interpretation["derived_u_to_t_corpus_created"]
    )
    return interpretation


def run_s5c_sequence_clustering(
    *,
    config_path: Path,
    repo_root: Path | None = None,
    verify_hashes: bool = True,
    enforce_expected_counts: bool = True,
    repeat_for_determinism: bool = True,
    write_outputs: bool = True,
    installation_method: str = "already_present_or_homebrew",
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config = json.loads(_resolve(root, str(config_path)).read_text(encoding="utf-8"))
    enforce_authorised_parameters(config)
    s4_hashes = {}
    s5a_hashes = {}
    if verify_hashes:
        s4_hashes = _verify_hashes(root, config["expected_s4_hashes"])
        s5a_hashes = _verify_hashes(root, config["expected_s5a_hashes"])
        _assert_git_ls_files_data_empty(root)

    tool = discover_mmseqs_environment()
    if not tool["mmseqs_path"]:
        raise S5SequenceClusteringError(
            "MMseqs2 is not installed; S5C cannot run the authorised clustering command"
        )
    tool["tool_name"] = config.get("tool_name", "mmseqs2")
    tool["installation_method"] = installation_method
    tool["cd_hit_fallback_run"] = False

    output_dir = _resolve(root, config["output_dir"])
    work_dir = _resolve(root, config["mmseqs_work_dir"])
    work_dir.mkdir(parents=True, exist_ok=True)
    frozen_dedup = _resolve(root, config["corpus_dedup_csv"])
    if frozen_dedup.name != FROZEN_CORPUS_DEDUP_NAME:
        raise S5SequenceClusteringError("S5C must read frozen corpus_dedup.csv")

    min_seq_id = float(config["min_seq_id"])
    coverage = float(config["coverage"])
    cov_mode = int(config["cov_mode"])
    sensitivity = float(config["sensitivity"])
    threads = int(config.get("threads", 1))

    preflight = _run_rna_u_preflight(
        work_dir=work_dir / "preflight",
        mmseqs_bin=tool["mmseqs_path"],
        min_seq_id=min_seq_id,
        coverage=coverage,
        cov_mode=cov_mode,
        sensitivity=sensitivity,
        threads=threads,
    )
    if not preflight["go"]:
        raise S5SequenceClusteringError(
            "NO-GO: MMseqs2 RNA/U preflight failed; refusing to cluster the "
            "biological corpus or to create a U→T derived input. "
            + json.dumps(preflight, sort_keys=True)
        )

    corpus_rows = _read_csv(frozen_dedup)
    membership_rows = _read_csv(_resolve(root, config["membership_csv"]))
    expected = config.get("expected_counts") if enforce_expected_counts else None

    fasta_path = _resolve(root, config["fasta_relative"])
    assert_not_corpus_dedup_path(fasta_path)
    sequence_rows, _identity_map = project_unique_sequence_cores(corpus_rows)
    fasta_text = render_fasta(sequence_rows)
    if write_outputs:
        _write_fasta(fasta_path, fasta_text)

    run_results = []
    for run_name in ("run1", "run2")[: 2 if repeat_for_determinism else 1]:
        run_results.append(
            run_mmseqs_easy_cluster(
                fasta_path=fasta_path if write_outputs else _write_temp_fasta(work_dir, fasta_text),
                output_prefix=work_dir / run_name / "clusters",
                tmp_dir=work_dir / run_name / "tmp",
                min_seq_id=min_seq_id,
                coverage=coverage,
                cov_mode=cov_mode,
                sensitivity=sensitivity,
                threads=threads,
                mmseqs_bin=tool["mmseqs_path"],
            )
        )

    assembled = [
        assemble_clustering(
            corpus_rows=corpus_rows,
            mmseqs_cluster_tsv=item["cluster_tsv_text"],
            membership_rows=membership_rows,
            min_seq_id=min_seq_id,
            expected_counts=expected,
        )
        for item in run_results
    ]
    if len(assembled) == 2:
        compare_cluster_runs(assembled[0].cluster_rows, assembled[1].cluster_rows)
        if assembled[0].clustered_corpus != assembled[1].clustered_corpus:
            raise S5SequenceClusteringError(
                "NO-GO: clustered corpus rows differed across identical runs"
            )
        if assembled[0].cluster_summary_rows != assembled[1].cluster_summary_rows:
            raise S5SequenceClusteringError(
                "NO-GO: cluster_summary.csv differed across identical runs"
            )
        if assembled[0].sequence_rows != assembled[1].sequence_rows:
            raise S5SequenceClusteringError(
                "NO-GO: sequence clustering input differed across identical runs"
            )

    result = assembled[0]
    mmseqs_run = run_results[0]
    command = mmseqs_run["command"]
    report = build_s5c_report(
        result.diagnostics,
        tool=tool,
        preflight=preflight,
        command=command,
    )
    assert_no_sequence_leak(report, label="s5c_sequence_clustering_report.md")

    output_paths: dict[str, Path] = {
        "sequence_clustering_input_csv": output_dir / "sequence_clustering_input.csv",
        "sequence_clustering_input_fasta": fasta_path,
        "clusters_tsv": output_dir / "clusters.tsv",
        "corpus_clustered_csv": output_dir / "corpus_clustered.csv",
        "cluster_summary_csv": output_dir / "cluster_summary.csv",
        "sequence_scientific_identity_map_csv": output_dir
        / "sequence_scientific_identity_map.csv",
        "cluster_identity_audit_csv": output_dir / "cluster_identity_audit.csv",
        "ena_family_clustering_diagnostics_csv": output_dir
        / "ena_family_clustering_diagnostics.csv",
        "manifest_json": output_dir / "s5c_clustering_manifest.json",
        "report_md": output_dir / "s5c_sequence_clustering_report.md",
        "preflight_json": output_dir / "s5c_rna_u_preflight.json",
    }
    for path in output_paths.values():
        assert_not_corpus_dedup_path(path)

    if write_outputs:
        write_corpus_csv_atomic(
            output_paths["sequence_clustering_input_csv"],
            result.sequence_rows,
            columns=SEQUENCE_INPUT_COLUMNS,
        )
        _write_fasta(output_paths["sequence_clustering_input_fasta"], fasta_text)
        write_corpus_csv_atomic(
            output_paths["clusters_tsv"],
            result.cluster_rows,
            columns=CLUSTER_TSV_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["corpus_clustered_csv"],
            result.clustered_corpus,
            columns=CORPUS_CLUSTERED_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["cluster_summary_csv"],
            result.cluster_summary_rows,
            columns=CLUSTER_SUMMARY_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["sequence_scientific_identity_map_csv"],
            result.identity_map_rows,
            columns=SEQUENCE_IDENTITY_MAP_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["cluster_identity_audit_csv"],
            result.identity_audit_rows,
            columns=IDENTITY_AUDIT_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["ena_family_clustering_diagnostics_csv"],
            result.ena_family_rows,
            columns=ENA_FAMILY_DIAGNOSTIC_COLUMNS,
        )
        write_text_atomic(output_paths["report_md"], report)
        write_json_atomic(output_paths["preflight_json"], preflight)

    output_hashes = {}
    if write_outputs:
        output_hashes = {
            name: _payload_hash(path)
            for name, path in output_paths.items()
            if name not in {"manifest_json"}
        }
        manifest = {
            "ok": True,
            "milestone": config["milestone"],
            "frozen_s5a_input_hash": s5a_hashes.get("corpus_dedup_csv"),
            "s4_hashes": s4_hashes,
            "s5a_hashes": s5a_hashes,
            "mmseqs_path": tool["mmseqs_path"],
            "mmseqs_version": tool["mmseqs_version"],
            "installation_method": installation_method,
            "cd_hit_est_installed": tool["cd_hit_est_installed"],
            "cd_hit_fallback_run": False,
            "command": command,
            "parameters": {
                "min_seq_id": min_seq_id,
                "coverage": coverage,
                "cov_mode": cov_mode,
                "sensitivity": sensitivity,
                "sequence_field": config["sequence_field"],
                "threads": threads,
            },
            "sequence_count": result.diagnostics["n_distinct_sequence_core"],
            "scientific_identity_count": result.diagnostics["n_scientific_identities"],
            "deterministic_sort_convention": result.diagnostics["fasta_sort"],
            "cluster_id_convention": result.diagnostics["cluster_id_convention"],
            "representative_convention": result.diagnostics["representative_convention"],
            "sequence_id_format": config["sequence_id_format"],
            "clustering_population_policy": config["clustering_population_policy"],
            "repeat_for_determinism": repeat_for_determinism,
            "determinism_ok": True,
            "rna_u_preflight_go": preflight["go"],
            "output_hashes": output_hashes,
            "diagnostics": {
                key: value
                for key, value in result.diagnostics.items()
                if key != "largest_clusters"
            },
        }
        write_json_atomic(output_paths["manifest_json"], manifest)
        output_hashes["manifest_json"] = _payload_hash(output_paths["manifest_json"])

    if verify_hashes:
        s4_after = _verify_hashes(root, config["expected_s4_hashes"])
        s5a_after = _verify_hashes(root, config["expected_s5a_hashes"])
        if s4_after != s4_hashes:
            raise S5SequenceClusteringError("S4 hashes changed during S5C")
        if s5a_after != s5a_hashes:
            raise S5SequenceClusteringError("S5A freeze hashes changed during S5C")
        _assert_git_ls_files_data_empty(root)

    return {
        "ok": True,
        "diagnostics": result.diagnostics,
        "tool": tool,
        "preflight": preflight,
        "command": command,
        "s4_hashes": s4_hashes,
        "s5a_hashes": s5a_hashes,
        "output_paths": {name: str(path) for name, path in output_paths.items()},
        "output_hashes": output_hashes,
        "determinism_ok": True,
    }


def _write_temp_fasta(work_dir: Path, fasta_text: str) -> Path:
    path = work_dir / "sequence_clustering_input.fasta"
    _write_fasta(path, fasta_text)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="S5C 90% sequence-identity clustering with MMseqs2"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--skip-expected-counts",
        action="store_true",
        help="Do not enforce live S5A regression counts (synthetic use only)",
    )
    parser.add_argument(
        "--skip-hash-gate",
        action="store_true",
        help="Do not verify frozen S4/S5A hashes (synthetic use only)",
    )
    parser.add_argument(
        "--skip-determinism-repeat",
        action="store_true",
        help="Run MMseqs once (not authorised for the live scientific freeze)",
    )
    parser.add_argument(
        "--installation-method",
        default="homebrew_mmseqs2_18-8cc5c",
        help="How MMseqs2 was installed on this machine",
    )
    args = parser.parse_args()
    try:
        result = run_s5c_sequence_clustering(
            config_path=args.config,
            enforce_expected_counts=not args.skip_expected_counts,
            verify_hashes=not args.skip_hash_gate,
            repeat_for_determinism=not args.skip_determinism_repeat,
            installation_method=args.installation_method,
        )
    except (S5SequenceClusteringError, ScientificProposalError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "n_scientific_identities": result["diagnostics"]["n_scientific_identities"],
                "n_distinct_sequence_core": result["diagnostics"]["n_distinct_sequence_core"],
                "n_clusters": result["diagnostics"]["n_clusters"],
                "n_singleton_clusters": result["diagnostics"]["n_singleton_clusters"],
                "n_multi_sequence_clusters": result["diagnostics"][
                    "n_multi_sequence_clusters"
                ],
                "determinism_ok": result["determinism_ok"],
                "rna_u_preflight_go": result["preflight"]["go"],
                "output_hashes": result["output_hashes"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

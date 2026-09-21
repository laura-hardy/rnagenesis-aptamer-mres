#!/usr/bin/env python3
"""GLOBAL S5D — ENA cluster validation + CD-HIT fallback + adjudication.

Preserves the frozen MMseqs S5C candidate. Runs the plan-authorised
``cd-hit-est -c 0.9 -n 8`` fallback. Does not tune parameters, begin S6/S7,
balance, partition, commit, or push.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s4_scientific_common import (  # noqa: E402
    ScientificProposalError,
    assert_no_sequence_leak,
    split_pipe,
    write_json_atomic,
    write_text_atomic,
)
from adapters.s5_cdhit_clustering import (  # noqa: E402
    CLUSTER_SUMMARY_COLUMNS,
    CLUSTER_TSV_CDHIT_COLUMNS,
    CORPUS_CLUSTERED_CDHIT_COLUMNS,
    FINAL_CLUSTER_TSV_COLUMNS,
    S5CdHitError,
    assemble_cdhit_clustering,
    compare_cdhit_cluster_runs,
    discover_cdhit_environment,
    enforce_cdhit_parameters,
    interpret_cdhit_rna_u_preflight,
    parse_cdhit_clstr,
    preflight_synthetic_sequences,
    project_final_cluster_rows,
    render_fasta,
    representative_by_cluster_from_cdhit,
    representative_by_cluster_from_mmseqs,
    run_cdhit_est,
)
from adapters.s5_ena_clustering_validation import (  # noqa: E402
    CROSS_FAMILY_COLUMNS,
    FAMILY_REPORT_COLUMNS,
    METHOD_COMPARISON_COLUMNS,
    SINGLETON_AUDIT_COLUMNS,
    adjudicate_clustering_methods,
    compare_methods,
    validate_ena_families,
)
from adapters.s5_exact_dedup import _blank  # noqa: E402
from adapters.s5_sequence_clustering import (  # noqa: E402
    FROZEN_CORPUS_DEDUP_NAME,
    assert_not_corpus_dedup_path,
    project_unique_sequence_cores,
)
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402

DEFAULT_CONFIG = Path("config/global_s5d_ena_validation_cdhit.json")
S5C_PROTECTED = frozenset(
    {
        "clusters.tsv",
        "corpus_clustered.csv",
        "cluster_summary.csv",
        "s5c_clustering_manifest.json",
        "s5c_sequence_clustering_report.md",
        "corpus_dedup.csv",
        "exact_duplicate_membership.csv",
        "exact_duplicate_groups.csv",
        "s5a_exact_dedup_report.md",
        "s5b_validation_report.md",
        "s5b_validation_summary.json",
        "sequence_clustering_input.fasta",
        "sequence_clustering_input.csv",
        "ena_family_clustering_diagnostics.csv",
    }
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
            raise S5CdHitError(f"{name} SHA-256 mismatch: expected {digest}, got {got}")
    return observed


def _assert_git_ls_files_data_empty(root: Path) -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "data"], cwd=root, text=True
    ).strip()
    if tracked:
        raise S5CdHitError("git ls-files data is not empty")


def _assert_not_protected(path: Path) -> None:
    assert_not_corpus_dedup_path(path)
    if path.name in S5C_PROTECTED and "s5d_cdhit" not in path.parts:
        if path.name in {
            "clusters.tsv",
            "corpus_clustered.csv",
            "cluster_summary.csv",
            "s5c_clustering_manifest.json",
            "s5c_sequence_clustering_report.md",
            "corpus_dedup.csv",
        }:
            raise S5CdHitError(f"refusing to overwrite frozen S5 artefact {path}")


def _parse_mmseqs_m8(text: str) -> dict[tuple[str, str], dict[str, Any]]:
    alignments: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        query, target, pident, alnlen, qlen, tlen, qcov, tcov = parts[:8]
        identity = float(pident) / 100.0 if float(pident) > 1.5 else float(pident)
        qcov_v = float(qcov)
        tcov_v = float(tcov)
        if qcov_v > 1.5:
            qcov_v = qcov_v / 100.0
        if tcov_v > 1.5:
            tcov_v = tcov_v / 100.0
        alignments[(query, target)] = {
            "identity": identity,
            "aligned_length": int(float(alnlen)),
            "query_length": int(float(qlen)),
            "target_length": int(float(tlen)),
            "query_coverage": qcov_v,
            "target_coverage": tcov_v,
            "qcov": qcov_v,
            "tcov": tcov_v,
        }
    return alignments


def _run_mmseqs_pairwise(
    *,
    fasta_path: Path,
    output_path: Path,
    tmp_dir: Path,
    mmseqs_bin: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        mmseqs_bin,
        "easy-search",
        str(fasta_path),
        str(fasta_path),
        str(output_path),
        str(tmp_dir),
        "--search-type",
        "3",
        "--prefilter-mode",
        "2",
        "--threads",
        "1",
        "-e",
        "inf",
        "--max-seqs",
        "10000",
        "--min-seq-id",
        "0",
        "-c",
        "0",
        "--format-output",
        "query,target,pident,alnlen,qlen,tlen,qcov,tcov",
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0 or not output_path.is_file():
        raise S5CdHitError(
            "MMseqs pairwise diagnostic search failed: "
            + (completed.stderr or completed.stdout or f"exit {completed.returncode}")
        )
    return _parse_mmseqs_m8(output_path.read_text(encoding="utf-8"))


def _run_cdhit_preflight(work_dir: Path, cdhit_bin: str) -> dict[str, Any]:
    sequences = preflight_synthetic_sequences()
    fasta_path = work_dir / "rna_u_preflight.fasta"
    lines = []
    for seq_id, sequence in sequences.items():
        lines.append(f">{seq_id}")
        lines.append(sequence)
    write_text_atomic(fasta_path, "\n".join(lines) + "\n")
    result = run_cdhit_est(
        fasta_path=fasta_path,
        output_prefix=work_dir / "rna_u_preflight_out",
        cdhit_bin=cdhit_bin,
    )
    pairs = parse_cdhit_clstr(
        result["clstr_text"],
        input_sequence_ids=list(sequences),
    )
    interpretation = interpret_cdhit_rna_u_preflight(pairs)
    interpretation["command"] = result["command"]
    interpretation["stdout"] = result["stdout"]
    return interpretation


def _write_family_member_fasta(
    *,
    membership_rows: Sequence[Mapping[str, str]],
    clustered_corpus: Sequence[Mapping[str, str]],
    sequence_rows: Sequence[Mapping[str, str]],
    dest: Path,
    family_ids: Sequence[str],
) -> list[str]:
    identity_core = {
        _blank(row.get("scientific_identity_id")): _blank(row.get("sequence_core"))
        for row in clustered_corpus
    }
    cores: dict[str, str] = {}
    family_set = set(family_ids)
    for row in membership_rows:
        if _blank(row.get("source_db")) != "ena":
            continue
        family_id = _blank(row.get("ena_effective_near_duplicate_family_id"))
        if family_id not in family_set:
            continue
        identity = _blank(row.get("scientific_identity_id"))
        core = identity_core.get(identity) or _blank(row.get("sequence_core"))
        if core:
            cores[core] = core
    selected = [
        row for row in sequence_rows if row["sequence_core"] in cores
    ]
    write_text_atomic(dest, render_fasta(selected))
    return [row["sequence_id"] for row in selected]


def _build_overlap_report(
    *,
    s5a_report: str,
    overlap_matrix: Sequence[Mapping[str, str]],
    clustered: Sequence[Mapping[str, str]],
    summary: Sequence[Mapping[str, str]],
    mmseqs_metrics: Mapping[str, Any],
    cdhit_metrics: Mapping[str, Any],
    adjudication: Mapping[str, Any],
    structural: Mapping[str, Any],
) -> str:
    corroboration = Counter(
        _blank(row.get("corroboration_count")) for row in clustered
    )
    size_dist = Counter(int(row["n_distinct_sequences"]) for row in summary)
    unique_to_source: dict[str, int] = defaultdict(int)
    for row in clustered:
        sources = split_pipe(row.get("contributing_sources") or "")
        if len(sources) == 1:
            unique_to_source[sources[0]] += 1
    multi_target = sum(
        1 for row in summary if row.get("contains_multi_target_identical_core") == "true"
    )
    lines = [
        "# S5 overlap report",
        "",
        "Aggregate overlap after exact scientific deduplication and the accepted",
        "S5 clustering method. No biological sequences.",
        "",
        "## Exact-dedup source overlap",
        "",
    ]
    for row in overlap_matrix:
        if row["source_a"] == row["source_b"]:
            continue
        if int(row["n_shared_scientific_identities"]) == 0:
            continue
        lines.append(
            f"- {row['source_a']} ∩ {row['source_b']}: "
            f"{row['n_shared_scientific_identities']} identities, "
            f"{row['n_shared_duplicate_groups']} duplicate groups"
        )
    lines += [
        "",
        "## Corroboration distribution",
        "",
    ]
    for value, count in sorted(corroboration.items(), key=lambda item: int(item[0] or 0)):
        lines.append(f"- corroboration_count {value}: {count}")
    lines += [
        "",
        "## Final cluster count",
        "",
        f"- clusters: {structural.get('n_clusters')}",
        f"- singleton clusters: {structural.get('n_singleton_clusters')}",
        f"- multi-sequence clusters: {structural.get('n_multi_sequence_clusters')}",
        f"- largest cluster: {structural.get('largest_cluster_size')}",
        "",
        "## Cluster-size distribution",
        "",
    ]
    for size, count in sorted(size_dist.items()):
        lines.append(f"- size {size}: {count}")
    lines += [
        "",
        "## Sequences unique to sources",
        "",
    ]
    for source, count in sorted(unique_to_source.items()):
        lines.append(f"- {source}: {count} identities with a single contributing source")
    lines += [
        "",
        "## Multi-target sequence diagnostics",
        "",
        f"- clusters containing a multi-target identical core: {multi_target}",
        "",
        "## ENA validation",
        "",
        f"- multi-member families: {cdhit_metrics.get('n_multi_member_families_with_at_least_two_s5_members')}",
        f"- contained: {cdhit_metrics.get('n_multi_member_families_contained_in_one_cluster')}",
        f"- split: {cdhit_metrics.get('n_multi_member_families_split_across_gt1_cluster')}",
        f"- containment rate: {cdhit_metrics.get('family_containment_rate')}",
        f"- contained-family cores: {cdhit_metrics.get('n_contained_family_cores')}/{cdhit_metrics.get('n_multi_member_family_cores')}",
        f"- singleton ENA-internal conflicts: {cdhit_metrics.get('n_ena_internal_singleton_conflicts')}",
        "",
        "## Candidate MMseqs vs accepted fallback",
        "",
        f"- MMseqs contained families: {mmseqs_metrics.get('n_multi_member_families_contained_in_one_cluster')}",
        f"- CD-HIT contained families: {cdhit_metrics.get('n_multi_member_families_contained_in_one_cluster')}",
        f"- decision: {adjudication.get('decision')}",
        f"- reason: {adjudication.get('reason')}",
        "",
        "MMseqs remains the planned first attempt. CD-HIT is the authorised",
        "fallback used because MMseqs ENA-family recall was poor.",
        "",
    ]
    text = "\n".join(lines) + "\n"
    assert_no_sequence_leak(text, label="overlap_report.md")
    return text


def _s5d_report(
    *,
    tool: Mapping[str, Any],
    preflight: Mapping[str, Any],
    command: Sequence[str],
    mmseqs_metrics: Mapping[str, Any],
    cdhit_metrics: Mapping[str, Any],
    cdhit_structural: Mapping[str, Any],
    adjudication: Mapping[str, Any],
    family_rows: Sequence[Mapping[str, str]],
    comparison_rows: Sequence[Mapping[str, str]],
    hashes: Mapping[str, Any],
    used_comparison_fasta: bool,
) -> str:
    family_lines = []
    for row in family_rows:
        if int(row["n_s5_ena_membership_rows"]) < 2:
            continue
        family_lines.append(
            f"- {row['ena_family_id']}: cores={row['n_s5_ena_sequence_cores']} "
            f"clusters={row['n_clusters']} partition={row['cluster_size_partition']} "
            f"len={row['min_core_length']}/{row['median_core_length']}/{row['max_core_length']} "
            f"lengths_differ={row['lengths_differ']} "
            f"lev={row['levenshtein_graph_status']} "
            f"mmseqs_pair={row['mmseqs_pairwise_graph_status']} "
            f"source={row['source_definition_graph_status']} "
            f"reason={row['split_reason_summary']}"
        )
    comparison_lines = [
        f"- {row['metric']}: mmseqs={row['mmseqs']} cdhit={row['cdhit']}"
        for row in comparison_rows
    ]
    text = "\n".join(
        [
            "# Global S5D — ENA cluster validation + CD-HIT fallback",
            "",
            "S5D validates the frozen MMseqs S5C candidate against ENA",
            "`near_duplicate_family_id` and runs the plan-authorised CD-HIT",
            "fallback. It does not tune the 90% threshold, begin S6/S7,",
            "balance, partition, or overwrite S5C/S5A artefacts.",
            "",
            "## GO / NO-GO",
            "",
            f"- S5D execution succeeded: true",
            f"- final clustering method scientifically accepted: {adjudication.get('accept_cdhit')}",
            f"- decision: {adjudication.get('decision')}",
            f"- case: {adjudication.get('case')}",
            f"- reason: {adjudication.get('reason')}",
            "",
            "## CD-HIT environment",
            "",
            f"- path: {tool.get('cd_hit_est_path')}",
            f"- version: {tool.get('cd_hit_est_version')}",
            f"- installation: {tool.get('installation_method')}",
            f"- identity semantics: {tool.get('identity_semantics')}",
            f"- command: {' '.join(command)}",
            f"- comparison-only U→T used: {used_comparison_fasta}",
            "",
            "## RNA/U preflight",
            "",
            f"- accepts A/C/G/U FASTA: {preflight.get('accepts_acgu_fasta')}",
            f"- identical U sequences cluster: {preflight.get('identical_u_sequences_cluster')}",
            f"- near-identical U sequences cluster: {preflight.get('near_identical_u_sequences_cluster')}",
            f"- native U works: {preflight.get('native_u_works')}",
            f"- U internally equivalent to T: {preflight.get('u_internally_equivalent_to_t')}",
            f"- input transcoded U→T: {preflight.get('input_transcoded_u_to_t')}",
            f"- preflight GO: {preflight.get('go')}",
            "",
            "## CD-HIT cluster results",
            "",
            f"- clusters: {cdhit_structural.get('n_clusters')}",
            f"- singleton clusters: {cdhit_structural.get('n_singleton_clusters')}",
            f"- multi-sequence clusters: {cdhit_structural.get('n_multi_sequence_clusters')}",
            f"- largest cluster: {cdhit_structural.get('largest_cluster_size')}",
            f"- scientific identities retained: {cdhit_structural.get('scientific_identities_retained')}",
            f"- missing cluster_id: {cdhit_structural.get('n_missing_cluster_id')}",
            f"- all cores assigned: {cdhit_structural.get('all_cores_assigned')}",
            "",
            "## Sixteen-family reports",
            "",
            *family_lines,
            "",
            "## Method comparison",
            "",
            *comparison_lines,
            "",
            "## Integrity hashes",
            "",
            f"- S4 combined input: {hashes.get('s4_hashes', {}).get('combined_input')}",
            f"- S5A corpus_dedup: {hashes.get('s5a_hashes', {}).get('corpus_dedup_csv')}",
            f"- S5C clusters.tsv: {hashes.get('s5c_hashes', {}).get('clusters_tsv')}",
            "",
            "## Boundary",
            "",
            "- S4/S5A science unchanged",
            "- MMseqs candidate preserved",
            "- no threshold tuning",
            "- no manual family merges/splits",
            "- no scientific identities removed",
            "- no balancing, S6, FT/REF/EVAL, or train/val split",
            "- no commit/push",
            "- no data tracked",
            "",
        ]
    )
    assert_no_sequence_leak(text, label="s5d report")
    return text if text.endswith("\n") else text + "\n"


def run_s5d(
    *,
    config_path: Path,
    repo_root: Path | None = None,
    verify_hashes: bool = True,
    enforce_expected_counts: bool = True,
    repeat_for_determinism: bool = True,
    write_outputs: bool = True,
    installation_method: str = "homebrew_brewsci_bio_cd-hit_4.8.1",
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config = json.loads(_resolve(root, str(config_path)).read_text(encoding="utf-8"))
    enforce_cdhit_parameters(config)
    s4_hashes = {}
    s5a_hashes = {}
    s5c_hashes = {}
    if verify_hashes:
        s4_hashes = _verify_hashes(root, config["expected_s4_hashes"])
        s5a_hashes = _verify_hashes(root, config["expected_s5a_hashes"])
        s5c_hashes = _verify_hashes(root, config["expected_s5c_hashes"])
        _assert_git_ls_files_data_empty(root)

    tool = discover_cdhit_environment()
    if not tool["cd_hit_est_path"]:
        raise S5CdHitError("cd-hit-est is not installed")
    tool["installation_method"] = installation_method
    mmseqs_bin = shutil.which("mmseqs") or ""

    output_dir = _resolve(root, config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    frozen_dedup = _resolve(root, config["corpus_dedup_csv"])
    if frozen_dedup.name != FROZEN_CORPUS_DEDUP_NAME:
        raise S5CdHitError("S5D must read frozen corpus_dedup.csv")

    corpus_rows = _read_csv(frozen_dedup)
    membership_rows = _read_csv(_resolve(root, config["membership_csv"]))
    mmseqs_cluster_rows = _read_csv(_resolve(root, config["mmseqs_clusters_tsv"]))
    mmseqs_clustered = _read_csv(_resolve(root, config["mmseqs_corpus_clustered_csv"]))
    mmseqs_summary = _read_csv(_resolve(root, config["mmseqs_cluster_summary_csv"]))
    expected = config.get("expected_counts") if enforce_expected_counts else None

    sequence_rows, _identity_map = project_unique_sequence_cores(corpus_rows)
    fasta_text = render_fasta(sequence_rows)
    s5c_fasta = _resolve(root, config["s5c_fasta"])
    if fasta_text.encode("utf-8") != s5c_fasta.read_bytes():
        raise S5CdHitError("regenerated clustering FASTA drifted from frozen S5C FASTA")

    mmseqs_rep = representative_by_cluster_from_mmseqs(mmseqs_cluster_rows)
    work_dir = output_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    family_fasta = work_dir / "ena_multi_member_cores.fasta"
    mmseqs_val_preview = validate_ena_families(
        membership_rows=membership_rows,
        clustered_corpus=mmseqs_clustered,
        cluster_rows=mmseqs_cluster_rows,
        representative_by_cluster=mmseqs_rep,
        method_label="mmseqs",
    )
    family_ids = mmseqs_val_preview.metrics["multi_member_family_ids"]
    _write_family_member_fasta(
        membership_rows=membership_rows,
        clustered_corpus=mmseqs_clustered,
        sequence_rows=sequence_rows,
        dest=family_fasta,
        family_ids=family_ids,
    )
    mmseqs_alignments: dict[tuple[str, str], dict[str, Any]] | None
    try:
        if not mmseqs_bin:
            raise S5CdHitError("mmseqs missing for diagnostic search")
        mmseqs_alignments = _run_mmseqs_pairwise(
            fasta_path=family_fasta,
            output_path=work_dir / "ena_family_pairwise.m8",
            tmp_dir=work_dir / "mmseqs_pair_tmp",
            mmseqs_bin=mmseqs_bin,
        )
    except S5CdHitError:
        mmseqs_alignments = None

    mmseqs_validation = validate_ena_families(
        membership_rows=membership_rows,
        clustered_corpus=mmseqs_clustered,
        cluster_rows=mmseqs_cluster_rows,
        mmseqs_alignments=mmseqs_alignments,
        representative_by_cluster=mmseqs_rep,
        method_label="mmseqs",
    )
    mmseqs_structural = {
        "n_clusters": len(mmseqs_summary),
        "n_singleton_clusters": sum(
            1 for row in mmseqs_summary if int(row["n_distinct_sequences"]) == 1
        ),
        "n_multi_sequence_clusters": sum(
            1 for row in mmseqs_summary if int(row["n_distinct_sequences"]) > 1
        ),
        "largest_cluster_size": max(
            int(row["n_distinct_sequences"]) for row in mmseqs_summary
        ),
        "all_cores_assigned": True,
        "determinism_ok": True,
        "scientific_identities_retained": len(mmseqs_clustered),
        "n_missing_cluster_id": 0,
    }

    preflight_dir = work_dir / "preflight"
    preflight_dir.mkdir(parents=True, exist_ok=True)
    preflight = _run_cdhit_preflight(preflight_dir, tool["cd_hit_est_path"])
    used_comparison = False
    if not preflight["go"]:
        raise S5CdHitError(
            "NO-GO: cd-hit-est RNA/U preflight failed and comparison "
            "representation was not required because native U already failed "
            "the authorised clustering semantics. "
            + json.dumps({k: preflight[k] for k in preflight if k != "membership"})
        )

    fasta_path = output_dir / "sequence_clustering_input.fasta"
    if write_outputs:
        _assert_not_protected(fasta_path)
        write_text_atomic(fasta_path, fasta_text)

    run_results = []
    n_runs = 2 if repeat_for_determinism else 1
    if write_outputs:
        input_fasta = fasta_path
    else:
        input_fasta = work_dir / "input.fasta"
        write_text_atomic(input_fasta, fasta_text)
    for index in range(n_runs):
        prefix = output_dir / (
            "cdhit_output.fasta" if index == 0 else f"cdhit_output_run{index + 1}.fasta"
        )
        run_results.append(
            run_cdhit_est(
                fasta_path=input_fasta,
                output_prefix=prefix,
                cdhit_bin=tool["cd_hit_est_path"],
            )
        )
    assembled = [
        assemble_cdhit_clustering(
            corpus_rows=corpus_rows,
            clstr_text=item["clstr_text"],
            membership_rows=membership_rows,
            expected_counts=expected,
            used_comparison_fasta=used_comparison,
        )
        for item in run_results
    ]
    if len(assembled) == 2:
        compare_cdhit_cluster_runs(assembled[0].cluster_rows, assembled[1].cluster_rows)
        if assembled[0].clustered_corpus != assembled[1].clustered_corpus:
            raise S5CdHitError("NO-GO: clustered corpus rows differed across identical CD-HIT runs")
        if assembled[0].cluster_summary_rows != assembled[1].cluster_summary_rows:
            raise S5CdHitError("NO-GO: cluster_summary differed across identical CD-HIT runs")
    result = assembled[0]
    command = run_results[0]["command"]
    cdhit_rep = representative_by_cluster_from_cdhit(result.cluster_rows)
    cdhit_validation = validate_ena_families(
        membership_rows=membership_rows,
        clustered_corpus=result.clustered_corpus,
        cluster_rows=result.cluster_rows,
        mmseqs_alignments=mmseqs_alignments,
        representative_by_cluster=cdhit_rep,
        method_label="cdhit",
    )
    adjudication = adjudicate_clustering_methods(
        mmseqs_metrics=mmseqs_validation.metrics,
        cdhit_metrics=cdhit_validation.metrics,
        cdhit_mechanical_ok=bool(result.diagnostics.get("all_cores_assigned")),
        expected_families=int(config.get("expected_multi_member_families", 16)),
    )
    comparison_rows = compare_methods(
        mmseqs_validation.metrics,
        cdhit_validation.metrics,
        mmseqs_structural=mmseqs_structural,
        cdhit_structural=result.diagnostics,
    )
    hashes = {
        "s4_hashes": s4_hashes,
        "s5a_hashes": s5a_hashes,
        "s5c_hashes": s5c_hashes,
    }
    report = _s5d_report(
        tool=tool,
        preflight=preflight,
        command=command,
        mmseqs_metrics=mmseqs_validation.metrics,
        cdhit_metrics=cdhit_validation.metrics,
        cdhit_structural=result.diagnostics,
        adjudication=adjudication,
        family_rows=cdhit_validation.family_rows,
        comparison_rows=comparison_rows,
        hashes=hashes,
        used_comparison_fasta=used_comparison,
    )

    output_paths: dict[str, Path] = {
        "sequence_clustering_input_fasta": fasta_path,
        "cdhit_output_fasta": output_dir / "cdhit_output.fasta",
        "cdhit_output_clstr": output_dir / "cdhit_output.fasta.clstr",
        "clusters_cdhit_tsv": output_dir / "clusters_cdhit.tsv",
        "corpus_clustered_cdhit_csv": output_dir / "corpus_clustered_cdhit.csv",
        "cluster_summary_cdhit_csv": output_dir / "cluster_summary_cdhit.csv",
        "ena_family_diagnostics_cdhit_csv": output_dir
        / "ena_family_clustering_diagnostics_cdhit.csv",
        "ena_singleton_audit_cdhit_csv": output_dir / "ena_singleton_audit_cdhit.csv",
        "ena_family_diagnostics_mmseqs_csv": output_dir
        / "ena_family_clustering_diagnostics_mmseqs.csv",
        "ena_singleton_audit_mmseqs_csv": output_dir / "ena_singleton_audit_mmseqs.csv",
        "cross_family_mmseqs_csv": output_dir / "ena_cross_family_clusters_mmseqs.csv",
        "cross_family_cdhit_csv": output_dir / "ena_cross_family_clusters_cdhit.csv",
        "method_comparison_csv": output_dir / "clustering_method_comparison.csv",
        "method_comparison_parent_csv": output_dir.parent / "clustering_method_comparison.csv",
        "manifest_json": output_dir / "s5d_cdhit_manifest.json",
        "report_md": output_dir / "s5d_report.md",
        "preflight_json": output_dir / "s5d_rna_u_preflight.json",
    }
    for path in output_paths.values():
        _assert_not_protected(path)

    output_hashes: dict[str, str] = {}
    if write_outputs:
        write_corpus_csv_atomic(
            output_paths["clusters_cdhit_tsv"],
            result.cluster_rows,
            columns=CLUSTER_TSV_CDHIT_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["corpus_clustered_cdhit_csv"],
            result.clustered_corpus,
            columns=CORPUS_CLUSTERED_CDHIT_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["cluster_summary_cdhit_csv"],
            result.cluster_summary_rows,
            columns=CLUSTER_SUMMARY_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["ena_family_diagnostics_cdhit_csv"],
            cdhit_validation.family_rows,
            columns=FAMILY_REPORT_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["ena_singleton_audit_cdhit_csv"],
            cdhit_validation.singleton_rows,
            columns=SINGLETON_AUDIT_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["ena_family_diagnostics_mmseqs_csv"],
            mmseqs_validation.family_rows,
            columns=FAMILY_REPORT_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["ena_singleton_audit_mmseqs_csv"],
            mmseqs_validation.singleton_rows,
            columns=SINGLETON_AUDIT_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["cross_family_mmseqs_csv"],
            mmseqs_validation.cross_family_rows,
            columns=CROSS_FAMILY_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["cross_family_cdhit_csv"],
            cdhit_validation.cross_family_rows,
            columns=CROSS_FAMILY_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["method_comparison_csv"],
            comparison_rows,
            columns=METHOD_COMPARISON_COLUMNS,
        )
        write_corpus_csv_atomic(
            output_paths["method_comparison_parent_csv"],
            comparison_rows,
            columns=METHOD_COMPARISON_COLUMNS,
        )
        write_text_atomic(output_paths["report_md"], report)
        write_json_atomic(output_paths["preflight_json"], preflight)

        final_paths: dict[str, Path] = {}
        if adjudication["create_final_artefacts"]:
            final_dir = output_dir.parent
            final_paths = {
                "clusters_final_tsv": final_dir / "clusters_final.tsv",
                "corpus_clustered_final_csv": final_dir / "corpus_clustered_final.csv",
                "cluster_summary_final_csv": final_dir / "cluster_summary_final.csv",
                "final_manifest_json": final_dir / "s5_final_clustering_manifest.json",
                "overlap_report_md": final_dir / "overlap_report.md",
            }
            for path in final_paths.values():
                _assert_not_protected(path)
            write_corpus_csv_atomic(
                final_paths["clusters_final_tsv"],
                project_final_cluster_rows(result.cluster_rows),
                columns=FINAL_CLUSTER_TSV_COLUMNS,
            )
            write_corpus_csv_atomic(
                final_paths["corpus_clustered_final_csv"],
                result.clustered_corpus,
                columns=CORPUS_CLUSTERED_CDHIT_COLUMNS,
            )
            write_corpus_csv_atomic(
                final_paths["cluster_summary_final_csv"],
                result.cluster_summary_rows,
                columns=CLUSTER_SUMMARY_COLUMNS,
            )
            overlap_matrix = _read_csv(_resolve(root, config["overlap_matrix_csv"]))
            overlap_report = _build_overlap_report(
                s5a_report="",
                overlap_matrix=overlap_matrix,
                clustered=result.clustered_corpus,
                summary=result.cluster_summary_rows,
                mmseqs_metrics=mmseqs_validation.metrics,
                cdhit_metrics=cdhit_validation.metrics,
                adjudication=adjudication,
                structural=result.diagnostics,
            )
            write_text_atomic(final_paths["overlap_report_md"], overlap_report)
            final_manifest = {
                "final_clustering_method": "cd-hit-est",
                "reason": "mmseqs_poor_ena_family_recall",
                "mmseqs_metrics": {
                    key: mmseqs_validation.metrics[key]
                    for key in mmseqs_validation.metrics
                    if key
                    not in {
                        "multi_member_family_ids",
                        "contained_family_ids",
                        "split_family_ids",
                        "incompatible_family_ids",
                    }
                },
                "cdhit_metrics": {
                    key: cdhit_validation.metrics[key]
                    for key in cdhit_validation.metrics
                    if key
                    not in {
                        "multi_member_family_ids",
                        "contained_family_ids",
                        "split_family_ids",
                        "incompatible_family_ids",
                    }
                },
            }
            write_json_atomic(final_paths["final_manifest_json"], final_manifest)
        output_hashes = {
            name: _payload_hash(path)
            for name, path in {**output_paths, **final_paths}.items()
            if name != "manifest_json" and path.exists()
        }
        manifest = {
            "ok": True,
            "milestone": config["milestone"],
            "s4_hashes": s4_hashes,
            "s5a_hashes": s5a_hashes,
            "s5c_hashes": s5c_hashes,
            "cd_hit_est_path": tool["cd_hit_est_path"],
            "cd_hit_est_version": tool["cd_hit_est_version"],
            "installation_method": installation_method,
            "identity_semantics": tool["identity_semantics"],
            "command": command,
            "used_comparison_u_to_t": used_comparison,
            "determinism_ok": True,
            "rna_u_preflight_go": preflight["go"],
            "adjudication": adjudication,
            "mmseqs_ena_metrics": mmseqs_validation.metrics,
            "cdhit_ena_metrics": cdhit_validation.metrics,
            "cdhit_structural": {
                key: result.diagnostics.get(key)
                for key in (
                    "n_clusters",
                    "n_singleton_clusters",
                    "n_multi_sequence_clusters",
                    "largest_cluster_size",
                    "n_scientific_identities",
                    "scientific_identities_retained",
                    "n_missing_cluster_id",
                    "all_cores_assigned",
                    "cluster_size_distribution",
                )
            },
            "output_hashes": output_hashes,
            "final_artefacts_created": bool(adjudication["create_final_artefacts"]),
        }
        write_json_atomic(output_paths["manifest_json"], manifest)
        output_hashes["manifest_json"] = _payload_hash(output_paths["manifest_json"])

    if verify_hashes:
        _verify_hashes(root, config["expected_s4_hashes"])
        _verify_hashes(root, config["expected_s5a_hashes"])
        _verify_hashes(root, config["expected_s5c_hashes"])
        _assert_git_ls_files_data_empty(root)
        if _payload_hash(frozen_dedup) != s5a_hashes.get("corpus_dedup_csv", _payload_hash(frozen_dedup)):
            raise S5CdHitError("corpus_dedup.csv changed during S5D")

    return {
        "ok": True,
        "adjudication": adjudication,
        "mmseqs_metrics": mmseqs_validation.metrics,
        "cdhit_metrics": cdhit_validation.metrics,
        "cdhit_diagnostics": result.diagnostics,
        "tool": tool,
        "preflight": preflight,
        "command": command,
        "s4_hashes": s4_hashes,
        "s5a_hashes": s5a_hashes,
        "s5c_hashes": s5c_hashes,
        "output_hashes": output_hashes,
        "used_comparison_u_to_t": used_comparison,
        "determinism_ok": True,
        "report": report,
        "comparison_rows": comparison_rows,
        "mmseqs_family_rows": mmseqs_validation.family_rows,
        "cdhit_family_rows": cdhit_validation.family_rows,
        "mmseqs_singleton_rows": mmseqs_validation.singleton_rows,
        "cdhit_singleton_rows": cdhit_validation.singleton_rows,
        "mmseqs_structural": mmseqs_structural,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="S5D ENA validation and CD-HIT fallback")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--skip-expected-counts", action="store_true")
    parser.add_argument("--skip-hash-gate", action="store_true")
    parser.add_argument("--skip-determinism-repeat", action="store_true")
    parser.add_argument(
        "--installation-method",
        default="homebrew_brewsci_bio_cd-hit_4.8.1",
    )
    args = parser.parse_args()
    try:
        result = run_s5d(
            config_path=args.config,
            enforce_expected_counts=not args.skip_expected_counts,
            verify_hashes=not args.skip_hash_gate,
            repeat_for_determinism=not args.skip_determinism_repeat,
            installation_method=args.installation_method,
        )
    except (S5CdHitError, ScientificProposalError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    payload = {
        "ok": True,
        "decision": result["adjudication"]["decision"],
        "case": result["adjudication"]["case"],
        "accept_cdhit": result["adjudication"]["accept_cdhit"],
        "n_clusters": result["cdhit_diagnostics"]["n_clusters"],
        "mmseqs_contained": result["mmseqs_metrics"][
            "n_multi_member_families_contained_in_one_cluster"
        ],
        "cdhit_contained": result["cdhit_metrics"][
            "n_multi_member_families_contained_in_one_cluster"
        ],
        "determinism_ok": result["determinism_ok"],
        "used_comparison_u_to_t": result["used_comparison_u_to_t"],
        "output_hashes": result["output_hashes"],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

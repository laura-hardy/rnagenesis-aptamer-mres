#!/usr/bin/env python3
"""Run RNAGenesis repository aptamer evaluation and expose returned metrics."""

from __future__ import annotations

import argparse
import csv
import json
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REF_SEQ = (
    "TCCAGCACTCCACGCATAACGGCGGTGGGTGGGTTGTTGTGGGAGGGGGAGGGGGAGTTATGCGTGCTACCGTGAA"
)
VERIFY_TOLERANCE = 1e-9


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run RNAGenesis test_wrap_aptamer evaluation on raw seqs_wo_guidance "
            "output and save metrics the upstream CLI returns silently."
        )
    )
    parser.add_argument(
        "--candidate-file",
        type=Path,
        required=True,
        help="Path to raw RNAGenesis seqs_wo_guidance_*.txt candidate file.",
    )
    parser.add_argument(
        "--rnagenesis-repo",
        type=Path,
        default=Path.home() / "RNAGenesis",
        help="Path to the RNAGenesis repository (default: ~/RNAGenesis).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/phase2_3_repo_evaluation"),
        help="Base output directory under the project repo.",
    )
    parser.add_argument(
        "--run-label",
        default=None,
        help="Label for output files (default: candidate filename stem).",
    )
    parser.add_argument(
        "--threshold-a",
        type=float,
        default=80.0,
        help="Structure similarity threshold (default: 80.0).",
    )
    parser.add_argument(
        "--threshold-b",
        type=float,
        default=2.0,
        help="MFE difference threshold in kcal/mol (default: 2.0).",
    )
    parser.add_argument(
        "--factor",
        type=float,
        default=2.0,
        help="bp_distance conversion factor (default: 2.0).",
    )
    parser.add_argument(
        "--write-per-sequence",
        action="store_true",
        help="Write per-sequence metrics CSV under per_sequence/.",
    )
    return parser.parse_args()


def count_raw_lines(candidate_file: Path) -> int:
    """Count non-empty lines in the candidate file."""
    count = 0
    with candidate_file.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def import_repo_functions(rnagenesis_repo: Path) -> tuple[Any, ...]:
    """Add RNAGenesis to sys.path and import evaluation helpers."""
    repo_path = rnagenesis_repo.expanduser().resolve()
    if not repo_path.is_dir():
        raise FileNotFoundError(f"RNAGenesis repo not found: {repo_path}")

    repo_str = str(repo_path)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)

    from test_wrap_aptamer import (  # noqa: PLC0415
        batch_analysis,
        get_gen_seqs,
        run_rna_analysis,
        threshold_analysis,
    )

    return get_gen_seqs, batch_analysis, threshold_analysis, run_rna_analysis


def get_git_commit(repo_path: Path) -> str | None:
    """Return short git commit hash for repo_path, or None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def stats(values: list[float]) -> dict[str, float | None]:
    """Return mean/min/max for a numeric list."""
    if not values:
        return {"mean": None, "min": None, "max": None}
    return {
        "mean": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
    }


def verify_against_run_rna_analysis(
    run_rna_analysis: Any,
    candidate_file: Path,
    threshold_a: float,
    threshold_b: float,
    factor: float,
    prop_similarity: float,
    prop_mfe: float,
) -> None:
    """Ensure run_rna_analysis agrees with wrapper-computed proportions."""
    repo_prop_similarity, repo_prop_mfe = run_rna_analysis(
        str(candidate_file),
        threshold_A=threshold_a,
        threshold_B=threshold_b,
        factor=factor,
    )
    if abs(repo_prop_similarity - prop_similarity) > VERIFY_TOLERANCE:
        raise RuntimeError(
            "prop_similarity mismatch: "
            f"wrapper={prop_similarity}, run_rna_analysis={repo_prop_similarity}"
        )
    if abs(repo_prop_mfe - prop_mfe) > VERIFY_TOLERANCE:
        raise RuntimeError(
            "prop_mfe mismatch: "
            f"wrapper={prop_mfe}, run_rna_analysis={repo_prop_mfe}"
        )


def build_summary(
    *,
    candidate_file: Path,
    run_label: str,
    rnagenesis_repo: Path,
    threshold_a: float,
    threshold_b: float,
    factor: float,
    raw_line_count: int,
    candidate_count: int,
    ref_structure: str,
    ref_mfe: float,
    prop_similarity: float,
    prop_mfe: float,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the evaluation summary payload."""
    similarities = [float(r["similarity"]) for r in results]
    mfes = [float(r["mfe"]) for r in results]
    mfe_diffs = [float(r["mfe_diff"]) for r in results]

    return {
        "candidate_file": str(candidate_file.resolve()),
        "run_label": run_label,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "rnagenesis_repo": str(rnagenesis_repo.resolve()),
        "rnagenesis_commit": get_git_commit(rnagenesis_repo),
        "threshold_a": threshold_a,
        "threshold_b": threshold_b,
        "factor": factor,
        "raw_line_count": raw_line_count,
        "candidate_count_after_preprocessing": candidate_count,
        "reference_sequence": REF_SEQ,
        "reference_structure": ref_structure,
        "reference_mfe": ref_mfe,
        "prop_similarity": prop_similarity,
        "prop_mfe": prop_mfe,
        "similarity_stats": stats(similarities),
        "mfe_stats": stats(mfes),
        "mfe_diff_stats": stats(mfe_diffs),
        "run_rna_analysis_verified": True,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, summary: dict[str, Any], output_paths: dict[str, Path]) -> None:
    sim = summary["similarity_stats"]
    mfe = summary["mfe_stats"]
    diff = summary["mfe_diff_stats"]

    lines = [
        f"# RNAGenesis repo aptamer evaluation — {summary['run_label']}",
        "",
        f"**Timestamp (UTC):** {summary['timestamp_utc']}",
        f"**Host:** {summary['host']}",
        "",
        "## Input",
        "",
        f"- Candidate file: `{summary['candidate_file']}`",
        f"- Raw lines: {summary['raw_line_count']}",
        f"- Candidates after repo preprocessing: {summary['candidate_count_after_preprocessing']}",
        f"- RNAGenesis repo: `{summary['rnagenesis_repo']}`",
        f"- RNAGenesis commit: `{summary['rnagenesis_commit']}`",
        "",
        "## Parameters",
        "",
        f"- threshold_a: {summary['threshold_a']}",
        f"- threshold_b: {summary['threshold_b']}",
        f"- factor: {summary['factor']}",
        "",
        "## Reference",
        "",
        f"- Sequence: `{summary['reference_sequence']}`",
        f"- MFE: {summary['reference_mfe']:.6f} kcal/mol",
        f"- Structure: `{summary['reference_structure']}`",
        "",
        "## Aggregate metrics",
        "",
        f"- prop_similarity (>= {summary['threshold_a']}): **{summary['prop_similarity']:.6f}%**",
        f"- prop_mfe (<= {summary['threshold_b']} kcal/mol): **{summary['prop_mfe']:.6f}%**",
        "",
        "## Per-sequence summary stats",
        "",
        "### Similarity",
        f"- mean: {sim['mean']:.6f}" if sim["mean"] is not None else "- mean: n/a",
        f"- min: {sim['min']:.6f}" if sim["min"] is not None else "- min: n/a",
        f"- max: {sim['max']:.6f}" if sim["max"] is not None else "- max: n/a",
        "",
        "### MFE",
        f"- mean: {mfe['mean']:.6f}" if mfe["mean"] is not None else "- mean: n/a",
        f"- min: {mfe['min']:.6f}" if mfe["min"] is not None else "- min: n/a",
        f"- max: {mfe['max']:.6f}" if mfe["max"] is not None else "- max: n/a",
        "",
        "### MFE difference",
        f"- mean: {diff['mean']:.6f}" if diff["mean"] is not None else "- mean: n/a",
        f"- min: {diff['min']:.6f}" if diff["min"] is not None else "- min: n/a",
        f"- max: {diff['max']:.6f}" if diff["max"] is not None else "- max: n/a",
        "",
        "## Outputs",
        "",
        f"- JSON: `{output_paths['json']}`",
        f"- Markdown: `{output_paths['markdown']}`",
        f"- Log: `{output_paths['log']}`",
    ]
    if "per_sequence" in output_paths:
        lines.append(f"- Per-sequence CSV: `{output_paths['per_sequence']}`")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_log(path: Path, summary: dict[str, Any], output_paths: dict[str, Path]) -> None:
    lines = [
        "RNAGenesis repo aptamer evaluation",
        "==================================",
        f"run_label: {summary['run_label']}",
        f"timestamp_utc: {summary['timestamp_utc']}",
        f"host: {summary['host']}",
        f"candidate_file: {summary['candidate_file']}",
        f"rnagenesis_repo: {summary['rnagenesis_repo']}",
        f"rnagenesis_commit: {summary['rnagenesis_commit']}",
        f"threshold_a: {summary['threshold_a']}",
        f"threshold_b: {summary['threshold_b']}",
        f"factor: {summary['factor']}",
        f"raw_line_count: {summary['raw_line_count']}",
        f"candidate_count_after_preprocessing: {summary['candidate_count_after_preprocessing']}",
        f"reference_mfe: {summary['reference_mfe']:.6f}",
        f"reference_structure: {summary['reference_structure']}",
        f"prop_similarity: {summary['prop_similarity']:.6f}",
        f"prop_mfe: {summary['prop_mfe']:.6f}",
        f"run_rna_analysis_verified: {summary['run_rna_analysis_verified']}",
        "",
        "Output files:",
        f"  json: {output_paths['json']}",
        f"  markdown: {output_paths['markdown']}",
        f"  log: {output_paths['log']}",
    ]
    if "per_sequence" in output_paths:
        lines.append(f"  per_sequence_csv: {output_paths['per_sequence']}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_per_sequence_csv(path: Path, results: list[dict[str, Any]]) -> None:
    fieldnames = [
        "index",
        "full_sequence",
        "structure",
        "mfe",
        "similarity",
        "mfe_diff",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, row in enumerate(results):
            writer.writerow(
                {
                    "index": index,
                    "full_sequence": row["seq"],
                    "structure": row["structure"],
                    "mfe": row["mfe"],
                    "similarity": row["similarity"],
                    "mfe_diff": row["mfe_diff"],
                }
            )


def run_evaluation(args: argparse.Namespace) -> dict[str, Any]:
    candidate_file = args.candidate_file.expanduser().resolve()
    if not candidate_file.is_file():
        raise FileNotFoundError(f"Candidate file not found: {candidate_file}")

    rnagenesis_repo = args.rnagenesis_repo.expanduser().resolve()
    run_label = args.run_label or candidate_file.stem

    output_dir = args.output_dir.expanduser().resolve()
    summaries_dir = output_dir / "summaries"
    logs_dir = output_dir / "logs"
    per_sequence_dir = output_dir / "per_sequence"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    get_gen_seqs, batch_analysis, threshold_analysis, run_rna_analysis = (
        import_repo_functions(rnagenesis_repo)
    )

    raw_line_count = count_raw_lines(candidate_file)
    candidate_seqs = get_gen_seqs(str(candidate_file))
    candidate_count = len(candidate_seqs)

    ref_structure, ref_mfe, results = batch_analysis(
        candidate_seqs, REF_SEQ, args.factor
    )
    prop_similarity, prop_mfe = threshold_analysis(
        results, args.threshold_a, args.threshold_b
    )

    verify_against_run_rna_analysis(
        run_rna_analysis,
        candidate_file,
        args.threshold_a,
        args.threshold_b,
        args.factor,
        prop_similarity,
        prop_mfe,
    )

    summary = build_summary(
        candidate_file=candidate_file,
        run_label=run_label,
        rnagenesis_repo=rnagenesis_repo,
        threshold_a=args.threshold_a,
        threshold_b=args.threshold_b,
        factor=args.factor,
        raw_line_count=raw_line_count,
        candidate_count=candidate_count,
        ref_structure=ref_structure,
        ref_mfe=float(ref_mfe),
        prop_similarity=float(prop_similarity),
        prop_mfe=float(prop_mfe),
        results=results,
    )

    output_paths: dict[str, Path] = {
        "json": summaries_dir / f"{run_label}_repo_eval_summary.json",
        "markdown": summaries_dir / f"{run_label}_repo_eval_summary.md",
        "log": logs_dir / f"{run_label}_repo_eval.log",
    }

    if args.write_per_sequence:
        per_sequence_dir.mkdir(parents=True, exist_ok=True)
        output_paths["per_sequence"] = (
            per_sequence_dir / f"{run_label}_repo_eval_per_sequence.csv"
        )
        write_per_sequence_csv(output_paths["per_sequence"], results)

    write_json(output_paths["json"], summary)
    write_markdown(output_paths["markdown"], summary, output_paths)
    write_log(output_paths["log"], summary, output_paths)

    print(f"n={candidate_count}")
    print(f"ref_mfe={summary['reference_mfe']:.6f}")
    print(f"prop_similarity={summary['prop_similarity']:.6f}")
    print(f"prop_mfe={summary['prop_mfe']:.6f}")
    print(f"json={output_paths['json']}")
    print(f"markdown={output_paths['markdown']}")
    print(f"log={output_paths['log']}")
    if "per_sequence" in output_paths:
        print(f"per_sequence_csv={output_paths['per_sequence']}")

    return summary


def main() -> None:
    args = parse_args()
    run_evaluation(args)


if __name__ == "__main__":
    main()

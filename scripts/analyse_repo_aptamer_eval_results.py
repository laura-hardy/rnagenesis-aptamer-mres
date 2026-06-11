#!/usr/bin/env python3
"""Summarise and visualise Stage 2.3 RNAGenesis repository aptamer evaluation results."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import warnings
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import seaborn as sns

    HAS_SEABORN = True
except ImportError:
    HAS_SEABORN = False

RUN_LABELS = [
    "medium_test_16",
    "baseline_30k_chunk1",
    "baseline_30080_full",
]

SUMMARY_SUFFIX = "_repo_eval_summary.json"
PER_SEQUENCE_SUFFIX = "_repo_eval_per_sequence.csv"

REF_SEQUENCE = (
    "TCCAGCACTCCACGCATAACGGCGGTGGGTGGGTTGTTGTGGGAGGGGGAGGGGGAGTTATGCGTGCTACCGTGAA"
)
REF_STRUCTURE = (
    ".((..(.((((.(.(((((((((.........))))))))).).)))))..))(((((.......))).))....."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyse Stage 2.3 RNAGenesis repository aptamer evaluation summaries "
            "and write plots, tables, and an Aim 1 markdown report."
        )
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results/phase2_3_repo_evaluation"),
        help="Directory containing summaries/, per_sequence/, and inputs/.",
    )
    parser.add_argument(
        "--raw-baseline-dir",
        type=Path,
        default=Path("results/phase4_1_unadapted_rnagenesis_30k/raw"),
        help="Directory of raw seqs_wo_guidance_*.txt baseline generation files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/phase2_3_repo_evaluation/analysis"),
        help="Output directory for plots, tables, and the markdown report.",
    )
    return parser.parse_args()


def warn_missing(path: Path, context: str) -> None:
    warnings.warn(f"{context}: file not found — {path}", stacklevel=2)


def load_summary(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        warn_missing(path, "Summary JSON")
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def flatten_summary(summary: dict[str, Any]) -> dict[str, Any]:
    sim = summary.get("similarity_stats", {})
    mfe = summary.get("mfe_stats", {})
    diff = summary.get("mfe_diff_stats", {})
    return {
        "run_label": summary.get("run_label"),
        "n": summary.get("candidate_count_after_preprocessing"),
        "threshold_a": summary.get("threshold_a"),
        "threshold_b": summary.get("threshold_b"),
        "factor": summary.get("factor"),
        "prop_similarity": summary.get("prop_similarity"),
        "prop_mfe": summary.get("prop_mfe"),
        "similarity_mean": sim.get("mean"),
        "similarity_min": sim.get("min"),
        "similarity_max": sim.get("max"),
        "mfe_mean": mfe.get("mean"),
        "mfe_min": mfe.get("min"),
        "mfe_max": mfe.get("max"),
        "mfe_diff_mean": diff.get("mean"),
        "mfe_diff_min": diff.get("min"),
        "mfe_diff_max": diff.get("max"),
        "reference_mfe": summary.get("reference_mfe"),
        "reference_structure": summary.get("reference_structure"),
        "reference_sequence": summary.get("reference_sequence"),
    }


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "run_label",
        "n",
        "threshold_a",
        "threshold_b",
        "factor",
        "prop_similarity",
        "prop_mfe",
        "similarity_mean",
        "similarity_min",
        "similarity_max",
        "mfe_mean",
        "mfe_min",
        "mfe_max",
        "mfe_diff_mean",
        "mfe_diff_min",
        "mfe_diff_max",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def fmt_float(value: Any, digits: int = 6) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}"


def fmt_pct(value: Any, digits: int = 6) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}%"


def write_summary_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "run_label",
        "n",
        "threshold_a",
        "threshold_b",
        "factor",
        "prop_similarity",
        "prop_mfe",
        "similarity_mean",
        "similarity_min",
        "similarity_max",
        "mfe_mean",
        "mfe_min",
        "mfe_max",
        "mfe_diff_mean",
        "mfe_diff_min",
        "mfe_diff_max",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        cells = [
            str(row.get("run_label", "")),
            str(row.get("n", "")),
            fmt_float(row.get("threshold_a"), 1),
            fmt_float(row.get("threshold_b"), 1),
            fmt_float(row.get("factor"), 1),
            fmt_pct(row.get("prop_similarity")),
            fmt_pct(row.get("prop_mfe")),
            fmt_float(row.get("similarity_mean")),
            fmt_float(row.get("similarity_min")),
            fmt_float(row.get("similarity_max")),
            fmt_float(row.get("mfe_mean")),
            fmt_float(row.get("mfe_min")),
            fmt_float(row.get("mfe_max")),
            fmt_float(row.get("mfe_diff_mean")),
            fmt_float(row.get("mfe_diff_min")),
            fmt_float(row.get("mfe_diff_max")),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_per_sequence_csv(path: Path) -> list[dict[str, str]] | None:
    if not path.is_file():
        warn_missing(path, "Per-sequence CSV")
        return None
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def collect_raw_sequence_lengths(raw_dir: Path) -> list[int]:
    lengths: list[int] = []
    if not raw_dir.is_dir():
        warn_missing(raw_dir, "Raw baseline directory")
        return lengths

    raw_files = sorted(raw_dir.glob("*.txt"))
    if not raw_files:
        warnings.warn(f"No .txt files found in {raw_dir}", stacklevel=2)
        return lengths

    for raw_file in raw_files:
        with raw_file.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    lengths.append(len(stripped))
    return lengths


def apply_plot_style() -> None:
    if HAS_SEABORN:
        sns.set_theme(style="whitegrid", context="notebook")
    else:
        plt.style.use("ggplot")


def plot_threshold_pass_rates(
    rows: list[dict[str, Any]],
    output_path: Path,
) -> bool:
    labels = [row["run_label"] for row in rows]
    if not labels:
        return False

    similarity = [float(row["prop_similarity"]) for row in rows]
    mfe_pass = [float(row["prop_mfe"]) for row in rows]

    x = range(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(9, 5))

    bars_sim = ax.bar(
        [i - width / 2 for i in x],
        similarity,
        width,
        label="prop_similarity (≥ threshold_a)",
        color="#4C78A8",
    )
    bars_mfe = ax.bar(
        [i + width / 2 for i in x],
        mfe_pass,
        width,
        label="prop_mfe (≤ threshold_b)",
        color="#F58518",
    )

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("Pass rate (%)")
    ax.set_title("Repository evaluation threshold pass rates by run")
    ax.legend(loc="upper right")

    for bars in (bars_sim, bars_mfe):
        for bar in bars:
            height = bar.get_height()
            ax.annotate(
                f"{height:.2f}%",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return True


def plot_full_baseline_metric_ranges(
    full_row: dict[str, Any],
    output_path: Path,
) -> bool:
    metrics = [
        ("Similarity", "similarity_min", "similarity_mean", "similarity_max"),
        ("MFE (kcal/mol)", "mfe_min", "mfe_mean", "mfe_max"),
        ("MFE diff (kcal/mol)", "mfe_diff_min", "mfe_diff_mean", "mfe_diff_max"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    colors = {"min": "#9ECAE1", "mean": "#3182BD", "max": "#08519C"}

    for ax, (title, min_key, mean_key, max_key) in zip(axes, metrics, strict=True):
        values = {
            "min": float(full_row[min_key]),
            "mean": float(full_row[mean_key]),
            "max": float(full_row[max_key]),
        }
        bars = ax.bar(list(values.keys()), list(values.values()), color=list(colors.values()))
        ax.set_title(title)
        ax.set_ylabel("Value")
        for bar, label in zip(bars, values.keys(), strict=True):
            ax.annotate(
                f"{values[label]:.3f}",
                xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    fig.suptitle(f"baseline_30080_full metric ranges (n={full_row['n']})")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return True


def plot_length_histogram(lengths: list[int], output_path: Path) -> bool:
    if not lengths:
        return False

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(lengths, bins=30, color="#72B7B2", edgecolor="white")
    ax.set_xlabel("Raw line length (characters)")
    ax.set_ylabel("Count")
    ax.set_title(
        f"Raw baseline sequence line-length distribution (n={len(lengths):,} lines)"
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return True


def plot_per_sequence_histogram(
    values: list[float],
    column_name: str,
    output_path: Path,
    run_label: str,
) -> bool:
    if not values:
        return False

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(values, bins=12, color="#B279A2", edgecolor="white")
    ax.set_xlabel(column_name)
    ax.set_ylabel("Count")
    ax.set_title(f"{run_label}: {column_name} distribution (n={len(values)})")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return True


def results_table_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Run | n | prop_similarity | prop_mfe |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['run_label']} | {row['n']} | "
            f"{fmt_pct(row['prop_similarity'])} | {fmt_pct(row['prop_mfe'])} |"
        )
    return "\n".join(lines)


def full_baseline_stats_markdown(full_row: dict[str, Any]) -> str:
    return "\n".join(
        [
            "| Metric | mean | min | max |",
            "| --- | ---: | ---: | ---: |",
            f"| Similarity | {fmt_float(full_row['similarity_mean'])} | "
            f"{fmt_float(full_row['similarity_min'])} | "
            f"{fmt_float(full_row['similarity_max'])} |",
            f"| MFE (kcal/mol) | {fmt_float(full_row['mfe_mean'])} | "
            f"{fmt_float(full_row['mfe_min'])} | "
            f"{fmt_float(full_row['mfe_max'])} |",
            f"| MFE difference (kcal/mol) | {fmt_float(full_row['mfe_diff_mean'])} | "
            f"{fmt_float(full_row['mfe_diff_min'])} | "
            f"{fmt_float(full_row['mfe_diff_max'])} |",
        ]
    )


def write_aim1_report(
    path: Path,
    rows: list[dict[str, Any]],
    full_row: dict[str, Any] | None,
    plot_paths: list[tuple[str, Path]],
    per_sequence_note: str,
) -> None:
    ref_mfe = full_row.get("reference_mfe") if full_row else None
    ref_structure = full_row.get("reference_structure") or REF_STRUCTURE
    ref_sequence = full_row.get("reference_sequence") or REF_SEQUENCE

    figure_lines = [
        f"- `{rel_path}` — {description}"
        for description, rel_path in plot_paths
    ]

    full_stats_section = ""
    if full_row:
        full_stats_section = (
            "\n### Full baseline (baseline_30080_full) summary statistics\n\n"
            + full_baseline_stats_markdown(full_row)
            + "\n"
        )

    content = f"""# Aim 1 Stage 2.3 — RNAGenesis repository aptamer evaluation reproduction

## Purpose

This stage reproduced the RNAGenesis repository-provided aptamer evaluation procedure
on generated aptamer outputs, rather than applying a new project-specific metric suite.
The goal was faithful reproduction of upstream `test_wrap_aptamer.py` behaviour on
medium-test, single-chunk, and full merged baseline pools.

## Inputs

- **medium_test_16** — medium-test RNAGenesis output with 16 sequences.
- **baseline_30k_chunk1** — one 30k baseline chunk with 3,008 sequences
  (`seqs_wo_guidance_*.txt` from the unadapted baseline run).
- **baseline_30080_full** — full merged unadapted baseline pool with 30,080 sequences
  (`inputs/merged_30080_raw.txt`).
- Raw `seqs_wo_guidance_*.txt` files were used to preserve repository-faithful
  preprocessing (including raw token handling quirks).

## Repository evaluation procedure

- **Evaluation script:** RNAGenesis `test_wrap_aptamer.py` (`batch_analysis`,
  `threshold_analysis`, `run_rna_analysis`).
- **Project wrapper:** `scripts/run_repo_aptamer_evaluation.py`.
- The original repository CLI calls `run_rna_analysis()` but does not print returned
  metrics; the project wrapper exposes those metrics and verifies consistency with
  `run_rna_analysis()`.
- **Reference aptamer sequence:** `{ref_sequence}`
- **Reference MFE:** {fmt_float(ref_mfe)} kcal/mol
- **Reference structure:** `{ref_structure}`

## Metrics reproduced

The repository evaluation computes only:

- secondary-structure similarity to the hard-coded reference aptamer;
- per-sequence minimum free energy (MFE);
- MFE difference from the reference aptamer;
- percentage passing the structure-similarity threshold (`prop_similarity`);
- percentage passing the MFE-difference threshold (`prop_mfe`).

Where per-sequence CSVs were saved, mean/min/max summary statistics are also reported.
Project-specific metrics (GC content, uniqueness, validity, normalised MFE, ensemble
defect, diversity) are **not** part of this repository procedure and are deferred to a
later stage.

## Results

### Threshold pass rates by run

{results_table_markdown(rows)}
{full_stats_section}
## Interpretation

- The unadapted baseline produced **no** candidates meeting the repository's high
  structure-similarity threshold of 80 (`prop_similarity = 0%` across all runs).
- About **one third** of candidates met the MFE-difference threshold of 2 kcal/mol
  (`prop_mfe` ≈ 25–37% depending on subset).
- This is plausible for an unadapted/unguided baseline because generation was not
  target-conditioned or explicitly optimised for the hard-coded reference aptamer fold.
- These results reproduce repository-style evaluation but do not yet answer all
  project-specific baseline-characterisation questions.

## Limitations

- Repository evaluation does **not** compute validity, uniqueness, GC content,
  normalised MFE, ensemble defect, or diversity.
- Repository preprocessing has quirks (including raw token handling); this report
  intentionally preserves those quirks for faithful reproduction.
- Full project-specific baseline evaluation is deferred to a later stage.

## Per-sequence data availability

{per_sequence_note}

## Generated figures

{chr(10).join(figure_lines) if figure_lines else "No figures were generated."}

## Next steps

- Commit analysis outputs (script, tables, plots, and this report).
- Later implement project-specific baseline evaluation once the repository
  reproduction stage is closed.
"""
    path.write_text(content, encoding="utf-8")


def rel_to_report(path: Path, report_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(report_dir.resolve()))
    except ValueError:
        return str(path)


def main() -> int:
    args = parse_args()
    results_dir = args.results_dir.expanduser().resolve()
    raw_baseline_dir = args.raw_baseline_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    plots_dir = output_dir / "plots"
    tables_dir = output_dir / "tables"
    plots_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    apply_plot_style()
    generated: list[Path] = []

    summaries: list[dict[str, Any]] = []
    for label in RUN_LABELS:
        summary_path = results_dir / "summaries" / f"{label}{SUMMARY_SUFFIX}"
        summary = load_summary(summary_path)
        if summary is not None:
            summaries.append(summary)

    if not summaries:
        print("ERROR: No summary JSON files found. Nothing to analyse.", file=sys.stderr)
        return 1

    flat_rows = [flatten_summary(summary) for summary in summaries]
    full_row = next(
        (row for row in flat_rows if row["run_label"] == "baseline_30080_full"),
        None,
    )

    summary_csv = tables_dir / "repo_eval_run_summary.csv"
    write_summary_csv(summary_csv, flat_rows)
    generated.append(summary_csv)

    summary_md = tables_dir / "repo_eval_run_summary.md"
    write_summary_markdown(summary_md, flat_rows)
    generated.append(summary_md)

    plot_paths: list[tuple[str, Path]] = []

    threshold_plot = plots_dir / "threshold_pass_rates.png"
    if plot_threshold_pass_rates(flat_rows, threshold_plot):
        generated.append(threshold_plot)
        plot_paths.append(
            ("Threshold pass rates across runs", threshold_plot)
        )

    if full_row is not None:
        ranges_plot = plots_dir / "full_baseline_metric_ranges.png"
        if plot_full_baseline_metric_ranges(full_row, ranges_plot):
            generated.append(ranges_plot)
            plot_paths.append(
                ("Full baseline mean/min/max for similarity, MFE, and MFE difference",
                 ranges_plot)
            )

    raw_lengths = collect_raw_sequence_lengths(raw_baseline_dir)
    length_plot = plots_dir / "raw_sequence_length_distribution.png"
    if plot_length_histogram(raw_lengths, length_plot):
        generated.append(length_plot)
        plot_paths.append(
            ("Histogram of raw baseline line lengths", length_plot)
        )

    per_sequence_notes: list[str] = []
    for label in RUN_LABELS:
        per_seq_path = results_dir / "per_sequence" / f"{label}{PER_SEQUENCE_SUFFIX}"
        rows = load_per_sequence_csv(per_seq_path)
        if rows is None:
            continue

        for column, filename in [
            ("similarity", f"{label}_similarity_histogram.png"),
            ("mfe", f"{label}_mfe_histogram.png"),
            ("mfe_diff", f"{label}_mfe_diff_histogram.png"),
        ]:
            values = [float(row[column]) for row in rows if row.get(column)]
            out_path = plots_dir / filename
            if plot_per_sequence_histogram(values, column, out_path, label):
                generated.append(out_path)
                plot_paths.append(
                    (f"Per-sequence {column} histogram ({label})", out_path)
                )

    if not any(
        (results_dir / "per_sequence" / f"{label}{PER_SEQUENCE_SUFFIX}").is_file()
        for label in RUN_LABELS
        if label != "medium_test_16"
    ):
        per_sequence_notes.append(
            "Full per-sequence CSV was saved only for `medium_test_16` unless "
            "additional per-sequence files are present under `per_sequence/`."
        )
    else:
        per_sequence_notes.append(
            "Per-sequence CSV files were found for additional runs; histograms were "
            "generated where data was available."
        )

    per_sequence_note = " ".join(per_sequence_notes)

    report_path = output_dir / "aim1_repo_eval_report.md"
    rel_plot_entries = [
        (desc, Path(rel_to_report(plot_path, output_dir)))
        for desc, plot_path in plot_paths
    ]
    write_aim1_report(
        report_path,
        flat_rows,
        full_row,
        rel_plot_entries,
        per_sequence_note,
    )
    generated.append(report_path)

    print("Generated files:")
    for path in generated:
        print(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

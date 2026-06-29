#!/usr/bin/env python3
"""Plot GC content distributions for poster Stage 1 preliminary results (Figure 3).

Compares GC fractions from unadapted RNAGenesis and an Aptadiff-A-calibrated null
model against the empirical Aptadiff Dataset A reference bounds used in Stage 1
hard filtering. This is a descriptive comparison of one intrinsic sequence property
only — not binding, aptamer function, or experimental validity.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Figure dimensions (pixels) and resolution — same canvas as Figure 2.
FIG_WIDTH_PX = 800
FIG_HEIGHT_PX = 750
FIG_DPI = 100

# Poster colour palette.
COLOR_RNAGENESIS = "#A6192E"  # Macquarie-style burgundy red
COLOR_NULL_MODEL = "#4A4A4A"  # neutral dark grey
COLOR_BOUND_LINE = "#1A1A1A"  # very dark charcoal for training corpus bounds

DEFAULT_NULL_CSV = PROJECT_ROOT / "results/aim3_stage1_null_30k/stage1_all_sequences.csv"
DEFAULT_RNAGENESIS_CSV = (
    PROJECT_ROOT / "results/aim3_stage1_unadapted_30k_poster_config/stage1_all_sequences.csv"
)
DEFAULT_REFERENCE_JSON = (
    PROJECT_ROOT / "data/processed/corpus_distributions/aptadiff_datasetA_p6.json"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results/aim3_poster_figures"

OUTPUT_BASENAME = "gc_content_distribution_plot"
DIAGNOSTICS_BASENAME = "gc_content_distribution_diagnostics"
PLOTTING_METHOD = (
    "overlapping histograms with density normalization; "
    "discrete bins aligned to GC count / sequence length (1/36 increments)"
)

# All poster-config sequences are 36 nt after cleaning.
SEQUENCE_LENGTH = 36
GC_INCREMENT = 1.0 / SEQUENCE_LENGTH
X_AXIS_MIN = 0.25
X_AXIS_MAX = 0.85


def discrete_gc_bin_edges(length: int = SEQUENCE_LENGTH) -> np.ndarray:
    """Return histogram bin edges centred on possible GC fractions k/length."""
    return np.array([(k - 0.5) / length for k in range(0, length + 2)], dtype=float)


HIST_BIN_EDGES = discrete_gc_bin_edges()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot GC content distributions for unadapted RNAGenesis and "
            "Aptadiff-A-calibrated null model random RNA (poster Figure 3)."
        )
    )
    parser.add_argument(
        "--null-csv",
        type=Path,
        default=DEFAULT_NULL_CSV,
        help="Stage 1 all-sequences CSV for the Aptadiff-A-calibrated null model.",
    )
    parser.add_argument(
        "--rnagenesis-csv",
        type=Path,
        default=DEFAULT_RNAGENESIS_CSV,
        help="Stage 1 all-sequences CSV for unadapted RNAGenesis (poster config run).",
    )
    parser.add_argument(
        "--reference-json",
        type=Path,
        default=DEFAULT_REFERENCE_JSON,
        help="Aptadiff Dataset A processed corpus distribution JSON.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for figure outputs and metadata JSON.",
    )
    return parser.parse_args()


def load_gc_values(csv_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load per-sequence GC fractions and cleaned lengths from a Stage 1 CSV."""
    frame = pd.read_csv(csv_path, usecols=["gc_fraction", "cleaned_length"])
    gc_values = frame["gc_fraction"].to_numpy(dtype=float)
    lengths = frame["cleaned_length"].to_numpy(dtype=int)
    if gc_values.size == 0:
        raise ValueError(f"No GC values found in {csv_path}")
    return gc_values, lengths


def load_reference_gc_bounds(reference_json_path: Path) -> dict[str, float]:
    """Load Aptadiff A GC summary statistics used for Stage 1 filtering bounds."""
    with reference_json_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    summary = payload["gc_content_distribution"]["summary"]
    return {
        "lower_bound": float(summary["q05"]),
        "upper_bound": float(summary["q95"]),
        "mean": float(summary["mean"]),
    }


def summarize_gc_values(values: np.ndarray) -> dict[str, float]:
    """Compute min, max, and mean GC content for metadata."""
    return {
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
    }


def _format_gc_label(value: float) -> str:
    """Format a GC fraction for direct on-plot labels."""
    return f"{value:.3f}"


def _gc_count_distribution(
    gc_values: np.ndarray,
    lengths: np.ndarray,
) -> dict[int, int]:
    """Count sequences by integer GC count inferred from gc_fraction * length."""
    gc_counts = np.rint(gc_values * lengths).astype(int)
    unique_counts, counts = np.unique(gc_counts, return_counts=True)
    return {int(gc_count): int(count) for gc_count, count in zip(unique_counts, counts)}


def _analyze_condition_gc(
    condition_name: str,
    gc_values: np.ndarray,
    lengths: np.ndarray,
    sequence_length: int,
) -> dict[str, Any]:
    """Compute GC diagnostics for one generated sequence pool."""
    unique_values = np.unique(gc_values)
    unique_sorted = np.sort(unique_values)
    gc_increment = 1.0 / sequence_length

    if unique_sorted.size >= 2:
        spacings = np.diff(unique_sorted)
        inferred_spacing = float(np.median(spacings))
    else:
        spacings = np.array([], dtype=float)
        inferred_spacing = float("nan")

    expected_counts = np.rint(unique_sorted * sequence_length).astype(int)
    alignment_residuals = np.abs(unique_sorted - expected_counts / sequence_length)
    aligns_with_increments = bool(np.all(alignment_residuals <= 1e-9))

    gc_count_counts = _gc_count_distribution(gc_values, lengths)
    observed_gc_counts = sorted(gc_count_counts)
    min_gc_count = observed_gc_counts[0]
    max_gc_count = observed_gc_counts[-1]
    missing_gc_counts = [
        gc_count
        for gc_count in range(min_gc_count, max_gc_count + 1)
        if gc_count not in gc_count_counts
    ]

    return {
        "condition_name": condition_name,
        "row_count": int(gc_values.size),
        "cleaned_length_min": int(np.min(lengths)),
        "cleaned_length_max": int(np.max(lengths)),
        "cleaned_length_unique": sorted(int(value) for value in np.unique(lengths)),
        "gc_min": float(np.min(gc_values)),
        "gc_max": float(np.max(gc_values)),
        "gc_mean": float(np.mean(gc_values)),
        "unique_gc_value_count": int(unique_sorted.size),
        "first_10_unique_gc_values": [float(value) for value in unique_sorted[:10]],
        "last_10_unique_gc_values": [float(value) for value in unique_sorted[-10:]],
        "inferred_spacing_between_unique_values": inferred_spacing,
        "expected_spacing_1_over_length": gc_increment,
        "aligns_with_1_over_length_increments": aligns_with_increments,
        "gc_count_min": min_gc_count,
        "gc_count_max": max_gc_count,
        "missing_gc_counts_within_observed_range": missing_gc_counts,
        "missing_gc_count_count": len(missing_gc_counts),
        "gc_count_distribution": {
            str(gc_count): count for gc_count, count in sorted(gc_count_counts.items())
        },
    }


def diagnose_gc_distributions(
    null_gc: np.ndarray,
    null_lengths: np.ndarray,
    rnagenesis_gc: np.ndarray,
    rnagenesis_lengths: np.ndarray,
    *,
    null_csv: Path,
    rnagenesis_csv: Path,
    sequence_length: int = SEQUENCE_LENGTH,
) -> dict[str, Any]:
    """Check whether plot gaps reflect discrete data or histogram binning artefacts."""
    null_diag = _analyze_condition_gc("null_model", null_gc, null_lengths, sequence_length)
    rnagenesis_diag = _analyze_condition_gc(
        "rnagenesis", rnagenesis_gc, rnagenesis_lengths, sequence_length
    )

    # Previous plot used 25 arbitrary bins between 0.25 and 0.85.
    old_bins = np.linspace(X_AXIS_MIN, X_AXIS_MAX, 25)
    old_null_counts, _ = np.histogram(null_gc, bins=old_bins)
    old_rnagenesis_counts, _ = np.histogram(rnagenesis_gc, bins=old_bins)
    old_empty_bins = int(np.sum(old_null_counts == 0) + np.sum(old_rnagenesis_counts == 0))

    discrete_null_counts, discrete_edges = np.histogram(null_gc, bins=HIST_BIN_EDGES)
    discrete_rnagenesis_counts, _ = np.histogram(rnagenesis_gc, bins=HIST_BIN_EDGES)
    bin_centers = (discrete_edges[:-1] + discrete_edges[1:]) / 2.0
    in_view = (bin_centers >= X_AXIS_MIN) & (bin_centers <= X_AXIS_MAX)
    discrete_empty_bins_total = int(
        np.sum(discrete_null_counts == 0) + np.sum(discrete_rnagenesis_counts == 0)
    )
    discrete_empty_bins_in_view = int(
        np.sum((discrete_null_counts == 0)[in_view])
        + np.sum((discrete_rnagenesis_counts == 0)[in_view])
    )

    total_missing_gc_counts = (
        null_diag["missing_gc_count_count"] + rnagenesis_diag["missing_gc_count_count"]
    )

    if total_missing_gc_counts > 0 and old_empty_bins >= discrete_empty_bins_in_view:
        interpretation = (
            "mixture of both: the previous 25-bin linspace misaligned with discrete "
            "1/36 GC fractions and created artificial gaps; after discrete binning, "
            "remaining blank spaces reflect true zero-count GC-count values within "
            "the observed range"
        )
    elif old_empty_bins > discrete_empty_bins_in_view:
        interpretation = (
            "histogram binning artefact: GC content is discrete at 1/36 increments "
            "and the previous 25-bin linspace misaligned with those values"
        )
    elif total_missing_gc_counts > 0:
        interpretation = (
            "true zero-count bins: some GC-count values within the observed range "
            "have no sequences in one or both generated pools"
        )
    else:
        interpretation = (
            "histogram binning artefact: GC content is discrete at 1/36 increments "
            "and the previous misaligned bins created artificial gaps; no missing "
            "GC-count values remain within either pool's observed range"
        )

    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_files": {
            "null_model_csv": str(null_csv.resolve()),
            "rnagenesis_csv": str(rnagenesis_csv.resolve()),
        },
        "sequence_length_used_for_diagnostics": sequence_length,
        "gc_increment": GC_INCREMENT,
        "histogram_binning": {
            "previous_method": f"np.linspace({X_AXIS_MIN}, {X_AXIS_MAX}, 25)",
            "previous_empty_bin_slots_across_both_conditions": old_empty_bins,
            "revised_method": "bin edges at (k - 0.5) / length for k in 0..length+1",
            "revised_empty_bin_slots_across_both_conditions": discrete_empty_bins_total,
            "revised_empty_bin_slots_within_x_axis_view": discrete_empty_bins_in_view,
            "x_axis_view_range": [X_AXIS_MIN, X_AXIS_MAX],
        },
        "null_model": null_diag,
        "rnagenesis": rnagenesis_diag,
        "interpretation": interpretation,
    }


def save_gc_diagnostics(diagnostics: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    """Write GC diagnostics to human-readable text and JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / f"{DIAGNOSTICS_BASENAME}.txt"
    json_path = output_dir / f"{DIAGNOSTICS_BASENAME}.json"

    null_diag = diagnostics["null_model"]
    rnagenesis_diag = diagnostics["rnagenesis"]

    lines = [
        "GC content distribution diagnostics",
        "===================================",
        "",
        f"Null model source: {diagnostics['source_files']['null_model_csv']}",
        f"RNAGenesis source: {diagnostics['source_files']['rnagenesis_csv']}",
        f"Sequence length (expected): {diagnostics['sequence_length_used_for_diagnostics']} nt",
        f"GC increment (1/length): {diagnostics['gc_increment']:.12f}",
        "",
        "Null model",
        "----------",
        f"Rows: {null_diag['row_count']:,}",
        f"Cleaned length range: {null_diag['cleaned_length_min']}–{null_diag['cleaned_length_max']}",
        f"GC min / max / mean: {null_diag['gc_min']:.6f} / {null_diag['gc_max']:.6f} / {null_diag['gc_mean']:.6f}",
        f"Unique GC values: {null_diag['unique_gc_value_count']}",
        f"First 10 unique GC values: {null_diag['first_10_unique_gc_values']}",
        f"Last 10 unique GC values: {null_diag['last_10_unique_gc_values']}",
        f"Inferred spacing between unique values: {null_diag['inferred_spacing_between_unique_values']:.12f}",
        f"Aligns with 1/length increments: {null_diag['aligns_with_1_over_length_increments']}",
        f"Missing GC-count values within observed range ({null_diag['gc_count_min']}–{null_diag['gc_count_max']}): "
        f"{null_diag['missing_gc_counts_within_observed_range']}",
        "",
        "Unadapted RNAGenesis",
        "--------------------",
        f"Rows: {rnagenesis_diag['row_count']:,}",
        f"Cleaned length range: {rnagenesis_diag['cleaned_length_min']}–{rnagenesis_diag['cleaned_length_max']}",
        f"GC min / max / mean: {rnagenesis_diag['gc_min']:.6f} / {rnagenesis_diag['gc_max']:.6f} / {rnagenesis_diag['gc_mean']:.6f}",
        f"Unique GC values: {rnagenesis_diag['unique_gc_value_count']}",
        f"First 10 unique GC values: {rnagenesis_diag['first_10_unique_gc_values']}",
        f"Last 10 unique GC values: {rnagenesis_diag['last_10_unique_gc_values']}",
        f"Inferred spacing between unique values: {rnagenesis_diag['inferred_spacing_between_unique_values']:.12f}",
        f"Aligns with 1/length increments: {rnagenesis_diag['aligns_with_1_over_length_increments']}",
        f"Missing GC-count values within observed range ({rnagenesis_diag['gc_count_min']}–{rnagenesis_diag['gc_count_max']}): "
        f"{rnagenesis_diag['missing_gc_counts_within_observed_range']}",
        "",
        "Histogram binning comparison",
        "----------------------------",
        f"Previous bins: {diagnostics['histogram_binning']['previous_method']}",
        f"Previous empty bin slots (both conditions): "
        f"{diagnostics['histogram_binning']['previous_empty_bin_slots_across_both_conditions']}",
        f"Revised bins: {diagnostics['histogram_binning']['revised_method']}",
        f"Revised empty bin slots (both conditions, all bins): "
        f"{diagnostics['histogram_binning']['revised_empty_bin_slots_across_both_conditions']}",
        f"Revised empty bin slots within x-axis view ({X_AXIS_MIN}–{X_AXIS_MAX}): "
        f"{diagnostics['histogram_binning']['revised_empty_bin_slots_within_x_axis_view']}",
        "",
        f"Interpretation: {diagnostics['interpretation']}",
        "",
    ]

    with txt_path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(diagnostics, handle, indent=2)
        handle.write("\n")

    return txt_path, json_path


def make_gc_distribution_plot(
    null_gc: np.ndarray,
    rnagenesis_gc: np.ndarray,
    bounds: dict[str, float],
    output_dir: Path,
) -> dict[str, Path]:
    """Create and save the GC content distribution figure."""
    output_dir.mkdir(parents=True, exist_ok=True)

    fig_width_in = FIG_WIDTH_PX / FIG_DPI
    fig_height_in = FIG_HEIGHT_PX / FIG_DPI
    fig, ax = plt.subplots(figsize=(fig_width_in, fig_height_in), dpi=FIG_DPI)

    # Null model drawn first so RNAGenesis remains visible on overlap.
    ax.hist(
        null_gc,
        bins=HIST_BIN_EDGES,
        density=True,
        alpha=0.55,
        color=COLOR_NULL_MODEL,
        edgecolor="white",
        linewidth=0.4,
        label="Null model random RNA",
        zorder=2,
    )
    ax.hist(
        rnagenesis_gc,
        bins=HIST_BIN_EDGES,
        density=True,
        alpha=0.55,
        color=COLOR_RNAGENESIS,
        edgecolor="white",
        linewidth=0.4,
        label="Unadapted RNAGenesis",
        zorder=3,
    )

    lower_bound = bounds["lower_bound"]
    upper_bound = bounds["upper_bound"]

    # Training corpus bounds — drawn above histogram fills for visibility.
    ax.axvline(
        lower_bound,
        color=COLOR_BOUND_LINE,
        linestyle="--",
        linewidth=2.2,
        zorder=5,
    )
    ax.axvline(
        upper_bound,
        color=COLOR_BOUND_LINE,
        linestyle="--",
        linewidth=2.2,
        zorder=5,
    )

    y_top = ax.get_ylim()[1]

    # Direct labels on the plot (not legend-only).
    ax.text(
        lower_bound - 0.008,
        y_top * 0.92,
        f"Aptadiff A q05\n{_format_gc_label(lower_bound)}",
        ha="right",
        va="top",
        fontsize=10,
        fontweight="bold",
        color=COLOR_BOUND_LINE,
        linespacing=1.15,
        zorder=6,
    )
    ax.text(
        upper_bound + 0.008,
        y_top * 0.92,
        f"Aptadiff A q95\n{_format_gc_label(upper_bound)}",
        ha="left",
        va="top",
        fontsize=10,
        fontweight="bold",
        color=COLOR_BOUND_LINE,
        linespacing=1.15,
        zorder=6,
    )

    ax.set_xlabel("GC content", fontsize=12)
    ax.set_ylabel("Density", fontsize=12)
    ax.set_xlim(X_AXIS_MIN, X_AXIS_MAX)

    ax.yaxis.grid(True, linestyle="-", linewidth=0.4, color="#DDDDDD", zorder=0)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.subplots_adjust(left=0.12, right=0.97, top=0.78, bottom=0.12)

    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.03),
        ncol=2,
        frameon=False,
        fontsize=10,
    )

    fig.suptitle(
        "GC content distributions",
        fontsize=14,
        fontweight="bold",
        y=0.985,
    )

    output_paths = {
        "png": output_dir / f"{OUTPUT_BASENAME}.png",
        "pdf": output_dir / f"{OUTPUT_BASENAME}.pdf",
        "svg": output_dir / f"{OUTPUT_BASENAME}.svg",
    }

    fig.savefig(
        output_paths["png"],
        dpi=FIG_DPI,
        facecolor="white",
        edgecolor="none",
    )
    fig.savefig(
        output_paths["pdf"],
        facecolor="white",
        edgecolor="none",
    )
    fig.savefig(
        output_paths["svg"],
        facecolor="white",
        edgecolor="none",
    )
    plt.close(fig)

    return output_paths


def save_metadata(
    *,
    null_csv: Path,
    rnagenesis_csv: Path,
    reference_json: Path,
    null_gc: np.ndarray,
    rnagenesis_gc: np.ndarray,
    bounds: dict[str, float],
    null_summary: dict[str, float],
    rnagenesis_summary: dict[str, float],
    diagnostics: dict[str, Any],
    output_paths: dict[str, Path],
    diagnostics_paths: tuple[Path, Path],
    output_dir: Path,
) -> Path:
    """Write a JSON metadata file describing inputs, summaries, and outputs."""
    metadata_path = output_dir / f"{OUTPUT_BASENAME}_metadata.json"
    diagnostics_txt_path, diagnostics_json_path = diagnostics_paths

    metadata: dict[str, Any] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "figure_title": "GC content distributions",
        "figure_description": (
            "Descriptive comparison of GC content for unadapted RNAGenesis generated "
            "sequences and Aptadiff-A-calibrated null model random RNA, with Aptadiff "
            "Dataset A Stage 1 training corpus bounds shown as dashed vertical lines."
        ),
        "plotting_method": PLOTTING_METHOD,
        "source_files": {
            "null_model_csv": str(null_csv.resolve()),
            "rnagenesis_csv": str(rnagenesis_csv.resolve()),
            "reference_json": str(reference_json.resolve()),
        },
        "sequence_counts": {
            "null_model": int(null_gc.size),
            "rnagenesis": int(rnagenesis_gc.size),
        },
        "null_model_gc": {
            **null_summary,
            "count": int(null_gc.size),
        },
        "rnagenesis_gc": {
            **rnagenesis_summary,
            "count": int(rnagenesis_gc.size),
        },
        "aptadiff_reference_gc": {
            "lower_bound_q05": bounds["lower_bound"],
            "upper_bound_q95": bounds["upper_bound"],
            "mean": bounds["mean"],
        },
        "gc_diagnostics_interpretation": diagnostics["interpretation"],
        "diagnostics_files": {
            "txt": str(diagnostics_txt_path.resolve()),
            "json": str(diagnostics_json_path.resolve()),
        },
        "output_files": {key: str(path.resolve()) for key, path in output_paths.items()},
        "metadata_path": str(metadata_path.resolve()),
        "canvas_size_px": {"width": FIG_WIDTH_PX, "height": FIG_HEIGHT_PX},
        "dpi": FIG_DPI,
    }

    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    return metadata_path


def print_summary(
    null_gc: np.ndarray,
    rnagenesis_gc: np.ndarray,
    bounds: dict[str, float],
    diagnostics: dict[str, Any],
    output_paths: dict[str, Path],
    diagnostics_paths: tuple[Path, Path],
) -> None:
    """Print plotted counts, means, bounds, diagnostics, and saved paths."""
    null_diag = diagnostics["null_model"]
    rnagenesis_diag = diagnostics["rnagenesis"]

    print(f"Null model sequences plotted: {null_gc.size:,}")
    print(f"RNAGenesis sequences plotted: {rnagenesis_gc.size:,}")
    print(f"Null model mean GC: {np.mean(null_gc):.6f}")
    print(f"RNAGenesis mean GC: {np.mean(rnagenesis_gc):.6f}")
    print(f"Aptadiff A lower GC bound (q05): {bounds['lower_bound']:.6f}")
    print(f"Aptadiff A upper GC bound (q95): {bounds['upper_bound']:.6f}")
    print("")
    print("GC diagnostics:")
    print(f"- Null model unique GC values: {null_diag['unique_gc_value_count']}")
    print(f"- RNAGenesis unique GC values: {rnagenesis_diag['unique_gc_value_count']}")
    print(
        "- Values align with 1/36 increments: "
        f"{'yes' if null_diag['aligns_with_1_over_length_increments'] and rnagenesis_diag['aligns_with_1_over_length_increments'] else 'no'}"
    )
    print(
        "- Missing GC-count bins within observed range: "
        f"null={null_diag['missing_gc_counts_within_observed_range']}, "
        f"rnagenesis={rnagenesis_diag['missing_gc_counts_within_observed_range']}"
    )
    print(f"- Interpretation: {diagnostics['interpretation']}")
    print("")
    print("Saved:")
    print(f"- {output_paths['png']}")
    print(f"- {output_paths['pdf']}")
    print(f"- {output_paths['svg']}")
    print(f"- {diagnostics_paths[0]}")
    print(f"- {diagnostics_paths[1]}")


def main() -> None:
    args = parse_args()

    null_gc, null_lengths = load_gc_values(args.null_csv)
    rnagenesis_gc, rnagenesis_lengths = load_gc_values(args.rnagenesis_csv)
    bounds = load_reference_gc_bounds(args.reference_json)

    diagnostics = diagnose_gc_distributions(
        null_gc,
        null_lengths,
        rnagenesis_gc,
        rnagenesis_lengths,
        null_csv=args.null_csv,
        rnagenesis_csv=args.rnagenesis_csv,
    )
    diagnostics_paths = save_gc_diagnostics(diagnostics, args.output_dir)

    null_summary = summarize_gc_values(null_gc)
    rnagenesis_summary = summarize_gc_values(rnagenesis_gc)

    output_paths = make_gc_distribution_plot(
        null_gc=null_gc,
        rnagenesis_gc=rnagenesis_gc,
        bounds=bounds,
        output_dir=args.output_dir,
    )

    metadata_path = save_metadata(
        null_csv=args.null_csv,
        rnagenesis_csv=args.rnagenesis_csv,
        reference_json=args.reference_json,
        null_gc=null_gc,
        rnagenesis_gc=rnagenesis_gc,
        bounds=bounds,
        null_summary=null_summary,
        rnagenesis_summary=rnagenesis_summary,
        diagnostics=diagnostics,
        output_paths=output_paths,
        diagnostics_paths=diagnostics_paths,
        output_dir=args.output_dir,
    )

    print_summary(
        null_gc,
        rnagenesis_gc,
        bounds,
        diagnostics,
        output_paths,
        diagnostics_paths,
    )
    print(f"- {metadata_path}")


if __name__ == "__main__":
    main()

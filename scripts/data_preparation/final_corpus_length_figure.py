#!/usr/bin/env python3
"""Render thesis core-length distributions for the final corpus and partitions."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MultipleLocator


REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "data" / "processed" / "corpus_final.csv"
OUTPUT_DIR = REPO_ROOT / "docs" / "data_curation" / "assets" / "figures"
OUTPUT_STEM = OUTPUT_DIR / "final_corpus_length_distribution"
REGIME_MEANS_NT = (39.0, 77.0)

MQ = {
    "charcoal": "#373A36",
    "success": "#009174",
    "alert": "#BC4700",
    "sand": "#D6D2C4",
    "sand_light": "#EDEBE5",
}

TEXT_WIDTH_IN = 15.5 / 2.54
FIGURE_HEIGHT_IN = 12.0 / 2.54


mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Liberation Sans", "Arimo", "DejaVu Sans"],
        "font.size": 9,
        "axes.titlesize": 9.5,
        "axes.labelsize": 10,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8.5,
        "legend.frameon": False,
        "text.color": MQ["charcoal"],
        "axes.labelcolor": MQ["charcoal"],
        "axes.edgecolor": MQ["charcoal"],
        "axes.linewidth": 0.8,
        "xtick.color": MQ["charcoal"],
        "ytick.color": MQ["charcoal"],
        "grid.color": MQ["sand"],
        "grid.linewidth": 0.5,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
    }
)


def normalise_core(row: dict[str, str]) -> str:
    sequence = row["sequence_core"].strip().upper().replace("T", "U")
    if not sequence:
        raise ValueError("Encountered an empty sequence_core value")
    invalid = set(sequence) - set("ACGU")
    if invalid:
        raise ValueError(f"Unexpected nucleotide symbols: {sorted(invalid)}")
    recorded_length = int(row["sequence_length_core"])
    if recorded_length != len(sequence):
        raise ValueError(
            f"Core-length mismatch: recorded {recorded_length}, observed {len(sequence)}"
        )
    return sequence


def load_lengths_by_subset() -> tuple[dict[str, np.ndarray], dict[str, int]]:
    with CORPUS_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    unexpected = {row["partition"] for row in rows} - {"FT", "EVAL", "REF"}
    if unexpected:
        raise ValueError(f"Unexpected partition labels: {sorted(unexpected)}")

    subset_rows = {
        "corpus_final": rows,
        "FT": [row for row in rows if row["partition"] == "FT"],
        "EVAL": [row for row in rows if row["partition"] == "EVAL"],
        "REF": [row for row in rows if row["partition"] == "REF"],
    }
    values: dict[str, np.ndarray] = {}
    identity_counts: dict[str, int] = {}
    for label, selected_rows in subset_rows.items():
        cores = {normalise_core(row) for row in selected_rows}
        values[label] = np.asarray([len(sequence) for sequence in cores], dtype=float)
        identity_counts[label] = len(selected_rows)

    if sum(len(values[label]) for label in ("FT", "EVAL", "REF")) != len(
        values["corpus_final"]
    ):
        raise ValueError("Unique sequence cores are not disjoint across FT, EVAL, and REF")
    return values, identity_counts


def render() -> None:
    values_by_subset, identity_counts = load_lengths_by_subset()
    panel_specs = (
        ("(a)", "corpus_final"),
        ("(b)", "FT"),
        ("(c)", "EVAL"),
        ("(d)", "REF"),
    )
    bins = np.arange(20.0, 125.0 + 5.0, 5.0)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(
        2,
        2,
        figsize=(TEXT_WIDTH_IN, FIGURE_HEIGHT_IN),
        sharex=True,
        sharey=True,
    )
    fig.subplots_adjust(
        left=0.12, right=0.985, top=0.88, bottom=0.14, wspace=0.12, hspace=0.24
    )

    statistics: dict[str, dict[str, float]] = {}
    max_frequency = 0.0
    for ax, (panel_label, subset_label) in zip(axes.flat, panel_specs, strict=True):
        values = values_by_subset[subset_label]
        q05, q95 = (float(value) for value in np.percentile(values, [5, 95]))
        mean = float(np.mean(values))
        statistics[subset_label] = {
            "mean": mean,
            "q05": q05,
            "q95": q95,
        }

        frequencies, _ = np.histogram(values, bins=bins)
        max_frequency = max(
            max_frequency, float((100.0 * frequencies / len(values)).max())
        )

        ax.axvspan(q05, q95, color=MQ["sand_light"], zorder=0)
        ax.hist(
            values,
            bins=bins,
            weights=np.full(len(values), 100.0 / len(values)),
            color=MQ["success"],
            edgecolor="white",
            linewidth=0.5,
            zorder=2,
        )
        for regime_mean in REGIME_MEANS_NT:
            ax.axvline(
                regime_mean,
                color=MQ["alert"],
                linewidth=1.4,
                linestyle=(0, (4, 2)),
                zorder=3,
            )

        ax.set_title(
            f"{panel_label} {subset_label} ($n={len(values):,}$)", loc="left", pad=4
        )
        ax.set_xlim(20, 125)
        ax.set_xticks(np.arange(20, 121, 20))
        ax.grid(axis="y", zorder=1)
        ax.grid(axis="x", visible=False)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(width=0.8, length=3)

    y_max = 5.0 * math.ceil((max_frequency * 1.15) / 5.0)
    for ax in axes.flat:
        ax.set_ylim(0, y_max)
        ax.yaxis.set_major_locator(MultipleLocator(5))

    fig.supxlabel(
        "Sequence core length (nt)",
        y=0.045,
        fontsize=10,
        color=MQ["charcoal"],
    )
    fig.supylabel(
        "Unique sequence cores (% per bin)",
        x=0.025,
        fontsize=10,
        color=MQ["charcoal"],
    )
    interval_handle = Patch(
        facecolor=MQ["sand_light"], edgecolor="none", label="5th–95th percentile"
    )
    regime_handle = Line2D(
        [0],
        [0],
        color=MQ["alert"],
        linewidth=1.4,
        linestyle=(0, (4, 2)),
        label="S6 component means (~39 and ~77 nt)",
    )
    fig.legend(
        handles=[interval_handle, regime_handle],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.985),
        ncol=2,
        handlelength=2.4,
        columnspacing=1.8,
        handletextpad=0.7,
    )

    metadata = {
        "Title": "Core-length distributions for the final corpus and partitions",
        "Subject": (
            "Relative-frequency distributions for distinct binding-sequence core "
            "lengths in corpus_final, FT, EVAL and REF"
        ),
        "Creator": "Matplotlib using the Macquarie University thesis style guide",
    }
    fig.savefig(OUTPUT_STEM.with_suffix(".pdf"), facecolor="white", metadata=metadata)
    fig.savefig(
        OUTPUT_STEM.with_suffix(".png"),
        dpi=300,
        facecolor="white",
        metadata={"Software": metadata["Creator"]},
    )
    fig.savefig(
        OUTPUT_STEM.with_suffix(".svg"),
        facecolor="white",
        metadata={"Title": metadata["Title"], "Description": metadata["Subject"]},
    )
    plt.close(fig)

    for _, subset_label in panel_specs:
        stats = statistics[subset_label]
        print(
            f"subset={subset_label} n_identities={identity_counts[subset_label]} "
            f"n_distinct_cores={len(values_by_subset[subset_label])} "
            f"mean={stats['mean']:.6f} q05={stats['q05']:.6f} "
            f"q95={stats['q95']:.6f}"
        )


if __name__ == "__main__":
    render()

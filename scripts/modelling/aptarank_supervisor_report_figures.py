#!/usr/bin/env python3
"""Generate aggregate-only figures for the Sections 6–10 supervisor report.

All plotted values are copied from independently reviewed and closed aggregate
result records. The script does not read candidate-level or sequence-bearing
evidence and does not recompute AptaRank scores.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


COLORS = {
    "blue": "#4477AA",
    "cyan": "#66CCEE",
    "green": "#228833",
    "yellow": "#CCBB44",
    "red": "#EE6677",
    "purple": "#AA3377",
    "grey": "#BBBBBB",
    "dark": "#333333",
}


def configure_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 160,
            "savefig.dpi": 240,
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
        }
    )


def save(fig: plt.Figure, output_dir: Path, stem: str) -> None:
    fig.savefig(output_dir / f"{stem}.png", bbox_inches="tight")
    fig.savefig(output_dir / f"{stem}.svg", bbox_inches="tight")
    plt.close(fig)


def figure_1_section6(output_dir: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.1), gridspec_kw={"width_ratios": [1.15, 1]})

    groups = ["Held-out\naptamer cores", "Exact-length\nuniform controls"]
    means = [0.513, 0.429]
    medians = [0.512, 0.409]
    x = np.arange(len(groups))
    width = 0.32
    axes[0].bar(x - width / 2, means, width, label="Mean", color=COLORS["blue"])
    axes[0].bar(x + width / 2, medians, width, label="Median", color=COLORS["cyan"])
    axes[0].set_xticks(x, groups)
    axes[0].set_ylim(0, 0.65)
    axes[0].set_ylabel("Tier 1 aptamer-likeness")
    axes[0].set_title("A. Reference-calibrated scores")
    axes[0].legend(frameon=False, loc="upper right")
    for xpos, values in zip(x, zip(means, medians)):
        for offset, value in zip((-width / 2, width / 2), values):
            axes[0].text(xpos + offset, value + 0.015, f"{value:.3f}", ha="center", va="bottom", fontsize=9)

    effect = 0.108
    low, high = 0.064, 0.164
    axes[1].errorbar(
        effect,
        1,
        xerr=np.array([[effect - low], [high - effect]]),
        fmt="o",
        color=COLORS["green"],
        ecolor=COLORS["green"],
        capsize=5,
        markersize=8,
    )
    axes[1].axvline(0, color=COLORS["dark"], linewidth=1, linestyle="--")
    axes[1].set_xlim(-0.03, 0.20)
    axes[1].set_ylim(0.55, 1.45)
    axes[1].set_yticks([1], ["Median paired difference"])
    axes[1].set_xlabel("Held-out aptamer minus paired control")
    axes[1].set_title("B. Paired effect with cluster-bootstrap 95% CI")
    axes[1].text(effect, 1.17, "0.108 [0.064, 0.164]", ha="center", color=COLORS["green"])
    axes[1].text(
        0.5,
        -0.24,
        "AUROC 0.638 [0.555, 0.717]\nShuffle pass: 9.8% vs 5.9%; difference 3.9 pp [−3.2, 11.1]",
        transform=axes[1].transAxes,
        ha="center",
        va="top",
        fontsize=9,
    )
    fig.suptitle("Section 6: Tier 1 separates held-out aptamers from a synthetic uniform floor", y=1.03, fontsize=13)
    fig.tight_layout()
    save(fig, output_dir, "figure_1_section6_tier1_calibration")


def add_band_background(ax: plt.Axes) -> None:
    ax.axvspan(0, 0.75, color=COLORS["grey"], alpha=0.28, label="Weak")
    ax.axvspan(0.75, 0.95, color=COLORS["yellow"], alpha=0.28, label="Moderate")
    ax.axvspan(0.95, 1.0, color=COLORS["green"], alpha=0.22, label="Strong")
    ax.axvline(0.75, color=COLORS["dark"], linewidth=0.8, linestyle="--")
    ax.axvline(0.95, color=COLORS["dark"], linewidth=0.8, linestyle="--")
    ax.set_xlim(0, 1)
    ax.set_xlabel("Target-control percentile")


def figure_2_section8(output_dir: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.1), sharex=True)
    add_band_background(axes[0])
    add_band_background(axes[1])

    axes[0].scatter([0.106], [0], marker="x", s=90, linewidth=2.2, color=COLORS["red"], zorder=3)
    axes[0].set_yticks([0], ["28-nt cognate core"])
    axes[0].set_ylim(-0.65, 0.65)
    axes[0].set_title("A. GRK2 pocket mode")
    axes[0].text(0.106, 0.20, "0.106\nshuffle fail", ha="center", color=COLORS["red"], fontsize=9)

    y = [1, 0]
    vals = [0.462, 0.753]
    axes[1].scatter(vals, y, marker="x", s=90, linewidth=2.2, color=COLORS["red"], zorder=3)
    axes[1].set_yticks(y, ["59-nt cognate core", "45-nt cognate core"])
    axes[1].set_ylim(-0.65, 1.65)
    axes[1].set_title("B. Lysozyme surface mode")
    axes[1].text(0.462, 1.22, "0.462\nshuffle fail", ha="center", color=COLORS["red"], fontsize=9)
    axes[1].text(0.753, 0.22, "0.753\nshuffle fail", ha="center", color=COLORS["red"], fontsize=9)

    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles[:3], labels[:3], loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.03))
    fig.suptitle("Section 8: target-aware annotation was weak to mixed in known cognate cases", y=1.03, fontsize=13)
    fig.text(
        0.5,
        -0.12,
        "Pocket and surface modes are shown separately; their raw geometric mismatches must not be compared.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    save(fig, output_dir, "figure_2_section8_cognate_target_cases")


def figure_3_section9(output_dir: Path) -> None:
    labels = ["B0", "B1", "B2", "D1"]
    colors = [COLORS["grey"], COLORS["blue"], COLORS["yellow"], COLORS["green"]]
    panels = [
        ("A. Tier 1 mean", [0.334, 0.402, 0.492, 0.460], "Mean score", (0, 0.58), "{:.3f}"),
        ("B. Target-control percentile mean", [0.376, 0.472, 0.485, 0.501], "Mean percentile", (0, 0.58), "{:.3f}"),
        ("C. Candidate-specific shuffle pass", [5.0, 5.5, 6.5, 8.5], "Candidates (%)", (0, 10.5), "{:.1f}%"),
        ("D. Strong or moderate compatibility", [8.0, 22.5, 23.5, 28.0], "Candidates (%)", (0, 32), "{:.1f}%"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.1))
    for ax, (title, values, ylabel, ylim, formatter) in zip(axes.flat, panels):
        bars = ax.bar(labels, values, color=colors)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_ylim(*ylim)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, value + (ylim[1] * 0.025), formatter.format(value), ha="center", va="bottom", fontsize=9)
    fig.suptitle("Section 9: descriptive AptaRank outputs for 200 candidates per condition", y=1.01, fontsize=13)
    fig.text(
        0.5,
        0.005,
        "B1 is the generic neural baseline; D1 is the aptamer-adapted model; B2 is a non-neural TRAIN-matched sampler; B0 is an external 36-nt comparator.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.98))
    save(fig, output_dir, "figure_3_section9_generated_condition_comparison")


def labelled_horizontal_bars(ax: plt.Axes, labels: list[str], values: list[int], denominator: int, title: str) -> None:
    y = np.arange(len(labels))
    bars = ax.barh(y, values, color=[COLORS["blue"], COLORS["cyan"], COLORS["yellow"], COLORS["green"]][: len(labels)])
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_title(title)
    ax.set_xlabel("Candidate records")
    maximum = max(values)
    ax.set_xlim(0, maximum * 1.18)
    for bar, value in zip(bars, values):
        pct = 100 * value / denominator
        ax.text(value + maximum * 0.018, bar.get_y() + bar.get_height() / 2, f"{value:,} ({pct:.2f}%)", va="center", fontsize=9)


def figure_4_section10(output_dir: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    labelled_horizontal_bars(
        axes[0],
        ["Uploaded", "Valid and scored", "Exact target-aware export"],
        [30000, 29583, 1000],
        30000,
        "A. Run accounting (percentage of uploads)",
    )
    labelled_horizontal_bars(
        axes[1],
        ["Target-aware top 1,000", "Shuffle pass", "Both mandatory gates", "Supervisor-review pool"],
        [1000, 558, 137, 100],
        1000,
        "B. Frozen screening (percentage of top 1,000)",
    )
    fig.suptitle("Section 10: the full D1 pool yielded 100 candidates for joint supervisor review", y=1.02, fontsize=13)
    fig.text(
        0.5,
        -0.02,
        "Both mandatory gates = shuffle pass plus strong-or-moderate NDM-1 compatibility. Tier 1 rank ordered the 137 eligible candidates; 37 were capped out.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.98))
    save(fig, output_dir, "figure_4_section10_shortlisting_funnel")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/evaluation/assets/figures"),
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    configure_style()
    figure_1_section6(args.output_dir)
    figure_2_section8(args.output_dir)
    figure_3_section9(args.output_dir)
    figure_4_section10(args.output_dir)


if __name__ == "__main__":
    main()

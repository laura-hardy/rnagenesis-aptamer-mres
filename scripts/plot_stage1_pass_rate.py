#!/usr/bin/env python3
"""Plot Stage 1 (Level 1) hard-filter pass rates for poster preliminary results.

Compares unadapted RNAGenesis generated sequences against an Aptadiff-A-calibrated
null model under identical Stage 1 hard filters. Passing Level 1 means only that
intrinsic hard filters were satisfied — not binding, aptamer function, or
experimental validity.
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Figure dimensions (pixels) and resolution.
FIG_WIDTH_PX = 800
FIG_HEIGHT_PX = 750
FIG_DPI = 100

# Poster colour palette.
COLOR_RNAGENESIS = "#A6192E"  # Macquarie-style burgundy red
COLOR_NULL_MODEL = "#4A4A4A"  # neutral dark grey

DEFAULT_RNAGENESIS_SUMMARY = (
    PROJECT_ROOT / "results/aim3_stage1_unadapted_30k_poster_config/stage1_summary.json"
)
DEFAULT_NULL_SUMMARY = PROJECT_ROOT / "results/aim3_stage1_null_30k/stage1_summary.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results/aim3_poster_figures"

OUTPUT_BASENAME = "stage1_pass_rate_column_plot"
METADATA_NOTE = (
    "No error bars are shown because this is a deterministic summary of one "
    "generated sequence pool per condition."
)

CONDITIONS = [
    {
        "key": "rnagenesis",
        "display_name": "Unadapted RNAGenesis",
        "x_label": "Unadapted\nRNAGenesis",
        "terminal_label": "Unadapted RNAGenesis",
        "color": COLOR_RNAGENESIS,
    },
    {
        "key": "null_model",
        "display_name": "Aptadiff-A-calibrated null model",
        "x_label": "Null model\nrandom RNA",
        "terminal_label": "Null model random RNA",
        "color": COLOR_NULL_MODEL,
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot Level 1 Stage 1 hard-filter pass rates for poster preliminary results."
        )
    )
    parser.add_argument(
        "--rnagenesis-summary",
        type=Path,
        default=DEFAULT_RNAGENESIS_SUMMARY,
        help="Path to unadapted RNAGenesis stage1_summary.json (poster config run).",
    )
    parser.add_argument(
        "--null-summary",
        type=Path,
        default=DEFAULT_NULL_SUMMARY,
        help="Path to Aptadiff-A-calibrated null model stage1_summary.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for figure outputs and metadata JSON.",
    )
    return parser.parse_args()


def load_stage1_summary(path: Path) -> dict[str, Any]:
    """Load a Stage 1 summary JSON file."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def extract_pass_rate(summary: dict[str, Any]) -> dict[str, int | float]:
    """Extract generated, passed, failed counts and pass rate from a summary."""
    generated = int(summary["total_sequences"])
    passed = int(summary["passed_sequences"])
    failed = int(summary["failed_sequences"])
    pass_rate = float(summary["pass_rate"])
    return {
        "generated": generated,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "pass_rate_percent": pass_rate * 100.0,
    }


def format_count(value: int) -> str:
    """Format an integer with thousands separators."""
    return f"{value:,}"


def format_percent(value: float) -> str:
    """Format a percentage to one decimal place."""
    return f"{value:.1f}%"


def build_records(
    rnagenesis_summary_path: Path,
    null_summary_path: Path,
) -> list[dict[str, Any]]:
    """Load both summaries and assemble plotting records in display order."""
    summary_paths = {
        "rnagenesis": rnagenesis_summary_path,
        "null_model": null_summary_path,
    }
    records: list[dict[str, Any]] = []

    for condition in CONDITIONS:
        summary_path = summary_paths[condition["key"]]
        summary = load_stage1_summary(summary_path)
        stats = extract_pass_rate(summary)
        records.append(
            {
                **condition,
                "source_summary_path": str(summary_path.resolve()),
                **stats,
            }
        )

    return records


def make_pass_rate_plot(records: list[dict[str, Any]], output_dir: Path) -> dict[str, Path]:
    """Create and save the Level 1 pass-rate column chart."""
    output_dir.mkdir(parents=True, exist_ok=True)

    fig_width_in = FIG_WIDTH_PX / FIG_DPI
    fig_height_in = FIG_HEIGHT_PX / FIG_DPI
    fig, ax = plt.subplots(figsize=(fig_width_in, fig_height_in), dpi=FIG_DPI)

    x_positions = range(len(records))
    pass_rates = [record["pass_rate_percent"] for record in records]
    colors = [record["color"] for record in records]
    x_labels = [record["x_label"] for record in records]

    bars = ax.bar(
        x_positions,
        pass_rates,
        width=0.55,
        color=colors,
        edgecolor="none",
        zorder=3,
    )

    ax.set_xticks(list(x_positions))
    ax.set_xticklabels(x_labels, fontsize=11)
    ax.set_ylabel("Level 1 pass rate (%)", fontsize=12)
    ax.set_ylim(0, 100)
    ax.set_title("Level 1 pass rate", fontsize=14, fontweight="bold", pad=12)
    ax.set_xlim(-0.6, len(records) - 0.4)

    # Light horizontal gridlines only.
    ax.yaxis.grid(True, linestyle="-", linewidth=0.4, color="#DDDDDD", zorder=0)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Optional subtitle when it fits cleanly below the title.
    fig.text(
        0.5,
        0.93,
        "Same hard filters applied to both sequence pools",
        ha="center",
        va="top",
        fontsize=10,
        color="#333333",
    )

    for bar, record in zip(bars, records, strict=True):
        height = bar.get_height()
        percent_label = format_percent(record["pass_rate_percent"])
        count_label = f"{format_count(record['passed'])} / {format_count(record['generated'])}"
        count_label_on_figure = bool(height >= 18)

        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height + 2.0,
            percent_label,
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
            color="#222222",
        )

        # Place count labels inside the lower portion of each bar when readable.
        if count_label_on_figure:
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                4.0,
                count_label,
                ha="center",
                va="bottom",
                fontsize=9,
                color="white",
            )

        record["count_label"] = count_label
        record["count_label_on_figure"] = count_label_on_figure

    fig.subplots_adjust(left=0.14, right=0.96, top=0.86, bottom=0.16)

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
    records: list[dict[str, Any]],
    output_paths: dict[str, Path],
    output_dir: Path,
) -> Path:
    """Write a small JSON metadata file describing the figure inputs and outputs."""
    metadata_path = output_dir / f"{OUTPUT_BASENAME}_metadata.json"

    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "figure_title": "Level 1 pass rate",
        "figure_description": (
            "Column chart comparing Level 1 Stage 1 hard-filter pass rates for "
            "unadapted RNAGenesis generated sequences and Aptadiff-A-calibrated "
            "null model random RNA under identical hard filters."
        ),
        "note": METADATA_NOTE,
        "conditions": [
            {
                "condition_name": record["display_name"],
                "source_summary_path": record["source_summary_path"],
                "generated": record["generated"],
                "passed": record["passed"],
                "failed": record["failed"],
                "pass_rate": record["pass_rate"],
                "pass_rate_percent": round(record["pass_rate_percent"], 1),
                "count_label": record["count_label"],
                "count_label_on_figure": record["count_label_on_figure"],
            }
            for record in records
        ],
        "output_files": {key: str(path.resolve()) for key, path in output_paths.items()},
        "metadata_path": str(metadata_path.resolve()),
        "canvas_size_px": {"width": FIG_WIDTH_PX, "height": FIG_HEIGHT_PX},
        "dpi": FIG_DPI,
    }

    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    return metadata_path


def print_summary(records: list[dict[str, Any]], output_paths: dict[str, Path]) -> None:
    """Print pass-rate summary and saved output paths to the terminal."""
    rnagenesis = records[0]
    null_model = records[1]

    print(
        f"{rnagenesis['terminal_label']}: "
        f"{format_count(rnagenesis['passed'])} / {format_count(rnagenesis['generated'])} "
        f"passed = {format_percent(rnagenesis['pass_rate_percent'])}"
    )
    print(
        f"{null_model['terminal_label']}: "
        f"{format_count(null_model['passed'])} / {format_count(null_model['generated'])} "
        f"passed = {format_percent(null_model['pass_rate_percent'])}"
    )

    omitted = [record for record in records if not record["count_label_on_figure"]]
    if omitted:
        print("Count labels omitted from figure (printed here and saved in metadata):")
        for record in omitted:
            print(f"  {record['terminal_label']}: {record['count_label']}")

    print("Saved:")
    print(f"- {output_paths['png']}")
    print(f"- {output_paths['pdf']}")
    print(f"- {output_paths['svg']}")


def main() -> None:
    args = parse_args()
    records = build_records(args.rnagenesis_summary, args.null_summary)
    output_paths = make_pass_rate_plot(records, args.output_dir)
    metadata_path = save_metadata(records, output_paths, args.output_dir)
    print_summary(records, output_paths)
    print(f"- {metadata_path}")


if __name__ == "__main__":
    main()

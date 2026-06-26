#!/usr/bin/env python3
"""Build a Stage 1 hard-filter JSON config from corpus distribution artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_NAME = "scripts/make_stage1_config_from_distributions.py"


def parse_bool(value: str) -> bool:
    """Parse a simple boolean CLI value."""
    normalised = value.strip().lower()
    if normalised in {"true", "1", "yes", "y"}:
        return True
    if normalised in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected true/false, got: {value!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Stage 1 hard-filter config from corpus distribution JSON."
    )
    parser.add_argument(
        "--base-config",
        type=Path,
        required=True,
        help="Base Stage 1 config JSON (typically stage1_hard_filter_default.json).",
    )
    parser.add_argument(
        "--distributions-json",
        type=Path,
        required=True,
        help="Corpus distribution JSON from estimate_corpus_distributions.py.",
    )
    parser.add_argument(
        "--output-config",
        type=Path,
        required=True,
        help="Output Stage 1 config JSON path.",
    )
    parser.add_argument(
        "--gc-lower-quantile",
        default="q05",
        help="GC summary quantile key for lower bound (default: q05).",
    )
    parser.add_argument(
        "--gc-upper-quantile",
        default="q95",
        help="GC summary quantile key for upper bound (default: q95).",
    )
    parser.add_argument(
        "--homopolymer-threshold",
        type=int,
        default=5,
        help="Homopolymer fail threshold (default: 5).",
    )
    parser.add_argument(
        "--enable-mfe-filter",
        type=parse_bool,
        default=False,
        help="Enable MFE filter using reference MFE distribution (default: false).",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def quantile_value(summary: dict[str, Any], key: str, label: str) -> float:
    if key not in summary:
        raise KeyError(f"Missing {label} quantile key {key!r} in distribution summary.")
    value = summary[key]
    if value is None:
        raise ValueError(f"{label} quantile {key!r} is null in distribution summary.")
    return float(value)


def build_config(
    base_config: dict[str, Any],
    distributions: dict[str, Any],
    *,
    gc_lower_quantile: str,
    gc_upper_quantile: str,
    homopolymer_threshold: int,
    enable_mfe_filter: bool,
) -> dict[str, Any]:
    length_summary = distributions["length_distribution"]["summary"]
    gc_summary = distributions["gc_content_distribution"]["summary"]

    min_length = int(length_summary["min"])
    max_length = int(length_summary["max"])
    min_gc = quantile_value(gc_summary, gc_lower_quantile, "GC lower")
    max_gc = quantile_value(gc_summary, gc_upper_quantile, "GC upper")

    config = dict(base_config)
    config["min_length"] = min_length
    config["max_length"] = max_length
    config["min_gc_fraction"] = min_gc
    config["max_gc_fraction"] = max_gc
    config["homopolymer_max_run_fail_threshold"] = homopolymer_threshold
    config["enforce_homopolymer_filter"] = True

    if enable_mfe_filter:
        mfe_distribution = distributions.get("mfe_distribution")
        if not isinstance(mfe_distribution, dict):
            raise ValueError(
                "MFE filter requested but distributions JSON has no mfe_distribution object."
            )
        mfe_summary = mfe_distribution.get("summary")
        if not isinstance(mfe_summary, dict):
            raise ValueError(
                "MFE filter requested but mfe_distribution.summary is missing."
            )
        mfe_key = "q95"
        if mfe_key not in mfe_summary or mfe_summary[mfe_key] is None:
            raise ValueError(
                f"MFE filter requested but mfe_distribution.summary[{mfe_key!r}] is null."
            )
        config["max_normalised_mfe"] = float(mfe_summary[mfe_key])
    else:
        config["max_normalised_mfe"] = None

    config["near_dedup_max_edit_distance"] = None
    return config


def summary_path_for_config(output_config: Path) -> Path:
    return output_config.with_name(f"{output_config.stem}_summary.md")


def write_summary_markdown(
    path: Path,
    *,
    distributions_json: Path,
    output_config: Path,
    config: dict[str, Any],
    gc_lower_quantile: str,
    gc_upper_quantile: str,
    distributions: dict[str, Any],
) -> None:
    retained = distributions.get("counts", {}).get("retained_sequences", "unknown")
    gc_summary = distributions["gc_content_distribution"]["summary"]
    gc_mean = gc_summary.get("mean")

    lines = [
        f"# Stage 1 config summary: `{output_config.name}`",
        "",
        "Human-readable notes for the poster Stage 1 hard-filter configuration.",
        "The JSON config itself contains only keys accepted by `Stage1Config`.",
        "",
        "## Source",
        "",
        f"- Distribution JSON: `{distributions_json}`",
        f"- Generated by: `{SCRIPT_NAME}`",
        f"- Retained reference sequences: {retained}",
        "",
        "## Thresholds",
        "",
        f"- Length bounds: **{config['min_length']}–{config['max_length']} nt** "
        "(from reference length distribution min/max).",
        f"- GC bounds: **{config['min_gc_fraction']:.6f}–{config['max_gc_fraction']:.6f}** "
        f"({gc_lower_quantile}–{gc_upper_quantile} percentiles of Aptadiff A; "
        f"reference mean GC = {gc_mean:.6f}).",
        f"- Homopolymer fail threshold: run length **≥ {config['homopolymer_max_run_fail_threshold']}**.",
        "- MFE filter: **not enabled** (reference MFE distribution not used).",
        "- Near-deduplication filter: **not enabled**.",
        "",
        "## Active filters preserved from base config",
        "",
        f"- RNA alphabet validity: `{config['enforce_rna_alphabet']}`",
        f"- Leading `11` stripping: `{config['strip_leading_11']}`",
        f"- Exact deduplication: `{config['enforce_exact_deduplication']}`",
        f"- Homopolymer filter: `{config['enforce_homopolymer_filter']}`",
        "",
        "## Purpose",
        "",
        "Preliminary poster Stage 1 comparison of unadapted RNAGenesis and "
        "Aptadiff-calibrated null sequences under empirically grounded thresholds.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()

    base_config = load_json(args.base_config)
    distributions = load_json(args.distributions_json)

    config = build_config(
        base_config,
        distributions,
        gc_lower_quantile=args.gc_lower_quantile,
        gc_upper_quantile=args.gc_upper_quantile,
        homopolymer_threshold=args.homopolymer_threshold,
        enable_mfe_filter=args.enable_mfe_filter,
    )

    args.output_config.parent.mkdir(parents=True, exist_ok=True)
    with args.output_config.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")

    summary_path = summary_path_for_config(args.output_config)
    write_summary_markdown(
        summary_path,
        distributions_json=args.distributions_json,
        output_config=args.output_config,
        config=config,
        gc_lower_quantile=args.gc_lower_quantile,
        gc_upper_quantile=args.gc_upper_quantile,
        distributions=distributions,
    )

    print(f"Wrote config: {args.output_config}")
    print(f"Wrote summary: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

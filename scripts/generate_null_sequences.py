#!/usr/bin/env python3
"""Generate null-model RNA sequences from empirical corpus distributions."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

RNA_BASES = ("A", "U", "C", "G")
SCRIPT_NAME = "scripts/generate_null_sequences.py"
GENERATION_METHOD = (
    "Independent mononucleotide sampling at each position with lengths sampled "
    "from the empirical length histogram. No structural, positional, GC, MFE, "
    "motif, or homopolymer constraints are applied."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate null-model RNA sequences from a corpus distribution JSON."
    )
    parser.add_argument(
        "--distributions-json",
        type=Path,
        required=True,
        help="Path to corpus distribution JSON artifact.",
    )
    parser.add_argument(
        "--n-sequences",
        type=int,
        required=True,
        help="Number of null sequences to generate.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible generation (default: 42).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for null sequence outputs.",
    )
    parser.add_argument(
        "--output-prefix",
        default="null_sequences",
        help="Prefix for output files (default: null_sequences).",
    )
    return parser.parse_args()


def quantile_summary(values: list[float] | np.ndarray) -> dict[str, float]:
    """Compute summary statistics including selected quantiles."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "q01": None,
            "q05": None,
            "q25": None,
            "q75": None,
            "q95": None,
            "q99": None,
        }

    quantiles = np.quantile(arr, [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
    return {
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "median": float(quantiles[3]),
        "q01": float(quantiles[0]),
        "q05": float(quantiles[1]),
        "q25": float(quantiles[2]),
        "q75": float(quantiles[4]),
        "q95": float(quantiles[5]),
        "q99": float(quantiles[6]),
    }


def gc_fraction(sequence: str) -> float:
    """Return GC fraction for a non-empty sequence."""
    return (sequence.count("G") + sequence.count("C")) / len(sequence)


def load_distributions(path: Path) -> dict[str, Any]:
    """Load and validate a corpus distribution JSON artifact."""
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    frequencies = data.get("mononucleotide_frequencies")
    if not isinstance(frequencies, dict):
        raise ValueError("Distribution JSON must contain mononucleotide_frequencies.")

    missing = [base for base in RNA_BASES if base not in frequencies]
    if missing:
        raise ValueError(f"Missing mononucleotide frequencies for: {missing}")

    extra = sorted(set(frequencies) - set(RNA_BASES))
    if extra:
        raise ValueError(f"Unexpected mononucleotide frequency keys: {extra}")

    probs = np.array([float(frequencies[base]) for base in RNA_BASES], dtype=float)
    if np.any(probs < 0):
        raise ValueError("Mononucleotide frequencies must be non-negative.")

    prob_sum = float(np.sum(probs))
    if not np.isclose(prob_sum, 1.0, atol=1e-6):
        raise ValueError(f"Mononucleotide frequencies must sum to 1.0; got {prob_sum:.8f}")

    length_hist = data.get("length_distribution", {}).get("histogram")
    if not isinstance(length_hist, dict) or not length_hist:
        raise ValueError("Distribution JSON must contain length_distribution.histogram.")

    lengths: list[int] = []
    weights: list[int] = []
    for length_str, count in length_hist.items():
        count_int = int(count)
        if count_int <= 0:
            continue
        length = int(length_str)
        if length <= 0:
            raise ValueError(
                f"Length histogram contains non-positive length {length!r} with count {count_int}."
            )
        lengths.append(length)
        weights.append(count_int)

    if not lengths:
        raise ValueError("Length histogram contains no positive counts.")

    return {
        "raw": data,
        "base_frequencies": {base: float(frequencies[base]) for base in RNA_BASES},
        "lengths": lengths,
        "length_weights": weights,
        "length_histogram": {str(length): int(count) for length, count in zip(lengths, weights)},
    }


def generate_sequences(
    n_sequences: int,
    *,
    base_frequencies: dict[str, float],
    lengths: list[int],
    length_weights: list[int],
    seed: int,
) -> list[str]:
    """Sample null sequences from empirical length and mononucleotide distributions."""
    rng = np.random.default_rng(seed)
    bases = np.array(RNA_BASES)
    probs = np.array([base_frequencies[base] for base in RNA_BASES], dtype=float)

    sampled_lengths = rng.choice(lengths, size=n_sequences, replace=True, p=np.array(length_weights) / sum(length_weights))
    sequences: list[str] = []
    for length in sampled_lengths:
        sampled_bases = rng.choice(bases, size=int(length), replace=True, p=probs)
        sequences.append("".join(sampled_bases))
    return sequences


def compute_mononucleotide_frequencies(sequences: list[str]) -> dict[str, float]:
    """Compute global mononucleotide frequencies across generated sequences."""
    counter = Counter("".join(sequences))
    total = sum(counter[base] for base in RNA_BASES)
    return {base: counter[base] / total if total else 0.0 for base in RNA_BASES}


def build_records(sequences: list[str], prefix: str = "null_model") -> list[dict[str, Any]]:
    """Build per-sequence records with IDs and GC fractions."""
    records: list[dict[str, Any]] = []
    for index, sequence in enumerate(sequences, start=1):
        records.append(
            {
                "sequence_id": f"{prefix}_{index:06d}",
                "sequence": sequence,
                "length": len(sequence),
                "gc_fraction": gc_fraction(sequence),
            }
        )
    return records


def write_txt(records: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(f"{record['sequence']}\n")


def write_fasta(records: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(f">{record['sequence_id']}\n{record['sequence']}\n")


def write_csv(records: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["sequence_id", "sequence", "length", "gc_fraction"],
        )
        writer.writeheader()
        writer.writerows(records)


def build_metadata(
    *,
    distributions_path: Path,
    distributions: dict[str, Any],
    n_sequences_requested: int,
    records: list[dict[str, Any]],
    seed: int,
) -> dict[str, Any]:
    """Build JSON-serialisable generation metadata."""
    sequences = [record["sequence"] for record in records]
    lengths = [record["length"] for record in records]
    gc_values = [record["gc_fraction"] for record in records]
    duplicate_count = len(sequences) - len(set(sequences))

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "script": SCRIPT_NAME,
        "source_distributions_json": str(distributions_path.resolve()),
        "number_requested": n_sequences_requested,
        "number_generated": len(records),
        "seed": seed,
        "numpy_version": np.__version__,
        "base_frequencies_used": distributions["base_frequencies"],
        "length_histogram_used": distributions["length_histogram"],
        "generated_length_summary": quantile_summary(lengths),
        "generated_gc_summary": quantile_summary(gc_values),
        "generated_mononucleotide_frequencies": compute_mononucleotide_frequencies(sequences),
        "duplicate_count": duplicate_count,
        "generation_method": GENERATION_METHOD,
    }


def format_value(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6f}"


def write_summary_markdown(path: Path, metadata: dict[str, Any]) -> None:
    """Write a human-readable generation summary."""
    length_summary = metadata["generated_length_summary"]
    gc_summary = metadata["generated_gc_summary"]
    mono_freqs = metadata["generated_mononucleotide_frequencies"]

    lines = [
        "# Null model generation summary",
        "",
        f"**Created (UTC):** {metadata['created_at']}",
        "",
        "## Inputs",
        "",
        f"- Source distribution JSON: `{metadata['source_distributions_json']}`",
        f"- Sequences requested: {metadata['number_requested']}",
        f"- Seed: {metadata['seed']}",
        f"- NumPy version: {metadata['numpy_version']}",
        "",
        "## Reference distributions used",
        "",
        f"- Base frequencies: A={format_value(metadata['base_frequencies_used']['A'])}, "
        f"U={format_value(metadata['base_frequencies_used']['U'])}, "
        f"C={format_value(metadata['base_frequencies_used']['C'])}, "
        f"G={format_value(metadata['base_frequencies_used']['G'])}",
        f"- Length histogram: `{metadata['length_histogram_used']}`",
        "",
        "## Generated outputs",
        "",
        f"- Sequences generated: {metadata['number_generated']}",
        f"- Duplicate count: {metadata['duplicate_count']}",
        "",
        "### Generated length summary",
        "",
        f"- Min: {format_value(length_summary['min'])}",
        f"- Max: {format_value(length_summary['max'])}",
        f"- Mean: {format_value(length_summary['mean'])}",
        f"- Median: {format_value(length_summary['median'])}",
        f"- Q05: {format_value(length_summary['q05'])}",
        f"- Q95: {format_value(length_summary['q95'])}",
        "",
        "### Generated GC summary",
        "",
        f"- Min: {format_value(gc_summary['min'])}",
        f"- Max: {format_value(gc_summary['max'])}",
        f"- Mean: {format_value(gc_summary['mean'])}",
        f"- Median: {format_value(gc_summary['median'])}",
        f"- Q05: {format_value(gc_summary['q05'])}",
        f"- Q95: {format_value(gc_summary['q95'])}",
        "",
        "### Generated mononucleotide frequencies",
        "",
        f"- A: {format_value(mono_freqs['A'])}",
        f"- U: {format_value(mono_freqs['U'])}",
        f"- C: {format_value(mono_freqs['C'])}",
        f"- G: {format_value(mono_freqs['G'])}",
        "",
        "## Notes",
        "",
        (
            "This null model is calibrated to the empirical Aptadiff A length and "
            "mononucleotide distributions only. It is not structure-aware and does "
            "not impose GC, MFE, motif, or homopolymer constraints. Duplicate sequences "
            "are intentionally retained at generation time; exact deduplication belongs "
            "in Stage 1 filtering."
        ),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.n_sequences <= 0:
        print("--n-sequences must be positive.", file=sys.stderr)
        return 1

    distributions_path = args.distributions_json.expanduser().resolve()
    if not distributions_path.is_file():
        print(f"Distribution JSON not found: {distributions_path}", file=sys.stderr)
        return 1

    prefix = args.output_prefix

    try:
        distributions = load_distributions(distributions_path)
        sequences = generate_sequences(
            args.n_sequences,
            base_frequencies=distributions["base_frequencies"],
            lengths=distributions["lengths"],
            length_weights=distributions["length_weights"],
            seed=args.seed,
        )
        records = build_records(sequences, prefix=prefix)
        metadata = build_metadata(
            distributions_path=distributions_path,
            distributions=distributions,
            n_sequences_requested=args.n_sequences,
            records=records,
            seed=args.seed,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    txt_path = output_dir / f"{prefix}.txt"
    fasta_path = output_dir / f"{prefix}.fasta"
    csv_path = output_dir / f"{prefix}.csv"
    metadata_path = output_dir / "null_generation_metadata.json"
    summary_path = output_dir / "null_generation_summary.md"

    write_txt(records, txt_path)
    write_fasta(records, fasta_path)
    write_csv(records, csv_path)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    write_summary_markdown(summary_path, metadata)

    print(f"Generated {metadata['number_generated']} null sequences")
    print(f"Seed: {metadata['seed']}")
    print(f"Duplicate count: {metadata['duplicate_count']}")
    print(f"Wrote outputs to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

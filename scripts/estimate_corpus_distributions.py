#!/usr/bin/env python3
"""Estimate empirical sequence distributions from an aptamer corpus CSV."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

VALID_RNA_BASES = frozenset("AUCG")
SCRIPT_NAME = "scripts/estimate_corpus_distributions.py"
GC_BIN_WIDTH = 0.01


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate empirical distributions from a sequence corpus CSV."
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        required=True,
        help="Input CSV path containing sequences.",
    )
    parser.add_argument(
        "--sequence-column",
        default="seq",
        help="Column name containing sequences (default: seq).",
    )
    parser.add_argument(
        "--convert-dna-to-rna",
        action="store_true",
        help="Convert DNA to RNA by replacing T with U.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        required=True,
        help="Output JSON path for distribution artifact.",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        required=True,
        help="Output markdown summary path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N rows (smoke tests).",
    )
    parser.add_argument(
        "--compute-mfe",
        action="store_true",
        help="Compute ViennaRNA MFE metrics for retained sequences.",
    )
    return parser.parse_args()


def normalise_sequence(raw: Any, convert_dna_to_rna: bool) -> str:
    """Uppercase, strip whitespace, and optionally convert T to U."""
    sequence = str(raw).strip().upper()
    if convert_dna_to_rna:
        sequence = sequence.replace("T", "U")
    return sequence


def invalid_characters(sequence: str) -> str:
    """Return sorted invalid characters outside A/U/C/G."""
    return "".join(sorted({char for char in sequence if char not in VALID_RNA_BASES}))


def quantile_summary(values: list[float] | np.ndarray) -> dict[str, float]:
    """Compute standard summary statistics including selected quantiles."""
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
            "q90": None,
            "q95": None,
            "q99": None,
        }

    quantiles = np.quantile(arr, [0.01, 0.05, 0.25, 0.5, 0.75, 0.90, 0.95, 0.99])
    return {
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "median": float(quantiles[3]),
        "q01": float(quantiles[0]),
        "q05": float(quantiles[1]),
        "q25": float(quantiles[2]),
        "q75": float(quantiles[4]),
        "q90": float(quantiles[5]),
        "q95": float(quantiles[6]),
        "q99": float(quantiles[7]),
    }


def gc_fraction(sequence: str) -> float:
    """Return GC fraction for a non-empty sequence."""
    return (sequence.count("G") + sequence.count("C")) / len(sequence)


def build_gc_histogram(values: list[float]) -> dict[str, int]:
    """Build fixed-width GC histogram bins from 0.00 to 1.00."""
    histogram: dict[str, int] = {}
    for start in np.arange(0.0, 1.0, GC_BIN_WIDTH):
        label = f"{start:.2f}-{start + GC_BIN_WIDTH:.2f}"
        histogram[label] = 0

    for value in values:
        index = min(int(value / GC_BIN_WIDTH), int(1.0 / GC_BIN_WIDTH) - 1)
        start = index * GC_BIN_WIDTH
        label = f"{start:.2f}-{start + GC_BIN_WIDTH:.2f}"
        histogram[label] += 1

    return histogram


def compute_mfe_distribution(sequences: list[str]) -> dict[str, Any]:
    """Fold retained sequences with ViennaRNA and summarise MFE metrics."""
    try:
        import RNA  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "ViennaRNA Python module 'RNA' is required when --compute-mfe is set."
        ) from exc

    mfe_values: list[float] = []
    normalised_values: list[float] = []
    fold_failures: list[dict[str, Any]] = []

    for index, sequence in enumerate(sequences):
        try:
            _, mfe = RNA.fold(sequence)
            mfe_float = float(mfe)
            mfe_values.append(mfe_float)
            normalised_values.append(mfe_float / len(sequence))
        except Exception as exc:  # noqa: BLE001 - record fold failures per sequence
            fold_failures.append(
                {
                    "sequence_index": index,
                    "sequence": sequence,
                    "error": str(exc),
                }
            )

    return {
        "folded_sequences": len(mfe_values),
        "fold_failures": len(fold_failures),
        "mfe_summary": quantile_summary(mfe_values),
        "normalised_mfe_summary": quantile_summary(normalised_values),
    }


def load_and_process_sequences(
    input_csv: Path,
    sequence_column: str,
    convert_dna_to_rna: bool,
    limit: int | None,
) -> dict[str, Any]:
    """Read CSV and return retained sequences plus exclusion bookkeeping."""
    df = pd.read_csv(input_csv)
    if sequence_column not in df.columns:
        raise ValueError(
            f"Sequence column {sequence_column!r} not found. "
            f"Available columns: {list(df.columns)}"
        )

    if limit is not None:
        df = df.head(limit)

    rows_read = len(df)
    input_alphabet_observed: set[str] = set()
    invalid_examples: list[dict[str, Any]] = []

    original_sequences: list[str] = []
    converted_sequences: list[str] = []
    row_indices: list[int] = []

    excluded_empty = 0
    excluded_invalid = 0
    non_empty_sequences = 0

    for row_index, raw_value in df[sequence_column].items():
        original = str(raw_value).strip().upper()
        converted = normalise_sequence(raw_value, convert_dna_to_rna)

        if original:
            input_alphabet_observed.update(original)

        if not converted:
            excluded_empty += 1
            continue

        non_empty_sequences += 1
        invalid = invalid_characters(converted)
        if invalid:
            excluded_invalid += 1
            if len(invalid_examples) < 10:
                invalid_examples.append(
                    {
                        "row_index": int(row_index),
                        "original_sequence": original,
                        "converted_sequence": converted,
                        "invalid_characters": invalid,
                    }
                )
            continue

        original_sequences.append(original)
        converted_sequences.append(converted)
        row_indices.append(int(row_index))

    retained_counter = Counter(converted_sequences)
    unique_retained = len(retained_counter)
    duplicate_retained = sum(count - 1 for count in retained_counter.values() if count > 1)

    return {
        "rows_read": rows_read,
        "non_empty_sequences": non_empty_sequences,
        "retained_sequences": converted_sequences,
        "excluded_empty_sequences": excluded_empty,
        "excluded_invalid_alphabet": excluded_invalid,
        "unique_retained_sequences": unique_retained,
        "duplicate_retained_sequences": duplicate_retained,
        "input_alphabet_observed": sorted(input_alphabet_observed),
        "invalid_examples": invalid_examples,
    }


def build_distribution_payload(
    *,
    source_path: str,
    sequence_column: str,
    convert_dna_to_rna: bool,
    processed: dict[str, Any],
    compute_mfe: bool,
) -> dict[str, Any]:
    """Assemble the JSON distribution artifact."""
    sequences = processed["retained_sequences"]
    lengths = [len(sequence) for sequence in sequences]
    length_histogram = {str(length): count for length, count in sorted(Counter(lengths).items())}

    gc_values = [gc_fraction(sequence) for sequence in sequences]
    mono_counter = Counter("".join(sequences))
    mono_total = sum(mono_counter[base] for base in "AUCG")
    mono_frequencies = {
        base: (mono_counter[base] / mono_total if mono_total else 0.0) for base in "AUCG"
    }

    mfe_distribution = None
    if compute_mfe:
        mfe_distribution = compute_mfe_distribution(sequences)

    return {
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "script": SCRIPT_NAME,
            "source_path": source_path,
            "sequence_column": sequence_column,
            "convert_dna_to_rna": convert_dna_to_rna,
            "weighting": "unweighted_each_sequence_once",
            "notes": (
                "Aptadiff Dataset A P6 preliminary reference corpus for poster "
                "Stage 1 workflow."
            ),
        },
        "counts": {
            "rows_read": processed["rows_read"],
            "non_empty_sequences": processed["non_empty_sequences"],
            "retained_sequences": len(sequences),
            "excluded_empty_sequences": processed["excluded_empty_sequences"],
            "excluded_invalid_alphabet": processed["excluded_invalid_alphabet"],
            "unique_retained_sequences": processed["unique_retained_sequences"],
            "duplicate_retained_sequences": processed["duplicate_retained_sequences"],
        },
        "alphabet": {
            "input_alphabet_observed": processed["input_alphabet_observed"],
            "output_alphabet": ["A", "U", "C", "G"],
            "invalid_examples": processed["invalid_examples"],
        },
        "mononucleotide_counts": {base: int(mono_counter[base]) for base in "AUCG"},
        "mononucleotide_frequencies": mono_frequencies,
        "length_distribution": {
            "histogram": length_histogram,
            "summary": quantile_summary(lengths),
        },
        "gc_content_distribution": {
            "summary": quantile_summary(gc_values),
            "histogram": build_gc_histogram(gc_values),
            "values": gc_values,
        },
        "mfe_distribution": mfe_distribution,
    }


def format_summary_value(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6f}"


def write_summary_markdown(
    output_path: Path,
    payload: dict[str, Any],
    compute_mfe: bool,
) -> None:
    """Write a human-readable markdown summary."""
    metadata = payload["metadata"]
    counts = payload["counts"]
    length_summary = payload["length_distribution"]["summary"]
    gc_summary = payload["gc_content_distribution"]["summary"]
    mono_freqs = payload["mononucleotide_frequencies"]
    invalid_examples = payload["alphabet"]["invalid_examples"]

    lines = [
        "# Corpus distribution summary",
        "",
        f"**Created (UTC):** {metadata['created_at']}",
        "",
        "## Input",
        "",
        f"- Input path: `{metadata['source_path']}`",
        f"- Sequence column: `{metadata['sequence_column']}`",
        f"- DNA-to-RNA conversion: `{metadata['convert_dna_to_rna']}` (`T -> U`)",
        "- Exclusion policy: retain only sequences with alphabet `{A, U, C, G}` after conversion",
        "- Weighting: each sequence counted once; `p6` not used",
        "",
        "## Counts",
        "",
        f"- Rows read: {counts['rows_read']}",
        f"- Non-empty sequences: {counts['non_empty_sequences']}",
        f"- Retained valid sequences: {counts['retained_sequences']}",
        f"- Excluded empty sequences: {counts['excluded_empty_sequences']}",
        f"- Excluded invalid-alphabet sequences: {counts['excluded_invalid_alphabet']}",
        f"- Unique retained sequences: {counts['unique_retained_sequences']}",
        f"- Duplicate retained sequences: {counts['duplicate_retained_sequences']}",
        f"- Invalid examples recorded: {len(invalid_examples)}",
        "",
        "## Mononucleotide frequencies",
        "",
        f"- A: {format_summary_value(mono_freqs['A'])}",
        f"- U: {format_summary_value(mono_freqs['U'])}",
        f"- C: {format_summary_value(mono_freqs['C'])}",
        f"- G: {format_summary_value(mono_freqs['G'])}",
        "",
        "## Length summary",
        "",
        f"- Min: {format_summary_value(length_summary['min'])}",
        f"- Max: {format_summary_value(length_summary['max'])}",
        f"- Mean: {format_summary_value(length_summary['mean'])}",
        f"- Median: {format_summary_value(length_summary['median'])}",
        f"- Q05: {format_summary_value(length_summary['q05'])}",
        f"- Q95: {format_summary_value(length_summary['q95'])}",
        "",
        "## GC content summary",
        "",
        f"- Min: {format_summary_value(gc_summary['min'])}",
        f"- Max: {format_summary_value(gc_summary['max'])}",
        f"- Mean: {format_summary_value(gc_summary['mean'])}",
        f"- Median: {format_summary_value(gc_summary['median'])}",
        f"- Q05: {format_summary_value(gc_summary['q05'])}",
        f"- Q95: {format_summary_value(gc_summary['q95'])}",
        "",
        "## MFE",
        "",
        f"- MFE computed: `{compute_mfe}`",
        "",
    ]

    mfe_distribution = payload.get("mfe_distribution")
    if isinstance(mfe_distribution, dict):
        norm_summary = mfe_distribution.get("normalised_mfe_summary", {})
        mfe_summary = mfe_distribution.get("mfe_summary", {})
        lines.extend(
            [
                f"- Folded sequences: {mfe_distribution.get('folded_sequences', 'n/a')}",
                f"- Fold failures: {mfe_distribution.get('fold_failures', 'n/a')}",
                "",
                "### Raw MFE summary",
                "",
                f"- Mean: {format_summary_value(mfe_summary.get('mean'))}",
                f"- Q90: {format_summary_value(mfe_summary.get('q90'))}",
                f"- Q95: {format_summary_value(mfe_summary.get('q95'))}",
                f"- Q99: {format_summary_value(mfe_summary.get('q99'))}",
                "",
                "### Normalised MFE summary (MFE / length)",
                "",
                f"- Mean: {format_summary_value(norm_summary.get('mean'))}",
                f"- Q90: {format_summary_value(norm_summary.get('q90'))}",
                f"- Q95: {format_summary_value(norm_summary.get('q95'))}",
                f"- Q99: {format_summary_value(norm_summary.get('q99'))}",
                "",
            ]
        )

    lines.extend(
        [
        "## Notes",
        "",
        (
            "This artifact is based on the preliminary Aptadiff Dataset A P6 subset. "
            "It is intended for poster Stage 1 null-model calibration and will later be "
            "replaced by distributions estimated from the full curated aptamer corpus."
        ),
        "",
        ]
    )

    if invalid_examples:
        lines.extend(["## Invalid examples", ""])
        for example in invalid_examples:
            lines.append(
                f"- Row {example['row_index']}: invalid={example['invalid_characters']} "
                f"original=`{example['original_sequence']}` "
                f"converted=`{example['converted_sequence']}`"
            )
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_json(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    input_csv = args.input_csv.expanduser().resolve()
    if not input_csv.is_file():
        print(f"Input CSV not found: {input_csv}", file=sys.stderr)
        return 1

    try:
        processed = load_and_process_sequences(
            input_csv=input_csv,
            sequence_column=args.sequence_column,
            convert_dna_to_rna=args.convert_dna_to_rna,
            limit=args.limit,
        )
        payload = build_distribution_payload(
            source_path=str(input_csv),
            sequence_column=args.sequence_column,
            convert_dna_to_rna=args.convert_dna_to_rna,
            processed=processed,
            compute_mfe=args.compute_mfe,
        )
    except (ValueError, ImportError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    write_json(args.output_json.expanduser().resolve(), payload)
    write_summary_markdown(
        args.output_summary.expanduser().resolve(),
        payload,
        compute_mfe=args.compute_mfe,
    )

    counts = payload["counts"]
    print(f"Rows read: {counts['rows_read']}")
    print(f"Retained sequences: {counts['retained_sequences']}")
    print(f"Excluded invalid-alphabet: {counts['excluded_invalid_alphabet']}")
    print(f"Wrote JSON to {args.output_json.resolve()}")
    print(f"Wrote summary to {args.output_summary.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

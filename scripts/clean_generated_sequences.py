"""Clean RNAGenesis aptamer generation output and export auditable CSV/FASTA."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

VALID_RNA_BASES = frozenset("AUCG")
LEADING_ARTIFACT_PREFIX = "11"
OUTPUT_COLUMNS = [
    "sequence_id",
    "source_file",
    "condition",
    "raw_sequence",
    "cleaned_sequence",
    "raw_length",
    "cleaned_length",
    "had_leading_11",
    "valid_rna_alphabet",
    "invalid_chars",
    "is_duplicate_within_condition",
    "cleaning_status",
]


def find_input_files(input_dir: Path, pattern: str = "*.txt") -> list[Path]:
    """Return sorted .txt files directly under input_dir."""
    return sorted(input_dir.glob(pattern))


def read_sequences_from_file(path: Path) -> list[str]:
    """Read non-blank lines from a text file."""
    sequences: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip().upper()
            if raw:
                sequences.append(raw)
    return sequences


def strip_leading_artifact(raw_sequence: str) -> tuple[str, bool]:
    """Remove a leading '11' decoder prefix when present."""
    if raw_sequence.startswith(LEADING_ARTIFACT_PREFIX):
        return raw_sequence[len(LEADING_ARTIFACT_PREFIX) :], True
    return raw_sequence, False


def validate_rna_alphabet(sequence: str) -> tuple[bool, str]:
    """Return whether sequence uses only A/U/C/G and any invalid characters."""
    invalid = sorted({char for char in sequence if char not in VALID_RNA_BASES})
    return not invalid, "".join(invalid)


def assign_cleaning_status(cleaned_sequence: str, valid_rna_alphabet: bool) -> str:
    """Classify the cleaning outcome for auditability."""
    if not cleaned_sequence:
        return "empty"
    if not valid_rna_alphabet:
        return "invalid_alphabet"
    return "ok"


def make_sequence_id(condition: str, source_file: str, index: int) -> str:
    """Build a stable identifier for one sequence row."""
    source_stem = Path(source_file).stem
    return f"{condition}_{source_stem}_{index:05d}"


def build_records(
    input_files: list[Path],
    condition: str,
) -> list[dict[str, object]]:
    """Parse input files and return one audit record per sequence."""
    records: list[dict[str, object]] = []

    for path in input_files:
        source_file = path.name
        for line_index, raw_sequence in enumerate(read_sequences_from_file(path), start=1):
            cleaned_sequence, had_leading_11 = strip_leading_artifact(raw_sequence)
            valid_rna_alphabet, invalid_chars = validate_rna_alphabet(cleaned_sequence)

            records.append(
                {
                    "sequence_id": make_sequence_id(condition, source_file, line_index),
                    "source_file": source_file,
                    "condition": condition,
                    "raw_sequence": raw_sequence,
                    "cleaned_sequence": cleaned_sequence,
                    "raw_length": len(raw_sequence),
                    "cleaned_length": len(cleaned_sequence),
                    "had_leading_11": had_leading_11,
                    "valid_rna_alphabet": valid_rna_alphabet,
                    "invalid_chars": invalid_chars,
                    "is_duplicate_within_condition": False,
                    "cleaning_status": assign_cleaning_status(
                        cleaned_sequence, valid_rna_alphabet
                    ),
                }
            )

    duplicate_counts = Counter(
        record["cleaned_sequence"]
        for record in records
        if record["cleaned_sequence"]
    )
    for record in records:
        cleaned = record["cleaned_sequence"]
        record["is_duplicate_within_condition"] = bool(
            cleaned and duplicate_counts[cleaned] > 1
        )

    return records


def records_to_dataframe(records: list[dict[str, object]]) -> pd.DataFrame:
    """Build a DataFrame with a stable column schema, including when empty."""
    return pd.DataFrame(records, columns=OUTPUT_COLUMNS)


def write_fasta(df: pd.DataFrame, output_path: Path) -> int:
    """Write valid non-empty cleaned sequences to FASTA; return count written."""
    valid_df = df[
        (df["cleaning_status"] == "ok")
        & df["cleaned_sequence"].astype(str).str.len().gt(0)
    ]

    with output_path.open("w", encoding="utf-8") as handle:
        for row in valid_df.itertuples(index=False):
            header = f">{row.sequence_id} condition={row.condition} source_file={row.source_file}"
            handle.write(f"{header}\n{row.cleaned_sequence}\n")

    return len(valid_df)


def write_cleaning_summary(
    output_path: Path,
    input_dir: Path,
    condition: str,
    input_files: list[Path],
    df: pd.DataFrame,
    fasta_count: int,
) -> None:
    """Write a human-readable summary of cleaning results."""
    status_counts = df["cleaning_status"].value_counts().to_dict()
    duplicate_sequences = int(
        df.loc[df["is_duplicate_within_condition"], "cleaned_sequence"].nunique()
    )
    duplicate_rows = int(df["is_duplicate_within_condition"].sum())

    lines = [
        "RNAGenesis sequence cleaning summary",
        "===================================",
        f"Input directory: {input_dir}",
        f"Condition: {condition}",
        f"Input files: {len(input_files)}",
        f"Total sequences: {len(df)}",
        f"Leading '11' stripped: {int(df['had_leading_11'].sum())}",
        f"Valid RNA alphabet: {int(df['valid_rna_alphabet'].sum())}",
        f"Invalid alphabet rows: {status_counts.get('invalid_alphabet', 0)}",
        f"Empty after cleaning: {status_counts.get('empty', 0)}",
        f"Duplicate cleaned sequences: {duplicate_sequences}",
        f"Rows marked duplicate: {duplicate_rows}",
        f"FASTA sequences written: {fasta_count}",
        "",
        "Cleaning status counts:",
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"  {status}: {count}")

    if input_files:
        lines.extend(["", "Source files:"])
        lines.extend(f"  - {path.name}" for path in input_files)

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def clean_generated_sequences(
    input_dir: Path,
    condition: str,
    output_dir: Path | None = None,
    pattern: str = "*.txt",
) -> pd.DataFrame:
    """Clean sequences from input_dir and write outputs under output_dir."""
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    input_files = find_input_files(input_dir, pattern=pattern)
    if not input_files:
        raise FileNotFoundError(
            f"No files matching '{pattern}' found in {input_dir}"
        )

    resolved_output_dir = output_dir or (input_dir / "cleaned")
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    records = build_records(input_files, condition)
    df = records_to_dataframe(records)

    csv_path = resolved_output_dir / "cleaned_sequences.csv"
    fasta_path = resolved_output_dir / "cleaned_sequences.fasta"
    summary_path = resolved_output_dir / "cleaning_summary.txt"

    df.to_csv(csv_path, index=False)
    fasta_count = write_fasta(df, fasta_path)
    write_cleaning_summary(
        summary_path,
        input_dir=input_dir,
        condition=condition,
        input_files=input_files,
        df=df,
        fasta_count=fasta_count,
    )

    return df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Clean RNAGenesis aptamer generation output: strip decoder artefacts, "
            "validate RNA alphabet, and export CSV/FASTA."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Run directory containing raw .txt sequence files (e.g. results/phase2_medium_test).",
    )
    parser.add_argument(
        "--condition",
        required=True,
        help="Condition label recorded in outputs (e.g. unadapted_rnagenesis).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: <input-dir>/cleaned).",
    )
    parser.add_argument(
        "--pattern",
        default="*.txt",
        help=(
            "Glob pattern for input files within input-dir (default: *.txt). "
            "For RNAGenesis outputs, use seqs_*.txt."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = clean_generated_sequences(
        input_dir=args.input_dir,
        condition=args.condition,
        output_dir=args.output_dir,
        pattern=args.pattern,
    )
    output_dir = args.output_dir or (args.input_dir / "cleaned")
    print(f"Processed {len(df)} sequences from {args.input_dir}")
    print(f"Wrote outputs to {output_dir}")


if __name__ == "__main__":
    main()

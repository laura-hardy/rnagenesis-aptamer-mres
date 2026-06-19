"""Input/output helpers for Aim 3 pipeline."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

VALID_RNA_BASES = frozenset("AUCG")
LEADING_ARTIFACT_PREFIX = "11"

STAGE1_OUTPUT_COLUMNS = [
    "sequence_id",
    "condition",
    "source_file",
    "source_row",
    "raw_sequence",
    "cleaned_sequence",
    "raw_length",
    "cleaned_length",
    "cleaning_notes",
    "alphabet_valid",
    "length_filter_status",
    "passes_length_filter",
    "duplicate_rank_within_condition",
    "duplicate_representative_id",
    "is_exact_duplicate_within_condition",
    "passes_exact_dedup",
    "max_homopolymer_run",
    "passes_homopolymer_filter",
    "gc_fraction",
    "gc_filter_status",
    "passes_gc_filter",
    "mfe_structure",
    "mfe",
    "normalised_mfe",
    "mfe_filter_status",
    "passes_mfe_filter",
    "nearest_reference_edit_distance",
    "near_dedup_filter_status",
    "passes_near_dedup_filter",
    "stage1_pass",
    "stage1_failure_reasons",
]


def resolve_input_files(input_glob: str) -> list[Path]:
    """Expand a glob pattern to sorted input file paths."""
    from glob import glob

    matches = sorted(Path(p) for p in glob(input_glob))
    files = [p for p in matches if p.is_file()]
    if not files:
        raise FileNotFoundError(f"No files matched input glob: {input_glob}")
    return files


def read_sequences_from_file(path: Path) -> list[str]:
    """Read non-blank lines from a text file, uppercased."""
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


def make_sequence_id(condition: str, source_file: str, index: int) -> str:
    """Build a stable identifier for one sequence row."""
    source_stem = Path(source_file).stem
    return f"{condition}_{source_stem}_{index:05d}"


def load_reference_sequences(path: Path) -> list[str]:
    """Load reference/training sequences from FASTA, CSV, or plain text."""
    suffix = path.suffix.lower()
    sequences: list[str] = []

    if suffix in {".fa", ".fasta", ".fna"}:
        current: list[str] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                if line.startswith(">"):
                    if current:
                        sequences.append("".join(current).upper())
                        current = []
                else:
                    current.append(line)
            if current:
                sequences.append("".join(current).upper())
    elif suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError(f"CSV has no header: {path}")
            seq_col = None
            for candidate in ("cleaned_sequence", "sequence", "seq", "rna_sequence"):
                if candidate in reader.fieldnames:
                    seq_col = candidate
                    break
            if seq_col is None:
                raise ValueError(
                    f"CSV must contain a sequence column (cleaned_sequence, sequence, seq): {path}"
                )
            for row in reader:
                seq = (row.get(seq_col) or "").strip().upper()
                if seq:
                    sequences.append(seq)
    else:
        sequences = read_sequences_from_file(path)

    if not sequences:
        raise ValueError(f"No sequences loaded from reference corpus: {path}")
    return sequences


def records_to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a DataFrame with the Stage 1 column schema."""
    return pd.DataFrame(records, columns=STAGE1_OUTPUT_COLUMNS)


def write_fasta(df: pd.DataFrame, output_path: Path) -> int:
    """Write passed cleaned sequences to FASTA."""
    count = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for row in df.itertuples(index=False):
            header = (
                f">{row.sequence_id} condition={row.condition} "
                f"source_file={row.source_file}"
            )
            handle.write(f"{header}\n{row.cleaned_sequence}\n")
            count += 1
    return count


def write_stage1_outputs(
    df: pd.DataFrame,
    output_dir: Path,
    *,
    config_path: Path,
    input_glob: str,
    condition: str,
    input_files: list[Path],
    write_fasta_file: bool,
    skip_mfe: bool,
    reference_corpus: Path | None,
    limit: int | None,
) -> dict[str, Path]:
    """Write all Stage 1 output artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)

    all_path = output_dir / "stage1_all_sequences.csv"
    passed_path = output_dir / "stage1_passed_sequences.csv"
    failed_path = output_dir / "stage1_failed_sequences.csv"
    summary_path = output_dir / "stage1_summary.json"
    counts_path = output_dir / "stage1_filter_counts.csv"
    notes_path = output_dir / "stage1_run_notes.md"

    df.to_csv(all_path, index=False)

    passed_df = df[df["stage1_pass"]].copy()
    failed_df = df[~df["stage1_pass"]].copy()
    passed_df.to_csv(passed_path, index=False)
    failed_df.to_csv(failed_path, index=False)

    filter_counts = compute_filter_counts(df)
    filter_counts.to_csv(counts_path, index=False)

    summary = build_summary_payload(
        df=df,
        config_path=config_path,
        input_glob=input_glob,
        condition=condition,
        input_files=input_files,
        skip_mfe=skip_mfe,
        reference_corpus=reference_corpus,
        limit=limit,
        filter_counts=filter_counts,
    )
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    notes_path.write_text(build_run_notes_markdown(summary), encoding="utf-8")

    output_paths: dict[str, Path] = {
        "all": all_path,
        "passed": passed_path,
        "failed": failed_path,
        "summary": summary_path,
        "counts": counts_path,
        "notes": notes_path,
    }

    if write_fasta_file and len(passed_df) > 0:
        fasta_path = output_dir / "stage1_passed_sequences.fasta"
        write_fasta(passed_df, fasta_path)
        output_paths["fasta"] = fasta_path

    return output_paths


def compute_filter_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Summarise pass/fail/not-applied counts per filter."""
    rows: list[dict[str, Any]] = []
    total = len(df)

    specs = [
        ("alphabet", "alphabet_valid", None, "enforce_rna_alphabet"),
        ("length", "passes_length_filter", "length_filter_status", None),
        ("exact_dedup", "passes_exact_dedup", None, None),
        ("homopolymer", "passes_homopolymer_filter", None, None),
        ("gc", "passes_gc_filter", "gc_filter_status", None),
        ("mfe", "passes_mfe_filter", "mfe_filter_status", None),
        ("near_dedup", "passes_near_dedup_filter", "near_dedup_filter_status", None),
    ]

    for name, pass_col, status_col, _ in specs:
        if pass_col not in df.columns:
            continue
        if status_col and status_col in df.columns:
            for status, group in df.groupby(status_col, dropna=False):
                rows.append(
                    {
                        "filter": name,
                        "status": status,
                        "count": len(group),
                        "fraction": len(group) / total if total else 0.0,
                    }
                )
        else:
            passed = int(df[pass_col].sum())
            failed = total - passed
            rows.append(
                {
                    "filter": name,
                    "status": "applied_pass",
                    "count": passed,
                    "fraction": passed / total if total else 0.0,
                }
            )
            rows.append(
                {
                    "filter": name,
                    "status": "applied_fail",
                    "count": failed,
                    "fraction": failed / total if total else 0.0,
                }
            )

    rows.append(
        {
            "filter": "stage1_overall",
            "status": "pass",
            "count": int(df["stage1_pass"].sum()),
            "fraction": df["stage1_pass"].mean() if total else 0.0,
        }
    )
    rows.append(
        {
            "filter": "stage1_overall",
            "status": "fail",
            "count": int((~df["stage1_pass"]).sum()),
            "fraction": (~df["stage1_pass"]).mean() if total else 0.0,
        }
    )
    return pd.DataFrame(rows)


def build_summary_payload(
    *,
    df: pd.DataFrame,
    config_path: Path,
    input_glob: str,
    condition: str,
    input_files: list[Path],
    skip_mfe: bool,
    reference_corpus: Path | None,
    limit: int | None,
    filter_counts: pd.DataFrame,
) -> dict[str, Any]:
    """Build JSON-serialisable run summary."""
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "stage1_hard_filter",
        "condition": condition,
        "config_path": str(config_path.resolve()),
        "input_glob": input_glob,
        "input_files": [str(p.resolve()) for p in input_files],
        "reference_corpus": str(reference_corpus.resolve()) if reference_corpus else None,
        "limit": limit,
        "skip_mfe": skip_mfe,
        "total_sequences": len(df),
        "passed_sequences": int(df["stage1_pass"].sum()),
        "failed_sequences": int((~df["stage1_pass"]).sum()),
        "pass_rate": float(df["stage1_pass"].mean()) if len(df) else 0.0,
        "filter_counts": filter_counts.to_dict(orient="records"),
    }


def build_run_notes_markdown(summary: dict[str, Any]) -> str:
    """Render human-readable run notes."""
    lines = [
        "# Stage 1 hard filtering run notes",
        "",
        f"**Timestamp (UTC):** {summary['timestamp_utc']}",
        f"**Condition:** {summary['condition']}",
        f"**Config:** `{summary['config_path']}`",
        f"**Input glob:** `{summary['input_glob']}`",
        "",
        "## Counts",
        "",
        f"- Total sequences: {summary['total_sequences']}",
        f"- Passed Stage 1: {summary['passed_sequences']}",
        f"- Failed Stage 1: {summary['failed_sequences']}",
        f"- Pass rate: {summary['pass_rate']:.4%}",
        "",
        "## Options",
        "",
        f"- Reference corpus: `{summary['reference_corpus'] or 'none'}`",
        f"- Limit: {summary['limit']}",
        f"- Skip MFE: {summary['skip_mfe']}",
        "",
        "## Input files",
        "",
    ]
    for path in summary["input_files"]:
        lines.append(f"- `{path}`")
    lines.extend(["", "## Filter counts", ""])
    for row in summary["filter_counts"]:
        lines.append(
            f"- {row['filter']} / {row['status']}: {row['count']} "
            f"({row['fraction']:.4%})"
        )
    return "\n".join(lines) + "\n"

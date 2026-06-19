"""Stage 1 hard filtering for intrinsic RNA sequence quality."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from aim3_pipeline.config import Stage1Config
from aim3_pipeline.io import (
    make_sequence_id,
    read_sequences_from_file,
    records_to_dataframe,
    strip_leading_artifact,
    validate_rna_alphabet,
    write_stage1_outputs,
    load_reference_sequences,
)


class RNAImportError(ImportError):
    """Raised when ViennaRNA is required but unavailable."""


class EditDistanceDependencyError(ImportError):
    """Raised when near-dedup needs Levenshtein/rapidfuzz but neither is installed."""


def try_import_rna() -> Any:
    """Import ViennaRNA Python module or raise a clear error."""
    try:
        import RNA  # noqa: PLC0415

        return RNA
    except ImportError as exc:
        raise RNAImportError(
            "ViennaRNA Python module 'RNA' is required for MFE calculation. "
            "Install viennarna in your environment (e.g. conda install -c bioconda viennarna "
            "or pip install viennarna)."
        ) from exc


def try_import_edit_distance() -> tuple[Any, str]:
    """Return (distance_function, backend_name) using rapidfuzz or Levenshtein."""
    try:
        from rapidfuzz.distance import Levenshtein as rf_levenshtein  # noqa: PLC0415

        return rf_levenshtein.distance, "rapidfuzz"
    except ImportError:
        pass
    try:
        import Levenshtein  # noqa: PLC0415

        return Levenshtein.distance, "python-Levenshtein"
    except ImportError as exc:
        raise EditDistanceDependencyError(
            "Near-deduplication against a reference corpus requires 'rapidfuzz' or "
            "'python-Levenshtein'. Install one of these packages, or omit --reference-corpus."
        ) from exc


def compute_max_homopolymer_run(sequence: str) -> int:
    """Return the length of the longest contiguous identical-base run."""
    if not sequence:
        return 0
    max_run = 1
    current_run = 1
    for index in range(1, len(sequence)):
        if sequence[index] == sequence[index - 1]:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 1
    return max_run


def compute_gc_fraction(sequence: str) -> float | None:
    """Return GC fraction for a non-empty sequence."""
    if not sequence:
        return None
    gc_count = sequence.count("G") + sequence.count("C")
    return gc_count / len(sequence)


def compute_mfe(sequence: str, rna_module: Any | None = None) -> tuple[str, float]:
    """Fold sequence with ViennaRNA and return (structure, mfe)."""
    rna = rna_module or try_import_rna()
    structure, mfe = rna.fold(sequence)
    return structure, float(mfe)


def compute_nearest_edit_distance(
    query: str,
    references: list[str],
    distance_fn: Any,
) -> int | None:
    """Return minimum edit distance to any reference sequence."""
    if not query or not references:
        return None
    return min(int(distance_fn(query, ref)) for ref in references)


def build_preprocessed_records(
    input_files: list[Path],
    condition: str,
    config: Stage1Config,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Parse raw inputs into preprocessed records before filter application."""
    records: list[dict[str, Any]] = []

    for path in input_files:
        source_file = path.name
        for line_index, raw_sequence in enumerate(read_sequences_from_file(path), start=1):
            if limit is not None and len(records) >= limit:
                return records

            cleaned_sequence = raw_sequence
            notes: list[str] = []
            if config.strip_leading_11:
                cleaned_sequence, stripped = strip_leading_artifact(raw_sequence)
                if stripped:
                    notes.append("stripped_leading_11")

            alphabet_valid, invalid_chars = validate_rna_alphabet(cleaned_sequence)
            if invalid_chars:
                notes.append(f"invalid_chars={invalid_chars}")
            if not cleaned_sequence:
                notes.append("empty_after_cleaning")

            records.append(
                {
                    "sequence_id": make_sequence_id(condition, source_file, line_index),
                    "condition": condition,
                    "source_file": source_file,
                    "source_row": line_index,
                    "raw_sequence": raw_sequence,
                    "cleaned_sequence": cleaned_sequence,
                    "raw_length": len(raw_sequence),
                    "cleaned_length": len(cleaned_sequence),
                    "cleaning_notes": ";".join(notes) if notes else "",
                    "alphabet_valid": alphabet_valid and bool(cleaned_sequence),
                }
            )

    return records


def assign_exact_deduplication(records: list[dict[str, Any]]) -> None:
    """Mark exact duplicate ranks within condition in-place."""
    seen: dict[str, str] = {}
    rank_counter: defaultdict[str, int] = defaultdict(int)

    for record in records:
        seq = record["cleaned_sequence"]
        if not seq:
            record["duplicate_rank_within_condition"] = 0
            record["duplicate_representative_id"] = ""
            record["is_exact_duplicate_within_condition"] = False
            continue

        rank_counter[seq] += 1
        rank = rank_counter[seq]
        record["duplicate_rank_within_condition"] = rank

        if rank == 1:
            seen[seq] = record["sequence_id"]
            record["duplicate_representative_id"] = record["sequence_id"]
            record["is_exact_duplicate_within_condition"] = False
        else:
            record["duplicate_representative_id"] = seen[seq]
            record["is_exact_duplicate_within_condition"] = True


def apply_length_filter(record: dict[str, Any], config: Stage1Config) -> None:
    """Apply optional length bounds."""
    length = record["cleaned_length"]
    if not config.length_filter_enabled():
        record["length_filter_status"] = "not_applied"
        record["passes_length_filter"] = True
        return

    reasons: list[str] = []
    if config.min_length is not None and length < config.min_length:
        reasons.append(f"length<{config.min_length}")
    if config.max_length is not None and length > config.max_length:
        reasons.append(f"length>{config.max_length}")

    if reasons:
        record["length_filter_status"] = "applied_fail"
        record["passes_length_filter"] = False
        record.setdefault("_length_fail_reasons", []).extend(reasons)
    else:
        record["length_filter_status"] = "applied_pass"
        record["passes_length_filter"] = True


def apply_homopolymer_filter(record: dict[str, Any], config: Stage1Config) -> None:
    """Apply homopolymer run filter."""
    seq = record["cleaned_sequence"]
    max_run = compute_max_homopolymer_run(seq) if seq else 0
    record["max_homopolymer_run"] = max_run

    if not config.enforce_homopolymer_filter:
        record["passes_homopolymer_filter"] = True
        return

    if not seq or not record["alphabet_valid"]:
        record["passes_homopolymer_filter"] = False
        record.setdefault("_homopolymer_fail_reasons", []).append("invalid_or_empty_sequence")
        return

    threshold = config.homopolymer_max_run_fail_threshold
    if max_run >= threshold:
        record["passes_homopolymer_filter"] = False
        record.setdefault("_homopolymer_fail_reasons", []).append(
            f"homopolymer_run>={threshold}"
        )
    else:
        record["passes_homopolymer_filter"] = True


def apply_gc_filter(record: dict[str, Any], config: Stage1Config) -> None:
    """Compute GC fraction and apply optional bounds."""
    seq = record["cleaned_sequence"]
    gc_fraction = compute_gc_fraction(seq) if seq and record["alphabet_valid"] else None
    record["gc_fraction"] = gc_fraction

    if not config.gc_filter_enabled():
        record["gc_filter_status"] = "not_applied"
        record["passes_gc_filter"] = True
        return

    if gc_fraction is None:
        record["gc_filter_status"] = "applied_fail"
        record["passes_gc_filter"] = False
        record.setdefault("_gc_fail_reasons", []).append("gc_unavailable")
        return

    reasons: list[str] = []
    if config.min_gc_fraction is not None and gc_fraction < config.min_gc_fraction:
        reasons.append(f"gc<{config.min_gc_fraction}")
    if config.max_gc_fraction is not None and gc_fraction > config.max_gc_fraction:
        reasons.append(f"gc>{config.max_gc_fraction}")

    if reasons:
        record["gc_filter_status"] = "applied_fail"
        record["passes_gc_filter"] = False
        record.setdefault("_gc_fail_reasons", []).extend(reasons)
    else:
        record["gc_filter_status"] = "applied_pass"
        record["passes_gc_filter"] = True


def apply_mfe_filter(
    record: dict[str, Any],
    config: Stage1Config,
    *,
    skip_mfe: bool,
    rna_module: Any | None,
) -> None:
    """Compute MFE metrics and apply optional normalised MFE threshold."""
    if skip_mfe:
        record["mfe_structure"] = ""
        record["mfe"] = None
        record["normalised_mfe"] = None
        record["mfe_filter_status"] = "skipped"
        record["passes_mfe_filter"] = True
        return

    seq = record["cleaned_sequence"]
    if not seq or not record["alphabet_valid"]:
        record["mfe_structure"] = ""
        record["mfe"] = None
        record["normalised_mfe"] = None
        record["mfe_filter_status"] = "applied_fail"
        record["passes_mfe_filter"] = False
        record.setdefault("_mfe_fail_reasons", []).append("mfe_unavailable")
        return

    structure, mfe = compute_mfe(seq, rna_module=rna_module)
    normalised = mfe / record["cleaned_length"]
    record["mfe_structure"] = structure
    record["mfe"] = mfe
    record["normalised_mfe"] = normalised

    if not config.mfe_filter_enabled():
        record["mfe_filter_status"] = "not_applied"
        record["passes_mfe_filter"] = True
        return

    if normalised > config.max_normalised_mfe:
        record["mfe_filter_status"] = "applied_fail"
        record["passes_mfe_filter"] = False
        record.setdefault("_mfe_fail_reasons", []).append(
            f"normalised_mfe>{config.max_normalised_mfe}"
        )
    else:
        record["mfe_filter_status"] = "applied_pass"
        record["passes_mfe_filter"] = True


def apply_near_dedup_filter(
    record: dict[str, Any],
    config: Stage1Config,
    *,
    reference_sequences: list[str] | None,
    distance_fn: Any | None,
) -> None:
    """Apply optional near-deduplication against a reference corpus."""
    if reference_sequences is None:
        record["nearest_reference_edit_distance"] = None
        record["near_dedup_filter_status"] = "not_applied_reference_missing"
        record["passes_near_dedup_filter"] = True
        return

    seq = record["cleaned_sequence"]
    if not seq or not record["alphabet_valid"]:
        record["nearest_reference_edit_distance"] = None
        record["near_dedup_filter_status"] = "applied_fail"
        record["passes_near_dedup_filter"] = False
        record.setdefault("_near_dedup_fail_reasons", []).append("near_dedup_unavailable")
        return

    nearest = compute_nearest_edit_distance(seq, reference_sequences, distance_fn)
    record["nearest_reference_edit_distance"] = nearest

    if config.near_dedup_max_edit_distance is None:
        record["near_dedup_filter_status"] = "not_applied"
        record["passes_near_dedup_filter"] = True
        return

    if nearest is not None and nearest <= config.near_dedup_max_edit_distance:
        record["near_dedup_filter_status"] = "applied_fail"
        record["passes_near_dedup_filter"] = False
        record.setdefault("_near_dedup_fail_reasons", []).append(
            f"near_duplicate<={config.near_dedup_max_edit_distance}"
        )
    else:
        record["near_dedup_filter_status"] = "applied_pass"
        record["passes_near_dedup_filter"] = True


def apply_exact_dedup_filter(record: dict[str, Any], config: Stage1Config) -> None:
    """Apply exact within-condition deduplication."""
    if not config.enforce_exact_deduplication:
        record["passes_exact_dedup"] = True
        return

    if record.get("duplicate_rank_within_condition", 0) <= 1:
        record["passes_exact_dedup"] = True
    else:
        record["passes_exact_dedup"] = False
        record.setdefault("_exact_dedup_fail_reasons", []).append("exact_duplicate")


def finalise_stage1_record(record: dict[str, Any], config: Stage1Config) -> None:
    """Compute stage1_pass and stage1_failure_reasons."""
    reasons: list[str] = []

    if config.enforce_rna_alphabet and not record["alphabet_valid"]:
        reasons.append("invalid_alphabet")

    if not record.get("passes_length_filter", True):
        reasons.extend(record.pop("_length_fail_reasons", []))

    if config.enforce_exact_deduplication and not record.get("passes_exact_dedup", True):
        reasons.extend(record.pop("_exact_dedup_fail_reasons", []))

    if config.enforce_homopolymer_filter and not record.get("passes_homopolymer_filter", True):
        reasons.extend(record.pop("_homopolymer_fail_reasons", []))

    if not record.get("passes_gc_filter", True):
        reasons.extend(record.pop("_gc_fail_reasons", []))

    if not record.get("passes_mfe_filter", True):
        reasons.extend(record.pop("_mfe_fail_reasons", []))

    if not record.get("passes_near_dedup_filter", True):
        reasons.extend(record.pop("_near_dedup_fail_reasons", []))

    record["stage1_failure_reasons"] = ";".join(reasons)
    record["stage1_pass"] = not reasons


def run_stage1_hard_filter(
    *,
    input_files: list[Path],
    condition: str,
    config: Stage1Config,
    output_dir: Path,
    config_path: Path,
    input_glob: str,
    reference_corpus: Path | None = None,
    limit: int | None = None,
    skip_mfe: bool = False,
) -> pd.DataFrame:
    """Run Stage 1 hard filtering and write outputs."""
    records = build_preprocessed_records(input_files, condition, config, limit=limit)
    assign_exact_deduplication(records)

    reference_sequences: list[str] | None = None
    distance_fn = None
    if reference_corpus is not None:
        reference_sequences = load_reference_sequences(reference_corpus)
        distance_fn, _ = try_import_edit_distance()

    rna_module = None
    if not skip_mfe:
        rna_module = try_import_rna()

    for record in records:
        apply_length_filter(record, config)
        apply_exact_dedup_filter(record, config)
        apply_homopolymer_filter(record, config)
        apply_gc_filter(record, config)
        apply_mfe_filter(record, config, skip_mfe=skip_mfe, rna_module=rna_module)
        apply_near_dedup_filter(
            record,
            config,
            reference_sequences=reference_sequences,
            distance_fn=distance_fn,
        )
        finalise_stage1_record(record, config)

    df = records_to_dataframe(records)
    write_stage1_outputs(
        df,
        output_dir,
        config_path=config_path,
        input_glob=input_glob,
        condition=condition,
        input_files=input_files,
        write_fasta_file=config.write_passed_fasta,
        skip_mfe=skip_mfe,
        reference_corpus=reference_corpus,
        limit=limit,
    )
    return df

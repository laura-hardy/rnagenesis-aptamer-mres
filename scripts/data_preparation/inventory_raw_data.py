#!/usr/bin/env python3
"""Read-only inventory and lightweight QC of files under data/raw.

Purpose
-------
Establish a reproducible starting point for subsequent data curation.
This script never modifies, renames, moves, or deletes anything under data/raw.

Outputs (write destinations only; never under data/raw):
  - docs/data_curation/raw_data_inventory.csv
  - docs/data_curation/raw_data_inventory_summary.json  (machine-readable QC/overlap;
    aggregate stats only — no sequence values)
  - docs/data_curation/raw_data_workbook_sheets.csv     (per-sheet XLSX metadata)
  - data/interim/inventory/sequence_overlap_samples.json  (ignored local detail;
    sequence-level overlap samples only)

Assumptions
-----------
* Repository root is the parent of ``data/`` and ``docs/``.
* Tabular inspection uses the stdlib ``csv`` module; Excel workbooks are
  inspected via ZIP/XML (no openpyxl/pandas required).
* Very large FASTQ / EMBL files are streamed; some QC metrics are sample-based
  and flagged as such in ``notes`` / ``possible_issue_flags``.
* ``.DS_Store`` and macOS resource-fork files are inventoried but not deeply
  content-inspected.
* Exact duplicate detection uses SHA-256 of full file bytes.
* Sequence-alphabet checks treat IUPAC nucleotide codes as valid; unusual
  composition is reported, not rejected as biologically invalid.

Usage
-----
  python3 scripts/data_preparation/inventory_raw_data.py
  python3 scripts/data_preparation/inventory_raw_data.py --repo-root .
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import logging
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INVENTORY_COLUMNS = [
    "relative_path",
    "top_level_source",
    "file_name",
    "extension",
    "file_size_bytes",
    "file_size_human",
    "last_modified",
    "sha256",
    "apparent_role",
    "compression_status",
    "readable",
    "row_count",
    "column_count",
    "column_names",
    "sequence_column_candidates",
    "target_column_candidates",
    "label_or_binding_column_candidates",
    "identifier_column_candidates",
    "source_or_provenance_column_candidates",
    "notes",
    "possible_issue_flags",
    # Extended curation-planning fields (2026-08-04 refresh)
    "documentation_files",
    "documented_source",
    "documented_processing_state",
    "observed_processing_state",
    "authoritative_candidate",
    "superseded_by",
    "sequence_type",
    "target_type",
    "recommended_S0_status",
    "change_since_previous_inventory",
    "last_inventory_hash",
    "current_hash",
    "readme_notes",
    "unresolved_questions",
]

WORKBOOK_SHEET_COLUMNS = [
    "relative_path",
    "sheet_name",
    "row_count",
    "column_count",
    "column_names",
    "non_empty_cells",
    "likely_sequence_columns",
    "likely_identifier_columns",
    "notes",
]

DOC_NAME_RE = re.compile(
    r"(readme|notes|dictionary|about|qc_report|data.?dictionary|source.?desc)",
    re.I,
)

# Prefer concrete sequence payloads over metadata columns that merely contain
# the substring "sequence" (e.g. sequence_version, sequence_length, sequence_role).
SEQ_COL_PRIORITY = [
    re.compile(r"^(seq|sequence)$", re.I),
    re.compile(r"^sequence_(deposited|clean|cleaned|raw)$", re.I),
    re.compile(r"^sequence_rna_normalized$", re.I),
    re.compile(r"^rna_sequence$", re.I),
    re.compile(r"sequence\s*\(5", re.I),
    re.compile(r"sequence_5to3|core_aptamer_sequence|reported_sequence", re.I),
    re.compile(r"aptamer.?sequence|oligonucleotide", re.I),
    re.compile(r"^feature_sequence_(deposited|rna_normalized)$", re.I),
    re.compile(r"sequence_deposited|sequence_rna|sequence_clean", re.I),
    re.compile(r"(^|_)seq($|_)", re.I),
]
SEQ_COL_EXCLUDE = re.compile(
    r"(version|length|role|alphabet|status|quality|count|family|group|"
    r"variation|summary|normalization|calculated|reported_length|"
    r"sequence.?name|mentions_|has_sequence|sequence_pattern)",
    re.I,
)
TARGET_COL_PATTERNS = re.compile(
    r"(target|protein|ligand|antigen|analyte|binder.?to|against)",
    re.I,
)
BINDING_COL_PATTERNS = re.compile(
    r"(bind|affinity|kd|kd_|ka_|kon|koff|label|positive|negative|"
    r"enrichment|count|round|p\d+$|binding)",
    re.I,
)
ID_COL_PATTERNS = re.compile(
    r"(^id$|accession|aptamer.?id|apta.?index|uid|uuid|record.?id|"
    r"entry|name|title|run|srr|srr_|gsm|geo)",
    re.I,
)
PROVENANCE_COL_PATTERNS = re.compile(
    r"(source|reference|doi|pmid|pubmed|url|citation|provenance|"
    r"paper|journal|author|download|origin|database)",
    re.I,
)

NT_VALID = set("ACGTUacgtuNRYSWKMBDHVnrykswmbdhv.-")
AA_VALID = set("ACDEFGHIKLMNPQRSTVWYacdefghiklmnpqrstvwyX*x")
# Contiguous nucleotide runs of this length must not appear in tracked inventory outputs.
TRACKED_NT_REDACT_MIN = 20
LATENT_COORDINATE_NAME_RE = re.compile(r"_x_z\.csv$", re.I)
ROLE_HINTS = [
    (re.compile(r"_x_z\.csv$", re.I), "latent_coordinate_or_embedding"),
    (re.compile(r"/review_v2/", re.I), "manual_review_output_or_template"),
    (re.compile(r"/review/", re.I), "manual_review_output_or_template"),
    (re.compile(r"/candidates/", re.I), "derived_candidate_processing"),
    (re.compile(r"/inspection/", re.I), "derived_inspection_output"),
    (re.compile(r"selected_after", re.I), "curated_or_selected_output"),
    (re.compile(r"rejected_after", re.I), "rejected_records"),
    (re.compile(r"unreviewed_after", re.I), "manual_review_remainder"),
    (re.compile(r"_cleaned\.", re.I), "cleaned_derived_output"),
    (re.compile(r"_raw\.", re.I), "scraped_or_assembled_raw_table"),
    (re.compile(r"fixtures?/", re.I), "fixture_or_test_input"),
    (re.compile(r"backup", re.I), "backup_or_versioned_copy"),
    (re.compile(r"template", re.I), "manual_review_template"),
    (re.compile(r"qc_report|processing_log|_log\.txt", re.I), "process_log_or_qc_report"),
    (re.compile(r"readme|README", re.I), "documentation"),
    (re.compile(r"\.pdf$", re.I), "source_document_pdf"),
    (re.compile(r"\.html$", re.I), "scraped_or_cached_html"),
    (re.compile(r"\.gb$", re.I), "genbank_source_record"),
    (re.compile(r"\.fastq$", re.I), "sequence_reads_fastq"),
    (re.compile(r"embl|\.txt$", re.I), "flat_file_or_text"),
    (re.compile(r"SraRunInfo|SraAccList", re.I), "sra_metadata"),
    (re.compile(r"extracted", re.I), "manually_extracted_table"),
]

LARGE_STREAM_BYTES = 5_000_000
FASTQ_SAMPLE_READS = 5000
EMBL_SAMPLE_RECORDS = 300
TABULAR_DUP_SAMPLE_LIMIT = 200_000
MAX_COLUMN_NAMES_STORED = 80


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for u in units:
        if size < 1024 or u == units[-1]:
            if u == "B":
                return f"{int(size)} {u}"
            return f"{size:.1f} {u}"
        size /= 1024
    return f"{n} B"


def utc_mtime(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def join_flags(flags: Iterable[str]) -> str:
    return "|".join(sorted(dict.fromkeys(f for f in flags if f)))


def classify_role(rel_posix: str, file_name: str) -> str:
    blob = f"{rel_posix}/{file_name}"
    for pat, role in ROLE_HINTS:
        if pat.search(blob):
            return role
    if file_name == ".DS_Store":
        return "os_metadata"
    ext = Path(file_name).suffix.lower()
    if ext in {".csv", ".tsv", ".xlsx", ".xls"}:
        return "tabular_data"
    if ext in {".md", ".rtf", ".txt"} and "readme" in file_name.lower():
        return "documentation"
    if ext in {".png", ".jpg", ".jpeg"}:
        return "image_asset"
    if ext in {".sh"}:
        return "download_script"
    return "unclassified_or_source_file"


def match_columns(names: list[str], pattern: re.Pattern[str]) -> list[str]:
    return [n for n in names if pattern.search(n or "")]


def match_sequence_columns(names: list[str]) -> list[str]:
    chosen: list[str] = []
    for pat in SEQ_COL_PRIORITY:
        for n in names:
            if not n or n in chosen:
                continue
            if SEQ_COL_EXCLUDE.search(n) and not re.search(
                r"sequence_(deposited|clean|cleaned|raw|rna_normalized)|rna_sequence|"
                r"feature_sequence_(deposited|rna_normalized)|sequence_5to3|"
                r"core_aptamer_sequence",
                n,
                re.I,
            ):
                continue
            if pat.search(n):
                chosen.append(n)
    # Fallback: any column with 'sequence' that is not excluded metadata
    if not chosen:
        for n in names:
            if n and re.search(r"sequence", n, re.I) and not SEQ_COL_EXCLUDE.search(n):
                chosen.append(n)
    return chosen


def looks_like_nucleotide(seq: str) -> bool:
    if not seq or len(seq) < 5:
        return False
    s = re.sub(r"\s+", "", seq)
    if not s:
        return False
    allowed = sum(1 for c in s if c in NT_VALID)
    return allowed / len(s) >= 0.9


def redact_sequence_like_column_names(colnames: list[str]) -> str:
    """Return trackable column_names that never expose raw nucleotide strings."""
    if not colnames:
        return ""
    if looks_like_nucleotide(colnames[0]) and len(re.sub(r"\s+", "", colnames[0])) >= TRACKED_NT_REDACT_MIN:
        if len(colnames) == 3:
            return "headerless_three_column_file"
        safe = []
        for i, name in enumerate(colnames[:MAX_COLUMN_NAMES_STORED]):
            if looks_like_nucleotide(name) and len(re.sub(r"\s+", "", name)) >= TRACKED_NT_REDACT_MIN:
                safe.append(f"col{i}_redacted_sequence_like")
            else:
                safe.append(name or f"col{i}")
        return "|".join(safe)
    return "|".join(colnames[:MAX_COLUMN_NAMES_STORED])


def is_latent_coordinate_file(path: Path) -> bool:
    return bool(LATENT_COORDINATE_NAME_RE.search(path.name))


def looks_like_protein(seq: str) -> bool:
    if not seq or len(seq) < 5:
        return False
    s = re.sub(r"\s+", "", seq)
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 5:
        return False
    aa = sum(1 for c in letters if c in AA_VALID)
    has_nt_only = set(c.upper() for c in letters) <= set("ACGTUN")
    return aa / len(letters) >= 0.95 and not has_nt_only


def sequence_issue_flags(seq: str, *, sample_based: bool = False) -> list[str]:
    flags: list[str] = []
    if seq is None:
        return ["missing_sequence"]
    raw = seq
    s = seq.strip()
    if not s:
        return ["missing_sequence"]
    if s != raw:
        flags.append("sequence_leading_or_trailing_whitespace")
    if re.search(r"\s", s):
        flags.append("whitespace_inside_sequence")
    if re.search(r"[^A-Za-z\-.*]", s):
        # punctuation / digits besides IUPAC letters
        if re.search(r"[0-9_/;,]", s):
            flags.append("punctuation_or_digits_in_sequence")
    letters = [c for c in s if c.isalpha()]
    if not letters:
        flags.append("no_alphabetic_sequence_chars")
        return flags
    upper = [c for c in letters if c.isupper()]
    lower = [c for c in letters if c.islower()]
    if upper and lower:
        flags.append("inconsistent_sequence_case")
    u = set(c.upper() for c in letters)
    if "T" in u and "U" in u:
        flags.append("mixed_T_and_U")
    invalid = [c for c in letters if c.upper() not in set("ACGTURYSWKMBDHVN")]
    # If mostly AA-like, skip nt-invalid flag
    if invalid and not looks_like_protein(s):
        if any(c.upper() not in set("ACDEFGHIKLMNPQRSTVWYX*") for c in invalid):
            flags.append("unexpected_sequence_characters")
        elif looks_like_nucleotide(s) is False and looks_like_protein(s):
            pass
        else:
            # ambiguous: report unexpected nt chars only when mostly nt
            nt_frac = sum(1 for c in letters if c.upper() in set("ACGTUN")) / len(letters)
            if nt_frac >= 0.8:
                flags.append("unexpected_sequence_characters")
    if len(letters) < 10:
        flags.append("unusually_short_sequence")
    if len(letters) > 500:
        flags.append("unusually_long_sequence")
    if sample_based:
        flags.append("qc_sample_based")
    return flags


def infer_sequence_type_from_values(values: list[str]) -> str:
    if not values:
        return "unclear"
    n_rna = n_dna = n_prot = n_mixed = n_unclear = 0
    for v in values:
        if not v or not str(v).strip():
            n_unclear += 1
            continue
        s = re.sub(r"\s+", "", str(v))
        letters = [c for c in s if c.isalpha()]
        if not letters:
            n_unclear += 1
            continue
        u = set(c.upper() for c in letters)
        if looks_like_protein(s):
            n_prot += 1
            continue
        if not looks_like_nucleotide(s):
            n_unclear += 1
            continue
        has_u = "U" in u
        has_t = "T" in u
        if has_u and has_t:
            n_mixed += 1
        elif has_u and not has_t:
            n_rna += 1
        elif has_t and not has_u:
            n_dna += 1  # DNA alphabet OR ENA-style RNA-as-T
        else:
            n_unclear += 1
    total = n_rna + n_dna + n_prot + n_mixed + n_unclear
    if total == 0:
        return "unclear"
    # Prefer mixed if both RNA-U and DNA-T present substantially
    if n_rna and n_dna and (n_rna + n_dna) / total >= 0.5:
        return "mixed"
    if n_prot / total >= 0.5:
        return "protein"
    if n_rna / total >= 0.5:
        return "RNA"
    if n_dna / total >= 0.5:
        return "DNA_or_RNA_stored_as_T"
    if n_mixed / total >= 0.3:
        return "mixed"
    return "unclear"


# ---------------------------------------------------------------------------
# Format inspectors
# ---------------------------------------------------------------------------


@dataclass
class FileInspection:
    relative_path: str
    top_level_source: str
    file_name: str
    extension: str
    file_size_bytes: int
    file_size_human: str
    last_modified: str
    sha256: str = ""
    apparent_role: str = ""
    compression_status: str = "none"
    readable: str = "yes"
    row_count: str = ""
    column_count: str = ""
    column_names: str = ""
    sequence_column_candidates: str = ""
    target_column_candidates: str = ""
    label_or_binding_column_candidates: str = ""
    identifier_column_candidates: str = ""
    source_or_provenance_column_candidates: str = ""
    notes: str = ""
    possible_issue_flags: str = ""
    documentation_files: str = ""
    documented_source: str = ""
    documented_processing_state: str = ""
    observed_processing_state: str = ""
    authoritative_candidate: str = ""
    superseded_by: str = ""
    sequence_type: str = ""
    target_type: str = ""
    recommended_S0_status: str = ""
    change_since_previous_inventory: str = ""
    last_inventory_hash: str = ""
    current_hash: str = ""
    readme_notes: str = ""
    unresolved_questions: str = ""
    # Internal (not written to CSV unless requested)
    _qc: dict[str, Any] = field(default_factory=dict, repr=False)
    _schema_sig: str = field(default="", repr=False)
    _seq_samples: list[str] = field(default_factory=list, repr=False)
    _pair_samples: list[tuple[str, str]] = field(default_factory=list, repr=False)
    _id_samples: list[str] = field(default_factory=list, repr=False)
    _workbook_sheets: list[dict[str, Any]] = field(default_factory=list, repr=False)


def open_text_maybe_gzip(path: Path):
    if path.suffix.lower() == ".gz" or path.name.lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    # Prefer utf-8; fall back to latin-1 for AptaDB-style exports with non-UTF bytes.
    try:
        fh = path.open("r", encoding="utf-8", errors="strict", newline="")
        fh.read(4096)
        fh.seek(0)
        return fh
    except UnicodeDecodeError:
        return path.open("r", encoding="latin-1", errors="replace", newline="")
    except Exception:
        return path.open("r", encoding="utf-8", errors="replace", newline="")


def detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t|;")
        return dialect.delimiter
    except csv.Error:
        if sample.count("\t") > sample.count(","):
            return "\t"
        return ","


def inspect_tabular_csv_like(path: Path, insp: FileInspection) -> None:
    flags: list[str] = []
    notes: list[str] = []
    size = path.stat().st_size
    sample_based = size > LARGE_STREAM_BYTES

    with open_text_maybe_gzip(path) as f:
        # BOM-aware peek
        peek = f.read(65536)
        if not peek.strip():
            insp.readable = "yes"
            insp.row_count = "0"
            flags.append("empty_or_nearly_empty")
            insp.possible_issue_flags = join_flags(flags)
            insp.notes = "File has no non-whitespace content"
            return
        delim = detect_delimiter(peek)
        f.seek(0)
        reader = csv.reader(f, delimiter=delim)
        try:
            header = next(reader)
        except StopIteration:
            flags.append("empty_or_nearly_empty")
            insp.possible_issue_flags = join_flags(flags)
            return

        # Strip BOM from first header cell
        if header and header[0].startswith("\ufeff"):
            header[0] = header[0].lstrip("\ufeff")
            flags.append("utf8_bom_present")

        colnames = [h.strip() for h in header]
        insp.column_count = str(len(colnames))
        insp.column_names = redact_sequence_like_column_names(colnames)
        # Schema signature for overlap grouping must also avoid raw sequences.
        insp._schema_sig = insp.column_names

        latent_file = is_latent_coordinate_file(path)
        seq_cols = match_sequence_columns(colnames)
        # Headerless embedding / coordinate CSV: first column looks like sequence
        headerless_seq = False
        if not seq_cols and colnames and looks_like_nucleotide(colnames[0]):
            headerless_seq = True
            if latent_file:
                # Latent-coordinate files use a sequence key column but are not
                # corpus sequence inputs; do not treat col0 as a sequence field.
                seq_cols = []
                flags.append("header_looks_like_sequence_data")
                flags.append("latent_coordinate_file_not_sequence_input")
                notes.append(
                    "Headerless three-column latent-coordinate file "
                    "(sequence key + latent dimensions); "
                    "column_names redacted for tracked inventory; "
                    "not a sequence input for the corpus"
                )
                insp.apparent_role = "latent_coordinate_or_embedding"
                insp.sequence_type = "not_applicable_latent_coordinates"
            else:
                seq_cols = ["__col0_as_sequence__"]
                flags.append("header_looks_like_sequence_data")
                notes.append(
                    "First header cell looks like a nucleotide sequence; "
                    "treated as headerless or header-embedded data for QC sampling; "
                    "column_names redacted for tracked inventory"
                )

        tgt_cols = match_columns(colnames, TARGET_COL_PATTERNS)
        bind_cols = match_columns(colnames, BINDING_COL_PATTERNS)
        id_cols = match_columns(colnames, ID_COL_PATTERNS)
        prov_cols = match_columns(colnames, PROVENANCE_COL_PATTERNS)

        insp.sequence_column_candidates = "|".join(seq_cols)
        insp.target_column_candidates = "|".join(tgt_cols)
        insp.label_or_binding_column_candidates = "|".join(bind_cols)
        insp.identifier_column_candidates = "|".join(id_cols)
        insp.source_or_provenance_column_candidates = "|".join(prov_cols)

        # Index maps
        def col_idx(name: str) -> Optional[int]:
            if name == "__col0_as_sequence__":
                return 0
            try:
                return colnames.index(name)
            except ValueError:
                return None

        seq_idx = col_idx(seq_cols[0]) if seq_cols else None
        tgt_idx = col_idx(tgt_cols[0]) if tgt_cols else None
        id_idx = col_idx(id_cols[0]) if id_cols else None

        n_rows = 0
        malformed = 0
        embedded_header_like = 0
        missing_seq = 0
        missing_tgt = 0
        missing_id = 0
        seq_flags_counter: Counter[str] = Counter()
        seq_values: list[str] = []
        seen_rows: set[str] = set()
        dup_rows = 0
        seen_seqs: set[str] = set()
        dup_seqs = 0
        seen_pairs: set[tuple[str, str]] = set()
        dup_pairs = 0
        seq_to_targets: dict[str, set[str]] = defaultdict(set)
        target_values: Counter[str] = Counter()
        lengths: list[int] = []

        # If headerless, treat sniffed header row as first data row
        if headerless_seq:
            data_iter: Iterator[list[str]] = _chain_row_then_reader(list(colnames), reader)
            expected_width = len(colnames)
        else:
            data_iter = reader
            expected_width = len(colnames)

        for row in data_iter:
            n_rows += 1

            if len(row) != expected_width and not headerless_seq:
                malformed += 1
                flags.append("malformed_row_column_count_mismatch")

            # Unexpected repeated header
            if (
                not headerless_seq
                and row
                and colnames
                and row[0] == colnames[0]
                and row == colnames
            ):
                embedded_header_like += 1

            # Row fingerprint for exact duplicate rows (bounded)
            if n_rows <= TABULAR_DUP_SAMPLE_LIMIT:
                fp = "\t".join(row)
                if fp in seen_rows:
                    dup_rows += 1
                else:
                    seen_rows.add(fp)

            seq_val = ""
            if seq_idx is not None and seq_idx < len(row):
                seq_val = row[seq_idx]
                if not str(seq_val).strip():
                    missing_seq += 1
                else:
                    for fl in sequence_issue_flags(str(seq_val)):
                        seq_flags_counter[fl] += 1
                    norm = re.sub(r"\s+", "", str(seq_val)).upper()
                    lengths.append(len(norm))
                    if len(seq_values) < 200:
                        seq_values.append(str(seq_val))
                    if n_rows <= TABULAR_DUP_SAMPLE_LIMIT:
                        if norm in seen_seqs:
                            dup_seqs += 1
                        else:
                            seen_seqs.add(norm)
                        insp._seq_samples.append(norm[:300])

            tgt_val = ""
            if tgt_idx is not None and tgt_idx < len(row):
                tgt_val = row[tgt_idx]
                if not str(tgt_val).strip():
                    missing_tgt += 1
                else:
                    target_values[str(tgt_val).strip()] += 1

            if id_idx is not None and id_idx < len(row):
                if not str(row[id_idx]).strip():
                    missing_id += 1
                elif len(insp._id_samples) < 50:
                    insp._id_samples.append(str(row[id_idx]).strip())

            if seq_val and tgt_idx is not None:
                norm = re.sub(r"\s+", "", str(seq_val)).upper()
                tnorm = str(tgt_val).strip().lower()
                pair = (norm, tnorm)
                if n_rows <= TABULAR_DUP_SAMPLE_LIMIT:
                    if pair in seen_pairs:
                        dup_pairs += 1
                    else:
                        seen_pairs.add(pair)
                    seq_to_targets[norm].add(tnorm)
                    if len(insp._pair_samples) < 5000:
                        insp._pair_samples.append(pair)

            if sample_based and n_rows >= 50_000:
                notes.append(f"row_scan_capped_at_{n_rows}_for_large_file")
                flags.append("qc_sample_based")
                # Continue counting remaining rows quickly without deep QC
                for _ in reader:
                    n_rows += 1
                break

    insp.row_count = str(n_rows)
    if delim == "\t":
        notes.append("delimiter=TAB")
    elif delim != ",":
        notes.append(f"delimiter={delim!r}")
        flags.append("non_comma_delimiter")

    if malformed:
        flags.append(f"malformed_rows_{malformed}")
    if embedded_header_like:
        flags.append(f"embedded_header_rows_{embedded_header_like}")
    if missing_seq:
        flags.append(f"missing_sequences_{missing_seq}")
    if tgt_cols and missing_tgt:
        flags.append(f"missing_targets_{missing_tgt}")
    if id_cols and missing_id:
        flags.append(f"missing_identifiers_{missing_id}")
    if dup_rows:
        flags.append(f"duplicate_rows_{dup_rows}")
    if dup_seqs:
        flags.append(f"duplicate_sequences_{dup_seqs}")
    if dup_pairs:
        flags.append(f"duplicate_sequence_target_pairs_{dup_pairs}")

    conflicting = sum(1 for ts in seq_to_targets.values() if len({t for t in ts if t}) > 1)
    if conflicting:
        flags.append(f"conflicting_targets_for_same_sequence_{conflicting}")

    for fl, cnt in seq_flags_counter.most_common():
        if cnt > 0:
            flags.append(f"{fl}_n{cnt}")

    if lengths:
        notes.append(
            f"seq_len_min={min(lengths)};seq_len_median={sorted(lengths)[len(lengths)//2]};"
            f"seq_len_max={max(lengths)}"
        )

    seq_type = infer_sequence_type_from_values(seq_values)
    if latent_file:
        seq_type = "not_applicable_latent_coordinates"
        notes.append("inferred_sequence_type=not_applicable_latent_coordinates")
        insp.sequence_type = seq_type
        insp.sequence_column_candidates = ""
    else:
        notes.append(f"inferred_sequence_type={seq_type}")
        insp.sequence_type = seq_type
    if target_values:
        notes.append(f"distinct_targets_sampled={len(target_values)}")
        insp.target_type = "present_in_table"

    # Name/content mismatch heuristics
    lower_name = path.name.lower()
    if "selected" in lower_name and n_rows == 0:
        flags.append("name_implies_selected_but_empty")
    if "raw" in lower_name and "cleaned" in lower_name:
        flags.append("name_mixes_raw_and_cleaned")

    insp.notes = "; ".join(notes)
    insp.possible_issue_flags = join_flags(flags)
    insp._qc = {
        "n_rows": n_rows,
        "malformed": malformed,
        "missing_seq": missing_seq,
        "missing_tgt": missing_tgt,
        "dup_rows": dup_rows,
        "dup_seqs": dup_seqs,
        "dup_pairs": dup_pairs,
        "conflicting_targets": conflicting,
        "seq_type": seq_type,
        "sample_based": sample_based or ("qc_sample_based" in flags),
        "distinct_targets": len(target_values),
        "seq_flag_counts": dict(seq_flags_counter),
    }


def _chain_row_then_reader(first: list[str], reader) -> Iterator[list[str]]:
    yield first
    yield from reader


def inspect_xlsx(path: Path, insp: FileInspection) -> None:
    """Inspect workbook sheets via ZIP+XML (stdlib only).

    File-level QC uses the first worksheet. All worksheets are summarised into
    ``insp._workbook_sheets`` for ``raw_data_workbook_sheets.csv``.
    """
    flags: list[str] = []
    notes: list[str] = []
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            notes.append(f"xlsx_parts={len(names)}")
            shared: list[str] = []
            if "xl/sharedStrings.xml" in names:
                ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in ss_root.findall("m:si", ns):
                    texts = [t.text or "" for t in si.findall(".//m:t", ns)]
                    shared.append("".join(texts))

            sheet_paths = sorted(
                n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
            )
            # Prefer workbook.xml order/names when available
            sheet_labels: dict[str, str] = {}
            if "xl/workbook.xml" in names:
                wb = ET.fromstring(zf.read("xl/workbook.xml"))
                for i, sh in enumerate(wb.findall("m:sheets/m:sheet", ns)):
                    sheet_labels[f"sheet{i+1}"] = sh.attrib.get("name", f"sheet{i+1}")

            if not sheet_paths:
                flags.append("xlsx_no_worksheets_found")
                insp.readable = "partial"
                insp.possible_issue_flags = join_flags(flags)
                insp.notes = "; ".join(notes)
                return

            def cell_value(c) -> str:
                t = c.attrib.get("t")
                v = c.find("m:v", ns)
                if v is None or v.text is None:
                    is_elem = c.find("m:is", ns)
                    if is_elem is not None:
                        return "".join(x.text or "" for x in is_elem.findall(".//m:t", ns))
                    return ""
                if t == "s":
                    try:
                        return shared[int(v.text)]
                    except (ValueError, IndexError):
                        return v.text
                return v.text

            def row_vals(r) -> list[str]:
                cells = r.findall("m:c", ns)
                out: dict[int, str] = {}
                max_idx = -1
                for c in cells:
                    ref = c.attrib.get("r", "A1")
                    col_letters = re.match(r"[A-Z]+", ref)
                    if not col_letters:
                        continue
                    idx = 0
                    for ch in col_letters.group(0):
                        idx = idx * 26 + (ord(ch) - 64)
                    idx -= 1
                    out[idx] = cell_value(c)
                    max_idx = max(max_idx, idx)
                if max_idx < 0:
                    return []
                return [out.get(i, "") for i in range(max_idx + 1)]

            notes.append(f"worksheets={len(sheet_paths)};inspecting={sheet_paths[0]}")
            first_rows_xml: list[Any] = []
            for sp_i, sp in enumerate(sheet_paths):
                sheet_root = ET.fromstring(zf.read(sp))
                sheet_rows_xml = sheet_root.findall("m:sheetData/m:row", ns)
                sheet_header = row_vals(sheet_rows_xml[0]) if sheet_rows_xml else []
                nonempty = 0
                for r in sheet_rows_xml:
                    vals = row_vals(r)
                    if any(str(v).strip() for v in vals):
                        nonempty += 1
                stem = Path(sp).stem
                sheet_name = sheet_labels.get(stem, stem)
                insp._workbook_sheets.append(
                    {
                        "relative_path": insp.relative_path,
                        "sheet_name": sheet_name,
                        "row_count": str(max(0, len(sheet_rows_xml) - 1)) if sheet_rows_xml else "0",
                        "column_count": str(len(sheet_header)),
                        "column_names": "|".join(
                            h.strip() for h in sheet_header[:MAX_COLUMN_NAMES_STORED]
                        ),
                        "non_empty_cells": str(nonempty),
                        "likely_sequence_columns": "|".join(match_sequence_columns(sheet_header)),
                        "likely_identifier_columns": "|".join(
                            match_columns(sheet_header, ID_COL_PATTERNS)
                        ),
                        "notes": (
                            "first_sheet_used_for_file_level_qc"
                            if sp_i == 0
                            else "additional_sheet_metadata_only"
                        ),
                    }
                )
                if sp_i == 0:
                    first_rows_xml = sheet_rows_xml

            rows_xml = first_rows_xml
            if not rows_xml:
                flags.append("empty_or_nearly_empty")
                insp.row_count = "0"
                insp.possible_issue_flags = join_flags(flags)
                insp.notes = "; ".join(notes)
                return

            header = row_vals(rows_xml[0])
            colnames = [h.strip() for h in header]
            insp.column_count = str(len(colnames))
            insp.column_names = "|".join(colnames[:MAX_COLUMN_NAMES_STORED])
            insp._schema_sig = "|".join(colnames)
            insp.row_count = str(max(0, len(rows_xml) - 1))

            seq_cols = match_sequence_columns(colnames)
            tgt_cols = match_columns(colnames, TARGET_COL_PATTERNS)
            bind_cols = match_columns(colnames, BINDING_COL_PATTERNS)
            id_cols = match_columns(colnames, ID_COL_PATTERNS)
            prov_cols = match_columns(colnames, PROVENANCE_COL_PATTERNS)
            insp.sequence_column_candidates = "|".join(seq_cols)
            insp.target_column_candidates = "|".join(tgt_cols)
            insp.label_or_binding_column_candidates = "|".join(bind_cols)
            insp.identifier_column_candidates = "|".join(id_cols)
            insp.source_or_provenance_column_candidates = "|".join(prov_cols)

            seq_idx = colnames.index(seq_cols[0]) if seq_cols and seq_cols[0] in colnames else None
            seq_values: list[str] = []
            missing_seq = 0
            seq_flags_counter: Counter[str] = Counter()
            seen_seqs: set[str] = set()
            dup_seqs = 0
            limit = min(len(rows_xml), 5001)
            for r in rows_xml[1:limit]:
                vals = row_vals(r)
                if seq_idx is not None:
                    sv = vals[seq_idx] if seq_idx < len(vals) else ""
                    if not str(sv).strip():
                        missing_seq += 1
                    else:
                        for fl in sequence_issue_flags(str(sv)):
                            seq_flags_counter[fl] += 1
                        if len(seq_values) < 200:
                            seq_values.append(str(sv))
                        norm = re.sub(r"\s+", "", str(sv)).upper()
                        if norm in seen_seqs:
                            dup_seqs += 1
                        else:
                            seen_seqs.add(norm)
                        insp._seq_samples.append(norm[:300])
            if len(rows_xml) - 1 > 5000:
                flags.append("qc_sample_based")
                notes.append("xlsx_qc_sampled_first_5000_data_rows")
            if missing_seq:
                flags.append(f"missing_sequences_{missing_seq}")
            if dup_seqs:
                flags.append(f"duplicate_sequences_{dup_seqs}")
            for fl, cnt in seq_flags_counter.most_common(12):
                flags.append(f"{fl}_n{cnt}")
            seq_type = infer_sequence_type_from_values(seq_values)
            notes.append(f"inferred_sequence_type={seq_type}")
            if len(sheet_paths) > 1:
                notes.append("multi_sheet_workbook_metadata_exported")
                flags.append("multi_sheet_workbook")
            insp._qc = {
                "n_rows": max(0, len(rows_xml) - 1),
                "seq_type": seq_type,
                "sheets": len(sheet_paths),
            }
            insp.sequence_type = seq_type
    except zipfile.BadZipFile as e:
        insp.readable = "no"
        flags.append("unreadable_bad_xlsx_zip")
        notes.append(f"BadZipFile: {e}")
    except ET.ParseError as e:
        insp.readable = "partial"
        flags.append("xlsx_xml_parse_error")
        notes.append(f"ParseError: {e}")
    insp.notes = "; ".join(notes)
    insp.possible_issue_flags = join_flags(flags)


def inspect_fastq(path: Path, insp: FileInspection) -> None:
    flags: list[str] = []
    notes: list[str] = []
    n_reads = 0
    seq_flags_counter: Counter[str] = Counter()
    lengths: list[int] = []
    seq_values: list[str] = []
    seen: set[str] = set()
    dup = 0
    sample_based = path.stat().st_size > LARGE_STREAM_BYTES
    with open_text_maybe_gzip(path) as f:
        while True:
            h = f.readline()
            if not h:
                break
            s = f.readline()
            plus = f.readline()
            q = f.readline()
            if not s:
                flags.append("truncated_fastq_record")
                break
            n_reads += 1
            seq = s.strip()
            for fl in sequence_issue_flags(seq, sample_based=False):
                seq_flags_counter[fl] += 1
            lengths.append(len(seq))
            if len(seq_values) < 100:
                seq_values.append(seq)
            norm = seq.upper()
            if n_reads <= FASTQ_SAMPLE_READS:
                if norm in seen:
                    dup += 1
                else:
                    seen.add(norm)
                insp._seq_samples.append(norm[:300])
            if not h.startswith("@"):
                flags.append("fastq_header_not_at_start")
            if plus and not plus.startswith("+"):
                flags.append("fastq_plus_line_unexpected")
            if sample_based and n_reads >= FASTQ_SAMPLE_READS:
                # Count remaining roughly by reading rest in chunks for total
                # Continue lightweight count
                while True:
                    h2 = f.readline()
                    if not h2:
                        break
                    f.readline()
                    f.readline()
                    f.readline()
                    if h2.startswith("@"):
                        n_reads += 1
                flags.append("qc_sample_based")
                notes.append(f"deep_qc_first_{FASTQ_SAMPLE_READS}_reads")
                break
    insp.row_count = str(n_reads)
    insp.column_names = "fastq:header|sequence|plus|quality"
    insp.column_count = "4"
    insp.sequence_column_candidates = "sequence"
    if lengths:
        notes.append(
            f"read_len_min={min(lengths[:FASTQ_SAMPLE_READS] or lengths)};"
            f"read_len_max={max(lengths[:FASTQ_SAMPLE_READS] or lengths)}"
        )
    notes.append(f"inferred_sequence_type={infer_sequence_type_from_values(seq_values)}")
    if dup:
        flags.append(f"duplicate_sequences_in_sample_{dup}")
    for fl, cnt in seq_flags_counter.most_common(10):
        flags.append(f"{fl}_n{cnt}")
    insp.notes = "; ".join(notes)
    insp.possible_issue_flags = join_flags(flags)
    insp._qc = {"n_reads": n_reads, "sample_based": sample_based}


def inspect_embl(path: Path, insp: FileInspection) -> None:
    flags: list[str] = []
    notes: list[str] = ["format=ENA_EMBL_flatfile"]
    n_records = 0
    n_with_seq = 0
    missing_ac = 0
    seq_flags_counter: Counter[str] = Counter()
    seq_values: list[str] = []
    accessions: list[str] = []
    sample_based = path.stat().st_size > LARGE_STREAM_BYTES
    deep_limit = EMBL_SAMPLE_RECORDS if sample_based else 10**9

    current_ac = ""
    in_seq = False
    seq_chunks: list[str] = []
    deep_done = 0

    def flush():
        nonlocal n_records, n_with_seq, missing_ac, deep_done
        if not current_ac and not seq_chunks and deep_done == 0 and n_records == 0:
            return
        n_records += 1
        if not current_ac:
            missing_ac += 1
        else:
            accessions.append(current_ac)
            if len(insp._id_samples) < 50:
                insp._id_samples.append(current_ac)
        seq = "".join(seq_chunks)
        if seq:
            n_with_seq += 1
            if deep_done < deep_limit:
                for fl in sequence_issue_flags(seq):
                    seq_flags_counter[fl] += 1
                if len(seq_values) < 200:
                    seq_values.append(seq)
                insp._seq_samples.append(seq.upper()[:300])
                deep_done += 1

    with open_text_maybe_gzip(path) as f:
        for line in f:
            if line.startswith("AC "):
                # may be multi
                acs = line[2:].replace(";", " ").split()
                if acs:
                    current_ac = acs[0].strip()
            elif line.startswith("SQ "):
                in_seq = True
                seq_chunks = []
            elif line.startswith("//"):
                flush()
                current_ac = ""
                in_seq = False
                seq_chunks = []
            elif in_seq:
                # sequence lines: bases then numbers
                part = "".join(ch for ch in line if ch.isalpha())
                seq_chunks.append(part)

    insp.row_count = str(n_records)
    insp.column_names = "EMBL:ID|AC|DE|OS|KW|FT|SQ"
    insp.sequence_column_candidates = "SQ"
    insp.identifier_column_candidates = "AC"
    insp.source_or_provenance_column_candidates = "RN|RX|DR"
    if sample_based:
        flags.append("qc_sample_based")
        notes.append(f"deep_sequence_qc_first_{deep_done}_records_of_{n_records}")
    if missing_ac:
        flags.append(f"missing_identifiers_{missing_ac}")
    if n_records and n_with_seq < n_records:
        flags.append(f"missing_sequences_{n_records - n_with_seq}")
    notes.append(f"inferred_sequence_type={infer_sequence_type_from_values(seq_values)}")
    for fl, cnt in seq_flags_counter.most_common(10):
        flags.append(f"{fl}_n{cnt}")
    insp.notes = "; ".join(notes)
    insp.possible_issue_flags = join_flags(flags)
    insp._qc = {"n_records": n_records, "n_with_seq": n_with_seq}


def inspect_genbank(path: Path, insp: FileInspection) -> None:
    flags: list[str] = []
    notes: list[str] = ["format=GenBank"]
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        flags.append("empty_or_nearly_empty")
        insp.row_count = "0"
        insp.possible_issue_flags = join_flags(flags)
        return
    loci = re.findall(r"^LOCUS\s+(\S+)", text, re.M)
    accessions = re.findall(r"^ACCESSION\s+(\S+)", text, re.M)
    # crude sequence extraction
    seqs = []
    for m in re.finditer(r"ORIGIN(.*?)//", text, re.S | re.I):
        seq = "".join(ch for ch in m.group(1) if ch.isalpha())
        if seq:
            seqs.append(seq)
            for fl in sequence_issue_flags(seq):
                flags.append(fl)
            insp._seq_samples.append(seq.upper()[:300])
    insp.row_count = str(max(len(loci), len(accessions), len(seqs), 1 if text else 0))
    insp.identifier_column_candidates = "ACCESSION|LOCUS"
    insp.sequence_column_candidates = "ORIGIN"
    if accessions:
        insp._id_samples.extend(accessions[:20])
    notes.append(f"loci={len(loci)};accessions={len(accessions)};sequences={len(seqs)}")
    notes.append(f"inferred_sequence_type={infer_sequence_type_from_values(seqs)}")
    # molecule type from LOCUS line
    mol = re.findall(r"^LOCUS\s+\S+\s+\d+\s+bp\s+(\S+)", text, re.M)
    if mol:
        notes.append(f"locus_molecule_tokens={','.join(sorted(set(mol)))}")
    insp.notes = "; ".join(notes)
    insp.possible_issue_flags = join_flags(flags)


def inspect_fasta(path: Path, insp: FileInspection) -> None:
    flags: list[str] = []
    notes: list[str] = ["format=FASTA"]
    n = 0
    seq_values: list[str] = []
    with open_text_maybe_gzip(path) as f:
        seq_chunks: list[str] = []
        for line in f:
            if line.startswith(">"):
                if seq_chunks:
                    s = "".join(seq_chunks)
                    n += 1
                    for fl in sequence_issue_flags(s):
                        flags.append(fl)
                    if len(seq_values) < 200:
                        seq_values.append(s)
                    insp._seq_samples.append(s.upper()[:300])
                    seq_chunks = []
            else:
                seq_chunks.append(line.strip())
        if seq_chunks:
            s = "".join(seq_chunks)
            n += 1
            for fl in sequence_issue_flags(s):
                flags.append(fl)
            seq_values.append(s)
    insp.row_count = str(n)
    insp.sequence_column_candidates = "fasta_sequence"
    insp.identifier_column_candidates = "fasta_header"
    notes.append(f"inferred_sequence_type={infer_sequence_type_from_values(seq_values)}")
    insp.notes = "; ".join(notes)
    insp.possible_issue_flags = join_flags(flags)


def inspect_json_like(path: Path, insp: FileInspection) -> None:
    flags: list[str] = []
    notes: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        flags.append("empty_or_nearly_empty")
        insp.row_count = "0"
        insp.possible_issue_flags = join_flags(flags)
        return
    if path.suffix.lower() == ".jsonl" or path.name.endswith(".jsonl"):
        n = 0
        keys: Counter[str] = Counter()
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                n += 1
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        keys.update(obj.keys())
                except json.JSONDecodeError as e:
                    flags.append("malformed_jsonl_line")
                    notes.append(f"JSONDecodeError_line_{n}: {e}")
        insp.row_count = str(n)
        colnames = [k for k, _ in keys.most_common(MAX_COLUMN_NAMES_STORED)]
        insp.column_names = "|".join(colnames)
        insp.column_count = str(len(keys))
    else:
        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                insp.row_count = str(len(obj))
                if obj and isinstance(obj[0], dict):
                    colnames = list(obj[0].keys())
                    insp.column_names = "|".join(colnames[:MAX_COLUMN_NAMES_STORED])
                    insp.column_count = str(len(colnames))
            elif isinstance(obj, dict):
                insp.row_count = "1"
                insp.column_names = "|".join(list(obj.keys())[:MAX_COLUMN_NAMES_STORED])
                insp.column_count = str(len(obj))
            notes.append(f"json_type={type(obj).__name__}")
        except json.JSONDecodeError as e:
            insp.readable = "no"
            flags.append("unreadable_json")
            notes.append(str(e))
    insp.notes = "; ".join(notes)
    insp.possible_issue_flags = join_flags(flags)


def inspect_generic_text(path: Path, insp: FileInspection) -> None:
    flags: list[str] = []
    notes: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = 0
            nonempty = 0
            sample = []
            for i, line in enumerate(f):
                lines += 1
                if line.strip():
                    nonempty += 1
                if i < 5:
                    sample.append(line.rstrip()[:100])
                if i > 100000:
                    flags.append("qc_sample_based")
                    # finish counting
                    for _ in f:
                        lines += 1
                    break
        insp.row_count = str(lines)
        if nonempty == 0:
            flags.append("empty_or_nearly_empty")
        notes.append(f"nonempty_lines={nonempty}")
        if sample:
            notes.append("head=" + " || ".join(sample)[:300])
        # accession list heuristic
        if "acclist" in path.name.lower() or path.name.lower().endswith("acclist.txt"):
            insp.apparent_role = "sra_metadata"
            insp.identifier_column_candidates = "accession_list"
    except OSError as e:
        insp.readable = "no"
        flags.append("unreadable")
        notes.append(str(e))
    insp.notes = "; ".join(notes)
    insp.possible_issue_flags = join_flags(flags)


def inspect_archive(path: Path, insp: FileInspection) -> None:
    flags: list[str] = []
    notes: list[str] = []
    insp.compression_status = "archive"
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                notes.append(f"zip_members={len(names)}")
                notes.append("members_sample=" + "|".join(names[:30]))
                insp.row_count = str(len(names))
        else:
            notes.append("archive_type_uninspected")
            flags.append("archive_contents_not_listed")
    except zipfile.BadZipFile as e:
        insp.readable = "no"
        flags.append("unreadable_archive")
        notes.append(str(e))
    insp.notes = "; ".join(notes)
    insp.possible_issue_flags = join_flags(flags)


def inspect_file(path: Path, repo_root: Path) -> FileInspection:
    rel = path.relative_to(repo_root).as_posix()
    parts = path.relative_to(repo_root / "data" / "raw").parts
    top = parts[0] if parts else "."
    ext = path.suffix.lower()
    # multi-suffix
    name_lower = path.name.lower()
    compression = "none"
    if name_lower.endswith(".gz"):
        compression = "gzip"
        # effective extension
        stem_ext = Path(path.stem).suffix.lower()
        if stem_ext:
            ext = stem_ext + ".gz"
    elif name_lower.endswith(".zip"):
        compression = "zip"

    insp = FileInspection(
        relative_path=rel,
        top_level_source=top if top != path.name else "(raw_root)",
        file_name=path.name,
        extension=ext.lstrip(".") if ext else "",
        file_size_bytes=path.stat().st_size,
        file_size_human=human_size(path.stat().st_size),
        last_modified=utc_mtime(path),
        compression_status=compression,
        apparent_role=classify_role(rel, path.name),
    )

    if path.stat().st_size == 0:
        insp.possible_issue_flags = "empty_or_nearly_empty"
        insp.notes = "zero_byte_file"
        insp.row_count = "0"
        try:
            insp.sha256 = sha256_file(path)
        except OSError as e:
            insp.readable = "no"
            insp.notes = f"hash_failed: {e}"
        return insp

    try:
        insp.sha256 = sha256_file(path)
    except OSError as e:
        insp.readable = "no"
        insp.possible_issue_flags = "unreadable"
        insp.notes = f"hash_failed: {e}"
        return insp

    try:
        if path.name == ".DS_Store":
            insp.notes = "macOS folder metadata; not scientific data"
            return insp

        if ext in {".csv", ".tsv"} or name_lower.endswith(".csv.gz") or name_lower.endswith(".tsv.gz"):
            inspect_tabular_csv_like(path, insp)
        elif ext in {".xlsx", ".xlsm"}:
            inspect_xlsx(path, insp)
        elif ext in {".fastq", ".fq"} or name_lower.endswith(".fastq.gz") or name_lower.endswith(".fq.gz"):
            inspect_fastq(path, insp)
        elif ext in {".fa", ".fasta", ".fna", ".ffn"} or "fasta" in name_lower:
            # Avoid misclassifying random text; require suffix
            if ext in {".fa", ".fasta", ".fna", ".ffn"} or name_lower.endswith(".fasta.gz"):
                inspect_fasta(path, insp)
            elif ext == ".txt" and "embl" in name_lower:
                inspect_embl(path, insp)
            else:
                inspect_generic_text(path, insp)
        elif ext == ".gb" or ext == ".gbk":
            inspect_genbank(path, insp)
        elif ext in {".json", ".jsonl"}:
            inspect_json_like(path, insp)
        elif ext == ".txt" and ("embl" in name_lower or path.name.startswith("ena_embl")):
            inspect_embl(path, insp)
        elif ext == ".zip":
            inspect_archive(path, insp)
        elif ext in {".txt", ".md", ".rtf", ".log"}:
            inspect_generic_text(path, insp)
        elif ext in {".html", ".htm"}:
            insp.notes = "HTML document; content not tabular-parsed in inventory"
            if path.stat().st_size < 50:
                insp.possible_issue_flags = "empty_or_nearly_empty"
        elif ext == ".pdf":
            insp.notes = "PDF document; binary content not text-parsed in inventory"
        elif ext in {".png", ".jpg", ".jpeg", ".gif"}:
            insp.notes = "image asset"
        elif ext == ".sh":
            inspect_generic_text(path, insp)
            insp.apparent_role = "download_script"
        else:
            # Unknown binary/text
            try:
                with path.open("rb") as f:
                    chunk = f.read(512)
                if b"\x00" in chunk:
                    insp.notes = "binary_or_unknown_format"
                else:
                    inspect_generic_text(path, insp)
            except OSError as e:
                insp.readable = "no"
                insp.possible_issue_flags = "unreadable"
                insp.notes = str(e)
    except Exception as e:  # noqa: BLE001 - must not abort whole inventory
        logging.exception("Failed inspecting %s", rel)
        insp.readable = "no"
        insp.possible_issue_flags = join_flags(
            [insp.possible_issue_flags, "inspection_exception", type(e).__name__]
        )
        insp.notes = (insp.notes + "; " if insp.notes else "") + f"exception: {e}"

    # Name-based leakage / processing-state flags
    role_flags = []
    if any(
        x in rel.lower()
        for x in (
            "/review/",
            "/review_v2/",
            "/candidates/",
            "/inspection/",
            "cleaned",
            "selected_after",
            "rejected_after",
        )
    ):
        role_flags.append("derived_or_reviewed_output_in_raw_tree")
    if "backup" in path.name.lower() or path.name.endswith("~"):
        role_flags.append("likely_backup_or_temporary")
    if "copy" in path.name.lower():
        role_flags.append("filename_contains_copy")
    if role_flags:
        insp.possible_issue_flags = join_flags(
            [insp.possible_issue_flags, *role_flags]
        )

    return insp


# ---------------------------------------------------------------------------
# Cross-file analyses
# ---------------------------------------------------------------------------


def build_overlap_summary(rows: list[FileInspection]) -> dict[str, Any]:
    by_hash: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r.sha256:
            by_hash[r.sha256].append(r.relative_path)
    exact_dups = {h: paths for h, paths in by_hash.items() if len(paths) > 1}

    by_schema: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r._schema_sig:
            by_schema[r._schema_sig].append(r.relative_path)
    shared_schemas = {
        s: paths for s, paths in by_schema.items() if len(paths) > 1 and s.count("|") >= 1
    }

    # Cross-file sequence overlap among sampled sequences (normalized)
    seq_index: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        for s in set(r._seq_samples):
            if len(s) >= 10:
                seq_index[s].append(r.relative_path)
    cross_seq = {
        s[:80]: sorted(set(paths))
        for s, paths in seq_index.items()
        if len(set(paths)) > 1
    }
    # Cap report size
    cross_seq_items = sorted(cross_seq.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:200]

    # Pair overlap
    pair_index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        for pair in set(r._pair_samples):
            if pair[0] and len(pair[0]) >= 10:
                pair_index[pair].append(r.relative_path)
    cross_pairs = [
        {"seq_prefix": k[0][:60], "target": k[1], "files": sorted(set(v))}
        for k, v in pair_index.items()
        if len(set(v)) > 1
    ][:100]

    files_in_seq_overlap = sorted(
        {p for _, files in cross_seq_items for p in files}
    )
    files_in_pair_overlap = sorted(
        {p for item in cross_pairs for p in item["files"]}
    )

    tracked = {
        "exact_byte_duplicate_groups": [
            {"sha256": h, "paths": paths, "size_bytes": next(
                (r.file_size_bytes for r in rows if r.sha256 == h), None
            )}
            for h, paths in sorted(exact_dups.items(), key=lambda kv: kv[1][0])
        ],
        "shared_schema_groups": [
            {"schema": s[:500], "paths": paths}
            for s, paths in sorted(shared_schemas.items(), key=lambda kv: -len(kv[1]))
            if len(paths) > 1
        ][:80],
        "n_exact_duplicate_groups": len(exact_dups),
        "n_files_in_duplicate_groups": sum(len(p) for p in exact_dups.values()),
        "n_cross_file_sequence_overlaps": len(cross_seq_items),
        "n_files_in_cross_sequence_overlap": len(files_in_seq_overlap),
        "n_cross_file_sequence_target_pair_overlaps": len(cross_pairs),
        "n_files_in_cross_sequence_target_pair_overlap": len(files_in_pair_overlap),
    }
    samples = {
        "cross_file_sequence_overlap_sample": [
            {"seq_prefix": s, "files": files} for s, files in cross_seq_items
        ],
        "cross_file_sequence_target_pair_overlap_sample": cross_pairs,
    }
    return tracked, samples


def source_rollups(rows: list[FileInspection]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    by_src: dict[str, list[FileInspection]] = defaultdict(list)
    for r in rows:
        by_src[r.top_level_source].append(r)
    for src, items in sorted(by_src.items()):
        exts = Counter(i.extension or "(none)" for i in items)
        roles = Counter(i.apparent_role for i in items)
        records = 0
        for i in items:
            if i.row_count.isdigit():
                records += int(i.row_count)
        flags = Counter()
        for i in items:
            for f in i.possible_issue_flags.split("|"):
                if f:
                    flags[f] += 1
        out[src] = {
            "n_files": len(items),
            "total_bytes": sum(i.file_size_bytes for i in items),
            "extensions": dict(exts),
            "roles": dict(roles),
            "approx_row_or_record_sum": records,
            "top_flags": flags.most_common(15),
            "paths": [i.relative_path for i in items],
        }
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def write_inventory_csv(path: Path, rows: list[FileInspection]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INVENTORY_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            d = asdict(r)
            d.pop("_qc", None)
            d.pop("_schema_sig", None)
            d.pop("_seq_samples", None)
            d.pop("_pair_samples", None)
            d.pop("_id_samples", None)
            d.pop("_workbook_sheets", None)
            if not d.get("current_hash"):
                d["current_hash"] = d.get("sha256", "")
            w.writerow({k: d.get(k, "") for k in INVENTORY_COLUMNS})


def write_workbook_sheets_csv(path: Path, rows: list[FileInspection]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=WORKBOOK_SHEET_COLUMNS)
        w.writeheader()
        for r in rows:
            for sheet in r._workbook_sheets:
                w.writerow({k: sheet.get(k, "") for k in WORKBOOK_SHEET_COLUMNS})
                n += 1
    return n


def load_previous_inventory(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8", newline="") as f:
        return {r["relative_path"]: r for r in csv.DictReader(f)}


def discover_documentation_files(raw_dir: Path, repo_root: Path) -> dict[str, list[str]]:
    """Map top-level source -> documentation-like relative paths."""
    by_src: dict[str, list[str]] = defaultdict(list)
    for p in raw_dir.rglob("*"):
        if not p.is_file():
            continue
        name = p.name
        ext = p.suffix.lower()
        if ext in {".md", ".rtf", ".txt"} and DOC_NAME_RE.search(name):
            pass
        elif "about" in name.lower() and ext == ".pdf":
            pass
        elif name.lower().endswith("qc_report.md"):
            pass
        else:
            continue
        rel = p.relative_to(repo_root).as_posix()
        parts = p.relative_to(raw_dir).parts
        top = parts[0] if parts else "(raw_root)"
        by_src[top].append(rel)
    for k in by_src:
        by_src[k] = sorted(by_src[k])
    return by_src


def extract_readme_snippet(path: Path, limit: int = 400) -> str:
    try:
        raw = path.read_bytes()
    except OSError as e:
        return f"unreadable:{e}"
    text = raw.decode("utf-8", errors="replace")
    if path.suffix.lower() == ".rtf":
        text = re.sub(r"\\[a-z]+-?\d* ?", " ", text)
        text = re.sub(r"[{}]", " ", text)
        text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def recommend_s0_status(insp: FileInspection) -> str:
    rel = insp.relative_path
    name = insp.file_name.lower()
    if name == ".ds_store" or name.startswith("~$"):
        return "not_relevant_to_protein_aptamer_corpus"
    if LATENT_COORDINATE_NAME_RE.search(name) or insp.apparent_role == "latent_coordinate_or_embedding":
        return "not_relevant_to_protein_aptamer_corpus"
    if "/review/" in rel or "/review_v2/" in rel or "/candidates/" in rel or "/inspection/" in rel:
        if "selected_after_manual_review" in name and insp.row_count not in {"", "0"}:
            return "derived_output_not_raw_input"
        if "selected_after_manual_review" in name and insp.row_count in {"", "0"}:
            return "superseded"
        return "derived_output_not_raw_input"
    if "cleaned" in name:
        return "derived_output_not_raw_input"
    if "/fixtures/" in rel:
        return "not_relevant_to_protein_aptamer_corpus"
    if name.endswith(".pdf") and "paper" in insp.top_level_source.lower():
        return "include_with_documented_caveat"
    if insp.top_level_source in {"NCBI_GEO_papers", "NCBI_SRA_papers", "NCBI_PRJNA1221092"}:
        return "not_relevant_to_protein_aptamer_corpus"
    if insp.top_level_source == "rbms_paper":
        return "hold_for_manual_review"
    if insp.top_level_source == "instructNA_paper":
        return "hold_for_manual_review"
    if insp.top_level_source == "riboaptamer" and "all_sequences" in name:
        return "include_as_authoritative_input"
    if insp.top_level_source == "AptaDB" and name in {
        "aptamer.csv",
        "protein.csv",
        "interaction.csv",
    }:
        return "include_as_authoritative_input"
    if insp.top_level_source == "ENA" and name.startswith("ena_embl"):
        return "include_as_authoritative_input"
    if insp.apparent_role in {
        "tabular_data",
        "sequence_reads_fastq",
        "genbank_source_record",
        "scraped_or_assembled_raw_table",
        "manually_extracted_table",
    }:
        return "include_as_authoritative_input"
    if insp.apparent_role in {"documentation", "source_document_pdf"}:
        return "include_with_documented_caveat"
    if insp.apparent_role == "os_metadata":
        return "not_relevant_to_protein_aptamer_corpus"
    return "hold_for_manual_review"


def observed_processing_state(insp: FileInspection) -> str:
    role = insp.apparent_role
    mapping = {
        "curated_or_selected_output": "selected_output",
        "rejected_records": "rejected_output",
        "derived_candidate_processing": "intermediate_candidate_processing",
        "derived_inspection_output": "intermediate_inspection",
        "manual_review_output_or_template": "manual_review_input_or_output",
        "cleaned_derived_output": "cleaned_derivative",
        "scraped_or_assembled_raw_table": "scraped_assembled_source",
        "manually_extracted_table": "manually_extracted_source",
        "fixture_or_test_input": "fixture",
        "backup_or_versioned_copy": "backup",
    }
    if role in mapping:
        return mapping[role]
    if insp.extension in {"csv", "tsv", "xlsx", "fastq", "gb", "txt"} and "derived" not in role:
        return "source_or_export"
    return role or "unclassified"


def enrich_inventory_rows(
    rows: list[FileInspection],
    *,
    previous: dict[str, dict[str, str]],
    docs_by_source: dict[str, list[str]],
    repo_root: Path,
) -> dict[str, Any]:
    """Populate extended fields and compute change summary vs previous inventory."""
    added: list[str] = []
    modified: list[str] = []
    unchanged: list[str] = []
    removed = sorted(set(previous) - {r.relative_path for r in rows})

    # Known supersession relationships (documented / observed)
    superseded_map = {
        "data/raw/ENA/review/ena_selected_after_manual_review.csv": (
            "data/raw/ENA/review_v2/ena_selected_after_manual_review.csv"
        ),
        "data/raw/riboaptamer/rna_aptamer_seqs.csv": (
            "data/raw/riboaptamer/all_sequences_509_rows.csv"
        ),
        "data/raw/riboaptamer/rna_aptamer_seqs.xlsx": (
            "data/raw/riboaptamer/all_sequences_509_rows.csv"
        ),
    }

    for r in rows:
        r.current_hash = r.sha256
        prev = previous.get(r.relative_path)
        if prev is None:
            r.change_since_previous_inventory = "added"
            r.last_inventory_hash = ""
            added.append(r.relative_path)
        else:
            r.last_inventory_hash = prev.get("sha256", "")
            if r.last_inventory_hash and r.sha256 and r.sha256 == r.last_inventory_hash:
                # Identical bytes: treat as unchanged even if decoded column labels
                # differ due to encoding fallback (e.g. AptaDB latin-1 exports).
                if prev.get("row_count") != r.row_count or prev.get("column_names") != r.column_names:
                    r.change_since_previous_inventory = "unchanged_bytes_schema_decode_diff"
                    notes_extra = (
                        "inventory_decode_diff_only_same_sha256;"
                        f"prior_cols_differ={prev.get('column_names') != r.column_names}"
                    )
                    r.notes = (r.notes + "; " if r.notes else "") + notes_extra
                else:
                    r.change_since_previous_inventory = "unchanged"
                unchanged.append(r.relative_path)
            elif r.last_inventory_hash and r.sha256 and r.sha256 != r.last_inventory_hash:
                r.change_since_previous_inventory = "modified_content"
                modified.append(r.relative_path)
            elif prev.get("row_count") != r.row_count or prev.get("column_names") != r.column_names:
                r.change_since_previous_inventory = "modified_schema_or_rows"
                modified.append(r.relative_path)
            else:
                r.change_since_previous_inventory = "unchanged"
                unchanged.append(r.relative_path)

        docs = docs_by_source.get(r.top_level_source, [])
        r.documentation_files = "|".join(docs)
        snippets = []
        for drel in docs[:3]:
            dpath = repo_root / drel
            if dpath.is_file():
                snippets.append(f"{Path(drel).name}: {extract_readme_snippet(dpath, 220)}")
        r.readme_notes = " || ".join(snippets)[:1500]

        # Lightweight documented fields from path + README presence
        if docs:
            r.documented_source = f"local_docs:{len(docs)}"
        if "selected" in r.file_name.lower():
            r.documented_processing_state = "selected_or_curated_output"
        elif "interaction" in r.file_name.lower() and r.top_level_source == "AptaDB":
            r.documented_processing_state = "official_interaction_export"
            r.documented_source = "AptaDB download (Interaction CSV)"
        elif r.file_name.startswith("all_sequences") and r.top_level_source == "riboaptamer":
            r.documented_processing_state = "corrected_full_sequence_export"
            r.documented_source = "Ribocentre-aptamer database"
        elif r.top_level_source == "precision_selex_against_kpc2_paper":
            r.documented_source = "Yu et al. 2021 Talanta Precision-SELEX (see README_extracted_data.md)"

        r.observed_processing_state = observed_processing_state(r)
        r.recommended_S0_status = recommend_s0_status(r)
        r.superseded_by = superseded_map.get(r.relative_path, "")

        # Sequence type from QC notes if not already set
        if not r.sequence_type:
            m = re.search(r"inferred_sequence_type=([A-Za-z0-9_]+)", r.notes or "")
            if m:
                r.sequence_type = m.group(1)
            elif r._qc.get("seq_type"):
                r.sequence_type = str(r._qc["seq_type"])

        if r.target_column_candidates:
            r.target_type = "columns_present"
        if r.top_level_source == "AptaDB" and r.file_name == "interaction.csv":
            r.target_type = "protein_molecule_cell_other_via_Target_chemistry"
            r.authoritative_candidate = "yes"
        if r.relative_path.endswith("ena_selected_after_manual_review.csv") and "/review_v2/" in r.relative_path:
            r.authoritative_candidate = "yes_for_ena_selected_raw_lane"
            r.unresolved_questions = (
                "near_duplicate_family_id empty for ~46% rows (likely singletons);"
                "processed supplement lacks experiment_group_id column"
            )
        if r.file_name == "all_sequences_509_rows.csv":
            r.authoritative_candidate = "yes"
            r.sequence_type = "RNA_or_mixed_from_Category"
        if LATENT_COORDINATE_NAME_RE.search(r.file_name) or r.apparent_role == "latent_coordinate_or_embedding":
            r.apparent_role = "latent_coordinate_or_embedding"
            r.sequence_type = "not_applicable_latent_coordinates"
            r.sequence_column_candidates = ""
            r.authoritative_candidate = "no_latent_coordinates_not_sequence_input"
            r.recommended_S0_status = "not_relevant_to_protein_aptamer_corpus"
            r.documented_processing_state = "vae_latent_coordinate_export"
            if not r.documented_source:
                r.documented_source = "AptaDiff encode/diffusion latent table"
            extra = (
                "latent_coordinate_file_excluded_from_corpus_sequence_inputs;"
                "paired_sequence_table_is_datasetA_IGFBP3_P6.csv"
            )
            r.notes = (r.notes + "; " if r.notes else "") + extra
        if r.relative_path.endswith("extracted_data.xlsx") and "precision_selex" in r.relative_path:
            r.authoritative_candidate = "yes_with_readme_schema"
            r.sequence_type = "DNA_ssDNA"
            r.target_type = "protein_KPC-2"
            r.unresolved_questions = "column_I_heading_incomplete_library1_interpretation"

        # Authoritative heuristics for major exports
        if r.relative_path in {
            "data/raw/ENA/ena_embl_20260720-0853.txt",
            "data/raw/Aptadiff_datasetA/datasetA_IGFBP3_P6.csv",
            "data/raw/AptaDB/aptamer.csv",
            "data/raw/AptaDB/protein.csv",
            "data/raw/AptaIndex/aptamers-export-2026-07-22.csv",
            "data/raw/aptabase/aptabase_raw.csv",
            "data/raw/aptamerbase/aptamerbase_aptamers.csv",
        } or r.file_name.startswith("UTexas Aptamer Database"):
            r.authoritative_candidate = r.authoritative_candidate or "yes"

    return {
        "added": added,
        "modified": modified,
        "unchanged": unchanged,
        "removed": removed,
        "n_added": len(added),
        "n_modified": len(modified),
        "n_unchanged": len(unchanged),
        "n_removed": len(removed),
    }


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: two levels above this script)",
    )
    p.add_argument(
        "--raw-dir",
        type=Path,
        default=None,
        help="Override raw data directory (default: <repo>/data/raw)",
    )
    p.add_argument(
        "--out-csv",
        type=Path,
        default=None,
        help="Inventory CSV path",
    )
    p.add_argument(
        "--out-summary-json",
        type=Path,
        default=None,
        help="Summary JSON path",
    )
    p.add_argument(
        "--previous-inventory",
        type=Path,
        default=None,
        help="Prior inventory CSV for change detection",
    )
    p.add_argument(
        "--out-workbook-sheets",
        type=Path,
        default=None,
        help="Workbook sheet metadata CSV path",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    script_path = Path(__file__).resolve()
    repo_root = (args.repo_root or script_path.parents[2]).resolve()
    raw_dir = (args.raw_dir or (repo_root / "data" / "raw")).resolve()
    out_csv = (
        args.out_csv or (repo_root / "docs" / "data_curation" / "raw_data_inventory.csv")
    ).resolve()
    out_json = (
        args.out_summary_json
        or (repo_root / "docs" / "data_curation" / "raw_data_inventory_summary.json")
    ).resolve()
    out_sheets = (
        args.out_workbook_sheets
        or (repo_root / "docs" / "data_curation" / "raw_data_workbook_sheets.csv")
    ).resolve()
    previous_path = args.previous_inventory
    if previous_path is None:
        cand = repo_root / "docs" / "data_curation" / "_prior_raw_data_inventory.csv"
        previous_path = cand if cand.is_file() else out_csv
    previous_path = previous_path.resolve()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log = logging.getLogger("inventory_raw_data")

    if not raw_dir.is_dir():
        log.error("Raw directory not found: %s", raw_dir)
        return 2

    # Safety: outputs must not be inside data/raw
    for out in (out_csv, out_json, out_sheets):
        try:
            out.relative_to(raw_dir)
            log.error("Refusing to write outputs under data/raw: %s", out)
            return 2
        except ValueError:
            pass

    log.info("Repository root: %s", repo_root)
    log.info("Scanning raw directory (read-only): %s", raw_dir)
    log.info("Previous inventory for diffs: %s", previous_path)

    previous = load_previous_inventory(previous_path)
    docs_by_source = discover_documentation_files(raw_dir, repo_root)
    log.info(
        "Documentation files discovered: %d across %d sources",
        sum(len(v) for v in docs_by_source.values()),
        len(docs_by_source),
    )

    all_paths = sorted(p for p in raw_dir.rglob("*") if p.is_file())
    dir_count = sum(1 for p in raw_dir.rglob("*") if p.is_dir()) + 1  # include raw itself
    log.info("Found %d files in %d directories", len(all_paths), dir_count)

    rows: list[FileInspection] = []
    unreadable: list[str] = []
    for i, path in enumerate(all_paths, 1):
        rel = path.relative_to(repo_root).as_posix()
        log.info("[%d/%d] %s", i, len(all_paths), rel)
        insp = inspect_file(path, repo_root)
        rows.append(insp)
        if insp.readable != "yes":
            unreadable.append(rel)

    # Deterministic sort
    rows.sort(key=lambda r: r.relative_path)

    changes = enrich_inventory_rows(
        rows,
        previous=previous,
        docs_by_source=docs_by_source,
        repo_root=repo_root,
    )
    log.info(
        "Change summary vs previous: added=%d modified=%d removed=%d unchanged=%d",
        changes["n_added"],
        changes["n_modified"],
        changes["n_removed"],
        changes["n_unchanged"],
    )

    write_inventory_csv(out_csv, rows)
    log.info("Wrote inventory CSV: %s (%d rows)", out_csv, len(rows))
    n_sheets = write_workbook_sheets_csv(out_sheets, rows)
    log.info("Wrote workbook sheets CSV: %s (%d sheet rows)", out_sheets, n_sheets)

    overlap, overlap_samples = build_overlap_summary(rows)
    out_overlap_samples = (
        repo_root / "data" / "interim" / "inventory" / "sequence_overlap_samples.json"
    ).resolve()
    # Safety: sequence samples must never land under data/raw or under docs/
    try:
        out_overlap_samples.relative_to(raw_dir)
        log.error("Refusing to write sequence samples under data/raw: %s", out_overlap_samples)
        return 2
    except ValueError:
        pass
    out_overlap_samples.parent.mkdir(parents=True, exist_ok=True)
    out_overlap_samples.write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
                "note": (
                    "Local-only sequence-level overlap samples. "
                    "Not for version control; tracked summary keeps aggregate counts only."
                ),
                **overlap_samples,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    log.info("Wrote local sequence overlap samples: %s", out_overlap_samples)

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "raw_dir": str(raw_dir.relative_to(repo_root)),
        "previous_inventory": str(previous_path),
        "n_directories": dir_count,
        "n_files": len(rows),
        "total_bytes": sum(r.file_size_bytes for r in rows),
        "unreadable_or_partial": unreadable,
        "documentation_files_by_source": docs_by_source,
        "changes_since_previous_inventory": changes,
        "extension_counts": dict(
            Counter(r.extension or "(none)" for r in rows).most_common()
        ),
        "role_counts": dict(Counter(r.apparent_role for r in rows).most_common()),
        "s0_status_counts": dict(
            Counter(r.recommended_S0_status for r in rows).most_common()
        ),
        "sources": source_rollups(rows),
        "overlap": overlap,
        "sequence_overlap_samples_path": str(
            out_overlap_samples.relative_to(repo_root)
        ),
        "assumptions": [
            "Read-only with respect to data/raw",
            "XLSX inspected via stdlib zipfile/xml; all sheets listed, first sheet QC",
            "Large file QC may be sample-based (flagged)",
            "DNA_or_RNA_stored_as_T means T-alphabet without U; ENA RNA often uses T",
            "Cross-file sequence overlap uses sampled/normalized sequences, not full all-pairs",
            "Sequence-level overlap samples are written only under ignored data/interim/",
            "Tracked inventory artefacts omit raw aptamer sequence values and prefixes",
            "Change detection uses prior inventory SHA-256/row_count/column_names when available",
            "README snippets are truncated extracts for inventory notes, not full documents",
            "AptaDiff *_x_z.csv files are latent-coordinate inputs, not corpus sequence tables",
        ],
        "checks_not_feasibly_complete": [
            "All-against-all sequence similarity clustering",
            "Full biological validity of unusual aptamer chemistries / modifications",
            "PDF table extraction",
            "HTML DOM record extraction (inventory only notes HTML presence)",
            "Complete deep QC of every row in multi-million-read FASTQ beyond sample+count",
        ],
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    log.info("Wrote summary JSON: %s", out_json)

    # Coverage check
    inventored = {r.relative_path for r in rows}
    expected = {p.relative_to(repo_root).as_posix() for p in all_paths}
    missing = sorted(expected - inventored)
    extra = sorted(inventored - expected)
    if missing or extra:
        log.error("Coverage mismatch missing=%s extra=%s", missing, extra)
        return 1

    log.info(
        "SUMMARY files=%d dirs=%d unreadable_or_partial=%d exact_dup_groups=%d added=%d removed=%d",
        len(rows),
        dir_count,
        len(unreadable),
        overlap["n_exact_duplicate_groups"],
        changes["n_added"],
        changes["n_removed"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

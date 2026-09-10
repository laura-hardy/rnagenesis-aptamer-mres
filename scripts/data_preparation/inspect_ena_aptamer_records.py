#!/usr/bin/env python3
"""Inspect ENA/EMBL flat-file search results for RNA aptamer-related records.

This is a **diagnostic inventory** stage only. It inventories record structure,
phrases, feature annotations, sequence alphabets, discrepancies and provisional
evidence signals. It does **not** build a final candidate aptamer dataset, does
not convert T→U in place, and does not decide corpus inclusion.

ENA commonly stores biological RNA using T rather than U. That convention is
reported as a diagnostic observation, not treated as an automatic error.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

try:
    from Bio import SeqIO  # type: ignore

    HAS_BIOPYTHON = True
except ImportError:  # pragma: no cover - optional cross-check
    HAS_BIOPYTHON = False

# ---------------------------------------------------------------------------
# Editable phrase inventories (case-insensitive matching)
# ---------------------------------------------------------------------------

PHRASE_CATEGORIES: dict[str, list[str]] = {
    "selection": [
        "SELEX",
        "systematic evolution of ligands",
        "in vitro selected",
        "in-vitro selected",
        "in vitro evolved",
        "in-vitro evolved",
        "selected RNA",
        "selected DNA",
        "selected ligand",
        "random library",
        "combinatorial library",
        "selection round",
        "binding selection",
        "genomic SELEX",
        "cell-SELEX",
        "capture-SELEX",
        "in vitro selection",
        "in-vitro selection",
        "in vitro evolution",
        "in-vitro evolution",
    ],
    "synthetic": [
        "synthetic construct",
        "artificial sequence",
        "artificial sequences",
        "engineered",
        "synthetic RNA",
        "synthetic DNA",
        "in vitro transcript",
        "transcribed",
        "T7 promoter",
        "SP6 promoter",
    ],
    "natural_genomic": [
        "genomic",
        "gene",
        "antisense",
        "Homo sapiens",
        "Mus musculus",
        "bacterial",
        "archaeal",
        "chromosome",
        "genomic locus",
        "natural aptamer",
        "conserved motif",
        "TPA:inferential",
        "Third Party Data",
    ],
    "riboswitch": [
        "riboswitch",
        "aptamer domain",
        "metabolite-sensing RNA",
        "cis-regulatory",
        "regulatory RNA",
        "leader RNA",
    ],
    "engineered_construct": [
        "aptazyme",
        "ribozyme",
        "molecular switch",
        "biosensor",
        "reporter",
        "expression construct",
        "vector",
        "cassette",
        "fusion",
        "chimeric",
        "allosteric",
    ],
    "sequence_role": [
        "complete sequence",
        "partial sequence",
        "core aptamer",
        "minimal aptamer",
        "truncated",
        "primer",
        "primer-binding",
        "random region",
        "variable region",
        "flanking sequence",
        "template",
        "promoter",
        "reverse complement",
        "complement",
    ],
    "target": [
        "binds to",
        "binding to",
        "recognizes",
        "recognise",
        "specific for",
        "targeting",
        "against",
        "ligand",
        "substrate",
    ],
    "aptamer": [
        "aptamer",
        "aptamers",
    ],
}

# Title terms used only as a provisional primary-selection-reference signal.
PRIMARY_SELECTION_TITLE_TERMS = [
    "selection",
    "isolation",
    "identification",
    "in vitro evolution",
    "SELEX",
    "characterization of aptamers",
    "characterisation of aptamers",
]

T7_PROMOTER_DNA = "TAATACGACTCACTATA"
T7_PROMOTER_RNA = "UAAUACGACUCACUAUA"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "raw" / "ena" / "inspection"
DEFAULT_INPUT_CANDIDATES = [
    REPO_ROOT / "data" / "raw" / "ena" / "input" / "ena_rna_aptamer_search.embl",
    REPO_ROOT / "data" / "raw" / "ENA" / "ena_embl_20260720-0853.txt",
]

EXPECTED_OUTPUT_FILES = [
    "ena_record_inventory.csv",
    "ena_keyword_summary.csv",
    "ena_record_class_signals.csv",
    "ena_feature_summary.csv",
    "ena_sequence_diagnostics.csv",
    "ena_reference_summary.csv",
    "ena_duplicate_summary.csv",
    "ena_review_examples.csv",
    "ena_inspection_report.md",
    "ena_inspection_log.txt",
]

RAW_EXCERPT_MAX_CHARS = 800

logger = logging.getLogger("inspect_ena_aptamer_records")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class FeatureQualifier:
    name: str
    value: str


@dataclass
class Feature:
    feature_index: int
    feature_key: str
    location_raw: str
    start: int | None
    end: int | None
    strand: str  # "+", "-", or "complex"
    is_complement: bool
    is_join: bool
    length: int | None
    qualifiers: list[FeatureQualifier] = field(default_factory=list)

    def qualifier_values(self, name: str) -> list[str]:
        return [q.value for q in self.qualifiers if q.name == name]


@dataclass
class Reference:
    reference_number: int
    titles_raw: list[str] = field(default_factory=list)
    authors_raw: list[str] = field(default_factory=list)
    locations_raw: list[str] = field(default_factory=list)
    doi_values: list[str] = field(default_factory=list)
    pubmed_values: list[str] = field(default_factory=list)
    rp: str = ""

    @property
    def title_joined(self) -> str:
        return " ".join(self.titles_raw).strip()

    @property
    def authors_joined(self) -> str:
        return " ".join(self.authors_raw).strip()

    @property
    def location_joined(self) -> str:
        return " ".join(self.locations_raw).strip()


@dataclass
class SequenceDiagnostics:
    sequence_deposited: str
    sequence_length_calculated: int
    sequence_alphabet: str
    count_A: int
    count_C: int
    count_G: int
    count_T: int
    count_U: int
    count_N: int
    count_other: int
    gc_percent_calculated: float | None
    sq_summary_raw: str = ""
    sq_reported_length: int | None = None
    sq_count_summary: dict[str, int] = field(default_factory=dict)


@dataclass
class PhraseHits:
    """Matched phrases and the fields in which they were found."""

    matched_by_category: dict[str, list[str]] = field(default_factory=dict)
    fields_by_category: dict[str, list[str]] = field(default_factory=dict)

    def add(self, category: str, phrase: str, field_name: str) -> None:
        self.matched_by_category.setdefault(category, [])
        self.fields_by_category.setdefault(category, [])
        if phrase not in self.matched_by_category[category]:
            self.matched_by_category[category].append(phrase)
        if field_name not in self.fields_by_category[category]:
            self.fields_by_category[category].append(field_name)

    def terms(self, category: str) -> str:
        return "|".join(self.matched_by_category.get(category, []))

    def fields(self, category: str) -> str:
        return "|".join(self.fields_by_category.get(category, []))

    def has(self, category: str) -> bool:
        return bool(self.matched_by_category.get(category))

    def all_terms(self) -> str:
        terms: list[str] = []
        for cat_terms in self.matched_by_category.values():
            for term in cat_terms:
                if term not in terms:
                    terms.append(term)
        return "|".join(terms)


@dataclass
class EnaRecord:
    """Internal representation preserving both structured fields and raw text."""

    record_index: int
    raw_record_text: str
    raw_record_character_count: int
    raw_record_line_count: int
    record_id_line: str = ""
    accession: str = ""
    sequence_version: str = ""
    description_raw: list[str] = field(default_factory=list)
    description_joined: str = ""
    keywords: str = ""
    organism: str = ""
    taxonomy_raw: list[str] = field(default_factory=list)
    taxonomy: str = ""
    molecule_type: str = ""
    topology: str = ""
    data_class: str = ""
    taxonomic_division: str = ""
    reported_length: int | None = None
    created_date: str = ""
    updated_date: str = ""
    references: list[Reference] = field(default_factory=list)
    database_cross_references: list[str] = field(default_factory=list)
    features: list[Feature] = field(default_factory=list)
    sequence: SequenceDiagnostics | None = None
    parse_status: str = "ok"
    parse_warnings: list[str] = field(default_factory=list)
    phrase_hits: PhraseHits = field(default_factory=PhraseHits)
    signals: dict[str, bool] = field(default_factory=dict)
    discrepancies: list[str] = field(default_factory=list)
    contains_t7_promoter_like_motif: bool = False
    t7_promoter_start: int | None = None
    t7_promoter_match: str = ""
    t7_promoter_position: str = ""
    biopython_parse_ok: bool | None = None


# ---------------------------------------------------------------------------
# Low-level EMBL helpers
# ---------------------------------------------------------------------------


def _join_multiline(parts: Iterable[str]) -> str:
    """Join multiline EMBL field continuation lines with single spaces."""
    return re.sub(r"\s+", " ", " ".join(p.strip() for p in parts if p is not None)).strip()


def _field_body(line: str) -> str:
    """Return the content after the two-letter tag and spaces (cols 6+)."""
    if len(line) >= 5:
        return line[5:]
    return line.strip()


def split_embl_records(text: str) -> list[str]:
    """Split an ENA/EMBL flat file on the record terminator ``//``.

    Blank lines alone are never used as record boundaries. Trailing empty
    blocks after a final ``//`` are discarded.
    """
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"(?m)^//\s*$", normalised)
    blocks: list[str] = []
    for part in parts:
        if not part.strip():
            continue
        blocks.append(part.strip() + "\n")
    return blocks


def parse_id_line(id_line: str) -> dict[str, Any]:
    """Parse an EMBL ID line into structured fields.

    Example:
        ID   AF083271; SV 1; linear; genomic RNA; STD; SYN; 77 BP.
    """
    body = id_line[5:].strip() if id_line.startswith("ID") else id_line.strip()
    body = body.rstrip(".")
    parts = [p.strip() for p in body.split(";")]
    result: dict[str, Any] = {
        "primary_id": parts[0] if parts else "",
        "sequence_version": "",
        "topology": "",
        "molecule_type": "",
        "data_class": "",
        "taxonomic_division": "",
        "reported_length": None,
    }
    known_classes = {
        "STD",
        "EST",
        "PAT",
        "STS",
        "GSS",
        "HTC",
        "HTG",
        "MGA",
        "WGS",
        "TSA",
        "TLS",
        "CON",
    }
    for part in parts[1:]:
        upper = part.upper()
        if upper.startswith("SV "):
            result["sequence_version"] = part[3:].strip()
        elif part.lower() in {"linear", "circular"}:
            result["topology"] = part.lower()
        elif upper in known_classes:
            result["data_class"] = upper
        elif re.search(r"\d+\s*BP", part, re.I):
            match = re.search(r"(\d+)\s*BP", part, re.I)
            if match:
                result["reported_length"] = int(match.group(1))
        elif re.fullmatch(r"[A-Z]{3}", part) and not result["taxonomic_division"]:
            result["taxonomic_division"] = part
        elif not result["molecule_type"]:
            result["molecule_type"] = part
    return result


_LOC_PAIR = re.compile(r"(?P<start>\d+)\.\.(?P<end>\d+)")


def parse_feature_location(location_raw: str) -> dict[str, Any]:
    """Parse a feature location string into start/end/strand flags.

    Complex locations are flagged rather than silently simplified.
    """
    loc = location_raw.strip()
    is_complement = "complement" in loc.lower()
    is_join = "join" in loc.lower()
    starts: list[int] = []
    ends: list[int] = []
    for match in _LOC_PAIR.finditer(loc):
        starts.append(int(match.group("start")))
        ends.append(int(match.group("end")))
    start = min(starts) if starts else None
    end = max(ends) if ends else None
    length: int | None = None
    if start is not None and end is not None and not is_join:
        length = end - start + 1
    elif starts and ends and is_join:
        length = sum(e - s + 1 for s, e in zip(starts, ends))
    if is_join:
        strand = "complex"
    elif is_complement:
        strand = "-"
    else:
        strand = "+"
    return {
        "start": start,
        "end": end,
        "strand": strand,
        "is_complement": is_complement,
        "is_join": is_join,
        "length": length,
    }


def extract_sequence_from_raw(raw_text: str) -> SequenceDiagnostics:
    """Extract deposited sequence letters from SQ lines only.

    Position numbers at the end of sequence lines and the SQ summary line
    itself are excluded. The deposited alphabet is never altered.
    """
    lines = raw_text.splitlines()
    sq_summary = ""
    collecting = False
    seq_chunks: list[str] = []
    for line in lines:
        if line.startswith("SQ"):
            collecting = True
            sq_summary = _field_body(line).strip()
            continue
        if not collecting:
            continue
        if line.startswith("//"):
            break
        # New two-letter tagged field after SQ would be unexpected.
        if len(line) >= 5 and line[:2].isalpha() and line[2:5] == "   " and not line.startswith(" "):
            break
        body = line.strip()
        if not body:
            continue
        # Keep only letters; strip spaces and trailing position counters.
        letters = re.sub(r"[^A-Za-z]", "", body)
        seq_chunks.append(letters)

    sequence = "".join(seq_chunks).upper()
    count_A = sequence.count("A")
    count_C = sequence.count("C")
    count_G = sequence.count("G")
    count_T = sequence.count("T")
    count_U = sequence.count("U")
    count_N = sequence.count("N")
    iupac_extra = sum(sequence.count(base) for base in "RYWSMKHBVD")
    recognised = count_A + count_C + count_G + count_T + count_U + count_N + iupac_extra
    count_other = len(sequence) - recognised

    if not sequence:
        alphabet = "missing"
    elif count_other > 0:
        alphabet = "invalid"
    elif count_T > 0 and count_U > 0:
        alphabet = "mixed_T_U"
    elif count_N > 0 or iupac_extra > 0:
        alphabet = "ambiguous_nucleotide"
    elif count_U > 0 and count_T == 0:
        alphabet = "RNA_alphabet"
    else:
        # A/C/G/T (or A/C/G only): DNA-style deposited alphabet.
        # Important: ENA often stores biological RNA with T; report alphabet only.
        alphabet = "DNA_alphabet"

    gc = None
    acgtu = count_A + count_C + count_G + count_T + count_U
    if acgtu > 0:
        gc = round(100.0 * (count_G + count_C) / acgtu, 2)

    sq_reported_length = None
    sq_counts: dict[str, int] = {}
    if sq_summary:
        match_len = re.search(r"(\d+)\s*BP", sq_summary, re.I)
        if match_len:
            sq_reported_length = int(match_len.group(1))
        for base in ("A", "C", "G", "T", "U"):
            match = re.search(rf"(\d+)\s*{base}\b", sq_summary, re.I)
            if match:
                sq_counts[base] = int(match.group(1))
        match_other = re.search(r"(\d+)\s*other", sq_summary, re.I)
        if match_other:
            sq_counts["other"] = int(match_other.group(1))

    return SequenceDiagnostics(
        sequence_deposited=sequence,
        sequence_length_calculated=len(sequence),
        sequence_alphabet=alphabet,
        count_A=count_A,
        count_C=count_C,
        count_G=count_G,
        count_T=count_T,
        count_U=count_U,
        count_N=count_N,
        count_other=count_other,
        gc_percent_calculated=gc,
        sq_summary_raw=sq_summary,
        sq_reported_length=sq_reported_length,
        sq_count_summary=sq_counts,
    )


def parse_feature_table(raw_text: str) -> list[Feature]:
    """Parse FT feature keys, locations and multiline qualifiers."""
    features: list[Feature] = []
    current: Feature | None = None
    current_qual_name: str | None = None
    current_qual_parts: list[str] = []

    def flush_qualifier() -> None:
        nonlocal current_qual_name, current_qual_parts
        if current is None or current_qual_name is None:
            return
        value = _join_multiline(current_qual_parts)
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1]
        current.qualifiers.append(FeatureQualifier(current_qual_name, value))
        current_qual_name = None
        current_qual_parts = []

    def flush_feature() -> None:
        nonlocal current
        flush_qualifier()
        if current is not None:
            features.append(current)
            current = None

    for line in raw_text.splitlines():
        if not line.startswith("FT"):
            if current is not None and (line.startswith("SQ") or line.startswith("//")):
                flush_feature()
            continue
        body = _field_body(line)
        # New feature key lines start with a non-space key token.
        if body and not body.startswith(" ") and not body.startswith("/"):
            flush_feature()
            match = re.match(r"^(\S+)\s+(\S.*)$", body)
            if match:
                key = match.group(1)
                loc = match.group(2).strip()
            else:
                key = body.strip()
                loc = ""
            loc_info = (
                parse_feature_location(loc)
                if loc
                else {
                    "start": None,
                    "end": None,
                    "strand": "+",
                    "is_complement": False,
                    "is_join": False,
                    "length": None,
                }
            )
            current = Feature(
                feature_index=len(features),
                feature_key=key,
                location_raw=loc,
                start=loc_info["start"],
                end=loc_info["end"],
                strand=loc_info["strand"],
                is_complement=loc_info["is_complement"],
                is_join=loc_info["is_join"],
                length=loc_info["length"],
            )
            current_qual_name = None
            current_qual_parts = []
        elif current is not None:
            stripped = body.strip()
            if stripped.startswith("/"):
                flush_qualifier()
                if "=" in stripped:
                    name, val = stripped[1:].split("=", 1)
                    current_qual_name = name.strip()
                    current_qual_parts = [val]
                else:
                    current_qual_name = stripped[1:].strip()
                    current_qual_parts = [""]
            elif current_qual_name is not None:
                current_qual_parts.append(stripped)
            elif stripped:
                current.location_raw = (current.location_raw + stripped).strip()
                loc_info = parse_feature_location(current.location_raw)
                current.start = loc_info["start"]
                current.end = loc_info["end"]
                current.strand = loc_info["strand"]
                current.is_complement = loc_info["is_complement"]
                current.is_join = loc_info["is_join"]
                current.length = loc_info["length"]

    flush_feature()
    return features


def parse_references(raw_text: str) -> list[Reference]:
    """Parse RN/RP/RX/RA/RT/RL reference blocks."""
    references: list[Reference] = []
    current: Reference | None = None
    current_rt: list[str] = []
    current_ra: list[str] = []
    current_rl: list[str] = []

    def flush() -> None:
        nonlocal current, current_rt, current_ra, current_rl
        if current is None:
            return
        current.titles_raw = list(current_rt)
        current.authors_raw = list(current_ra)
        current.locations_raw = list(current_rl)
        references.append(current)
        current = None
        current_rt, current_ra, current_rl = [], [], []

    stop_tags = ("XX", "DR", "FH", "FT", "SQ", "CC", "KW", "DE", "OS", "OC", "DT", "AC", "ID")

    for line in raw_text.splitlines():
        if line.startswith("RN"):
            flush()
            match = re.search(r"\[(\d+)\]", line)
            num = int(match.group(1)) if match else len(references) + 1
            current = Reference(reference_number=num)
        elif current is None:
            continue
        elif line.startswith("RP"):
            current.rp = _field_body(line).strip()
        elif line.startswith("RX"):
            body = _field_body(line).strip().rstrip(".")
            if body.upper().startswith("DOI"):
                doi = body.split(";", 1)[-1].strip().rstrip(".")
                if doi:
                    current.doi_values.append(doi)
            elif body.upper().startswith("PUBMED"):
                pmid = body.split(";", 1)[-1].strip().rstrip(".")
                if pmid:
                    current.pubmed_values.append(pmid)
        elif line.startswith("RA"):
            current_ra.append(_field_body(line).strip())
        elif line.startswith("RT"):
            current_rt.append(_field_body(line).strip().strip('"'))
        elif line.startswith("RL"):
            current_rl.append(_field_body(line).strip())
        elif line.startswith(stop_tags):
            flush()

    flush()
    return references


def parse_raw_record(record_index: int, raw_text: str) -> EnaRecord:
    """Parse one ENA record block into structured fields + raw text."""
    lines = raw_text.splitlines()
    record = EnaRecord(
        record_index=record_index,
        raw_record_text=raw_text,
        raw_record_character_count=len(raw_text),
        raw_record_line_count=len(lines),
    )

    if not raw_text.strip():
        record.parse_status = "malformed"
        record.parse_warnings.append("empty_record_block")
        return record

    de_parts: list[str] = []
    oc_parts: list[str] = []
    kw_parts: list[str] = []
    os_parts: list[str] = []
    ac_parts: list[str] = []
    dt_lines: list[str] = []
    dr_parts: list[str] = []
    id_line = ""

    for line in lines:
        tag = line[:2] if len(line) >= 2 else ""
        if tag == "ID":
            id_line = line
        elif tag == "AC":
            ac_parts.append(_field_body(line).strip().rstrip(";"))
        elif tag == "DT":
            dt_lines.append(_field_body(line).strip())
        elif tag == "DE":
            de_parts.append(_field_body(line).strip())
        elif tag == "KW":
            kw_parts.append(_field_body(line).strip().rstrip("."))
        elif tag == "OS":
            os_parts.append(_field_body(line).strip())
        elif tag == "OC":
            oc_parts.append(_field_body(line).strip().rstrip("."))
        elif tag == "DR":
            dr_parts.append(_field_body(line).strip().rstrip("."))

    record.record_id_line = id_line
    if not id_line:
        record.parse_status = "malformed"
        record.parse_warnings.append("missing_ID_line")
    else:
        id_info = parse_id_line(id_line)
        record.sequence_version = str(id_info.get("sequence_version") or "")
        record.topology = str(id_info.get("topology") or "")
        record.molecule_type = str(id_info.get("molecule_type") or "")
        record.data_class = str(id_info.get("data_class") or "")
        record.taxonomic_division = str(id_info.get("taxonomic_division") or "")
        record.reported_length = id_info.get("reported_length")

    accessions: list[str] = []
    for chunk in ac_parts:
        for tok in chunk.split(";"):
            tok = tok.strip()
            if tok:
                accessions.append(tok)
    record.accession = accessions[0] if accessions else ""
    if not record.accession and id_line:
        id_info = parse_id_line(id_line)
        record.accession = str(id_info.get("primary_id") or "")
        if record.accession:
            record.parse_warnings.append("accession_taken_from_ID_line")
    if not record.accession:
        if record.parse_status == "ok":
            record.parse_status = "malformed"
        record.parse_warnings.append("missing_accession")

    record.description_raw = de_parts
    record.description_joined = _join_multiline(de_parts)
    record.keywords = _join_multiline(kw_parts)
    record.organism = _join_multiline(os_parts)
    record.taxonomy_raw = oc_parts
    record.taxonomy = _join_multiline(oc_parts)
    record.database_cross_references = dr_parts

    for dt in dt_lines:
        if "Created" in dt and not record.created_date:
            record.created_date = dt
        elif "Last updated" in dt or "updated" in dt.lower():
            record.updated_date = dt
        elif not record.created_date:
            record.created_date = dt

    try:
        record.references = parse_references(raw_text)
    except Exception as exc:  # noqa: BLE001 - diagnostic stage
        record.parse_warnings.append(f"reference_parse_failure:{exc}")

    try:
        record.features = parse_feature_table(raw_text)
    except Exception as exc:  # noqa: BLE001
        record.parse_warnings.append(f"feature_parse_failure:{exc}")

    try:
        record.sequence = extract_sequence_from_raw(raw_text)
        if record.sequence.sequence_alphabet == "missing":
            record.parse_warnings.append("missing_sequence")
    except Exception as exc:  # noqa: BLE001
        record.parse_warnings.append(f"sequence_parse_failure:{exc}")
        record.sequence = SequenceDiagnostics(
            sequence_deposited="",
            sequence_length_calculated=0,
            sequence_alphabet="missing",
            count_A=0,
            count_C=0,
            count_G=0,
            count_T=0,
            count_U=0,
            count_N=0,
            count_other=0,
            gc_percent_calculated=None,
        )

    if record.parse_status == "ok" and not id_line and not accessions:
        record.parse_status = "malformed"
        record.parse_warnings.append("implausible_record_block")

    return record


# ---------------------------------------------------------------------------
# Phrase search, signals, discrepancies
# ---------------------------------------------------------------------------


def _search_phrases_in_text(text: str, phrases: list[str]) -> list[str]:
    """Case-insensitive phrase search.

    Short alphabetic tokens (e.g. ``gene``) use word-boundary matching so that
    ``generated`` does not count as a genomic ``gene`` hit.
    """
    if not text:
        return []
    lower = text.lower()
    hits: list[str] = []
    for phrase in phrases:
        needle = phrase.lower()
        if re.fullmatch(r"[a-z0-9+-]+", needle) and len(needle) <= 6:
            if re.search(rf"\b{re.escape(needle)}\b", lower):
                hits.append(phrase)
        elif needle in lower:
            hits.append(phrase)
    return hits


def collect_phrase_hits(record: EnaRecord) -> PhraseHits:
    """Search biologically relevant phrases across separate field sources."""
    hits = PhraseHits()

    feature_notes: list[str] = []
    products: list[str] = []
    ncrna_classes: list[str] = []
    for feat in record.features:
        feature_notes.extend(feat.qualifier_values("note"))
        products.extend(feat.qualifier_values("product"))
        ncrna_classes.extend(feat.qualifier_values("ncRNA_class"))

    ref_titles = " | ".join(ref.title_joined for ref in record.references)

    field_map = {
        "description": record.description_joined,
        "keywords": record.keywords,
        "organism": record.organism,
        "reference_titles": ref_titles,
        "feature_notes": " | ".join(feature_notes),
        "products": " | ".join(products),
        "ncrna_class": " | ".join(ncrna_classes),
        "raw_record_text": record.raw_record_text,
    }

    for category, phrases in PHRASE_CATEGORIES.items():
        for field_name, text in field_map.items():
            for phrase in _search_phrases_in_text(text, phrases):
                hits.add(category, phrase, field_name)

    record.phrase_hits = hits
    return hits


def reverse_complement(seq: str) -> str:
    """Return reverse complement; map U↔A and T↔A symmetrically for DNA/RNA mix."""
    table = str.maketrans("ACGTURYSWKMBDHVN", "TGCAAYRSWMKVHDBN")
    return seq.upper().translate(table)[::-1]


def rna_equivalent(seq: str) -> str:
    """Temporary comparison form: T→U. Does not mutate the deposited sequence."""
    return seq.upper().replace("T", "U")


def detect_t7_promoter(record: EnaRecord) -> None:
    """Conservatively flag T7 promoter-like motifs as diagnostic clues only."""
    seq = record.sequence.sequence_deposited if record.sequence else ""
    if not seq:
        return
    seq_u = rna_equivalent(seq)
    match_seq = ""
    start = None
    position = ""

    idx = seq.find(T7_PROMOTER_DNA)
    if idx >= 0:
        match_seq = T7_PROMOTER_DNA
        start = idx + 1  # 1-based
        position = "5_prime" if idx == 0 else "internal"
    else:
        idx_u = seq_u.find(T7_PROMOTER_RNA)
        if idx_u >= 0:
            match_seq = T7_PROMOTER_RNA
            start = idx_u + 1
            position = "5_prime" if idx_u == 0 else "internal"
        else:
            rc = reverse_complement(seq)
            rc_u = rna_equivalent(rc)
            idx_rc = rc.find(T7_PROMOTER_DNA)
            if idx_rc < 0:
                idx_rc = rc_u.find(T7_PROMOTER_RNA)
                if idx_rc >= 0:
                    match_seq = T7_PROMOTER_RNA
            else:
                match_seq = T7_PROMOTER_DNA
            if idx_rc >= 0:
                # Map RC coordinate back approximately to original 1-based end region.
                start = len(seq) - idx_rc - len(match_seq) + 1
                position = "reverse_complement"

    if match_seq:
        record.contains_t7_promoter_like_motif = True
        record.t7_promoter_start = start
        record.t7_promoter_match = match_seq
        record.t7_promoter_position = position


def _organism_looks_synthetic(organism: str) -> bool:
    lower = organism.lower()
    return any(
        token in lower
        for token in (
            "synthetic construct",
            "artificial",
            "synthetic",
            "vector",
            "cloning",
        )
    )


def _organism_looks_natural(organism: str) -> bool:
    if not organism:
        return False
    if _organism_looks_synthetic(organism):
        return False
    return True


def _aptamer_related_features(record: EnaRecord) -> list[Feature]:
    related: list[Feature] = []
    for feat in record.features:
        blob = " ".join(
            [feat.feature_key, feat.location_raw]
            + [q.value for q in feat.qualifiers]
        ).lower()
        if "aptamer" in blob or feat.feature_key in {"ncRNA", "misc_RNA", "misc_feature"}:
            if "aptamer" in blob or any(
                "aptamer" in q.value.lower() for q in feat.qualifiers
            ):
                related.append(feat)
    return related


def assign_signals(record: EnaRecord) -> dict[str, bool]:
    """Assign non-exclusive provisional evidence signals (not final classes)."""
    hits = record.phrase_hits
    desc = record.description_joined.lower()
    mol = record.molecule_type.lower()
    seq_len = record.sequence.sequence_length_calculated if record.sequence else 0

    aptamer_feats = _aptamer_related_features(record)
    has_subregion = False
    has_complement_aptamer = False
    for feat in aptamer_feats:
        if feat.length is not None and seq_len > 0 and feat.length < seq_len:
            has_subregion = True
        if feat.is_complement:
            has_complement_aptamer = True
    # Also consider any non-source feature that does not span the full record.
    for feat in record.features:
        if feat.feature_key == "source":
            continue
        if feat.length is not None and seq_len > 0 and feat.length < seq_len:
            has_subregion = True
        if feat.is_complement:
            has_complement_aptamer = True

    # Annotation-level aptamer if not only raw/reference.
    aptamer_fields = set(hits.fields_by_category.get("aptamer", []))
    annotation_fields = aptamer_fields - {"raw_record_text", "reference_titles"}
    aptamer_in_annotation = bool(annotation_fields) or "aptamer" in desc
    aptamer_only_in_reference = (
        "reference_titles" in aptamer_fields
        and not annotation_fields
        and "aptamer" not in desc
    )

    signal_synthetic_selected = bool(
        (
            (
                _organism_looks_synthetic(record.organism)
                or hits.has("synthetic")
                or record.taxonomic_division == "SYN"
            )
            and (hits.has("selection") or "aptamer" in desc)
        )
        or (
            hits.has("selection")
            and ("synthetic" in desc or _organism_looks_synthetic(record.organism))
        )
    )

    signal_natural_or_genomic = bool(
        (
            _organism_looks_natural(record.organism)
            and not _organism_looks_synthetic(record.organism)
        )
        or hits.has("natural_genomic")
        or "tpa" in record.keywords.lower()
        or (
            any(feat.feature_key == "ncRNA" for feat in record.features)
            and _organism_looks_natural(record.organism)
        )
    )

    signal_riboswitch = hits.has("riboswitch")

    signal_engineered = hits.has("engineered_construct") or (
        has_subregion and seq_len >= 150 and aptamer_in_annotation
    )

    signal_dna_template = bool(
        record.contains_t7_promoter_like_motif
        or ("promoter" in hits.matched_by_category.get("sequence_role", [])
            or "T7 promoter" in hits.matched_by_category.get("synthetic", []))
        or ("rna" in desc and "dna" in mol and "aptamer" in desc)
        or ("template" in hits.matched_by_category.get("sequence_role", []) and "dna" in mol)
    )

    signal_feature_subregion = has_subregion
    signal_reverse_complement_feature = has_complement_aptamer or any(
        feat.is_complement for feat in record.features if feat.feature_key != "source"
    )
    signal_incidental = aptamer_only_in_reference

    # Uncertainty: conflicting signals or sparse evidence.
    signal_uncertain = False
    if signal_synthetic_selected and signal_natural_or_genomic:
        signal_uncertain = True
    if aptamer_in_annotation and not hits.has("selection") and not signal_riboswitch:
        signal_uncertain = True
    if signal_incidental:
        signal_uncertain = True
    if record.parse_status != "ok":
        signal_uncertain = True
    if not aptamer_in_annotation and not signal_incidental and "aptamer" in record.raw_record_text.lower():
        signal_uncertain = True

    signals = {
        "signal_synthetic_selected": signal_synthetic_selected,
        "signal_natural_or_genomic": signal_natural_or_genomic,
        "signal_riboswitch_related": signal_riboswitch,
        "signal_engineered_construct": signal_engineered,
        "signal_dna_template_or_promoter": signal_dna_template,
        "signal_feature_subregion": signal_feature_subregion,
        "signal_reverse_complement_feature": signal_reverse_complement_feature,
        "signal_incidental_aptamer_reference": signal_incidental,
        "signal_uncertain": signal_uncertain,
    }
    record.signals = signals
    return signals


def detect_discrepancies(record: EnaRecord) -> list[str]:
    """Flag metadata / sequence / feature / reference discrepancies."""
    warnings: list[str] = []
    desc = record.description_joined.lower()
    mol = record.molecule_type.lower()
    seq = record.sequence

    # Metadata conflicts
    if "rna" in desc and "dna" in mol and "cdna" not in mol:
        warnings.append("description_says_RNA_but_molecule_type_says_DNA")
    if "dna" in desc and "rna" in mol:
        warnings.append("description_says_DNA_but_molecule_type_says_RNA")
    if "synthetic" in desc and _organism_looks_natural(record.organism):
        warnings.append("description_says_synthetic_but_organism_is_natural")
    if "complete sequence" in desc:
        for feat in _aptamer_related_features(record):
            if (
                feat.length is not None
                and record.reported_length is not None
                and feat.length < record.reported_length
            ):
                warnings.append("complete_sequence_but_aptamer_feature_is_subregion")
                break

    if seq is not None:
        if record.reported_length is not None and seq.sequence_length_calculated != record.reported_length:
            warnings.append("reported_length_differs_from_calculated_length")
        if seq.sq_reported_length is not None and seq.sq_reported_length != seq.sequence_length_calculated:
            warnings.append("SQ_summary_length_differs_from_extracted_sequence")
        # SQ base-count mismatches
        for base, attr in (("A", "count_A"), ("C", "count_C"), ("G", "count_G"), ("T", "count_T"), ("U", "count_U")):
            if base in seq.sq_count_summary and seq.sq_count_summary[base] != getattr(seq, attr):
                warnings.append(f"SQ_count_mismatch_{base}")
                break

        # Sequence representation (T-in-RNA is normal for ENA — label accordingly)
        if "rna" in mol and seq.count_T > 0 and seq.count_U == 0:
            warnings.append("RNA_molecule_stored_with_T_ENA_convention")
        if "dna" in mol and seq.count_U > 0:
            warnings.append("DNA_molecule_contains_U")
        if seq.sequence_alphabet == "mixed_T_U":
            warnings.append("sequence_contains_both_T_and_U")
        if seq.sequence_alphabet == "ambiguous_nucleotide":
            warnings.append("sequence_contains_ambiguous_bases")
        if seq.sequence_alphabet == "invalid":
            warnings.append("sequence_contains_non_nucleotide_characters")
        if seq.sequence_alphabet == "missing":
            warnings.append("sequence_is_missing")

        # Feature coordinates
        for feat in record.features:
            if feat.end is not None and seq.sequence_length_calculated > 0:
                if feat.end > seq.sequence_length_calculated:
                    warnings.append("feature_coordinates_exceed_sequence_length")
                    break

    aptamer_feats = _aptamer_related_features(record)
    if any(feat.is_complement for feat in aptamer_feats):
        warnings.append("aptamer_feature_is_complement")
    if any(feat.is_join for feat in aptamer_feats):
        warnings.append("aptamer_feature_is_join")
    if len(aptamer_feats) > 1:
        warnings.append("several_possible_aptamer_related_features")
    seq_len = seq.sequence_length_calculated if seq else 0
    if any(
        feat.length is not None and seq_len > 0 and feat.length < seq_len
        for feat in aptamer_feats
    ):
        warnings.append("aptamer_feature_covers_only_part_of_record")

    # References
    all_doi = [d for ref in record.references for d in ref.doi_values]
    all_pmid = [p for ref in record.references for p in ref.pubmed_values]
    if not all_doi:
        warnings.append("missing_DOI")
    if not all_pmid:
        warnings.append("missing_PMID")
    if len(record.references) > 1:
        warnings.append("multiple_references_present")

    aptamer_fields = set(record.phrase_hits.fields_by_category.get("aptamer", []))
    if "reference_titles" in aptamer_fields and not (
        aptamer_fields - {"raw_record_text", "reference_titles"}
    ):
        warnings.append("reference_title_contains_aptamer_but_record_annotation_does_not")

    has_selection_title = any(
        any(term.lower() in ref.title_joined.lower() for term in PRIMARY_SELECTION_TITLE_TERMS)
        for ref in record.references
    )
    if "aptamer" in desc and not has_selection_title and not record.phrase_hits.has("selection"):
        warnings.append("no_apparent_primary_selection_reference")

    # Selection evidence
    if "aptamer" in desc and not record.phrase_hits.has("selection"):
        warnings.append("aptamer_description_but_no_explicit_SELEX_evidence")
    if _organism_looks_synthetic(record.organism) and not record.phrase_hits.has("selection"):
        warnings.append("synthetic_construct_but_no_selection_evidence")
    if _organism_looks_natural(record.organism) and record.phrase_hits.has("selection"):
        warnings.append("natural_organism_with_SELEX_evidence")
    if "genomic SELEX" in record.phrase_hits.terms("selection").lower() or (
        "genomic selex" in record.raw_record_text.lower()
    ):
        warnings.append("genomic_SELEX_versus_natural_genomic_motif_ambiguity")

    # Sequence-role ambiguity
    if record.contains_t7_promoter_like_motif:
        warnings.append("possible_promoter_present")
    if "primer" in record.phrase_hits.terms("sequence_role").lower():
        warnings.append("possible_primer_regions")
    if record.signals.get("signal_feature_subregion") and seq_len >= 120:
        warnings.append("possible_aptamer_embedded_in_larger_construct")
    if "complete sequence" in desc and "partial" in desc:
        warnings.append("possible_full_length_versus_core_sequence_uncertainty")
    elif "core aptamer" in record.phrase_hits.terms("sequence_role").lower():
        warnings.append("possible_full_length_versus_core_sequence_uncertainty")

    # Deduplicate while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for item in warnings:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    record.discrepancies = ordered
    return ordered


def enrich_record(record: EnaRecord) -> EnaRecord:
    """Run phrase, promoter, signal and discrepancy passes on one record."""
    collect_phrase_hits(record)
    detect_t7_promoter(record)
    assign_signals(record)
    detect_discrepancies(record)
    return record


# ---------------------------------------------------------------------------
# Duplicate analysis
# ---------------------------------------------------------------------------


def analyse_duplicates(records: list[EnaRecord]) -> pd.DataFrame:
    """Identify accession, sequence, RC, RNA-equivalent and publication duplicates."""
    rows: list[dict[str, Any]] = []

    # Exact accession duplicates
    by_acc: dict[str, list[EnaRecord]] = defaultdict(list)
    for rec in records:
        if rec.accession:
            by_acc[rec.accession].append(rec)
    for acc, group in by_acc.items():
        if len(group) > 1:
            rows.append(
                {
                    "duplicate_type": "exact_accession",
                    "group_key": acc,
                    "group_size": len(group),
                    "accessions": "|".join(r.accession for r in group),
                    "record_indices": "|".join(str(r.record_index) for r in group),
                    "notes": "same accession appearing more than once",
                }
            )

    # Exact sequence duplicates
    by_seq: dict[str, list[EnaRecord]] = defaultdict(list)
    for rec in records:
        seq = rec.sequence.sequence_deposited if rec.sequence else ""
        if seq:
            by_seq[seq].append(rec)
    for seq, group in by_seq.items():
        if len(group) > 1:
            rows.append(
                {
                    "duplicate_type": "exact_sequence",
                    "group_key": seq[:40] + ("..." if len(seq) > 40 else ""),
                    "group_size": len(group),
                    "accessions": "|".join(sorted({r.accession for r in group if r.accession})),
                    "record_indices": "|".join(str(r.record_index) for r in group),
                    "notes": f"identical deposited sequence length={len(seq)}",
                }
            )

    # RNA-equivalent duplicates (temporary T→U comparison for RNA-like records)
    by_rna: dict[str, list[EnaRecord]] = defaultdict(list)
    for rec in records:
        seq = rec.sequence.sequence_deposited if rec.sequence else ""
        mol = rec.molecule_type.lower()
        if not seq:
            continue
        if "rna" in mol or "rna" in rec.description_joined.lower():
            by_rna[rna_equivalent(seq)].append(rec)
    for seq_u, group in by_rna.items():
        # Only report groups that are not already exact-sequence identical.
        deposited = {r.sequence.sequence_deposited for r in group if r.sequence}
        if len(group) > 1 and len(deposited) > 1:
            rows.append(
                {
                    "duplicate_type": "rna_equivalent_sequence",
                    "group_key": seq_u[:40] + ("..." if len(seq_u) > 40 else ""),
                    "group_size": len(group),
                    "accessions": "|".join(sorted({r.accession for r in group if r.accession})),
                    "record_indices": "|".join(str(r.record_index) for r in group),
                    "notes": "identical after temporary T→U comparison; originals unchanged",
                }
            )

    # Reverse-complement duplicates
    seen_rc: set[str] = set()
    seq_to_recs = {seq: group for seq, group in by_seq.items()}
    for seq, group in by_seq.items():
        if seq in seen_rc:
            continue
        rc = reverse_complement(seq)
        if rc == seq:
            continue
        if rc in seq_to_recs:
            partner = seq_to_recs[rc]
            seen_rc.add(seq)
            seen_rc.add(rc)
            all_recs = group + partner
            rows.append(
                {
                    "duplicate_type": "reverse_complement",
                    "group_key": seq[:30] + "...|RC|" + rc[:30] + "...",
                    "group_size": len(all_recs),
                    "accessions": "|".join(sorted({r.accession for r in all_recs if r.accession})),
                    "record_indices": "|".join(str(r.record_index) for r in all_recs),
                    "notes": "exact reverse-complement pair/group",
                }
            )

    # Shared DOI / PMID / title
    by_doi: dict[str, list[EnaRecord]] = defaultdict(list)
    by_pmid: dict[str, list[EnaRecord]] = defaultdict(list)
    by_title: dict[str, list[EnaRecord]] = defaultdict(list)
    for rec in records:
        for ref in rec.references:
            for doi in ref.doi_values:
                by_doi[doi].append(rec)
            for pmid in ref.pubmed_values:
                by_pmid[pmid].append(rec)
            title = ref.title_joined.strip().strip(";").lower()
            if title and title not in {".", ";", ""}:
                by_title[title].append(rec)

    def _unique_accessions(group: list[EnaRecord]) -> list[str]:
        out: list[str] = []
        for rec in group:
            if rec.accession and rec.accession not in out:
                out.append(rec.accession)
        return out

    for doi, group in by_doi.items():
        accs = _unique_accessions(group)
        if len(accs) > 1:
            rows.append(
                {
                    "duplicate_type": "shared_doi",
                    "group_key": doi,
                    "group_size": len(accs),
                    "accessions": "|".join(accs),
                    "record_indices": "|".join(str(r.record_index) for r in group),
                    "notes": "records sharing DOI",
                }
            )
    for pmid, group in by_pmid.items():
        accs = _unique_accessions(group)
        if len(accs) > 1:
            rows.append(
                {
                    "duplicate_type": "shared_pmid",
                    "group_key": pmid,
                    "group_size": len(accs),
                    "accessions": "|".join(accs),
                    "record_indices": "|".join(str(r.record_index) for r in group),
                    "notes": "records sharing PMID",
                }
            )
    for title, group in by_title.items():
        accs = _unique_accessions(group)
        if len(accs) > 1:
            rows.append(
                {
                    "duplicate_type": "shared_reference_title",
                    "group_key": title[:80],
                    "group_size": len(accs),
                    "accessions": "|".join(accs[:50]) + ("|..." if len(accs) > 50 else ""),
                    "record_indices": "",
                    "notes": "records sharing reference title",
                }
            )

    # Adjacent accession heuristic (same paper + numeric neighbours)
    # Keep this as a soft relatedness note, not a deletion rule.
    prefix_groups: dict[str, list[EnaRecord]] = defaultdict(list)
    for rec in records:
        match = re.match(r"^([A-Za-z]+)(\d+)$", rec.accession)
        if match:
            prefix_groups[match.group(1)].append(rec)
    for prefix, group in prefix_groups.items():
        if len(group) < 3:
            continue
        # Only note large same-prefix clusters that also share a DOI.
        dois = set()
        for rec in group:
            for ref in rec.references:
                dois.update(ref.doi_values)
        if dois:
            rows.append(
                {
                    "duplicate_type": "related_accession_prefix",
                    "group_key": prefix,
                    "group_size": len(group),
                    "accessions": "|".join(sorted({r.accession for r in group})[:40]),
                    "record_indices": "",
                    "notes": "same accession prefix and at least one shared publication context",
                }
            )

    if not rows:
        rows.append(
            {
                "duplicate_type": "none_detected",
                "group_key": "",
                "group_size": 0,
                "accessions": "",
                "record_indices": "",
                "notes": "no duplicate groups identified",
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Output builders
# ---------------------------------------------------------------------------


def _pipe(values: Iterable[Any]) -> str:
    return "|".join(str(v) for v in values if v is not None and str(v) != "")


def _feature_notes(record: EnaRecord) -> str:
    notes: list[str] = []
    for feat in record.features:
        for note in feat.qualifier_values("note"):
            notes.append(note)
    return " || ".join(notes)


def _products(record: EnaRecord) -> str:
    vals: list[str] = []
    for feat in record.features:
        vals.extend(feat.qualifier_values("product"))
    return _pipe(vals)


def _ncrna_classes(record: EnaRecord) -> str:
    vals: list[str] = []
    for feat in record.features:
        vals.extend(feat.qualifier_values("ncRNA_class"))
    return _pipe(vals)


def build_inventory_row(record: EnaRecord) -> dict[str, Any]:
    seq = record.sequence
    hits = record.phrase_hits
    return {
        "record_index": record.record_index,
        "accession": record.accession,
        "sequence_version": record.sequence_version,
        "description": record.description_joined,
        "keywords": record.keywords,
        "organism": record.organism,
        "taxonomy": record.taxonomy,
        "molecule_type": record.molecule_type,
        "topology": record.topology,
        "data_class": record.data_class,
        "taxonomic_division": record.taxonomic_division,
        "reported_length": record.reported_length,
        "sequence_length_calculated": seq.sequence_length_calculated if seq else None,
        "length_matches": (
            record.reported_length == seq.sequence_length_calculated
            if seq and record.reported_length is not None
            else None
        ),
        "sequence_alphabet": seq.sequence_alphabet if seq else "missing",
        "count_A": seq.count_A if seq else None,
        "count_C": seq.count_C if seq else None,
        "count_G": seq.count_G if seq else None,
        "count_T": seq.count_T if seq else None,
        "count_U": seq.count_U if seq else None,
        "count_N": seq.count_N if seq else None,
        "count_other": seq.count_other if seq else None,
        "gc_percent_calculated": seq.gc_percent_calculated if seq else None,
        "feature_keys": _pipe(f.feature_key for f in record.features),
        "feature_locations": _pipe(f.location_raw for f in record.features),
        "feature_notes": _feature_notes(record),
        "products": _products(record),
        "ncrna_classes": _ncrna_classes(record),
        "has_complement_feature": any(f.is_complement for f in record.features),
        "has_join_feature": any(f.is_join for f in record.features),
        "has_subregion_feature": record.signals.get("signal_feature_subregion", False),
        "doi_values": _pipe(d for ref in record.references for d in ref.doi_values),
        "pubmed_values": _pipe(p for ref in record.references for p in ref.pubmed_values),
        "reference_titles": " || ".join(ref.title_joined for ref in record.references if ref.title_joined),
        "mentions_aptamer": hits.has("aptamer"),
        "mentions_selex": any("selex" in t.lower() for t in hits.matched_by_category.get("selection", [])),
        "mentions_in_vitro_selection": any(
            "in vitro" in t.lower() or "in-vitro" in t.lower()
            for t in hits.matched_by_category.get("selection", [])
        ),
        "mentions_synthetic_construct": hits.has("synthetic"),
        "mentions_genomic": hits.has("natural_genomic"),
        "mentions_riboswitch": hits.has("riboswitch"),
        "mentions_aptazyme": any(
            "aptazyme" in t.lower() for t in hits.matched_by_category.get("engineered_construct", [])
        ),
        "mentions_molecular_switch": any(
            "molecular switch" in t.lower()
            for t in hits.matched_by_category.get("engineered_construct", [])
        ),
        "mentions_promoter": any(
            "promoter" in t.lower() for t in hits.matched_by_category.get("sequence_role", [])
        )
        or any("promoter" in t.lower() for t in hits.matched_by_category.get("synthetic", [])),
        "mentions_primer": any(
            "primer" in t.lower() for t in hits.matched_by_category.get("sequence_role", [])
        ),
        "mentions_complete_sequence": "complete sequence"
        in hits.matched_by_category.get("sequence_role", []),
        "mentions_partial_sequence": "partial sequence"
        in hits.matched_by_category.get("sequence_role", []),
        "mentions_binding_target": hits.has("target"),
        "contains_t7_promoter_like_motif": record.contains_t7_promoter_like_motif,
        "t7_promoter_start": record.t7_promoter_start,
        "t7_promoter_match": record.t7_promoter_match,
        "t7_promoter_position": record.t7_promoter_position,
        "signal_synthetic_selected": record.signals.get("signal_synthetic_selected", False),
        "signal_natural_or_genomic": record.signals.get("signal_natural_or_genomic", False),
        "signal_riboswitch_related": record.signals.get("signal_riboswitch_related", False),
        "signal_engineered_construct": record.signals.get("signal_engineered_construct", False),
        "signal_dna_template_or_promoter": record.signals.get("signal_dna_template_or_promoter", False),
        "signal_feature_subregion": record.signals.get("signal_feature_subregion", False),
        "signal_reverse_complement_feature": record.signals.get("signal_reverse_complement_feature", False),
        "signal_incidental_aptamer_reference": record.signals.get(
            "signal_incidental_aptamer_reference", False
        ),
        "signal_uncertain": record.signals.get("signal_uncertain", False),
        "matched_terms": hits.all_terms(),
        "matched_selection_terms": hits.terms("selection"),
        "matched_selection_fields": hits.fields("selection"),
        "matched_construct_terms": hits.terms("engineered_construct"),
        "matched_construct_fields": hits.fields("engineered_construct"),
        "discrepancies": _pipe(record.discrepancies),
        "parse_status": record.parse_status,
        "parse_warnings": _pipe(record.parse_warnings),
        "created_date": record.created_date,
        "updated_date": record.updated_date,
        "raw_record_character_count": record.raw_record_character_count,
        "raw_record_line_count": record.raw_record_line_count,
        "record_id_line": record.record_id_line,
    }


def build_sequence_diagnostics_row(record: EnaRecord) -> dict[str, Any]:
    seq = record.sequence
    assert seq is not None
    return {
        "accession": record.accession,
        "record_index": record.record_index,
        "molecule_type": record.molecule_type,
        "reported_length": record.reported_length,
        "sequence_deposited": seq.sequence_deposited,
        "sequence_length_calculated": seq.sequence_length_calculated,
        "sequence_alphabet": seq.sequence_alphabet,
        "count_A": seq.count_A,
        "count_C": seq.count_C,
        "count_G": seq.count_G,
        "count_T": seq.count_T,
        "count_U": seq.count_U,
        "count_N": seq.count_N,
        "count_other": seq.count_other,
        "gc_percent_calculated": seq.gc_percent_calculated,
        "sq_summary_raw": seq.sq_summary_raw,
        "sq_reported_length": seq.sq_reported_length,
        "sq_count_summary": ";".join(f"{k}:{v}" for k, v in seq.sq_count_summary.items()),
        "length_matches_id": (
            record.reported_length == seq.sequence_length_calculated
            if record.reported_length is not None
            else None
        ),
        "contains_t7_promoter_like_motif": record.contains_t7_promoter_like_motif,
        "t7_promoter_start": record.t7_promoter_start,
        "t7_promoter_match": record.t7_promoter_match,
        "t7_promoter_position": record.t7_promoter_position,
        "discrepancies": _pipe(record.discrepancies),
    }


def build_signals_row(record: EnaRecord) -> dict[str, Any]:
    row = {
        "accession": record.accession,
        "record_index": record.record_index,
        "description": record.description_joined,
        "organism": record.organism,
        "molecule_type": record.molecule_type,
    }
    row.update(record.signals)
    row["matched_terms"] = record.phrase_hits.all_terms()
    row["discrepancies"] = _pipe(record.discrepancies)
    return row


def build_reference_rows(record: EnaRecord) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not record.references:
        rows.append(
            {
                "accession": record.accession,
                "reference_number": None,
                "reference_title": "",
                "authors": "",
                "journal_or_submission": "",
                "doi": "",
                "pmid": "",
                "reference_mentions_aptamer": False,
                "reference_mentions_selection": False,
                "reference_mentions_selex": False,
                "likely_primary_selection_reference": False,
                "reference_signal_notes": "no_references_parsed",
            }
        )
        return rows

    for ref in record.references:
        title = ref.title_joined
        title_l = title.lower()
        mentions_aptamer = "aptamer" in title_l
        mentions_selection = any(
            term.lower() in title_l for term in ("selection", "selected", "evolved", "isolation")
        )
        mentions_selex = "selex" in title_l
        likely_primary = any(term.lower() in title_l for term in PRIMARY_SELECTION_TITLE_TERMS)
        notes: list[str] = []
        if likely_primary:
            notes.append("provisional_primary_selection_title_signal")
        if mentions_aptamer and not mentions_selection and not mentions_selex:
            notes.append("aptamer_in_title_without_selection_terms")
        rows.append(
            {
                "accession": record.accession,
                "reference_number": ref.reference_number,
                "reference_title": title,
                "authors": ref.authors_joined,
                "journal_or_submission": ref.location_joined,
                "doi": _pipe(ref.doi_values),
                "pmid": _pipe(ref.pubmed_values),
                "reference_mentions_aptamer": mentions_aptamer,
                "reference_mentions_selection": mentions_selection,
                "reference_mentions_selex": mentions_selex,
                "likely_primary_selection_reference": likely_primary,
                "reference_signal_notes": _pipe(notes),
            }
        )
    return rows


def build_feature_long_rows(record: EnaRecord) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seq_len = record.sequence.sequence_length_calculated if record.sequence else None
    for feat in record.features:
        is_full = (
            feat.start == 1
            and seq_len is not None
            and feat.end == seq_len
            and not feat.is_join
        )
        if not feat.qualifiers:
            rows.append(
                {
                    "accession": record.accession,
                    "feature_index": feat.feature_index,
                    "feature_key": feat.feature_key,
                    "feature_location_raw": feat.location_raw,
                    "feature_start": feat.start,
                    "feature_end": feat.end,
                    "feature_strand": feat.strand,
                    "feature_is_complement": feat.is_complement,
                    "feature_is_join": feat.is_join,
                    "feature_length": feat.length,
                    "feature_is_full_record": is_full,
                    "qualifier_name": "",
                    "qualifier_value": "",
                }
            )
        else:
            for qual in feat.qualifiers:
                rows.append(
                    {
                        "accession": record.accession,
                        "feature_index": feat.feature_index,
                        "feature_key": feat.feature_key,
                        "feature_location_raw": feat.location_raw,
                        "feature_start": feat.start,
                        "feature_end": feat.end,
                        "feature_strand": feat.strand,
                        "feature_is_complement": feat.is_complement,
                        "feature_is_join": feat.is_join,
                        "feature_length": feat.length,
                        "feature_is_full_record": is_full,
                        "qualifier_name": qual.name,
                        "qualifier_value": qual.value,
                    }
                )
    return rows


def build_feature_summary(feature_long: pd.DataFrame) -> pd.DataFrame:
    """Aggregate feature-key / qualifier / location-type counts."""
    rows: list[dict[str, Any]] = []
    if feature_long.empty:
        return pd.DataFrame(
            columns=["summary_type", "item", "count", "notes"]
        )

    feat_unique = feature_long.drop_duplicates(subset=["accession", "feature_index"])

    for key, count in feat_unique["feature_key"].value_counts().items():
        rows.append(
            {"summary_type": "feature_key", "item": key, "count": int(count), "notes": ""}
        )
    for name, count in feature_long["qualifier_name"].value_counts().items():
        if name == "":
            continue
        rows.append(
            {
                "summary_type": "qualifier_name",
                "item": name,
                "count": int(count),
                "notes": "",
            }
        )

    full = int(feat_unique["feature_is_full_record"].fillna(False).sum())
    sub = int((~feat_unique["feature_is_full_record"].fillna(False)).sum())
    rows.append(
        {
            "summary_type": "location_span",
            "item": "full_record_features",
            "count": full,
            "notes": "feature start..end equals full deposited length",
        }
    )
    rows.append(
        {
            "summary_type": "location_span",
            "item": "subregion_or_other_features",
            "count": sub,
            "notes": "includes source-length mismatches and complex locations",
        }
    )

    comp = int(feat_unique["feature_is_complement"].fillna(False).sum())
    fwd = int((~feat_unique["feature_is_complement"].fillna(False)).sum())
    join = int(feat_unique["feature_is_join"].fillna(False).sum())
    rows.append(
        {"summary_type": "strand", "item": "forward_features", "count": fwd, "notes": ""}
    )
    rows.append(
        {
            "summary_type": "strand",
            "item": "complement_features",
            "count": comp,
            "notes": "",
        }
    )
    rows.append(
        {
            "summary_type": "location_type",
            "item": "join_features",
            "count": join,
            "notes": "",
        }
    )
    return pd.DataFrame(rows)


def build_keyword_summary(records: list[EnaRecord]) -> pd.DataFrame:
    """Inventory keyword tokens and selected phrase-category hit counts."""
    rows: list[dict[str, Any]] = []
    kw_counter: Counter[str] = Counter()
    for rec in records:
        raw = rec.keywords.strip()
        if not raw or raw == ".":
            kw_counter["(empty_or_dot)"] += 1
            continue
        for token in re.split(r"\s*;\s*", raw):
            token = token.strip().rstrip(".")
            if token:
                kw_counter[token] += 1
    for item, count in kw_counter.most_common():
        rows.append(
            {
                "summary_type": "keyword_token",
                "item": item,
                "count": count,
                "notes": "",
            }
        )

    # Phrase-category record counts
    for category in PHRASE_CATEGORIES:
        n = sum(1 for rec in records if rec.phrase_hits.has(category))
        rows.append(
            {
                "summary_type": "phrase_category_records",
                "item": category,
                "count": n,
                "notes": "records with ≥1 match in any searched field",
            }
        )

    # Individual phrase counts across raw text (record-level)
    for category, phrases in PHRASE_CATEGORIES.items():
        for phrase in phrases:
            n = sum(
                1
                for rec in records
                if phrase in _search_phrases_in_text(rec.raw_record_text, [phrase])
            )
            if n:
                rows.append(
                    {
                        "summary_type": f"phrase:{category}",
                        "item": phrase,
                        "count": n,
                        "notes": "case-insensitive raw-record match",
                    }
                )
    return pd.DataFrame(rows)


def build_review_examples(
    records: list[EnaRecord],
    duplicates: pd.DataFrame,
    examples_per_category: int = 5,
) -> pd.DataFrame:
    """Select representative examples for major signal / discrepancy categories."""

    def excerpt(rec: EnaRecord) -> str:
        text = rec.raw_record_text
        if len(text) > RAW_EXCERPT_MAX_CHARS:
            return text[:RAW_EXCERPT_MAX_CHARS] + "\n...[truncated]..."
        return text

    def base_row(category: str, rec: EnaRecord) -> dict[str, Any]:
        return {
            "review_category": category,
            "accession": rec.accession,
            "description": rec.description_joined,
            "organism": rec.organism,
            "molecule_type": rec.molecule_type,
            "reported_length": rec.reported_length,
            "sequence_length_calculated": (
                rec.sequence.sequence_length_calculated if rec.sequence else None
            ),
            "feature_summary": _pipe(
                f"{f.feature_key}:{f.location_raw}" for f in rec.features
            ),
            "feature_notes": _feature_notes(rec)[:500],
            "reference_titles": " || ".join(
                r.title_joined for r in rec.references if r.title_joined
            )[:500],
            "matched_terms": rec.phrase_hits.all_terms()[:500],
            "provisional_signals": _pipe(
                k for k, v in rec.signals.items() if v
            ),
            "discrepancies": _pipe(rec.discrepancies),
            "raw_record_excerpt": excerpt(rec),
        }

    selectors: dict[str, Any] = {
        "strong_synthetic_selection_evidence": lambda r: r.signals.get(
            "signal_synthetic_selected", False
        )
        and r.phrase_hits.has("selection"),
        "natural_or_genomic_records": lambda r: r.signals.get(
            "signal_natural_or_genomic", False
        ),
        "riboswitch_related": lambda r: r.signals.get("signal_riboswitch_related", False),
        "engineered_constructs": lambda r: r.signals.get(
            "signal_engineered_construct", False
        ),
        "possible_dna_templates": lambda r: r.signals.get(
            "signal_dna_template_or_promoter", False
        ),
        "complement_features": lambda r: r.signals.get(
            "signal_reverse_complement_feature", False
        ),
        "subregion_features": lambda r: r.signals.get("signal_feature_subregion", False),
        "RNA_records_with_T": lambda r: (
            "rna" in r.molecule_type.lower()
            and r.sequence is not None
            and r.sequence.count_T > 0
            and r.sequence.count_U == 0
        ),
        "mixed_T_U_sequences": lambda r: (
            r.sequence is not None and r.sequence.sequence_alphabet == "mixed_T_U"
        ),
        "missing_sequences": lambda r: (
            r.sequence is not None and r.sequence.sequence_alphabet == "missing"
        ),
        "length_mismatches": lambda r: (
            r.reported_length is not None
            and r.sequence is not None
            and r.reported_length != r.sequence.sequence_length_calculated
        ),
        "reference_only_aptamer_mentions": lambda r: r.signals.get(
            "signal_incidental_aptamer_reference", False
        ),
        "records_with_no_selection_evidence": lambda r: (
            r.phrase_hits.has("aptamer") and not r.phrase_hits.has("selection")
        ),
        "uncertain_records": lambda r: r.signals.get("signal_uncertain", False),
        "malformed_records": lambda r: r.parse_status != "ok",
    }

    rows: list[dict[str, Any]] = []
    used: set[tuple[str, str]] = set()
    for category, predicate in selectors.items():
        chosen = 0
        for rec in records:
            if chosen >= examples_per_category:
                break
            if not predicate(rec):
                continue
            key = (category, rec.accession or str(rec.record_index))
            if key in used:
                continue
            used.add(key)
            rows.append(base_row(category, rec))
            chosen += 1

    # Duplicate sequences from duplicate table
    if not duplicates.empty:
        exact = duplicates[duplicates["duplicate_type"] == "exact_sequence"]
        chosen = 0
        acc_to_rec = {r.accession: r for r in records if r.accession}
        for _, dup_row in exact.iterrows():
            if chosen >= examples_per_category:
                break
            for acc in str(dup_row["accessions"]).split("|"):
                if chosen >= examples_per_category:
                    break
                rec = acc_to_rec.get(acc)
                if rec is None:
                    continue
                key = ("duplicate_sequences", acc)
                if key in used:
                    continue
                used.add(key)
                rows.append(base_row("duplicate_sequences", rec))
                chosen += 1

    return pd.DataFrame(rows)


def _counter_md(counter: Counter[Any], limit: int = 20) -> str:
    if not counter:
        return "_None_\n"
    lines = ["| value | count |", "|---|---:|"]
    for value, count in counter.most_common(limit):
        lines.append(f"| {value} | {count} |")
    return "\n".join(lines) + "\n"


def write_inspection_report(
    path: Path,
    input_path: Path,
    records: list[EnaRecord],
    duplicates: pd.DataFrame,
    feature_summary: pd.DataFrame,
) -> None:
    """Write a Markdown inspection report summarising observed distributions."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ok = [r for r in records if r.parse_status == "ok"]
    malformed = [r for r in records if r.parse_status != "ok"]
    accessions = [r.accession for r in records if r.accession]
    unique_acc = sorted(set(accessions))

    mol_c = Counter(r.molecule_type or "(missing)" for r in records)
    org_c = Counter(r.organism or "(missing)" for r in records)
    div_c = Counter(r.taxonomic_division or "(missing)" for r in records)
    alph_c = Counter(
        (r.sequence.sequence_alphabet if r.sequence else "missing") for r in records
    )

    n_aptamer = sum(1 for r in records if r.phrase_hits.has("aptamer"))
    n_selex = sum(
        1
        for r in records
        if any("selex" in t.lower() for t in r.phrase_hits.matched_by_category.get("selection", []))
    )
    n_invitro = sum(
        1
        for r in records
        if any(
            "in vitro" in t.lower() or "in-vitro" in t.lower()
            for t in r.phrase_hits.matched_by_category.get("selection", [])
        )
    )
    signal_counts = Counter()
    for r in records:
        for key, val in r.signals.items():
            if val:
                signal_counts[key] += 1

    rna_with_t = sum(
        1
        for r in records
        if "rna" in r.molecule_type.lower()
        and r.sequence
        and r.sequence.count_T > 0
        and r.sequence.count_U == 0
    )
    dna_with_u = sum(
        1
        for r in records
        if "dna" in r.molecule_type.lower() and r.sequence and r.sequence.count_U > 0
    )
    mixed = sum(
        1
        for r in records
        if r.sequence and r.sequence.sequence_alphabet == "mixed_T_U"
    )
    missing_seq = sum(
        1 for r in records if r.sequence and r.sequence.sequence_alphabet == "missing"
    )
    length_mm = sum(
        1
        for r in records
        if r.reported_length is not None
        and r.sequence
        and r.reported_length != r.sequence.sequence_length_calculated
    )
    t7 = sum(1 for r in records if r.contains_t7_promoter_like_motif)
    complement = sum(
        1 for r in records if r.signals.get("signal_reverse_complement_feature")
    )
    subregion = sum(1 for r in records if r.signals.get("signal_feature_subregion"))

    has_doi = sum(
        1 for r in records if any(ref.doi_values for ref in r.references)
    )
    has_pmid = sum(
        1 for r in records if any(ref.pubmed_values for ref in r.references)
    )

    # Pattern combinations
    patterns = Counter()
    for r in records:
        if (
            _organism_looks_synthetic(r.organism)
            and r.phrase_hits.has("selection")
            and not r.signals.get("signal_feature_subregion")
        ):
            patterns["synthetic_construct + SELEX/selection + full-length-like"] += 1
        if _organism_looks_natural(r.organism) and any(
            f.feature_key == "ncRNA" for f in r.features
        ):
            patterns["natural_organism + ncRNA feature"] += 1
        if "rna" in r.description_joined.lower() and r.sequence and r.sequence.sequence_alphabet == "DNA_alphabet":
            patterns["RNA description + DNA_alphabet deposit"] += 1
        if r.signals.get("signal_incidental_aptamer_reference"):
            patterns["aptamer reference title only"] += 1
        if r.signals.get("signal_feature_subregion") and r.phrase_hits.has("aptamer"):
            patterns["aptamer-related feature covering subregion"] += 1

    dup_acc = (
        int(duplicates.loc[duplicates["duplicate_type"] == "exact_accession", "group_size"].sum())
        if not duplicates.empty
        else 0
    )
    dup_seq_groups = (
        int((duplicates["duplicate_type"] == "exact_sequence").sum())
        if not duplicates.empty
        else 0
    )
    dup_rc = (
        int((duplicates["duplicate_type"] == "reverse_complement").sum())
        if not duplicates.empty
        else 0
    )
    dup_doi = (
        int((duplicates["duplicate_type"] == "shared_doi").sum())
        if not duplicates.empty
        else 0
    )
    dup_pmid = (
        int((duplicates["duplicate_type"] == "shared_pmid").sum())
        if not duplicates.empty
        else 0
    )

    feat_keys = ""
    if not feature_summary.empty:
        fk = feature_summary[feature_summary["summary_type"] == "feature_key"]
        feat_keys = _counter_md(Counter(dict(zip(fk["item"], fk["count"]))))
    else:
        feat_keys = "_No features parsed_\n"

    lengths = [
        r.sequence.sequence_length_calculated
        for r in records
        if r.sequence and r.sequence.sequence_length_calculated
    ]
    length_note = (
        f"n={len(lengths)}; min={min(lengths)}; median={sorted(lengths)[len(lengths)//2]}; "
        f"max={max(lengths)}"
        if lengths
        else "no lengths available"
    )

    report = f"""# ENA aptamer-search inspection report

## File summary

| field | value |
|---|---|
| input filename | `{input_path.name}` |
| input path | `{input_path}` |
| file size (bytes) | {input_path.stat().st_size if input_path.exists() else "n/a"} |
| inspection date | {now} |
| total record blocks | {len(records)} |
| successfully parsed (`parse_status=ok`) | {len(ok)} |
| malformed / incomplete blocks | {len(malformed)} |
| unique accessions | {len(unique_acc)} |
| Biopython available | {HAS_BIOPYTHON} |

**Important:** this report inventories evidence and provisional signals only. It does
**not** define final corpus-inclusion rules.

## Core distributions

### Molecule types

{_counter_md(mol_c)}

### Organisms (top 20)

{_counter_md(org_c, 20)}

### Taxonomic divisions

{_counter_md(div_c)}

### Sequence alphabets

{_counter_md(alph_c)}

### Record lengths

{length_note}

### Feature keys

{feat_keys}

### Reference identifier availability

| metric | count |
|---|---:|
| records with ≥1 DOI | {has_doi} |
| records with ≥1 PMID | {has_pmid} |
| records missing DOI | {len(records) - has_doi} |
| records missing PMID | {len(records) - has_pmid} |

## Aptamer-related evidence

| evidence / signal | count |
|---|---:|
| mentions aptamer (any searched field) | {n_aptamer} |
| explicit SELEX phrase | {n_selex} |
| in vitro selected/evolved/selection phrase | {n_invitro} |
| signal_synthetic_selected | {signal_counts.get("signal_synthetic_selected", 0)} |
| signal_natural_or_genomic | {signal_counts.get("signal_natural_or_genomic", 0)} |
| signal_riboswitch_related | {signal_counts.get("signal_riboswitch_related", 0)} |
| signal_engineered_construct | {signal_counts.get("signal_engineered_construct", 0)} |
| signal_dna_template_or_promoter | {signal_counts.get("signal_dna_template_or_promoter", 0)} |
| signal_incidental_aptamer_reference | {signal_counts.get("signal_incidental_aptamer_reference", 0)} |
| signal_uncertain | {signal_counts.get("signal_uncertain", 0)} |
| signal_feature_subregion | {signal_counts.get("signal_feature_subregion", 0)} |
| signal_reverse_complement_feature | {signal_counts.get("signal_reverse_complement_feature", 0)} |

## Sequence diagnostics

| diagnostic | count |
|---|---:|
| RNA molecule_type stored with T (no U) | {rna_with_t} |
| DNA molecule_type contains U | {dna_with_u} |
| mixed T/U sequences | {mixed} |
| missing sequences | {missing_seq} |
| ID length ≠ calculated length | {length_mm} |
| T7 promoter-like motif | {t7} |
| complement (non-trivial) feature signal | {complement} |
| subregion feature signal | {subregion} |

RNA records deposited with T are consistent with common ENA practice and must not
be auto-corrected in this stage.

## Duplicate analysis

| duplicate class | groups / note |
|---|---:|
| exact accession duplicate memberships (sum group sizes) | {dup_acc} |
| exact sequence duplicate groups | {dup_seq_groups} |
| reverse-complement groups | {dup_rc} |
| shared DOI groups | {dup_doi} |
| shared PMID groups | {dup_pmid} |

See `ena_duplicate_summary.csv` for accession lists. Duplicates are **not** deleted.

## Important observed record patterns

{_counter_md(patterns, 30)}

## Recommendations for the next stage

Based only on observed inventory needs (not final inclusion rules):

1. **Candidate-record fields likely needed:** accession, description, organism,
   molecule_type, deposited sequence (unaltered), alphabet flags, feature keys /
   locations / notes, DOI/PMID, selection-evidence phrases, provisional signals,
   discrepancy list, and a manual-review flag.
2. **Classifications that appear necessary (non-exclusive):** synthetic selected
   aptamer; natural/genomic motif; riboswitch aptamer domain; engineered construct /
   aptazyme; DNA template / promoter-bearing deposit; incidental reference-only;
   uncertain / needs review.
3. **Edge cases needing manual review:** genomic SELEX vs natural genomic motifs;
   RNA description with DNA molecule_type; complement-strand ncRNA aptamer features;
   aptamer subregions inside longer constructs; reference-title-only aptamer hits;
   mixed T/U alphabets; missing identifiers.
4. **Unsafe to automate yet:** converting all T→U; trimming promoters/primers;
   assuming the first reference is the selection paper; deleting duplicates;
   treating SELEX phrase absence as exclusion; treating organism=`synthetic construct`
   alone as proof of experimental selection.
5. **Unresolved questions:** which feature key reliably marks the aptamer core;
   how often DNA records are intentional templates versus mis-labelled RNA; how to
   treat TPA inferential genomic aptamers relative to experimentally selected
   sequences; whether reverse-complement deposits are independent biological
   entities or strand artefacts.

Do **not** treat this inspection output as a filtered aptamer corpus.
"""
    path.write_text(report, encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def resolve_default_input() -> Path | None:
    for candidate in DEFAULT_INPUT_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def load_and_parse_records(input_path: Path) -> list[EnaRecord]:
    """Read the flat file, split on ``//``, parse and enrich every block."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input ENA flat file does not exist: {input_path}")

    logger.info("Reading input: %s", input_path)
    text = input_path.read_text(encoding="utf-8", errors="replace")
    blocks = split_embl_records(text)
    if not blocks:
        raise ValueError(f"No ENA record blocks found in {input_path} (no // terminators?)")

    logger.info("Split into %d record blocks", len(blocks))
    records: list[EnaRecord] = []
    for idx, block in enumerate(blocks):
        rec = parse_raw_record(idx, block)
        enrich_record(rec)
        records.append(rec)
        if (idx + 1) % 1000 == 0:
            logger.info("Parsed %d / %d records", idx + 1, len(blocks))

    # Optional Biopython cross-check (does not replace raw parsing).
    if HAS_BIOPYTHON:
        try:
            bio_ids: set[str] = set()
            with input_path.open(encoding="utf-8", errors="replace") as handle:
                for seq_record in SeqIO.parse(handle, "embl"):
                    bio_ids.add(seq_record.id)
            bio_primary = {bio_id.split(".", 1)[0] for bio_id in bio_ids}
            matched = 0
            for rec in records:
                if rec.accession and rec.accession in bio_primary:
                    rec.biopython_parse_ok = True
                    matched += 1
                elif rec.parse_status == "ok":
                    rec.biopython_parse_ok = False
            logger.info(
                "Biopython cross-check: %d accessions matched of %d Bio records",
                matched,
                len(bio_ids),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Biopython cross-check failed: %s", exc)

    ok_count = sum(1 for r in records if r.parse_status == "ok")
    if ok_count == 0:
        raise ValueError(
            f"No records could be parsed successfully from {input_path} "
            f"({len(records)} blocks examined)."
        )
    return records


def write_outputs(
    records: list[EnaRecord],
    input_path: Path,
    output_dir: Path,
    examples_per_category: int,
    overwrite: bool,
) -> dict[str, Path]:
    """Write all inspection CSV/Markdown/log artefacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: output_dir / name for name in EXPECTED_OUTPUT_FILES}

    if not overwrite:
        existing = [p for p in paths.values() if p.exists() and p.name != "ena_inspection_log.txt"]
        if existing:
            raise FileExistsError(
                "Output files already exist (use --overwrite): "
                + ", ".join(p.name for p in existing)
            )

    # Ensure the log artefact exists even when called outside main().
    log_path = paths["ena_inspection_log.txt"]
    if not log_path.exists():
        log_path.write_text(
            f"Inspection outputs written for input={input_path}\n",
            encoding="utf-8",
        )

    inventory = pd.DataFrame([build_inventory_row(r) for r in records])
    signals = pd.DataFrame([build_signals_row(r) for r in records])
    seq_diag = pd.DataFrame(
        [build_sequence_diagnostics_row(r) for r in records if r.sequence is not None]
    )

    feature_long_rows: list[dict[str, Any]] = []
    for rec in records:
        feature_long_rows.extend(build_feature_long_rows(rec))
    feature_long = pd.DataFrame(feature_long_rows)
    feature_summary = build_feature_summary(feature_long)

    # Persist a compact feature summary; also write long form beside it for review.
    feature_long_path = output_dir / "ena_feature_table_long.csv"
    feature_long.to_csv(feature_long_path, index=False)

    ref_rows: list[dict[str, Any]] = []
    for rec in records:
        ref_rows.extend(build_reference_rows(rec))
    references = pd.DataFrame(ref_rows)

    keywords = build_keyword_summary(records)
    duplicates = analyse_duplicates(records)
    examples = build_review_examples(records, duplicates, examples_per_category)

    inventory.to_csv(paths["ena_record_inventory.csv"], index=False)
    keywords.to_csv(paths["ena_keyword_summary.csv"], index=False)
    signals.to_csv(paths["ena_record_class_signals.csv"], index=False)
    feature_summary.to_csv(paths["ena_feature_summary.csv"], index=False)
    seq_diag.to_csv(paths["ena_sequence_diagnostics.csv"], index=False)
    references.to_csv(paths["ena_reference_summary.csv"], index=False)
    duplicates.to_csv(paths["ena_duplicate_summary.csv"], index=False)
    examples.to_csv(paths["ena_review_examples.csv"], index=False)

    write_inspection_report(
        paths["ena_inspection_report.md"],
        input_path,
        records,
        duplicates,
        feature_summary,
    )

    # Optional per-accession raw text (only when record count is modest).
    # For large files, store a lightweight offset index instead.
    records_dir = output_dir / "records"
    if len(records) <= 200:
        records_dir.mkdir(parents=True, exist_ok=True)
        for rec in records:
            name = rec.accession or f"record_{rec.record_index:05d}"
            safe = re.sub(r"[^\w.-]", "_", name)
            (records_dir / f"{safe}.embl").write_text(rec.raw_record_text, encoding="utf-8")
    else:
        offset_rows = [
            {
                "record_index": r.record_index,
                "accession": r.accession,
                "raw_record_character_count": r.raw_record_character_count,
                "raw_record_line_count": r.raw_record_line_count,
                "parse_status": r.parse_status,
            }
            for r in records
        ]
        pd.DataFrame(offset_rows).to_csv(output_dir / "ena_record_offsets.csv", index=False)

    logger.info("Wrote inventory: %s (%d rows)", paths["ena_record_inventory.csv"], len(inventory))
    logger.info("Wrote feature long table: %s", feature_long_path)
    return paths


def configure_logging(log_path: Path, log_level: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    root.addHandler(stream_handler)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnostically inspect an ENA/EMBL aptamer search flat file. "
            "Does not create a final candidate dataset."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to ENA/EMBL flat file (default: search known download locations)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for inspection outputs (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--examples-per-category",
        type=int,
        default=5,
        help="Maximum review examples per category (default: 5)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing inspection output files",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    output_dir: Path = args.output_dir
    log_path = output_dir / "ena_inspection_log.txt"
    configure_logging(log_path, args.log_level)

    input_path = args.input or resolve_default_input()
    if input_path is None:
        logger.error(
            "No input file provided and no default candidate found. Tried: %s",
            ", ".join(str(p) for p in DEFAULT_INPUT_CANDIDATES),
        )
        return 2
    input_path = Path(input_path)

    logger.info("Starting ENA aptamer record inspection")
    logger.info("Input file: %s", input_path)
    logger.info("Output directory: %s", output_dir)
    logger.info("Biopython available: %s", HAS_BIOPYTHON)

    try:
        records = load_and_parse_records(input_path)
        malformed = sum(1 for r in records if r.parse_status != "ok")
        seq_fail = sum(1 for r in records if "sequence_parse_failure" in _pipe(r.parse_warnings))
        feat_fail = sum(1 for r in records if "feature_parse_failure" in _pipe(r.parse_warnings))
        logger.info("Records scanned: %d", len(records))
        logger.info("Malformed records: %d", malformed)
        logger.info("Sequence parsing failures: %d", seq_fail)
        logger.info("Feature parsing failures: %d", feat_fail)

        paths = write_outputs(
            records,
            input_path,
            output_dir,
            examples_per_category=args.examples_per_category,
            overwrite=args.overwrite,
        )
        for name, path in paths.items():
            logger.info("Output: %s -> %s", name, path)
        logger.info("Run completion status: SUCCESS")
        return 0
    except Exception as exc:
        logger.exception("Run completion status: FAILED (%s)", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

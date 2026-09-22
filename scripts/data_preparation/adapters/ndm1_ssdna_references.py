"""NDM-1 ssDNA published-reference verification (not a corpus-curation stage).

Independently transcribes a small target-specific set from primary PDFs,
compares those transcriptions with the preliminary additions/overrides CSV,
writes ignored verification ledgers, and runs leakage diagnostics against
frozen partitions. Does not modify the frozen RNA corpus or S0b outputs.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
import re
import subprocess
import tempfile
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from adapters.s4_scientific_common import write_json_atomic, write_text_atomic
from adapters.s5_validate_exact_dedup import (
    scan_paths_for_sequence_leak,
    scan_text_for_sequence_leak,
)
from adapters.target_extraction_common import SEQ_LEAK_RE
from common.leakage_matching import (
    IDENTITY_THRESHOLD,
    comparison_form,
    global_edit_identity,
)
from s0_build_registry import find_repo_root, sha256_file

SSDNA_ALPHABET = frozenset("ACGT")
MODIFICATION_RE = re.compile(r"^/(5BiotinTEG|5Cy5)/", re.IGNORECASE)
TERMINAL_MARK_RE = re.compile(
    r"(?:^\s*(?:5[′']|5'|5′)\s*[-–—:]?\s*)|(?:\s*[-–—:]?\s*(?:3[′']|3'|3′)\s*$)",
    re.IGNORECASE,
)
WHITESPACE_RE = re.compile(r"\s+")
DNA_TOKEN_RE = re.compile(r"[ACGT]+")
NUCLEOTIDE_ONLY_RE = re.compile(r"^[ACGTUacgtu]+$")
SEQUENCE_BEARING_KEY_RE = re.compile(
    r"(sequence|display[_-]?groups|fixed[_-]?5p|fixed[_-]?3p|flank)",
    re.I,
)
HASH_OR_LENGTH_KEY_RE = re.compile(r"(sha256|hash|length)", re.I)
PARAGRAPH_0040_RE = re.compile(r"\[0040\](.{0,1200}?)(?:\[0041\]|$)", re.S)
SEQ_ID_NO_1_RE = re.compile(r"SEQ\s*ID\s*NO\.?\s*:?\s*1\b", re.I)
HEX_TJ_RE = re.compile(rb"\[(.*?)\]\s*TJ", re.S)
PAREN_STRING_RE = re.compile(rb"\((?:\\.|[^\\)])*\)")
STREAM_RE = re.compile(rb"stream\r?\n(.*?)endstream", re.S)
MANUAL_EVIDENCE_COLUMNS: tuple[str, ...] = (
    "evidence_id",
    "reference_id",
    "evidence_type",
    "primary_source_file",
    "source_locator",
    "transcription_method",
    "orientation_evidence",
    "sequence_length",
    "sequence_sha256",
    "sequence",
)
EVIDENCE_CN102_LISTING = "image_only_sequence_listing"
EVIDENCE_CN102_FIXED_5P = "library_fixed_5p_flank"
EVIDENCE_CN102_FIXED_3P = "library_fixed_3p_flank"
EVIDENCE_APNV_FALLBACK = "fallback_seq_id_no_1_transcription"

VERIFICATION_STATUSES = frozenset(
    {
        "verified",
        "needs_human_review",
        "excluded_control",
        "excluded_not_ndm1",
        "excluded_not_sequence",
    }
)
INCLUDED_ROLES = frozenset(
    {
        "positive_ndm1_binder",
        "positive_ndm1_vim2_cross_binder",
    }
)
COMPATIBLE_REFERENCE_IDS = (
    "sabrowski2022_ndm1_h14_2_43",
    "sabrowski2022_ndm1_h14_01",
    "sabrowski2022_ndm1_h14_01_fr",
    "cn108949766b_apnv",
    "cn102965377b_seq1",
)
CONTROL_REFERENCE_IDS = (
    "sabrowski2022_con1",
    "sabrowski2022_consc",
)
CANDIDATE_REFERENCE_IDS = COMPATIBLE_REFERENCE_IDS
PROTECTED_UNTRACKED_DEFAULT = (
    "Consent to Act as Corresponding Author.pdf",
    "docs/dataset_search_curation_inventory_log_entry.md",
    "docs/fine-tuning-implementation-plan.md",
)

REFERENCE_COLUMNS: tuple[str, ...] = (
    "reference_id",
    "nucleotide_sequence_id",
    "aptamer_name",
    "target",
    "target_variant",
    "reference_role",
    "parent_reference_id",
    "variant_relationship",
    "molecule_type",
    "chemistry",
    "sequence",
    "sequence_length",
    "sequence_orientation",
    "sequence_scope",
    "fixed_regions_included",
    "selected_variable_region_length",
    "normalisation_applied",
    "sequence_sha256",
    "publication_type",
    "publication_title",
    "first_author_or_inventor",
    "year",
    "journal",
    "doi",
    "pmid",
    "patent_number",
    "source_file",
    "source_file_sha256",
    "source_location",
    "source_type",
    "source_sequence_verification_method",
    "selection_method",
    "selection_rounds",
    "binding_summary",
    "notes",
    "verification_status",
    "verified_against_primary_source",
    "sequence_discrepancy",
    "human_review_resolution",
    "human_reviewer",
    "human_review_resolution_date",
    "include_in_final_reference_set",
    "exclusion_reason",
)
CONSTRUCT_COLUMNS: tuple[str, ...] = (
    "construct_id",
    "reference_id",
    "nucleotide_sequence_id",
    "construct_name",
    "chemistry_label",
    "modification_5p",
    "modification_3p",
    "modification_position",
    "modification_linker",
    "sequence_sha256",
    "assay_roles",
    "source_file",
    "source_location",
    "notes",
)
MEASUREMENT_COLUMNS: tuple[str, ...] = (
    "measurement_id",
    "construct_id",
    "reference_id",
    "assay_method",
    "target",
    "target_variant",
    "ligand",
    "analyte",
    "affinity_type",
    "affinity_value",
    "affinity_unit",
    "affinity_value_molar",
    "ka_value",
    "ka_unit",
    "kd_value",
    "kd_unit",
    "binding_call",
    "source_location",
    "notes",
)
TRANSCRIPTION_COLUMNS: tuple[str, ...] = (
    "transcription_id",
    "reference_id",
    "aptamer_name",
    "construct_name",
    "source_file",
    "source_file_sha256",
    "source_location",
    "extraction_method",
    "sequence_as_transcribed",
    "sequence_canonical",
    "sequence_length",
    "sequence_sha256",
    "orientation_evidence",
    "fixed_regions_included",
    "modification_token",
    "modification_position",
    "has_u",
    "compared_to_additions_sequence_raw",
    "matches_additions_sequence_raw",
    "notes",
)

SABROWSKI_TITLE = (
    "The use of high-affinity polyhistidine binders as masking probes "
    "for the selection of an NDM-1 specific aptamer"
)
CN108_TITLE = (
    "A nucleic acid aptamer capable of simultaneously recognizing NDM-1 and VIM-2"
)
CN102_TITLE = "NDM-1 nucleic acid aptamer and its screening method and application"


class Ndm1SsdnaError(ValueError):
    """Hard failure during NDM-1 ssDNA reference verification."""


def bool_token(value: bool) -> str:
    return "true" if value else "false"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def nucleotide_sequence_id(sequence: str) -> str:
    return f"ntsha_{sha256_text(sequence)[:16]}"


def canonicalise_ssdna_sequence(raw: str, *, context: str = "sequence") -> str:
    """Uppercase and remove whitespace/display grouping only. Retain T. Reject U."""
    if raw is None:
        raise Ndm1SsdnaError(f"{context} is missing")
    text = TERMINAL_MARK_RE.sub("", str(raw))
    text = WHITESPACE_RE.sub("", text)
    text = text.upper()
    if not text:
        raise Ndm1SsdnaError(f"{context} is empty after whitespace/display cleanup")
    if "U" in text:
        raise Ndm1SsdnaError(
            f"{context} contains U; canonical ssDNA must retain T and reject U"
        )
    invalid = sorted({ch for ch in text if ch not in SSDNA_ALPHABET})
    if invalid:
        raise Ndm1SsdnaError(
            f"{context} contains characters outside A/C/G/T after cleanup"
        )
    return text


def split_modification_prefix(raw: str) -> tuple[str, str]:
    text = str(raw or "").strip()
    match = MODIFICATION_RE.match(WHITESPACE_RE.sub("", text))
    if not match:
        return "", text
    token = f"/{match.group(1)}/"
    remainder = WHITESPACE_RE.sub("", text)[match.end() :]
    return token, remainder


def join_display_groups(groups: Sequence[str], *, context: str) -> str:
    joined = "".join(str(item).strip() for item in groups)
    return canonicalise_ssdna_sequence(joined, context=context)


def is_nucleotide_token(value: str) -> bool:
    return bool(value) and NUCLEOTIDE_ONLY_RE.fullmatch(value) is not None


def is_sequence_bearing_key(key: str) -> bool:
    if HASH_OR_LENGTH_KEY_RE.search(key or ""):
        return False
    return SEQUENCE_BEARING_KEY_RE.search(key or "") is not None


def collect_reconstructable_nucleotide_payloads(obj: Any, *, key_hint: str = "") -> list[str]:
    payloads: list[str] = []
    if isinstance(obj, str):
        if is_nucleotide_token(obj):
            payloads.append(obj.upper())
        return payloads
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            key_text = str(key)
            if is_sequence_bearing_key(key_text):
                if isinstance(value, str) and is_nucleotide_token(value):
                    payloads.append(value.upper())
                elif isinstance(value, (list, tuple)) and value and all(
                    isinstance(item, str) and is_nucleotide_token(item) for item in value
                ):
                    payloads.append("".join(str(item).upper() for item in value))
            payloads.extend(
                collect_reconstructable_nucleotide_payloads(value, key_hint=key_text)
            )
        return payloads
    if isinstance(obj, (list, tuple)):
        items = list(obj)
        if items and all(isinstance(item, str) and is_nucleotide_token(item) for item in items):
            payloads.append("".join(str(item).upper() for item in items))
        for item in items:
            payloads.extend(
                collect_reconstructable_nucleotide_payloads(item, key_hint=key_hint)
            )
        return payloads
    return payloads


def _ast_string_constant(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def collect_python_reconstructable_nucleotide_payloads(source: str) -> list[str]:
    tree = ast.parse(source)
    payloads: list[str] = []

    def append_nucleotide_list(elts: Sequence[ast.AST]) -> None:
        values = [_ast_string_constant(item) for item in elts]
        if values and all(value is not None and is_nucleotide_token(value) for value in values):
            payloads.append("".join(str(value).upper() for value in values))

    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple)):
            append_nucleotide_list(node.elts)
        elif isinstance(node, ast.Dict):
            for key_node, value_node in zip(node.keys, node.values):
                key = _ast_string_constant(key_node) or ""
                value = _ast_string_constant(value_node)
                if is_sequence_bearing_key(key) and value and is_nucleotide_token(value):
                    payloads.append(value.upper())
                if isinstance(value_node, (ast.List, ast.Tuple)):
                    append_nucleotide_list(value_node.elts)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if is_nucleotide_token(node.value):
                payloads.append(node.value.upper())
    return payloads


def find_tracked_sequence_leaks(
    text: str,
    *,
    source_kind: str,
    published_hashes: Sequence[str] | None = None,
    min_json_literal_length: int = 8,
    leak_length: int = 20,
) -> list[str]:
    """Detect reconstructable nucleotide payloads in tracked text.

    Flags contiguous or concatenated nucleotide runs at `leak_length`,
    sequence-bearing JSON keys, JSON nucleotide literals, and any payload
    whose SHA-256 matches a published canonical hash.
    """
    reasons: list[str] = []
    payloads: list[str] = []
    published = {item.lower() for item in (published_hashes or []) if item}
    stripped = text.lstrip()
    if source_kind == "json" or stripped[:1] in "{[":
        try:
            payloads.extend(collect_reconstructable_nucleotide_payloads(json.loads(text)))
        except json.JSONDecodeError:
            pass
    if source_kind == "python":
        try:
            payloads.extend(collect_python_reconstructable_nucleotide_payloads(text))
        except SyntaxError:
            pass
    seen: set[str] = set()
    for payload in payloads:
        if payload in seen:
            continue
        seen.add(payload)
        digest = sha256_text(payload)
        if len(payload) >= leak_length:
            reasons.append(
                f"reconstructable_nucleotide_run length={len(payload)} sha256={digest}"
            )
        if source_kind == "json" and len(payload) >= min_json_literal_length:
            reasons.append(
                f"tracked_json_nucleotide_literal length={len(payload)} sha256={digest}"
            )
        if digest in published:
            reasons.append(f"published_canonical_hash_reconstructed sha256={digest}")
    if SEQ_LEAK_RE.search(text or ""):
        reasons.append("contiguous_nucleotide_string_of_length_20_or_more")
    return reasons


def validate_evidence_sequence(
    raw: str,
    *,
    context: str,
    expected_length: int | None = None,
    expected_sha256: str = "",
    orientation_evidence: str = "",
) -> str:
    sequence = canonicalise_ssdna_sequence(raw, context=context)
    if expected_length is not None and len(sequence) != int(expected_length):
        raise Ndm1SsdnaError(
            f"{context} length {len(sequence)} != expected {expected_length}"
        )
    if expected_sha256 and sha256_text(sequence) != expected_sha256:
        raise Ndm1SsdnaError(f"{context} SHA-256 does not match the evidence ledger")
    if not str(orientation_evidence or "").strip():
        raise Ndm1SsdnaError(f"{context} is missing orientation evidence")
    return sequence


def load_manual_primary_source_evidence(
    path: Path, *, expected_sha256: str
) -> list[dict[str, str]]:
    if not path.is_file():
        raise Ndm1SsdnaError(f"manual-evidence input is missing: {path}")
    observed = sha256_file(path)
    if expected_sha256 and observed != expected_sha256:
        raise Ndm1SsdnaError("manual-evidence input SHA-256 mismatch")
    rows = read_csv_rows(path)
    if not rows:
        raise Ndm1SsdnaError("manual-evidence input has no data rows")
    missing = [column for column in MANUAL_EVIDENCE_COLUMNS if column not in rows[0]]
    if missing:
        raise Ndm1SsdnaError(
            "manual-evidence input is missing columns: " + ", ".join(missing)
        )
    require_unique([row["evidence_id"] for row in rows], label="evidence_id")
    validated: list[dict[str, str]] = []
    for row in rows:
        expected_length = int(row["sequence_length"]) if row.get("sequence_length") else None
        sequence = validate_evidence_sequence(
            row["sequence"],
            context=row.get("evidence_id") or "manual evidence",
            expected_length=expected_length,
            expected_sha256=row.get("sequence_sha256") or "",
            orientation_evidence=row.get("orientation_evidence") or "",
        )
        validated.append({**row, "sequence": sequence})
    return validated


def evidence_sequence(
    rows: Sequence[Mapping[str, str]],
    *,
    reference_id: str,
    evidence_type: str,
    expected_length: int | None = None,
    expected_sha256: str = "",
) -> str:
    matches = [
        row
        for row in rows
        if row.get("reference_id") == reference_id
        and row.get("evidence_type") == evidence_type
    ]
    if len(matches) != 1:
        raise Ndm1SsdnaError(
            f"expected exactly one {evidence_type} evidence row for {reference_id}"
        )
    row = matches[0]
    return validate_evidence_sequence(
        row["sequence"],
        context=row.get("evidence_id") or evidence_type,
        expected_length=expected_length
        if expected_length is not None
        else (int(row["sequence_length"]) if row.get("sequence_length") else None),
        expected_sha256=expected_sha256 or row.get("sequence_sha256") or "",
        orientation_evidence=row.get("orientation_evidence") or "",
    )


def _decode_pdf_literal(raw: bytes) -> str:
    text = raw.replace(b"\\(", b"(").replace(b"\\)", b")")
    text = text.replace(b"\\n", b"\n").replace(b"\\r", b"").replace(b"\\t", b"\t")
    return text.decode("latin1", errors="replace")


def extract_pdf_tj_strings(path: Path) -> list[str]:
    data = path.read_bytes()
    items: list[str] = []
    for match in STREAM_RE.finditer(data):
        raw = match.group(1)
        if raw.endswith(b"\r\n"):
            raw = raw[:-2]
        elif raw.endswith(b"\n"):
            raw = raw[:-1]
        try:
            decoded = zlib.decompress(raw)
        except Exception:
            continue
        for tj in HEX_TJ_RE.finditer(decoded):
            parts = [
                _decode_pdf_literal(literal.group(0)[1:-1])
                for literal in PAREN_STRING_RE.finditer(tj.group(1))
            ]
            if parts:
                items.append("".join(parts))
    return items


def extract_pdf_text_pypdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def extract_pdf_text_mapped(path: Path) -> str:
    text = extract_pdf_text_pypdf(path)
    if text.strip():
        return text
    try:
        import pymupdf
    except ImportError:
        return text
    try:
        doc = pymupdf.open(str(path))
        return "\n".join((page.get_text("text") or "") for page in doc)
    except Exception:
        return text


def _first_dna_after(blob: str, pattern: str, *, context: str) -> str:
    match = re.search(pattern, blob)
    if not match:
        raise Ndm1SsdnaError(f"primary-source locator failed: {context}")
    fragments = [match.group(1)]
    tail = blob[match.end() :]
    extra = re.match(r"([ACGT]+)", tail)
    # Concatenate immediately adjacent DNA fragments split across PDF operators.
    while extra:
        fragments.append(extra.group(1))
        tail = tail[extra.end() :]
        extra = re.match(r"([ACGT]+)", tail)
    return canonicalise_ssdna_sequence("".join(fragments), context=context)


def extract_sabrowski_table_s2(path: Path) -> dict[str, dict[str, str]]:
    blob = "".join(extract_pdf_tj_strings(path))
    if "NDM1-H14.2_43" not in blob and "H14.2_43" not in blob:
        raise Ndm1SsdnaError("Sabrowski Supplementary Table S2 was not found")
    extracted = {
        "NDM1-H14.2_43": _first_dna_after(
            blob, r"NDM1-H14\.2_43\s*([ACGT]+)", context="NDM1-H14.2_43"
        ),
        "NDM1-H14-01-FR": _first_dna_after(
            blob, r"NDM1-H14-01-FR\s*([ACGT]+)", context="NDM1-H14-01-FR"
        ),
        "NDM1-H14-01": _first_dna_after(
            blob, r"NDM1-H14-01(?!-FR)\s*([ACGT]+)", context="NDM1-H14-01"
        ),
        "Bio-NDM1-H14-01-FR": _first_dna_after(
            blob,
            r"Bio-NDM1-H14-01-FR\s*/5BiotinTEG/([ACGT]+)",
            context="Bio-NDM1-H14-01-FR",
        ),
        "Bio-NDM1-H14-01": _first_dna_after(
            blob,
            r"Bio-NDM1-H14-01(?!-FR)\s*/5BiotinTEG/([ACGT]+)",
            context="Bio-NDM1-H14-01",
        ),
        "Cy5-NDM1-H14-01": _first_dna_after(
            blob,
            r"Cy5-NDM1-H14-01\s*/5Cy5/([ACGT]+)",
            context="Cy5-NDM1-H14-01",
        ),
        "Bio-NDM1-H14.2_43": _first_dna_after(
            blob,
            r"Bio-NDM1-H14\.2_43\s*/5BiotinTEG/([ACGT]+)",
            context="Bio-NDM1-H14.2_43",
        ),
        "Cy5-NDM1-H14.2_43": _first_dna_after(
            blob,
            r"Cy5-NDM1-H14\.2_43\s*/5Cy5/([ACGT]+)",
            context="Cy5-NDM1-H14.2_43",
        ),
        "Cy5-Con1": _first_dna_after(
            blob, r"Cy5-Con1\s*/5Cy5/([ACGT]+)", context="Cy5-Con1"
        ),
        "Bio-ConSc": _first_dna_after(
            blob, r"Bio-ConSc\s*/5BiotinTEG/([ACGT]+)", context="Bio-ConSc"
        ),
    }
    return extracted


def extract_dna_window(
    blob: str,
    *,
    expected_length: int,
    context: str,
) -> str:
    tokens = DNA_TOKEN_RE.findall(blob.upper())
    joined = ""
    for token in tokens:
        joined += token
        if len(joined) >= expected_length:
            break
    if len(joined) < expected_length:
        raise Ndm1SsdnaError(
            f"{context} did not yield the expected DNA length {expected_length}"
        )
    return canonicalise_ssdna_sequence(joined[:expected_length], context=context)


def extract_cn108_apnv_from_pdf(
    path: Path, *, expected_length: int
) -> tuple[str, str]:
    if not path.is_file():
        raise Ndm1SsdnaError("CN108 patent PDF is missing")
    pdf_text = extract_pdf_text_mapped(path)
    if not str(pdf_text or "").strip():
        raise Ndm1SsdnaError("CN108 PDF text extraction returned no mapped text")
    paragraph = PARAGRAPH_0040_RE.search(pdf_text)
    window = paragraph.group(0) if paragraph else pdf_text
    marker = SEQ_ID_NO_1_RE.search(window)
    blob = window[marker.end() :] if marker else window
    sequence = extract_dna_window(
        blob, expected_length=expected_length, context="CN108 PDF paragraph [0040]"
    )
    return sequence, "independent_pdf_text_extraction_paragraph_0040"


def obtain_apnv_sequence(
    *,
    pdf_path: Path,
    evidence_rows: Sequence[Mapping[str, str]],
    expected_length: int,
    expected_sha256: str,
) -> tuple[str, str]:
    fallback: str | None = None
    fallback_rows = [
        row
        for row in evidence_rows
        if row.get("reference_id") == "cn108949766b_apnv"
        and row.get("evidence_type") == EVIDENCE_APNV_FALLBACK
    ]
    if len(fallback_rows) > 1:
        raise Ndm1SsdnaError("multiple APNV fallback evidence rows are present")
    if fallback_rows:
        fallback = validate_evidence_sequence(
            fallback_rows[0]["sequence"],
            context=fallback_rows[0].get("evidence_id") or "APNV fallback",
            expected_length=expected_length,
            expected_sha256=expected_sha256 or fallback_rows[0].get("sequence_sha256") or "",
            orientation_evidence=fallback_rows[0].get("orientation_evidence") or "",
        )
    try:
        sequence, method = extract_cn108_apnv_from_pdf(
            pdf_path, expected_length=expected_length
        )
    except Ndm1SsdnaError as exc:
        if fallback is None:
            raise Ndm1SsdnaError(
                "CN108 APNV PDF extraction failed and no fallback evidence is present"
            ) from exc
        if expected_sha256 and sha256_text(fallback) != expected_sha256:
            raise Ndm1SsdnaError("APNV fallback hash mismatch") from exc
        return fallback, "fallback_manual_primary_source_evidence_paragraph_0040"
    if expected_length and len(sequence) != expected_length:
        raise Ndm1SsdnaError("CN108 PDF APNV length mismatch")
    if expected_sha256 and sha256_text(sequence) != expected_sha256:
        raise Ndm1SsdnaError("CN108 PDF APNV SHA-256 mismatch")
    if fallback is not None and sequence != fallback:
        raise Ndm1SsdnaError("CN108 PDF text and fallback evidence disagree")
    return sequence, method


def cn102_architecture_conflict(
    sequence: str,
    architecture: Mapping[str, Any],
    *,
    flank5: str,
    flank3: str,
) -> dict[str, Any]:
    flank5_seq = canonicalise_ssdna_sequence(flank5, context="CN102 5p flank")
    flank3_seq = canonicalise_ssdna_sequence(flank3, context="CN102 3p flank")
    expected_5p = int(architecture["fixed_5p_length"])
    expected_3p = int(architecture["fixed_3p_length"])
    if len(flank5_seq) != expected_5p:
        raise Ndm1SsdnaError("CN102 5-prime flank length does not match config")
    if len(flank3_seq) != expected_3p:
        raise Ndm1SsdnaError("CN102 3-prime flank length does not match config")
    stated_total = int(architecture["stated_total_length"])
    listing_length = int(architecture["sequence_listing_length"])
    n_random = int(architecture["n_random"])
    starts_5p = sequence.startswith(flank5_seq)
    ends_3p = sequence.endswith(flank3_seq)
    return {
        "stated_architecture": f"{len(flank5_seq)} + N{n_random} + {len(flank3_seq)}",
        "stated_total_length": stated_total,
        "sequence_listing_length": listing_length,
        "starts_with_stated_5p_flank": starts_5p,
        "ends_with_stated_3p_flank": ends_3p,
        "architecture_length_matches_listing": stated_total == listing_length,
        "conflict": True,
        "discrepancy": "source_internal_library_architecture_conflict",
        "human_review_resolution": (
            "explicit_sequence_listing_accepted_over_generic_library_architecture"
        ),
    }


def _atomic_write_csv(
    path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, str]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".csv.tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(fieldnames),
                lineterminator="\n",
                extrasaction="ignore",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(handle)]


def collect_raw_source_hashes(repo_root: Path) -> dict[str, str]:
    root = repo_root / "data" / "raw" / "evaluation_references"
    hashes: dict[str, str] = {}
    if not root.is_dir():
        return hashes
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != ".DS_Store":
            rel = path.relative_to(repo_root).as_posix()
            hashes[rel] = sha256_file(path)
    return hashes


def hash_protected_files(repo_root: Path, relative_paths: Sequence[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for rel in relative_paths:
        path = repo_root / rel
        hashes[rel] = sha256_file(path) if path.is_file() else "missing"
    return hashes


def git_ls_files_data(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "ls-files", "data"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def include_in_final_reference_set(
    *, verification_status: str, reference_role: str
) -> bool:
    if verification_status not in VERIFICATION_STATUSES:
        raise Ndm1SsdnaError(f"unknown verification_status: {verification_status}")
    if verification_status != "verified":
        return False
    return reference_role in INCLUDED_ROLES


def require_unique(values: Sequence[str], *, label: str) -> None:
    if len(values) != len(set(values)):
        raise Ndm1SsdnaError(f"duplicate {label} values")


def exact_sequence_duplicates(rows: Sequence[Mapping[str, str]]) -> list[list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        grouped[row["sequence"]].append(row["reference_id"])
    return [ids for ids in grouped.values() if len(ids) > 1]


def _row(
    columns: Sequence[str], values: Mapping[str, Any]
) -> dict[str, str]:
    return {column: "" if values.get(column) is None else str(values.get(column, "")) for column in columns}


def build_transcription_rows(
    *,
    config: Mapping[str, Any],
    repo_root: Path,
    source_hashes: Mapping[str, str],
    additions_by_id: Mapping[str, Mapping[str, str]],
    sabrowski_extract: Mapping[str, str],
    apnv_sequence: str,
    apnv_method: str,
    cn102_sequence: str,
) -> list[dict[str, str]]:
    supp = config["raw_sources"]["sabrowski_2022_supplementary.pdf"]
    cn108 = config["raw_sources"]["CN108949766B_patent.pdf"]
    cn102 = config["raw_sources"]["CN102965377B_patent.pdf"]
    specs = [
        {
            "transcription_id": "tx_sabrowski2022_ndm1_h14_2_43",
            "reference_id": "sabrowski2022_ndm1_h14_2_43",
            "aptamer_name": "NDM1-H14.2_43",
            "construct_name": "NDM1-H14.2_43",
            "source_file": supp["path"],
            "source_location": "Supplementary Table S2, PDF pages 6-7",
            "extraction_method": "independent_pdf_tj_text_extraction",
            "sequence": sabrowski_extract["NDM1-H14.2_43"],
            "orientation_evidence": "Table S2 5-prime-to-3-prime listing; library written 5p-N44-3p on main PDF page 8",
            "fixed_regions_included": "true",
            "modification_token": "",
            "modification_position": "",
        },
        {
            "transcription_id": "tx_sabrowski2022_ndm1_h14_01",
            "reference_id": "sabrowski2022_ndm1_h14_01",
            "aptamer_name": "NDM1-H14-01",
            "construct_name": "NDM1-H14-01",
            "source_file": supp["path"],
            "source_location": "Supplementary Table S2, PDF pages 6-7",
            "extraction_method": "independent_pdf_tj_text_extraction",
            "sequence": sabrowski_extract["NDM1-H14-01"],
            "orientation_evidence": "Table S2 5-prime-to-3-prime listing; full-length library clone including both primer regions",
            "fixed_regions_included": "true",
            "modification_token": "",
            "modification_position": "",
        },
        {
            "transcription_id": "tx_sabrowski2022_ndm1_h14_01_fr",
            "reference_id": "sabrowski2022_ndm1_h14_01_fr",
            "aptamer_name": "NDM1-H14-01-FR",
            "construct_name": "NDM1-H14-01-FR",
            "source_file": supp["path"],
            "source_location": "Supplementary Table S2, PDF pages 6-7; main article PDF page 4 truncation description",
            "extraction_method": "independent_pdf_tj_text_extraction",
            "sequence": sabrowski_extract["NDM1-H14-01-FR"],
            "orientation_evidence": "Published 44-nt truncated derivative lacking both primer-binding regions; 5-prime-to-3-prime",
            "fixed_regions_included": "false",
            "modification_token": "",
            "modification_position": "",
        },
        {
            "transcription_id": "tx_sabrowski2022_con1",
            "reference_id": "sabrowski2022_con1",
            "aptamer_name": "Con1",
            "construct_name": "Cy5-Con1",
            "source_file": supp["path"],
            "source_location": "Supplementary Table S2, PDF page 7, Cy5-Con1 row",
            "extraction_method": "independent_pdf_tj_text_extraction",
            "sequence": sabrowski_extract["Cy5-Con1"],
            "orientation_evidence": "Table S2 5-prime-to-3-prime listing of the Cy5-labelled control oligonucleotide",
            "fixed_regions_included": "not_applicable",
            "modification_token": "/5Cy5/",
            "modification_position": "5_prime",
        },
        {
            "transcription_id": "tx_sabrowski2022_consc",
            "reference_id": "sabrowski2022_consc",
            "aptamer_name": "ConSc",
            "construct_name": "Bio-ConSc",
            "source_file": supp["path"],
            "source_location": "Supplementary Table S2, PDF page 7, Bio-ConSc row",
            "extraction_method": "independent_pdf_tj_text_extraction",
            "sequence": sabrowski_extract["Bio-ConSc"],
            "orientation_evidence": "Table S2 5-prime-to-3-prime listing of the biotinylated scramble control",
            "fixed_regions_included": "not_applicable",
            "modification_token": "/5BiotinTEG/",
            "modification_position": "5_prime",
        },
        {
            "transcription_id": "tx_cn108949766b_apnv",
            "reference_id": "cn108949766b_apnv",
            "aptamer_name": "APNV",
            "construct_name": "APNV",
            "source_file": cn108["path"],
            "source_location": "CN108949766B paragraph [0040], PDF page 6, SEQ ID NO:1",
            "extraction_method": apnv_method,
            "sequence": apnv_sequence,
            "orientation_evidence": "Patent SEQ ID NO:1 nucleotide listing in 5-prime-to-3-prime order",
            "fixed_regions_included": "false",
            "modification_token": "",
            "modification_position": "",
        },
        {
            "transcription_id": "tx_cn102965377b_seq1",
            "reference_id": "cn102965377b_seq1",
            "aptamer_name": "SEQ ID NO:1",
            "construct_name": "CN102965377B SEQ ID NO:1",
            "source_file": cn102["path"],
            "source_location": "CN102965377B sequence listing, PDF page 9, <400>1",
            "extraction_method": "independent_visual_transcription_of_image_only_sequence_listing",
            "sequence": cn102_sequence,
            "orientation_evidence": "Patent sequence listing <400>1 in standard 5-prime-to-3-prime SEQ ID format; listing is an image-only scanned page",
            "fixed_regions_included": "claimed_with_3p_mismatch",
            "modification_token": "",
            "modification_position": "",
        },
    ]
    rows: list[dict[str, str]] = []
    for spec in specs:
        sequence = canonicalise_ssdna_sequence(
            spec["sequence"], context=spec["reference_id"]
        )
        additions = additions_by_id.get(spec["reference_id"], {})
        raw = additions.get("sequence_raw", "")
        compared = bool(raw)
        matches = False
        if compared:
            matches = (
                canonicalise_ssdna_sequence(raw, context=f"{spec['reference_id']} additions")
                == sequence
            )
        rows.append(
            _row(
                TRANSCRIPTION_COLUMNS,
                {
                    **spec,
                    "source_file_sha256": source_hashes.get(spec["source_file"], ""),
                    "sequence_as_transcribed": sequence,
                    "sequence_canonical": sequence,
                    "sequence_length": str(len(sequence)),
                    "sequence_sha256": sha256_text(sequence),
                    "has_u": "false",
                    "compared_to_additions_sequence_raw": bool_token(compared),
                    "matches_additions_sequence_raw": bool_token(matches) if compared else "",
                    "notes": "",
                },
            )
        )
    labeled = [
        (
            "tx_bio_ndm1_h14_2_43",
            "sabrowski2022_ndm1_h14_2_43",
            "NDM1-H14.2_43",
            "Bio-NDM1-H14.2_43",
            "/5BiotinTEG/",
            sabrowski_extract["Bio-NDM1-H14.2_43"],
        ),
        (
            "tx_cy5_ndm1_h14_2_43",
            "sabrowski2022_ndm1_h14_2_43",
            "NDM1-H14.2_43",
            "Cy5-NDM1-H14.2_43",
            "/5Cy5/",
            sabrowski_extract["Cy5-NDM1-H14.2_43"],
        ),
        (
            "tx_bio_ndm1_h14_01",
            "sabrowski2022_ndm1_h14_01",
            "NDM1-H14-01",
            "Bio-NDM1-H14-01",
            "/5BiotinTEG/",
            sabrowski_extract["Bio-NDM1-H14-01"],
        ),
        (
            "tx_cy5_ndm1_h14_01",
            "sabrowski2022_ndm1_h14_01",
            "NDM1-H14-01",
            "Cy5-NDM1-H14-01",
            "/5Cy5/",
            sabrowski_extract["Cy5-NDM1-H14-01"],
        ),
        (
            "tx_bio_ndm1_h14_01_fr",
            "sabrowski2022_ndm1_h14_01_fr",
            "NDM1-H14-01-FR",
            "Bio-NDM1-H14-01-FR",
            "/5BiotinTEG/",
            sabrowski_extract["Bio-NDM1-H14-01-FR"],
        ),
    ]
    parent_seq = {row["reference_id"]: row["sequence_canonical"] for row in rows}
    for tx_id, ref_id, aptamer, construct, token, seq in labeled:
        sequence = canonicalise_ssdna_sequence(seq, context=construct)
        if sequence != parent_seq[ref_id]:
            raise Ndm1SsdnaError(
                f"labelled construct {construct} nucleotide sequence differs from parent"
            )
        rows.append(
            _row(
                TRANSCRIPTION_COLUMNS,
                {
                    "transcription_id": tx_id,
                    "reference_id": ref_id,
                    "aptamer_name": aptamer,
                    "construct_name": construct,
                    "source_file": supp["path"],
                    "source_file_sha256": source_hashes.get(supp["path"], ""),
                    "source_location": "Supplementary Table S2, PDF page 7 labelled-construct rows",
                    "extraction_method": "independent_pdf_tj_text_extraction",
                    "sequence_as_transcribed": sequence,
                    "sequence_canonical": sequence,
                    "sequence_length": str(len(sequence)),
                    "sequence_sha256": sha256_text(sequence),
                    "orientation_evidence": "Table S2 5-prime modification token precedes the same 5-prime-to-3-prime nucleotide string",
                    "fixed_regions_included": next(
                        item["fixed_regions_included"]
                        for item in rows
                        if item["reference_id"] == ref_id
                        and item["construct_name"] == aptamer
                    ),
                    "modification_token": token,
                    "modification_position": "5_prime",
                    "has_u": "false",
                    "compared_to_additions_sequence_raw": bool_token(
                        bool(additions_by_id.get(ref_id, {}).get("sequence_raw"))
                    ),
                    "matches_additions_sequence_raw": (
                        bool_token(
                            sequence
                            == canonicalise_ssdna_sequence(
                                additions_by_id[ref_id]["sequence_raw"],
                                context=f"{ref_id} labelled comparison",
                            )
                        )
                        if additions_by_id.get(ref_id, {}).get("sequence_raw")
                        else ""
                    ),
                    "notes": "Modification token kept outside the canonical sequence field",
                },
            )
        )
    rows.sort(key=lambda row: row["transcription_id"])
    return rows


def build_reference_rows(
    *,
    config: Mapping[str, Any],
    transcriptions: Mapping[str, Mapping[str, str]],
    source_hashes: Mapping[str, str],
    cn102_conflict: Mapping[str, Any],
) -> list[dict[str, str]]:
    supp = config["raw_sources"]["sabrowski_2022_supplementary.pdf"]["path"]
    cn108 = config["raw_sources"]["CN108949766B_patent.pdf"]["path"]
    cn102 = config["raw_sources"]["CN102965377B_patent.pdf"]["path"]
    records = [
        {
            "reference_id": "cn102965377b_seq1",
            "aptamer_name": "SEQ ID NO:1",
            "target": "NDM-1",
            "target_variant": "",
            "reference_role": str(
                (config.get("cn102_human_review") or {}).get(
                    "reference_role", "positive_ndm1_binder"
                )
            ),
            "parent_reference_id": "",
            "variant_relationship": "",
            "sequence_scope": "full_length_selected_oligonucleotide",
            "fixed_regions_included": "claimed_with_3p_mismatch",
            "selected_variable_region_length": "",
            "publication_type": "patent",
            "publication_title": CN102_TITLE,
            "first_author_or_inventor": "Zhao Zuguo",
            "year": "2014",
            "journal": "",
            "doi": "",
            "pmid": "",
            "patent_number": "CN102965377B",
            "source_file": cn102,
            "source_location": "Sequence listing PDF page 9; library [0052]-[0056] PDF page 6; SPR [0091]-[0096] PDF pages 7-8",
            "source_type": "patent_sequence_listing",
            "source_sequence_verification_method": "independent_visual_transcription_of_image_only_sequence_listing",
            "selection_method": "In vitro DNA SELEX against purified NDM-1 with BSA counter-selection",
            "selection_rounds": "10",
            "binding_summary": "SPR KD = 5 nM versus NDM-1 for a biotinylated assay construct",
            "notes": (
                "Laura accepted the exact published 88-nt SEQ ID NO:1 listing on "
                "2026-09-22. The contradictory generic library architecture "
                "(19 + N45 + 22 = 86 nt; 3-prime flank mismatch) remains documented. "
                "No shortening, 3-prime repair, or inferred core was generated."
            ),
            "verification_status": str(
                (config.get("cn102_human_review") or {}).get(
                    "verification_status", "verified"
                )
            ),
            "sequence_discrepancy": str(
                (config.get("cn102_human_review") or {}).get(
                    "sequence_discrepancy",
                    "source_internal_library_architecture_conflict",
                )
            ),
            "human_review_resolution": str(
                (config.get("cn102_human_review") or {}).get(
                    "human_review_resolution",
                    "explicit_sequence_listing_accepted_over_generic_library_architecture",
                )
            ),
            "human_reviewer": str(
                (config.get("cn102_human_review") or {}).get("human_reviewer", "Laura")
            ),
            "human_review_resolution_date": str(
                (config.get("cn102_human_review") or {}).get(
                    "human_review_resolution_date", "2026-09-22"
                )
            ),
            "exclusion_reason": "",
        },
        {
            "reference_id": "cn108949766b_apnv",
            "aptamer_name": "APNV",
            "target": "NDM-1|VIM-2",
            "target_variant": "",
            "reference_role": "positive_ndm1_vim2_cross_binder",
            "parent_reference_id": "",
            "variant_relationship": "",
            "sequence_scope": "selected_aptamer_sequence",
            "fixed_regions_included": "false",
            "selected_variable_region_length": "35",
            "publication_type": "patent",
            "publication_title": CN108_TITLE,
            "first_author_or_inventor": "Zhao Zuguo",
            "year": "2022",
            "journal": "",
            "doi": "",
            "pmid": "",
            "patent_number": "CN108949766B",
            "source_file": cn108,
            "source_location": "Paragraph [0040], PDF page 6; affinity [0070]-[0073], PDF page 7",
            "source_type": "patent_specification",
            "selection_method": "Alternating SELEX against immobilised NDM-1 and VIM-2",
            "selection_rounds": "8",
            "binding_summary": "SPR KD = 8.7 nM for NDM-1 and 11 nM for VIM-2",
            "notes": "Cross-binder, not NDM-1-specific. 35-nt SEQ ID NO:1 is the selected sequence without stated fixed flanks.",
            "verification_status": "verified",
            "sequence_discrepancy": "",
            "exclusion_reason": "",
        },
        {
            "reference_id": "sabrowski2022_con1",
            "aptamer_name": "Con1",
            "target": "HIS-NDM-1",
            "target_variant": "HIS-NDM-1",
            "reference_role": "unrelated_dna_binding_control",
            "parent_reference_id": "",
            "variant_relationship": "",
            "sequence_scope": "unrelated_control_oligonucleotide",
            "fixed_regions_included": "not_applicable",
            "selected_variable_region_length": "",
            "publication_type": "journal_article",
            "publication_title": SABROWSKI_TITLE,
            "first_author_or_inventor": "Wiebke Sabrowski",
            "year": "2022",
            "journal": "Scientific Reports",
            "doi": "10.1038/s41598-022-12062-2",
            "pmid": "",
            "patent_number": "",
            "source_file": supp,
            "source_location": "Supplementary Table S2 Cy5-Con1 row, PDF page 7; main article Table 2 and PDF pages 6 and 9",
            "source_type": "supplementary_table",
            "source_sequence_verification_method": "independent_pdf_tj_text_extraction",
            "selection_method": "Unrelated control oligonucleotide; not an NDM-1 selection product",
            "selection_rounds": "",
            "binding_summary": "MST: no binding of Cy5-Con1 to HIS-NDM-1",
            "notes": "Audit/control lane only. Sequence taken from the Cy5-Con1 Table S2 row after removing the 5-prime Cy5 token.",
            "verification_status": "excluded_control",
            "sequence_discrepancy": "",
            "exclusion_reason": "excluded_control",
        },
        {
            "reference_id": "sabrowski2022_consc",
            "aptamer_name": "ConSc",
            "target": "HIS-NDM-1",
            "target_variant": "HIS-NDM-1",
            "reference_role": "scramble_control",
            "parent_reference_id": "",
            "variant_relationship": "",
            "sequence_scope": "scramble_control_oligonucleotide",
            "fixed_regions_included": "not_applicable",
            "selected_variable_region_length": "",
            "publication_type": "journal_article",
            "publication_title": SABROWSKI_TITLE,
            "first_author_or_inventor": "Wiebke Sabrowski",
            "year": "2022",
            "journal": "Scientific Reports",
            "doi": "10.1038/s41598-022-12062-2",
            "pmid": "",
            "patent_number": "",
            "source_file": supp,
            "source_location": "Supplementary Table S2 Bio-ConSc row, PDF page 7; main article Table 2, Figure 4 discussion PDF page 6, SPR methods PDF page 9",
            "source_type": "supplementary_table",
            "source_sequence_verification_method": "independent_pdf_tj_text_extraction",
            "selection_method": "Scramble control designed with The Sequence Manipulation Suite",
            "selection_rounds": "",
            "binding_summary": "SPR: reduced response versus HIS-NDM-1; kinetic parameters not determined",
            "notes": "Audit/control lane only. Sequence taken from the Bio-ConSc Table S2 row after removing the 5-prime BiotinTEG token.",
            "verification_status": "excluded_control",
            "sequence_discrepancy": "",
            "exclusion_reason": "excluded_control",
        },
        {
            "reference_id": "sabrowski2022_ndm1_h14_01",
            "aptamer_name": "NDM1-H14-01",
            "target": "HIS-tag",
            "target_variant": "polyhistidine_tag",
            "reference_role": "his_tag_binding_control",
            "parent_reference_id": "",
            "variant_relationship": "",
            "sequence_scope": "full_length_with_fixed_regions",
            "fixed_regions_included": "true",
            "selected_variable_region_length": "44",
            "publication_type": "journal_article",
            "publication_title": SABROWSKI_TITLE,
            "first_author_or_inventor": "Wiebke Sabrowski",
            "year": "2022",
            "journal": "Scientific Reports",
            "doi": "10.1038/s41598-022-12062-2",
            "pmid": "",
            "patent_number": "",
            "source_file": supp,
            "source_location": "Supplementary Table S2, PDF pages 6-7; main article Table 1, PDF page 4",
            "source_type": "supplementary_table",
            "source_sequence_verification_method": "independent_pdf_tj_text_extraction",
            "selection_method": "Initial semiautomatic DNA SELEX against HIS-NDM-1 before masking",
            "selection_rounds": "Identified after SR14.1",
            "binding_summary": "SPR/MST polyhistidine binder, not NDM-1-specific",
            "notes": "High-affinity HIS-tag binder. Includes both 18-nt primer-binding regions.",
            "verification_status": "excluded_control",
            "sequence_discrepancy": "",
            "exclusion_reason": "excluded_control; his_tag_binding_control",
        },
        {
            "reference_id": "sabrowski2022_ndm1_h14_01_fr",
            "aptamer_name": "NDM1-H14-01-FR",
            "target": "HIS-tag",
            "target_variant": "polyhistidine_tag",
            "reference_role": "his_tag_masking_control",
            "parent_reference_id": "sabrowski2022_ndm1_h14_01",
            "variant_relationship": "experimentally_tested_truncation",
            "sequence_scope": "truncated_masking_probe_without_fixed_regions",
            "fixed_regions_included": "false",
            "selected_variable_region_length": "44",
            "publication_type": "journal_article",
            "publication_title": SABROWSKI_TITLE,
            "first_author_or_inventor": "Wiebke Sabrowski",
            "year": "2022",
            "journal": "Scientific Reports",
            "doi": "10.1038/s41598-022-12062-2",
            "pmid": "",
            "patent_number": "",
            "source_file": supp,
            "source_location": "Supplementary Table S2, PDF pages 6-7; main article Table 1 and truncation description, PDF page 4",
            "source_type": "supplementary_table",
            "source_sequence_verification_method": "independent_pdf_tj_text_extraction",
            "selection_method": "Truncated derivative of NDM1-H14-01 used as a HIS-tag masking probe",
            "selection_rounds": "Used during SR11.2_Mask-SR14.2_Mask",
            "binding_summary": "SPR HIS-tag masking probe; retains polyhistidine binding without primer regions",
            "notes": "Source-supported 44-nt truncation of NDM1-H14-01. Not an NDM-1-specific aptamer.",
            "verification_status": "excluded_control",
            "sequence_discrepancy": "",
            "exclusion_reason": "excluded_control; his_tag_masking_control",
        },
        {
            "reference_id": "sabrowski2022_ndm1_h14_2_43",
            "aptamer_name": "NDM1-H14.2_43",
            "target": "NDM-1",
            "target_variant": "HIS-NDM-1",
            "reference_role": "positive_ndm1_binder",
            "parent_reference_id": "",
            "variant_relationship": "",
            "sequence_scope": "full_length_with_fixed_regions",
            "fixed_regions_included": "true",
            "selected_variable_region_length": "44",
            "publication_type": "journal_article",
            "publication_title": SABROWSKI_TITLE,
            "first_author_or_inventor": "Wiebke Sabrowski",
            "year": "2022",
            "journal": "Scientific Reports",
            "doi": "10.1038/s41598-022-12062-2",
            "pmid": "",
            "patent_number": "",
            "source_file": supp,
            "source_location": "Supplementary Table S2, PDF pages 6-7; main article Figure 4 PDF page 6, Table 2 PDF page 7",
            "source_type": "supplementary_table",
            "source_sequence_verification_method": "independent_pdf_tj_text_extraction",
            "selection_method": "Semiautomatic DNA SELEX with negative selection against unrelated HIS-tagged proteins and HIS-tag masking using NDM1-H14-01-FR",
            "selection_rounds": "Restarted from SR10.1; SR11.2_Mask-SR14.2_Mask",
            "binding_summary": "SPR KD = 7.45e-7 M and MST KD = 2.82e-6 M versus HIS-NDM-1; no MST binding to HIS-OXA-23 or hexa-HIS peptide",
            "notes": "Binds HIS-NDM-1 but not HIS-OXA-23 or isolated hexa-HIS peptide. Includes both 18-nt primer-binding regions.",
            "verification_status": "verified",
            "sequence_discrepancy": "",
            "exclusion_reason": "",
        },
    ]
    rows: list[dict[str, str]] = []
    for record in records:
        tx = transcriptions[record["reference_id"]]
        if record["reference_id"] == "cn108949766b_apnv":
            record = {
                **record,
                "source_sequence_verification_method": tx["extraction_method"],
            }
        sequence = tx["sequence_canonical"]
        status = record["verification_status"]
        role = record["reference_role"]
        include = include_in_final_reference_set(
            verification_status=status, reference_role=role
        )
        if status == "needs_human_review" and include:
            raise Ndm1SsdnaError("needs_human_review cannot be included")
        if status == "excluded_control" and include:
            raise Ndm1SsdnaError("controls cannot be included as positive references")
        if "U" in sequence:
            raise Ndm1SsdnaError("canonical ssDNA sequence unexpectedly contains U")
        if comparison_form(sequence) != sequence:
            raise Ndm1SsdnaError(
                "canonical ssDNA sequence must not store comparison-normalised U-to-T text"
            )
        rows.append(
            _row(
                REFERENCE_COLUMNS,
                {
                    **record,
                    "nucleotide_sequence_id": nucleotide_sequence_id(sequence),
                    "molecule_type": "ssDNA",
                    "chemistry": "ssDNA",
                    "sequence": sequence,
                    "sequence_length": str(len(sequence)),
                    "sequence_orientation": "5_prime_to_3_prime",
                    "normalisation_applied": "uppercase_whitespace_display_grouping_only",
                    "sequence_sha256": sha256_text(sequence),
                    "source_file_sha256": source_hashes.get(record["source_file"], ""),
                    "verified_against_primary_source": bool_token(True),
                    "include_in_final_reference_set": bool_token(include),
                },
            )
        )
    rows.sort(key=lambda row: row["reference_id"])
    expected = config.get("expected_canonical_sequence_sha256") or {}
    expected_lengths = config.get("expected_sequence_lengths") or {}
    for row in rows:
        wanted = expected.get(row["reference_id"])
        if wanted and row["sequence_sha256"] != wanted:
            raise Ndm1SsdnaError(
                f"canonical sequence hash mismatch for {row['reference_id']}"
            )
        wanted_length = expected_lengths.get(row["reference_id"])
        if wanted_length is not None and int(row["sequence_length"]) != int(wanted_length):
            raise Ndm1SsdnaError(
                f"canonical sequence length mismatch for {row['reference_id']}"
            )
    if cn102_conflict["discrepancy"] != "source_internal_library_architecture_conflict":
        raise Ndm1SsdnaError("CN102 conflict was not recorded")
    cn102_row = next(row for row in rows if row["reference_id"] == "cn102965377b_seq1")
    review = config.get("cn102_human_review") or {}
    if review:
        if cn102_row["verification_status"] != str(review.get("verification_status", "verified")):
            raise Ndm1SsdnaError("CN102 verification_status does not match the accepted review")
        if cn102_row["include_in_final_reference_set"] != bool_token(
            bool(review.get("include_in_final_reference_set", True))
        ):
            raise Ndm1SsdnaError("CN102 include flag does not match the accepted review")
        if cn102_row["sequence_discrepancy"] != str(
            review.get(
                "sequence_discrepancy",
                "source_internal_library_architecture_conflict",
            )
        ):
            raise Ndm1SsdnaError("CN102 sequence_discrepancy was not retained")
    return rows


def build_construct_rows(
    *,
    references: Sequence[Mapping[str, str]],
    sabrowski_extract: Mapping[str, str],
    source_hashes: Mapping[str, str],
    supp_path: str,
    cn108_path: str,
    cn102_path: str,
) -> list[dict[str, str]]:
    by_id = {row["reference_id"]: row for row in references}
    specs = [
        ("sabrowski2022_ndm1_h14_2_43", "NDM1-H14.2_43", "unmodified", "", "", "", "unmodified parent oligonucleotide", supp_path, "Supplementary Table S2 unmodified row"),
        ("sabrowski2022_ndm1_h14_2_43", "Bio-NDM1-H14.2_43", "5p_biotinteg", "/5BiotinTEG/", "5_prime", "TEG", "SPR ligand", supp_path, "Supplementary Table S2; main article Table 2 and SPR methods PDF page 9"),
        ("sabrowski2022_ndm1_h14_2_43", "Cy5-NDM1-H14.2_43", "5p_cy5", "/5Cy5/", "5_prime", "not_applicable", "MST ligand", supp_path, "Supplementary Table S2; main article Table 2 and MST methods PDF page 9"),
        ("sabrowski2022_ndm1_h14_01", "NDM1-H14-01", "unmodified", "", "", "", "unmodified parent oligonucleotide", supp_path, "Supplementary Table S2 unmodified row"),
        ("sabrowski2022_ndm1_h14_01", "Bio-NDM1-H14-01", "5p_biotinteg", "/5BiotinTEG/", "5_prime", "TEG", "SPR ligand", supp_path, "Supplementary Table S2; main article Table 1"),
        ("sabrowski2022_ndm1_h14_01", "Cy5-NDM1-H14-01", "5p_cy5", "/5Cy5/", "5_prime", "not_applicable", "MST ligand", supp_path, "Supplementary Table S2; main article Table 1"),
        ("sabrowski2022_ndm1_h14_01_fr", "NDM1-H14-01-FR", "unmodified", "", "", "", "unmodified truncated masking probe", supp_path, "Supplementary Table S2 unmodified row"),
        ("sabrowski2022_ndm1_h14_01_fr", "Bio-NDM1-H14-01-FR", "5p_biotinteg", "/5BiotinTEG/", "5_prime", "TEG", "SPR ligand and HIS-tag masking probe", supp_path, "Supplementary Table S2; main article Table 1"),
        ("sabrowski2022_con1", "Cy5-Con1", "5p_cy5", "/5Cy5/", "5_prime", "not_applicable", "MST unrelated-DNA control", supp_path, "Supplementary Table S2 Cy5-Con1 row"),
        ("sabrowski2022_consc", "Bio-ConSc", "5p_biotinteg", "/5BiotinTEG/", "5_prime", "TEG", "SPR scramble control", supp_path, "Supplementary Table S2 Bio-ConSc row"),
        ("cn108949766b_apnv", "APNV", "unmodified", "", "", "", "unmodified selected aptamer", cn108_path, "Paragraph [0040], SEQ ID NO:1"),
        ("cn108949766b_apnv", "APNV-biotin", "5p_or_unspecified_biotin", "biotin", "not_reported", "not_reported", "SPR assay construct", cn108_path, "Paragraphs [0070]-[0073], PDF page 7; biotinylated aptamer stated, position/linker not reported"),
        ("cn102965377b_seq1", "CN102965377B-SEQ1", "unmodified", "", "", "", "unmodified sequence-listing oligonucleotide", cn102_path, "Sequence listing PDF page 9"),
        ("cn102965377b_seq1", "CN102965377B-SEQ1-biotin", "5p_or_unspecified_biotin", "biotin", "not_reported", "not_reported", "SPR assay construct", cn102_path, "Paragraphs [0091]-[0096], PDF pages 7-8; 10 nM biotinylated aptamer, position/linker not reported"),
    ]
    rows: list[dict[str, str]] = []
    for ref_id, name, suffix, mod5, pos, linker, roles, source, locator in specs:
        ref = by_id[ref_id]
        construct_id = f"{ref_id}__{suffix}"
        rows.append(
            _row(
                CONSTRUCT_COLUMNS,
                {
                    "construct_id": construct_id,
                    "reference_id": ref_id,
                    "nucleotide_sequence_id": ref["nucleotide_sequence_id"],
                    "construct_name": name,
                    "chemistry_label": suffix,
                    "modification_5p": mod5,
                    "modification_3p": "",
                    "modification_position": pos,
                    "modification_linker": linker,
                    "sequence_sha256": ref["sequence_sha256"],
                    "assay_roles": roles,
                    "source_file": source,
                    "source_location": locator,
                    "notes": "",
                },
            )
        )
    rows.sort(key=lambda row: row["construct_id"])
    require_unique([row["construct_id"] for row in rows], label="construct_id")
    return rows


def _measurement(**values: Any) -> dict[str, str]:
    return _row(MEASUREMENT_COLUMNS, values)


def build_measurement_rows(constructs: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    by_name = {row["construct_name"]: row for row in constructs}
    specs = [
        dict(construct="Bio-NDM1-H14-01", assay="SPR", target="NDM-1", variant="HIS-NDM-1", ligand="Bio-NDM1-H14-01", analyte="HIS-NDM-1", kd="4.34e-9", ka="1.30e6", kdis="5.62e-3", call="binder", loc="Table 1, PDF page 4"),
        dict(construct="Bio-NDM1-H14-01", assay="SPR", target="mPD1-HIS", variant="HIS-tagged_mPD1", ligand="Bio-NDM1-H14-01", analyte="mPD1-HIS", kd="9.86e-11", ka="1.40e6", kdis="1.38e-4", call="binder", loc="Table 1, PDF page 4"),
        dict(construct="Bio-NDM1-H14-01", assay="SPR", target="CFHR1-HIS", variant="HIS-tagged_CFHR1", ligand="Bio-NDM1-H14-01", analyte="CFHR1-HIS", kd="4.49e-11", ka="2.79e6", kdis="1.25e-4", call="binder", loc="Table 1, PDF page 4"),
        dict(construct="Cy5-NDM1-H14-01", assay="MST", target="hexa-HIS-peptide", variant="hexa-HIS-peptide", ligand="Cy5-NDM1-H14-01", analyte="hexa-HIS-peptide", kd="2.81e-8", ka="", kdis="", call="binder", loc="Table 1, PDF page 4"),
        dict(construct="Bio-NDM1-H14-01-FR", assay="SPR", target="NDM-1", variant="HIS-NDM-1", ligand="Bio-NDM1-H14-01-FR", analyte="HIS-NDM-1", kd="5.91e-9", ka="1.20e6", kdis="7.11e-3", call="binder", loc="Table 1, PDF page 4"),
        dict(construct="Bio-NDM1-H14-01-FR", assay="SPR", target="mPD1-HIS", variant="HIS-tagged_mPD1", ligand="Bio-NDM1-H14-01-FR", analyte="mPD1-HIS", kd="1.25e-10", ka="1.02e6", kdis="1.28e-4", call="binder", loc="Table 1, PDF page 4"),
        dict(construct="Bio-NDM1-H14-01-FR", assay="SPR", target="CFHR1-HIS", variant="HIS-tagged_CFHR1", ligand="Bio-NDM1-H14-01-FR", analyte="CFHR1-HIS", kd="2.86e-11", ka="4.28e6", kdis="1.22e-4", call="binder", loc="Table 1, PDF page 4"),
        dict(construct="Bio-NDM1-H14.2_43", assay="SPR", target="NDM-1", variant="HIS-NDM-1", ligand="Bio-NDM1-H14.2_43", analyte="HIS-NDM-1", kd="7.45e-7", ka="1.00e3", kdis="7.48e-4", call="binder", loc="Table 2, PDF page 7; Figure 4 PDF page 6"),
        dict(construct="Bio-ConSc", assay="SPR", target="NDM-1", variant="HIS-NDM-1", ligand="Bio-ConSc", analyte="HIS-NDM-1", kd="", ka="", kdis="", call="kinetic_parameters_not_determined_reduced_response", loc="Table 2, PDF page 7; Supplementary Figure S3"),
        dict(construct="Cy5-Con1", assay="MST", target="NDM-1", variant="HIS-NDM-1", ligand="Cy5-Con1", analyte="HIS-NDM-1", kd="", ka="", kdis="", call="no_binding", loc="Table 2, PDF page 7; MST methods PDF page 9"),
        dict(construct="Cy5-NDM1-H14.2_43", assay="MST", target="NDM-1", variant="HIS-NDM-1", ligand="Cy5-NDM1-H14.2_43", analyte="HIS-NDM-1", kd="2.82e-6", ka="", kdis="", call="binder", loc="Table 2, PDF page 7; Figure 4 PDF page 6"),
        dict(construct="Cy5-NDM1-H14.2_43", assay="MST", target="OXA-23", variant="HIS-OXA-23", ligand="Cy5-NDM1-H14.2_43", analyte="HIS-OXA-23", kd="", ka="", kdis="", call="no_binding", loc="Table 2, PDF page 7"),
        dict(construct="Cy5-NDM1-H14.2_43", assay="MST", target="hexa-HIS-peptide", variant="hexa-HIS-peptide", ligand="Cy5-NDM1-H14.2_43", analyte="hexa-HIS-peptide", kd="", ka="", kdis="", call="no_binding", loc="Table 2, PDF page 7"),
        dict(construct="APNV-biotin", assay="SPR", target="NDM-1", variant="", ligand="biotinylated APNV", analyte="NDM-1", kd="8.7e-9", ka="", kdis="", call="binder", loc="CN108949766B paragraphs [0072]-[0073], PDF page 7"),
        dict(construct="APNV-biotin", assay="SPR", target="VIM-2", variant="", ligand="biotinylated APNV", analyte="VIM-2", kd="1.1e-8", ka="", kdis="", call="binder", loc="CN108949766B paragraphs [0072]-[0073], PDF page 7"),
        dict(construct="CN102965377B-SEQ1-biotin", assay="SPR", target="NDM-1", variant="", ligand="biotinylated SEQ ID NO:1", analyte="NDM-1", kd="5e-9", ka="2e8", kdis="", call="binder", loc="CN102965377B paragraphs [0091]-[0096], PDF pages 7-8"),
    ]
    rows: list[dict[str, str]] = []
    for spec in specs:
        construct = by_name[spec["construct"]]
        target_slug = re.sub(r"[^A-Za-z0-9]+", "_", spec["target"]).strip("_").lower()
        measurement_id = f"{construct['construct_id']}__{spec['assay'].lower()}__{target_slug}"
        rows.append(
            _measurement(
                measurement_id=measurement_id,
                construct_id=construct["construct_id"],
                reference_id=construct["reference_id"],
                assay_method=spec["assay"],
                target=spec["target"],
                target_variant=spec["variant"],
                ligand=spec["ligand"],
                analyte=spec["analyte"],
                affinity_type="KD" if spec["kd"] else "",
                affinity_value=spec["kd"],
                affinity_unit="M" if spec["kd"] else "",
                affinity_value_molar=spec["kd"],
                ka_value=spec["ka"],
                ka_unit="1/(M*s)" if spec["ka"] and spec["assay"] == "SPR" and spec["construct"].startswith("Bio-") else ("1/M" if spec["ka"] else ""),
                kd_value=spec["kdis"],
                kd_unit="1/s" if spec["kdis"] else "",
                binding_call=spec["call"],
                source_location=spec["loc"],
                notes="",
            )
        )
    rows.sort(key=lambda row: row["measurement_id"])
    require_unique([row["measurement_id"] for row in rows], label="measurement_id")
    return rows


def leakage_queries(
    references: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    queries: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in references:
        seq = row["sequence"]
        key = sha256_text(seq)
        if key not in seen:
            queries.append(
                {
                    "query_id": row["reference_id"],
                    "query_kind": "canonical_reference_sequence",
                    "sequence": seq,
                }
            )
            seen.add(key)
        if row.get("variant_relationship") == "experimentally_tested_truncation":
            if key not in seen:
                queries.append(
                    {
                        "query_id": row["reference_id"],
                        "query_kind": "source_supported_truncation",
                        "sequence": seq,
                    }
                )
    queries.sort(key=lambda item: item["query_id"])
    return queries


def run_leakage_diagnostics(
    *,
    queries: Sequence[Mapping[str, str]],
    partitions: Mapping[str, Sequence[Mapping[str, str]]],
    threshold: float = IDENTITY_THRESHOLD,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "threshold": threshold,
        "n_queries": len(queries),
        "by_partition": {},
        "flagged_for_human_review": [],
    }
    for partition_name in ("TRAIN", "VALIDATION", "REF", "EVAL"):
        rows = list(partitions.get(partition_name, []))
        partition_result = {
            "n_rows": len(rows),
            "exact_matches": 0,
            "identity_ge_threshold": 0,
            "queries": [],
        }
        prepared: list[dict[str, str]] = []
        for row in rows:
            prepared.append(
                {
                    "scientific_identity_id": row.get("scientific_identity_id", ""),
                    "record_id": row.get("record_id", ""),
                    "sequence_full": comparison_form(row["sequence_full"])
                    if row.get("sequence_full")
                    else "",
                    "sequence_core": comparison_form(row["sequence_core"])
                    if row.get("sequence_core")
                    else "",
                }
            )
        for query in queries:
            query_form = comparison_form(query["sequence"])
            query_row: dict[str, Any] = {
                "query_id": query["query_id"],
                "query_kind": query["query_kind"],
                "query_length": len(query["sequence"]),
            }
            for field in ("sequence_full", "sequence_core"):
                exact = 0
                ge_thr = 0
                best_identity = -1.0
                best_ids: list[tuple[str, str]] = []
                for item in prepared:
                    target = item[field]
                    if not target:
                        continue
                    identity = 1.0 if query_form == target else global_edit_identity(
                        query_form, target
                    )
                    if query_form == target:
                        exact += 1
                    if identity >= threshold:
                        ge_thr += 1
                    key = (item["scientific_identity_id"], item["record_id"])
                    if identity > best_identity:
                        best_identity = identity
                        best_ids = [key]
                    elif identity == best_identity:
                        best_ids.append(key)
                best_ids.sort()
                best = best_ids[0] if best_ids else ("", "")
                field_result = {
                    "n_exact": exact,
                    "n_identity_ge_threshold": ge_thr,
                    "best_identity": None if best_identity < 0 else round(best_identity, 6),
                    "best_scientific_identity_id": best[0],
                    "best_record_id": best[1],
                }
                query_row[field] = field_result
                partition_result["exact_matches"] += exact
                partition_result["identity_ge_threshold"] += ge_thr
                if exact or ge_thr:
                    summary["flagged_for_human_review"].append(
                        {
                            "query_id": query["query_id"],
                            "partition": partition_name,
                            "field": field,
                            "n_exact": exact,
                            "n_identity_ge_threshold": ge_thr,
                        }
                    )
            partition_result["queries"].append(query_row)
        summary["by_partition"][partition_name] = partition_result
    summary["any_exact"] = any(
        part["exact_matches"] for part in summary["by_partition"].values()
    )
    summary["any_identity_ge_threshold"] = any(
        part["identity_ge_threshold"] for part in summary["by_partition"].values()
    )
    return summary


def _status_counts(references: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts = {
        "candidate_or_reference_records": len(references),
        "included_verified_references": 0,
        "needs_human_review": 0,
        "excluded_control": 0,
        "verified": 0,
    }
    for row in references:
        status = row["verification_status"]
        if row["include_in_final_reference_set"] == "true":
            counts["included_verified_references"] += 1
        if status in counts:
            counts[status] += 1
        elif status == "needs_human_review":
            counts["needs_human_review"] += 1
    return counts


def render_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    if scan_text_for_sequence_leak(text):
        raise Ndm1SsdnaError("manifest contains a contiguous nucleotide string of length 20+")
    return payload


def render_report(payload: Mapping[str, Any]) -> str:
    counts = payload["counts"]
    leakage = payload["leakage"]
    lines = [
        "# NDM-1 ssDNA published-reference verification report",
        "",
        "This is a target-specific published-reference audit. It is not a corpus-curation stage.",
        "Nucleotide strings are omitted from this report.",
        "",
        "## Counts",
        "",
        f"- candidate/reference records: `{counts['candidate_or_reference_records']}`",
        f"- included verified references: `{counts['included_verified_references']}`",
        f"- needs_human_review: `{counts['needs_human_review']}`",
        f"- excluded_control: `{counts['excluded_control']}`",
        f"- distinct canonical nucleotide sequences: `{counts['distinct_canonical_nucleotide_sequences']}`",
        f"- experimental constructs: `{counts['experimental_constructs']}`",
        f"- binding measurements: `{counts['binding_measurements']}`",
        "",
        "## Source coverage",
        "",
    ]
    for item in payload["source_coverage"]:
        lines.append(
            f"- `{item['source']}` ({item['publication_type']}): {item['records']}"
        )
    lines.extend(["", "## Per-record status", ""])
    lines.append(
        "| reference_id | role | status | include | length | locator |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in payload["per_record"]:
        lines.append(
            f"| `{row['reference_id']}` | `{row['reference_role']}` | "
            f"`{row['verification_status']}` | `{row['include_in_final_reference_set']}` | "
            f"`{row['sequence_length']}` | {row['source_location']} |"
        )
    lines.extend(
        [
            "",
            "## Modifications",
            "",
            "- Sabrowski labelled constructs: 5-prime BiotinTEG and 5-prime Cy5 as published in Table S2.",
            "- APNV and CN102 biotinylated assay constructs: modification position/linker `not_reported`.",
            "- Canonical `sequence` fields contain no chemical labels.",
            "",
            "## Duplicate and parent/truncation relationships",
            "",
            f"- exact nucleotide duplicates among reference records: `{payload['exact_duplicate_groups']}`",
            "- `sabrowski2022_ndm1_h14_01_fr` is an experimentally tested truncation of `sabrowski2022_ndm1_h14_01`.",
            "- Labelled chemistry variants share `nucleotide_sequence_id` with their parent nucleotide record and remain distinct at construct level.",
            "",
            "## CN102 human-review resolution",
            "",
            "Laura accepted the exact published 88-nt SEQ ID NO:1 listing as authoritative",
            " on 2026-09-22. The contradictory generic library architecture remains documented:",
            f" `{payload['cn102_conflict']['stated_architecture']}` totalling",
            f" `{payload['cn102_conflict']['stated_total_length']}` nt versus listing length",
            f" `{payload['cn102_conflict']['sequence_listing_length']}`; starts with the stated",
            f" 5-prime flank=`{payload['cn102_conflict']['starts_with_stated_5p_flank']}`; ends with",
            f" the stated 3-prime flank=`{payload['cn102_conflict']['ends_with_stated_3p_flank']}`.",
            " No shortening, 3-prime repair, or inferred core was generated.",
            " `verification_status=verified`; `include_in_final_reference_set=true`;",
            " `sequence_discrepancy=source_internal_library_architecture_conflict`;",
            " `human_review_resolution=explicit_sequence_listing_accepted_over_generic_library_architecture`;",
            " reviewer=`Laura`; resolution_date=`2026-09-22`.",
            "",
            "## Leakage diagnostics",
            "",
            f"- comparison form: repository `comparison_form` (U-to-T for matching only); identity threshold = `{leakage['threshold']}`",
            f"- reverse-complement matching: no",
            f"- any exact match: `{leakage['any_exact']}`",
            f"- any identity >= threshold: `{leakage['any_identity_ge_threshold']}`",
            "",
        ]
    )
    for name in ("TRAIN", "VALIDATION", "REF", "EVAL"):
        part = leakage["by_partition"][name]
        lines.append(
            f"- `{name}`: rows=`{part['n_rows']}`; exact=`{part['exact_matches']}`; "
            f">=0.90=`{part['identity_ge_threshold']}`"
        )
    if leakage["flagged_for_human_review"]:
        lines.extend(["", "Unexpected leakage hits were flagged for human review. Frozen partitions were not altered."])
    else:
        lines.extend(["", "No exact or >=0.90 hits were observed against frozen TRAIN, VALIDATION, REF, or EVAL."])
    lines.extend(
        [
            "",
            "## Provenance completeness",
            "",
            f"- verified included records with required provenance: `{payload['provenance_ok']}`",
            f"- additions/overrides sequence comparison matches: `{payload['additions_sequence_matches']}`",
            "",
            "## Hashes",
            "",
            "### Inputs",
            "",
        ]
    )
    for name, digest in sorted(payload["input_hashes"].items()):
        lines.append(f"- `{name}`: `{digest}`")
    lines.extend(["", "### Outputs", ""])
    for name, digest in sorted(payload["output_hashes"].items()):
        lines.append(f"- `{name}`: `{digest}`")
    lines.extend(
        [
            "",
            "## Immutability",
            "",
            f"- frozen files unchanged versus preflight: `{payload['frozen_unchanged']}`",
            f"- raw evidence unchanged versus preflight: `{payload['raw_evidence_unchanged']}`",
            f"- git ls-files data empty: `{payload['git_ls_files_data_empty']}`",
            f"- protected untracked files unchanged: `{payload['protected_untracked_unchanged']}`",
            "",
            "Resource is not marked final. S0b/S7D authorities were not updated.",
        ]
    )
    report = "\n".join(lines) + "\n"
    if scan_text_for_sequence_leak(report):
        raise Ndm1SsdnaError("verification report contains a contiguous nucleotide string of length 20+")
    return report


def load_partitions(
    repo_root: Path, config: Mapping[str, Any]
) -> dict[str, list[dict[str, str]]]:
    loaded: dict[str, list[dict[str, str]]] = {}
    for name, rel in config["frozen_partitions"].items():
        path = repo_root / rel
        loaded[name] = read_csv_rows(path) if path.is_file() else []
    return loaded


def run_ndm1_ssdna_build(
    *,
    config: Mapping[str, Any],
    repo_root: Path | None = None,
    write_outputs: bool = True,
    run_leakage: bool = True,
    sabrowski_extract: Mapping[str, str] | None = None,
    partitions: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    protected = list(config.get("protected_untracked_files") or PROTECTED_UNTRACKED_DEFAULT)
    protected_before = hash_protected_files(root, protected)
    raw_before = collect_raw_source_hashes(root)
    expected_raw = config.get("raw_evidence_immutable_hashes") or {}
    for rel, digest in expected_raw.items():
        observed = raw_before.get(rel)
        if observed != digest:
            raise Ndm1SsdnaError(f"raw evidence hash mismatch before build: {rel}")

    frozen_paths = {
        **config["frozen_partitions"],
        **config["frozen_corpus"],
        "evaluation_references.csv": config["evaluation_references_path"],
    }
    frozen_before = {
        name: sha256_file(root / rel)
        for name, rel in frozen_paths.items()
        if (root / rel).is_file()
    }
    expected_frozen = config.get("expected_frozen_sha256") or {}
    name_to_path = {Path(rel).name: root / rel for rel in frozen_paths.values()}
    for name, digest in expected_frozen.items():
        path = name_to_path.get(name)
        if path is not None and path.is_file() and sha256_file(path) != digest:
            raise Ndm1SsdnaError(f"frozen hash mismatch before build: {name}")

    additions_path = root / config["additions_overrides_path"]
    additions_rows = read_csv_rows(additions_path) if additions_path.is_file() else []
    additions_by_id = {row["reference_id"]: row for row in additions_rows}

    manual_rel = str(config.get("manual_primary_source_evidence_path") or "")
    if not manual_rel:
        raise Ndm1SsdnaError("manual_primary_source_evidence_path is missing from config")
    manual_path = root / manual_rel
    manual_hash_before = sha256_file(manual_path) if manual_path.is_file() else ""
    evidence_rows = load_manual_primary_source_evidence(
        manual_path,
        expected_sha256=str(
            config.get("expected_manual_primary_source_evidence_sha256") or ""
        ),
    )

    supp_spec = config["raw_sources"]["sabrowski_2022_supplementary.pdf"]
    cn108_spec = config["raw_sources"]["CN108949766B_patent.pdf"]
    cn102_spec = config["raw_sources"]["CN102965377B_patent.pdf"]
    if sabrowski_extract is None:
        sabrowski_extract = extract_sabrowski_table_s2(root / supp_spec["path"])
    expected_hashes = config.get("expected_canonical_sequence_sha256") or {}
    expected_lengths = config.get("expected_sequence_lengths") or {}
    apnv_sequence, apnv_method = obtain_apnv_sequence(
        pdf_path=root / cn108_spec["path"],
        evidence_rows=evidence_rows,
        expected_length=int(expected_lengths.get("cn108949766b_apnv") or 35),
        expected_sha256=str(expected_hashes.get("cn108949766b_apnv") or ""),
    )
    cn102_sequence = evidence_sequence(
        evidence_rows,
        reference_id="cn102965377b_seq1",
        evidence_type=EVIDENCE_CN102_LISTING,
        expected_length=int(expected_lengths.get("cn102965377b_seq1") or 88),
        expected_sha256=str(expected_hashes.get("cn102965377b_seq1") or ""),
    )
    cn102_architecture = config["cn102_library_architecture"]
    cn102_conflict = cn102_architecture_conflict(
        cn102_sequence,
        cn102_architecture,
        flank5=evidence_sequence(
            evidence_rows,
            reference_id="cn102965377b_seq1",
            evidence_type=EVIDENCE_CN102_FIXED_5P,
            expected_length=int(cn102_architecture["fixed_5p_length"]),
        ),
        flank3=evidence_sequence(
            evidence_rows,
            reference_id="cn102965377b_seq1",
            evidence_type=EVIDENCE_CN102_FIXED_3P,
            expected_length=int(cn102_architecture["fixed_3p_length"]),
        ),
    )

    source_hashes = {
        spec["path"]: spec["sha256"] for spec in config["raw_sources"].values()
    }
    source_hashes.update(raw_before)

    transcription_rows = build_transcription_rows(
        config=config,
        repo_root=root,
        source_hashes=source_hashes,
        additions_by_id=additions_by_id,
        sabrowski_extract=sabrowski_extract,
        apnv_sequence=apnv_sequence,
        apnv_method=apnv_method,
        cn102_sequence=cn102_sequence,
    )
    nucleotide_tx = {
        row["reference_id"]: row
        for row in transcription_rows
        if row["transcription_id"]
        in {
            "tx_sabrowski2022_ndm1_h14_2_43",
            "tx_sabrowski2022_ndm1_h14_01",
            "tx_sabrowski2022_ndm1_h14_01_fr",
            "tx_sabrowski2022_con1",
            "tx_sabrowski2022_consc",
            "tx_cn108949766b_apnv",
            "tx_cn102965377b_seq1",
        }
    }

    reference_rows = build_reference_rows(
        config=config,
        transcriptions=nucleotide_tx,
        source_hashes=source_hashes,
        cn102_conflict=cn102_conflict,
    )
    for row in reference_rows:
        tx = nucleotide_tx[row["reference_id"]]
        if tx["extraction_method"] != row["source_sequence_verification_method"]:
            raise Ndm1SsdnaError(
                f"{row['reference_id']} source_sequence_verification_method "
                "does not match transcription extraction_method"
            )
        if row["verification_status"] == "verified":
            if tx["sequence_canonical"] != row["sequence"]:
                raise Ndm1SsdnaError(
                    f"verified record {row['reference_id']} does not match transcription"
                )
            required = [
                row["source_file"],
                row["source_file_sha256"],
                row["source_location"],
                row["source_sequence_verification_method"],
            ]
            if any(not item for item in required):
                raise Ndm1SsdnaError(
                    f"verified record {row['reference_id']} is missing provenance"
                )

    construct_rows = build_construct_rows(
        references=reference_rows,
        sabrowski_extract=sabrowski_extract,
        source_hashes=source_hashes,
        supp_path=supp_spec["path"],
        cn108_path=cn108_spec["path"],
        cn102_path=cn102_spec["path"],
    )
    measurement_rows = build_measurement_rows(construct_rows)
    require_unique([row["reference_id"] for row in reference_rows], label="reference_id")
    nt_by_seq = defaultdict(set)
    for row in reference_rows:
        nt_by_seq[row["sequence"]].add(row["nucleotide_sequence_id"])
    for seq, ids in nt_by_seq.items():
        if len(ids) != 1:
            raise Ndm1SsdnaError("nucleotide_sequence_id is not a pure function of sequence")
    duplicates = exact_sequence_duplicates(reference_rows)
    parent = next(
        row for row in reference_rows if row["reference_id"] == "sabrowski2022_ndm1_h14_01_fr"
    )
    if parent["parent_reference_id"] != "sabrowski2022_ndm1_h14_01":
        raise Ndm1SsdnaError("H14-01-FR parent relationship was not preserved")
    if parent["variant_relationship"] != "experimentally_tested_truncation":
        raise Ndm1SsdnaError("H14-01-FR variant relationship was not preserved")

    partition_rows = partitions if partitions is not None else load_partitions(root, config)
    leakage = (
        run_leakage_diagnostics(
            queries=leakage_queries(reference_rows),
            partitions=partition_rows,
            threshold=float(config.get("identity_threshold", IDENTITY_THRESHOLD)),
        )
        if run_leakage
        else {
            "threshold": float(config.get("identity_threshold", IDENTITY_THRESHOLD)),
            "n_queries": 0,
            "by_partition": {
                name: {"n_rows": 0, "exact_matches": 0, "identity_ge_threshold": 0, "queries": []}
                for name in ("TRAIN", "VALIDATION", "REF", "EVAL")
            },
            "flagged_for_human_review": [],
            "any_exact": False,
            "any_identity_ge_threshold": False,
            "skipped": True,
        }
    )

    counts = _status_counts(reference_rows)
    counts["distinct_canonical_nucleotide_sequences"] = len(
        {row["nucleotide_sequence_id"] for row in reference_rows}
    )
    counts["experimental_constructs"] = len(construct_rows)
    counts["binding_measurements"] = len(measurement_rows)
    expected_counts = config.get("expected_counts") or {}
    for key, wanted in expected_counts.items():
        if counts.get(key) != wanted:
            raise Ndm1SsdnaError(f"count mismatch for {key}: {counts.get(key)} != {wanted}")
    additions_matches = [
        row
        for row in transcription_rows
        if row["transcription_id"].startswith("tx_")
        and row["reference_id"] in CANDIDATE_REFERENCE_IDS
        and row["construct_name"]
        in {
            "NDM1-H14.2_43",
            "NDM1-H14-01",
            "NDM1-H14-01-FR",
            "APNV",
            "CN102965377B SEQ ID NO:1",
        }
        and row["matches_additions_sequence_raw"] == "true"
    ]

    output_dir = root / config["output_dir"]
    transcription_path = root / config["transcription_path"]
    outputs = {
        "ndm1_ssdna_aptamer_references.csv": output_dir / "ndm1_ssdna_aptamer_references.csv",
        "ndm1_ssdna_experimental_constructs.csv": output_dir / "ndm1_ssdna_experimental_constructs.csv",
        "ndm1_ssdna_binding_measurements.csv": output_dir / "ndm1_ssdna_binding_measurements.csv",
        "ndm1_ssdna_reference_manifest.json": output_dir / "ndm1_ssdna_reference_manifest.json",
        "ndm1_ssdna_reference_verification_report.md": output_dir
        / "ndm1_ssdna_reference_verification_report.md",
        "ndm1_ssdna_primary_source_transcriptions.csv": transcription_path,
    }
    if transcription_path.resolve() == manual_path.resolve():
        raise Ndm1SsdnaError("builder must not treat the manual-evidence input as an output")

    per_record = [
        {
            "reference_id": row["reference_id"],
            "reference_role": row["reference_role"],
            "verification_status": row["verification_status"],
            "include_in_final_reference_set": row["include_in_final_reference_set"],
            "sequence_length": row["sequence_length"],
            "source_location": row["source_location"],
            "parent_reference_id": row["parent_reference_id"],
            "variant_relationship": row["variant_relationship"],
            "sequence_discrepancy": row["sequence_discrepancy"],
            "human_review_resolution": row.get("human_review_resolution", ""),
            "human_reviewer": row.get("human_reviewer", ""),
            "human_review_resolution_date": row.get("human_review_resolution_date", ""),
        }
        for row in reference_rows
    ]
    source_coverage = [
        {
            "source": "Sabrowski et al. 2022",
            "publication_type": "journal_article_plus_supplement",
            "records": "NDM1-H14.2_43, NDM1-H14-01, NDM1-H14-01-FR, Con1, ConSc",
        },
        {
            "source": "CN108949766B",
            "publication_type": "patent",
            "records": "APNV",
        },
        {
            "source": "CN102965377B",
            "publication_type": "patent",
            "records": "SEQ ID NO:1",
        },
    ]
    report_payload = {
        "counts": counts,
        "source_coverage": source_coverage,
        "per_record": per_record,
        "exact_duplicate_groups": len(duplicates),
        "cn102_conflict": {
            "stated_architecture": cn102_conflict["stated_architecture"],
            "stated_total_length": cn102_conflict["stated_total_length"],
            "sequence_listing_length": cn102_conflict["sequence_listing_length"],
            "starts_with_stated_5p_flank": cn102_conflict["starts_with_stated_5p_flank"],
            "ends_with_stated_3p_flank": cn102_conflict["ends_with_stated_3p_flank"],
            "human_review_resolution": cn102_conflict.get("human_review_resolution", ""),
        },
        "leakage": leakage,
        "provenance_ok": True,
        "additions_sequence_matches": len(additions_matches) == 5,
        "input_hashes": {
            **{Path(k).name: v for k, v in expected_raw.items()},
            **frozen_before,
            Path(manual_rel).name: manual_hash_before,
        },
        "output_hashes": {},
        "frozen_unchanged": True,
        "raw_evidence_unchanged": True,
        "git_ls_files_data_empty": git_ls_files_data(root) == "",
        "protected_untracked_unchanged": True,
    }

    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)
        transcription_path.parent.mkdir(parents=True, exist_ok=True)
        if transcription_path.resolve() == manual_path.resolve():
            raise Ndm1SsdnaError("refusing to overwrite the manual-evidence input")
        _atomic_write_csv(transcription_path, TRANSCRIPTION_COLUMNS, transcription_rows)
        _atomic_write_csv(
            outputs["ndm1_ssdna_aptamer_references.csv"],
            REFERENCE_COLUMNS,
            reference_rows,
        )
        _atomic_write_csv(
            outputs["ndm1_ssdna_experimental_constructs.csv"],
            CONSTRUCT_COLUMNS,
            construct_rows,
        )
        _atomic_write_csv(
            outputs["ndm1_ssdna_binding_measurements.csv"],
            MEASUREMENT_COLUMNS,
            measurement_rows,
        )

    output_hashes = {}
    if write_outputs:
        for name, path in outputs.items():
            if path.suffix == ".md" or path.suffix == ".json":
                continue
            output_hashes[path.name] = sha256_file(path)
    report_payload["output_hashes"] = output_hashes
    report_text = render_report(report_payload)
    manifest = render_manifest(
        {
            "contract_id": config.get("contract_id"),
            "milestone": config.get("milestone"),
            "build_date": config.get("build_date"),
            "repository_head_baseline": config.get("repository_head_baseline"),
            "counts": counts,
            "per_record": per_record,
            "source_coverage": source_coverage,
            "cn102_conflict": report_payload["cn102_conflict"],
            "leakage": {
                "threshold": leakage["threshold"],
                "any_exact": leakage["any_exact"],
                "any_identity_ge_threshold": leakage["any_identity_ge_threshold"],
                "flagged_for_human_review": leakage["flagged_for_human_review"],
                "by_partition": {
                    name: {
                        "n_rows": part["n_rows"],
                        "exact_matches": part["exact_matches"],
                        "identity_ge_threshold": part["identity_ge_threshold"],
                    }
                    for name, part in leakage["by_partition"].items()
                },
            },
            "input_hashes": report_payload["input_hashes"],
            "output_hashes": output_hashes,
            "frozen_unchanged": True,
            "raw_evidence_unchanged": True,
            "git_ls_files_data_empty": report_payload["git_ls_files_data_empty"],
            "resource_marked_final": False,
            "s0b_or_s7d_authorities_updated": False,
        }
    )
    if write_outputs:
        write_text_atomic(outputs["ndm1_ssdna_reference_verification_report.md"], report_text)
        write_json_atomic(outputs["ndm1_ssdna_reference_manifest.json"], manifest)
        output_hashes[outputs["ndm1_ssdna_reference_verification_report.md"].name] = sha256_file(
            outputs["ndm1_ssdna_reference_verification_report.md"]
        )
        output_hashes[outputs["ndm1_ssdna_reference_manifest.json"].name] = sha256_file(
            outputs["ndm1_ssdna_reference_manifest.json"]
        )
        leaked = scan_paths_for_sequence_leak(
            [
                outputs["ndm1_ssdna_reference_verification_report.md"],
                outputs["ndm1_ssdna_reference_manifest.json"],
            ]
        )
        if leaked:
            raise Ndm1SsdnaError("sequence-free outputs unexpectedly contain nucleotide strings")

    raw_after = collect_raw_source_hashes(root)
    if raw_after != raw_before:
        raise Ndm1SsdnaError("raw evaluation-reference evidence changed during the build")
    frozen_after = {
        name: sha256_file(root / rel)
        for name, rel in frozen_paths.items()
        if (root / rel).is_file()
    }
    if frozen_after != frozen_before:
        raise Ndm1SsdnaError("frozen corpus or evaluation_references.csv changed during the build")
    protected_after = hash_protected_files(root, protected)
    if protected_after != protected_before:
        raise Ndm1SsdnaError("protected untracked files changed during the build")
    if git_ls_files_data(root) != "":
        raise Ndm1SsdnaError("git ls-files data is no longer empty")
    if not manual_path.is_file() or sha256_file(manual_path) != manual_hash_before:
        raise Ndm1SsdnaError("manual-evidence input was overwritten")

    return {
        "ok": True,
        "counts": counts,
        "references": reference_rows,
        "constructs": construct_rows,
        "measurements": measurement_rows,
        "transcriptions": transcription_rows,
        "leakage": leakage,
        "cn102_conflict": cn102_conflict,
        "report": report_text,
        "manifest": manifest,
        "output_hashes": output_hashes,
        "input_hashes": report_payload["input_hashes"],
        "frozen_unchanged": True,
        "raw_evidence_unchanged": True,
        "git_ls_files_data_empty": True,
        "additions_sequence_matches": len(additions_matches) == 5,
    }

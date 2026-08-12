"""UTexas S1 adapter: verbatim extraction into the canonical corpus schema.

Reads the registry-bound September 2023 workbook via stdlib ZIP/XML so that
all physically represented sheetData rows are retained (including blank
trailing rows that dataframe readers may drop). Does not perform S2
normalisation, filtering, trimming, molecule inference, affinity
interpretation, or deduplication.
"""

from __future__ import annotations

import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from common.corpus_schema import (
    empty_corpus_record,
    validate_s1_record,
    write_corpus_csv_atomic,
)

# Exact header strings from the registered workbook (trailing spaces / newlines
# are part of the source schema and must be matched character-for-character).
UTEXAS_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    "Year of Paper",
    "Link to PubMed Entry",
    "Journals",
    "Journal DOI",
    "Citation",
    "Type of Nucleic Acid",
    "Name of Aptamer",
    "Target ",
    "Aptamer Sequence",
    "Sequence Length",
    "GC Content ",
    "Affinity",
    "Kd (nM)",
    "Pool Type",
    "Pool Random Region ",
    "Binding Buffer/Conditions",
    "Divalent Salt ",
    "Type of the buffer",
    "pH",
    "Molecular weight of target",
    "Application as quoted in the referenced paper",
    "Post-selex modifications to the aptamer",
    "Additional Information\n\n",
    "Serial Number",
    "Parent sequence serial number",
    "Corresponding Author Name, email address",
    "please fill out the form for any feedbacks/comments",
    "Aptagen Cross Referencing(Check  Aptamer Chemistry, Affinity, Length, GC content, sequence)",
)

SIDECAR_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "utexas_worksheet_row",
    "utexas_year_of_paper",
    "utexas_link_to_pubmed_entry",
    "utexas_journals",
    "utexas_journal_doi",
    "utexas_citation",
    "utexas_type_of_nucleic_acid",
    "utexas_name_of_aptamer",
    "utexas_target",
    "utexas_aptamer_sequence",
    "utexas_sequence_length",
    "utexas_gc_content",
    "utexas_affinity",
    "utexas_kd_nm",
    "utexas_pool_type",
    "utexas_pool_random_region",
    "utexas_binding_buffer_conditions",
    "utexas_divalent_salt",
    "utexas_type_of_the_buffer",
    "utexas_ph",
    "utexas_molecular_weight_of_target",
    "utexas_application_as_quoted",
    "utexas_post_selex_modifications",
    "utexas_additional_information",
    "utexas_serial_number",
    "utexas_parent_sequence_serial_number",
    "utexas_corresponding_author",
    "utexas_feedback_comments",
    "utexas_aptagen_cross_referencing",
)

_SOURCE_TO_SIDECAR: Final[tuple[tuple[str, str], ...]] = (
    ("Year of Paper", "utexas_year_of_paper"),
    ("Link to PubMed Entry", "utexas_link_to_pubmed_entry"),
    ("Journals", "utexas_journals"),
    ("Journal DOI", "utexas_journal_doi"),
    ("Citation", "utexas_citation"),
    ("Type of Nucleic Acid", "utexas_type_of_nucleic_acid"),
    ("Name of Aptamer", "utexas_name_of_aptamer"),
    ("Target ", "utexas_target"),
    ("Aptamer Sequence", "utexas_aptamer_sequence"),
    ("Sequence Length", "utexas_sequence_length"),
    ("GC Content ", "utexas_gc_content"),
    ("Affinity", "utexas_affinity"),
    ("Kd (nM)", "utexas_kd_nm"),
    ("Pool Type", "utexas_pool_type"),
    ("Pool Random Region ", "utexas_pool_random_region"),
    ("Binding Buffer/Conditions", "utexas_binding_buffer_conditions"),
    ("Divalent Salt ", "utexas_divalent_salt"),
    ("Type of the buffer", "utexas_type_of_the_buffer"),
    ("pH", "utexas_ph"),
    ("Molecular weight of target", "utexas_molecular_weight_of_target"),
    (
        "Application as quoted in the referenced paper",
        "utexas_application_as_quoted",
    ),
    (
        "Post-selex modifications to the aptamer",
        "utexas_post_selex_modifications",
    ),
    ("Additional Information\n\n", "utexas_additional_information"),
    ("Serial Number", "utexas_serial_number"),
    (
        "Parent sequence serial number",
        "utexas_parent_sequence_serial_number",
    ),
    (
        "Corresponding Author Name, email address",
        "utexas_corresponding_author",
    ),
    (
        "please fill out the form for any feedbacks/comments",
        "utexas_feedback_comments",
    ),
    (
        "Aptagen Cross Referencing(Check  Aptamer Chemistry, Affinity, Length, GC content, sequence)",
        "utexas_aptagen_cross_referencing",
    ),
)

EXPECTED_INPUT_ROWS: Final[int] = 1894
EXPECTED_NONEMPTY_SEQUENCES: Final[int] = 1495
EXPECTED_MISSING_SEQUENCES: Final[int] = 399
EXPECTED_NONEMPTY_TARGETS: Final[int] = 1495
EXPECTED_MISSING_TARGETS: Final[int] = 399
EXPECTED_DUPLICATE_SERIAL_KEYS: Final[int] = 45
EXPECTED_ROWS_IN_DUPLICATE_SERIAL_GROUPS: Final[int] = 96
EXPECTED_POPULATED_SERIALS: Final[int] = 1495
EXPECTED_UNIQUE_SERIALS: Final[int] = 1444
EXPECTED_BLANK_SERIALS: Final[int] = 399

SHEET_NAME: Final[str] = "Dataset"
NATIVE_ID_WIDTH: Final[int] = 4
SOURCE_DB: Final[str] = "utexas"

_OOXML_NS: Final[dict[str, str]] = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
}
_REL_ID_ATTR: Final[str] = (
    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
)

# Deterministic PMID extraction from PubMed URLs or a bare numeric token.
_PMID_URL_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:https?://)?(?:www\.)?pubmed\.ncbi\.nlm\.nih\.gov/(?:pubmed/)?"
    r"(?P<pmid>\d+)\b"
)
_PMID_BARE_RE: Final[re.Pattern[str]] = re.compile(r"^\d{1,9}$")


class UTexasAdapterError(ValueError):
    """Hard failure while validating or extracting the UTexas source."""


@dataclass
class UTexasExtractionStats:
    """Aggregate counts for the UTexas S1 report (no sequence values)."""

    input_rows: int = 0
    canonical_rows: int = 0
    sidecar_rows: int = 0
    unique_native_ids: int = 0
    unique_record_ids: int = 0
    nonempty_sequences: int = 0
    missing_sequences: int = 0
    nonempty_targets: int = 0
    missing_targets: int = 0
    nonempty_publication: int = 0
    nonempty_doi: int = 0
    nonempty_pmid: int = 0
    populated_serials: int = 0
    unique_serials: int = 0
    duplicate_serial_keys: int = 0
    rows_in_duplicate_serial_groups: int = 0
    blank_serials: int = 0
    sequence_exact_copy_ok: bool = False
    target_exact_copy_ok: bool = False
    order_preserved: bool = False
    sheet_name: str = SHEET_NAME
    native_id_strategy: str = (
        "excel_worksheet_row (row_{NNNN} from sheetData @r; "
        "Serial Number retained only in sidecar)"
    )


@dataclass
class UTexasSourceRow:
    """One physically represented worksheet data row."""

    worksheet_row: int
    values: dict[str, str]


@dataclass
class UTexasExtractionResult:
    """Canonical rows, sidecar rows, and aggregate extraction statistics."""

    canonical_rows: list[dict[str, str]]
    sidecar_rows: list[dict[str, str]]
    stats: UTexasExtractionStats = field(default_factory=UTexasExtractionStats)


def format_native_id(worksheet_row: int, *, width: int = NATIVE_ID_WIDTH) -> str:
    """Format a worksheet row number as the deterministic UTexas native_id."""
    if worksheet_row < 1:
        raise UTexasAdapterError(
            f"worksheet_row must be a positive Excel row number; got {worksheet_row}"
        )
    return f"row_{worksheet_row:0{width}d}"


def encode_aptamer_name_notes(aptamer_name: str) -> str:
    """Encode a nonempty aptamer name as deterministic JSON for ``notes``."""
    if aptamer_name == "":
        return ""
    return json.dumps(
        {"aptamer_name": aptamer_name},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def extract_pubmed_id(raw_value: str) -> str:
    """Return a numeric PMID when it can be extracted deterministically.

    Accepts a bare numeric token or a PubMed URL. Otherwise returns ``\"\"``
    without attempting network lookup or scientific interpretation.
    """
    if raw_value == "":
        return ""
    stripped = raw_value.strip()
    if _PMID_BARE_RE.fullmatch(stripped):
        return stripped
    match = _PMID_URL_RE.search(raw_value)
    if match is not None:
        return match.group("pmid")
    return ""


def validate_utexas_header(fieldnames: Sequence[str] | None) -> None:
    """Hard-fail on missing, extra, reordered, duplicate, or blank headers."""
    if fieldnames is None:
        raise UTexasAdapterError("UTexas input has no header row")

    actual = list(fieldnames)
    if any(name == "" for name in actual):
        raise UTexasAdapterError("UTexas input has a blank header column")
    if len(actual) != len(set(actual)):
        raise UTexasAdapterError("UTexas input has duplicate header columns")
    expected = list(UTEXAS_INPUT_COLUMNS)
    if actual != expected:
        if set(actual) != set(expected):
            missing = [c for c in expected if c not in actual]
            extra = [c for c in actual if c not in expected]
            parts: list[str] = []
            if missing:
                parts.append(f"missing={missing!r}")
            if extra:
                parts.append(f"extra={extra!r}")
            raise UTexasAdapterError(
                "UTexas input columns do not match the required schema; "
                + "; ".join(parts)
            )
        raise UTexasAdapterError(
            "UTexas input columns are reordered relative to the required schema"
        )


def _col_letters(cell_ref: str) -> str:
    return "".join(ch for ch in cell_ref if ch.isalpha())


def _load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    names = zf.namelist()
    if "xl/sharedStrings.xml" not in names:
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    shared: list[str] = []
    for si in root.findall("m:si", _OOXML_NS):
        shared.append(
            "".join(t.text or "" for t in si.findall(".//m:t", _OOXML_NS))
        )
    return shared


def _select_first_sheet_path(zf: zipfile.ZipFile) -> str:
    names = zf.namelist()
    sheet_paths = sorted(
        n
        for n in names
        if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
    )
    if not sheet_paths:
        raise UTexasAdapterError("UTexas workbook has no worksheets")
    selected = sheet_paths[0]
    if "xl/workbook.xml" not in names:
        return selected
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    sheets = wb.findall("m:sheets/m:sheet", _OOXML_NS)
    if not sheets:
        return selected
    rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root
        if "Id" in rel.attrib and "Target" in rel.attrib
    }
    rid = sheets[0].attrib.get(_REL_ID_ATTR)
    target = rid_to_target.get(rid or "")
    if not target:
        return selected
    if not target.startswith("xl/"):
        target = "xl/" + target.lstrip("/")
    if target not in names:
        return selected
    return target


def _first_sheet_name(zf: zipfile.ZipFile) -> str:
    if "xl/workbook.xml" not in zf.namelist():
        return SHEET_NAME
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    sheets = wb.findall("m:sheets/m:sheet", _OOXML_NS)
    if not sheets:
        return SHEET_NAME
    return sheets[0].attrib.get("name") or SHEET_NAME


def _cell_value(cell: ET.Element, shared: Sequence[str]) -> str | None:
    """Return the raw stored cell value, or None if the cell has no value."""
    cell_type = cell.attrib.get("t")
    value_elem = cell.find("m:v", _OOXML_NS)
    if value_elem is None or value_elem.text is None:
        inline = cell.find("m:is", _OOXML_NS)
        if inline is not None:
            return "".join(
                t.text or "" for t in inline.findall(".//m:t", _OOXML_NS)
            )
        return None
    if cell_type == "s":
        return shared[int(value_elem.text)]
    # Preserve the literal XML text for numbers/booleans/strings.
    return value_elem.text


def read_utexas_rows(path: Path) -> tuple[list[UTexasSourceRow], str]:
    """Read all physical sheetData data rows from the UTexas workbook.

    Returns ``(rows, sheet_name)``. Row identity uses the Excel ``r`` attribute
    on each sheetData row element. Completely absent worksheet row numbers
    (gaps in sheetData) are not fabricated. Empty but present rows are kept.
    """
    if path.name.startswith("~$"):
        raise UTexasAdapterError(
            f"Excel lock/temp file is not a valid UTexas input: {path.name}"
        )
    try:
        with zipfile.ZipFile(path, "r") as zf:
            shared = _load_shared_strings(zf)
            sheet_name = _first_sheet_name(zf)
            sheet_path = _select_first_sheet_path(zf)
            sheet_root = ET.fromstring(zf.read(sheet_path))
            xml_rows = sheet_root.findall("m:sheetData/m:row", _OOXML_NS)
            if not xml_rows:
                raise UTexasAdapterError(
                    "UTexas worksheet has no sheetData rows"
                )

            header_row = xml_rows[0]
            header_cells: dict[str, str] = {}
            for cell in header_row.findall("m:c", _OOXML_NS):
                ref = cell.attrib.get("r", "")
                letters = _col_letters(ref)
                value = _cell_value(cell, shared)
                header_cells[letters] = "" if value is None else value

            # Reconstruct header order by Excel column letters A..AB.
            ordered_cols = sorted(
                header_cells.keys(),
                key=lambda letters: (
                    len(letters),
                    letters,
                ),
            )
            headers = [header_cells[col] for col in ordered_cols]
            validate_utexas_header(headers)
            col_to_header = {
                col: header_cells[col] for col in ordered_cols
            }

            source_rows: list[UTexasSourceRow] = []
            seen_worksheet_rows: set[int] = set()
            for xml_row in xml_rows[1:]:
                row_attr = xml_row.attrib.get("r")
                if row_attr is None or not row_attr.isdigit():
                    raise UTexasAdapterError(
                        f"UTexas sheetData row is missing a numeric r "
                        f"attribute: {row_attr!r}"
                    )
                worksheet_row = int(row_attr)
                if worksheet_row in seen_worksheet_rows:
                    raise UTexasAdapterError(
                        f"Duplicate worksheet row attribute: {worksheet_row}"
                    )
                seen_worksheet_rows.add(worksheet_row)

                values = {header: "" for header in UTEXAS_INPUT_COLUMNS}
                for cell in xml_row.findall("m:c", _OOXML_NS):
                    letters = _col_letters(cell.attrib.get("r", ""))
                    header = col_to_header.get(letters)
                    if header is None:
                        continue
                    raw = _cell_value(cell, shared)
                    values[header] = "" if raw is None else raw
                source_rows.append(
                    UTexasSourceRow(
                        worksheet_row=worksheet_row,
                        values=values,
                    )
                )
    except zipfile.BadZipFile as exc:
        raise UTexasAdapterError(
            f"UTexas workbook is not a valid ZIP/OOXML file: {path.name}"
        ) from exc
    except ET.ParseError as exc:
        raise UTexasAdapterError(
            f"UTexas worksheet XML could not be parsed: {path.name}"
        ) from exc

    if not source_rows:
        raise UTexasAdapterError("UTexas workbook contains no data rows")
    return source_rows, sheet_name


def map_utexas_row(
    source_row: UTexasSourceRow,
    *,
    source_dataset: str,
    redistribution_status: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Map one source row to canonical + sidecar records."""
    native_id = format_native_id(source_row.worksheet_row)
    canonical_id = f"{SOURCE_DB}:{native_id}"
    values = source_row.values
    sequence_raw = values["Aptamer Sequence"]
    target_raw = values["Target "]
    pubmed_raw = values["Link to PubMed Entry"]

    record = empty_corpus_record()
    record["record_id"] = canonical_id
    record["sequence_raw"] = sequence_raw
    record["source_db"] = SOURCE_DB
    record["source_dataset"] = source_dataset
    record["contributing_sources"] = SOURCE_DB
    record["contributing_datasets"] = source_dataset
    record["corroboration_count"] = "1"
    record["redistribution_status"] = redistribution_status
    record["independently_attested_by_permissive_source"] = "false"
    record["native_id"] = native_id
    record["target_name_raw"] = target_raw
    record["publication"] = values["Citation"]
    record["doi"] = values["Journal DOI"]
    record["pubmed_id"] = extract_pubmed_id(pubmed_raw)
    record["notes"] = encode_aptamer_name_notes(values["Name of Aptamer"])

    validated = validate_s1_record(record)

    sidecar: dict[str, str] = {
        "record_id": canonical_id,
        "utexas_worksheet_row": str(source_row.worksheet_row),
    }
    for source_col, sidecar_col in _SOURCE_TO_SIDECAR:
        sidecar[sidecar_col] = values[source_col]

    return validated, sidecar


def extract_utexas(
    input_path: Path,
    *,
    source_dataset: str,
    redistribution_status: str,
    expected_rows: int | None = EXPECTED_INPUT_ROWS,
) -> UTexasExtractionResult:
    """Extract all UTexas physical rows into canonical and sidecar tables.

    ``expected_rows`` is the registry ``n_rows_expected``. When it equals the
    frozen production snapshot size (1894), known nonempty/missing audits for
    sequences, targets and Serial Number duplication are also enforced.
    """
    source_rows, sheet_name = read_utexas_rows(input_path)
    if expected_rows is not None and len(source_rows) != expected_rows:
        raise UTexasAdapterError(
            f"UTexas input row count must be {expected_rows}; "
            f"got {len(source_rows)}"
        )

    canonical_rows: list[dict[str, str]] = []
    sidecar_rows: list[dict[str, str]] = []
    stats = UTexasExtractionStats()
    stats.input_rows = len(source_rows)
    stats.sheet_name = sheet_name
    stats.order_preserved = True
    sequence_exact = True
    target_exact = True

    native_ids: list[str] = []
    record_ids: list[str] = []
    serials: list[str] = []

    for source_row in source_rows:
        canonical, sidecar = map_utexas_row(
            source_row,
            source_dataset=source_dataset,
            redistribution_status=redistribution_status,
        )
        src_seq = source_row.values["Aptamer Sequence"]
        src_target = source_row.values["Target "]
        if canonical["sequence_raw"] != src_seq:
            sequence_exact = False
        if sidecar["utexas_aptamer_sequence"] != src_seq:
            sequence_exact = False
        if canonical["sequence_raw"] != sidecar["utexas_aptamer_sequence"]:
            sequence_exact = False
        if canonical["target_name_raw"] != src_target:
            target_exact = False
        if sidecar["utexas_target"] != src_target:
            target_exact = False
        if canonical["target_name_raw"] != sidecar["utexas_target"]:
            target_exact = False

        if canonical["sequence_raw"] == "":
            stats.missing_sequences += 1
        else:
            stats.nonempty_sequences += 1
        if canonical["target_name_raw"] == "":
            stats.missing_targets += 1
        else:
            stats.nonempty_targets += 1
        if canonical["publication"] != "":
            stats.nonempty_publication += 1
        if canonical["doi"] != "":
            stats.nonempty_doi += 1
        if canonical["pubmed_id"] != "":
            stats.nonempty_pmid += 1

        serials.append(source_row.values["Serial Number"])
        native_ids.append(canonical["native_id"])
        record_ids.append(canonical["record_id"])
        canonical_rows.append(canonical)
        sidecar_rows.append(sidecar)

    populated = [s for s in serials if s != ""]
    serial_counts = Counter(populated)
    duplicate_keys = {k: v for k, v in serial_counts.items() if v > 1}

    stats.canonical_rows = len(canonical_rows)
    stats.sidecar_rows = len(sidecar_rows)
    stats.unique_native_ids = len(set(native_ids))
    stats.unique_record_ids = len(set(record_ids))
    stats.populated_serials = len(populated)
    stats.unique_serials = len(serial_counts)
    stats.duplicate_serial_keys = len(duplicate_keys)
    stats.rows_in_duplicate_serial_groups = sum(duplicate_keys.values())
    stats.blank_serials = sum(1 for s in serials if s == "")
    stats.sequence_exact_copy_ok = sequence_exact
    stats.target_exact_copy_ok = target_exact

    _assert_extraction_invariants(stats, expected_rows=expected_rows)

    return UTexasExtractionResult(
        canonical_rows=canonical_rows,
        sidecar_rows=sidecar_rows,
        stats=stats,
    )


def _assert_extraction_invariants(
    stats: UTexasExtractionStats,
    *,
    expected_rows: int | None,
) -> None:
    """Hard-fail unless S1 retention and identity invariants hold."""
    n = stats.input_rows
    if expected_rows is not None and n != expected_rows:
        raise UTexasAdapterError(
            f"input_rows must be {expected_rows}; got {n}"
        )
    if stats.canonical_rows != n:
        raise UTexasAdapterError(
            f"canonical_rows ({stats.canonical_rows}) != input_rows ({n})"
        )
    if stats.sidecar_rows != n:
        raise UTexasAdapterError(
            f"sidecar_rows ({stats.sidecar_rows}) != input_rows ({n})"
        )
    if stats.unique_native_ids != n:
        raise UTexasAdapterError(
            f"unique_native_ids ({stats.unique_native_ids}) != input_rows ({n})"
        )
    if stats.unique_record_ids != n:
        raise UTexasAdapterError(
            f"unique_record_ids ({stats.unique_record_ids}) != input_rows ({n})"
        )
    if not stats.sequence_exact_copy_ok:
        raise UTexasAdapterError("sequence_raw exact-copy validation failed")
    if not stats.target_exact_copy_ok:
        raise UTexasAdapterError("target_name_raw exact-copy validation failed")
    if not stats.order_preserved:
        raise UTexasAdapterError("input order was not preserved")

    if expected_rows == EXPECTED_INPUT_ROWS:
        if stats.nonempty_sequences != EXPECTED_NONEMPTY_SEQUENCES:
            raise UTexasAdapterError(
                f"nonempty sequence_raw must be {EXPECTED_NONEMPTY_SEQUENCES}; "
                f"got {stats.nonempty_sequences}"
            )
        if stats.missing_sequences != EXPECTED_MISSING_SEQUENCES:
            raise UTexasAdapterError(
                f"missing sequence_raw must be {EXPECTED_MISSING_SEQUENCES}; "
                f"got {stats.missing_sequences}"
            )
        if stats.nonempty_targets != EXPECTED_NONEMPTY_TARGETS:
            raise UTexasAdapterError(
                f"nonempty target_name_raw must be {EXPECTED_NONEMPTY_TARGETS}; "
                f"got {stats.nonempty_targets}"
            )
        if stats.missing_targets != EXPECTED_MISSING_TARGETS:
            raise UTexasAdapterError(
                f"missing target_name_raw must be {EXPECTED_MISSING_TARGETS}; "
                f"got {stats.missing_targets}"
            )
        if stats.populated_serials != EXPECTED_POPULATED_SERIALS:
            raise UTexasAdapterError(
                f"populated Serial Number must be {EXPECTED_POPULATED_SERIALS}; "
                f"got {stats.populated_serials}"
            )
        if stats.unique_serials != EXPECTED_UNIQUE_SERIALS:
            raise UTexasAdapterError(
                f"unique Serial Number must be {EXPECTED_UNIQUE_SERIALS}; "
                f"got {stats.unique_serials}"
            )
        if stats.duplicate_serial_keys != EXPECTED_DUPLICATE_SERIAL_KEYS:
            raise UTexasAdapterError(
                "duplicate Serial Number keys must be "
                f"{EXPECTED_DUPLICATE_SERIAL_KEYS}; "
                f"got {stats.duplicate_serial_keys}"
            )
        if (
            stats.rows_in_duplicate_serial_groups
            != EXPECTED_ROWS_IN_DUPLICATE_SERIAL_GROUPS
        ):
            raise UTexasAdapterError(
                "rows in duplicate Serial Number groups must be "
                f"{EXPECTED_ROWS_IN_DUPLICATE_SERIAL_GROUPS}; "
                f"got {stats.rows_in_duplicate_serial_groups}"
            )
        if stats.blank_serials != EXPECTED_BLANK_SERIALS:
            raise UTexasAdapterError(
                f"blank Serial Number must be {EXPECTED_BLANK_SERIALS}; "
                f"got {stats.blank_serials}"
            )


def write_sidecar_csv_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Atomically write the UTexas source-metadata sidecar."""
    write_corpus_csv_atomic(path, rows, columns=SIDECAR_COLUMNS)

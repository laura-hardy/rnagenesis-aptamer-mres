"""Parse AptaBase HTML search pages into raw tabular records.

The AptaBase result pages are server-rendered HTML. Each aptamer is one
``<tr>`` in the main results table with ten ``<td>`` cells. This module
extracts those cells without normalising scientific content so that the
raw CSV preserves website values as closely as possible.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
import pandas as pd

logger = logging.getLogger(__name__)

EXPECTED_HEADERS = [
    "#",
    "Aptamer Name",
    "Aptamer Target (General)",
    "Aptamer Target (Specific)",
    "Length",
    "Affinity",
    "Buffer",
    "GC Content",
    "Sequence",
    "Reference",
]

RAW_COLUMNS = [
    "record_id_raw",
    "aptamer_name_raw",
    "target_general_raw",
    "target_specific_raw",
    "reported_length_raw",
    "affinity_raw",
    "buffer_raw",
    "gc_content_raw",
    "sequence_raw",
    "reference_raw",
    "source_page",
    "source_url",
    "source_html_file",
    "retrieved_at_utc",
    "row_parse_status",
    "row_parse_warnings",
]

BASE_URL = "https://www.iitg.ac.in/proj/aptabase/aptasearch.php"

# Match page_001.html, page_37.html, or live cache names page_00037.html
PAGE_NUMBER_RE = re.compile(r"page[_-]?0*(\d+)\.html$", re.IGNORECASE)


def page_url(page_number: int) -> str:
    """Return the canonical AptaBase URL for a result page."""
    return f"{BASE_URL}?page={page_number}"


def infer_page_number_from_path(path: Path) -> int | None:
    """Infer a page number from a cached HTML filename, if possible."""
    match = PAGE_NUMBER_RE.search(path.name)
    if match:
        return int(match.group(1))
    return None


def _normalise_header_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _find_results_table(soup: BeautifulSoup):
    """Locate the main results table that has the expected ten columns."""
    tables = soup.find_all("table")
    if not tables:
        raise ValueError("No HTML tables found on page.")

    for table in tables:
        header_cells = table.select("thead th")
        if not header_cells:
            first_row = table.find("tr")
            if first_row:
                header_cells = first_row.find_all(["th", "td"])
        headers = [_normalise_header_text(cell.get_text(" ", strip=True)) for cell in header_cells]
        if headers == EXPECTED_HEADERS:
            return table, headers

    # Fall back to the largest table with ten columns in the first row.
    for table in tables:
        first_row = table.find("tr")
        if not first_row:
            continue
        cells = first_row.find_all(["th", "td"])
        if len(cells) == 10:
            headers = [_normalise_header_text(cell.get_text(" ", strip=True)) for cell in cells]
            return table, headers

    raise ValueError("Could not identify the AptaBase results table with ten expected columns.")


def _extract_data_rows(table) -> list:
    """Return data rows from the table body, skipping header-only rows."""
    tbody = table.find("tbody")
    if tbody is not None:
        rows = tbody.find_all("tr")
    else:
        rows = table.find_all("tr")
        # Drop a leading header row if present.
        if rows and rows[0].find_all("th"):
            rows = rows[1:]
    return rows


def parse_aptabase_html(
    html: str | bytes,
    *,
    source_page: int | None = None,
    source_url: str | None = None,
    source_html_file: str | None = None,
    retrieved_at_utc: str | None = None,
) -> list[dict[str, Any]]:
    """Parse one AptaBase HTML page into a list of raw record dictionaries.

    Malformed rows are retained with ``row_parse_status`` set to
    ``malformed`` and a warning message, rather than being dropped.
    """
    if isinstance(html, bytes):
        # Preserve bytes exactly for caching elsewhere; decode here for parsing.
        html_text = html.decode("utf-8", errors="replace")
    else:
        html_text = html

    soup = BeautifulSoup(html_text, "html.parser")
    table, headers = _find_results_table(soup)
    if headers != EXPECTED_HEADERS:
        logger.warning(
            "Header mismatch on page %s: got %s",
            source_page,
            headers,
        )

    if retrieved_at_utc is None:
        retrieved_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if source_url is None and source_page is not None:
        source_url = page_url(source_page)

    records: list[dict[str, Any]] = []
    rows = _extract_data_rows(table)

    for row_index, row in enumerate(rows, start=1):
        cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
        warnings: list[str] = []
        status = "ok"

        if len(cells) != 10:
            status = "malformed"
            warnings.append(
                f"expected_10_cells_got_{len(cells)}_at_row_index_{row_index}"
            )
            # Pad or truncate so downstream columns stay aligned.
            if len(cells) < 10:
                cells = cells + [""] * (10 - len(cells))
            else:
                cells = cells[:10]

        record = {
            "record_id_raw": cells[0],
            "aptamer_name_raw": cells[1],
            "target_general_raw": cells[2],
            "target_specific_raw": cells[3],
            "reported_length_raw": cells[4],
            "affinity_raw": cells[5],
            "buffer_raw": cells[6],
            "gc_content_raw": cells[7],
            "sequence_raw": cells[8],
            "reference_raw": cells[9],
            "source_page": source_page,
            "source_url": source_url or "",
            "source_html_file": source_html_file or "",
            "retrieved_at_utc": retrieved_at_utc,
            "row_parse_status": status,
            "row_parse_warnings": "; ".join(warnings),
        }
        records.append(record)

    return records


def parse_aptabase_html_file(
    path: Path,
    *,
    source_page: int | None = None,
    source_url: str | None = None,
    retrieved_at_utc: str | None = None,
) -> list[dict[str, Any]]:
    """Parse a saved HTML file into raw records."""
    path = Path(path)
    if source_page is None:
        source_page = infer_page_number_from_path(path)
    # Read as bytes so the cache remains byte-identical to the download.
    raw_bytes = path.read_bytes()
    return parse_aptabase_html(
        raw_bytes,
        source_page=source_page,
        source_url=source_url,
        source_html_file=str(path),
        retrieved_at_utc=retrieved_at_utc,
    )


def records_to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert raw record dictionaries to a DataFrame with stable column order."""
    if not records:
        return pd.DataFrame(columns=RAW_COLUMNS)
    frame = pd.DataFrame(records)
    for column in RAW_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[RAW_COLUMNS]


def parse_html_directory(
    directory: Path,
    *,
    pattern: str = "page_*.html",
) -> pd.DataFrame:
    """Parse all matching HTML files in a directory into one raw DataFrame."""
    directory = Path(directory)
    paths = sorted(directory.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"No HTML files matching {pattern!r} in {directory}")

    all_records: list[dict[str, Any]] = []
    for path in paths:
        page_number = infer_page_number_from_path(path)
        logger.info("Parsing %s (page=%s)", path.name, page_number)
        records = parse_aptabase_html_file(path, source_page=page_number)
        all_records.extend(records)
        logger.info("  extracted %d rows", len(records))

    return records_to_dataframe(all_records)


def page_content_signature(records: list[dict[str, Any]]) -> tuple[tuple[str, ...], ...]:
    """Build a comparable signature of record IDs and core fields for a page.

    Used by the downloader to detect repeated/pagination-overflow pages.
    """
    signature: list[tuple[str, ...]] = []
    for record in records:
        signature.append(
            (
                record.get("record_id_raw", ""),
                record.get("aptamer_name_raw", ""),
                record.get("sequence_raw", ""),
                record.get("affinity_raw", ""),
            )
        )
    return tuple(signature)

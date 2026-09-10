#!/usr/bin/env python3
"""AptaBase scraper and cleaning pipeline orchestration.

Commands
--------
parse-fixtures
    Parse the four saved fixture HTML pages only.
download
    Respectfully download and cache live result pages.
build
    Parse cached HTML (no network) and write raw, cleaned, and QC outputs.
all
    Download, then build outputs.

Example
-------
python scripts/data_preparation/scrape_aptabase.py parse-fixtures
python scripts/data_preparation/scrape_aptabase.py download --start-page 1 --max-pages 100
python scripts/data_preparation/scrape_aptabase.py build
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

# Allow running as a script without installing a package.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from aptabase_cleaning import (  # noqa: E402
    clean_raw_dataframe,
    generate_qc_report,
)
from aptabase_parser import (  # noqa: E402
    BASE_URL,
    RAW_COLUMNS,
    page_content_signature,
    page_url,
    parse_aptabase_html,
    parse_aptabase_html_file,
    parse_html_directory,
    records_to_dataframe,
)

DATA_DIR = REPO_ROOT / "data" / "raw" / "aptabase"
HTML_DIR = DATA_DIR / "html"
FIXTURES_DIR = DATA_DIR / "fixtures"
RAW_CSV = DATA_DIR / "aptabase_raw.csv"
CLEANED_CSV = DATA_DIR / "aptabase_cleaned.csv"
QC_REPORT = DATA_DIR / "aptabase_qc_report.md"
SCRAPE_LOG = DATA_DIR / "aptabase_scrape_log.txt"

USER_AGENT = (
    "AcademicResearchAptaBaseScraper/0.1 "
    "(Macquarie University RNA aptamer research)"
)
TRANSIENT_STATUS = {500, 502, 503, 504}
STOP_STATUS = {403, 429}

logger = logging.getLogger("aptabase_scraper")


def setup_logging(level: str = "INFO", log_file: Path | None = SCRAPE_LOG) -> None:
    """Configure console and file logging."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    numeric = getattr(logging, level.upper(), logging.INFO)
    logger.handlers.clear()
    logger.setLevel(numeric)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    if log_file is not None:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)


def cached_html_path(page_number: int, directory: Path = HTML_DIR) -> Path:
    """Return the cache path for a page number."""
    return directory / f"page_{page_number:03d}.html"


def download_page(
    session: requests.Session,
    page_number: int,
    *,
    timeout: float = 30.0,
    max_retries: int = 3,
    delay: float = 2.0,
    overwrite: bool = False,
    html_dir: Path = HTML_DIR,
) -> dict[str, Any]:
    """Download one page or load it from cache.

    Returns a metadata dictionary describing the retrieval.
    """
    html_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cached_html_path(page_number, html_dir)
    url = page_url(page_number)
    meta: dict[str, Any] = {
        "page": page_number,
        "url": url,
        "path": cache_path,
        "from_cache": False,
        "status_code": None,
        "bytes": 0,
        "retries": 0,
        "error": None,
        "html_bytes": None,
    }

    if cache_path.exists() and not overwrite:
        data = cache_path.read_bytes()
        meta.update(
            {
                "from_cache": True,
                "status_code": "cache",
                "bytes": len(data),
                "html_bytes": data,
            }
        )
        logger.info(
            "page=%s loaded_from_cache bytes=%s file=%s",
            page_number,
            len(data),
            cache_path.name,
        )
        return meta

    attempt = 0
    while attempt <= max_retries:
        try:
            # Respectful delay before each live request (including retries).
            time.sleep(delay)
            response = session.get(url, timeout=timeout)
            meta["status_code"] = response.status_code
            meta["retries"] = attempt

            if response.status_code in STOP_STATUS:
                meta["error"] = f"blocked_status_{response.status_code}"
                logger.error(
                    "page=%s HTTP %s — stopping further live downloads",
                    page_number,
                    response.status_code,
                )
                return meta

            if response.status_code in TRANSIENT_STATUS:
                attempt += 1
                logger.warning(
                    "page=%s transient HTTP %s retry=%s/%s",
                    page_number,
                    response.status_code,
                    attempt,
                    max_retries,
                )
                if attempt > max_retries:
                    meta["error"] = f"transient_failed_{response.status_code}"
                    return meta
                continue

            response.raise_for_status()
            data = response.content  # raw bytes exactly as received
            cache_path.write_bytes(data)
            meta.update({"bytes": len(data), "html_bytes": data, "from_cache": False})
            logger.info(
                "page=%s retrieved_live status=%s bytes=%s file=%s",
                page_number,
                response.status_code,
                len(data),
                cache_path.name,
            )
            return meta
        except requests.RequestException as exc:
            attempt += 1
            meta["retries"] = attempt
            logger.warning(
                "page=%s request_error=%s retry=%s/%s",
                page_number,
                exc,
                attempt,
                max_retries,
            )
            if attempt > max_retries:
                meta["error"] = str(exc)
                return meta

    return meta


def download_pages(
    *,
    start_page: int = 1,
    max_pages: int = 100,
    delay: float = 2.0,
    timeout: float = 30.0,
    overwrite: bool = False,
    html_dir: Path = HTML_DIR,
) -> dict[str, Any]:
    """Download pages sequentially until a stop condition is met."""
    html_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html"})

    stopping_reason = "max_pages_reached"
    previous_signature: tuple[tuple[str, ...], ...] | None = None
    pages_downloaded = 0
    last_page = start_page - 1

    page = start_page
    end_page = start_page + max_pages - 1

    while page <= end_page:
        meta = download_page(
            session,
            page,
            timeout=timeout,
            delay=delay,
            overwrite=overwrite,
            html_dir=html_dir,
        )
        if meta.get("error"):
            if str(meta["error"]).startswith("blocked_status"):
                stopping_reason = meta["error"]
                break
            stopping_reason = f"download_error:{meta['error']}"
            break

        html_bytes = meta["html_bytes"]
        records = parse_aptabase_html(
            html_bytes,
            source_page=page,
            source_url=meta["url"],
            source_html_file=str(meta["path"]),
        )
        n_rows = len(records)
        logger.info("page=%s table_rows=%s", page, n_rows)
        pages_downloaded += 1
        last_page = page

        if n_rows == 0:
            stopping_reason = "empty_table"
            logger.info("Stopping: page %s contains zero data rows", page)
            break

        signature = page_content_signature(records)
        if previous_signature is not None and signature == previous_signature:
            stopping_reason = "repeated_page_content"
            logger.info(
                "Stopping: page %s repeats the same record IDs/content as previous page",
                page,
            )
            break

        previous_signature = signature
        page += 1
    else:
        stopping_reason = "max_pages_reached"
        logger.info("Stopping: reached max_pages=%s", max_pages)

    result = {
        "stopping_reason": stopping_reason,
        "pages_downloaded_or_cached": pages_downloaded,
        "first_page": start_page,
        "last_page": last_page,
        "html_dir": str(html_dir),
    }
    logger.info("Download finished: %s", result)
    return result


def write_outputs(
    raw_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    *,
    stopping_reason: str,
    raw_path: Path = RAW_CSV,
    cleaned_path: Path = CLEANED_CSV,
    qc_path: Path = QC_REPORT,
) -> None:
    """Write raw CSV, cleaned CSV, and QC Markdown report."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw_df.to_csv(raw_path, index=False, encoding="utf-8-sig")
    cleaned_df.to_csv(cleaned_path, index=False, encoding="utf-8-sig")
    report = generate_qc_report(
        raw_df,
        cleaned_df,
        stopping_reason=stopping_reason,
        scrape_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    qc_path.write_text(report, encoding="utf-8")
    logger.info("Wrote %s (%d rows)", raw_path, len(raw_df))
    logger.info("Wrote %s (%d rows)", cleaned_path, len(cleaned_df))
    logger.info("Wrote %s", qc_path)


def cmd_parse_fixtures(args: argparse.Namespace) -> int:
    """Parse fixture HTML pages and optionally write sample outputs."""
    fixtures_dir = Path(args.fixtures_dir) if args.fixtures_dir else FIXTURES_DIR
    if not fixtures_dir.exists():
        raise FileNotFoundError(f"Fixtures directory not found: {fixtures_dir}")

    raw_df = parse_html_directory(fixtures_dir)
    cleaned_df = clean_raw_dataframe(raw_df)
    write_outputs(
        raw_df,
        cleaned_df,
        stopping_reason="fixtures_only",
    )
    logger.info(
        "Fixture parse complete: %d raw rows, %d cleaned rows",
        len(raw_df),
        len(cleaned_df),
    )
    print(raw_df[["record_id_raw", "aptamer_name_raw", "source_page"]].to_string(index=False))
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    """Download live pages into the HTML cache."""
    result = download_pages(
        start_page=args.start_page,
        max_pages=args.max_pages,
        delay=args.delay,
        timeout=args.timeout,
        overwrite=args.overwrite,
        html_dir=Path(args.html_dir) if args.html_dir else HTML_DIR,
    )
    # Persist stopping reason for a later build step.
    reason_path = DATA_DIR / "aptabase_stopping_reason.txt"
    reason_path.write_text(result["stopping_reason"] + "\n", encoding="utf-8")
    return 0


def _load_stopping_reason() -> str:
    reason_path = DATA_DIR / "aptabase_stopping_reason.txt"
    if reason_path.exists():
        return reason_path.read_text(encoding="utf-8").strip() or "not_recorded"
    return "not_recorded"


def cmd_build(args: argparse.Namespace) -> int:
    """Build outputs from cached HTML without contacting the network."""
    if args.fixtures_only:
        html_dir = Path(args.fixtures_dir) if args.fixtures_dir else FIXTURES_DIR
        stopping_reason = "fixtures_only"
    else:
        html_dir = Path(args.html_dir) if args.html_dir else HTML_DIR
        stopping_reason = _load_stopping_reason()
        if not any(html_dir.glob("page_*.html")):
            # Fall back to fixtures so offline builds still work for development.
            logger.warning(
                "No cached HTML in %s; falling back to fixtures in %s",
                html_dir,
                FIXTURES_DIR,
            )
            html_dir = FIXTURES_DIR
            stopping_reason = "fixtures_fallback_no_cached_html"

    raw_df = parse_html_directory(html_dir)
    cleaned_df = clean_raw_dataframe(raw_df)
    write_outputs(raw_df, cleaned_df, stopping_reason=stopping_reason)
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    """Download then build."""
    download_code = cmd_download(args)
    if download_code != 0:
        return download_code
    return cmd_build(args)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape and clean publicly displayed AptaBase records.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    parser.add_argument(
        "--fixtures-dir",
        default=str(FIXTURES_DIR),
        help="Directory containing fixture HTML pages.",
    )
    parser.add_argument(
        "--html-dir",
        default=str(HTML_DIR),
        help="Directory for cached live HTML pages.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_fixtures = sub.add_parser("parse-fixtures", help="Parse saved fixture pages.")
    p_fixtures.set_defaults(func=cmd_parse_fixtures)

    p_download = sub.add_parser("download", help="Download and cache live pages.")
    p_download.add_argument("--start-page", type=int, default=1)
    p_download.add_argument("--max-pages", type=int, default=100)
    p_download.add_argument("--delay", type=float, default=2.0, help="Seconds between live requests.")
    p_download.add_argument("--timeout", type=float, default=30.0)
    p_download.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing cached HTML files.",
    )
    p_download.set_defaults(func=cmd_download)

    p_build = sub.add_parser("build", help="Build CSV/QC outputs from cached HTML (offline).")
    p_build.add_argument(
        "--fixtures-only",
        action="store_true",
        help="Build from fixtures only (no live cache).",
    )
    p_build.set_defaults(func=cmd_build)

    p_all = sub.add_parser("all", help="Download then build outputs.")
    p_all.add_argument("--start-page", type=int, default=1)
    p_all.add_argument("--max-pages", type=int, default=100)
    p_all.add_argument("--delay", type=float, default=2.0)
    p_all.add_argument("--timeout", type=float, default=30.0)
    p_all.add_argument("--overwrite", action="store_true")
    p_all.add_argument("--fixtures-only", action="store_true")
    p_all.set_defaults(func=cmd_all)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    setup_logging(args.log_level)
    logger.info("Repository root: %s", REPO_ROOT)
    logger.info("Data directory: %s", DATA_DIR)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

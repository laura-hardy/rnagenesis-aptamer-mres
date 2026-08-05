#!/usr/bin/env python3
"""S0a: validate the tracked source-registry specification and write the operational registry.

This stage freezes registered inputs by verifying path, SHA-256 and CSV row counts.
It does not build the leakage-exclusion set, extract sequences, or implement S1 adapters.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from xml.etree import ElementTree as ET

REQUIRED_COLUMNS: tuple[str, ...] = (
    "source_key",
    "source_dataset",
    "path",
    "sha256",
    "n_rows_expected",
    "snapshot_date",
    "tier",
    "redistribution_status",
    "notes",
)

ALLOWED_TIERS = frozenset({"1", "2", "3", "eval"})
ALLOWED_REDISTRIBUTION = frozenset(
    {"unknown", "permissive", "restricted", "prohibited"}
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

FORBIDDEN_EXACT_RELATIVE_PATHS = frozenset(
    {
        "data/raw/aptabase/aptabase_raw.csv",
        "data/raw/aptabase/Aptamer Search Page 1.html",
        "data/raw/aptabase/Aptamer Search Page 2.html",
        "data/raw/aptabase/Aptamer Search Page 37.html",
        "data/raw/aptabase/Aptamer Search Page 61.html",
    }
)

APTABASE_CLEANED_REL = "data/raw/aptabase/aptabase_cleaned.csv"
APTABASE_RAW_REL = "data/raw/aptabase/aptabase_raw.csv"


class RegistryError(Exception):
    """Hard failure while validating or writing the source registry."""


@dataclass
class RegistrySpecRow:
    """One row from the tracked registry specification."""

    source_key: str
    source_dataset: str
    path: str
    sha256: str
    n_rows_expected: int
    snapshot_date: str
    tier: str
    redistribution_status: str
    notes: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source_key": self.source_key,
            "source_dataset": self.source_dataset,
            "path": self.path,
            "sha256": self.sha256,
            "n_rows_expected": str(self.n_rows_expected),
            "snapshot_date": self.snapshot_date,
            "tier": self.tier,
            "redistribution_status": self.redistribution_status,
            "notes": self.notes,
        }


@dataclass
class ValidationResult:
    """Aggregate outcome of an S0a registry build."""

    rows: list[RegistrySpecRow]
    warnings: list[str] = field(default_factory=list)
    validated: int = 0


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the repository root by walking upward for ``.git`` or known markers."""
    current = (start or Path(__file__).resolve()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() and (candidate / "docs").is_dir():
            return candidate
        if (candidate / "docs" / "data_curation").is_dir() and (
            candidate / "scripts" / "data_preparation"
        ).is_dir():
            return candidate
    raise RegistryError(
        f"Unable to locate repository root starting from {current}"
    )


def normalise_relative_path(path_text: str) -> str:
    """Normalise a registry path to a forward-slash relative form."""
    text = path_text.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def resolve_registered_path(repo_root: Path, relative_path: str) -> Path:
    """Resolve a registered relative path under the repository root."""
    rel = normalise_relative_path(relative_path)
    if not rel or rel.startswith("/") or re.match(r"^[A-Za-z]:/", rel):
        raise RegistryError(
            f"Registered path must be a relative repository path: {relative_path!r}"
        )
    resolved = (repo_root / rel).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise RegistryError(
            f"Registered path escapes the repository root: {relative_path!r}"
        ) from exc
    return resolved


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute the SHA-256 digest of a file using streaming reads."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def count_csv_data_rows(path: Path) -> int:
    """Count CSV data rows, excluding the header and respecting quoted newlines.

    Opens the file as ``utf-8-sig``. Raises ``RegistryError`` if the header is
    missing or the file is empty.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise RegistryError(
                f"Registered CSV has no header row: {path}"
            ) from exc
        if not header or all(not cell.strip() for cell in header):
            raise RegistryError(
                f"Registered CSV header is empty or invalid: {path}"
            )
        return sum(1 for _ in reader)


def count_xlsx_physical_data_rows(path: Path) -> int:
    """Count physical data rows on the first worksheet of an XLSX workbook.

    Uses ZIP/XML only (stdlib). Never saves or rewrites the workbook. The count
    is ``len(sheetData/row) - 1`` when at least one row exists (first row treated
    as header layout), matching the inventory convention for worksheet layout.
    Logical aptamer-record counts for irregular layouts must be asserted by
    source adapters separately.
    """
    if path.name.startswith("~$"):
        raise RegistryError(f"Excel lock/temp file is not a valid input: {path.name}")
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            sheet_paths = sorted(
                n
                for n in names
                if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
            )
            if not sheet_paths:
                raise RegistryError(
                    f"Registered XLSX has no worksheets: {path.name}"
                )
            # Prefer workbook.xml sheet order when available.
            selected = sheet_paths[0]
            ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            if "xl/workbook.xml" in names:
                wb = ET.fromstring(zf.read("xl/workbook.xml"))
                sheets = wb.findall("m:sheets/m:sheet", ns)
                if sheets:
                    rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
                    rid_to_target = {
                        rel.attrib["Id"]: rel.attrib["Target"]
                        for rel in rels_root
                        if "Id" in rel.attrib and "Target" in rel.attrib
                    }
                    rid = sheets[0].attrib.get(
                        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                    )
                    target = rid_to_target.get(rid or "")
                    if target:
                        if not target.startswith("xl/"):
                            target = "xl/" + target.lstrip("/")
                        if target in names:
                            selected = target
            sheet_root = ET.fromstring(zf.read(selected))
            rows_xml = sheet_root.findall("m:sheetData/m:row", ns)
            if not rows_xml:
                return 0
            return max(0, len(rows_xml) - 1)
    except zipfile.BadZipFile as exc:
        raise RegistryError(
            f"Registered XLSX is not a valid ZIP/OOXML workbook: {path.name}"
        ) from exc
    except ET.ParseError as exc:
        raise RegistryError(
            f"Registered XLSX worksheet XML could not be parsed: {path.name}"
        ) from exc


def count_registered_rows(path: Path) -> int:
    """Count rows for a registered input according to its file type."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return count_csv_data_rows(path)
    if suffix in {".xlsx", ".xlsm"}:
        return count_xlsx_physical_data_rows(path)
    raise RegistryError(
        f"Unsupported registered input type for row counting: {path.name}"
    )


def _require_exact_columns(fieldnames: Sequence[str] | None) -> None:
    if fieldnames is None:
        raise RegistryError("Registry specification has no header row")
    actual = list(fieldnames)
    expected = list(REQUIRED_COLUMNS)
    if actual != expected:
        raise RegistryError(
            "Registry specification columns must match exactly in order. "
            f"Expected {expected}, got {actual}"
        )


def load_registry_spec(path: Path) -> list[RegistrySpecRow]:
    """Load and structurally validate the tracked registry specification."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_exact_columns(reader.fieldnames)
        raw_rows = list(reader)

    if not raw_rows:
        raise RegistryError(f"Registry specification is empty: {path}")

    parsed: list[RegistrySpecRow] = []
    keys: set[str] = set()
    datasets: set[str] = set()
    paths: set[str] = set()

    for index, row in enumerate(raw_rows, start=2):
        source_key = (row.get("source_key") or "").strip()
        source_dataset = (row.get("source_dataset") or "").strip()
        rel_path = normalise_relative_path(row.get("path") or "")
        sha256 = (row.get("sha256") or "").strip().lower()
        n_rows_text = (row.get("n_rows_expected") or "").strip()
        snapshot_date = (row.get("snapshot_date") or "").strip()
        tier = (row.get("tier") or "").strip()
        redistribution = (row.get("redistribution_status") or "").strip()
        notes = row.get("notes") or ""

        missing = [
            name
            for name, value in (
                ("source_key", source_key),
                ("source_dataset", source_dataset),
                ("path", rel_path),
                ("sha256", sha256),
                ("snapshot_date", snapshot_date),
            )
            if not value
        ]
        if missing:
            raise RegistryError(
                f"Registry specification row {index} missing required "
                f"nonempty field(s): {', '.join(missing)}"
            )

        if source_key in keys:
            raise RegistryError(
                f"Duplicate source_key in registry specification: {source_key!r}"
            )
        if source_dataset in datasets:
            raise RegistryError(
                f"Duplicate source_dataset in registry specification: "
                f"{source_dataset!r}"
            )
        if rel_path in paths:
            raise RegistryError(
                f"Duplicate registered path in registry specification: "
                f"{rel_path!r}"
            )
        keys.add(source_key)
        datasets.add(source_dataset)
        paths.add(rel_path)

        if not SHA256_RE.fullmatch(sha256):
            raise RegistryError(
                f"Invalid SHA-256 for source_key={source_key!r}: must be 64 "
                f"lowercase hexadecimal characters"
            )

        if not n_rows_text.isdigit():
            raise RegistryError(
                f"n_rows_expected must be a nonnegative integer for "
                f"source_key={source_key!r}; got {n_rows_text!r}"
            )
        n_rows_expected = int(n_rows_text)

        if tier not in ALLOWED_TIERS:
            raise RegistryError(
                f"Invalid tier for source_key={source_key!r}: {tier!r}; "
                f"allowed={sorted(ALLOWED_TIERS)}"
            )
        if redistribution not in ALLOWED_REDISTRIBUTION:
            raise RegistryError(
                f"Invalid redistribution_status for source_key={source_key!r}: "
                f"{redistribution!r}; allowed={sorted(ALLOWED_REDISTRIBUTION)}"
            )

        parsed.append(
            RegistrySpecRow(
                source_key=source_key,
                source_dataset=source_dataset,
                path=rel_path,
                sha256=sha256,
                n_rows_expected=n_rows_expected,
                snapshot_date=snapshot_date,
                tier=tier,
                redistribution_status=redistribution,
                notes=notes,
            )
        )

    return parsed


def assert_path_allowed(repo_root: Path, relative_path: str) -> Path:
    """Reject forbidden or unsafe registered paths; return the resolved file path."""
    rel = normalise_relative_path(relative_path)
    lower = rel.lower()

    if rel in FORBIDDEN_EXACT_RELATIVE_PATHS:
        raise RegistryError(
            f"Forbidden AptaBase companion registered as input: {rel}"
        )
    if rel == APTABASE_RAW_REL or rel.endswith("/aptabase_raw.csv"):
        raise RegistryError(
            f"Forbidden AptaBase raw CSV registered as input: {rel}"
        )
    if ".ds_store" in lower or lower.endswith(".ds_store"):
        raise RegistryError(f"Registered path must not be .DS_Store: {rel}")
    if "/~$" in f"/{rel}" or Path(rel).name.startswith("~$"):
        raise RegistryError(f"Excel lock/temp file is not a valid input: {rel}")
    if "/html/" in f"/{lower}/" or lower.endswith("/html") or "/html/" in lower:
        raise RegistryError(f"HTML cache paths are forbidden inputs: {rel}")
    if (
        "/fixtures/" in f"/{lower}/"
        or lower.endswith("/fixtures")
        or "/fixtures/" in lower
    ):
        raise RegistryError(f"Fixture paths are forbidden inputs: {rel}")

    if not rel.startswith("data/raw/"):
        raise RegistryError(
            f"Registered path must lie beneath data/raw/: {rel}"
        )

    resolved = resolve_registered_path(repo_root, rel)
    if resolved.is_dir():
        raise RegistryError(
            f"Registered path is a directory, not a file: {rel}"
        )
    if not resolved.exists():
        raise RegistryError(f"Registered input file is missing: {rel}")
    if not resolved.is_file():
        raise RegistryError(f"Registered path is not a regular file: {rel}")
    return resolved


def load_inventory_index(path: Path) -> dict[str, dict[str, str]]:
    """Index inventory rows by normalised relative path."""
    if not path.is_file():
        raise RegistryError(f"Inventory file not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "relative_path" not in reader.fieldnames:
            raise RegistryError(
                f"Inventory is missing relative_path column: {path}"
            )
        index: dict[str, dict[str, str]] = {}
        for row in reader:
            rel = normalise_relative_path(row.get("relative_path") or "")
            if rel:
                index[rel] = row
    return index


_AUTHORITATIVE_S0_STATUSES = frozenset(
    {
        "include_as_authoritative_input",
        "include",
        "authoritative_input",
    }
)


def _append_aptabase_inventory_overrides(
    inventory: Mapping[str, Mapping[str, str]],
    warnings: list[str],
) -> None:
    """Emit the two AptaBase-specific inventory override warnings (no duplicates)."""
    warnings.append(
        "AptaBase inventory override: raw_data_inventory.csv classifies "
        "data/raw/aptabase/aptabase_cleaned.csv as a derived output "
        "(recommended_S0_status=derived_output_not_raw_input); the binding "
        "registry deliberately uses the cleaned scrape as the Tier 1 input."
    )
    raw_inv = inventory.get(APTABASE_RAW_REL)
    raw_status = (
        (raw_inv.get("recommended_S0_status") or "").strip() if raw_inv else ""
    )
    warnings.append(
        "AptaBase inventory override: raw_data_inventory.csv recommends "
        f"{APTABASE_RAW_REL}"
        + (f" (recommended_S0_status={raw_status})" if raw_status else "")
        + " as an authoritative input, but that companion file is a "
        "forbidden pipeline input."
    )


def compare_with_inventory(
    row: RegistrySpecRow,
    inventory: Mapping[str, Mapping[str, str]],
    warnings: list[str],
) -> None:
    """Emit inventory divergence warnings; never hard-fail on inventory alone.

    Source-specific override messages replace the generic status warning for the
    same mismatch so a single disagreement is not reported twice.
    """
    inv = inventory.get(row.path)
    if inv is None:
        warnings.append(
            f"Inventory warning for {row.source_key}: registered path "
            f"{row.path} is absent from raw_data_inventory.csv"
        )
        return

    inv_sha = (inv.get("sha256") or "").strip().lower()
    if inv_sha and inv_sha != row.sha256:
        warnings.append(
            f"Inventory warning for {row.source_key}: inventory sha256 "
            f"{inv_sha} differs from registry sha256 {row.sha256} for {row.path}"
        )

    inv_rows = (inv.get("row_count") or "").strip()
    if inv_rows and inv_rows.isdigit() and int(inv_rows) != row.n_rows_expected:
        warnings.append(
            f"Inventory warning for {row.source_key}: inventory row_count "
            f"{inv_rows} differs from registry n_rows_expected "
            f"{row.n_rows_expected} for {row.path}"
        )

    status = (inv.get("recommended_S0_status") or "").strip()
    is_aptabase_cleaned = (
        row.source_key == "aptabase" and row.path == APTABASE_CLEANED_REL
    )
    if is_aptabase_cleaned:
        # Dedicated messages cover cleaned-file status and forbidden raw companion.
        _append_aptabase_inventory_overrides(inventory, warnings)
        return

    if status and status not in _AUTHORITATIVE_S0_STATUSES:
        warnings.append(
            f"Inventory warning for {row.source_key}: inventory "
            f"recommended_S0_status={status!r} for {row.path}, but the binding "
            f"registry deliberately registers this path"
        )


def validate_registered_file(
    repo_root: Path,
    row: RegistrySpecRow,
) -> None:
    """Hard-fail if the on-disk file does not match the registry specification."""
    resolved = assert_path_allowed(repo_root, row.path)
    actual_sha = sha256_file(resolved)
    if actual_sha != row.sha256:
        raise RegistryError(
            f"SHA-256 mismatch for source_key={row.source_key!r} path={row.path}: "
            f"expected {row.sha256}, actual {actual_sha}"
        )
    actual_rows = count_registered_rows(resolved)
    if actual_rows != row.n_rows_expected:
        raise RegistryError(
            f"Row-count mismatch for source_key={row.source_key!r} "
            f"path={row.path}: expected {row.n_rows_expected}, "
            f"actual {actual_rows}"
        )


def write_operational_registry(
    output_path: Path,
    rows: Iterable[RegistrySpecRow],
) -> None:
    """Atomically write the operational registry with deterministic formatting."""
    ordered = sorted(rows, key=lambda item: item.source_key)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Refuse to create anything under data/raw via this writer.
    parts = [part.lower() for part in output_path.resolve().parts]
    if "data" in parts:
        data_index = parts.index("data")
        if data_index + 1 < len(parts) and parts[data_index + 1] == "raw":
            raise RegistryError(
                f"Refusing to write operational registry under data/raw/: "
                f"{output_path}"
            )

    fd, temp_name = tempfile.mkstemp(
        prefix=".source_registry.",
        suffix=".csv.tmp",
        dir=str(output_path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(REQUIRED_COLUMNS),
                lineterminator="\n",
            )
            writer.writeheader()
            for row in ordered:
                writer.writerow(row.as_dict())
        temp_path.replace(output_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def build_registry(
    repo_root: Path,
    registry_spec: Path,
    inventory_path: Path,
    output_path: Path,
) -> ValidationResult:
    """Validate the specification against disk and write the operational registry."""
    spec_rows = load_registry_spec(registry_spec)
    inventory = load_inventory_index(inventory_path)
    warnings: list[str] = []
    validated = 0

    for row in spec_rows:
        compare_with_inventory(row, inventory, warnings)
        validate_registered_file(repo_root, row)
        validated += 1

    write_operational_registry(output_path, spec_rows)
    return ValidationResult(rows=spec_rows, warnings=warnings, validated=validated)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "S0a: validate config/source_registry.csv and write the operational "
            "registry under data/interim/registry/."
        )
    )
    parser.add_argument(
        "--registry-spec",
        type=Path,
        default=None,
        help="Tracked registry specification CSV (default: config/source_registry.csv)",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=None,
        help=(
            "Raw-data inventory CSV "
            "(default: docs/data_curation/raw_data_inventory.csv)"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Operational registry output "
            "(default: data/interim/registry/source_registry.csv)"
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detected)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        repo_root = (
            args.repo_root.resolve()
            if args.repo_root is not None
            else find_repo_root(Path(__file__).resolve())
        )
        if not repo_root.is_dir():
            raise RegistryError(f"Repository root does not exist: {repo_root}")

        registry_spec = (
            args.registry_spec
            if args.registry_spec is not None
            else repo_root / "config" / "source_registry.csv"
        )
        inventory = (
            args.inventory
            if args.inventory is not None
            else repo_root / "docs" / "data_curation" / "raw_data_inventory.csv"
        )
        output = (
            args.output
            if args.output is not None
            else repo_root / "data" / "interim" / "registry" / "source_registry.csv"
        )

        # Resolve relative CLI paths against the repository root, not cwd.
        def under_repo(path: Path) -> Path:
            return path if path.is_absolute() else (repo_root / path).resolve()

        registry_spec = under_repo(registry_spec)
        inventory = under_repo(inventory)
        output = under_repo(output)

        result = build_registry(
            repo_root=repo_root,
            registry_spec=registry_spec,
            inventory_path=inventory,
            output_path=output,
        )
    except RegistryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    # Aggregate summary only — never print sequence contents.
    try:
        output_display = str(output.relative_to(repo_root))
    except ValueError:
        output_display = str(output)

    print(
        "S0a registry build OK: "
        f"registered_sources={len(result.rows)} "
        f"validated={result.validated} "
        f"warnings={len(result.warnings)} "
        f"output={output_display}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

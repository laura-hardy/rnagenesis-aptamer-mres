#!/usr/bin/env python3
"""S0b: build the carbapenemase evaluation-reference manifest and leakage-exclusion set.

Protects the training/reference corpus from evaluation leakage via known reference
sequences (including alternate full/core and DNA/RNA T↔U-equivalent forms), while
recording target-level exclusion aliases separately. Pending sequence extractions
are reported without silently omitting them. Outputs under data/ are gitignored.

This stage does not implement the general S2 sequence normaliser, AptaBase S1
adapters, corpus merging, or partitioning.
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
from typing import Any, Iterable, Mapping, Sequence
from xml.etree import ElementTree as ET

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.leakage_matching import (  # noqa: E402
    LeakageMatchingError,
    comparison_form,
    prepare_molecule_native_sequence,
    remove_display_artifacts,
    validate_simple_nucleotide_string,
)
from s0_build_registry import (  # noqa: E402
    RegistryError,
    RegistrySpecRow,
    find_repo_root,
    load_registry_spec,
    sha256_file,
    validate_registered_file,
)

LEAKAGE_COLUMNS: tuple[str, ...] = (
    "exclusion_id",
    "reference_id",
    "aptamer_name",
    "target_name_raw",
    "target_name",
    "evaluation_role",
    "evaluation_label",
    "molecule_type",
    "alphabet_as_reported",
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "sequence_compare_full",
    "sequence_compare_core",
    "sequence_length_full",
    "sequence_length_core",
    "construct_scope",
    "t_to_u_applied",
    "source_key",
    "source_record_id",
    "publication",
    "source_location",
    "contributing_sources",
    "contributing_publications",
    "status",
    "qc_flags",
    "notes",
)

MANIFEST_COLUMNS: tuple[str, ...] = (
    "reference_id",
    "record_type",
    "aptamer_name",
    "target_name_raw",
    "target_name",
    "evaluation_role",
    "evaluation_label",
    "molecule_type",
    "alphabet_as_reported",
    "sequence_scope",
    "reported_length",
    "source_key",
    "publication",
    "source_location",
    "include_in_sequence_leakage",
    "status",
    "exclusion_id",
    "contributing_sources",
    "notes",
)

DATASET_COLUMNS: tuple[str, ...] = (
    "reference_id",
    "source_key",
    "publication",
    "target_name_raw",
    "evaluation_role",
    "source_location",
    "selection_rounds",
    "status",
    "include_in_sequence_leakage",
    "notes",
)

PENDING_COLUMNS: tuple[str, ...] = (
    "reference_id",
    "aptamer_name",
    "target_name_raw",
    "evaluation_role",
    "expected_source",
    "missing_artefact",
    "include_in_sequence_leakage",
    "family_already_protected",
    "action_needed",
    "supersedes_record_id",
    "notes",
)

ADDITIONS_COLUMNS: tuple[str, ...] = (
    "reference_id",
    "record_type",
    "action",
    "source_key",
    "publication",
    "target_name_raw",
    "aptamer_name",
    "sequence_raw",
    "molecule_type",
    "alphabet_as_reported",
    "sequence_scope",
    "reported_length",
    "binding_metric",
    "selection_method",
    "selection_rounds",
    "source_location",
    "evaluation_role",
    "status",
    "include_in_sequence_leakage",
    "supersedes_record_id",
    "notes",
)

EXPECTED_D9_IDS: tuple[str, ...] = (
    "D902",
    "D907",
    "D909",
    "D913",
    "D914",
    "D918",
    "D920",
)

D9_DOCUMENTED_LENGTHS: dict[str, int] = {
    "D902": 50,
    "D907": 34,
    "D909": 48,
    "D913": 50,
    "D914": 50,
    "D918": 49,
    "D920": 50,
}

D9_EVALUATION_LABELS: dict[str, str] = {
    "D902": "pool_nonbinder",
    "D907": "pool_nonbinder",
    "D909": "positive",
    "D913": "pool_nonbinder",
    "D914": "pool_nonbinder",
    "D918": "secondary_positive",
    "D920": "secondary_positive",
}

BOOL_TRUE = frozenset({"true", "1", "yes", "y"})
BOOL_FALSE = frozenset({"false", "0", "no", "n"})

S0B_SOURCE_KEYS: frozenset[str] = frozenset(
    {
        "von_laer_2013_d9_table6",
        "yu_2021_precision_selex_xlsx",
        "chen_2020_xk10_csv",
        "shi_2025_kpc2kp_csv",
        "carbapenemase_additions_overrides",
    }
)


class LeakageBuildError(Exception):
    """Hard failure while building the S0b leakage-exclusion artefacts."""


@dataclass
class ParsedReference:
    """One evaluation-reference sequence or provenance contribution."""

    reference_id: str
    aptamer_name: str
    target_name_raw: str
    target_name: str
    evaluation_role: str
    evaluation_label: str
    molecule_type: str
    alphabet_as_reported: str
    sequence_raw: str
    sequence_full: str
    sequence_core: str
    sequence_compare_full: str
    sequence_compare_core: str
    construct_scope: str
    t_to_u_applied: bool
    source_key: str
    source_record_id: str
    publication: str
    source_location: str
    status: str = "resolved"
    qc_flags: list[str] = field(default_factory=list)
    notes: str = ""
    include_in_sequence_leakage: bool = True
    record_type: str = "sequence"
    action: str = "add"
    reported_length: str = ""
    sequence_scope: str = ""
    supersedes_record_id: str = ""
    contributing_sources: list[str] = field(default_factory=list)
    contributing_publications: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.contributing_sources:
            self.contributing_sources = [self.source_key]
        if not self.contributing_publications and self.publication:
            self.contributing_publications = [self.publication]


@dataclass
class DatasetReference:
    reference_id: str
    source_key: str
    publication: str
    target_name_raw: str
    evaluation_role: str
    source_location: str
    selection_rounds: str
    status: str
    include_in_sequence_leakage: bool
    notes: str


@dataclass
class PendingReference:
    reference_id: str
    aptamer_name: str
    target_name_raw: str
    evaluation_role: str
    expected_source: str
    missing_artefact: str
    include_in_sequence_leakage: bool
    family_already_protected: str
    action_needed: str
    supersedes_record_id: str
    notes: str


@dataclass
class BuildResult:
    leakage_rows: list[dict[str, str]]
    manifest_rows: list[dict[str, str]]
    dataset_rows: list[dict[str, str]]
    pending_rows: list[dict[str, str]]
    report_markdown: str
    aggregates: dict[str, Any]
    incomplete: bool


def _parse_bool(value: str, *, field_name: str) -> bool:
    text = (value or "").strip().lower()
    if text in BOOL_TRUE:
        return True
    if text in BOOL_FALSE:
        return False
    raise LeakageBuildError(f"Invalid boolean for {field_name}: {value!r}")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


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
                writer.writerow({k: row.get(k, "") for k in fieldnames})
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def _refuse_raw_output(path: Path, repo_root: Path) -> None:
    resolved = path.resolve()
    raw_root = (repo_root / "data" / "raw").resolve()
    try:
        resolved.relative_to(raw_root)
    except ValueError:
        return
    raise LeakageBuildError(f"Refusing to write under data/raw/: {path}")


def _rel_display(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return path.name


def _canonical_target(raw: str) -> str:
    text = (raw or "").strip()
    lower = text.lower()
    if "ndm" in lower and "vim" in lower:
        return "NDM-1|VIM-2"
    if "vim-2" in lower or re.search(r"\bvim2\b", lower):
        return "VIM-2"
    if "ndm" in lower:
        return "NDM-1"
    if "kpc" in lower:
        return "KPC-2"
    if "oxa-48" in lower or "oxa48" in lower:
        return "OXA-48"
    if "oxa-23" in lower or "oxa23" in lower:
        return "OXA-23"
    if "human serum albumin" in lower or re.search(r"\bhsa\b", lower):
        return "HSA"
    if "his" in lower and "tag" in lower:
        return "HIS-tag"
    if "polyhistidine" in lower or "hexa-his" in lower or "his-tag" in lower:
        return "HIS-tag"
    return text


def _bool_str(value: bool) -> str:
    return "true" if value else "false"


def _join_unique(values: Iterable[str]) -> str:
    seen: list[str] = []
    for value in values:
        text = (value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return "|".join(seen)


def _make_sequence_fields(
    *,
    sequence_raw: str,
    sequence_core_raw: str | None,
    molecule_type: str,
    alphabet_as_reported: str,
    construct_scope: str,
    core_unresolved: bool = False,
) -> tuple[str, str, str, str, list[str], bool]:
    """Return full, core, compare_full, compare_core, qc_flags, t_to_u_applied."""
    flags: list[str] = []
    try:
        sequence_full, t_to_u = prepare_molecule_native_sequence(
            sequence_raw,
            molecule_type=molecule_type,
            alphabet_as_reported=alphabet_as_reported,
        )
    except LeakageMatchingError as exc:
        raise LeakageBuildError(str(exc)) from exc

    if sequence_core_raw is None or not str(sequence_core_raw).strip():
        sequence_core = sequence_full
        if core_unresolved:
            flags.append("core_unresolved")
    else:
        try:
            sequence_core, _ = prepare_molecule_native_sequence(
                sequence_core_raw,
                molecule_type=molecule_type,
                alphabet_as_reported=alphabet_as_reported,
            )
        except LeakageMatchingError as exc:
            raise LeakageBuildError(str(exc)) from exc

    compare_full = comparison_form(sequence_full)
    compare_core = comparison_form(sequence_core)
    if construct_scope:
        pass
    return sequence_full, sequence_core, compare_full, compare_core, flags, t_to_u


def _assert_length(name: str, sequence: str, expected: int) -> None:
    actual = len(sequence)
    if actual != expected:
        raise LeakageBuildError(
            f"Length mismatch for {name}: expected {expected} nt, computed {actual} nt"
        )


def load_target_aliases(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = [
            "canonical_target",
            "alias",
            "match_type",
            "target_family",
            "exclusion_reason",
            "notes",
        ]
        if list(reader.fieldnames or []) != expected:
            raise LeakageBuildError(
                f"leakage_target_aliases.csv columns must match {expected}"
            )
        rows = list(reader)
    allowed = {"exact_alias", "normalised_alias", "family_pattern"}
    for index, row in enumerate(rows, start=2):
        if (row.get("match_type") or "").strip() not in allowed:
            raise LeakageBuildError(
                f"Invalid match_type on leakage_target_aliases.csv row {index}"
            )
        if not (row.get("canonical_target") or "").strip() or not (
            row.get("alias") or ""
        ).strip():
            raise LeakageBuildError(
                f"Empty canonical_target/alias on leakage_target_aliases.csv row {index}"
            )
    return rows


def _xlsx_sheet_rows(path: Path) -> list[dict[str, str | None]]:
    """Return sparse A/B/C/D cell maps for each physical sheet row (stdlib ZIP/XML)."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_root.findall("m:si", ns):
                shared.append(
                    "".join(t.text or "" for t in si.findall(".//m:t", ns))
                )
        sheet_path = sorted(
            n
            for n in names
            if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
        )[0]
        if "xl/workbook.xml" in names:
            wb = ET.fromstring(zf.read("xl/workbook.xml"))
            sheets = wb.findall("m:sheets/m:sheet", ns)
            if sheets:
                rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
                rid_map = {
                    rel.attrib["Id"]: rel.attrib["Target"]
                    for rel in rels
                    if "Id" in rel.attrib and "Target" in rel.attrib
                }
                rid = sheets[0].attrib.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                target = rid_map.get(rid or "")
                if target:
                    if not target.startswith("xl/"):
                        target = "xl/" + target.lstrip("/")
                    if target in names:
                        sheet_path = target
        root = ET.fromstring(zf.read(sheet_path))

        def cell_value(c: ET.Element) -> str | None:
            t = c.attrib.get("t")
            v = c.find("m:v", ns)
            if v is None or v.text is None:
                is_elem = c.find("m:is", ns)
                if is_elem is not None:
                    return "".join(
                        x.text or "" for x in is_elem.findall(".//m:t", ns)
                    )
                return None
            if t == "s":
                return shared[int(v.text)]
            return v.text

        rows: list[dict[str, str | None]] = []
        for row in root.findall("m:sheetData/m:row", ns):
            cells: dict[str, str | None] = {}
            for c in row.findall("m:c", ns):
                ref = c.attrib.get("r", "")
                col = "".join(ch for ch in ref if ch.isalpha())
                cells[col] = cell_value(c)
            rows.append(cells)
        return rows


def parse_d9(
    path: Path, *, source_key: str, source_sha: str
) -> list[ParsedReference]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = [(r.get("clone_id") or "").strip() for r in rows]
    if ids != list(EXPECTED_D9_IDS):
        raise LeakageBuildError(
            "D9 source must contain exactly the seven expected clone IDs in order"
        )
    out: list[ParsedReference] = []
    for row in rows:
        clone = (row.get("clone_id") or "").strip()
        sequence_raw = row.get("sequence_reported") or ""
        # Do not trust sequence_cleaned when length/whitespace disagree; derive
        # molecule-native form from the published DNA-alphabet sequence.
        (
            sequence_full,
            sequence_core,
            compare_full,
            compare_core,
            flags,
            t_to_u,
        ) = _make_sequence_fields(
            sequence_raw=sequence_raw,
            sequence_core_raw=None,
            molecule_type="RNA",
            alphabet_as_reported="DNA_T",
            construct_scope="variable_region",
        )
        _assert_length(clone, sequence_full, D9_DOCUMENTED_LENGTHS[clone])
        if not t_to_u:
            raise LeakageBuildError(f"D9 clone {clone} must apply T→U conversion")
        label = D9_EVALUATION_LABELS[clone]
        out.append(
            ParsedReference(
                reference_id=f"von_laer_2013_{clone.lower()}",
                aptamer_name=clone,
                target_name_raw="NDM-1",
                target_name="NDM-1",
                evaluation_role=(
                    "primary_positive_rna_reference"
                    if clone == "D909"
                    else (
                        "secondary_positive_rna_reference"
                        if label == "secondary_positive"
                        else "pool_nonbinder_or_control"
                    )
                ),
                evaluation_label=label,
                molecule_type="RNA",
                alphabet_as_reported="DNA_T",
                sequence_raw=sequence_raw,
                sequence_full=sequence_full,
                sequence_core=sequence_core,
                sequence_compare_full=compare_full,
                sequence_compare_core=compare_core,
                construct_scope="full_equals_core",
                t_to_u_applied=True,
                source_key=source_key,
                source_record_id=clone,
                publication="von Laer 2013 dissertation",
                source_location="Dissertation Table 6",
                qc_flags=flags,
                notes=(
                    f"D9 RNA clone from selected pool; published DNA-alphabet "
                    f"sequence; source sha256={source_sha[:12]}"
                ),
                reported_length=str(D9_DOCUMENTED_LENGTHS[clone]),
                sequence_scope="variable_region",
            )
        )
    return out


def parse_precision_selex(
    path: Path, *, source_key: str
) -> list[ParsedReference]:
    sheet_rows = _xlsx_sheet_rows(path)
    records: list[ParsedReference] = []
    id_re = re.compile(r"^XK-?(\d+)$", re.IGNORECASE)
    for cells in sheet_rows:
        aptamer_id = (cells.get("A") or "").strip() if cells.get("A") else ""
        match = id_re.match(aptamer_id)
        if not match:
            continue
        core_raw = cells.get("B") or ""
        full_raw = cells.get("D") or ""
        if not str(core_raw).strip():
            raise LeakageBuildError(
                f"Precision-SELEX record {aptamer_id} missing core sequence (column B)"
            )
        # Column D is full construct where present; otherwise full equals core.
        if str(full_raw).strip():
            sequence_raw = str(full_raw)
            core_for_fields = str(core_raw)
            scope = "full_and_core"
        else:
            sequence_raw = str(core_raw)
            core_for_fields = str(core_raw)
            scope = "core_only_as_full"
        (
            sequence_full,
            sequence_core,
            compare_full,
            compare_core,
            flags,
            t_to_u,
        ) = _make_sequence_fields(
            sequence_raw=sequence_raw,
            sequence_core_raw=core_for_fields,
            molecule_type="ssDNA",
            alphabet_as_reported="DNA",
            construct_scope=scope,
        )
        if t_to_u:
            raise LeakageBuildError(
                f"Precision-SELEX {aptamer_id} is ssDNA and must not apply T→U"
            )
        num = int(match.group(1))
        canon_name = f"XK-{num}"
        label = "positive"
        records.append(
            ParsedReference(
                reference_id=f"yu2021_{canon_name.lower().replace('-', '')}",
                aptamer_name=canon_name,
                target_name_raw="KPC-2",
                target_name="KPC-2",
                evaluation_role="positive_kpc2_precision_selex",
                evaluation_label=label,
                molecule_type="ssDNA",
                alphabet_as_reported="DNA",
                sequence_raw=sequence_raw,
                sequence_full=sequence_full,
                sequence_core=sequence_core,
                sequence_compare_full=compare_full,
                sequence_compare_core=compare_core,
                construct_scope=scope,
                t_to_u_applied=False,
                source_key=source_key,
                source_record_id=canon_name,
                publication="Yu et al. 2021 Precision-SELEX",
                source_location="extracted_data.xlsx columns A/B/D",
                qc_flags=flags,
                notes="Observation counts are not affinities; both full and core retained where present.",
                reported_length=str(len(sequence_full)),
                sequence_scope=scope,
            )
        )
    if len(records) != 20:
        raise LeakageBuildError(
            f"Precision-SELEX extraction must yield exactly 20 aptamer IDs; got {len(records)}"
        )
    names = [r.aptamer_name for r in records]
    expected = [f"XK-{i}" for i in range(1, 21)]
    if names != expected:
        raise LeakageBuildError(
            "Precision-SELEX aptamer IDs must be XK-1..XK-20 in ascending order"
        )
    return records


def parse_chen_xk10(
    path: Path, *, source_key: str
) -> list[ParsedReference]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    # Retain only the positive XK10 aptamer core (not primers / negatives / reagents).
    chosen = None
    for row in rows:
        aptamer_id = (row.get("aptamer_id") or "").strip().upper()
        is_binder = (row.get("is_target_binding_aptamer") or "").strip().lower()
        is_neg = (row.get("is_negative_control") or "").strip().lower()
        core = (row.get("core_aptamer_sequence_5to3") or "").strip()
        if "XK10" in aptamer_id.replace("-", "") and is_binder in {
            "yes",
            "true",
            "1",
        } and is_neg in {"no", "false", "0", ""} and core:
            # Prefer unmodified core length 61 over spacer-bearing constructs.
            if chosen is None or aptamer_id == "FAM-XK10":
                chosen = row
                if aptamer_id == "FAM-XK10":
                    break
    if chosen is None:
        raise LeakageBuildError(
            "Chen source did not yield a positive XK10 aptamer record"
        )
    sequence_raw = (chosen.get("core_aptamer_sequence_5to3") or "").strip()
    (
        sequence_full,
        sequence_core,
        compare_full,
        compare_core,
        flags,
        t_to_u,
    ) = _make_sequence_fields(
        sequence_raw=sequence_raw,
        sequence_core_raw=sequence_raw,
        molecule_type="ssDNA",
        alphabet_as_reported="DNA",
        construct_scope="full_equals_core",
    )
    if t_to_u:
        raise LeakageBuildError("Chen XK10 is ssDNA and must not apply T→U")
    _assert_length("Chen XK10", sequence_full, 61)
    return [
        ParsedReference(
            reference_id="chen2020_xk10",
            aptamer_name="XK10",
            target_name_raw=(
                chosen.get("target_name")
                or "KPC-2-expressing Escherichia coli"
            ),
            target_name="KPC-2",
            evaluation_role="duplicate_provenance_xk10",
            evaluation_label="positive",
            molecule_type="ssDNA",
            alphabet_as_reported="DNA",
            sequence_raw=sequence_raw,
            sequence_full=sequence_full,
            sequence_core=sequence_core,
            sequence_compare_full=compare_full,
            sequence_compare_core=compare_core,
            construct_scope="full_equals_core",
            t_to_u_applied=False,
            source_key=source_key,
            source_record_id=(chosen.get("record_id") or "").strip(),
            publication="Chen et al. 2020",
            source_location=(chosen.get("source_location") or "Table 1").strip(),
            qc_flags=flags
            + ["duplicate_provenance", "application_replication_not_independent_selection"],
            notes=(
                "Duplicate provenance for Yu/Precision XK10; not an independent "
                "corroborating experimental selection."
            ),
            action="duplicate_provenance",
            supersedes_record_id="yu2021_xk10",
            reported_length="61",
            sequence_scope="full_length_aptamer_sequence",
        )
    ]


def parse_shi_with_override(
    shi_path: Path,
    override_row: Mapping[str, str] | None,
    *,
    source_key: str,
    si_present: bool,
) -> tuple[list[ParsedReference], list[PendingReference], list[str]]:
    """Reconcile Shi CSV against the authoritative override.

    Returns (resolved_refs, pending_refs, inconsistency_notes).
    """
    notes: list[str] = []
    with shi_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    kpc_row = None
    for row in rows:
        label = (row.get("target_label") or "").strip().upper()
        record_id = (row.get("record_id") or "").strip().lower()
        if "KPC" in label or "kpc2" in record_id:
            kpc_row = row
            break
    if kpc_row is None:
        raise LeakageBuildError("Shi CSV missing KPC-2 KP record")

    csv_seq = (kpc_row.get("sequence_5to3_fam_removed") or "").strip()
    csv_location = (kpc_row.get("source_location") or "").strip()
    cites_s1 = "table s1" in csv_location.lower() or "supporting" in csv_location.lower()
    cites_chen = "chen" in (
        (kpc_row.get("source_reference_cited_in_si") or "")
        + (kpc_row.get("curation_notes") or "")
    ).lower()

    if override_row is None:
        raise LeakageBuildError("Missing authoritative Shi override row")

    override_status = (override_row.get("status") or "").strip()
    override_seq = (override_row.get("sequence_raw") or "").strip()
    override_action = (override_row.get("action") or "").strip()

    # Authoritative path: SI present + override resolved with sequence → treat as
    # XK10 duplicate provenance (not an independent sequence).
    if (
        override_status == "resolved"
        and override_seq
        and si_present
        and cites_s1
    ):
        (
            sequence_full,
            sequence_core,
            compare_full,
            compare_core,
            flags,
            t_to_u,
        ) = _make_sequence_fields(
            sequence_raw=override_seq,
            sequence_core_raw=override_seq,
            molecule_type="ssDNA",
            alphabet_as_reported="DNA",
            construct_scope="full_equals_core",
        )
        if t_to_u:
            raise LeakageBuildError("Shi/XK10 override is ssDNA and must not apply T→U")
        if csv_seq:
            try:
                csv_compare = comparison_form(csv_seq)
            except LeakageMatchingError:
                csv_compare = ""
                notes.append(
                    "Shi CSV sequence failed cleanup; override sequence used"
                )
            if csv_compare and csv_compare != compare_full:
                notes.append(
                    "Shi CSV sequence assignment disagreed with authoritative "
                    "Supporting Table S1 override; override wins"
                )
        ref = ParsedReference(
            reference_id=(override_row.get("reference_id") or "shi2025_kpc2kp").strip(),
            aptamer_name="XK10",
            target_name_raw=(
                override_row.get("target_name_raw") or "KPC-2 KP"
            ).strip(),
            target_name="KPC-2",
            evaluation_role=(
                override_row.get("evaluation_role")
                or "duplicate_provenance_xk10_bacterial_detection"
            ).strip(),
            evaluation_label="positive",
            molecule_type="ssDNA",
            alphabet_as_reported="DNA",
            sequence_raw=override_seq,
            sequence_full=sequence_full,
            sequence_core=sequence_core,
            sequence_compare_full=compare_full,
            sequence_compare_core=compare_core,
            construct_scope="full_equals_core",
            t_to_u_applied=False,
            source_key=source_key,
            source_record_id=(kpc_row.get("record_id") or "").strip(),
            publication=(override_row.get("publication") or "Shi et al. 2025").strip(),
            source_location=(
                override_row.get("source_location") or csv_location
            ).strip(),
            qc_flags=flags
            + [
                "duplicate_provenance",
                "shi_override_applied",
                "application_replication_not_independent_selection",
            ],
            notes=(
                (override_row.get("notes") or "").strip()
                + (
                    " Existing Shi CSV preserved as raw provenance."
                    if notes
                    else " Supporting Table S1 confirms XK10 / Chen provenance."
                )
            ).strip(),
            action=override_action or "override",
            reported_length=(override_row.get("reported_length") or "61").strip(),
            sequence_scope=(
                override_row.get("sequence_scope") or "full_length_aptamer_sequence"
            ).strip(),
        )
        return [ref], [], notes

    # Unsupported assignment without traceable SI → pending extraction.
    notes.append(
        "Shi CSV sequence assignment is not trusted without traceable "
        "Supporting Table S1 proof; authoritative override routes to pending"
    )
    pending = PendingReference(
        reference_id=(override_row.get("reference_id") or "shi2025_kpc2kp").strip(),
        aptamer_name=(
            override_row.get("aptamer_name") or "KPC-2 KP aptamer"
        ).strip(),
        target_name_raw=(
            override_row.get("target_name_raw") or "KPC-2 KP"
        ).strip(),
        evaluation_role=(
            override_row.get("evaluation_role")
            or "duplicate_provenance_xk10_bacterial_detection"
        ).strip(),
        expected_source="Shi et al. 2025 Supporting Information Table S1",
        missing_artefact=(
            "Traceable Supporting Table S1 sequence extraction with exact "
            "source citation"
        ),
        include_in_sequence_leakage=True,
        family_already_protected=(
            "yes_xk10_excluded_via_yu_precision_and_or_chen"
            if cites_chen or (csv_seq and "xk10" in (
                (override_row.get("aptamer_name") or "")
                + (override_row.get("notes") or "")
            ).lower())
            else "unknown"
        ),
        action_needed=(
            "Extract the KPC-2 KP aptamer sequence from Supporting Table S1 "
            "with exact source location; preserve the existing Shi CSV as raw "
            "provenance only."
        ),
        supersedes_record_id=(
            override_row.get("supersedes_record_id") or ""
        ).strip(),
        notes="; ".join(notes),
    )
    return [], [pending], notes


def parse_additions_overrides(
    path: Path,
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if list(reader.fieldnames or []) != list(ADDITIONS_COLUMNS):
            raise LeakageBuildError(
                "additions-and-overrides CSV schema mismatch"
            )
        rows = list(reader)
    if not rows:
        raise LeakageBuildError("additions-and-overrides CSV is empty")

    ids: set[str] = set()
    bool_reprs: set[str] = set()
    by_id: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        reference_id = (row.get("reference_id") or "").strip()
        if not reference_id:
            raise LeakageBuildError(
                f"additions row {index} has empty reference_id"
            )
        if reference_id in ids:
            raise LeakageBuildError(
                f"Duplicate reference_id in additions CSV: {reference_id}"
            )
        ids.add(reference_id)
        record_type = (row.get("record_type") or "").strip()
        action = (row.get("action") or "").strip()
        status = (row.get("status") or "").strip()
        seq = row.get("sequence_raw") or ""
        if record_type not in {"sequence", "dataset"}:
            raise LeakageBuildError(
                f"Invalid record_type for {reference_id}: {record_type}"
            )
        if action not in {"add", "override", "duplicate_provenance"}:
            raise LeakageBuildError(
                f"Invalid action for {reference_id}: {action}"
            )
        leakage_raw = (row.get("include_in_sequence_leakage") or "").strip()
        bool_reprs.add(leakage_raw.lower())
        _parse_bool(leakage_raw, field_name="include_in_sequence_leakage")
        if record_type == "dataset" and seq.strip():
            raise LeakageBuildError(
                f"Dataset row {reference_id} must not carry a sequence"
            )
        if record_type == "sequence":
            if status == "resolved" and not seq.strip():
                raise LeakageBuildError(
                    f"Resolved sequence row {reference_id} missing sequence"
                )
            if status == "pending_sequence_extraction" and seq.strip():
                raise LeakageBuildError(
                    f"Pending sequence row {reference_id} must have empty sequence"
                )
            if status not in {
                "resolved",
                "pending_sequence_extraction",
            }:
                raise LeakageBuildError(
                    f"Unexpected status for sequence row {reference_id}: {status}"
                )
        by_id[reference_id] = row
    # Boolean representation must be consistent (true/false lowercase here).
    if bool_reprs - {"true", "false"}:
        raise LeakageBuildError(
            f"Inconsistent boolean representation in additions CSV: {sorted(bool_reprs)}"
        )
    return rows, by_id


def materialise_addition_row(
    row: Mapping[str, str],
    *,
    skip_reference_ids: set[str],
) -> tuple[
    list[ParsedReference],
    list[DatasetReference],
    list[PendingReference],
]:
    reference_id = (row.get("reference_id") or "").strip()
    if reference_id in skip_reference_ids:
        return [], [], []

    record_type = (row.get("record_type") or "").strip()
    status = (row.get("status") or "").strip()
    include = _parse_bool(
        row.get("include_in_sequence_leakage") or "",
        field_name="include_in_sequence_leakage",
    )

    if record_type == "dataset":
        if include:
            raise LeakageBuildError(
                f"Dataset-level record {reference_id} must not enter the sequence leakage set"
            )
        return (
            [],
            [
                DatasetReference(
                    reference_id=reference_id,
                    source_key=(row.get("source_key") or "").strip(),
                    publication=(row.get("publication") or "").strip(),
                    target_name_raw=(row.get("target_name_raw") or "").strip(),
                    evaluation_role=(row.get("evaluation_role") or "").strip(),
                    source_location=(row.get("source_location") or "").strip(),
                    selection_rounds=(row.get("selection_rounds") or "").strip(),
                    status=status,
                    include_in_sequence_leakage=False,
                    notes=(row.get("notes") or "").strip(),
                )
            ],
            [],
        )

    if status == "pending_sequence_extraction":
        return (
            [],
            [],
            [
                PendingReference(
                    reference_id=reference_id,
                    aptamer_name=(row.get("aptamer_name") or "").strip(),
                    target_name_raw=(row.get("target_name_raw") or "").strip(),
                    evaluation_role=(row.get("evaluation_role") or "").strip(),
                    expected_source=(row.get("source_location") or "").strip(),
                    missing_artefact="Exact source sequence extraction",
                    include_in_sequence_leakage=include,
                    family_already_protected="unknown",
                    action_needed=(
                        "Obtain the exact sequence from the cited supplement or "
                        "source location and re-run S0b."
                    ),
                    supersedes_record_id=(
                        row.get("supersedes_record_id") or ""
                    ).strip(),
                    notes=(row.get("notes") or "").strip(),
                )
            ],
        )

    sequence_raw = row.get("sequence_raw") or ""
    molecule_type = (row.get("molecule_type") or "").strip()
    alphabet = (row.get("alphabet_as_reported") or "").strip()
    scope = (row.get("sequence_scope") or "").strip()
    aptamer_name = (row.get("aptamer_name") or "").strip()
    core_unresolved = "patent" in reference_id or "cn10" in reference_id
    # Patents: retain disclosed complete form; core unresolved unless documented.
    if reference_id in {"cn108949766b_apnv"}:
        core_unresolved = False
    if reference_id == "cn102965377b_seq1":
        core_unresolved = True

    (
        sequence_full,
        sequence_core,
        compare_full,
        compare_core,
        flags,
        t_to_u,
    ) = _make_sequence_fields(
        sequence_raw=sequence_raw,
        sequence_core_raw=None,
        molecule_type=molecule_type,
        alphabet_as_reported=alphabet or "DNA",
        construct_scope=scope or "full",
        core_unresolved=core_unresolved,
    )
    if molecule_type.upper() in {"SSDNA", "DNA"} and t_to_u:
        raise LeakageBuildError(
            f"{reference_id} is ssDNA and must not apply T→U"
        )

    # Hard length gates for named controls / patents.
    length_gates = {
        "cn108949766b_apnv": ("APNV", 35),
        "cn102965377b_seq1": ("CN102965377B SEQ ID NO:1", 88),
        "sabrowski2022_ndm1_h14_01": ("H14-01", 80),
        "sabrowski2022_ndm1_h14_01_fr": ("H14-01-FR", 44),
        "sabrowski2022_ndm1_h14_2_43": ("H14.2_43", 80),
    }
    if reference_id in length_gates:
        label, expected = length_gates[reference_id]
        _assert_length(label, sequence_full, expected)

    role = (row.get("evaluation_role") or "").strip()
    label = _label_from_role(role, aptamer_name)
    target_raw = (row.get("target_name_raw") or "").strip()
    target_name = _canonical_target(target_raw)

    # Source-specific label assertions.
    if reference_id == "sabrowski2022_ndm1_h14_01":
        label = "tag_binding_control"
    elif reference_id == "sabrowski2022_ndm1_h14_01_fr":
        label = "masking_control"
    elif reference_id == "cn108949766b_apnv":
        label = "cross_binding_positive"
        target_name = "NDM-1|VIM-2"

    return (
        [
            ParsedReference(
                reference_id=reference_id,
                aptamer_name=aptamer_name,
                target_name_raw=target_raw,
                target_name=target_name,
                evaluation_role=role,
                evaluation_label=label,
                molecule_type=molecule_type,
                alphabet_as_reported=alphabet or "DNA",
                sequence_raw=sequence_raw,
                sequence_full=sequence_full,
                sequence_core=sequence_core,
                sequence_compare_full=compare_full,
                sequence_compare_core=compare_core,
                construct_scope=scope or "full",
                t_to_u_applied=t_to_u,
                source_key=(row.get("source_key") or "").strip(),
                source_record_id=reference_id,
                publication=(row.get("publication") or "").strip(),
                source_location=(row.get("source_location") or "").strip(),
                qc_flags=flags,
                notes=(row.get("notes") or "").strip(),
                include_in_sequence_leakage=include,
                action=(row.get("action") or "add").strip(),
                reported_length=(row.get("reported_length") or "").strip(),
                sequence_scope=scope,
                supersedes_record_id=(
                    row.get("supersedes_record_id") or ""
                ).strip(),
            )
        ],
        [],
        [],
    )


def _label_from_role(role: str, aptamer_name: str) -> str:
    text = f"{role} {aptamer_name}".lower()
    if "mask" in text:
        return "masking_control"
    if "his_tag" in text or "his-tag" in text or (
        "his" in text and "negative_control" in text
    ):
        return "tag_binding_control"
    if "cross" in text or "vim2" in text or "vim-2" in text:
        return "cross_binding_positive"
    if "secondary" in text:
        return "secondary_positive"
    # "positive_control_*" means a positive evaluation reference, not a non-binder.
    if "positive" in text:
        return "positive"
    if "negative" in text or "nonbinder" in text or "non-binder" in text:
        return "pool_nonbinder"
    return "positive"


def _xk10_merge_key(ref: ParsedReference) -> str | None:
    name = ref.aptamer_name.upper().replace("-", "")
    if name in {"XK10", "XK10"} or name == "XK10":
        return "XK10|KPC-2"
    if "XK10" in name:
        return "XK10|KPC-2"
    if ref.reference_id in {
        "yu2021_xk10",
        "chen2020_xk10",
        "shi2025_kpc2kp",
    }:
        return "XK10|KPC-2"
    return None


def deduplicate_references(
    refs: list[ParsedReference],
) -> tuple[list[ParsedReference], list[str], int]:
    """Deduplicate by compare_full + compare_core + target_name; merge provenance."""
    groups: dict[str, ParsedReference] = {}
    order: list[str] = []
    sequence_only_dup_notes: list[str] = []
    merge_count = 0
    seq_index: dict[str, list[str]] = {}

    for ref in refs:
        if not ref.include_in_sequence_leakage:
            continue
        if ref.record_type == "dataset":
            raise LeakageBuildError(
                f"Dataset-level record {ref.reference_id} entered sequence leakage set"
            )
        xk_key = _xk10_merge_key(ref)
        key = xk_key or (
            f"{ref.sequence_compare_full}|{ref.sequence_compare_core}|{ref.target_name}"
        )
        seq_only = f"{ref.sequence_compare_full}|{ref.sequence_compare_core}"
        seq_index.setdefault(seq_only, []).append(ref.target_name)

        if key not in groups:
            groups[key] = ref
            order.append(key)
            continue
        merge_count += 1
        primary = groups[key]
        for src in ref.contributing_sources:
            if src not in primary.contributing_sources:
                primary.contributing_sources.append(src)
        for pub in ref.contributing_publications:
            if pub not in primary.contributing_publications:
                primary.contributing_publications.append(pub)
        for flag in ref.qc_flags:
            if flag not in primary.qc_flags:
                primary.qc_flags.append(flag)
        # Prefer Yu/Precision as primary XK10 reference_id when merging.
        if xk_key:
            if primary.reference_id.startswith("yu2021") is False and (
                ref.reference_id.startswith("yu2021")
            ):
                # Swap identity toward Yu while retaining merged provenance.
                ref.contributing_sources = list(
                    dict.fromkeys(
                        ref.contributing_sources + primary.contributing_sources
                    )
                )
                ref.contributing_publications = list(
                    dict.fromkeys(
                        ref.contributing_publications
                        + primary.contributing_publications
                    )
                )
                ref.qc_flags = list(
                    dict.fromkeys(ref.qc_flags + primary.qc_flags)
                )
                ref.notes = (
                    (primary.notes + " | " if primary.notes else "")
                    + (ref.notes or "")
                ).strip(" |")
                groups[key] = ref
            else:
                primary.notes = (
                    (primary.notes + " | " if primary.notes else "")
                    + f"merged_provenance:{ref.reference_id}"
                    + (f" ({ref.notes})" if ref.notes else "")
                ).strip()
            if "merged_duplicate_provenance" not in primary.qc_flags:
                primary.qc_flags.append("merged_duplicate_provenance")
        else:
            primary.notes = (
                (primary.notes + " | " if primary.notes else "")
                + f"merged_provenance:{ref.reference_id}"
            ).strip()
            if "merged_duplicate_provenance" not in primary.qc_flags:
                primary.qc_flags.append("merged_duplicate_provenance")

    for seq_key, targets in seq_index.items():
        uniq = sorted(set(targets))
        if len(uniq) > 1:
            sequence_only_dup_notes.append(
                f"sequence-only duplicate across targets={uniq}"
            )

    return [groups[k] for k in order], sequence_only_dup_notes, merge_count


def _exclusion_id_for(ref: ParsedReference, index: int) -> str:
    digest = hashlib.sha256(
        f"{ref.sequence_compare_full}|{ref.sequence_compare_core}|{ref.target_name}|{ref.aptamer_name}".encode(
            "utf-8"
        )
    ).hexdigest()[:12]
    return f"lex_{index:04d}_{digest}"


def references_to_leakage_rows(
    refs: list[ParsedReference],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, ref in enumerate(refs, start=1):
        exclusion_id = _exclusion_id_for(ref, index)
        if exclusion_id in seen_ids:
            raise LeakageBuildError("Duplicate exclusion_id generated")
        seen_ids.add(exclusion_id)
        rows.append(
            {
                "exclusion_id": exclusion_id,
                "reference_id": ref.reference_id,
                "aptamer_name": ref.aptamer_name,
                "target_name_raw": ref.target_name_raw,
                "target_name": ref.target_name,
                "evaluation_role": ref.evaluation_role,
                "evaluation_label": ref.evaluation_label,
                "molecule_type": ref.molecule_type,
                "alphabet_as_reported": ref.alphabet_as_reported,
                "sequence_raw": ref.sequence_raw,
                "sequence_full": ref.sequence_full,
                "sequence_core": ref.sequence_core,
                "sequence_compare_full": ref.sequence_compare_full,
                "sequence_compare_core": ref.sequence_compare_core,
                "sequence_length_full": str(len(ref.sequence_full)),
                "sequence_length_core": str(len(ref.sequence_core)),
                "construct_scope": ref.construct_scope,
                "t_to_u_applied": _bool_str(ref.t_to_u_applied),
                "source_key": ref.source_key,
                "source_record_id": ref.source_record_id,
                "publication": ref.publication,
                "source_location": ref.source_location,
                "contributing_sources": _join_unique(ref.contributing_sources),
                "contributing_publications": _join_unique(
                    ref.contributing_publications
                ),
                "status": "resolved",
                "qc_flags": "|".join(ref.qc_flags),
                "notes": ref.notes,
            }
        )
    return rows


def build_leakage_exclusion(
    repo_root: Path,
    registry_spec: Path,
    target_aliases_path: Path,
    output_dir: Path,
) -> BuildResult:
    spec_rows = load_registry_spec(registry_spec)
    by_key = {row.source_key: row for row in spec_rows}
    missing = sorted(S0B_SOURCE_KEYS - set(by_key))
    if missing:
        raise LeakageBuildError(
            f"Registry missing required S0b source_key(s): {missing}"
        )

    # Validate registered S0b inputs (and all registry rows for consistency).
    for row in spec_rows:
        try:
            validate_registered_file(repo_root, row)
        except RegistryError as exc:
            raise LeakageBuildError(str(exc)) from exc

    aliases = load_target_aliases(target_aliases_path)
    source_hashes = {
        key: by_key[key].sha256 for key in sorted(S0B_SOURCE_KEYS)
    }

    d9_path = repo_root / by_key["von_laer_2013_d9_table6"].path
    precision_path = repo_root / by_key["yu_2021_precision_selex_xlsx"].path
    chen_path = repo_root / by_key["chen_2020_xk10_csv"].path
    shi_path = repo_root / by_key["shi_2025_kpc2kp_csv"].path
    additions_path = repo_root / by_key["carbapenemase_additions_overrides"].path

    # Capture pre-run hashes for immutability checks by the caller.
    input_hashes = {
        str(p.relative_to(repo_root)): sha256_file(p)
        for p in (d9_path, precision_path, chen_path, shi_path, additions_path)
    }

    addition_rows, additions_by_id = parse_additions_overrides(additions_path)
    shi_override = additions_by_id.get("shi2025_kpc2kp")
    si_shi = (
        repo_root
        / "data/raw/evaluation_references/source_documents/shi_2025_supplementary.pdf"
    ).is_file()

    parsed: list[ParsedReference] = []
    datasets: list[DatasetReference] = []
    pending: list[PendingReference] = []
    inconsistency_notes: list[str] = []

    parsed.extend(
        parse_d9(
            d9_path,
            source_key="von_laer_2013_d9_table6",
            source_sha=source_hashes["von_laer_2013_d9_table6"],
        )
    )
    parsed.extend(
        parse_precision_selex(
            precision_path, source_key="yu_2021_precision_selex_xlsx"
        )
    )
    parsed.extend(
        parse_chen_xk10(chen_path, source_key="chen_2020_xk10_csv")
    )
    shi_refs, shi_pending, shi_notes = parse_shi_with_override(
        shi_path,
        shi_override,
        source_key="shi_2025_kpc2kp_csv",
        si_present=si_shi,
    )
    parsed.extend(shi_refs)
    pending.extend(shi_pending)
    inconsistency_notes.extend(shi_notes)

    # Materialise additions except Shi (handled above) and Chen duplicate row
    # when Chen CSV already contributed (still keep additions chen row as
    # provenance merge via skip only if identical handling already done).
    skip_ids = {"shi2025_kpc2kp"}
    # Chen additions row is duplicate_provenance; still materialise so merge
    # captures additions source_key if CSV parse already added chen2020_xk10.
    for row in addition_rows:
        refs, dsets, pend = materialise_addition_row(
            row, skip_reference_ids=skip_ids
        )
        # Avoid double-adding an identical Chen sequence row with same reference_id
        # when CSV parse already produced chen2020_xk10 — merge path handles it.
        parsed.extend(refs)
        datasets.extend(dsets)
        pending.extend(pend)

    # Ensure every additions sequence/dataset/pending row was accounted for.
    accounted = (
        {r.reference_id for r in parsed}
        | {d.reference_id for d in datasets}
        | {p.reference_id for p in pending}
        | skip_ids
    )
    # Shi pending uses same id; if resolved via override, id is in parsed.
    for row in addition_rows:
        rid = (row.get("reference_id") or "").strip()
        if rid not in accounted and rid not in skip_ids:
            raise LeakageBuildError(
                f"Pending/additions reference silently omitted: {rid}"
            )
    # If Shi was skipped from materialise but neither parsed nor pending, fail.
    if "shi2025_kpc2kp" not in (
        {r.reference_id for r in parsed} | {p.reference_id for p in pending}
    ):
        raise LeakageBuildError(
            "Shi reference silently omitted from resolved and pending outputs"
        )

    deduped, seq_only_notes, merge_count = deduplicate_references(parsed)
    leakage_rows = references_to_leakage_rows(deduped)

    # Manifest covers all resolved evaluation sequence references (pre-dedup
    # identity retained via contributing sources on leakage rows) plus pending
    # and dataset pointers without sequences for pending.
    exclusion_by_ref = {r["reference_id"]: r["exclusion_id"] for r in leakage_rows}
    # Map merged contributors back to exclusion ids via compare key.
    compare_to_excl = {
        (
            r["sequence_compare_full"],
            r["sequence_compare_core"],
            r["target_name"],
        ): r["exclusion_id"]
        for r in leakage_rows
    }
    for r in leakage_rows:
        # Also index XK10 family by aptamer.
        if "XK10" in r["aptamer_name"].upper().replace("-", ""):
            compare_to_excl[("XK10", "XK10", "KPC-2")] = r["exclusion_id"]

    manifest_rows: list[dict[str, str]] = []
    for ref in parsed:
        excl = exclusion_by_ref.get(ref.reference_id, "")
        if not excl:
            excl = compare_to_excl.get(
                (
                    ref.sequence_compare_full,
                    ref.sequence_compare_core,
                    ref.target_name,
                ),
                "",
            )
        if not excl and _xk10_merge_key(ref):
            excl = compare_to_excl.get(("XK10", "XK10", "KPC-2"), "")
        manifest_rows.append(
            {
                "reference_id": ref.reference_id,
                "record_type": "sequence",
                "aptamer_name": ref.aptamer_name,
                "target_name_raw": ref.target_name_raw,
                "target_name": ref.target_name,
                "evaluation_role": ref.evaluation_role,
                "evaluation_label": ref.evaluation_label,
                "molecule_type": ref.molecule_type,
                "alphabet_as_reported": ref.alphabet_as_reported,
                "sequence_scope": ref.sequence_scope or ref.construct_scope,
                "reported_length": ref.reported_length
                or str(len(ref.sequence_full)),
                "source_key": ref.source_key,
                "publication": ref.publication,
                "source_location": ref.source_location,
                "include_in_sequence_leakage": _bool_str(
                    ref.include_in_sequence_leakage
                ),
                "status": "resolved",
                "exclusion_id": excl,
                "contributing_sources": _join_unique(ref.contributing_sources),
                "notes": ref.notes,
            }
        )
    for pend in pending:
        manifest_rows.append(
            {
                "reference_id": pend.reference_id,
                "record_type": "sequence",
                "aptamer_name": pend.aptamer_name,
                "target_name_raw": pend.target_name_raw,
                "target_name": _canonical_target(pend.target_name_raw),
                "evaluation_role": pend.evaluation_role,
                "evaluation_label": "",
                "molecule_type": "",
                "alphabet_as_reported": "",
                "sequence_scope": "",
                "reported_length": "",
                "source_key": "",
                "publication": "",
                "source_location": pend.expected_source,
                "include_in_sequence_leakage": _bool_str(
                    pend.include_in_sequence_leakage
                ),
                "status": "pending_sequence_extraction",
                "exclusion_id": "",
                "contributing_sources": "",
                "notes": pend.notes,
            }
        )

    dataset_rows = [
        {
            "reference_id": d.reference_id,
            "source_key": d.source_key,
            "publication": d.publication,
            "target_name_raw": d.target_name_raw,
            "evaluation_role": d.evaluation_role,
            "source_location": d.source_location,
            "selection_rounds": d.selection_rounds,
            "status": d.status,
            "include_in_sequence_leakage": "false",
            "notes": d.notes,
        }
        for d in datasets
    ]
    pending_rows = [
        {
            "reference_id": p.reference_id,
            "aptamer_name": p.aptamer_name,
            "target_name_raw": p.target_name_raw,
            "evaluation_role": p.evaluation_role,
            "expected_source": p.expected_source,
            "missing_artefact": p.missing_artefact,
            "include_in_sequence_leakage": _bool_str(p.include_in_sequence_leakage),
            "family_already_protected": p.family_already_protected,
            "action_needed": p.action_needed,
            "supersedes_record_id": p.supersedes_record_id,
            "notes": p.notes,
        }
        for p in pending
    ]

    # Source-specific hard assertions on leakage output.
    _assert_source_specific(leakage_rows)

    positive_labels = {
        "positive",
        "secondary_positive",
        "cross_binding_positive",
    }
    control_labels = {
        "pool_nonbinder",
        "tag_binding_control",
        "masking_control",
    }
    n_positive = sum(
        1 for r in leakage_rows if r["evaluation_label"] in positive_labels
    )
    n_control = sum(
        1 for r in leakage_rows if r["evaluation_label"] in control_labels
    )
    n_full_core_distinct = sum(
        1
        for r in leakage_rows
        if r["sequence_compare_full"] != r["sequence_compare_core"]
    )
    n_dna = sum(
        1
        for r in leakage_rows
        if r["molecule_type"].upper() in {"SSDNA", "DNA"}
    )
    n_rna = sum(1 for r in leakage_rows if r["molecule_type"].upper() == "RNA")

    incomplete = len(pending_rows) > 0
    aggregates = {
        "source_files_validated": len(S0B_SOURCE_KEYS),
        "source_records_read": len(parsed) + len(datasets) + len(pending),
        "resolved_evaluation_records": len(parsed),
        "unique_sequence_exclusions": len(leakage_rows),
        "records_with_distinct_full_core": n_full_core_distinct,
        "dna_records": n_dna,
        "rna_records": n_rna,
        "positive_references": n_positive,
        "negative_or_control_references": n_control,
        "merged_duplicate_provenance_groups": merge_count,
        "dataset_level_references": len(dataset_rows),
        "pending_sequence_extractions": len(pending_rows),
        "target_alias_rows": len(aliases),
        "sequence_only_cross_target_notes": len(seq_only_notes),
        "inconsistency_notes": inconsistency_notes,
        "input_hashes": input_hashes,
        "incomplete": incomplete,
    }

    report = _render_report(
        aggregates=aggregates,
        pending_rows=pending_rows,
        seq_only_notes=seq_only_notes,
        alias_count=len(aliases),
        output_dir=output_dir,
        repo_root=repo_root,
    )

    # Write outputs atomically.
    leakage_path = repo_root / "data" / "interim" / "leakage_exclusion_set.csv"
    manifest_path = output_dir / "evaluation_reference_manifest.csv"
    dataset_path = output_dir / "reference_dataset_manifest.csv"
    pending_path = output_dir / "pending_reference_extractions.csv"
    report_path = output_dir / "leakage_build_report.md"

    for path in (
        leakage_path,
        manifest_path,
        dataset_path,
        pending_path,
        report_path,
    ):
        _refuse_raw_output(path, repo_root)

    # Deterministic ordering.
    leakage_rows_sorted = sorted(
        leakage_rows,
        key=lambda r: (
            r["target_name"],
            r["aptamer_name"],
            r["exclusion_id"],
        ),
    )
    # Reassign exclusion ids after sort for stable lex_0001.. order while
    # keeping content hash suffix.
    for index, row in enumerate(leakage_rows_sorted, start=1):
        digest = row["exclusion_id"].split("_")[-1]
        row["exclusion_id"] = f"lex_{index:04d}_{digest}"
    # Refresh manifest exclusion ids after renumbering.
    excl_lookup = {
        (r["sequence_compare_full"], r["sequence_compare_core"], r["target_name"]): r[
            "exclusion_id"
        ]
        for r in leakage_rows_sorted
    }
    xk_excl = next(
        (
            r["exclusion_id"]
            for r in leakage_rows_sorted
            if r["aptamer_name"].upper().replace("-", "") in {"XK10", "XK10"}
            or r["reference_id"].startswith("yu2021_xk10")
        ),
        "",
    )
    for m in manifest_rows:
        if m["status"] != "resolved":
            continue
        # Prefer matching leakage row reference_id.
        match = next(
            (
                r["exclusion_id"]
                for r in leakage_rows_sorted
                if r["reference_id"] == m["reference_id"]
            ),
            "",
        )
        if not match and "XK10" in m["aptamer_name"].upper().replace("-", ""):
            match = xk_excl
        if not match:
            # Fall back via contributing merge targets already in leakage set.
            for r in leakage_rows_sorted:
                if m["reference_id"] in r["notes"] or m["source_key"] in r[
                    "contributing_sources"
                ].split("|"):
                    if m["aptamer_name"].upper().replace("-", "") == r[
                        "aptamer_name"
                    ].upper().replace("-", ""):
                        match = r["exclusion_id"]
                        break
        m["exclusion_id"] = match

    manifest_rows_sorted = sorted(
        manifest_rows, key=lambda r: (r["status"], r["reference_id"])
    )
    dataset_rows_sorted = sorted(dataset_rows, key=lambda r: r["reference_id"])
    pending_rows_sorted = sorted(pending_rows, key=lambda r: r["reference_id"])

    _atomic_write_csv(leakage_path, LEAKAGE_COLUMNS, leakage_rows_sorted)
    _atomic_write_csv(manifest_path, MANIFEST_COLUMNS, manifest_rows_sorted)
    _atomic_write_csv(dataset_path, DATASET_COLUMNS, dataset_rows_sorted)
    _atomic_write_csv(pending_path, PENDING_COLUMNS, pending_rows_sorted)
    _atomic_write_text(report_path, report)

    # Verify inputs unchanged.
    for rel, expected in input_hashes.items():
        actual = sha256_file(repo_root / rel)
        if actual != expected:
            raise LeakageBuildError(
                f"Input file changed during S0b build: {rel}"
            )

    aggregates["output_paths"] = {
        "leakage_exclusion_set": _rel_display(leakage_path, repo_root),
        "evaluation_reference_manifest": _rel_display(manifest_path, repo_root),
        "reference_dataset_manifest": _rel_display(dataset_path, repo_root),
        "pending_reference_extractions": _rel_display(pending_path, repo_root),
        "leakage_build_report": _rel_display(report_path, repo_root),
    }
    return BuildResult(
        leakage_rows=leakage_rows_sorted,
        manifest_rows=manifest_rows_sorted,
        dataset_rows=dataset_rows_sorted,
        pending_rows=pending_rows_sorted,
        report_markdown=report,
        aggregates=aggregates,
        incomplete=incomplete,
    )


def _assert_source_specific(leakage_rows: list[dict[str, str]]) -> None:
    by_name = {r["aptamer_name"]: r for r in leakage_rows}
    d9 = [r for r in leakage_rows if r["aptamer_name"] in EXPECTED_D9_IDS]
    if len(d9) != 7:
        raise LeakageBuildError(
            f"Expected all seven D9 clones in leakage set; found {len(d9)}"
        )
    for row in d9:
        if row["molecule_type"] != "RNA":
            raise LeakageBuildError("D9 records must be molecule_type=RNA")
        if row["alphabet_as_reported"] != "DNA_T":
            raise LeakageBuildError(
                "D9 records must be alphabet_as_reported=DNA_T"
            )
        if row["t_to_u_applied"] != "true":
            raise LeakageBuildError("D9 records must have t_to_u_applied=true")

    for row in leakage_rows:
        mol = row["molecule_type"].upper()
        if mol in {"SSDNA", "DNA"} and row["t_to_u_applied"] != "false":
            raise LeakageBuildError(
                "Genuine ssDNA must have t_to_u_applied=false"
            )

    xk = [
        r
        for r in leakage_rows
        if r["aptamer_name"].upper().replace("-", "") == "XK10"
    ]
    if len(xk) != 1:
        raise LeakageBuildError(
            f"XK10 must merge to one leakage row; found {len(xk)}"
        )
    sources = set(xk[0]["contributing_sources"].split("|"))
    if not any("yu_2021" in s or "precision" in s for s in sources):
        # Primary may be yu source_key.
        if "yu_2021_precision_selex_xlsx" not in sources and not xk[0][
            "reference_id"
        ].startswith("yu2021"):
            raise LeakageBuildError(
                "XK10 merge must retain Yu/Precision provenance"
            )
    if "chen_2020_xk10_csv" not in sources and "chen2020" not in xk[0]["notes"]:
        # Chen may appear only via merged notes / contributing sources.
        if "chen_2020_xk10_csv" not in sources:
            raise LeakageBuildError(
                "XK10 merge must retain Chen duplicate provenance"
            )

    apnv = by_name.get("APNV")
    if apnv is None:
        raise LeakageBuildError("APNV missing from leakage set")
    if "NDM-1" not in apnv["target_name"] or "VIM-2" not in apnv["target_name"]:
        raise LeakageBuildError(
            "APNV target must include both NDM-1 and VIM-2 provenance"
        )

    h14 = by_name.get("NDM1-H14-01")
    if h14 is None or h14["evaluation_label"] != "tag_binding_control":
        raise LeakageBuildError(
            "H14-01 must be labelled as a HIS-tag control"
        )
    h14fr = by_name.get("NDM1-H14-01-FR")
    if h14fr is None or h14fr["evaluation_label"] != "masking_control":
        raise LeakageBuildError(
            "H14-01-FR must be labelled as a masking control"
        )


def _render_report(
    *,
    aggregates: Mapping[str, Any],
    pending_rows: Sequence[Mapping[str, str]],
    seq_only_notes: Sequence[str],
    alias_count: int,
    output_dir: Path,
    repo_root: Path,
) -> str:
    lines = [
        "# S0b leakage-exclusion build report",
        "",
        "Aggregate information only — no source sequences.",
        "",
        "## Summary",
        "",
        f"- Source files validated: {aggregates['source_files_validated']}",
        f"- Source records read: {aggregates['source_records_read']}",
        f"- Resolved evaluation records: {aggregates['resolved_evaluation_records']}",
        f"- Unique sequence-level exclusions: {aggregates['unique_sequence_exclusions']}",
        f"- Records with distinct full/core forms: {aggregates['records_with_distinct_full_core']}",
        f"- DNA records: {aggregates['dna_records']}",
        f"- RNA records: {aggregates['rna_records']}",
        f"- Positive references: {aggregates['positive_references']}",
        f"- Negative/control references: {aggregates['negative_or_control_references']}",
        f"- Merged duplicate-provenance groups: {aggregates['merged_duplicate_provenance_groups']}",
        f"- Dataset-level references: {aggregates['dataset_level_references']}",
        f"- Pending sequence extractions: {aggregates['pending_sequence_extractions']}",
        f"- Target-alias rows: {alias_count}",
        "",
        "## Sequence comparison policy",
        "",
        "- Display cleanup removes whitespace, terminal 5′/3′ marks, and alignment gaps.",
        "- Identity uses global Levenshtein edit distance: "
        "`1 - edit_distance / max(len_a, len_b)`.",
        "- Comparison representation collapses U→T so DNA/RNA T↔U equivalents have identity 1.0.",
        "- Threshold for later merge matching: 0.90.",
        "- No local substring matching; no automatic promoter/primer trimming.",
        "- Genuine ssDNA is never converted to RNA.",
        "",
        "## Pending references",
        "",
    ]
    if not pending_rows:
        lines.append(
            "None. All required evaluation-reference sequences are resolved."
        )
    else:
        for row in pending_rows:
            lines.extend(
                [
                    f"### {row['reference_id']}",
                    "",
                    f"- Expected source: {row['expected_source']}",
                    f"- Missing artefact: {row['missing_artefact']}",
                    f"- Target: {row['target_name_raw']}",
                    f"- Intended evaluation role: {row['evaluation_role']}",
                    f"- Family already protected: {row['family_already_protected']}",
                    f"- Action needed: {row['action_needed']}",
                    "",
                ]
            )
        lines.append(
            "S0b implementation is operational, but S0 remains incomplete "
            "pending source-sequence extraction."
        )
    lines.extend(
        [
            "",
            "## Cross-target sequence-only duplicates",
            "",
        ]
    )
    if seq_only_notes:
        for note in seq_only_notes:
            lines.append(f"- {note}")
    else:
        lines.append("- None reported.")
    lines.extend(
        [
            "",
            "## Output paths",
            "",
            f"- `{_rel_display(repo_root / 'data/interim/leakage_exclusion_set.csv', repo_root)}`",
            f"- `{_rel_display(output_dir / 'evaluation_reference_manifest.csv', repo_root)}`",
            f"- `{_rel_display(output_dir / 'reference_dataset_manifest.csv', repo_root)}`",
            f"- `{_rel_display(output_dir / 'pending_reference_extractions.csv', repo_root)}`",
            f"- `{_rel_display(output_dir / 'leakage_build_report.md', repo_root)}`",
            "",
            f"Incomplete: {str(bool(aggregates['incomplete'])).lower()}",
            "",
        ]
    )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "S0b: build evaluation-reference manifests and the leakage-exclusion set."
        )
    )
    parser.add_argument(
        "--registry-spec",
        type=Path,
        default=None,
        help="Tracked registry specification (default: config/source_registry.csv)",
    )
    parser.add_argument(
        "--target-aliases",
        type=Path,
        default=None,
        help=(
            "Tracked target-alias CSV "
            "(default: config/leakage_target_aliases.csv)"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Evaluation interim output directory "
            "(default: data/interim/evaluation)"
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

        def under_repo(path: Path | None, default: Path) -> Path:
            if path is None:
                return default
            return path if path.is_absolute() else (repo_root / path).resolve()

        registry_spec = under_repo(
            args.registry_spec, repo_root / "config" / "source_registry.csv"
        )
        target_aliases = under_repo(
            args.target_aliases,
            repo_root / "config" / "leakage_target_aliases.csv",
        )
        output_dir = under_repo(
            args.output_dir, repo_root / "data" / "interim" / "evaluation"
        )

        result = build_leakage_exclusion(
            repo_root=repo_root,
            registry_spec=registry_spec,
            target_aliases_path=target_aliases,
            output_dir=output_dir,
        )
    except (LeakageBuildError, RegistryError) as exc:
        # Never print sequences; exception messages are metadata-only by construction.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    agg = result.aggregates
    print(
        "S0b leakage build OK: "
        f"sources_validated={agg['source_files_validated']} "
        f"records_read={agg['source_records_read']} "
        f"resolved={agg['resolved_evaluation_records']} "
        f"unique_exclusions={agg['unique_sequence_exclusions']} "
        f"full_core_distinct={agg['records_with_distinct_full_core']} "
        f"dna={agg['dna_records']} rna={agg['rna_records']} "
        f"positive={agg['positive_references']} "
        f"controls={agg['negative_or_control_references']} "
        f"merged_groups={agg['merged_duplicate_provenance_groups']} "
        f"datasets={agg['dataset_level_references']} "
        f"pending={agg['pending_sequence_extractions']} "
        f"incomplete={str(result.incomplete).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

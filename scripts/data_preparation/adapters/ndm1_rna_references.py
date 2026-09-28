"""NDM-1 RNA D9 reference verification (not a corpus-curation stage).

Independently transcribes von Laer 2013 dissertation Table 6, checks that
transcription against the machine-readable CSV, and writes an enriched RNA
reference layer. Does not modify frozen partitions, S0b outputs, or S7D
authorities, and does not add duplicate leakage records.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from adapters.s4_scientific_common import write_json_atomic, write_text_atomic
from adapters.s5_validate_exact_dedup import scan_text_for_sequence_leak
from adapters.target_extraction_common import SEQ_LEAK_RE
from common.leakage_matching import (
    IDENTITY_THRESHOLD,
    comparison_form,
    global_edit_identity,
)
from s0_build_registry import find_repo_root, load_registry_spec, sha256_file

EXPECTED_CLONE_IDS: tuple[str, ...] = (
    "D902",
    "D907",
    "D909",
    "D913",
    "D914",
    "D918",
    "D920",
)
TABLE6_ROW_RE = re.compile(
    r"(D902|D907|D909|D913|D914|D918|D920)\s+([ACGT-]+)\s+(\d+%)\s+(\d+%)"
)
REPORTED_RE = re.compile(r"^[ACGT-]+$")
CLEANED_RE = re.compile(r"^[ACGT]+$")
XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
POSITIVE_STATUSES = frozenset({"positive_strongest", "positive_secondary"})
WEAK_STATUSES = frozenset({"weak_binding"})
NEGATIVE_STATUSES = frozenset({"no_detectable_binding"})
ABSENT_FILE = "absent"
NOT_A_REGULAR_FILE = "not_a_regular_file"

REFERENCE_COLUMNS: tuple[str, ...] = (
    "reference_id",
    "clone_id",
    "molecule_type",
    "source_reported_alphabet",
    "sequence_reported_raw",
    "sequence_cleaned_source",
    "sequence_canonical_rna",
    "reported_length",
    "cleaned_length",
    "canonical_length",
    "trailing_gap_count",
    "reported_sha256",
    "cleaned_source_sha256",
    "canonical_rna_sha256",
    "t_to_u_applied",
    "purine_percent_reported",
    "gc_percent_reported",
    "source_filename",
    "source_sha256",
    "source_table",
    "pdf_page",
    "dissertation_page",
    "target",
    "selection_pool",
    "selection_round",
    "selection_method",
    "clone_frequency",
    "clone_frequency_support",
    "qualitative_binding_status",
    "evidence_strength",
    "assay_type",
    "concentration_threshold_or_range",
    "quantitative_affinity_reported",
    "affinity_type",
    "affinity_value",
    "scientific_limitations",
    "legacy_s0b_reference_id",
    "legacy_s0b_evaluation_label",
    "legacy_s0b_evaluation_role",
    "legacy_exclusion_id",
    "legacy_discrepancy_code",
    "sequence_comparison_role",
    "include_in_sequence_comparison",
    "similarity_is_not_binding_proof",
    "fixed_regions_included",
    "flanks_inferred",
    "reverse_complement_inferred",
    "motifs_inferred",
    "truncations_included",
    "doped_selex_included",
    "sequence_scope",
    "human_review_status",
    "discrepancy_codes",
    "proposed_disposition",
    "publication_title",
    "first_author",
    "year",
)
EVIDENCE_COLUMNS: tuple[str, ...] = (
    "evidence_id",
    "reference_id",
    "clone_id",
    "evidence_class",
    "assay_type",
    "qualitative_result",
    "target",
    "target_concentration_range",
    "aptamer_concentration_range",
    "enzyme_concentration",
    "substrate",
    "preincubation",
    "replicates",
    "observed_effect",
    "quantitative_affinity_reported",
    "affinity_type",
    "affinity_value",
    "high_affinity_claim",
    "clinically_validated",
    "pdf_page",
    "dissertation_page",
    "source_locator",
    "scientific_limitations",
)

TABLE6_PHRASES: tuple[str, ...] = (
    "20 Klone sequenziert",
    "14 eine N50-Sequenz",
    "acht Sequenzen identisch",
    "sieben Einzelsequenzen",
    "D902 war die Sequenz, die achtmal",
    "D907 bestand nur aus 34 nt",
    "Tabelle 6",
)
BINDING_PHRASES: tuple[str, ...] = (
    "D902 konnte keine NDM1-Bindung festgestellt werden",
    "zeigten D909, D918 und D920 eine NDM1-Bindung",
    "D907, D913 und D914 zeigten wie",
    "D902 nur eine schwache Bindung",
    "geringeren Konzentrationen als 1 µM",
    "höchste Signalintensität wurde bei D909",
    "Abbildung 18",
)
INHIBITION_RESULT_PHRASES: tuple[str, ...] = (
    "ab einer D909-Konzentration von 10 µM",
    "30 µM D909 wurde die NDM1-Aktivität um 70% gesenkt",
    "30 nM NDM1",
    "300 nM konnte keine Inhibition",
    "tausendfachem Überschuss",
)
INHIBITION_METHOD_PHRASES: tuple[str, ...] = (
    "30 nM NDM1",
    "1 µM bis 30 µM",
    "halbe Stunde bei 37",
    "100 µM Nitrocefin",
    "Dreierwerte",
)
SHARED_LIMITATION = (
    "Qualitative filter-retention only. No dissociation constant was reported. "
    "No tested clone showed a filter-retention signal below 1 µM NDM-1. "
    "D909 inhibition was assayed at 30 nM NDM-1 with about 1-30 µM RNA, "
    "100 µM nitrocefin, 30 min preincubation at 37 C, and triplicate reads; "
    "activity fell from about 10 µM and by about 70 percent at 30 µM, and was "
    "not detected at 300 nM NDM-1. Inhibition required a very large RNA excess. "
    "D909 is not a high-affinity or clinically validated inhibitor. "
    "Published Table 6 strings are the tabulated inserts. Primers, flanks, "
    "reverse complements, motifs, doped-SELEX variants, and truncations were "
    "not inferred. Sequence or structural similarity is not evidence that a "
    "generated candidate binds or inhibits NDM-1."
)


class Ndm1RnaError(ValueError):
    """Hard failure during NDM-1 RNA reference verification."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def bool_token(value: bool) -> str:
    return "true" if value else "false"


def normalise_source_text(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.replace("μ", "µ"))
    return collapsed.strip()


def clean_reported_sequence(reported: str, *, context: str = "reported sequence") -> str:
    """Drop only trailing alignment hyphens. Refuse internal hyphens."""
    text = str(reported or "")
    if not text or REPORTED_RE.fullmatch(text) is None:
        raise Ndm1RnaError(f"{context} is not a DNA-alphabet string with optional hyphens")
    if "-" in text.rstrip("-"):
        raise Ndm1RnaError(f"{context} has a non-trailing alignment hyphen")
    cleaned = text.rstrip("-")
    if not cleaned or CLEANED_RE.fullmatch(cleaned) is None:
        raise Ndm1RnaError(f"{context} is empty after removing trailing alignment hyphens")
    if "U" in cleaned:
        raise Ndm1RnaError(f"{context} already contains U; source alphabet must stay DNA_T")
    return cleaned


def canonical_rna_from_cleaned(cleaned: str, *, context: str = "cleaned sequence") -> str:
    """Deterministic T-to-U conversion. Does not add or remove bases."""
    if cleaned and "U" in cleaned:
        raise Ndm1RnaError(f"{context} contains U before T-to-U conversion")
    if CLEANED_RE.fullmatch(cleaned or "") is None:
        raise Ndm1RnaError(f"{context} is not a cleaned DNA-alphabet string")
    rna = cleaned.replace("T", "U")
    if len(rna) != len(cleaned):
        raise Ndm1RnaError(f"{context} changed length during T-to-U conversion")
    if "T" in rna or not re.fullmatch(r"^[ACGU]+$", rna):
        raise Ndm1RnaError(f"{context} did not convert cleanly to RNA")
    return rna


def _row(columns: Sequence[str], values: Mapping[str, Any]) -> dict[str, str]:
    return {
        column: "" if values.get(column) is None else str(values.get(column, ""))
        for column in columns
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
        return [{key: (value or "") for key, value in row.items()} for row in csv.DictReader(handle)]


def require_phrases(text: str, phrases: Sequence[str], *, context: str) -> None:
    normalised = normalise_source_text(text)
    missing = [phrase for phrase in phrases if phrase not in normalised]
    if missing:
        raise Ndm1RnaError(
            f"{context} is missing source wording: " + "; ".join(missing)
        )


def _decode_pdf_literal(raw: bytes) -> str:
    text = raw.replace(b"\\(", b"(").replace(b"\\)", b")")
    text = text.replace(b"\\n", b"\n").replace(b"\\r", b"").replace(b"\\t", b"\t")
    return text.decode("latin1", errors="replace")


def extract_pdf_tj_strings(path: Path) -> list[str]:
    """Extract text-showing strings without an external PDF library."""
    import zlib

    data = path.read_bytes()
    stream_re = re.compile(rb"stream\r?\n(.*?)endstream", re.S)
    tj_re = re.compile(rb"\[(.*?)\]\s*TJ", re.S)
    literal_re = re.compile(rb"\((?:\\.|[^\\)])*\)")
    items: list[str] = []
    for match in stream_re.finditer(data):
        raw = match.group(1)
        if raw.endswith(b"\r\n"):
            raw = raw[:-2]
        elif raw.endswith(b"\n"):
            raw = raw[:-1]
        try:
            decoded = zlib.decompress(raw)
        except Exception:
            continue
        for tj in tj_re.finditer(decoded):
            parts = [
                _decode_pdf_literal(literal.group(0)[1:-1])
                for literal in literal_re.finditer(tj.group(1))
            ]
            if parts:
                items.append("".join(parts))
    if not items:
        raise Ndm1RnaError("dissertation PDF text extraction returned no text")
    return items


def dissertation_text(path: Path) -> str:
    return normalise_source_text("".join(extract_pdf_tj_strings(path)))


def extract_table6_rows_from_text(page_text: str) -> list[dict[str, str]]:
    """Independently transcribe Table 6 from the dissertation text."""
    require_phrases(page_text, TABLE6_PHRASES, context="Table 6")
    for anchor in ("Ergebnisse 36", "3.2.6", "Tabelle 6"):
        if anchor not in page_text:
            raise Ndm1RnaError(f"Table 6 locator is missing: {anchor}")
    matches = list(TABLE6_ROW_RE.finditer(page_text))
    rows = [
        {
            "clone_id": match.group(1),
            "sequence_reported": match.group(2),
            "purine_percent_reported": match.group(3),
            "gc_percent_reported": match.group(4),
        }
        for match in matches
    ]
    if [row["clone_id"] for row in rows] != list(EXPECTED_CLONE_IDS):
        raise Ndm1RnaError(
            "independent Table 6 transcription did not yield the seven clones once, in order"
        )
    return rows


def load_table6_csv(path: Path) -> list[dict[str, str]]:
    rows = read_csv_rows(path)
    required = {
        "clone_id",
        "sequence_reported",
        "sequence_cleaned",
        "purine_percent_reported",
        "gc_percent_reported",
    }
    if not rows or required - set(rows[0]):
        raise Ndm1RnaError("Table 6 CSV is missing required columns")
    if [row["clone_id"].strip() for row in rows] != list(EXPECTED_CLONE_IDS):
        raise Ndm1RnaError("Table 6 CSV clone IDs are not the seven expected IDs in order")
    return rows


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall("m:si", XLSX_NS):
        values.append("".join(node.text or "" for node in item.findall(".//m:t", XLSX_NS)))
    return values


def load_xlsx_clone_rows(path: Path) -> list[dict[str, str]]:
    """Corroborate Table 6 from the workbook's first column. Not a primary authority."""
    try:
        with zipfile.ZipFile(path) as workbook:
            shared = _xlsx_shared_strings(workbook)
            sheet_name = "xl/worksheets/sheet1.xml"
            if sheet_name not in workbook.namelist():
                raise Ndm1RnaError("NDM-1 workbook is missing the first worksheet")
            sheet = ET.fromstring(workbook.read(sheet_name))
    except zipfile.BadZipFile as exc:
        raise Ndm1RnaError("NDM-1 workbook is not a valid xlsx file") from exc
    parsed: list[dict[str, str]] = []
    for row in sheet.findall("m:sheetData/m:row", XLSX_NS):
        first = ""
        round_value = ""
        target_value = ""
        for cell in row.findall("m:c", XLSX_NS):
            ref = cell.attrib.get("r", "")
            column = "".join(ch for ch in ref if ch.isalpha())
            raw = cell.find("m:v", XLSX_NS)
            value = raw.text if raw is not None and raw.text is not None else ""
            if cell.attrib.get("t") == "s" and value.isdigit():
                value = shared[int(value)]
            if column == "A":
                first = value.strip()
            elif column == "H":
                round_value = value.strip()
            elif column == "I":
                target_value = value.strip()
        if not first or first.startswith("#"):
            continue
        match = TABLE6_ROW_RE.fullmatch(first)
        if match is None:
            raise Ndm1RnaError("workbook row does not match the Table 6 clone pattern")
        parsed.append(
            {
                "clone_id": match.group(1),
                "sequence_reported": match.group(2),
                "purine_percent_reported": match.group(3),
                "gc_percent_reported": match.group(4),
                "selection_round": round_value,
                "target": target_value,
            }
        )
    if [row["clone_id"] for row in parsed] != list(EXPECTED_CLONE_IDS):
        raise Ndm1RnaError("workbook clone IDs do not match Table 6")
    return parsed


def assert_transcription_agreement(
    pdf_rows: Sequence[Mapping[str, str]],
    csv_rows: Sequence[Mapping[str, str]],
    xlsx_rows: Sequence[Mapping[str, str]] | None = None,
) -> None:
    if [row["clone_id"] for row in pdf_rows] != list(EXPECTED_CLONE_IDS):
        raise Ndm1RnaError("PDF clone order disagrees with the expected Table 6 order")
    if [row["clone_id"] for row in csv_rows] != list(EXPECTED_CLONE_IDS):
        raise Ndm1RnaError("CSV clone order disagrees with the PDF")
    for pdf_row, csv_row in zip(pdf_rows, csv_rows):
        clone = pdf_row["clone_id"]
        if csv_row["clone_id"].strip() != clone:
            raise Ndm1RnaError(f"clone ID disagreement for {clone}")
        if csv_row["sequence_reported"] != pdf_row["sequence_reported"]:
            raise Ndm1RnaError(f"reported sequence disagreement for {clone}")
        cleaned = clean_reported_sequence(
            pdf_row["sequence_reported"], context=f"{clone} reported sequence"
        )
        if csv_row["sequence_cleaned"] != cleaned:
            raise Ndm1RnaError(
                f"CSV cleaned sequence disagrees with hyphen-stripped Table 6 text for {clone}"
            )
        if csv_row["purine_percent_reported"] != pdf_row["purine_percent_reported"]:
            raise Ndm1RnaError(f"purine percent disagreement for {clone}")
        if csv_row["gc_percent_reported"] != pdf_row["gc_percent_reported"]:
            raise Ndm1RnaError(f"GC percent disagreement for {clone}")
    if xlsx_rows is not None:
        if [row["clone_id"] for row in xlsx_rows] != list(EXPECTED_CLONE_IDS):
            raise Ndm1RnaError("workbook clone order disagrees with Table 6")
        for pdf_row, xlsx_row in zip(pdf_rows, xlsx_rows):
            clone = pdf_row["clone_id"]
            if xlsx_row["sequence_reported"] != pdf_row["sequence_reported"]:
                raise Ndm1RnaError(f"workbook sequence disagrees with Table 6 for {clone}")
            if xlsx_row["purine_percent_reported"] != pdf_row["purine_percent_reported"]:
                raise Ndm1RnaError(f"workbook purine percent disagrees for {clone}")
            if xlsx_row["gc_percent_reported"] != pdf_row["gc_percent_reported"]:
                raise Ndm1RnaError(f"workbook GC percent disagrees for {clone}")
            if xlsx_row.get("selection_round") not in {"", "9"}:
                raise Ndm1RnaError(f"workbook round disagrees for {clone}")
            if xlsx_row.get("target") and "NDM-1" not in xlsx_row["target"]:
                raise Ndm1RnaError(f"workbook target disagrees for {clone}")


def verify_binding_and_inhibition_wording(text: str) -> None:
    require_phrases(text, BINDING_PHRASES, context="filter-retention wording")
    require_phrases(text, INHIBITION_RESULT_PHRASES, context="D909 inhibition results")
    require_phrases(text, INHIBITION_METHOD_PHRASES, context="D909 inhibition methods")
    for anchor in (
        "Ergebnisse 37",
        "Abbildung 18",
        "Ergebnisse 40",
        "Ergebnisse 41",
        "3.2.9",
        "Methoden 84",
        "Laer",
    ):
        if anchor not in text:
            raise Ndm1RnaError(f"dissertation locator is missing: {anchor}")


def verify_readme_corroboration(path: Path) -> None:
    text = path.read_text(encoding="latin-1", errors="replace")
    if "DNA alphabet" not in text or "T rather than U" not in text:
        raise Ndm1RnaError("readme does not corroborate the DNA-alphabet RNA reporting")
    if "alignment hyphens" not in text:
        raise Ndm1RnaError("readme does not corroborate alignment-hyphen removal")


def verify_raw_source_hashes(repo_root: Path, config: Mapping[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for spec in config["raw_sources"].values():
        path = repo_root / spec["path"]
        if not path.is_file():
            raise Ndm1RnaError(f"source file is missing: {spec['path']}")
        observed = sha256_file(path)
        if observed != spec["sha256"]:
            raise Ndm1RnaError(f"source SHA-256 mismatch: {spec['path']}")
        hashes[spec["path"]] = observed
    return hashes


def verify_registry(repo_root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    spec_path = repo_root / str(config["source_registry_path"])
    rows = load_registry_spec(spec_path)
    key = str(config["registered_source_key"])
    matches = [row for row in rows if row.source_key == key]
    if len(matches) != 1:
        raise Ndm1RnaError("tracked registry does not contain exactly one D9 source row")
    row = matches[0]
    expected_path = str(config["registered_csv_path"])
    expected_sha = str(config["raw_sources"]["table6_csv"]["sha256"])
    if row.path != expected_path:
        raise Ndm1RnaError("tracked registry still points at the stale D9 path")
    if row.path == str(config["previous_registered_csv_path"]):
        raise Ndm1RnaError("tracked registry path was not repaired")
    if row.sha256 != expected_sha:
        raise Ndm1RnaError("tracked registry D9 SHA-256 changed")
    if row.n_rows_expected != 7:
        raise Ndm1RnaError("tracked registry D9 row count is not 7")
    operational_path = repo_root / str(config["operational_registry_path"])
    status = "missing"
    operational_sha = ""
    if operational_path.is_file():
        operational_sha = sha256_file(operational_path)
        operational_rows = load_registry_spec(operational_path)
        operational_matches = [item for item in operational_rows if item.source_key == key]
        if len(operational_matches) != 1:
            raise Ndm1RnaError("operational registry does not contain exactly one D9 source row")
        operational = operational_matches[0]
        if operational.path != expected_path or operational.sha256 != expected_sha:
            raise Ndm1RnaError(
                "operational registry was not rebuilt onto the repaired D9 path"
            )
        if operational.n_rows_expected != 7:
            raise Ndm1RnaError("operational registry D9 row count is not 7")
        status = "aligned"
    historical = str(config.get("historical_s7d_source_registry_sha256") or "")
    manifest_path = repo_root / str(config["s7d_manifest_path"])
    manifest_registry_sha = ""
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_registry_sha = str(manifest.get("source_registry_sha256") or "")
        if historical and manifest_registry_sha != historical:
            raise Ndm1RnaError("frozen S7D manifest source-registry hash changed")
    return {
        "tracked_path": row.path,
        "tracked_sha256": row.sha256,
        "operational_status": status,
        "operational_registry_sha256": operational_sha,
        "s7d_recorded_source_registry_sha256": manifest_registry_sha,
        "operational_registry_differs_from_historical_s7d_pin": bool(
            operational_sha and historical and operational_sha != historical
        ),
    }


def _expected_map(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = config.get(key) or {}
    if not isinstance(value, Mapping):
        raise Ndm1RnaError(f"config {key} must be an object")
    return value


def _check_expected_int(actual: int, expected: Mapping[str, Any], clone: str, label: str) -> None:
    if clone not in expected:
        raise Ndm1RnaError(f"config is missing {label} for {clone}")
    if actual != int(expected[clone]):
        raise Ndm1RnaError(f"{label} mismatch for {clone}")


def _check_expected_hash(
    actual: str, expected: Mapping[str, Any], clone: str, label: str
) -> None:
    if clone not in expected:
        raise Ndm1RnaError(f"config is missing {label} for {clone}")
    if actual != str(expected[clone]):
        raise Ndm1RnaError(f"{label} mismatch for {clone}")


def build_verified_clone_records(
    *,
    config: Mapping[str, Any],
    pdf_rows: Sequence[Mapping[str, str]],
    source_sha: str,
) -> list[dict[str, Any]]:
    clones = _expected_map(config, "clones")
    if list(clones) != list(EXPECTED_CLONE_IDS):
        raise Ndm1RnaError("config clone records are not exactly the seven Table 6 IDs")
    publication = config["publication"]
    table = config["table6_locator"]
    binding = config["filter_retention_locator"]
    records: list[dict[str, Any]] = []
    for pdf_row in pdf_rows:
        clone = str(pdf_row["clone_id"])
        spec = clones[clone]
        reported = str(pdf_row["sequence_reported"])
        cleaned = clean_reported_sequence(reported, context=f"{clone} reported sequence")
        canonical = canonical_rna_from_cleaned(cleaned, context=f"{clone} cleaned sequence")
        gaps = len(reported) - len(cleaned)
        _check_expected_int(len(reported), _expected_map(config, "expected_reported_lengths"), clone, "reported length")
        _check_expected_int(len(cleaned), _expected_map(config, "expected_cleaned_lengths"), clone, "cleaned length")
        _check_expected_int(gaps, _expected_map(config, "expected_trailing_gap_counts"), clone, "trailing gap count")
        _check_expected_hash(sha256_text(reported), _expected_map(config, "expected_reported_sha256"), clone, "reported hash")
        _check_expected_hash(sha256_text(cleaned), _expected_map(config, "expected_cleaned_source_sha256"), clone, "cleaned hash")
        _check_expected_hash(sha256_text(canonical), _expected_map(config, "expected_canonical_rna_sha256"), clone, "canonical RNA hash")
        if len(canonical) != len(cleaned):
            raise Ndm1RnaError(f"{clone} canonical length differs from the cleaned length")
        status = str(spec["qualitative_binding_status"])
        if status not in POSITIVE_STATUSES | WEAK_STATUSES | NEGATIVE_STATUSES:
            raise Ndm1RnaError(f"unsupported binding status for {clone}")
        if clone == "D902" and status != "no_detectable_binding":
            raise Ndm1RnaError("D902 must be classified as no detectable binding")
        if clone in {"D907", "D913", "D914"} and status != "weak_binding":
            raise Ndm1RnaError(f"{clone} must be classified as weak binding")
        if clone == "D909" and status != "positive_strongest":
            raise Ndm1RnaError("D909 must keep primary/strongest positive status")
        if clone in {"D918", "D920"} and status != "positive_secondary":
            raise Ndm1RnaError(f"{clone} must keep secondary positive status")
        records.append(
            {
                "reference_id": spec["reference_id"],
                "clone_id": clone,
                "reported": reported,
                "cleaned": cleaned,
                "canonical": canonical,
                "gaps": gaps,
                "purine_percent_reported": pdf_row["purine_percent_reported"],
                "gc_percent_reported": pdf_row["gc_percent_reported"],
                "spec": spec,
                "source_sha256": source_sha,
                "publication": publication,
                "table": table,
                "binding": binding,
            }
        )
    if len({item["reference_id"] for item in records}) != 7:
        raise Ndm1RnaError("enriched reference IDs are not unique")
    if len({item["canonical"] for item in records}) != 7:
        raise Ndm1RnaError("canonical RNA sequences are not unique")
    return records


def reference_rows_from_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in records:
        spec = item["spec"]
        publication = item["publication"]
        table = item["table"]
        binding = item["binding"]
        rows.append(
            _row(
                REFERENCE_COLUMNS,
                {
                    "reference_id": item["reference_id"],
                    "clone_id": item["clone_id"],
                    "molecule_type": publication["molecule_type"],
                    "source_reported_alphabet": publication["source_reported_alphabet"],
                    "sequence_reported_raw": item["reported"],
                    "sequence_cleaned_source": item["cleaned"],
                    "sequence_canonical_rna": item["canonical"],
                    "reported_length": len(item["reported"]),
                    "cleaned_length": len(item["cleaned"]),
                    "canonical_length": len(item["canonical"]),
                    "trailing_gap_count": item["gaps"],
                    "reported_sha256": sha256_text(item["reported"]),
                    "cleaned_source_sha256": sha256_text(item["cleaned"]),
                    "canonical_rna_sha256": sha256_text(item["canonical"]),
                    "t_to_u_applied": bool_token(True),
                    "purine_percent_reported": item["purine_percent_reported"],
                    "gc_percent_reported": item["gc_percent_reported"],
                    "source_filename": Path(
                        str(item.get("source_filename") or "")
                    ).name,
                    "source_sha256": item["source_sha256"],
                    "source_table": table["table"],
                    "pdf_page": table["pdf_page"],
                    "dissertation_page": table["dissertation_page"],
                    "target": publication["target"],
                    "selection_pool": publication["selection_pool"],
                    "selection_round": publication["selection_round"],
                    "selection_method": publication["selection_method"],
                    "clone_frequency": spec["clone_frequency"],
                    "clone_frequency_support": spec["clone_frequency_support"],
                    "qualitative_binding_status": spec["qualitative_binding_status"],
                    "evidence_strength": spec["evidence_strength"],
                    "assay_type": binding["assay_type"],
                    "concentration_threshold_or_range": binding["concentration_threshold"],
                    "quantitative_affinity_reported": bool_token(False),
                    "affinity_type": "",
                    "affinity_value": "",
                    "scientific_limitations": SHARED_LIMITATION,
                    "legacy_s0b_reference_id": spec["legacy_s0b_reference_id"],
                    "legacy_s0b_evaluation_label": spec["legacy_evaluation_label"],
                    "legacy_s0b_evaluation_role": spec["legacy_evaluation_role"],
                    "legacy_exclusion_id": spec["legacy_exclusion_id"],
                    "legacy_discrepancy_code": spec["legacy_discrepancy_code"],
                    "sequence_comparison_role": spec["sequence_comparison_role"],
                    "include_in_sequence_comparison": bool_token(True),
                    "similarity_is_not_binding_proof": bool_token(True),
                    "fixed_regions_included": bool_token(False),
                    "flanks_inferred": bool_token(False),
                    "reverse_complement_inferred": bool_token(False),
                    "motifs_inferred": bool_token(False),
                    "truncations_included": bool_token(False),
                    "doped_selex_included": bool_token(False),
                    "sequence_scope": "published_table6_insert",
                    "human_review_status": spec["human_review_status"],
                    "discrepancy_codes": spec["discrepancy_codes"],
                    "proposed_disposition": spec["proposed_disposition"],
                    "publication_title": publication["publication_title"],
                    "first_author": publication["first_author"],
                    "year": publication["year"],
                },
            )
        )
    return rows


def evidence_rows_from_records(
    records: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> list[dict[str, str]]:
    binding = config["filter_retention_locator"]
    inhibition = config["inhibition_locator"]
    rows: list[dict[str, str]] = []
    for item in records:
        spec = item["spec"]
        rows.append(
            _row(
                EVIDENCE_COLUMNS,
                {
                    "evidence_id": f"{item['reference_id']}__filter_retention",
                    "reference_id": item["reference_id"],
                    "clone_id": item["clone_id"],
                    "evidence_class": "binding",
                    "assay_type": "filter_retention",
                    "qualitative_result": spec["qualitative_binding_status"],
                    "target": "NDM-1",
                    "target_concentration_range": binding["concentration_range"],
                    "aptamer_concentration_range": "not_reported_as_a_titrated_affinity",
                    "enzyme_concentration": "",
                    "substrate": "",
                    "preincubation": "",
                    "replicates": "not_reported_as_a_numeric_replicate_count",
                    "observed_effect": binding["concentration_threshold"],
                    "quantitative_affinity_reported": bool_token(False),
                    "affinity_type": "",
                    "affinity_value": "",
                    "high_affinity_claim": bool_token(False),
                    "clinically_validated": bool_token(False),
                    "pdf_page": binding["pdf_page"],
                    "dissertation_page": binding["dissertation_page"],
                    "source_locator": (
                        f"{binding['figure']}; PDF page {binding['pdf_page']}; "
                        f"dissertation page {binding['dissertation_page']}"
                    ),
                    "scientific_limitations": SHARED_LIMITATION,
                },
            )
        )
    d909 = next(item for item in records if item["clone_id"] == "D909")
    rows.append(
        _row(
            EVIDENCE_COLUMNS,
            {
                "evidence_id": f"{d909['reference_id']}__nitrocefin_inhibition",
                "reference_id": d909["reference_id"],
                "clone_id": "D909",
                "evidence_class": "inhibition",
                "assay_type": inhibition["assay_type"],
                "qualitative_result": "concentration_dependent_inhibition_at_large_rna_excess",
                "target": "NDM-1",
                "target_concentration_range": inhibition["enzyme_concentration"],
                "aptamer_concentration_range": inhibition["rna_concentration_range"],
                "enzyme_concentration": inhibition["enzyme_concentration"],
                "substrate": inhibition["substrate"],
                "preincubation": inhibition["preincubation"],
                "replicates": inhibition["replicates"],
                "observed_effect": (
                    f"{inhibition['activity_decrease_from']}; "
                    f"{inhibition['reduction_at_30_uM']}; "
                    f"no inhibition at {inhibition['no_inhibition_at']}; "
                    f"{inhibition['excess']}"
                ),
                "quantitative_affinity_reported": bool_token(False),
                "affinity_type": "",
                "affinity_value": "",
                "high_affinity_claim": bool_token(False),
                "clinically_validated": bool_token(False),
                "pdf_page": inhibition["result_pdf_pages"],
                "dissertation_page": inhibition["result_dissertation_pages"],
                "source_locator": (
                    f"PDF pages {inhibition['result_pdf_pages']} "
                    f"(dissertation pages {inhibition['result_dissertation_pages']}); "
                    f"methods PDF page {inhibition['methods_pdf_page']} "
                    f"(dissertation page {inhibition['methods_dissertation_page']})"
                ),
                "scientific_limitations": SHARED_LIMITATION,
            },
        )
    )
    if len(rows) != 8:
        raise Ndm1RnaError("binding-evidence row count is not 8")
    if any(row["quantitative_affinity_reported"] != "false" for row in rows):
        raise Ndm1RnaError("a quantitative affinity was incorrectly recorded")
    if any(row["affinity_value"] or row["affinity_type"] for row in rows):
        raise Ndm1RnaError("an affinity value was incorrectly recorded")
    return rows


def reconcile_existing_s0b(
    *,
    records: Sequence[Mapping[str, Any]],
    manifest_rows: Sequence[Mapping[str, str]],
    leakage_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    manifest_by_id = {row["reference_id"]: row for row in manifest_rows}
    leakage_by_id = {row["reference_id"]: row for row in leakage_rows}
    d9_leakage = [
        row
        for row in leakage_rows
        if row.get("source_key") == "von_laer_2013_d9_table6"
        or str(row.get("reference_id") or "").startswith("von_laer_2013_d9")
    ]
    if len(d9_leakage) != 7:
        raise Ndm1RnaError("leakage-exclusion set does not already contain exactly seven D9 records")
    reconciliation: list[dict[str, str]] = []
    for item in records:
        spec = item["spec"]
        legacy_id = str(spec["legacy_s0b_reference_id"])
        manifest = manifest_by_id.get(legacy_id)
        leakage = leakage_by_id.get(legacy_id)
        if manifest is None or leakage is None:
            raise Ndm1RnaError(f"existing S0b record missing for {item['clone_id']}")
        if manifest["aptamer_name"] != item["clone_id"] or leakage["aptamer_name"] != item["clone_id"]:
            raise Ndm1RnaError(f"existing clone ID disagrees for {item['clone_id']}")
        if manifest["evaluation_label"] != spec["legacy_evaluation_label"]:
            raise Ndm1RnaError(f"existing manifest label disagrees for {item['clone_id']}")
        if leakage["evaluation_label"] != spec["legacy_evaluation_label"]:
            raise Ndm1RnaError(f"existing leakage label disagrees for {item['clone_id']}")
        if leakage["evaluation_role"] != spec["legacy_evaluation_role"]:
            raise Ndm1RnaError(f"existing leakage role disagrees for {item['clone_id']}")
        if leakage["exclusion_id"] != spec["legacy_exclusion_id"]:
            raise Ndm1RnaError(f"existing exclusion ID disagrees for {item['clone_id']}")
        if manifest.get("exclusion_id") != spec["legacy_exclusion_id"]:
            raise Ndm1RnaError(f"manifest exclusion ID disagrees for {item['clone_id']}")
        if leakage["sequence_raw"] != item["reported"]:
            raise Ndm1RnaError(f"existing reported sequence is not equivalent for {item['clone_id']}")
        if leakage["sequence_full"] != item["canonical"] or leakage["sequence_core"] != item["canonical"]:
            raise Ndm1RnaError(f"existing canonical RNA is not equivalent for {item['clone_id']}")
        if leakage["sequence_compare_full"] != item["cleaned"]:
            raise Ndm1RnaError(f"existing comparison form is not equivalent for {item['clone_id']}")
        if leakage["t_to_u_applied"] != "true":
            raise Ndm1RnaError(f"existing record did not record T-to-U for {item['clone_id']}")
        if leakage["molecule_type"] != "RNA" or leakage["alphabet_as_reported"] != "DNA_T":
            raise Ndm1RnaError(f"existing molecule metadata disagrees for {item['clone_id']}")
        if manifest.get("include_in_sequence_leakage") != "true":
            raise Ndm1RnaError(f"existing manifest drops {item['clone_id']} from leakage")
        reconciliation.append(
            {
                "clone_id": item["clone_id"],
                "raw_source": "dissertation_table6_pdf_and_csv",
                "enriched_reference_id": item["reference_id"],
                "legacy_s0b_reference_id": legacy_id,
                "legacy_classification": spec["legacy_evaluation_label"],
                "enriched_classification": spec["qualitative_binding_status"],
                "canonical_rna_sha256": sha256_text(item["canonical"]),
                "cleaned_source_sha256": sha256_text(item["cleaned"]),
                "canonical_equivalent_to_s0b": "true",
                "leakage_exclusion_id": spec["legacy_exclusion_id"],
                "legacy_discrepancy_code": spec["legacy_discrepancy_code"],
                "proposed_disposition": spec["proposed_disposition"],
            }
        )
    return reconciliation


def _prepared_partition_rows(
    rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    prepared: list[dict[str, str]] = []
    for row in rows:
        full = row.get("sequence_full") or ""
        core = row.get("sequence_core") or ""
        prepared.append(
            {
                "record_id": row.get("record_id", ""),
                "scientific_identity_id": row.get("scientific_identity_id", ""),
                "sequence_full": comparison_form(full) if full else "",
                "sequence_core": comparison_form(core) if core else "",
            }
        )
    return prepared


def _best_against_field(
    query: str, prepared: Sequence[Mapping[str, str]], field: str, threshold: float
) -> dict[str, Any]:
    exact = 0
    ge_thr = 0
    best_identity = -1.0
    best_ids: list[tuple[str, str]] = []
    for item in prepared:
        target = item[field]
        if not target:
            continue
        identity = 1.0 if query == target else global_edit_identity(query, target)
        if query == target:
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
    return {
        "n_exact": exact,
        "n_identity_ge_threshold": ge_thr,
        "best_identity": None if best_identity < 0 else round(best_identity, 6),
        "best_scientific_identity_id": best[0],
        "best_record_id": best[1],
    }


def run_leakage_diagnostics(
    *,
    records: Sequence[Mapping[str, Any]],
    partitions: Mapping[str, Sequence[Mapping[str, str]]],
    corpus_lines: Sequence[str] | None = None,
    threshold: float = IDENTITY_THRESHOLD,
) -> dict[str, Any]:
    queries: list[dict[str, Any]] = []
    for item in records:
        forms = {
            "reported": comparison_form(item["reported"]),
            "cleaned_source": comparison_form(item["cleaned"]),
            "canonical_rna": comparison_form(item["canonical"]),
        }
        if len(set(forms.values())) != 1:
            raise Ndm1RnaError(
                f"source-supported forms are not comparison-equivalent for {item['clone_id']}"
            )
        queries.append(
            {
                "clone_id": item["clone_id"],
                "reference_id": item["reference_id"],
                "query": forms["canonical_rna"],
                "forms_checked": sorted(forms),
                "forms_comparison_equivalent": True,
            }
        )
    summary: dict[str, Any] = {
        "threshold": threshold,
        "n_queries": len(queries),
        "forms_per_query": ["reported", "cleaned_source", "canonical_rna"],
        "reverse_complement_matching": False,
        "by_partition": {},
        "flagged_for_human_review": [],
    }
    named_rows = {
        "TRAIN": partitions.get("TRAIN", []),
        "VALIDATION": partitions.get("VALIDATION", []),
        "REF": partitions.get("REF", []),
        "EVAL": partitions.get("EVAL", []),
        "CORPUS": partitions.get("CORPUS", []),
    }
    for name, rows in named_rows.items():
        prepared = _prepared_partition_rows(list(rows))
        part = {
            "n_rows": len(prepared),
            "exact_matches": 0,
            "identity_ge_threshold": 0,
            "queries": [],
        }
        for query in queries:
            query_row: dict[str, Any] = {
                "clone_id": query["clone_id"],
                "forms_comparison_equivalent": True,
            }
            for field in ("sequence_full", "sequence_core"):
                field_result = _best_against_field(
                    query["query"], prepared, field, threshold
                )
                query_row[field] = field_result
                part["exact_matches"] += field_result["n_exact"]
                part["identity_ge_threshold"] += field_result["n_identity_ge_threshold"]
                if field_result["n_exact"] or field_result["n_identity_ge_threshold"]:
                    summary["flagged_for_human_review"].append(
                        {
                            "clone_id": query["clone_id"],
                            "partition": name,
                            "field": field,
                            "n_exact": field_result["n_exact"],
                            "n_identity_ge_threshold": field_result["n_identity_ge_threshold"],
                        }
                    )
            part["queries"].append(query_row)
        summary["by_partition"][name] = part
    txt_prepared = [
        {"record_id": f"line_{index}", "scientific_identity_id": "", "sequence_line": comparison_form(line)}
        for index, line in enumerate(corpus_lines or [], start=1)
        if str(line).strip()
    ]
    txt_part = {
        "n_rows": len(txt_prepared),
        "exact_matches": 0,
        "identity_ge_threshold": 0,
        "queries": [],
    }
    for query in queries:
        field_result = _best_against_field(
            query["query"],
            [
                {
                    "record_id": item["record_id"],
                    "scientific_identity_id": "",
                    "sequence_line": item["sequence_line"],
                }
                for item in txt_prepared
            ],
            "sequence_line",
            threshold,
        )
        txt_part["queries"].append(
            {"clone_id": query["clone_id"], "sequence_line": field_result}
        )
        txt_part["exact_matches"] += field_result["n_exact"]
        txt_part["identity_ge_threshold"] += field_result["n_identity_ge_threshold"]
        if field_result["n_exact"] or field_result["n_identity_ge_threshold"]:
            summary["flagged_for_human_review"].append(
                {
                    "clone_id": query["clone_id"],
                    "partition": "CORPUS_TXT",
                    "field": "sequence_line",
                    "n_exact": field_result["n_exact"],
                    "n_identity_ge_threshold": field_result["n_identity_ge_threshold"],
                }
            )
    summary["by_partition"]["CORPUS_TXT"] = txt_part
    summary["any_exact"] = any(
        part["exact_matches"] for part in summary["by_partition"].values()
    )
    summary["any_identity_ge_threshold"] = any(
        part["identity_ge_threshold"] for part in summary["by_partition"].values()
    )
    return summary


def _status_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    statuses = [str(item["spec"]["qualitative_binding_status"]) for item in records]
    return {
        "reference_records": len(records),
        "binding_evidence_records": len(records) + 1,
        "positive_references": sum(status in POSITIVE_STATUSES for status in statuses),
        "weak_binding_references": sum(status in WEAK_STATUSES for status in statuses),
        "no_detectable_binding_references": sum(status in NEGATIVE_STATUSES for status in statuses),
        "leakage_exclusion_matches": len(records),
    }


def hash_existing_files(repo_root: Path, relative_paths: Mapping[str, str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name, rel in relative_paths.items():
        path = repo_root / rel
        if not path.is_file():
            raise Ndm1RnaError(f"required file is missing: {rel}")
        hashes[name] = sha256_file(path)
    return hashes


def snapshot_optional_paths(repo_root: Path, relative_paths: Sequence[str]) -> dict[str, str]:
    """Hash each existing file. A missing path is ``absent`` and is not an error."""
    snapshots: dict[str, str] = {}
    for rel in relative_paths:
        path = repo_root / rel
        if path.is_file():
            snapshots[rel] = sha256_file(path)
        elif path.exists():
            snapshots[rel] = NOT_A_REGULAR_FILE
        else:
            snapshots[rel] = ABSENT_FILE
    return snapshots


def snapshot_required_files(repo_root: Path, relative_paths: Sequence[str]) -> dict[str, str]:
    snapshots: dict[str, str] = {}
    for rel in relative_paths:
        path = repo_root / rel
        if not path.is_file():
            raise Ndm1RnaError(f"untouched-during-run file is missing: {rel}")
        snapshots[rel] = sha256_file(path)
    return snapshots


def _reject_permanent_non_corpus_pins(config: Mapping[str, Any]) -> list[str]:
    if config.get("expected_protected_untracked_sha256"):
        raise Ndm1RnaError("protected document hashes are not permanent build inputs")
    pinned = config.get("immutable_tracked_authorities")
    if isinstance(pinned, Mapping) and pinned:
        raise Ndm1RnaError(
            "unrelated tracked files must be listed in untouched_during_run, not pinned by hash"
        )
    untouched = config.get("untouched_during_run") or []
    if isinstance(untouched, Mapping):
        raise Ndm1RnaError("untouched_during_run must be a list of paths, not a hash map")
    return [str(item) for item in untouched]


def frozen_path_map(config: Mapping[str, Any]) -> dict[str, str]:
    paths = {Path(rel).name: rel for rel in config["frozen_partitions"].values()}
    paths.update(dict(config["frozen_corpus"]))
    paths["evaluation_references.csv"] = str(config["evaluation_references_path"])
    paths["evaluation_reference_manifest.csv"] = str(config["evaluation_reference_manifest_path"])
    paths["leakage_exclusion_set.csv"] = str(config["leakage_exclusion_set_path"])
    paths["corpus_manifest.json"] = str(config["s7d_manifest_path"])
    return paths


def assert_expected_hashes(observed: Mapping[str, str], expected: Mapping[str, str], *, label: str) -> None:
    for name, digest in expected.items():
        if observed.get(name) != digest:
            raise Ndm1RnaError(f"{label} hash mismatch: {name}")


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


def load_corpus_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def render_report(payload: Mapping[str, Any]) -> str:
    counts = payload["counts"]
    leakage = payload["leakage"]
    registry = payload["registry"]
    lines = [
        "# NDM-1 RNA D9 reference verification report",
        "",
        "This is a target-specific RNA reference audit for the von Laer 2013 D9 clones.",
        "It does not modify frozen partitions, S0b records, or S7D authorities.",
        "Nucleotide strings are omitted from this report.",
        "",
        "## Counts and classifications",
        "",
        f"- reference records: `{counts['reference_records']}`",
        f"- binding/inhibition evidence records: `{counts['binding_evidence_records']}`",
        f"- positive references (D909, D918, D920): `{counts['positive_references']}`",
        f"- weak-binding contextual references (D907, D913, D914): `{counts['weak_binding_references']}`",
        f"- no-detectable-binding comparator (D902): `{counts['no_detectable_binding_references']}`",
        "- D909 is the strongest filter-retention positive and the only clone with a nitrocefin inhibition assay.",
        "- D918 and D920 are secondary positives: the source reports NDM-1 binding, and D909 had the highest signal.",
        "- D907, D913, and D914 are weak-binding contextual references.",
        "- D902 had no detectable NDM-1 binding. A following sentence groups it rhetorically with the weak binders; the enriched status keeps the no-detectable-binding distinction.",
        "- No quantitative affinity was reported. D909 is not described as a high-affinity or clinically validated inhibitor.",
        "",
        "## Reconciliation",
        "",
        "| clone | enriched ID | legacy S0b ID | legacy classification | enriched classification | canonical equivalent | leakage ID | disposition |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["reconciliation"]:
        lines.append(
            f"| `{row['clone_id']}` | `{row['enriched_reference_id']}` | "
            f"`{row['legacy_s0b_reference_id']}` | `{row['legacy_classification']}` | "
            f"`{row['enriched_classification']}` | `{row['canonical_equivalent_to_s0b']}` | "
            f"`{row['leakage_exclusion_id']}` | retain existing S0b/leakage record; enrich separately |"
        )
    lines.extend(
        [
            "",
            "All seven canonical RNA sequences match the existing leakage-exclusion records.",
            "No duplicate S0b or leakage row was written.",
            "",
            "## Legacy classification discrepancy",
            "",
            "The closed S0b label `pool_nonbinder` is scientifically misleading for D907, D913, and D914, which the dissertation describes as weak binding. It also collapses D902, for which no NDM-1 binding was detected.",
            "Those enriched statuses live only in this RNA reference layer.",
            "Migrating the frozen S0b labels would change pinned evaluation-reference and leakage-exclusion hashes and is stopped for approval.",
            "",
            "Downstream contracts a migration would affect:",
            "",
        ]
    )
    for item in payload["migration_contracts"]:
        lines.append(f"- `{item}`")
    lines.extend(
        [
            "",
            "## Registry path repair and S7D provenance",
            "",
            f"- tracked path: `{registry['tracked_path']}`",
            f"- tracked D9 CSV SHA-256: `{registry['tracked_sha256']}`",
            f"- operational registry: `{registry['operational_status']}`",
            f"- operational registry SHA-256: `{registry['operational_registry_sha256']}`",
            f"- S7D manifest source-registry SHA-256: `{registry['s7d_recorded_source_registry_sha256']}`",
            "The S7D manifest records the source registry used when that frozen corpus was built.",
            "The current operational registry contains a path-only repair. The D9 CSV content and SHA-256 are unchanged.",
            "A difference between the operational registry hash and the hash recorded in the frozen S7D manifest is an expected historical/current provenance distinction.",
            "A future deliberate S7D rebuild would record the registry that is current at that time.",
            "This verification does not rebuild or edit the frozen S7D manifest.",
            "- Rebuilding S0b from the repaired path was byte-stable for the leakage-exclusion set, evaluation-reference manifest, and processed evaluation references. Those artifacts were not rewritten.",
            "- The tracked raw-data inventory still lists the previous directory, so an S0a inventory comparison warns that the repaired path is absent. That warning is non-fatal. This builder does not regenerate the inventory.",
            "",
            "## Leakage diagnostics",
            "",
            f"- threshold: `{leakage['threshold']}`",
            "- forms checked for every clone: reported DNA, cleaned DNA, and canonical RNA",
            "- those three forms are comparison-equivalent under U-to-T collapse",
            "- reverse-complement matching: no",
            f"- any exact match in frozen TRAIN, VALIDATION, REF, EVAL, corpus CSV, or corpus TXT: `{leakage['any_exact']}`",
            f"- any identity >= 0.90: `{leakage['any_identity_ge_threshold']}`",
            "",
        ]
    )
    for name in ("TRAIN", "VALIDATION", "REF", "EVAL", "CORPUS", "CORPUS_TXT"):
        part = leakage["by_partition"][name]
        lines.append(
            f"- `{name}`: rows=`{part['n_rows']}`; exact=`{part['exact_matches']}`; "
            f">=0.90=`{part['identity_ge_threshold']}`"
        )
    lines.extend(
        [
            "",
            "All seven references remain in the existing leakage-exclusion set, including weak-binding and no-detectable-binding comparators.",
            "Frozen partitions were not changed.",
            "",
            "## Future evaluation role",
            "",
            "Later candidate comparison may use D909, D918, and D920 as source-supported positive references; D907, D913, and D914 as weak-binding contextual references; and D902 as the no-detectable-binding comparator.",
            "That comparison is descriptive. Sequence or structural similarity must not be presented as proof of NDM-1 binding or inhibition.",
            "",
            "## Documentation impact",
            "",
            "The following documents were not edited. Later evaluation write-up should add:",
            "",
            "### docs/aptarank_full_mres_thesis_evaluation_plan.md",
            "",
            "- Name the von Laer 2013 D9 panel as the NDM-1 RNA reference set, separate from the published NDM-1 ssDNA references.",
            "- State the comparison roles: D909/D918/D920 positive, D907/D913/D914 weak-binding context, D902 no-detectable-binding comparator.",
            "- State that similarity is descriptive and is not binding or inhibition evidence.",
            "- Record that the legacy S0b `pool_nonbinder` labels for D902, D907, D913, and D914 are not migrated.",
            "- Summarise the filter-retention limit (no signal below 1 µM NDM-1) and the D909 nitrocefin assay limits (large RNA excess, no Kd, not clinically validated).",
            "",
            "### docs/aptarank-two-stage-evaluation-implementation-plan.md",
            "",
            "- Point implementation at `scripts/data_preparation/build_ndm1_rna_references.py` and the ignored outputs under `data/processed/`.",
            "- Use the repaired registry path `data/raw/evaluation_references/selektion_paper/table6_d9_ndm1_sequences.csv`.",
            "- Compare candidates with `comparison_form` and global identity >= 0.90, without adding duplicate leakage rows.",
            "- Keep frozen TRAIN, VALIDATION, REF, EVAL, corpus, S0b, and S7D authorities unchanged when scoring this panel.",
            "",
            "### docs/planned_evaluation_report.md",
            "",
            "- Add a results subsection for exact and >=0.90 identity of generated candidates against the seven clones, stratified by positive, weak-binding, and no-detectable-binding roles.",
            "- Report the D909 inhibition assay separately from sequence similarity.",
            "- Keep doped-SELEX variants and truncation constructs out of the verified full-length set until they are separately transcribed.",
            "- State that the dissertation did not report a quantitative affinity.",
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
            f"- frozen files unchanged: `{payload['frozen_unchanged']}`",
            f"- raw sources unchanged: `{payload['raw_sources_unchanged']}`",
            f"- protected untracked files unchanged during this run: `{payload['protected_untracked_unchanged']}`",
            "- A missing protected file is recorded as `absent` and does not block the build.",
            "- Current hashes of those documents are not build inputs.",
            f"- untouched-during-run files unchanged: `{payload['untouched_during_run_unchanged']}`",
            "- Frozen corpus, partition, S0b, and S7D manifest hashes remain the reproducibility contracts.",
            "- The following tracked files are snapshotted only to prove this run did not edit them. Their versions are not RNA reference pins.",
            "- `config/ndm1_ssdna_reference_build.json` is in that check so this run does not edit the ssDNA authority. Its corpus hash is not an RNA contract and can be corrected later.",
            f"- git ls-files data empty: `{payload['git_ls_files_data_empty']}`",
            "",
            "### Protected files at the start of this run",
            "",
        ]
    )
    for rel, digest in payload["protected_untracked_snapshot"].items():
        lines.append(f"- `{rel}`: `{digest}`")
    lines.extend(
        [
            "",
            "### Untouched during this run",
            "",
        ]
    )
    for rel, digest in payload["untouched_during_run_sha256"].items():
        lines.append(f"- `{rel}`: `{digest}`")
    lines.extend(
        [
            "",
            "Resource is not a corpus-curation stage. S0b classifications were not migrated.",
        ]
    )
    report = "\n".join(lines) + "\n"
    if scan_text_for_sequence_leak(report):
        raise Ndm1RnaError("verification report contains a nucleotide string of length 20 or more")
    return report


def render_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    if scan_text_for_sequence_leak(text) or SEQ_LEAK_RE.search(text):
        raise Ndm1RnaError("manifest contains a nucleotide string of length 20 or more")
    return json.loads(text)


def run_ndm1_rna_build(
    *,
    config: Mapping[str, Any],
    repo_root: Path | None = None,
    write_outputs: bool = True,
    run_leakage: bool = True,
    enforce_frozen_hashes: bool = True,
    pdf_rows: Sequence[Mapping[str, str]] | None = None,
    csv_rows: Sequence[Mapping[str, str]] | None = None,
    xlsx_rows: Sequence[Mapping[str, str]] | None = None,
    partitions: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
    corpus_lines: Sequence[str] | None = None,
    skip_primary_text_checks: bool = False,
) -> dict[str, Any]:
    untouched_paths = _reject_permanent_non_corpus_pins(config)
    root = repo_root or find_repo_root()
    protected = list(config.get("protected_untracked_files") or [])
    protected_before = snapshot_optional_paths(root, protected)
    raw_before = verify_raw_source_hashes(root, config)
    registry = verify_registry(root, config)
    frozen_paths = frozen_path_map(config)
    frozen_before = hash_existing_files(root, frozen_paths)
    untouched_before = snapshot_required_files(root, untouched_paths)
    if enforce_frozen_hashes:
        assert_expected_hashes(
            frozen_before, config.get("expected_frozen_sha256") or {}, label="frozen"
        )

    pdf_path = root / config["raw_sources"]["dissertation_pdf"]["path"]
    csv_path = root / config["raw_sources"]["table6_csv"]["path"]
    xlsx_path = root / config["raw_sources"]["data_xlsx"]["path"]
    readme_path = root / config["raw_sources"]["readme_rtf"]["path"]
    if not skip_primary_text_checks:
        source_text = dissertation_text(pdf_path)
        verify_binding_and_inhibition_wording(source_text)
        verify_readme_corroboration(readme_path)
        if pdf_rows is None:
            pdf_rows = extract_table6_rows_from_text(source_text)
        if csv_rows is None:
            csv_rows = load_table6_csv(csv_path)
        if xlsx_rows is None:
            xlsx_rows = load_xlsx_clone_rows(xlsx_path)
    else:
        if pdf_rows is None or csv_rows is None:
            raise Ndm1RnaError("synthetic builds must supply PDF and CSV rows")
    assert_transcription_agreement(pdf_rows, csv_rows, xlsx_rows)
    records = build_verified_clone_records(
        config=config,
        pdf_rows=pdf_rows,
        source_sha=config["raw_sources"]["dissertation_pdf"]["sha256"],
    )
    for record in records:
        record["source_filename"] = config["raw_sources"]["dissertation_pdf"]["path"]
    reference_rows = reference_rows_from_records(records)
    evidence_rows = evidence_rows_from_records(records, config)
    manifest_rows = read_csv_rows(root / config["evaluation_reference_manifest_path"])
    leakage_rows = read_csv_rows(root / config["leakage_exclusion_set_path"])
    reconciliation = reconcile_existing_s0b(
        records=records,
        manifest_rows=manifest_rows,
        leakage_rows=leakage_rows,
    )
    counts = _status_counts(records)
    expected_counts = config.get("expected_counts") or {}
    for key, wanted in expected_counts.items():
        if counts.get(key) != wanted:
            raise Ndm1RnaError(f"count mismatch for {key}")

    if partitions is None:
        partitions = {
            name: read_csv_rows(root / rel)
            for name, rel in config["frozen_partitions"].items()
        }
        partitions["CORPUS"] = read_csv_rows(root / config["frozen_corpus"]["corpus_final.csv"])
    if corpus_lines is None and run_leakage:
        corpus_lines = load_corpus_lines(root / config["frozen_corpus"]["corpus_final.txt"])
    leakage = (
        run_leakage_diagnostics(
            records=records,
            partitions=partitions,
            corpus_lines=corpus_lines or [],
            threshold=float(config.get("identity_threshold", IDENTITY_THRESHOLD)),
        )
        if run_leakage
        else {
            "threshold": float(config.get("identity_threshold", IDENTITY_THRESHOLD)),
            "n_queries": 0,
            "forms_per_query": ["reported", "cleaned_source", "canonical_rna"],
            "reverse_complement_matching": False,
            "by_partition": {
                name: {"n_rows": 0, "exact_matches": 0, "identity_ge_threshold": 0, "queries": []}
                for name in ("TRAIN", "VALIDATION", "REF", "EVAL", "CORPUS", "CORPUS_TXT")
            },
            "flagged_for_human_review": [],
            "any_exact": False,
            "any_identity_ge_threshold": False,
            "skipped": True,
        }
    )
    expected_leakage = config.get("expected_leakage") or {}
    if run_leakage and enforce_frozen_hashes and expected_leakage:
        if bool(leakage["any_exact"]) != bool(
            expected_leakage["any_exact_in_frozen_partitions_or_corpus"]
        ):
            raise Ndm1RnaError("frozen-partition exact-match result differed from the pinned expectation")
        if bool(leakage["any_identity_ge_threshold"]) != bool(
            expected_leakage["any_identity_ge_threshold"]
        ):
            raise Ndm1RnaError("frozen-partition near-match result differed from the pinned expectation")

    output_dir = root / config["output_dir"]
    outputs = {
        "ndm1_rna_aptamer_references.csv": output_dir / "ndm1_rna_aptamer_references.csv",
        "ndm1_rna_binding_evidence.csv": output_dir / "ndm1_rna_binding_evidence.csv",
        "ndm1_rna_reference_manifest.json": output_dir / "ndm1_rna_reference_manifest.json",
        "ndm1_rna_reference_verification_report.md": output_dir
        / "ndm1_rna_reference_verification_report.md",
    }
    input_hashes = {
        **{Path(path).name: digest for path, digest in raw_before.items()},
        **frozen_before,
        "source_registry.csv": sha256_file(root / config["source_registry_path"]),
    }
    report_payload = {
        "counts": counts,
        "reconciliation": reconciliation,
        "migration_contracts": list(config.get("s0b_migration_would_affect") or []),
        "registry": registry,
        "leakage": leakage,
        "input_hashes": input_hashes,
        "output_hashes": {},
        "frozen_unchanged": True,
        "raw_sources_unchanged": True,
        "protected_untracked_unchanged": True,
        "protected_untracked_snapshot": protected_before,
        "untouched_during_run_unchanged": True,
        "untouched_during_run_sha256": untouched_before,
        "git_ls_files_data_empty": git_ls_files_data(root) == "",
    }
    per_record = [
        {
            "reference_id": row["reference_id"],
            "clone_id": row["clone_id"],
            "qualitative_binding_status": row["qualitative_binding_status"],
            "sequence_comparison_role": row["sequence_comparison_role"],
            "cleaned_length": int(row["cleaned_length"]),
            "canonical_length": int(row["canonical_length"]),
            "trailing_gap_count": int(row["trailing_gap_count"]),
            "t_to_u_applied": row["t_to_u_applied"],
            "quantitative_affinity_reported": row["quantitative_affinity_reported"],
            "legacy_s0b_reference_id": row["legacy_s0b_reference_id"],
            "legacy_s0b_evaluation_label": row["legacy_s0b_evaluation_label"],
            "legacy_discrepancy_code": row["legacy_discrepancy_code"],
            "human_review_status": row["human_review_status"],
            "canonical_rna_sha256": row["canonical_rna_sha256"],
            "cleaned_source_sha256": row["cleaned_source_sha256"],
        }
        for row in reference_rows
    ]
    manifest = render_manifest(
        {
            "contract_id": config.get("contract_id"),
            "milestone": config.get("milestone"),
            "build_date": config.get("build_date"),
            "repository_head_baseline": config.get("repository_head_baseline"),
            "does_not_migrate_s0b_classifications": True,
            "counts": counts,
            "per_record": per_record,
            "reconciliation": reconciliation,
            "registry": registry,
            "leakage": {
                "threshold": leakage["threshold"],
                "any_exact": leakage["any_exact"],
                "any_identity_ge_threshold": leakage["any_identity_ge_threshold"],
                "reverse_complement_matching": False,
                "forms_per_query": leakage["forms_per_query"],
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
            "migration_contracts": list(config.get("s0b_migration_would_affect") or []),
            "input_hashes": input_hashes,
            "output_hashes": {},
            "frozen_unchanged": True,
            "s0b_or_s7d_authorities_updated": False,
            "protected_document_hashes_are_build_inputs": False,
            "untouched_during_run_hashes_are_permanent_pins": False,
            "protected_untracked_snapshot": protected_before,
            "untouched_during_run_sha256": untouched_before,
            "resource_marked_final": False,
        }
    )
    report_text = render_report(report_payload)
    output_hashes: dict[str, str] = {}
    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_csv(
            outputs["ndm1_rna_aptamer_references.csv"], REFERENCE_COLUMNS, reference_rows
        )
        _atomic_write_csv(
            outputs["ndm1_rna_binding_evidence.csv"], EVIDENCE_COLUMNS, evidence_rows
        )
        csv_hashes = {
            outputs["ndm1_rna_aptamer_references.csv"].name: sha256_file(
                outputs["ndm1_rna_aptamer_references.csv"]
            ),
            outputs["ndm1_rna_binding_evidence.csv"].name: sha256_file(
                outputs["ndm1_rna_binding_evidence.csv"]
            ),
        }
        report_payload["output_hashes"] = csv_hashes
        manifest["output_hashes"] = csv_hashes
        report_text = render_report(report_payload)
        manifest = render_manifest(manifest)
        write_text_atomic(outputs["ndm1_rna_reference_verification_report.md"], report_text)
        write_json_atomic(outputs["ndm1_rna_reference_manifest.json"], manifest)
        output_hashes = {path.name: sha256_file(path) for path in outputs.values()}
        if scan_text_for_sequence_leak(
            outputs["ndm1_rna_reference_verification_report.md"].read_text(encoding="utf-8")
        ) or scan_text_for_sequence_leak(
            outputs["ndm1_rna_reference_manifest.json"].read_text(encoding="utf-8")
        ):
            raise Ndm1RnaError("sequence-free outputs contain a nucleotide string")

    raw_after = verify_raw_source_hashes(root, config)
    if raw_after != raw_before:
        raise Ndm1RnaError("raw sources changed during the build")
    frozen_after = hash_existing_files(root, frozen_paths)
    if frozen_after != frozen_before:
        raise Ndm1RnaError("frozen or S0b artifacts changed during the build")
    untouched_after = snapshot_required_files(root, untouched_paths)
    if untouched_after != untouched_before:
        raise Ndm1RnaError("untouched-during-run files changed during the build")
    protected_after = snapshot_optional_paths(root, protected)
    if protected_after != protected_before:
        raise Ndm1RnaError("protected untracked files changed during the build")
    if git_ls_files_data(root) != "":
        raise Ndm1RnaError("git ls-files data is no longer empty")

    return {
        "ok": True,
        "counts": counts,
        "references": reference_rows,
        "evidence": evidence_rows,
        "reconciliation": reconciliation,
        "leakage": leakage,
        "registry": registry,
        "report": report_text,
        "manifest": manifest,
        "output_hashes": output_hashes,
        "input_hashes": input_hashes,
        "frozen_unchanged": True,
        "raw_sources_unchanged": True,
        "protected_untracked_unchanged": True,
        "protected_untracked_snapshot": protected_before,
        "untouched_during_run_unchanged": True,
        "untouched_during_run_sha256": untouched_before,
        "git_ls_files_data_empty": True,
    }

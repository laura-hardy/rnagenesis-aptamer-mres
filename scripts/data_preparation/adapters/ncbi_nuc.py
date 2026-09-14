"""NCBI Nucleotide S1 adapter: verbatim GenBank extraction.

Consumes every registered ``ncbi_nuc`` GenBank file belonging to one
logical ``source_dataset``. Does not classify molecules, convert T→U,
trim, extract targets, score evidence, reject/park records, or
deduplicate against ENA or within NCBI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from Bio import SeqIO
from Bio.SeqRecord import SeqRecord

from common.corpus_schema import (
    empty_corpus_record,
    validate_s1_record,
    write_corpus_csv_atomic,
)

SOURCE_DB: Final[str] = "ncbi_nuc"
EXPECTED_INPUT_RECORDS: Final[int] = 18
EXPECTED_NONEMPTY_SEQUENCES: Final[int] = 18
EXPECTED_MISSING_SEQUENCES: Final[int] = 0
EXPECTED_EMPTY_TARGET_NAME_RAW: Final[int] = 18
EXPECTED_NONEMPTY_PMID: Final[int] = 2
EXPECTED_NONEMPTY_DOI: Final[int] = 0
EXPECTED_NONEMPTY_PUBLICATION: Final[int] = 0
EXPECTED_EMPTY_ACCESSION: Final[int] = 18

SIDECAR_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "ncbi_nuc_registered_path",
    "ncbi_nuc_input_basename",
    "ncbi_nuc_file_sha256",
    "ncbi_nuc_locus",
    "ncbi_nuc_locus_length",
    "ncbi_nuc_locus_molecule",
    "ncbi_nuc_topology",
    "ncbi_nuc_division",
    "ncbi_nuc_date",
    "ncbi_nuc_accession",
    "ncbi_nuc_version",
    "ncbi_nuc_gi",
    "ncbi_nuc_definition",
    "ncbi_nuc_comment",
    "ncbi_nuc_keywords",
    "ncbi_nuc_source_organism",
    "ncbi_nuc_source_mol_type",
    "ncbi_nuc_dbxrefs_json",
    "ncbi_nuc_features_json",
    "ncbi_nuc_references_json",
    "ncbi_nuc_origin_length",
    "ncbi_nuc_origin_residues",
)

_ORIGIN_DISPLAY_RE: Final[re.Pattern[str]] = re.compile(r"[\d\s]+")
_LOCUS_RE: Final[re.Pattern[str]] = re.compile(
    r"^LOCUS\s+(\S+)\s+(\d+)\s+(bp|aa|rc)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$"
)
_COMPLEMENT_RE: Final[re.Pattern[str]] = re.compile(r"complement\s*\(", re.I)


class NcbiNucAdapterError(ValueError):
    """Hard failure while validating or extracting NCBI Nucleotide GenBank."""


@dataclass(frozen=True)
class NcbiNucRegisteredInput:
    """One registered GenBank file in registry order."""

    path: Path
    relative_path: str
    sha256: str
    n_rows_expected: int | None


@dataclass
class NcbiNucExtractionStats:
    """Aggregate counts for the NCBI Nucleotide S1 report (no sequences)."""

    input_files: int = 0
    input_rows: int = 0
    canonical_rows: int = 0
    sidecar_rows: int = 0
    unique_native_ids: int = 0
    unique_record_ids: int = 0
    nonempty_sequences: int = 0
    missing_sequences: int = 0
    empty_target_name_raw: int = 0
    nonempty_target_name_raw: int = 0
    nonempty_publication: int = 0
    nonempty_doi: int = 0
    nonempty_pmid: int = 0
    empty_canonical_accession: int = 0
    origin_length_matches_locus: int = 0
    first_native_id: str = ""
    last_native_id: str = ""
    pmid_native_ids: tuple[str, ...] = ()
    sequence_exact_copy_ok: bool = False
    order_preserved: bool = False
    native_id_strategy: str = (
        "GenBank ACCESSION (never local filename, LOCUS, or VERSION)"
    )


@dataclass
class NcbiNucExtractionResult:
    """Canonical rows, sidecar rows, and aggregate extraction statistics."""

    canonical_rows: list[dict[str, str]]
    sidecar_rows: list[dict[str, str]]
    stats: NcbiNucExtractionStats = field(default_factory=NcbiNucExtractionStats)


def dumps_json(value: Any) -> str:
    """Serialize nested provenance as deterministic JSON."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def split_genbank_record_texts(text: str) -> list[str]:
    """Split a GenBank flatfile into terminator-delimited record texts."""
    records: list[str] = []
    buf: list[str] = []
    for line in text.splitlines(keepends=True):
        buf.append(line)
        if line.strip() == "//":
            records.append("".join(buf))
            buf = []
    leftover = "".join(buf)
    if leftover.strip():
        raise NcbiNucAdapterError(
            "GenBank file has unterminated record text after the last //"
        )
    if not records:
        raise NcbiNucAdapterError("GenBank file contains no records")
    return records


def extract_origin_residues(record_text: str) -> str:
    """Recover ORIGIN residue letters by removing flatfile display syntax.

    Removes line numbers, display-grouping spaces, and line breaks only.
    Does not uppercase, convert T/U, drop IUPAC/N, drop gaps, trim, or
    otherwise alter deposited residue characters.
    """
    match = re.search(r"(?ms)^ORIGIN[^\n]*\n(.*?)(?:^//\s*\Z)", record_text)
    if match is None:
        raise NcbiNucAdapterError("GenBank record is missing an ORIGIN block")
    residues = _ORIGIN_DISPLAY_RE.sub("", match.group(1))
    if residues == "":
        raise NcbiNucAdapterError("GenBank ORIGIN contains no residue characters")
    return residues


def _field_body(record_text: str, field_name: str) -> str:
    """Return a GenBank header field body, preserving continuation text."""
    prefix = field_name
    lines = record_text.splitlines()
    collected: list[str] = []
    capturing = False
    for line in lines:
        if line.startswith("ORIGIN"):
            break
        if not capturing:
            if line.startswith(prefix) and (
                len(line) == len(prefix) or line[len(prefix)] in " \t"
            ):
                capturing = True
                collected.append(line[12:] if len(line) > 12 else "")
            continue
        if len(line) >= 12 and line[:12].strip() == "":
            collected.append(line[12:] if len(line) > 12 else "")
            continue
        break
    return "\n".join(collected)


def parse_locus_fields(record_text: str) -> dict[str, str]:
    """Parse LOCUS identifier, length, molecule, topology, division, date."""
    locus_line = ""
    for line in record_text.splitlines():
        if line.startswith("LOCUS"):
            locus_line = line.rstrip("\n")
            break
    if not locus_line:
        raise NcbiNucAdapterError("GenBank record is missing a LOCUS line")
    match = _LOCUS_RE.match(locus_line)
    if match is None:
        raise NcbiNucAdapterError(
            f"LOCUS line could not be parsed: {locus_line!r}"
        )
    return {
        "locus": match.group(1),
        "locus_length": match.group(2),
        "locus_unit": match.group(3),
        "locus_molecule": match.group(4),
        "topology": match.group(5),
        "division": match.group(6),
        "date": match.group(7),
    }


def parse_accession_and_version(record_text: str) -> tuple[str, str, str]:
    """Return ``(accession, version, gi)`` from source ACCESSION/VERSION."""
    accession_body = _field_body(record_text, "ACCESSION").strip()
    tokens = accession_body.split()
    accession = tokens[0] if tokens else ""
    if accession == "":
        raise NcbiNucAdapterError("GenBank record has a missing ACCESSION")

    version_body = _field_body(record_text, "VERSION").strip()
    version_tokens = version_body.split()
    version = version_tokens[0] if version_tokens else ""
    gi = ""
    for token in version_tokens[1:]:
        if token.upper().startswith("GI:"):
            gi = token.split(":", 1)[1]
            break
    return accession, version, gi


def strand_from_location(location: str) -> str:
    """Return ``-`` only when complement() is represented in the location."""
    if _COMPLEMENT_RE.search(location):
        return "-"
    return ""


def parse_features_from_text(record_text: str) -> list[dict[str, Any]]:
    """Parse FEATURES from source text, preserving location strings and order."""
    lines = record_text.splitlines()
    capturing = False
    block: list[str] = []
    for line in lines:
        if line.startswith("FEATURES"):
            capturing = True
            continue
        if capturing:
            if line.startswith("ORIGIN") or line.strip() == "//":
                break
            block.append(line)

    features: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    qualifier_key: str | None = None
    qualifier_raw: str | None = None

    def _finish_qualifier() -> None:
        nonlocal qualifier_key, qualifier_raw
        if current is None or qualifier_key is None:
            qualifier_key = None
            qualifier_raw = None
            return
        qualifiers: dict[str, list[str]] = current["qualifiers"]
        if qualifier_raw is None:
            value = ""
        else:
            value = qualifier_raw
            if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
        qualifiers.setdefault(qualifier_key, []).append(value)
        qualifier_key = None
        qualifier_raw = None

    def _finish_feature() -> None:
        nonlocal current
        if current is None:
            return
        _finish_qualifier()
        current["strand"] = strand_from_location(str(current["location"]))
        features.append(current)
        current = None

    for line in block:
        if len(line) >= 6 and line.startswith("     ") and line[5] != " ":
            _finish_feature()
            key = line[5:21].strip()
            location = line[21:].strip() if len(line) > 21 else ""
            current = {"type": key, "location": location, "qualifiers": {}}
            continue
        if current is None:
            continue
        payload = line[21:] if len(line) > 21 else line.strip()
        stripped = payload.lstrip()
        if stripped.startswith("/") and "=" in stripped:
            _finish_qualifier()
            qualifier_key, qualifier_raw = stripped[1:].split("=", 1)
            continue
        if stripped.startswith("/") and "=" not in stripped:
            _finish_qualifier()
            qualifier_key = stripped[1:]
            qualifier_raw = None
            continue
        if qualifier_key is not None:
            qualifier_raw = (qualifier_raw or "") + "\n" + payload
            continue
        if payload.strip():
            sep = "" if current["location"].endswith("(") or payload.startswith((")", ",")) else ""
            if current["location"] and not sep and not current["location"].endswith(" "):
                current["location"] += payload.strip() if payload[:1].isspace() else payload
            else:
                current["location"] += payload

    _finish_feature()
    return features


def _reference_location_text(ref: Any) -> str:
    """Serialize Biopython reference locations without Python repr."""
    locations = getattr(ref, "location", None) or []
    parts: list[str] = []
    for loc in locations:
        start = int(loc.start) + 1
        end = int(loc.end)
        parts.append(f"{start}..{end}")
    return ",".join(parts)


def serialize_references(record: SeqRecord) -> list[dict[str, str]]:
    """Preserve the complete GenBank reference set in source order."""
    serialized: list[dict[str, str]] = []
    for ref in record.annotations.get("references", []) or []:
        serialized.append(
            {
                "authors": getattr(ref, "authors", "") or "",
                "comment": getattr(ref, "comment", "") or "",
                "consortium": getattr(ref, "consrtm", "") or "",
                "journal": getattr(ref, "journal", "") or "",
                "location": _reference_location_text(ref),
                "medline_id": getattr(ref, "medline_id", "") or "",
                "pubmed_id": getattr(ref, "pubmed_id", "") or "",
                "title": getattr(ref, "title", "") or "",
            }
        )
    return serialized


def canonical_pubmed_id(references: Sequence[Mapping[str, str]]) -> str:
    """Return a PMID only when exactly one unambiguous structured PMID exists."""
    unique: list[str] = []
    seen: set[str] = set()
    for ref in references:
        pmid = (ref.get("pubmed_id") or "").strip()
        if pmid == "" or pmid in seen:
            continue
        seen.add(pmid)
        unique.append(pmid)
    if len(unique) == 1:
        return unique[0]
    return ""


def canonical_doi(references: Sequence[Mapping[str, str]]) -> str:
    """Populate DOI only from an explicit structured GenBank DOI field.

    Local GenBank ``Reference`` objects have no dedicated DOI attribute in
    this source. S1 does not mine titles, journals, or COMMENT text.
    """
    del references
    return ""


def _source_qualifier(features: Sequence[Mapping[str, Any]], name: str) -> str:
    for feature in features:
        if feature.get("type") != "source":
            continue
        values = feature.get("qualifiers", {}).get(name) or []
        if values:
            return str(values[0])
    return ""


def _collect_dbxrefs(
    features: Sequence[Mapping[str, Any]],
    gi: str,
    record: SeqRecord,
) -> list[str]:
    dbxrefs: list[str] = []
    seen: set[str] = set()

    def _add(token: str) -> None:
        if token == "" or token in seen:
            return
        seen.add(token)
        dbxrefs.append(token)

    for feature in features:
        for value in feature.get("qualifiers", {}).get("db_xref", []):
            _add(str(value))
    for value in record.dbxrefs or []:
        _add(str(value))
    if gi:
        _add(f"GI:{gi}")
    return dbxrefs


def parse_genbank_file(
    path: Path,
) -> list[tuple[str, SeqRecord, dict[str, Any]]]:
    """Parse every GenBank record in ``path`` with source-case ORIGIN residues."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise NcbiNucAdapterError(
            f"GenBank file is not valid UTF-8: {path.name}"
        ) from exc
    except OSError as exc:
        raise NcbiNucAdapterError(
            f"GenBank file could not be read: {path.name}"
        ) from exc

    try:
        chunks = split_genbank_record_texts(text)
    except NcbiNucAdapterError:
        raise

    parsed: list[tuple[str, SeqRecord, dict[str, Any]]] = []
    for index, chunk in enumerate(chunks, start=1):
        try:
            records = list(SeqIO.parse(StringIO(chunk), "genbank"))
        except Exception as exc:
            raise NcbiNucAdapterError(
                f"GenBank file {path.name} record {index} could not be parsed"
            ) from exc
        if len(records) != 1:
            raise NcbiNucAdapterError(
                f"GenBank file {path.name} record {index} parsed as "
                f"{len(records)} records"
            )
        record = records[0]
        accession, version, gi = parse_accession_and_version(chunk)
        locus = parse_locus_fields(chunk)
        origin = extract_origin_residues(chunk)
        declared = int(locus["locus_length"])
        if len(origin) != declared:
            raise NcbiNucAdapterError(
                f"ORIGIN residue count {len(origin)} disagrees with LOCUS "
                f"length {declared} in {path.name} ACCESSION {accession}"
            )
        features = parse_features_from_text(chunk)
        references = serialize_references(record)
        extras = {
            "accession": accession,
            "version": version,
            "gi": gi,
            "locus": locus,
            "origin": origin,
            "definition": _field_body(chunk, "DEFINITION"),
            "comment": _field_body(chunk, "COMMENT"),
            "keywords": _field_body(chunk, "KEYWORDS"),
            "features": features,
            "references": references,
            "source_organism": _source_qualifier(features, "organism")
            or (record.annotations.get("organism") or ""),
            "source_mol_type": _source_qualifier(features, "mol_type"),
            "dbxrefs": _collect_dbxrefs(features, gi, record),
        }
        parsed.append((chunk, record, extras))
    return parsed


def map_ncbi_nuc_record(
    extras: Mapping[str, Any],
    *,
    registered: NcbiNucRegisteredInput,
    source_dataset: str,
    redistribution_status: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Map one parsed GenBank record to canonical + sidecar rows."""
    native_id = str(extras["accession"])
    if native_id == "":
        raise NcbiNucAdapterError("GenBank ACCESSION must be nonempty")
    record_id = f"{SOURCE_DB}:{native_id}"
    sequence_raw = str(extras["origin"])
    references = list(extras["references"])
    pubmed_id = canonical_pubmed_id(references)

    canonical = empty_corpus_record()
    canonical["record_id"] = record_id
    canonical["sequence_raw"] = sequence_raw
    canonical["source_db"] = SOURCE_DB
    canonical["source_dataset"] = source_dataset
    canonical["contributing_sources"] = SOURCE_DB
    canonical["contributing_datasets"] = source_dataset
    canonical["corroboration_count"] = "1"
    canonical["redistribution_status"] = redistribution_status
    canonical["independently_attested_by_permissive_source"] = "false"
    canonical["native_id"] = native_id
    canonical["target_name_raw"] = ""
    canonical["publication"] = ""
    canonical["doi"] = canonical_doi(references)
    canonical["pubmed_id"] = pubmed_id
    canonical["notes"] = ""
    canonical["accession"] = ""
    validated = validate_s1_record(canonical)

    locus = extras["locus"]
    sidecar = {
        "record_id": record_id,
        "native_id": native_id,
        "ncbi_nuc_registered_path": registered.relative_path,
        "ncbi_nuc_input_basename": Path(registered.relative_path).name,
        "ncbi_nuc_file_sha256": registered.sha256,
        "ncbi_nuc_locus": str(locus["locus"]),
        "ncbi_nuc_locus_length": str(locus["locus_length"]),
        "ncbi_nuc_locus_molecule": str(locus["locus_molecule"]),
        "ncbi_nuc_topology": str(locus["topology"]),
        "ncbi_nuc_division": str(locus["division"]),
        "ncbi_nuc_date": str(locus["date"]),
        "ncbi_nuc_accession": native_id,
        "ncbi_nuc_version": str(extras["version"]),
        "ncbi_nuc_gi": str(extras["gi"]),
        "ncbi_nuc_definition": str(extras["definition"]),
        "ncbi_nuc_comment": str(extras["comment"]),
        "ncbi_nuc_keywords": str(extras["keywords"]),
        "ncbi_nuc_source_organism": str(extras["source_organism"]),
        "ncbi_nuc_source_mol_type": str(extras["source_mol_type"]),
        "ncbi_nuc_dbxrefs_json": dumps_json(list(extras["dbxrefs"])),
        "ncbi_nuc_features_json": dumps_json(list(extras["features"])),
        "ncbi_nuc_references_json": dumps_json(references),
        "ncbi_nuc_origin_length": str(len(sequence_raw)),
        "ncbi_nuc_origin_residues": sequence_raw,
    }
    return validated, sidecar


def extract_ncbi_nuc(
    inputs: Sequence[NcbiNucRegisteredInput],
    *,
    source_dataset: str,
    redistribution_status: str,
    expected_records: int | None = EXPECTED_INPUT_RECORDS,
) -> NcbiNucExtractionResult:
    """Extract every parsed GenBank record from registry-ordered files.

    ``inputs`` must already be in deterministic registry order. Filesystem
    glob order is not used. ``expected_records`` is the total parsed-record
    count across the logical source. Pass ``expected_records=None`` only
    in unit tests that skip the production count gate.
    """
    if not inputs:
        raise NcbiNucAdapterError("ncbi_nuc has no registered GenBank inputs")

    canonical_rows: list[dict[str, str]] = []
    sidecar_rows: list[dict[str, str]] = []
    stats = NcbiNucExtractionStats()
    stats.input_files = len(inputs)
    stats.order_preserved = True
    sequence_exact = True
    native_ids: list[str] = []
    record_ids: list[str] = []
    seen_accessions: set[str] = set()
    seen_record_ids: set[str] = set()
    pmid_native_ids: list[str] = []

    for registered in inputs:
        parsed_records = parse_genbank_file(registered.path)
        if (
            registered.n_rows_expected is not None
            and len(parsed_records) != registered.n_rows_expected
        ):
            raise NcbiNucAdapterError(
                "GenBank record-count mismatch for "
                f"{registered.relative_path}: expected "
                f"{registered.n_rows_expected}, actual {len(parsed_records)}"
            )
        for _chunk, _record, extras in parsed_records:
            canonical, sidecar = map_ncbi_nuc_record(
                extras,
                registered=registered,
                source_dataset=source_dataset,
                redistribution_status=redistribution_status,
            )
            native_id = canonical["native_id"]
            record_id = canonical["record_id"]
            if native_id in seen_accessions:
                raise NcbiNucAdapterError(
                    f"Duplicate ACCESSION across registered NCBI inputs: "
                    f"{native_id!r}"
                )
            if record_id in seen_record_ids:
                raise NcbiNucAdapterError(
                    f"Duplicate record_id across registered NCBI inputs: "
                    f"{record_id!r}"
                )
            seen_accessions.add(native_id)
            seen_record_ids.add(record_id)

            if canonical["sequence_raw"] != extras["origin"]:
                sequence_exact = False
            if sidecar["ncbi_nuc_origin_residues"] != extras["origin"]:
                sequence_exact = False

            if canonical["sequence_raw"] == "":
                stats.missing_sequences += 1
            else:
                stats.nonempty_sequences += 1
            if canonical["target_name_raw"] == "":
                stats.empty_target_name_raw += 1
            else:
                stats.nonempty_target_name_raw += 1
            if canonical["publication"] != "":
                stats.nonempty_publication += 1
            if canonical["doi"] != "":
                stats.nonempty_doi += 1
            if canonical["pubmed_id"] != "":
                stats.nonempty_pmid += 1
                pmid_native_ids.append(native_id)
            if canonical["accession"] == "":
                stats.empty_canonical_accession += 1
            if sidecar["ncbi_nuc_origin_length"] == sidecar["ncbi_nuc_locus_length"]:
                stats.origin_length_matches_locus += 1

            native_ids.append(native_id)
            record_ids.append(record_id)
            canonical_rows.append(canonical)
            sidecar_rows.append(sidecar)

    stats.input_rows = len(canonical_rows)
    stats.canonical_rows = len(canonical_rows)
    stats.sidecar_rows = len(sidecar_rows)
    stats.unique_native_ids = len(set(native_ids))
    stats.unique_record_ids = len(set(record_ids))
    stats.sequence_exact_copy_ok = sequence_exact
    stats.first_native_id = native_ids[0] if native_ids else ""
    stats.last_native_id = native_ids[-1] if native_ids else ""
    stats.pmid_native_ids = tuple(pmid_native_ids)

    _assert_extraction_invariants(stats, expected_records=expected_records)
    return NcbiNucExtractionResult(
        canonical_rows=canonical_rows,
        sidecar_rows=sidecar_rows,
        stats=stats,
    )


def _assert_extraction_invariants(
    stats: NcbiNucExtractionStats,
    *,
    expected_records: int | None,
) -> None:
    n = stats.input_rows
    if expected_records is not None and n != expected_records:
        raise NcbiNucAdapterError(
            f"input_rows must be {expected_records}; got {n}"
        )
    if stats.canonical_rows != n:
        raise NcbiNucAdapterError(
            f"canonical_rows ({stats.canonical_rows}) != input_rows ({n})"
        )
    if stats.sidecar_rows != n:
        raise NcbiNucAdapterError(
            f"sidecar_rows ({stats.sidecar_rows}) != input_rows ({n})"
        )
    if stats.unique_native_ids != n:
        raise NcbiNucAdapterError(
            f"unique_native_ids ({stats.unique_native_ids}) != input_rows ({n})"
        )
    if stats.unique_record_ids != n:
        raise NcbiNucAdapterError(
            f"unique_record_ids ({stats.unique_record_ids}) != input_rows ({n})"
        )
    if not stats.sequence_exact_copy_ok:
        raise NcbiNucAdapterError("sequence_raw ORIGIN exact-copy validation failed")
    if not stats.order_preserved:
        raise NcbiNucAdapterError("input order was not preserved")
    if stats.nonempty_target_name_raw != 0:
        raise NcbiNucAdapterError(
            "S1 must not populate target_name_raw for ncbi_nuc; "
            f"got {stats.nonempty_target_name_raw} nonempty values"
        )
    if stats.empty_target_name_raw != n:
        raise NcbiNucAdapterError(
            "every ncbi_nuc S1 row must have empty target_name_raw"
        )
    if stats.empty_canonical_accession != n:
        raise NcbiNucAdapterError(
            "canonical accession must remain empty at S1 for every ncbi_nuc row"
        )
    if stats.missing_sequences != 0:
        raise NcbiNucAdapterError(
            "every parsed ncbi_nuc record must have ORIGIN sequence"
        )
    if stats.origin_length_matches_locus != n:
        raise NcbiNucAdapterError(
            "ORIGIN residue count must agree with LOCUS length for every record"
        )

    if expected_records == EXPECTED_INPUT_RECORDS:
        if stats.nonempty_sequences != EXPECTED_NONEMPTY_SEQUENCES:
            raise NcbiNucAdapterError(
                f"nonempty sequence_raw must be {EXPECTED_NONEMPTY_SEQUENCES}; "
                f"got {stats.nonempty_sequences}"
            )
        if stats.missing_sequences != EXPECTED_MISSING_SEQUENCES:
            raise NcbiNucAdapterError(
                f"missing sequence_raw must be {EXPECTED_MISSING_SEQUENCES}; "
                f"got {stats.missing_sequences}"
            )
        if stats.nonempty_pmid != EXPECTED_NONEMPTY_PMID:
            raise NcbiNucAdapterError(
                f"nonempty pubmed_id must be {EXPECTED_NONEMPTY_PMID}; "
                f"got {stats.nonempty_pmid}"
            )
        if stats.nonempty_doi != EXPECTED_NONEMPTY_DOI:
            raise NcbiNucAdapterError(
                f"nonempty doi must be {EXPECTED_NONEMPTY_DOI}; "
                f"got {stats.nonempty_doi}"
            )
        if stats.nonempty_publication != EXPECTED_NONEMPTY_PUBLICATION:
            raise NcbiNucAdapterError(
                f"nonempty publication must be {EXPECTED_NONEMPTY_PUBLICATION}; "
                f"got {stats.nonempty_publication}"
            )
        if stats.empty_canonical_accession != EXPECTED_EMPTY_ACCESSION:
            raise NcbiNucAdapterError(
                "canonical accession must remain empty for all 18 records"
            )


def write_sidecar_csv_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Atomically write the NCBI Nucleotide source-metadata sidecar."""
    write_corpus_csv_atomic(path, rows, columns=SIDECAR_COLUMNS)

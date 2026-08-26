"""AptaDB S1 adapter: interaction-grain verbatim extraction.

Reads the three registry-bound official exports (interaction spine + aptamer
and protein lookups). Emits one canonical record per interaction row. Does
not perform S2 normalisation, filtering, trimming, molecule inference,
evidence scoring, or deduplication.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from common.corpus_schema import (
    empty_corpus_record,
    validate_s1_record,
    write_corpus_csv_atomic,
)
from s0_build_registry import detect_csv_text_encoding

SOURCE_DB: Final[str] = "aptadb"

INTERACTION_LEADING_COLUMNS: Final[tuple[str, ...]] = (
    "Index",
    "Apta_index",
    "TargetID",
    "Sequence",
    "Target chemistry",
    "Binding Conditions/Buffer",
    "Reference(pubmed ID)",
)
INTERACTION_TRAILING_HEADER: Final[str] = ""

APTAMER_LEADING_COLUMNS: Final[tuple[str, ...]] = (
    "Apta_index",
    "Sequence",
    "Aptamer description",
    "Aptamer Chemistry",
    "Length",
    "GC content",
    "Molecular weight",
)
APTAMER_TRAILING_COLUMNS: Final[tuple[str, ...]] = (
    "Number of tetrads",
    "G-Score",
    "Function",
    "Applications",
    "Assay",
)
APTAMER_MOLARITY_PREFIX: Final[str] = "Molarity of 1 "
APTAMER_MOLARITY_SUFFIX: Final[str] = " solution"

PROTEIN_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    "Uni-port ID",
    "Entry name",
    "Protein names",
    "Gene names",
    "Status",
    "Organism",
    "Length",
    "Mass",
    "Activity regulation",
    "Involvement in disease",
    "Catalytic activity",
    "Cross-reference (PDB)",
    "Function",
)

TARGET_CHEMISTRY_PROTEIN: Final[str] = "Protein"
TARGET_CHEMISTRY_NON_PROTEIN: Final[frozenset[str]] = frozenset(
    {"Molecule", "Cell", "Other"}
)
ALLOWED_TARGET_CHEMISTRY: Final[frozenset[str]] = frozenset(
    {TARGET_CHEMISTRY_PROTEIN} | TARGET_CHEMISTRY_NON_PROTEIN
)

SIDECAR_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "aptadb_interaction_index",
    "aptadb_apta_index",
    "aptadb_target_id",
    "aptadb_target_chemistry",
    "aptadb_binding_conditions_buffer",
    "aptadb_reference_pubmed_id",
    "aptadb_interaction_unnamed_trailing",
    "aptadb_interaction_sequence",
    "aptadb_aptamer_sequence",
    "aptadb_aptamer_description",
    "aptadb_aptamer_chemistry",
    "aptadb_aptamer_length",
    "aptadb_aptamer_gc_content",
    "aptadb_aptamer_molecular_weight",
    "aptadb_aptamer_molarity",
    "aptadb_aptamer_number_of_tetrads",
    "aptadb_aptamer_g_score",
    "aptadb_aptamer_function",
    "aptadb_aptamer_applications",
    "aptadb_aptamer_assay",
    "aptadb_uniprot_id",
    "aptadb_entry_name",
    "aptadb_protein_names",
    "aptadb_gene_names",
    "aptadb_status",
    "aptadb_organism",
    "aptadb_protein_length",
    "aptadb_mass",
    "aptadb_activity_regulation",
    "aptadb_involvement_in_disease",
    "aptadb_catalytic_activity",
    "aptadb_pdb_cross_reference",
    "aptadb_protein_function",
    "aptadb_sequence_agreement",
    "aptadb_aptamer_join_status",
    "aptadb_protein_join_status",
    "aptadb_target_name_source",
)

UNLINKED_COLUMNS: Final[tuple[str, ...]] = (
    "apta_index",
    "aptamer_chemistry",
    "sequence",
    "aptamer_description",
    "length",
    "gc_content",
    "molecular_weight",
    "function",
    "applications",
    "assay",
    "reconciliation_status",
    "planned_s3_reason",
)

EXPECTED_INTERACTION_ROWS: Final[int] = 1350
EXPECTED_APTAMER_ROWS: Final[int] = 1293
EXPECTED_PROTEIN_ROWS: Final[int] = 194
EXPECTED_PROTEIN_INTERACTIONS: Final[int] = 639
EXPECTED_UNLINKED_APTAMERS: Final[int] = 37
EXPECTED_SEQUENCE_MISMATCHES: Final[int] = 0

UNLINKED_STATUS: Final[str] = "unlinked_no_interaction_row"
PLANNED_S3_MISSING_TARGET: Final[str] = "missing_target"


class AptaDBAdapterError(ValueError):
    """Hard failure while validating or extracting the AptaDB source."""


@dataclass
class AptaDBExtractionStats:
    """Aggregate counts for the AptaDB S1 report (no sequence values)."""

    input_rows: int = 0
    canonical_rows: int = 0
    sidecar_rows: int = 0
    unique_native_ids: int = 0
    unique_record_ids: int = 0
    nonempty_sequences: int = 0
    missing_sequences: int = 0
    aptamer_rows: int = 0
    protein_rows: int = 0
    aptamer_joins: int = 0
    failed_aptamer_joins: int = 0
    sequence_mismatches: int = 0
    sequence_exact_copy_ok: bool = False
    protein_interactions: int = 0
    protein_joins: int = 0
    failed_protein_joins: int = 0
    proteins_represented: int = 0
    nonprotein_interactions: int = 0
    empty_target_name_raw: int = 0
    nonempty_target_name_raw: int = 0
    nonempty_pmid: int = 0
    nonempty_publication: int = 0
    unnamed_trailing_nonempty: int = 0
    unlinked_aptamers: int = 0
    unlinked_chemistry_counts: dict[str, int] = field(default_factory=dict)
    target_chemistry_counts: dict[str, int] = field(default_factory=dict)
    aptamer_chemistry_counts: dict[str, int] = field(default_factory=dict)
    order_preserved: bool = False
    native_id_strategy: str = (
        "interaction.Index verbatim; record_id = aptadb:{Index}"
    )


@dataclass
class AptaDBExtractionResult:
    """Canonical rows, sidecar rows, unlinked aptamers, and stats."""

    canonical_rows: list[dict[str, str]]
    sidecar_rows: list[dict[str, str]]
    unlinked_rows: list[dict[str, str]]
    stats: AptaDBExtractionStats = field(default_factory=AptaDBExtractionStats)


def encode_aptadb_notes(apta_index: str, description: str) -> str:
    """Encode Apta_index (and optional description) as JSON for ``notes``."""
    payload: dict[str, str] = {"aptamer_id": apta_index}
    if description != "":
        payload["aptamer_description"] = description
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _cell(row: Mapping[str, str], column: str) -> str:
    value = row.get(column)
    return "" if value is None else value


def _normalise_fieldnames(fieldnames: Sequence[str] | None) -> list[str]:
    if fieldnames is None:
        return []
    return ["" if name is None else name for name in fieldnames]


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV with utf-8-sig, falling back to latin-1. Does not rewrite."""
    encoding = detect_csv_text_encoding(path)
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = _normalise_fieldnames(reader.fieldnames)
        rows: list[dict[str, str]] = []
        for raw in reader:
            row: dict[str, str] = {}
            for key, value in raw.items():
                column = "" if key is None else key
                if isinstance(value, list):
                    raise AptaDBAdapterError(
                        f"{path.name} has extra CSV fields beyond the header"
                    )
                row[column] = "" if value is None else value
            rows.append(row)
    return fieldnames, rows


def _require_exact_header(
    *,
    actual: Sequence[str],
    expected: Sequence[str],
    label: str,
) -> None:
    actual_list = list(actual)
    expected_list = list(expected)
    if actual_list != expected_list:
        if set(actual_list) != set(expected_list):
            missing = [c for c in expected_list if c not in actual_list]
            extra = [c for c in actual_list if c not in expected_list]
            parts: list[str] = []
            if missing:
                parts.append(f"missing={missing!r}")
            if extra:
                parts.append(f"extra={extra!r}")
            raise AptaDBAdapterError(
                f"{label} columns do not match the required schema; "
                + "; ".join(parts)
            )
        raise AptaDBAdapterError(
            f"{label} columns are reordered relative to the required schema"
        )


def validate_interaction_header(fieldnames: Sequence[str] | None) -> None:
    """Accept the official eight-column interaction header, including the trailing empty name."""
    actual = _normalise_fieldnames(fieldnames)
    if not actual:
        raise AptaDBAdapterError("AptaDB interaction.csv has no header row")
    expected = list(INTERACTION_LEADING_COLUMNS) + [INTERACTION_TRAILING_HEADER]
    _require_exact_header(
        actual=actual,
        expected=expected,
        label="AptaDB interaction.csv",
    )


def validate_aptamer_header(fieldnames: Sequence[str] | None) -> str:
    """Validate aptamer headers; return the source molarity column name unchanged."""
    actual = _normalise_fieldnames(fieldnames)
    if len(actual) != 13:
        raise AptaDBAdapterError(
            f"AptaDB aptamer.csv must have 13 columns; got {len(actual)}"
        )
    if actual[:7] != list(APTAMER_LEADING_COLUMNS):
        _require_exact_header(
            actual=actual[:7],
            expected=APTAMER_LEADING_COLUMNS,
            label="AptaDB aptamer.csv (leading columns)",
        )
    if actual[8:] != list(APTAMER_TRAILING_COLUMNS):
        _require_exact_header(
            actual=actual[8:],
            expected=APTAMER_TRAILING_COLUMNS,
            label="AptaDB aptamer.csv (trailing columns)",
        )
    molarity = actual[7]
    if not (
        molarity.startswith(APTAMER_MOLARITY_PREFIX)
        and molarity.endswith(APTAMER_MOLARITY_SUFFIX)
    ):
        raise AptaDBAdapterError(
            "AptaDB aptamer.csv molarity column is not in the expected "
            "position or does not match the ASCII 'Molarity of 1 … solution' "
            "shape; the raw header glyph is not repaired"
        )
    return molarity


def validate_protein_header(fieldnames: Sequence[str] | None) -> None:
    actual = _normalise_fieldnames(fieldnames)
    if not actual:
        raise AptaDBAdapterError("AptaDB protein.csv has no header row")
    _require_exact_header(
        actual=actual,
        expected=PROTEIN_INPUT_COLUMNS,
        label="AptaDB protein.csv",
    )


def _index_unique(
    rows: Sequence[Mapping[str, str]],
    column: str,
    *,
    label: str,
) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for offset, row in enumerate(rows, start=2):
        key = _cell(row, column)
        if key == "":
            raise AptaDBAdapterError(
                f"{label} row {offset} has a blank {column}"
            )
        if key in index:
            raise AptaDBAdapterError(
                f"Duplicate {label} {column}: {key!r}"
            )
        index[key] = dict(row)
    return index


def map_interaction_row(
    interaction_row: Mapping[str, str],
    aptamer_row: Mapping[str, str],
    protein_row: Mapping[str, str] | None,
    *,
    source_dataset: str,
    redistribution_status: str,
    molarity_column: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Map one interaction to canonical + sidecar records."""
    native_id = _cell(interaction_row, "Index")
    apta_index = _cell(interaction_row, "Apta_index")
    interaction_sequence = _cell(interaction_row, "Sequence")
    aptamer_sequence = _cell(aptamer_row, "Sequence")
    if interaction_sequence != aptamer_sequence:
        raise AptaDBAdapterError(
            f"Sequence disagreement for interaction Index={native_id!r} "
            f"Apta_index={apta_index!r}: interaction and aptamer Sequence "
            "fields are not byte-identical"
        )

    target_chemistry = _cell(interaction_row, "Target chemistry")
    if target_chemistry not in ALLOWED_TARGET_CHEMISTRY:
        raise AptaDBAdapterError(
            f"Unrecognised Target chemistry {target_chemistry!r} for "
            f"interaction Index={native_id!r}"
        )

    if target_chemistry == TARGET_CHEMISTRY_PROTEIN:
        if protein_row is None:
            raise AptaDBAdapterError(
                f"Protein TargetID did not join protein.csv for "
                f"interaction Index={native_id!r}"
            )
        target_name_raw = _cell(protein_row, "Protein names")
        target_name_source = "protein_names"
        protein_join_status = "joined"
    else:
        target_name_raw = ""
        target_name_source = "unresolved_missing_lookup_table"
        protein_join_status = "not_applicable"

    record = empty_corpus_record()
    record["record_id"] = f"aptadb:{native_id}"
    record["sequence_raw"] = aptamer_sequence
    record["source_db"] = SOURCE_DB
    record["source_dataset"] = source_dataset
    record["contributing_sources"] = SOURCE_DB
    record["contributing_datasets"] = source_dataset
    record["corroboration_count"] = "1"
    record["redistribution_status"] = redistribution_status
    record["independently_attested_by_permissive_source"] = "false"
    record["native_id"] = native_id
    record["target_name_raw"] = target_name_raw
    record["pubmed_id"] = _cell(interaction_row, "Reference(pubmed ID)")
    record["notes"] = encode_aptadb_notes(
        apta_index,
        _cell(aptamer_row, "Aptamer description"),
    )
    validated = validate_s1_record(record)

    protein = protein_row or {}
    sidecar: dict[str, str] = {
        "record_id": validated["record_id"],
        "aptadb_interaction_index": native_id,
        "aptadb_apta_index": apta_index,
        "aptadb_target_id": _cell(interaction_row, "TargetID"),
        "aptadb_target_chemistry": target_chemistry,
        "aptadb_binding_conditions_buffer": _cell(
            interaction_row, "Binding Conditions/Buffer"
        ),
        "aptadb_reference_pubmed_id": _cell(
            interaction_row, "Reference(pubmed ID)"
        ),
        "aptadb_interaction_unnamed_trailing": _cell(
            interaction_row, INTERACTION_TRAILING_HEADER
        ),
        "aptadb_interaction_sequence": interaction_sequence,
        "aptadb_aptamer_sequence": aptamer_sequence,
        "aptadb_aptamer_description": _cell(aptamer_row, "Aptamer description"),
        "aptadb_aptamer_chemistry": _cell(aptamer_row, "Aptamer Chemistry"),
        "aptadb_aptamer_length": _cell(aptamer_row, "Length"),
        "aptadb_aptamer_gc_content": _cell(aptamer_row, "GC content"),
        "aptadb_aptamer_molecular_weight": _cell(aptamer_row, "Molecular weight"),
        "aptadb_aptamer_molarity": _cell(aptamer_row, molarity_column),
        "aptadb_aptamer_number_of_tetrads": _cell(
            aptamer_row, "Number of tetrads"
        ),
        "aptadb_aptamer_g_score": _cell(aptamer_row, "G-Score"),
        "aptadb_aptamer_function": _cell(aptamer_row, "Function"),
        "aptadb_aptamer_applications": _cell(aptamer_row, "Applications"),
        "aptadb_aptamer_assay": _cell(aptamer_row, "Assay"),
        "aptadb_uniprot_id": _cell(protein, "Uni-port ID"),
        "aptadb_entry_name": _cell(protein, "Entry name"),
        "aptadb_protein_names": _cell(protein, "Protein names"),
        "aptadb_gene_names": _cell(protein, "Gene names"),
        "aptadb_status": _cell(protein, "Status"),
        "aptadb_organism": _cell(protein, "Organism"),
        "aptadb_protein_length": _cell(protein, "Length"),
        "aptadb_mass": _cell(protein, "Mass"),
        "aptadb_activity_regulation": _cell(protein, "Activity regulation"),
        "aptadb_involvement_in_disease": _cell(
            protein, "Involvement in disease"
        ),
        "aptadb_catalytic_activity": _cell(protein, "Catalytic activity"),
        "aptadb_pdb_cross_reference": _cell(protein, "Cross-reference (PDB)"),
        "aptadb_protein_function": _cell(protein, "Function"),
        "aptadb_sequence_agreement": "exact",
        "aptadb_aptamer_join_status": "joined",
        "aptadb_protein_join_status": protein_join_status,
        "aptadb_target_name_source": target_name_source,
    }
    return validated, sidecar


def _unlinked_row(aptamer_row: Mapping[str, str]) -> dict[str, str]:
    return {
        "apta_index": _cell(aptamer_row, "Apta_index"),
        "aptamer_chemistry": _cell(aptamer_row, "Aptamer Chemistry"),
        "sequence": _cell(aptamer_row, "Sequence"),
        "aptamer_description": _cell(aptamer_row, "Aptamer description"),
        "length": _cell(aptamer_row, "Length"),
        "gc_content": _cell(aptamer_row, "GC content"),
        "molecular_weight": _cell(aptamer_row, "Molecular weight"),
        "function": _cell(aptamer_row, "Function"),
        "applications": _cell(aptamer_row, "Applications"),
        "assay": _cell(aptamer_row, "Assay"),
        "reconciliation_status": UNLINKED_STATUS,
        "planned_s3_reason": PLANNED_S3_MISSING_TARGET,
    }


def extract_aptadb(
    *,
    interaction_path: Path,
    aptamer_path: Path,
    protein_path: Path,
    source_dataset: str,
    redistribution_status: str,
    expected_interaction_rows: int | None = EXPECTED_INTERACTION_ROWS,
    expected_aptamer_rows: int | None = EXPECTED_APTAMER_ROWS,
    expected_protein_rows: int | None = EXPECTED_PROTEIN_ROWS,
) -> AptaDBExtractionResult:
    """Extract every interaction row into canonical and sidecar tables."""
    interaction_header, interaction_rows = read_csv_rows(interaction_path)
    validate_interaction_header(interaction_header)
    aptamer_header, aptamer_rows = read_csv_rows(aptamer_path)
    molarity_column = validate_aptamer_header(aptamer_header)
    protein_header, protein_rows = read_csv_rows(protein_path)
    validate_protein_header(protein_header)

    if (
        expected_interaction_rows is not None
        and len(interaction_rows) != expected_interaction_rows
    ):
        raise AptaDBAdapterError(
            f"AptaDB interaction.csv row count must be "
            f"{expected_interaction_rows}; got {len(interaction_rows)}"
        )
    if (
        expected_aptamer_rows is not None
        and len(aptamer_rows) != expected_aptamer_rows
    ):
        raise AptaDBAdapterError(
            f"AptaDB aptamer.csv row count must be {expected_aptamer_rows}; "
            f"got {len(aptamer_rows)}"
        )
    if (
        expected_protein_rows is not None
        and len(protein_rows) != expected_protein_rows
    ):
        raise AptaDBAdapterError(
            f"AptaDB protein.csv row count must be {expected_protein_rows}; "
            f"got {len(protein_rows)}"
        )

    aptamer_by_id = _index_unique(
        aptamer_rows, "Apta_index", label="aptamer.csv"
    )
    protein_by_id = _index_unique(
        protein_rows, "Uni-port ID", label="protein.csv"
    )

    canonical_rows: list[dict[str, str]] = []
    sidecar_rows: list[dict[str, str]] = []
    stats = AptaDBExtractionStats()
    stats.input_rows = len(interaction_rows)
    stats.aptamer_rows = len(aptamer_rows)
    stats.protein_rows = len(protein_rows)
    stats.order_preserved = True
    sequence_exact = True
    native_ids: list[str] = []
    record_ids: list[str] = []
    linked_apta: set[str] = set()
    proteins_used: set[str] = set()
    chemistry_counts: Counter[str] = Counter()
    aptamer_chem_counts: Counter[str] = Counter()

    for offset, interaction_row in enumerate(interaction_rows, start=2):
        native_id = _cell(interaction_row, "Index")
        if native_id == "":
            raise AptaDBAdapterError(
                f"interaction.csv row {offset} has a blank Index"
            )
        if native_id in native_ids:
            raise AptaDBAdapterError(
                f"Duplicate interaction Index: {native_id!r}"
            )
        apta_index = _cell(interaction_row, "Apta_index")
        aptamer_row = aptamer_by_id.get(apta_index)
        if aptamer_row is None:
            raise AptaDBAdapterError(
                f"interaction.csv Index={native_id!r} Apta_index="
                f"{apta_index!r} does not join aptamer.csv"
            )
        stats.aptamer_joins += 1
        linked_apta.add(apta_index)

        interaction_sequence = _cell(interaction_row, "Sequence")
        aptamer_sequence = _cell(aptamer_row, "Sequence")
        if interaction_sequence != aptamer_sequence:
            stats.sequence_mismatches += 1
            sequence_exact = False
            raise AptaDBAdapterError(
                f"Sequence disagreement for interaction Index={native_id!r} "
                f"Apta_index={apta_index!r}: interaction and aptamer Sequence "
                "fields are not byte-identical"
            )

        target_chemistry = _cell(interaction_row, "Target chemistry")
        chemistry_counts[target_chemistry or "(blank)"] += 1
        protein_row: dict[str, str] | None = None
        if target_chemistry == TARGET_CHEMISTRY_PROTEIN:
            stats.protein_interactions += 1
            target_id = _cell(interaction_row, "TargetID")
            protein_row = protein_by_id.get(target_id)
            if protein_row is None:
                stats.failed_protein_joins += 1
                raise AptaDBAdapterError(
                    f"Protein TargetID {target_id!r} for interaction "
                    f"Index={native_id!r} does not join protein.csv"
                )
            stats.protein_joins += 1
            proteins_used.add(target_id)
        elif target_chemistry in TARGET_CHEMISTRY_NON_PROTEIN:
            stats.nonprotein_interactions += 1
        else:
            raise AptaDBAdapterError(
                f"Unrecognised Target chemistry {target_chemistry!r} for "
                f"interaction Index={native_id!r}"
            )

        canonical, sidecar = map_interaction_row(
            interaction_row,
            aptamer_row,
            protein_row,
            source_dataset=source_dataset,
            redistribution_status=redistribution_status,
            molarity_column=molarity_column,
        )
        if canonical["sequence_raw"] != aptamer_sequence:
            sequence_exact = False
            raise AptaDBAdapterError(
                "canonical sequence_raw is not an exact copy of "
                "aptamer.csv.Sequence"
            )
        if canonical["publication"] != "":
            raise AptaDBAdapterError(
                "AptaDB S1 must not populate publication; PMID stays in "
                "pubmed_id only"
            )

        aptamer_chem = _cell(aptamer_row, "Aptamer Chemistry")
        aptamer_chem_counts[aptamer_chem or "(blank)"] += 1
        if canonical["sequence_raw"] == "":
            stats.missing_sequences += 1
        else:
            stats.nonempty_sequences += 1
        if canonical["target_name_raw"] == "":
            stats.empty_target_name_raw += 1
        else:
            stats.nonempty_target_name_raw += 1
        if canonical["pubmed_id"] != "":
            stats.nonempty_pmid += 1
        if sidecar["aptadb_interaction_unnamed_trailing"] != "":
            stats.unnamed_trailing_nonempty += 1

        native_ids.append(canonical["native_id"])
        record_ids.append(canonical["record_id"])
        canonical_rows.append(canonical)
        sidecar_rows.append(sidecar)

    unlinked_rows = [
        _unlinked_row(row)
        for row in aptamer_rows
        if _cell(row, "Apta_index") not in linked_apta
    ]
    unlinked_rows.sort(key=lambda item: item["apta_index"])
    unlinked_chem = Counter(
        row["aptamer_chemistry"] or "(blank)" for row in unlinked_rows
    )

    stats.canonical_rows = len(canonical_rows)
    stats.sidecar_rows = len(sidecar_rows)
    stats.unique_native_ids = len(set(native_ids))
    stats.unique_record_ids = len(set(record_ids))
    stats.sequence_exact_copy_ok = sequence_exact
    stats.proteins_represented = len(proteins_used)
    stats.unlinked_aptamers = len(unlinked_rows)
    stats.unlinked_chemistry_counts = dict(sorted(unlinked_chem.items()))
    stats.target_chemistry_counts = dict(sorted(chemistry_counts.items()))
    stats.aptamer_chemistry_counts = dict(sorted(aptamer_chem_counts.items()))
    stats.failed_aptamer_joins = 0

    _assert_extraction_invariants(
        stats,
        expected_interaction_rows=expected_interaction_rows,
        expected_aptamer_rows=expected_aptamer_rows,
        expected_protein_rows=expected_protein_rows,
    )

    return AptaDBExtractionResult(
        canonical_rows=canonical_rows,
        sidecar_rows=sidecar_rows,
        unlinked_rows=unlinked_rows,
        stats=stats,
    )


def _assert_extraction_invariants(
    stats: AptaDBExtractionStats,
    *,
    expected_interaction_rows: int | None,
    expected_aptamer_rows: int | None,
    expected_protein_rows: int | None,
) -> None:
    n = stats.input_rows
    if expected_interaction_rows is not None and n != expected_interaction_rows:
        raise AptaDBAdapterError(
            f"input_rows must be {expected_interaction_rows}; got {n}"
        )
    if stats.canonical_rows != n:
        raise AptaDBAdapterError(
            f"canonical_rows ({stats.canonical_rows}) != input_rows ({n})"
        )
    if stats.sidecar_rows != n:
        raise AptaDBAdapterError(
            f"sidecar_rows ({stats.sidecar_rows}) != input_rows ({n})"
        )
    if stats.unique_native_ids != n:
        raise AptaDBAdapterError(
            f"unique_native_ids ({stats.unique_native_ids}) != input_rows ({n})"
        )
    if stats.unique_record_ids != n:
        raise AptaDBAdapterError(
            f"unique_record_ids ({stats.unique_record_ids}) != input_rows ({n})"
        )
    if not stats.sequence_exact_copy_ok:
        raise AptaDBAdapterError("sequence_raw exact-copy validation failed")
    if stats.sequence_mismatches != 0:
        raise AptaDBAdapterError(
            f"sequence mismatches must be 0; got {stats.sequence_mismatches}"
        )
    if stats.failed_aptamer_joins != 0:
        raise AptaDBAdapterError("aptamer join failures are not permitted")
    if stats.failed_protein_joins != 0:
        raise AptaDBAdapterError("protein join failures are not permitted")
    if not stats.order_preserved:
        raise AptaDBAdapterError("input order was not preserved")

    production = (
        expected_interaction_rows == EXPECTED_INTERACTION_ROWS
        and expected_aptamer_rows == EXPECTED_APTAMER_ROWS
        and expected_protein_rows == EXPECTED_PROTEIN_ROWS
    )
    if production:
        if stats.protein_interactions != EXPECTED_PROTEIN_INTERACTIONS:
            raise AptaDBAdapterError(
                f"protein interactions must be {EXPECTED_PROTEIN_INTERACTIONS}; "
                f"got {stats.protein_interactions}"
            )
        if stats.protein_joins != EXPECTED_PROTEIN_INTERACTIONS:
            raise AptaDBAdapterError(
                f"protein joins must be {EXPECTED_PROTEIN_INTERACTIONS}; "
                f"got {stats.protein_joins}"
            )
        if stats.proteins_represented != EXPECTED_PROTEIN_ROWS:
            raise AptaDBAdapterError(
                f"proteins represented must be {EXPECTED_PROTEIN_ROWS}; "
                f"got {stats.proteins_represented}"
            )
        if stats.unlinked_aptamers != EXPECTED_UNLINKED_APTAMERS:
            raise AptaDBAdapterError(
                f"unlinked aptamers must be {EXPECTED_UNLINKED_APTAMERS}; "
                f"got {stats.unlinked_aptamers}"
            )
        if stats.sequence_mismatches != EXPECTED_SEQUENCE_MISMATCHES:
            raise AptaDBAdapterError("production snapshot sequence mismatches")


def write_sidecar_csv_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Atomically write the AptaDB source-metadata sidecar."""
    write_corpus_csv_atomic(path, rows, columns=SIDECAR_COLUMNS)


def write_unlinked_csv_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Atomically write the unlinked-aptamer reconciliation table."""
    write_corpus_csv_atomic(path, rows, columns=UNLINKED_COLUMNS)

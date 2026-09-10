"""AptaDiff Dataset A/B S1 adapters: verbatim extraction into the canonical schema.

Two distinct Tier-1 source identities share a schema-neutral ``seq,p6`` CSV
helper. They do not share a combined ``aptadiff`` output. S1 does not
classify molecule type or chemistry, convert T→U, trim constant regions,
canonicalise targets, interpret ``p6``, filter N-containing rows, cap,
downsample, or deduplicate.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any, Final, Mapping, Sequence

from common.corpus_schema import (
    empty_corpus_record,
    validate_s1_record,
    write_corpus_csv_atomic,
)

APTADIFF_INPUT_COLUMNS: Final[tuple[str, ...]] = ("seq", "p6")

SIDECAR_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "aptadiff_csv_data_row",
    "aptadiff_seq",
    "aptadiff_p6",
    "aptadiff_dataset",
    "aptadiff_source_key",
    "aptadiff_documented_target",
    "aptadiff_target_provenance",
)

NATIVE_ID_WIDTH: Final[int] = 5
APTADIFF_SOURCE_KEYS: Final[frozenset[str]] = frozenset(
    {"aptadiff_a", "aptadiff_b"}
)

# Derived latent-coordinate table and deferred Dataset C/D FASTQs must never
# be registered or dispatched as Dataset A/B corpus inputs.
FORBIDDEN_APTADIFF_BASENAMES: Final[frozenset[str]] = frozenset(
    {
        "dataseta_igfbp3_x_z.csv",
        "datasetc.fastq",
        "datasetd.fastq",
        "aptadiff_repo_readme.rtf",
    }
)


@dataclass(frozen=True)
class AptaDiffSourceProfile:
    """Fixed source-level identity for one AptaDiff P6 table."""

    source_key: str
    dataset_label: str
    documented_target: str
    target_provenance: str
    expected_input_rows: int
    expected_n_containing: int
    expected_acgt_only: int
    expected_unique_sequences: int
    expected_length_36: int
    expected_p6_min: str
    expected_p6_median: str
    expected_p6_max: str
    expected_first_native_id: str
    expected_last_native_id: str
    required_basename: str


SOURCE_PROFILES: Final[dict[str, AptaDiffSourceProfile]] = {
    "aptadiff_a": AptaDiffSourceProfile(
        source_key="aptadiff_a",
        dataset_label="A",
        documented_target="IGFBP3",
        target_provenance=(
            "AptaDiff Dataset A filename datasetA_IGFBP3_P6.csv; "
            "AptaDiff paper/repository documentation; "
            "DDBJ/DRA accession DRA009383"
        ),
        expected_input_rows=13803,
        expected_n_containing=1,
        expected_acgt_only=13802,
        expected_unique_sequences=13803,
        expected_length_36=13803,
        expected_p6_min="5",
        expected_p6_median="9",
        expected_p6_max="194981",
        expected_first_native_id="00001",
        expected_last_native_id="13803",
        required_basename="datasetA_IGFBP3_P6.csv",
    ),
    "aptadiff_b": AptaDiffSourceProfile(
        source_key="aptadiff_b",
        dataset_label="B",
        documented_target="PTK7",
        target_provenance=(
            "AptaDiff Dataset B filename datasetB_PTK7_P6.csv; "
            "AptaDiff paper/repository documentation; "
            "DDBJ/DRA accession DRA009384"
        ),
        expected_input_rows=11547,
        expected_n_containing=15,
        expected_acgt_only=11532,
        expected_unique_sequences=11547,
        expected_length_36=11547,
        expected_p6_min="2",
        expected_p6_median="4",
        expected_p6_max="36136",
        expected_first_native_id="00001",
        expected_last_native_id="11547",
        required_basename="datasetB_PTK7_P6.csv",
    ),
}


class AptaDiffAdapterError(ValueError):
    """Hard failure while validating or extracting an AptaDiff P6 source."""


@dataclass
class AptaDiffExtractionStats:
    """Aggregate counts for one AptaDiff S1 report (no sequence values)."""

    source_key: str = ""
    dataset_label: str = ""
    documented_target: str = ""
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
    unique_sequences: int = 0
    duplicate_sequence_groups: int = 0
    rows_in_duplicate_sequence_groups: int = 0
    n_containing: int = 0
    acgt_only: int = 0
    length_36: int = 0
    other_lengths: int = 0
    p6_min: str = ""
    p6_median: str = ""
    p6_max: str = ""
    p6_all_integer: bool = False
    first_native_id: str = ""
    last_native_id: str = ""
    sequence_exact_copy_ok: bool = False
    p6_exact_copy_ok: bool = False
    order_preserved: bool = False
    no_row_consolidation: bool = True
    native_id_strategy: str = (
        "1-based CSV data-row number, zero-padded to 5 digits "
        "(source has no native record ID; sequence is not used as native_id)"
    )


@dataclass
class AptaDiffExtractionResult:
    """Canonical rows, sidecar rows, and aggregate extraction statistics."""

    canonical_rows: list[dict[str, str]]
    sidecar_rows: list[dict[str, str]]
    stats: AptaDiffExtractionStats = field(default_factory=AptaDiffExtractionStats)


def profile_for_source(source_key: str) -> AptaDiffSourceProfile:
    """Return the frozen A/B profile; reject unknown or combined keys."""
    try:
        return SOURCE_PROFILES[source_key]
    except KeyError as exc:
        raise AptaDiffAdapterError(
            f"Unknown AptaDiff source_key={source_key!r}; expected "
            "aptadiff_a or aptadiff_b"
        ) from exc


def required_basename_for_source(source_key: str) -> str:
    """Return the only authorised P6 basename for ``source_key``."""
    return profile_for_source(source_key).required_basename


def format_native_id(csv_data_row: int, *, width: int = NATIVE_ID_WIDTH) -> str:
    """Format a 1-based CSV data-row number as the AptaDiff native_id."""
    if csv_data_row < 1:
        raise AptaDiffAdapterError(
            f"csv_data_row must be a positive 1-based row number; got {csv_data_row}"
        )
    return f"{csv_data_row:0{width}d}"


def _contains_n(sequence: str) -> bool:
    """Diagnostic only: whether the verbatim sequence contains N/n."""
    return "N" in sequence or "n" in sequence


def _is_acgt_only(sequence: str) -> bool:
    """Diagnostic only: nonempty verbatim A/C/G/T with no other characters."""
    return sequence != "" and all(ch in "ACGT" for ch in sequence)


def _integer_min_median_max(values: Sequence[str]) -> tuple[str, str, str] | None:
    """Return min/median/max strings when every token is a base-10 integer."""
    parsed: list[int] = []
    for value in values:
        try:
            parsed.append(int(value))
        except ValueError:
            return None
    if not parsed:
        return None
    ordered = sorted(parsed)
    med = median(parsed)
    if isinstance(med, float) and med.is_integer():
        med_str = str(int(med))
    else:
        med_str = str(med)
    return str(ordered[0]), med_str, str(ordered[-1])


def validate_aptadiff_header(fieldnames: Sequence[str] | None) -> None:
    """Hard-fail on missing, extra, reordered, duplicate, or blank headers."""
    if fieldnames is None:
        raise AptaDiffAdapterError("AptaDiff input has no header row")

    actual = list(fieldnames)
    if any(not name.strip() for name in actual):
        raise AptaDiffAdapterError("AptaDiff input has a blank header column")
    if len(actual) != len(set(actual)):
        raise AptaDiffAdapterError("AptaDiff input has duplicate header columns")
    expected = list(APTADIFF_INPUT_COLUMNS)
    if actual != expected:
        if set(actual) != set(expected):
            missing = [c for c in expected if c not in actual]
            extra = [c for c in actual if c not in expected]
            parts: list[str] = []
            if missing:
                parts.append(f"missing={missing}")
            if extra:
                parts.append(f"extra={extra}")
            raise AptaDiffAdapterError(
                "AptaDiff input columns do not match the required seq,p6 schema; "
                + "; ".join(parts)
            )
        raise AptaDiffAdapterError(
            "AptaDiff input columns are reordered relative to the required schema"
        )


def _coerce_source_row(row: Mapping[str, str | None], index: int) -> dict[str, str]:
    """Return a source row with every expected column present as a string."""
    coerced: dict[str, str] = {}
    for column in APTADIFF_INPUT_COLUMNS:
        value = row.get(column)
        if value is None:
            raise AptaDiffAdapterError(
                f"AptaDiff row {index} missing column {column!r}"
            )
        coerced[column] = value
    return coerced


def read_aptadiff_rows(path: Path) -> list[dict[str, str]]:
    """Read a schema-validated AptaDiff ``seq,p6`` CSV.

    Uses ``encoding=utf-8-sig`` and ``newline=''``. Does not use pandas.
    Does not uppercase, strip, convert T→U, or interpret ``p6``.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_aptadiff_header(reader.fieldnames)
        raw_rows = list(reader)

    coerced: list[dict[str, str]] = []
    for index, row in enumerate(raw_rows, start=2):
        coerced.append(_coerce_source_row(row, index))
    return coerced


def map_aptadiff_row(
    source_row: Mapping[str, str],
    *,
    csv_data_row: int,
    source_key: str,
    source_dataset: str,
    redistribution_status: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Map one physical source row to canonical + sidecar records.

    ``csv_data_row`` is the 1-based data-row number in source order.
    Source ``seq`` is never used as ``native_id``. Documented A/B targets
    are sidecar-only; ``target_name_raw`` remains empty. Source ``p6`` is
    preserved verbatim and is not mapped to affinity or evidence.
    """
    profile = profile_for_source(source_key)
    native_id = format_native_id(csv_data_row)
    canonical_id = f"{source_key}:{native_id}"
    sequence_raw = source_row["seq"]

    record = empty_corpus_record()
    record["record_id"] = canonical_id
    record["sequence_raw"] = sequence_raw
    record["source_db"] = source_key
    record["source_dataset"] = source_dataset
    record["contributing_sources"] = source_key
    record["contributing_datasets"] = source_dataset
    record["corroboration_count"] = "1"
    record["redistribution_status"] = redistribution_status
    record["independently_attested_by_permissive_source"] = "false"
    record["native_id"] = native_id
    record["target_name_raw"] = ""
    record["publication"] = ""
    record["doi"] = ""
    record["pubmed_id"] = ""
    record["notes"] = ""

    validated = validate_s1_record(record)

    sidecar: dict[str, str] = {
        "record_id": canonical_id,
        "native_id": native_id,
        "aptadiff_csv_data_row": str(csv_data_row),
        "aptadiff_seq": source_row["seq"],
        "aptadiff_p6": source_row["p6"],
        "aptadiff_dataset": profile.dataset_label,
        "aptadiff_source_key": source_key,
        "aptadiff_documented_target": profile.documented_target,
        "aptadiff_target_provenance": profile.target_provenance,
    }
    return validated, sidecar


def extract_aptadiff(
    input_path: Path,
    *,
    source_key: str,
    source_dataset: str,
    redistribution_status: str,
    expected_rows: int | None,
) -> AptaDiffExtractionResult:
    """Extract every physical AptaDiff P6 row into canonical and sidecar tables.

    ``expected_rows`` is the registry ``n_rows_expected`` for this input.
    When it equals the frozen production snapshot size for ``source_key``,
    known production audit counts are also enforced. Pass
    ``expected_rows=None`` only in unit tests that skip that gate.
    """
    profile = profile_for_source(source_key)
    source_rows = read_aptadiff_rows(input_path)
    if expected_rows is not None and len(source_rows) != expected_rows:
        raise AptaDiffAdapterError(
            f"{source_key} input row count must be {expected_rows}; "
            f"got {len(source_rows)}"
        )

    canonical_rows: list[dict[str, str]] = []
    sidecar_rows: list[dict[str, str]] = []
    stats = AptaDiffExtractionStats(
        source_key=source_key,
        dataset_label=profile.dataset_label,
        documented_target=profile.documented_target,
    )
    stats.input_rows = len(source_rows)
    stats.order_preserved = True
    stats.no_row_consolidation = True
    sequence_exact = True
    p6_exact = True

    native_ids: list[str] = []
    record_ids: list[str] = []
    sequences: list[str] = []
    p6_values: list[str] = []

    for csv_data_row, source_row in enumerate(source_rows, start=1):
        canonical, sidecar = map_aptadiff_row(
            source_row,
            csv_data_row=csv_data_row,
            source_key=source_key,
            source_dataset=source_dataset,
            redistribution_status=redistribution_status,
        )
        if canonical["sequence_raw"] != source_row["seq"]:
            sequence_exact = False
        if sidecar["aptadiff_seq"] != source_row["seq"]:
            sequence_exact = False
        if canonical["sequence_raw"] != sidecar["aptadiff_seq"]:
            sequence_exact = False
        if sidecar["aptadiff_p6"] != source_row["p6"]:
            p6_exact = False
        if canonical["target_name_raw"] != "":
            raise AptaDiffAdapterError(
                "S1 must not populate target_name_raw from AptaDiff source identity"
            )

        sequence_raw = canonical["sequence_raw"]
        if sequence_raw == "":
            stats.missing_sequences += 1
        else:
            stats.nonempty_sequences += 1
        if _contains_n(sequence_raw):
            stats.n_containing += 1
        if _is_acgt_only(sequence_raw):
            stats.acgt_only += 1
        if len(sequence_raw) == 36:
            stats.length_36 += 1
        else:
            stats.other_lengths += 1

        stats.empty_target_name_raw += 1
        if canonical["publication"] != "":
            stats.nonempty_publication += 1
        if canonical["doi"] != "":
            stats.nonempty_doi += 1
        if canonical["pubmed_id"] != "":
            stats.nonempty_pmid += 1

        native_ids.append(canonical["native_id"])
        record_ids.append(canonical["record_id"])
        sequences.append(source_row["seq"])
        p6_values.append(source_row["p6"])
        canonical_rows.append(canonical)
        sidecar_rows.append(sidecar)

    sequence_counts = Counter(sequences)
    duplicate_groups = {seq: n for seq, n in sequence_counts.items() if n > 1}
    p6_summary = _integer_min_median_max(p6_values)

    stats.canonical_rows = len(canonical_rows)
    stats.sidecar_rows = len(sidecar_rows)
    stats.unique_native_ids = len(set(native_ids))
    stats.unique_record_ids = len(set(record_ids))
    stats.unique_sequences = len(sequence_counts)
    stats.duplicate_sequence_groups = len(duplicate_groups)
    stats.rows_in_duplicate_sequence_groups = sum(duplicate_groups.values())
    stats.first_native_id = native_ids[0] if native_ids else ""
    stats.last_native_id = native_ids[-1] if native_ids else ""
    stats.sequence_exact_copy_ok = sequence_exact
    stats.p6_exact_copy_ok = p6_exact
    if p6_summary is not None:
        stats.p6_all_integer = True
        stats.p6_min, stats.p6_median, stats.p6_max = p6_summary

    _assert_extraction_invariants(
        stats,
        profile=profile,
        expected_rows=expected_rows,
    )

    return AptaDiffExtractionResult(
        canonical_rows=canonical_rows,
        sidecar_rows=sidecar_rows,
        stats=stats,
    )


def _assert_extraction_invariants(
    stats: AptaDiffExtractionStats,
    *,
    profile: AptaDiffSourceProfile,
    expected_rows: int | None,
) -> None:
    """Hard-fail unless S1 retention and identity invariants hold."""
    n = stats.input_rows
    if expected_rows is not None and n != expected_rows:
        raise AptaDiffAdapterError(
            f"input_rows must be {expected_rows}; got {n}"
        )
    if stats.canonical_rows != n:
        raise AptaDiffAdapterError(
            f"canonical_rows ({stats.canonical_rows}) != input_rows ({n})"
        )
    if stats.sidecar_rows != n:
        raise AptaDiffAdapterError(
            f"sidecar_rows ({stats.sidecar_rows}) != input_rows ({n})"
        )
    if stats.unique_native_ids != n:
        raise AptaDiffAdapterError(
            f"unique_native_ids ({stats.unique_native_ids}) != input_rows ({n})"
        )
    if stats.unique_record_ids != n:
        raise AptaDiffAdapterError(
            f"unique_record_ids ({stats.unique_record_ids}) != input_rows ({n})"
        )
    if not stats.sequence_exact_copy_ok:
        raise AptaDiffAdapterError("sequence_raw exact-copy validation failed")
    if not stats.p6_exact_copy_ok:
        raise AptaDiffAdapterError("sidecar p6 exact-copy validation failed")
    if not stats.order_preserved:
        raise AptaDiffAdapterError("input order was not preserved")
    if not stats.no_row_consolidation:
        raise AptaDiffAdapterError("S1 must not consolidate AptaDiff rows")
    if stats.nonempty_target_name_raw != 0:
        raise AptaDiffAdapterError(
            "S1 must not populate target_name_raw for AptaDiff; "
            f"got {stats.nonempty_target_name_raw} nonempty values"
        )
    if stats.empty_target_name_raw != n:
        raise AptaDiffAdapterError(
            "every AptaDiff S1 row must have empty target_name_raw"
        )
    if stats.nonempty_publication != 0:
        raise AptaDiffAdapterError(
            "S1 must not populate publication for AptaDiff; "
            f"got {stats.nonempty_publication} nonempty values"
        )
    if stats.nonempty_doi != 0:
        raise AptaDiffAdapterError(
            "S1 must not invent doi values for AptaDiff; "
            f"got {stats.nonempty_doi} nonempty values"
        )
    if stats.nonempty_pmid != 0:
        raise AptaDiffAdapterError(
            "S1 must not invent pubmed_id values for AptaDiff; "
            f"got {stats.nonempty_pmid} nonempty values"
        )
    if stats.missing_sequences + stats.nonempty_sequences != n:
        raise AptaDiffAdapterError(
            "missing plus nonempty sequence counts must sum to input_rows"
        )

    if expected_rows == profile.expected_input_rows:
        if stats.nonempty_sequences != profile.expected_input_rows:
            raise AptaDiffAdapterError(
                f"nonempty sequence_raw must be {profile.expected_input_rows}; "
                f"got {stats.nonempty_sequences}"
            )
        if stats.missing_sequences != 0:
            raise AptaDiffAdapterError(
                f"missing sequence_raw must be 0; got {stats.missing_sequences}"
            )
        if stats.n_containing != profile.expected_n_containing:
            raise AptaDiffAdapterError(
                "N-containing sequences must be "
                f"{profile.expected_n_containing}; got {stats.n_containing}"
            )
        if stats.acgt_only != profile.expected_acgt_only:
            raise AptaDiffAdapterError(
                f"A/C/G/T-only sequences must be {profile.expected_acgt_only}; "
                f"got {stats.acgt_only}"
            )
        if stats.unique_sequences != profile.expected_unique_sequences:
            raise AptaDiffAdapterError(
                "unique sequences must be "
                f"{profile.expected_unique_sequences}; got {stats.unique_sequences}"
            )
        if stats.duplicate_sequence_groups != 0:
            raise AptaDiffAdapterError(
                "production AptaDiff P6 tables have no duplicate sequences; "
                f"got {stats.duplicate_sequence_groups} duplicate groups"
            )
        if stats.length_36 != profile.expected_length_36:
            raise AptaDiffAdapterError(
                f"length-36 sequences must be {profile.expected_length_36}; "
                f"got {stats.length_36}"
            )
        if stats.other_lengths != 0:
            raise AptaDiffAdapterError(
                f"non-36-nt sequences must be 0; got {stats.other_lengths}"
            )
        if not stats.p6_all_integer:
            raise AptaDiffAdapterError(
                "production AptaDiff p6 values must all be integer tokens"
            )
        if stats.p6_min != profile.expected_p6_min:
            raise AptaDiffAdapterError(
                f"p6 min must be {profile.expected_p6_min!r}; got {stats.p6_min!r}"
            )
        if stats.p6_median != profile.expected_p6_median:
            raise AptaDiffAdapterError(
                f"p6 median must be {profile.expected_p6_median!r}; "
                f"got {stats.p6_median!r}"
            )
        if stats.p6_max != profile.expected_p6_max:
            raise AptaDiffAdapterError(
                f"p6 max must be {profile.expected_p6_max!r}; got {stats.p6_max!r}"
            )
        if stats.first_native_id != profile.expected_first_native_id:
            raise AptaDiffAdapterError(
                f"first native_id must be {profile.expected_first_native_id!r}; "
                f"got {stats.first_native_id!r}"
            )
        if stats.last_native_id != profile.expected_last_native_id:
            raise AptaDiffAdapterError(
                f"last native_id must be {profile.expected_last_native_id!r}; "
                f"got {stats.last_native_id!r}"
            )


def extract_aptadiff_a(
    input_path: Path,
    *,
    source_dataset: str,
    redistribution_status: str,
    expected_rows: int | None = SOURCE_PROFILES["aptadiff_a"].expected_input_rows,
) -> AptaDiffExtractionResult:
    """S1 extraction wrapper for ``source_key=aptadiff_a``."""
    return extract_aptadiff(
        input_path,
        source_key="aptadiff_a",
        source_dataset=source_dataset,
        redistribution_status=redistribution_status,
        expected_rows=expected_rows,
    )


def extract_aptadiff_b(
    input_path: Path,
    *,
    source_dataset: str,
    redistribution_status: str,
    expected_rows: int | None = SOURCE_PROFILES["aptadiff_b"].expected_input_rows,
) -> AptaDiffExtractionResult:
    """S1 extraction wrapper for ``source_key=aptadiff_b``."""
    return extract_aptadiff(
        input_path,
        source_key="aptadiff_b",
        source_dataset=source_dataset,
        redistribution_status=redistribution_status,
        expected_rows=expected_rows,
    )


def write_sidecar_csv_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Atomically write one AptaDiff source-metadata sidecar."""
    write_corpus_csv_atomic(path, rows, columns=SIDECAR_COLUMNS)

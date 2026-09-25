#!/usr/bin/env python3
"""S2: sequence normalisation and QC for a registered extracted source.

Consumes S1 canonical CSV plus the source-metadata sidecar. Applies the shared
sequence-normalisation contract and a source-specific molecule-evidence policy.
Does not filter, accept, reject or park records. Does not create CHECKPOINT-1.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptabase_s2 import (  # noqa: E402
    CONSTANT_PROPOSAL_COLUMNS,
    S2_QC_COLUMNS,
    AptaBaseS2Error,
    AptaBaseS2Stats,
    CORRECTION_CONFIG_REL,
    assert_no_legacy_cleaner_import,
    corrections_for_records,
    is_review_candidate,
    load_aptabase_policy,
    normalise_aptabase_record,
    update_stats_from_row,
)
from adapters.aptadiff_s2 import (  # noqa: E402
    CONSTANT_INFERENCE_DISABLED_REASON,
    CONSTANT_PROPOSAL_COLUMNS as APTADIFF_CONSTANT_PROPOSAL_COLUMNS,
    CONSTRUCT_SCOPE_RANDOM_REGION_ONLY,
    S2_QC_COLUMNS as APTADIFF_S2_QC_COLUMNS,
    AptaDiffS2Error,
    AptaDiffS2Stats,
    empty_constant_proposals,
    expected_documented_target as aptadiff_expected_documented_target,
    is_review_candidate as aptadiff_is_review_candidate,
    load_aptadiff_policy,
    normalise_aptadiff_record,
    s4_fields_are_empty as aptadiff_s4_fields_are_empty,
    summarise_lengths as summarise_aptadiff_lengths,
    update_stats_from_row as update_aptadiff_stats_from_row,
)
from adapters.aptamerbase_rdf import (  # noqa: E402
    AptamerBaseRdfError,
    load_aptamerbase_rdf_index,
    require_subject_facts,
)
from adapters.aptamerbase_s2 import (  # noqa: E402
    CONSTANT_PROPOSAL_COLUMNS as APTAMERBASE_CONSTANT_PROPOSAL_COLUMNS,
    S2_QC_COLUMNS as APTAMERBASE_S2_QC_COLUMNS,
    AptamerBaseS2Error,
    AptamerBaseS2Stats,
    assert_genuine_proposals as assert_aptamerbase_genuine_proposals,
    build_known_motif_proposals as build_aptamerbase_known_motif_proposals,
    finalise_review_and_id_stats as finalise_aptamerbase_review_and_id_stats,
    is_review_candidate as aptamerbase_is_review_candidate,
    load_aptamerbase_policy,
    normalise_aptamerbase_record,
    s4_fields_are_empty as aptamerbase_s4_fields_are_empty,
    summarise_lengths as summarise_aptamerbase_lengths,
    update_stats_from_row as update_aptamerbase_stats_from_row,
)
from adapters.aptaindex_s2 import (  # noqa: E402
    CONSTANT_PROPOSAL_COLUMNS as APTAINDEX_CONSTANT_PROPOSAL_COLUMNS,
    S2_QC_COLUMNS as APTAINDEX_S2_QC_COLUMNS,
    AptaIndexS2Error,
    AptaIndexS2Stats,
    assert_genuine_proposals as assert_aptaindex_genuine_proposals,
    build_known_motif_proposals as build_aptaindex_known_motif_proposals,
    is_review_candidate as aptaindex_is_review_candidate,
    load_aptaindex_policy,
    normalise_aptaindex_record,
    summarise_lengths as summarise_aptaindex_lengths,
    update_stats_from_row as update_aptaindex_stats_from_row,
)
from adapters.aptadb_s2 import (  # noqa: E402
    CONSTANT_PROPOSAL_COLUMNS as APTADB_CONSTANT_PROPOSAL_COLUMNS,
    S2_QC_COLUMNS as APTADB_S2_QC_COLUMNS,
    AptaDBS2Error,
    AptaDBS2Stats,
    assert_genuine_proposals as assert_aptadb_genuine_proposals,
    build_group_proposal_rows as build_aptadb_group_proposal_rows,
    build_known_motif_proposals as build_aptadb_known_motif_proposals,
    is_review_candidate as aptadb_is_review_candidate,
    load_aptadb_policy,
    normalise_aptadb_record,
    summarise_lengths as summarise_aptadb_lengths,
    update_stats_from_row as update_aptadb_stats_from_row,
)
from adapters.ena_s2 import (  # noqa: E402
    CONSTANT_PROPOSAL_COLUMNS as ENA_CONSTANT_PROPOSAL_COLUMNS,
    MEMBERSHIP_COLUMNS as ENA_MEMBERSHIP_COLUMNS,
    S2_QC_COLUMNS as ENA_S2_QC_COLUMNS,
    EnaS2Error,
    EnaS2Stats,
    annotate_group_consensus_on_qc,
    assert_genuine_proposals as assert_ena_genuine_proposals,
    assert_no_legacy_ena_normaliser_import,
    build_group_proposal_rows as build_ena_group_proposal_rows,
    build_known_motif_proposals as build_ena_known_motif_proposals,
    build_membership_rows as build_ena_membership_rows,
    finalise_review_and_duplicate_stats,
    group_size_bucket,
    is_review_candidate as ena_is_review_candidate,
    load_ena_policy,
    normalise_ena_record,
    split_supporting_group_ids,
    summarise_lengths as summarise_ena_lengths,
    update_stats_from_row as update_ena_stats_from_row,
)
from adapters.ncbi_nuc_s2 import (  # noqa: E402
    CONSTANT_PROPOSAL_COLUMNS as NCBI_NUC_CONSTANT_PROPOSAL_COLUMNS,
    S2_QC_COLUMNS as NCBI_NUC_S2_QC_COLUMNS,
    NcbiNucS2Error,
    NcbiNucS2Stats,
    assert_genuine_proposals as assert_ncbi_nuc_genuine_proposals,
    build_known_motif_proposals as build_ncbi_nuc_known_motif_proposals,
    finalise_review_stats as finalise_ncbi_nuc_review_stats,
    is_review_candidate as ncbi_nuc_is_review_candidate,
    load_ncbi_nuc_policy,
    normalise_ncbi_nuc_record,
    summarise_lengths as summarise_ncbi_nuc_lengths,
    update_stats_from_row as update_ncbi_nuc_stats_from_row,
)
from adapters.riboaptamer_s2 import (  # noqa: E402
    CONSTANT_PROPOSAL_COLUMNS as RIBOAPTAMER_CONSTANT_PROPOSAL_COLUMNS,
    S2_QC_COLUMNS as RIBOAPTAMER_S2_QC_COLUMNS,
    RiboAptamerS2Error,
    RiboAptamerS2Stats,
    assert_genuine_proposals as assert_riboaptamer_genuine_proposals,
    assert_truncation_regressions as assert_riboaptamer_truncation_regressions,
    build_known_motif_proposals as build_riboaptamer_known_motif_proposals,
    finalise_truncation_regressions as finalise_riboaptamer_truncation_regressions,
    is_review_candidate as riboaptamer_is_review_candidate,
    load_riboaptamer_policy,
    normalise_riboaptamer_record,
    summarise_lengths as summarise_riboaptamer_lengths,
    update_stats_from_row as update_riboaptamer_stats_from_row,
)
from adapters.utexas_s2 import (  # noqa: E402
    CONSTANT_PROPOSAL_COLUMNS as UTEXAS_CONSTANT_PROPOSAL_COLUMNS,
    S2_QC_COLUMNS as UTEXAS_S2_QC_COLUMNS,
    UTexasS2Error,
    UTexasS2Stats,
    assert_genuine_proposals,
    build_known_motif_proposals,
    build_pool_type_proposals,
    is_review_candidate as utexas_is_review_candidate,
    load_utexas_policy,
    normalise_utexas_record,
    update_stats_from_row as update_utexas_stats_from_row,
)
from adapters.utexas_constant_region_review import (  # noqa: E402
    EXPECTED_APPROVE,
    EXPECTED_CANDIDATE_RULES,
    EXPECTED_NEEDS_SOURCE_REVIEW,
    build_constant_region_review_package,
    load_tracked_constant_region_decisions,
    write_review_package_files,
    write_tracked_review_artefacts,
)
from adapters.utexas_approved_trims import (  # noqa: E402
    AMBIGUITY_COLUMNS,
    TRIM_AUDIT_COLUMNS,
    apply_approved_trims_to_rows,
    load_approved_trim_rules,
)
from adapters.utexas_alphabet_exceptions import (  # noqa: E402
    RECOVERY_AUDIT_COLUMNS,
    AlphabetExceptionError,
    approved_recovery_ids,
    load_alphabet_exception_resolutions,
)
from common.constant_region_inference import (  # noqa: E402
    build_group_inference_key,
    infer_group_constant_regions,
    infer_group_constant_regions_with_diagnostics,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    CorpusSchemaError,
    validate_column_order,
    write_corpus_csv_atomic,
)
from common.sequence_normalisation import (  # noqa: E402
    load_normalisation_rules,
)
from s0_build_registry import find_repo_root  # noqa: E402

EXPECTED_APTABASE_ROWS = 610
EXPECTED_APTABASE_MISSING = 54
EXPECTED_APTABASE_NONEMPTY = 556

EXPECTED_UTEXAS_ROWS = 1894
EXPECTED_UTEXAS_MISSING = 399
EXPECTED_UTEXAS_NONEMPTY = 1495
EXPECTED_UTEXAS_MOLECULE = {"RNA": 583, "ssDNA": 896, "DNA": 13, "unknown": 402}
EXPECTED_UTEXAS_CHEMISTRY = {
    "RNA": 438,
    "DNA": 897,
    "2F-RNA": 108,
    "2NH2-RNA": 23,
    "2OMe-RNA": 6,
    "mixed": 5,
    "unknown": 417,
}
EXPECTED_RAW_SHA256 = (
    "b5a66beb58d30c5c3d2f36a29ea2cc3678e7d4a6b1bb1a97efc1e166a49fd15c"
)

EXPECTED_APTADB_ROWS = 1350
EXPECTED_APTADB_MOLECULE = {"RNA": 289, "ssDNA": 1061}
EXPECTED_APTADB_CHEMISTRY = {"RNA": 289, "DNA": 1061}
EXPECTED_APTADB_RAW_SHA256 = {
    "interaction.csv": (
        "6dbd97f20fa6f98d359d697713c43032d5a6a3c1a400d80ef28a150d676dff86"
    ),
    "aptamer.csv": (
        "9d3ab029d1de4408d2406051a68bc0e6da347ee1be1838aee9c938ca3f3fb464"
    ),
    "protein.csv": (
        "4de0d8b105b3318c9704ff64819089f5e17b5c735f0730724052f3e808325f79"
    ),
}

EXPECTED_RIBOAPTAMER_ROWS = 509
EXPECTED_RIBOAPTAMER_MOLECULE = {"RNA": 509}
EXPECTED_RIBOAPTAMER_CHEMISTRY = {"RNA": 509}
EXPECTED_RIBOAPTAMER_RAW_SHA256 = (
    "721d8c5ea81476c1f371ef8bfa814743f364eaf004c0a6eda2aabd6dc5d9a9fd"
)
EXPECTED_RIBOAPTAMER_SOURCE_DATASET = "riboaptamer_full_2026-08"

EXPECTED_APTAINDEX_ROWS = 1050
EXPECTED_APTAINDEX_SOURCE_DATASET = "aptaindex_export_2026-07-22"
EXPECTED_APTAINDEX_RAW_SHA256 = (
    "912b8e554fa2bb2ed3a9e9bdf1cfbe4f757d8c7a00c401629e5bcb5e5c2877a8"
)

EXPECTED_ENA_ROWS = 679
EXPECTED_ENA_MOLECULE = {"RNA": 679}
EXPECTED_ENA_CHEMISTRY = {"RNA": 679}
EXPECTED_ENA_ALPHABET = {"RNA": 674, "DNA_T": 5}
EXPECTED_ENA_T_TO_U = 5
EXPECTED_ENA_SOURCE_DATASET = "ena_selected_v2_2026-08"
EXPECTED_ENA_RAW_SHA256 = (
    "d1069b96c2bcf5eba02d7d7907b3bcc33e041bf80aac6345e7295715e45c5a35"
)
EXPECTED_ENA_PRIMARY_GROUPS = 25
EXPECTED_ENA_SEQUENCE_CORRECTIONS = 8

EXPECTED_APTAMERBASE_ROWS = 2128
EXPECTED_APTAMERBASE_UNIQUE_IDS = 1868
EXPECTED_APTAMERBASE_SOURCE_DATASET = "aptamerbase_export_2026-06-24"
EXPECTED_APTAMERBASE_RAW_CSV_SHA256 = (
    "40b329551b225a29ee2c656cf6b59b98ff686a981968b856685cdc7c222a784c"
)
EXPECTED_APTAMERBASE_RAW_RDF_SHA256 = (
    "3ab9340ee1fcb6a0910532a6e8d4cf5cc62579c3b21d85355c48d473e372006c"
)
EXPECTED_APTAMERBASE_RDF_STATEMENTS = 270507
EXPECTED_APTAMERBASE_S1_CANONICAL_SHA256 = (
    "0bb0282033ba0561b2c8d8de1358ae6e5a4e8fa47bfb640c56dc87b177552896"
)
EXPECTED_APTAMERBASE_S1_SIDECAR_SHA256 = (
    "47a49f7495648bb11105a77eee9cbcfeabeb7b7b05f357dc433d3edb779f41b7"
)

EXPECTED_APTADIFF_A_ROWS = 13803
EXPECTED_APTADIFF_B_ROWS = 11547
EXPECTED_APTADIFF_A_SOURCE_DATASET = "aptadiff_a_igfbp3_p6_2026-06-22"
EXPECTED_APTADIFF_B_SOURCE_DATASET = "aptadiff_b_ptk7_p6_2026-06-22"
EXPECTED_APTADIFF_A_RAW_SHA256 = (
    "ec970c478aaba1aa089ecbaf7f5bc8aa7a11f6eacd0f7b3d3c418de6a27e8c77"
)
EXPECTED_APTADIFF_B_RAW_SHA256 = (
    "546de810e34035731502caf6476c73cc06feab8156ec8178efaade2d21bf4d72"
)
EXPECTED_APTADIFF_A_RAW_PATH = "data/raw/Aptadiff_datasetA/datasetA_IGFBP3_P6.csv"
EXPECTED_APTADIFF_B_RAW_PATH = "data/raw/Aptadiff_otherdata/datasetB_PTK7_P6.csv"
EXPECTED_APTADIFF_A_MOLECULE = {"ssDNA": 13803}
EXPECTED_APTADIFF_B_MOLECULE = {"ssDNA": 11547}
EXPECTED_APTADIFF_A_CHEMISTRY = {"DNA": 13803}
EXPECTED_APTADIFF_B_CHEMISTRY = {"DNA": 11547}
EXPECTED_APTADIFF_A_ALPHABET = {"DNA_T": 13802, "ambiguous": 1}
EXPECTED_APTADIFF_B_ALPHABET = {"DNA_T": 11532, "ambiguous": 15}

EXPECTED_NCBI_NUC_ROWS = 18
EXPECTED_NCBI_NUC_MOLECULE = {"RNA": 5, "DNA": 1, "unknown": 12}
EXPECTED_NCBI_NUC_CHEMISTRY = {"RNA": 5, "DNA": 1, "unknown": 12}
EXPECTED_NCBI_NUC_T_TO_U = 5
EXPECTED_NCBI_NUC_SOURCE_DATASET = "ncbi_nuc_genbank_2026-07-27"
EXPECTED_NCBI_NUC_S1_CANONICAL_SHA256 = (
    "329f518e94e0813080545fe61d823ad44607ec8a193e14498fc62a91d647e9dc"
)
EXPECTED_NCBI_NUC_S1_SIDECAR_SHA256 = (
    "f1d003f64e7a9619d94b7025838e229b4ec7655fa93f9bda2bf34e2ba0021fe1"
)
EXPECTED_NCBI_NUC_RAW_SHA256: dict[str, str] = {
    "data/raw/NCBI_nucleotide/sequence (1).gb": (
        "0cfcbb085f86501c541bdf5eb5a3b7344d0554319db3f2e0a97509e28cb5c05a"
    ),
    "data/raw/NCBI_nucleotide/sequence (10).gb": (
        "d47bb0d8ab74f202ff3b4a336ac49abc8a0e29d9cde67b710896b0234acbab3f"
    ),
    "data/raw/NCBI_nucleotide/sequence (11).gb": (
        "950b13e83474ad066360bacd4a4d2ef1c7e8f4219259d50079a862c6771ce080"
    ),
    "data/raw/NCBI_nucleotide/sequence (12).gb": (
        "a27b6cddb546565055911873fce2fdde1bd29d064435d8badf2754af6fac055c"
    ),
    "data/raw/NCBI_nucleotide/sequence (13).gb": (
        "0b74ea872b31e09af5d10ef4ead998e1874c83e975c846b30e15e24d3bbed2fb"
    ),
    "data/raw/NCBI_nucleotide/sequence (14).gb": (
        "3490c7e66ba22df5f451ce0a05ec86cbee6a8cdef446ea9fa73eb15679b7f56c"
    ),
    "data/raw/NCBI_nucleotide/sequence (15).gb": (
        "a49fb40c880af0ea16662d9c88305264276ef5182a51bc40830d67416bc1ff5f"
    ),
    "data/raw/NCBI_nucleotide/sequence (16).gb": (
        "d2275cbd2e1134ad7de5f9e687297179d936059470e8357f1dce446a33571db2"
    ),
    "data/raw/NCBI_nucleotide/sequence (17).gb": (
        "78289052d3d0cc769bd2318af269f0ab6e4652cea7b4fd068733aa9456cf1ec4"
    ),
    "data/raw/NCBI_nucleotide/sequence (2).gb": (
        "b34e78d3754b7f1147df984d3f796f8bdb9bfad288287d318fd49e6a20c83be8"
    ),
    "data/raw/NCBI_nucleotide/sequence (3).gb": (
        "7d58262d81ddfc4af5899cc78341794948ecac826513c339b8bb2de4dd137227"
    ),
    "data/raw/NCBI_nucleotide/sequence (4).gb": (
        "62431cd2b251c63b0ccf96b99ecdd2b814397be2b40d50722dabf77175778380"
    ),
    "data/raw/NCBI_nucleotide/sequence (5).gb": (
        "3cf2cf0193095d3b74ed07617c28fc55222ad7ccba8d31a5a602c1d892172228"
    ),
    "data/raw/NCBI_nucleotide/sequence (6).gb": (
        "3d4227ef665d9f4fe210b4999654e8bccbee38c6d4b2ed2a93ed194fbfdd8562"
    ),
    "data/raw/NCBI_nucleotide/sequence (7).gb": (
        "9114ec869c8401a54cc88219b2920bc8910275748c0d2bce2df06b33ea258647"
    ),
    "data/raw/NCBI_nucleotide/sequence (8).gb": (
        "22e417676d8fdff7ca6fbdc3f887d34eac3f19d3906d7100f1c9d0d600dd038f"
    ),
    "data/raw/NCBI_nucleotide/sequence (9).gb": (
        "2d866410f1ee6748b4256d34ffb6231b019ed2c3261fd46e42b68120ef1b158f"
    ),
    "data/raw/NCBI_nucleotide/sequence.gb": (
        "59f078113f4e3b2bdb6cd0c2cc14b76bf542c9b3042b34a71a47a2ef10c02ede"
    ),
}


class S2NormaliseError(ValueError):
    """Hard failure during S2 normalisation orchestration."""


@dataclass(frozen=True)
class S2RunResult:
    """Aggregate outcome of one S2 normalisation run."""

    source_key: str
    stats: (
        AptaBaseS2Stats
        | AptamerBaseS2Stats
        | AptaDiffS2Stats
        | UTexasS2Stats
        | AptaDBS2Stats
        | RiboAptamerS2Stats
        | AptaIndexS2Stats
        | EnaS2Stats
        | NcbiNucS2Stats
    )
    output_normalised: Path
    output_qc: Path
    output_review: Path
    output_proposals: Path
    output_report: Path
    s1_hash_before: str
    s1_hash_after: str
    sidecar_hash_before: str
    sidecar_hash_after: str
    inputs_unchanged: bool
    deterministic_rerun_ok: bool | None
    raw_sha256: str | None = None
    raw_sha_unchanged: bool | None = None
    output_rule_candidates: Path | None = None
    output_rule_membership: Path | None = None
    output_review_decisions: Path | None = None
    output_review_summary: Path | None = None
    output_trim_audit: Path | None = None
    output_trim_ambiguity: Path | None = None
    output_recovery_audit: Path | None = None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_output_dir_allowed(repo_root: Path, output_dir: Path) -> Path:
    resolved = output_dir if output_dir.is_absolute() else (repo_root / output_dir)
    resolved = resolved.resolve()
    interim_root = (repo_root / "data" / "interim").resolve()
    try:
        resolved.relative_to(interim_root)
    except ValueError as exc:
        raise S2NormaliseError(
            "S2 output directory must lie beneath data/interim/: "
            f"{output_dir}"
        ) from exc
    raw_root = (repo_root / "data" / "raw").resolve()
    try:
        resolved.relative_to(raw_root)
    except ValueError:
        pass
    else:
        raise S2NormaliseError(
            f"Refusing to write S2 outputs under data/raw/: {output_dir}"
        )
    return resolved


def _relative_display(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _write_text_atomic(path: Path, text: str) -> None:
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
            if not text.endswith("\n"):
                handle.write("\n")
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def write_csv_atomic(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[dict[str, str]],
) -> None:
    """Atomically write a CSV with Unix newlines and a trailing newline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(fieldnames),
                lineterminator="\n",
                extrasaction="raise",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({col: row.get(col, "") for col in fieldnames})
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def _read_corpus_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise S2NormaliseError(f"S1 canonical CSV has no header: {path.name}")
        validate_column_order(list(reader.fieldnames))
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        for column in CORPUS_COLUMNS:
            value = row.get(column)
            if value is None:
                raise S2NormaliseError(
                    f"S1 row {index} missing column {column!r}"
                )
            row[column] = value
    return rows


def _read_sidecar_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise S2NormaliseError(f"Source-metadata CSV has no header: {path.name}")
        if "record_id" not in reader.fieldnames:
            raise S2NormaliseError("Source-metadata CSV missing record_id")
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        if not row.get("record_id"):
            raise S2NormaliseError(f"Source-metadata row {index} has blank record_id")
        for key, value in list(row.items()):
            row[key] = "" if value is None else value
    return rows


def _match_sidecar_one_to_one(
    canonical_rows: Sequence[dict[str, str]],
    sidecar_rows: Sequence[dict[str, str]],
) -> list[dict[str, str]]:
    """Return sidecar rows aligned to canonical order; hard-fail on mismatch."""
    if len(canonical_rows) != len(sidecar_rows):
        raise S2NormaliseError(
            "S1 canonical and source-metadata row counts must match: "
            f"{len(canonical_rows)} vs {len(sidecar_rows)}"
        )

    by_id: dict[str, dict[str, str]] = {}
    for row in sidecar_rows:
        record_id = row["record_id"]
        if record_id in by_id:
            raise S2NormaliseError(
                f"Duplicate source-metadata record_id: {record_id!r}"
            )
        by_id[record_id] = row

    if len(by_id) != len(sidecar_rows):
        raise S2NormaliseError("Source-metadata record_id values are not unique")

    aligned: list[dict[str, str]] = []
    for canonical in canonical_rows:
        record_id = canonical["record_id"]
        if record_id not in by_id:
            raise S2NormaliseError(
                f"Missing source-metadata row for record_id={record_id!r}"
            )
        aligned.append(by_id[record_id])

    extra = set(by_id) - {row["record_id"] for row in canonical_rows}
    if extra:
        raise S2NormaliseError(
            f"Extra source-metadata record_id values not in canonical: {len(extra)}"
        )
    return aligned


def _count_sorted(mapping: dict[str, int]) -> list[tuple[str, int]]:
    return sorted(mapping.items(), key=lambda item: item[0])


def build_aptabase_s2_report(
    *,
    repo_root: Path,
    result: S2RunResult,
    rules_path: Path,
    policy_path: Path,
) -> str:
    """Build an aggregate-only Markdown S2 report (no sequences or IDs)."""
    stats = result.stats
    lines = [
        "# AptaBase S2 normalisation report",
        "",
        "## Inputs",
        "",
        f"- S1 canonical rows: `{stats.s1_rows}`",
        f"- Source-metadata rows: `{stats.source_metadata_rows}`",
        f"- Shared rules: `{_relative_display(rules_path, repo_root)}`",
        f"- Source policy: `{_relative_display(policy_path, repo_root)}`",
        "",
        "## Row retention",
        "",
        f"- S2 output rows: `{stats.s2_rows}`",
        f"- Unique record_id values: `{stats.unique_record_ids}`",
        f"- S1 row order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        f"- S1 provenance preserved: "
        f"`{'pass' if stats.provenance_preserved else 'fail'}`",
        f"- sequence_raw unchanged: "
        f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
        f"- Missing sequence rows: `{stats.missing_sequence_rows}`",
        f"- Nonempty sequence rows: `{stats.nonempty_sequence_rows}`",
        "",
        "## Display-cleaning transformations",
        "",
    ]
    if stats.transformation_counts:
        for name, count in _count_sorted(stats.transformation_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## Alphabet as reported",
            "",
        ]
    )
    for name, count in _count_sorted(stats.alphabet_counts):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(
        [
            "",
            "## Molecule type",
            "",
        ]
    )
    for name, count in _count_sorted(stats.molecule_type_counts):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(
        [
            "",
            "## Molecule evidence source",
            "",
        ]
    )
    for name, count in _count_sorted(stats.molecule_evidence_source_counts):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(
        [
            "",
            "## Sequence and trim QC",
            "",
            f"- T→U conversions: `{stats.t_to_u_count}`",
            f"- Invalid character rows: `{stats.invalid_character_count}`",
            f"- Ambiguous base rows: `{stats.ambiguous_base_count}`",
            f"- Mixed T/U rows: `{stats.mixed_t_u_count}`",
            f"- Known motif detections: `{stats.known_motif_detection_count}`",
            f"- Trim-review rows: `{stats.trim_review_count}`",
            f"- Core below minimum length: `{stats.core_below_min_count}`",
            f"- Core above maximum length: `{stats.core_above_max_count}`",
            "",
            "## Reported length and GC diagnostics",
            "",
            f"- Reported length unparseable: "
            f"`{stats.reported_length_unparseable_count}`",
            f"- Reported length mismatch: `{stats.reported_length_mismatch_count}`",
            f"- Reported GC unparseable: `{stats.reported_gc_unparseable_count}`",
            f"- Reported GC mismatch: `{stats.reported_gc_mismatch_count}`",
            "",
            "## QC flag summary",
            "",
            f"- Rows with any QC flag: `{stats.rows_with_any_qc_flag}`",
            f"- Rows with multiple QC flags: `{stats.rows_with_multiple_qc_flags}`",
            f"- Review-candidate rows: `{stats.review_candidate_rows}`",
            "",
            "## Legacy diagnostic disagreements",
            "",
            f"- Legacy sequence_clean disagreement: "
            f"`{stats.legacy_sequence_clean_disagreement_count}`",
            f"- Legacy length disagreement: "
            f"`{stats.legacy_length_disagreement_count}`",
            f"- Legacy alphabet disagreement: "
            f"`{stats.legacy_alphabet_disagreement_count}`",
            f"- Legacy molecule-type substantive disagreement: "
            f"`{stats.legacy_molecule_type_disagreement_count}`",
            f"- Legacy molecule-type semantic agreement: "
            f"`{stats.legacy_molecule_type_agreement_count}`",
            f"- Legacy molecule-type compatible difference: "
            f"`{stats.legacy_molecule_type_compatible_difference_count}`",
            f"- Legacy molecule-type unresolved comparison: "
            f"`{stats.legacy_molecule_type_unresolved_comparison_count}`",
            f"- Legacy molecule-type unrecognised: "
            f"`{stats.legacy_molecule_type_unrecognised_count}`",
            f"- Legacy molecule-type empty legacy: "
            f"`{stats.legacy_molecule_type_empty_legacy_count}`",
            f"- Legacy GC disagreement: `{stats.legacy_gc_disagreement_count}`",
            "",
            "## Constant-region inference boundary",
            "",
            f"- Records with experiment_group_id: "
            f"`{stats.records_with_experiment_group_id}`",
            f"- Eligible groups: `{stats.eligible_groups}`",
            f"- Constant-region proposals: `{stats.constant_region_proposals}`",
            f"- Reason: `{stats.constant_region_reason}`",
            "",
            "## Comparison with earlier AptaBase preprocessing",
            "",
            "- Prior audit reported 54 missing sequences; S2 retains the same "
            "missing-row count when inputs are unchanged.",
            "- Prior DNA/RNA alphabet tallies (290 DNA / 199 RNA / 63 invalid / "
            "3 mixed / 1 ambiguous) are not hard requirements. Differences are "
            "expected under the shared display-cleaning contract and when "
            "legacy `sequence_clean` is not used as input.",
            "- Prior molecule inference is diagnostic only; S2 uses conservative "
            "text-then-alphabet evidence and leaves T-only without explicit "
            "evidence as unknown.",
            "- Prior length and GC discrepancy tallies (65 length / 16 GC at "
            "1 pp) are compared in diagnostics only; S2 does not force agreement.",
            "- Prior T7 promoter detections (~17) used unconstrained substring",
            "  search. Shared motif detection requires the configured five_prime",
            "  position after display cleaning; most residual motif hits remain",
            "  at nonzero offsets because non-label prefixes precede the motif,",
            "  so leading five_prime detections stay rare even after AptaBase",
            "  corrupted-terminal cleanup.",
            "",
            "## Integrity",
            "",
            f"- S1 canonical hash before: `{result.s1_hash_before}`",
            f"- S1 canonical hash after: `{result.s1_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            f"- S1 inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            "",
            "## Outputs",
            "",
            f"- Normalised: "
            f"`{_relative_display(result.output_normalised, repo_root)}`",
            f"- QC: `{_relative_display(result.output_qc, repo_root)}`",
            f"- Review candidates: "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Constant-region proposals: "
            f"`{_relative_display(result.output_proposals, repo_root)}`",
            f"- Report: `{_relative_display(result.output_report, repo_root)}`",
            "",
            "## Stage boundary",
            "",
            "- S2 only: no S3 inclusion/parking/rejection rules were applied.",
            "- No CHECKPOINT-1 artefact was created.",
            "",
        ]
    )
    return "\n".join(lines)


def run_aptabase_s2(
    *,
    repo_root: Path,
    input_dir: Path,
    output_dir: Path,
    rules_path: Path,
    policy_path: Path,
    expected_rows: int | None = EXPECTED_APTABASE_ROWS,
    check_deterministic_rerun: bool = False,
) -> S2RunResult:
    """Execute AptaBase S2 normalisation."""
    assert_no_legacy_cleaner_import()
    repo_root = repo_root.resolve()
    input_dir = input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    input_dir = input_dir.resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    rules_path = (
        rules_path if rules_path.is_absolute() else (repo_root / rules_path)
    ).resolve()
    policy_path = (
        policy_path if policy_path.is_absolute() else (repo_root / policy_path)
    ).resolve()

    canonical_path = input_dir / "aptabase_extracted.csv"
    sidecar_path = input_dir / "aptabase_source_metadata.csv"
    if not canonical_path.is_file():
        raise S2NormaliseError(f"Missing S1 canonical input: {canonical_path.name}")
    if not sidecar_path.is_file():
        raise S2NormaliseError(f"Missing S1 sidecar input: {sidecar_path.name}")

    s1_hash_before = _sha256_file(canonical_path)
    sidecar_hash_before = _sha256_file(sidecar_path)

    rules = load_normalisation_rules(rules_path)
    policy = load_aptabase_policy(policy_path)

    canonical_rows = _read_corpus_csv(canonical_path)
    sidecar_rows = _read_sidecar_csv(sidecar_path)
    aligned_sidecar = _match_sidecar_one_to_one(canonical_rows, sidecar_rows)

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S2NormaliseError(
            f"S1 row count must be {expected_rows}; got {len(canonical_rows)}"
        )

    stats = AptaBaseS2Stats()
    stats.s1_rows = len(canonical_rows)
    stats.source_metadata_rows = len(aligned_sidecar)
    stats.order_preserved = True
    stats.provenance_preserved = True
    stats.sequence_raw_unchanged = True
    corrections = corrections_for_records(
        repo_root / CORRECTION_CONFIG_REL,
        repo_root=repo_root,
        record_ids=(row["record_id"] for row in canonical_rows),
    )

    normalised_rows: list[dict[str, str]] = []
    qc_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []

    for s1_row, meta_row in zip(canonical_rows, aligned_sidecar, strict=True):
        result = normalise_aptabase_record(
            s1_row,
            meta_row,
            policy=policy,
            rules=rules,
            corrections=corrections,
        )
        if result.canonical["record_id"] != s1_row["record_id"]:
            stats.order_preserved = False
            raise S2NormaliseError("S2 altered record_id or row identity")
        if result.canonical["sequence_raw"] != s1_row["sequence_raw"]:
            stats.sequence_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter sequence_raw")
        normalised_rows.append(result.canonical)
        qc_rows.append(result.qc)
        if is_review_candidate(result.canonical["qc_flags"]):
            review_rows.append(result.qc)
        update_stats_from_row(stats, result)

    stats.s2_rows = len(normalised_rows)
    stats.unique_record_ids = len({row["record_id"] for row in normalised_rows})

    if expected_rows == EXPECTED_APTABASE_ROWS:
        if stats.s2_rows != EXPECTED_APTABASE_ROWS:
            raise S2NormaliseError(
                f"S2 must preserve {EXPECTED_APTABASE_ROWS} rows; got {stats.s2_rows}"
            )
        if stats.unique_record_ids != EXPECTED_APTABASE_ROWS:
            raise S2NormaliseError("S2 record_id values are not unique")
        if stats.missing_sequence_rows != EXPECTED_APTABASE_MISSING:
            raise S2NormaliseError(
                "missing_sequence_rows must be "
                f"{EXPECTED_APTABASE_MISSING}; got {stats.missing_sequence_rows}"
            )
        if stats.nonempty_sequence_rows != EXPECTED_APTABASE_NONEMPTY:
            raise S2NormaliseError(
                "nonempty_sequence_rows must be "
                f"{EXPECTED_APTABASE_NONEMPTY}; got {stats.nonempty_sequence_rows}"
            )

    # Constant-region inference: AptaBase has no experiment_group_id values.
    inference_inputs = [
        {
            "record_id": row["record_id"],
            "experiment_group_id": row["experiment_group_id"],
            "sequence_full": row["sequence_full"] or None,
        }
        for row in normalised_rows
    ]
    stats.records_with_experiment_group_id = sum(
        1 for row in normalised_rows if row["experiment_group_id"]
    )
    proposals = infer_group_constant_regions(inference_inputs, rules=rules)
    stats.constant_region_proposals = len(proposals)
    stats.eligible_groups = 0
    stats.constant_region_reason = "no_experiment_group_id"
    if stats.records_with_experiment_group_id != 0:
        raise S2NormaliseError(
            "AptaBase S2 expected zero experiment_group_id values"
        )
    if stats.constant_region_proposals != 0:
        raise S2NormaliseError(
            "AptaBase S2 must not emit constant-region proposals without groups"
        )

    # Approved per-record corrections still keep sequence_full == sequence_core.
    # sequence_raw remains the original Aptabase construct string.
    for row in normalised_rows:
        if row["sequence_full"] == "" and row["sequence_core"] == "":
            continue
        if row["sequence_full"] != row["sequence_core"]:
            raise S2NormaliseError(
                "AptaBase S2 requires sequence_full == sequence_core "
                "(no approved trim)"
            )
        if row["construct_scope"] != "full_equals_core_untrimmed":
            raise S2NormaliseError("Unexpected construct_scope for nonempty sequence")

    output_dir.mkdir(parents=True, exist_ok=True)
    out_normalised = output_dir / "aptabase_normalised.csv"
    out_qc = output_dir / "aptabase_s2_qc.csv"
    out_review = output_dir / "aptabase_s2_review_candidates.csv"
    out_proposals = output_dir / "aptabase_constant_region_proposals.csv"
    out_report = output_dir / "aptabase_s2_report.md"

    write_corpus_csv_atomic(out_normalised, normalised_rows)
    write_csv_atomic(out_qc, S2_QC_COLUMNS, qc_rows)
    write_csv_atomic(out_review, S2_QC_COLUMNS, review_rows)
    write_csv_atomic(out_proposals, CONSTANT_PROPOSAL_COLUMNS, [])

    s1_hash_after = _sha256_file(canonical_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    inputs_unchanged = (
        s1_hash_before == s1_hash_after
        and sidecar_hash_before == sidecar_hash_after
    )
    if not inputs_unchanged:
        raise S2NormaliseError("S1 inputs were modified during S2 execution")

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "normalised": _sha256_file(out_normalised),
            "qc": _sha256_file(out_qc),
            "review": _sha256_file(out_review),
            "proposals": _sha256_file(out_proposals),
        }
        second = run_aptabase_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=policy_path,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["normalised"] == _sha256_file(second.output_normalised)
            and first_hashes["qc"] == _sha256_file(second.output_qc)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["proposals"] == _sha256_file(second.output_proposals)
        )
        if not deterministic_ok:
            raise S2NormaliseError(
                "S2 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S2RunResult(
        source_key="aptabase",
        stats=stats,
        output_normalised=out_normalised,
        output_qc=out_qc,
        output_review=out_review,
        output_proposals=out_proposals,
        output_report=out_report,
        s1_hash_before=s1_hash_before,
        s1_hash_after=s1_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
    )
    report_text = build_aptabase_s2_report(
        repo_root=repo_root,
        result=run_result,
        rules_path=rules_path,
        policy_path=policy_path,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in report_text:
        raise S2NormaliseError("S2 report must not contain absolute repository paths")
    _write_text_atomic(out_report, report_text)
    return run_result


def build_utexas_s2_report(
    *,
    repo_root: Path,
    result: S2RunResult,
    rules_path: Path,
    policy_path: Path,
    review_stats: dict | None = None,
    diagnostics=None,
) -> str:
    """Build an aggregate-only Markdown UTexas S2 report (no sequences or IDs)."""
    stats = result.stats
    if not isinstance(stats, UTexasS2Stats):
        raise S2NormaliseError("UTexas report requires UTexasS2Stats")
    lines = [
        "# UTexas S2 normalisation report",
        "",
        "## Input / reconciliation",
        "",
        f"- Source key: `utexas`",
        f"- Source dataset: `utexas_sept2023_2026-08`",
        f"- S1 canonical rows: `{stats.s1_rows}`",
        f"- Source-metadata rows: `{stats.source_metadata_rows}`",
        f"- S2 output rows: `{stats.s2_rows}`",
        f"- Unique record_id values: `{stats.unique_record_ids}`",
        f"- Unique native_id values: `{stats.unique_native_ids}`",
        f"- S1 row order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        f"- S1 provenance preserved: "
        f"`{'pass' if stats.provenance_preserved else 'fail'}`",
        f"- sequence_raw unchanged: "
        f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
        f"- Missing sequence rows: `{stats.missing_sequence_rows}`",
        f"- Nonempty sequence rows: `{stats.nonempty_sequence_rows}`",
        f"- Shared rules: `{_relative_display(rules_path, repo_root)}`",
        f"- Source policy: `{_relative_display(policy_path, repo_root)}`",
        "",
        "## Display cleaning",
        "",
    ]
    if stats.transformation_counts:
        for name, count in _count_sorted(stats.transformation_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            f"- Bracketed `[3'T]`-style labels stripped: "
            f"`{stats.bracketed_three_prime_stripped}`",
            f"- Bracketed `[5'T]`-style labels stripped: "
            f"`{stats.bracketed_five_prime_stripped}`",
            "",
            "## Molecule and transcription provenance",
            "",
            "### Source Type of Nucleic Acid",
            "",
        ]
    )
    for name, count in _count_sorted(stats.source_nucleic_acid_type_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Canonical molecule_type", ""])
    for name, count in _count_sorted(stats.molecule_type_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### alphabet_as_reported", ""])
    for name, count in _count_sorted(stats.alphabet_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            f"- T→U conversions: `{stats.t_to_u_count}`",
            "",
            "## Chemistry",
            "",
            "Canonical `chemistry` is an abstraction over the closed plan",
            "vocabulary. Exact UTexas `Type of Nucleic Acid` values remain in",
            "the source-metadata sidecar (`utexas_type_of_nucleic_acid`).",
            "",
        ]
    )
    for name, count in _count_sorted(stats.chemistry_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Sequence quality",
            "",
            f"- Invalid character rows: `{stats.invalid_character_count}`",
            f"- Ambiguous base rows: `{stats.ambiguous_base_count}`",
            f"- Mixed T/U rows: `{stats.mixed_t_u_count}`",
            f"- Core below minimum length: `{stats.core_below_min_count}`",
            f"- Core above maximum length: `{stats.core_above_max_count}`",
            "",
            "### sequence_length_full buckets",
            "",
        ]
    )
    for name, count in _count_sorted(stats.length_full_buckets):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### sequence_length_core buckets", ""])
    for name, count in _count_sorted(stats.length_core_buckets):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## QC flag summary",
            "",
            f"- Rows with any QC flag: `{stats.rows_with_any_qc_flag}`",
            f"- Rows with multiple QC flags: `{stats.rows_with_multiple_qc_flags}`",
            f"- Review-candidate rows: `{stats.review_candidate_rows}`",
            "",
        ]
    )
    for name, count in _count_sorted(stats.qc_flag_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Constants / constructs",
            "",
            f"- Known motif detections: `{stats.known_motif_detection_count}`",
            f"- Genuine constant-region proposals: `{stats.constant_region_proposals}`",
            f"- Parseable pool-type groups: `{stats.pool_type_parseable_groups}`",
            f"- Applied trims: `{stats.applied_trims}`",
            f"- Rows where sequence_core != sequence_full: "
            f"`{stats.core_differs_from_full}`",
            f"- Reason: `{stats.constant_region_reason}`",
            "",
            "Tier-2 consensus groups by `(source_db, target_name_raw, publication)`.",
            "Pool Type is independent source-documented evidence only.",
            "Failed consensus attempts are diagnostics, not proposal rows.",
            "",
            "### Human-reviewed trim policy",
            "",
            f"- Candidate constant rules: `{stats.approved_rules + stats.unresolved_rules}`",
            f"- Human-approved rules: `{stats.approved_rules}`",
            f"- Rules still needing source review: `{stats.unresolved_rules}`",
            f"- Approved rules matching ≥1 record: `{stats.approved_rules_matching_ge1}`",
            f"- Approved rules matching no records: `{stats.approved_rules_matching_none}`",
            f"- Records with a safe approved trim applied: `{stats.records_trimmed}`",
            f"- 5′ only: `{stats.trim_five_prime_only}`",
            f"- 3′ only: `{stats.trim_three_prime_only}`",
            f"- both ends: `{stats.trim_both_ends}`",
            f"- Same-side approved-rule ambiguities: `{stats.trim_same_side_ambiguities}`",
            f"- Combined core <20 blocked: `{stats.trim_skipped_combined_below_20}`",
            f"- Combined trim >40% blocked: `{stats.trim_skipped_combined_over_40}`",
            f"- Total bases removed: `{stats.trim_total_bases_removed}`",
            f"- Resolved by approved trim: `{stats.resolved_by_approved_trim}`",
            f"- Still trim_requires_review: `{stats.still_trim_requires_review}`",
            f"- Full >100 rescued into core 20–100: `{stats.rescued_overlength_to_20_100}`",
            f"- Core became out of 20–100 after trim: `{stats.core_became_out_of_range}`",
            f"- Same motif, multiple rule IDs: `{stats.same_motif_multi_rule_applications}`",
            "",
            "### Reviewed alphabet recoveries",
            "",
            f"- Reviewed alphabet recoveries applied: `{stats.alphabet_recoveries_applied}`",
            "- `sequence_raw` remains the immutable source string.",
            "- Recovered A/C/G/U strings feed `sequence_full` before approved trims.",
            f"- Recovered records with core length 20–100: "
            f"`{stats.recovered_core_in_20_100}`",
            f"- Recovered records with core length <20: "
            f"`{stats.recovered_core_below_20}`",
            f"- Recovered records with core length >100: "
            f"`{stats.recovered_core_above_100}`",
            f"- Recovered records with approved constant trim applied: "
            f"`{stats.recovered_approved_trim_applied}`",
            f"- Recovered records still `trim_requires_review`: "
            f"`{stats.recovered_still_trim_requires_review}`",
            "",
            "Approved application requires an unambiguous exact terminal match.",
            "Combined per-record <20 nt or >40% trims are not applied.",
            "",
            "### construct_scope",
            "",
        ]
    )
    for name, count in _count_sorted(stats.construct_scope_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_status", ""])
    for name, count in _count_sorted(stats.trim_status_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_confidence", ""])
    for name, count in _count_sorted(stats.trim_confidence_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### proposal sources", ""])
    if stats.proposal_source_counts:
        for name, count in _count_sorted(stats.proposal_source_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    if diagnostics is not None:
        lines.extend(
            [
                "",
                "### Tier-2 consensus diagnostics",
                "",
                f"- Groups total: `{diagnostics.groups_total}`",
                f"- Groups below min size: `{diagnostics.groups_below_min_size}`",
                f"- Qualifying 5′ groups: `{diagnostics.groups_qualifying_prefix}`",
                f"- Qualifying 3′ groups: `{diagnostics.groups_qualifying_suffix}`",
                f"- No qualifying 5′: `{diagnostics.groups_no_qualifying_prefix}`",
                f"- No qualifying 3′: `{diagnostics.groups_no_qualifying_suffix}`",
                f"- Skipped missing grouping evidence: "
                f"`{diagnostics.skipped_missing_group}`",
                f"- Group-size histogram: `{dict(diagnostics.group_size_histogram)}`",
            ]
        )
    if review_stats:
        lines.extend(
            [
                "",
                "### Rule-level review package",
                "",
                f"- Unique candidate rules: `{review_stats.get('unique_candidate_rules', 0)}`",
                f"- Conflicted rules: `{review_stats.get('conflicted_rules', 0)}`",
                f"- High-priority rules: `{review_stats.get('high_priority_rules', 0)}`",
                f"- Records affected (hypothetical): "
                f"`{review_stats.get('records_affected', 0)}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Integrity",
            "",
            f"- S1 canonical hash before: `{result.s1_hash_before}`",
            f"- S1 canonical hash after: `{result.s1_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            f"- S1 inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Raw workbook SHA-256: `{result.raw_sha256}`"
                if result.raw_sha256
                else "- Raw workbook SHA-256: `not_checked`"
            ),
            (
                f"- Raw workbook SHA unchanged: "
                f"`{'pass' if result.raw_sha_unchanged else 'fail'}`"
                if result.raw_sha_unchanged is not None
                else "- Raw workbook SHA unchanged: `not_checked`"
            ),
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            "",
            "## Outputs",
            "",
            f"- Normalised: "
            f"`{_relative_display(result.output_normalised, repo_root)}`",
            f"- QC: `{_relative_display(result.output_qc, repo_root)}`",
            f"- Review candidates: "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Constant-region proposals: "
            f"`{_relative_display(result.output_proposals, repo_root)}`",
        ]
    )
    if result.output_rule_candidates is not None:
        lines.append(
            f"- Rule candidates: "
            f"`{_relative_display(result.output_rule_candidates, repo_root)}`"
        )
    if result.output_rule_membership is not None:
        lines.append(
            f"- Rule membership: "
            f"`{_relative_display(result.output_rule_membership, repo_root)}`"
        )
    if result.output_review_decisions is not None:
        lines.append(
            f"- Review decisions template: "
            f"`{_relative_display(result.output_review_decisions, repo_root)}`"
        )
    if result.output_review_summary is not None:
        lines.append(
            f"- Review summary: "
            f"`{_relative_display(result.output_review_summary, repo_root)}`"
        )
    if result.output_trim_audit is not None:
        lines.append(
            f"- Trim application audit: "
            f"`{_relative_display(result.output_trim_audit, repo_root)}`"
        )
    if result.output_trim_ambiguity is not None:
        lines.append(
            f"- Trim ambiguity sidecar: "
            f"`{_relative_display(result.output_trim_ambiguity, repo_root)}`"
        )
    lines.extend(
        [
            f"- Report: `{_relative_display(result.output_report, repo_root)}`",
            "",
            "## Stage boundary",
            "",
            "UTexas S2 sequence normalisation and approved constant-region trimming complete.",
            "",
            "- No record was rejected or parked.",
            "- No target normalisation was performed.",
            "- No affinity/evidence decision was performed.",
            "- S3 has not started.",
            "- CHECKPOINT-1 record eligibility review has not started.",
            "- Unresolved constant/construct cases remain flagged for S3 CHECKPOINT-1.",
            "",
        ]
    )
    return "\n".join(lines)


def _recompute_utexas_row_stats(stats: UTexasS2Stats, row_results: list) -> None:
    """Rebuild row-derived S2 stats after approved-trim application."""
    stats.missing_sequence_rows = 0
    stats.nonempty_sequence_rows = 0
    stats.transformation_counts = {}
    stats.alphabet_counts = {}
    stats.molecule_type_counts = {}
    stats.chemistry_counts = {}
    stats.source_nucleic_acid_type_counts = {}
    stats.t_to_u_count = 0
    stats.invalid_character_count = 0
    stats.ambiguous_base_count = 0
    stats.mixed_t_u_count = 0
    stats.known_motif_detection_count = 0
    stats.trim_review_count = 0
    stats.core_below_min_count = 0
    stats.core_above_max_count = 0
    stats.rows_with_any_qc_flag = 0
    stats.rows_with_multiple_qc_flags = 0
    stats.review_candidate_rows = 0
    stats.bracketed_three_prime_stripped = 0
    stats.bracketed_five_prime_stripped = 0
    stats.core_differs_from_full = 0
    stats.construct_scope_counts = {}
    stats.trim_status_counts = {}
    stats.trim_confidence_counts = {}
    stats.length_full_buckets = {}
    stats.length_core_buckets = {}
    stats.qc_flag_counts = {}
    for row in row_results:
        update_utexas_stats_from_row(stats, row)
    stats.s2_rows = len(row_results)
    stats.unique_record_ids = len({row.canonical["record_id"] for row in row_results})
    stats.unique_native_ids = len({row.canonical["native_id"] for row in row_results})


def _record_recovered_core_outcomes(
    stats: UTexasS2Stats,
    normalised_rows: Sequence[Mapping[str, str]],
    recovery_ids: frozenset[str],
) -> None:
    """Summarise post-trim core outcomes for reviewed alphabet recoveries."""
    stats.recovered_core_in_20_100 = 0
    stats.recovered_core_below_20 = 0
    stats.recovered_core_above_100 = 0
    stats.recovered_approved_trim_applied = 0
    stats.recovered_still_trim_requires_review = 0
    applied_trim_status = {
        "primers_removed",
        "t7_removed",
        "t7_and_primers_removed",
        "constants_removed",
    }
    for row in normalised_rows:
        if row.get("record_id") not in recovery_ids:
            continue
        core = row.get("sequence_core") or ""
        length = len(core)
        if length < 20:
            stats.recovered_core_below_20 += 1
        elif length <= 100:
            stats.recovered_core_in_20_100 += 1
        else:
            stats.recovered_core_above_100 += 1
        full = row.get("sequence_full") or ""
        trim_status = row.get("trim_status") or ""
        trim_conf = row.get("trim_confidence") or ""
        if trim_status in applied_trim_status or (
            full and core and core != full and trim_conf in {"high", "medium"}
        ):
            stats.recovered_approved_trim_applied += 1
        flags = {part for part in (row.get("qc_flags") or "").split("|") if part}
        if "trim_requires_review" in flags:
            stats.recovered_still_trim_requires_review += 1


def run_utexas_s2(
    *,
    repo_root: Path,
    input_dir: Path,
    output_dir: Path,
    rules_path: Path,
    policy_path: Path,
    expected_rows: int | None = EXPECTED_UTEXAS_ROWS,
    check_deterministic_rerun: bool = False,
) -> S2RunResult:
    """Execute UTexas S2 normalisation."""
    repo_root = repo_root.resolve()
    input_dir = input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    input_dir = input_dir.resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    rules_path = (
        rules_path if rules_path.is_absolute() else (repo_root / rules_path)
    ).resolve()
    policy_path = (
        policy_path if policy_path.is_absolute() else (repo_root / policy_path)
    ).resolve()

    canonical_path = input_dir / "utexas_extracted.csv"
    sidecar_path = input_dir / "utexas_source_metadata.csv"
    if not canonical_path.is_file():
        raise S2NormaliseError(f"Missing S1 canonical input: {canonical_path.name}")
    if not sidecar_path.is_file():
        raise S2NormaliseError(f"Missing S1 sidecar input: {sidecar_path.name}")

    raw_path = (
        repo_root
        / "data"
        / "raw"
        / "UTexas_aptamer_dataset"
        / "UTexas Aptamer Database dataset_Sept2023.xlsx"
    )
    if not raw_path.is_file():
        raise S2NormaliseError("Missing registered UTexas raw workbook")
    raw_sha_before = _sha256_file(raw_path)
    if raw_sha_before != EXPECTED_RAW_SHA256:
        raise S2NormaliseError(
            "UTexas raw workbook SHA-256 does not match registry expectation"
        )

    s1_hash_before = _sha256_file(canonical_path)
    sidecar_hash_before = _sha256_file(sidecar_path)

    rules = load_normalisation_rules(rules_path)
    policy = load_utexas_policy(policy_path)

    alphabet_resolutions = {}
    recovery_ids: frozenset[str] = frozenset()
    if policy.alphabet_exception_resolutions_path:
        resolutions_path = Path(policy.alphabet_exception_resolutions_path)
        if not resolutions_path.is_absolute():
            resolutions_path = (policy_path.parent / resolutions_path).resolve()
        if resolutions_path.is_file():
            try:
                alphabet_resolutions = load_alphabet_exception_resolutions(
                    resolutions_path
                )
            except AlphabetExceptionError as exc:
                raise S2NormaliseError(str(exc)) from exc
            recovery_ids = approved_recovery_ids(alphabet_resolutions)
        elif expected_rows == EXPECTED_UTEXAS_ROWS:
            raise S2NormaliseError(
                "Missing UTexas alphabet-exception resolutions required for S2"
            )

    canonical_rows = _read_corpus_csv(canonical_path)
    sidecar_rows = _read_sidecar_csv(sidecar_path)
    aligned_sidecar = _match_sidecar_one_to_one(canonical_rows, sidecar_rows)

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S2NormaliseError(
            f"S1 row count must be {expected_rows}; got {len(canonical_rows)}"
        )

    # Registry provenance hard checks.
    for index, row in enumerate(canonical_rows, start=1):
        if row["source_db"] != "utexas":
            raise S2NormaliseError(f"row {index}: source_db must be utexas")
        if row["source_dataset"] != "utexas_sept2023_2026-08":
            raise S2NormaliseError(
                f"row {index}: source_dataset must be utexas_sept2023_2026-08"
            )

    stats = UTexasS2Stats()
    stats.s1_rows = len(canonical_rows)
    stats.source_metadata_rows = len(aligned_sidecar)
    stats.order_preserved = True
    stats.provenance_preserved = True
    stats.sequence_raw_unchanged = True

    normalised_rows: list[dict[str, str]] = []
    qc_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    row_results: list = []

    for s1_row, meta_row in zip(canonical_rows, aligned_sidecar, strict=True):
        record_id = s1_row["record_id"]
        resolution = None
        if record_id in recovery_ids:
            resolution = alphabet_resolutions[record_id]
        result = normalise_utexas_record(
            s1_row,
            meta_row,
            policy=policy,
            rules=rules,
            alphabet_resolution=resolution,
        )
        if result.canonical["record_id"] != s1_row["record_id"]:
            stats.order_preserved = False
            raise S2NormaliseError("S2 altered record_id or row identity")
        if result.canonical["native_id"] != s1_row["native_id"]:
            raise S2NormaliseError("S2 altered native_id")
        if result.canonical["sequence_raw"] != s1_row["sequence_raw"]:
            stats.sequence_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter sequence_raw")
        if result.canonical["target_name_raw"] != s1_row["target_name_raw"]:
            raise S2NormaliseError("S2 must not alter target_name_raw")
        normalised_rows.append(result.canonical)
        qc_rows.append(result.qc)
        row_results.append(result)
        if utexas_is_review_candidate(result.canonical["qc_flags"]):
            review_rows.append(result.qc)
        update_utexas_stats_from_row(stats, result)

    recovery_audit_rows: list[dict[str, str]] = []
    for result in row_results:
        record_id = result.canonical["record_id"]
        if record_id not in recovery_ids:
            continue
        resolution = alphabet_resolutions[record_id]
        recovered_full = result.canonical.get("sequence_full") or ""
        recovery_audit_rows.append(
            {
                "record_id": record_id,
                "native_id": result.canonical.get("native_id") or "",
                "decision": resolution.decision,
                "transformation_profile": resolution.transformation_profile,
                "expected_recovered_length": str(
                    resolution.expected_recovered_length or ""
                ),
                "recovered_length": str(len(recovered_full)) if recovered_full else "",
                "applied": "true",
            }
        )
    recovery_audit_rows.sort(key=lambda row: row["record_id"])
    stats.alphabet_recoveries_applied = len(recovery_audit_rows)
    if expected_rows == EXPECTED_UTEXAS_ROWS:
        if stats.alphabet_recoveries_applied != 17:
            raise S2NormaliseError(
                "Reviewed alphabet recoveries applied must be 17; got "
                f"{stats.alphabet_recoveries_applied}"
            )
        recovered_ids = {row["record_id"] for row in recovery_audit_rows}
        if recovered_ids != set(recovery_ids):
            raise S2NormaliseError(
                "Applied alphabet recoveries do not match the approved ID set"
            )

    stats.s2_rows = len(normalised_rows)
    stats.unique_record_ids = len({row["record_id"] for row in normalised_rows})
    stats.unique_native_ids = len({row["native_id"] for row in normalised_rows})

    if expected_rows == EXPECTED_UTEXAS_ROWS:
        if stats.s2_rows != EXPECTED_UTEXAS_ROWS:
            raise S2NormaliseError(
                f"S2 must preserve {EXPECTED_UTEXAS_ROWS} rows; got {stats.s2_rows}"
            )
        if stats.unique_record_ids != EXPECTED_UTEXAS_ROWS:
            raise S2NormaliseError("S2 record_id values are not unique")
        if stats.unique_native_ids != EXPECTED_UTEXAS_ROWS:
            raise S2NormaliseError("S2 native_id values are not unique")
        if stats.missing_sequence_rows != EXPECTED_UTEXAS_MISSING:
            raise S2NormaliseError(
                "missing_sequence_rows must be "
                f"{EXPECTED_UTEXAS_MISSING}; got {stats.missing_sequence_rows}"
            )
        if stats.nonempty_sequence_rows != EXPECTED_UTEXAS_NONEMPTY:
            raise S2NormaliseError(
                "nonempty_sequence_rows must be "
                f"{EXPECTED_UTEXAS_NONEMPTY}; got {stats.nonempty_sequence_rows}"
            )
        for key, expected in EXPECTED_UTEXAS_MOLECULE.items():
            got = stats.molecule_type_counts.get(key, 0)
            if got != expected:
                raise S2NormaliseError(
                    f"molecule_type {key} expected {expected}; got {got}"
                )
        for key, expected in EXPECTED_UTEXAS_CHEMISTRY.items():
            got = stats.chemistry_counts.get(key, 0)
            if got != expected:
                raise S2NormaliseError(
                    f"chemistry {key} expected {expected}; got {got}"
                )

    # Pool Type = source-documented evidence (independent of Tier-2 grouping).
    pool_proposals, pool_membership = build_pool_type_proposals(row_results)
    known_motif_proposals = build_known_motif_proposals(row_results)

    # Tier-2 consensus uses configured grouping (target_name_raw + publication
    # for UTexas). Pool Type is never the consensus group key.
    inference_inputs = []
    group_membership: dict[str, list[str]] = {}
    for row in normalised_rows:
        group_id = build_group_inference_key(
            source_db=row.get("source_db") or "utexas",
            grouping_mode=policy.group_inference_key,
            experiment_group_id=row.get("experiment_group_id") or None,
            target_name_raw=row.get("target_name_raw") or None,
            publication=row.get("publication") or None,
            pubmed_id=row.get("pubmed_id") or None,
        )
        if group_id is not None:
            group_membership.setdefault(group_id, []).append(row["record_id"])
        inference_inputs.append(
            {
                "record_id": row["record_id"],
                "experiment_group_id": group_id,
                "sequence_full": row["sequence_full"] or None,
            }
        )
    inference_result = infer_group_constant_regions_with_diagnostics(
        inference_inputs, rules=rules
    )
    by_record_id = {row["record_id"]: row for row in normalised_rows}
    group_proposal_rows: list[dict[str, str]] = []
    from adapters.utexas_constant_region_review import simulate_hypothetical_trim

    for proposal in inference_result.proposals:
        if not proposal.proposed_sequence or proposal.length <= 0:
            continue
        # Aggregate hypothetical flags across group members for the proposal row.
        n_fail_min = 0
        n_exceed_40 = 0
        n_unmatched = 0
        for record_id in group_membership.get(proposal.experiment_group_id, ()):
            seq = by_record_id.get(record_id, {}).get("sequence_full") or ""
            effect = simulate_hypothetical_trim(
                seq,
                side=proposal.side,
                motif=proposal.proposed_sequence,
            )
            if effect.would_leave_core_below_20:
                n_fail_min += 1
            if effect.would_trim_more_than_40_percent:
                n_exceed_40 += 1
            if effect.prefix_or_suffix_not_exactly_matched:
                n_unmatched += 1
        group_proposal_rows.append(
            {
                "proposal_id": (
                    f"{proposal.experiment_group_id}:{proposal.side}:group_consensus"
                ),
                "experiment_group_id": proposal.experiment_group_id,
                "proposal_source": "group_consensus",
                "side": proposal.side,
                "proposed_sequence": proposal.proposed_sequence,
                "motif_id": "",
                "motif_length": str(proposal.length),
                "support": f"{proposal.support:.6f}".rstrip("0").rstrip("."),
                "source_documented": "no",
                "empirical_exact_match_fraction": (
                    f"{proposal.support:.6f}".rstrip("0").rstrip(".")
                ),
                "records_considered": str(proposal.records_considered),
                "records_matching_exactly": str(proposal.records_matching_exactly),
                "documented_random_region_length": "",
                "confidence": proposal.confidence,
                "status": proposal.status,
                "applied": "false",
                "reason_not_applied": "no_approved_utexas_trim_rule",
                "reason": proposal.reason,
                "would_leave_core_below_20": "true" if n_fail_min else "false",
                "would_trim_more_than_40_percent": (
                    "true" if n_exceed_40 else "false"
                ),
                "prefix_or_suffix_not_exactly_matched": (
                    "true" if n_unmatched else "false"
                ),
                "predicted_bases_trimmed": str(proposal.length),
            }
        )

    all_proposals = pool_proposals + known_motif_proposals + group_proposal_rows
    all_proposals.sort(key=lambda item: item["proposal_id"])
    assert_genuine_proposals(all_proposals)
    stats.constant_region_proposals = len(all_proposals)
    stats.pool_type_parseable_groups = len(pool_membership)
    for row in all_proposals:
        source = row["proposal_source"]
        stats.proposal_source_counts[source] = (
            stats.proposal_source_counts.get(source, 0) + 1
        )
    stats.applied_trims = 0
    stats.constant_region_reason = (
        f"tier2_grouping={policy.group_inference_key};"
        "approved_trims_pending_application"
    )

    freeze_approved_trims = expected_rows == EXPECTED_UTEXAS_ROWS
    rebuild_tracked_trim_package = freeze_approved_trims and not recovery_ids
    review_package = build_constant_region_review_package(
        proposals=all_proposals,
        normalised_rows=normalised_rows,
        group_membership={
            key: tuple(sorted(set(vals))) for key, vals in group_membership.items()
        },
        pool_type_record_ids=pool_membership,
        diagnostics=inference_result.diagnostics,
        apply_reviewed_policy=rebuild_tracked_trim_package,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_normalised = output_dir / "utexas_normalised.csv"
    out_qc = output_dir / "utexas_s2_qc.csv"
    out_review = output_dir / "utexas_s2_review_candidates.csv"
    out_proposals = output_dir / "utexas_constant_region_proposals.csv"
    out_report = output_dir / "utexas_s2_report.md"
    out_trim_audit = output_dir / "utexas_constant_region_trim_audit.csv"
    out_trim_ambiguity = output_dir / "utexas_constant_region_trim_ambiguity.csv"
    out_recovery_audit = output_dir / "utexas_alphabet_recovery_audit.csv"

    write_csv_atomic(out_proposals, UTEXAS_CONSTANT_PROPOSAL_COLUMNS, all_proposals)
    review_paths = write_review_package_files(
        review_package, output_dir, write_csv_atomic=write_csv_atomic
    )

    s1_by_id = {row["record_id"]: row for row in canonical_rows}
    if rebuild_tracked_trim_package:
        if len(review_package.rule_candidates) != EXPECTED_CANDIDATE_RULES:
            raise S2NormaliseError(
                "UTexas candidate rule count drifted from the reviewed package"
            )
        candidate_sha = _sha256_file(review_paths["rule_candidates"])
        decision_sha = _sha256_file(review_paths["review_decisions"])
        write_tracked_review_artefacts(
            repo_root=repo_root,
            candidates=review_package.rule_candidates,
            decisions=review_package.review_decisions,
            candidate_sha256=candidate_sha,
            decision_sha256=decision_sha,
            write_csv_atomic=write_csv_atomic,
        )

    trim_audit_rows: list[dict[str, str]] = []
    ambiguity_rows: list[dict[str, str]] = []
    if policy.apply_approved_trims:
        rules_file = policy.approved_trim_rules_path
        if not rules_file:
            raise S2NormaliseError("apply_approved_trims requires approved_trim_rules_path")
        rules_path_resolved = Path(rules_file)
        if not rules_path_resolved.is_absolute():
            rules_path_resolved = (policy_path.parent / rules_path_resolved).resolve()
        approved_defs = load_approved_trim_rules(rules_path_resolved)
        approved_ids = {rule.candidate_rule_id for rule in approved_defs}
        decision_approve = {
            row["candidate_rule_id"]
            for row in review_package.review_decisions
            if row["decision"] == "approve"
        }
        decision_unresolved = {
            row["candidate_rule_id"]
            for row in review_package.review_decisions
            if row["decision"] == "needs_source_review"
        }
        if rebuild_tracked_trim_package:
            if approved_ids != decision_approve:
                raise S2NormaliseError(
                    "approved trim-rule IDs do not match explicit review approvals"
                )
            if len(approved_ids) != EXPECTED_APPROVE:
                raise S2NormaliseError(
                    f"approved trim rules must be {EXPECTED_APPROVE}"
                )
            if len(decision_unresolved) != EXPECTED_NEEDS_SOURCE_REVIEW:
                raise S2NormaliseError(
                    "needs_source_review count drifted from the reviewed policy"
                )
        elif freeze_approved_trims:
            tracked_approve, tracked_unresolved = (
                load_tracked_constant_region_decisions(
                    repo_root
                    / "config"
                    / "checkpoint_reviews"
                    / "utexas_constant_region_resolutions.csv"
                )
            )
            if approved_ids != set(tracked_approve):
                raise S2NormaliseError(
                    "approved trim-rule IDs drifted from the tracked 47-rule review"
                )
            if len(approved_ids) != EXPECTED_APPROVE:
                raise S2NormaliseError(
                    f"approved trim rules must be {EXPECTED_APPROVE}"
                )
            if len(tracked_unresolved) != EXPECTED_NEEDS_SOURCE_REVIEW:
                raise S2NormaliseError(
                    "needs_source_review count drifted from the reviewed policy"
                )
            decision_unresolved = set(tracked_unresolved)
        trim_result = apply_approved_trims_to_rows(
            row_results,
            approved_rules=approved_defs,
            unresolved_rule_ids=decision_unresolved,
            membership_rows=review_package.rule_membership,
            s1_by_id=s1_by_id,
        )
        trim_audit_rows = trim_result.audit_rows
        ambiguity_rows = trim_result.ambiguity_rows
        normalised_rows = [item.canonical for item in row_results]
        qc_rows = [item.qc for item in row_results]
        review_rows = [
            item.qc
            for item in row_results
            if utexas_is_review_candidate(item.canonical["qc_flags"])
        ]
        # Rebuild row-derived stats after trim application.
        _recompute_utexas_row_stats(stats, row_results)
        tstats = trim_result.stats
        stats.applied_trims = tstats.records_trimmed
        stats.records_trimmed = tstats.records_trimmed
        stats.trim_five_prime_only = tstats.five_prime_only
        stats.trim_three_prime_only = tstats.three_prime_only
        stats.trim_both_ends = tstats.both_ends
        stats.trim_same_side_ambiguities = tstats.same_side_ambiguities
        stats.trim_skipped_combined_below_20 = tstats.skipped_combined_below_20
        stats.trim_skipped_combined_over_40 = tstats.skipped_combined_over_40
        stats.trim_total_bases_removed = tstats.total_bases_removed
        stats.approved_rules = tstats.approved_rules
        stats.unresolved_rules = tstats.unresolved_rules
        stats.approved_rules_matching_ge1 = tstats.approved_rules_matching_ge1
        stats.approved_rules_matching_none = tstats.approved_rules_matching_none
        stats.resolved_by_approved_trim = tstats.resolved_by_approved_trim
        stats.still_trim_requires_review = tstats.still_trim_requires_review
        stats.rescued_overlength_to_20_100 = tstats.rescued_overlength_to_20_100
        stats.core_became_out_of_range = tstats.core_became_out_of_range
        stats.same_motif_multi_rule_applications = (
            tstats.same_motif_multi_rule_applications
        )
        stats.constant_region_reason = (
            f"tier2_grouping={policy.group_inference_key};"
            f"approved_rules={tstats.approved_rules};"
            f"unresolved_rules={tstats.unresolved_rules}"
        )

    _record_recovered_core_outcomes(stats, normalised_rows, recovery_ids)

    for row in normalised_rows:
        if row["sequence_raw"] != s1_by_id[row["record_id"]]["sequence_raw"]:
            raise S2NormaliseError("S2 must not alter sequence_raw after trim application")

    write_corpus_csv_atomic(out_normalised, normalised_rows)
    write_csv_atomic(out_qc, UTEXAS_S2_QC_COLUMNS, qc_rows)
    write_csv_atomic(out_review, UTEXAS_S2_QC_COLUMNS, review_rows)
    write_csv_atomic(out_trim_audit, TRIM_AUDIT_COLUMNS, trim_audit_rows)
    write_csv_atomic(out_trim_ambiguity, AMBIGUITY_COLUMNS, ambiguity_rows)
    write_csv_atomic(out_recovery_audit, RECOVERY_AUDIT_COLUMNS, recovery_audit_rows)

    s1_hash_after = _sha256_file(canonical_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    inputs_unchanged = (
        s1_hash_before == s1_hash_after
        and sidecar_hash_before == sidecar_hash_after
    )
    if not inputs_unchanged:
        raise S2NormaliseError("S1 inputs were modified during S2 execution")

    raw_sha_after = _sha256_file(raw_path)
    if raw_sha_after != EXPECTED_RAW_SHA256:
        raise S2NormaliseError("UTexas raw workbook SHA changed during S2")

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "normalised": _sha256_file(out_normalised),
            "qc": _sha256_file(out_qc),
            "review": _sha256_file(out_review),
            "proposals": _sha256_file(out_proposals),
            "rule_candidates": _sha256_file(review_paths["rule_candidates"]),
            "rule_membership": _sha256_file(review_paths["rule_membership"]),
            "review_decisions": _sha256_file(review_paths["review_decisions"]),
            "review_summary": _sha256_file(review_paths["review_summary"]),
            "trim_audit": _sha256_file(out_trim_audit),
            "trim_ambiguity": _sha256_file(out_trim_ambiguity),
            "recovery_audit": _sha256_file(out_recovery_audit),
        }
        second = run_utexas_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=policy_path,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["normalised"] == _sha256_file(second.output_normalised)
            and first_hashes["qc"] == _sha256_file(second.output_qc)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["proposals"] == _sha256_file(second.output_proposals)
            and second.output_rule_candidates is not None
            and first_hashes["rule_candidates"]
            == _sha256_file(second.output_rule_candidates)
            and second.output_rule_membership is not None
            and first_hashes["rule_membership"]
            == _sha256_file(second.output_rule_membership)
            and second.output_review_decisions is not None
            and first_hashes["review_decisions"]
            == _sha256_file(second.output_review_decisions)
            and second.output_review_summary is not None
            and first_hashes["review_summary"]
            == _sha256_file(second.output_review_summary)
            and second.output_trim_audit is not None
            and first_hashes["trim_audit"] == _sha256_file(second.output_trim_audit)
            and second.output_trim_ambiguity is not None
            and first_hashes["trim_ambiguity"]
            == _sha256_file(second.output_trim_ambiguity)
            and second.output_recovery_audit is not None
            and first_hashes["recovery_audit"]
            == _sha256_file(second.output_recovery_audit)
        )
        if not deterministic_ok:
            raise S2NormaliseError(
                "S2 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S2RunResult(
        source_key="utexas",
        stats=stats,
        output_normalised=out_normalised,
        output_qc=out_qc,
        output_review=out_review,
        output_proposals=out_proposals,
        output_report=out_report,
        s1_hash_before=s1_hash_before,
        s1_hash_after=s1_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        raw_sha256=raw_sha_after,
        raw_sha_unchanged=True,
        output_rule_candidates=review_paths["rule_candidates"],
        output_rule_membership=review_paths["rule_membership"],
        output_review_decisions=review_paths["review_decisions"],
        output_review_summary=review_paths["review_summary"],
        output_trim_audit=out_trim_audit,
        output_trim_ambiguity=out_trim_ambiguity,
        output_recovery_audit=out_recovery_audit,
    )
    report_text = build_utexas_s2_report(
        repo_root=repo_root,
        result=run_result,
        rules_path=rules_path,
        policy_path=policy_path,
        review_stats=review_package.stats,
        diagnostics=inference_result.diagnostics,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in report_text:
        raise S2NormaliseError("S2 report must not contain absolute repository paths")
    _write_text_atomic(out_report, report_text)
    return run_result


def build_aptadb_s2_report(
    *,
    repo_root: Path,
    result: S2RunResult,
    rules_path: Path,
    policy_path: Path,
    diagnostics=None,
) -> str:
    """Build an aggregate-only Markdown AptaDB S2 report (no sequences or IDs)."""
    stats = result.stats
    if not isinstance(stats, AptaDBS2Stats):
        raise S2NormaliseError("AptaDB report requires AptaDBS2Stats")
    full_min, full_med, full_max = summarise_aptadb_lengths(stats.length_full_values)
    core_min, core_med, core_max = summarise_aptadb_lengths(stats.length_core_values)
    lines = [
        "# AptaDB S2 normalisation report",
        "",
        "## Reconciliation",
        "",
        f"- Source key: `aptadb`",
        f"- Source dataset: `aptadb_official_export_2026-08`",
        f"- S1 canonical rows: `{stats.s1_rows}`",
        f"- Source-metadata rows: `{stats.source_metadata_rows}`",
        f"- S2 output rows: `{stats.s2_rows}`",
        f"- Unique record_id values: `{stats.unique_record_ids}`",
        f"- Unique native_id values: `{stats.unique_native_ids}`",
        f"- Row disappearance: `{stats.s1_rows - stats.s2_rows}`",
        f"- S1 row order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        f"- S1 provenance preserved: "
        f"`{'pass' if stats.provenance_preserved else 'fail'}`",
        f"- sequence_raw unchanged: "
        f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
        f"- publication unchanged: "
        f"`{'pass' if stats.publication_unchanged else 'fail'}`",
        f"- Missing sequence rows: `{stats.missing_sequence_rows}`",
        f"- Nonempty sequence rows: `{stats.nonempty_sequence_rows}`",
        f"- Shared rules: `{_relative_display(rules_path, repo_root)}`",
        f"- Source policy: `{_relative_display(policy_path, repo_root)}`",
        "",
        "## Molecule / chemistry",
        "",
        "Source `aptamer.csv.Aptamer Chemistry` is authoritative. `DNA` maps",
        "to canonical `ssDNA` (DNA aptamers, not double-stranded DNA).",
        "Molecule type is never inferred from alphabet.",
        "",
        "### Source Aptamer Chemistry",
        "",
    ]
    for name, count in _count_sorted(stats.source_chemistry_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Canonical molecule_type", ""])
    for name, count in _count_sorted(stats.molecule_type_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Canonical chemistry", ""])
    for name, count in _count_sorted(stats.chemistry_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Reported alphabet",
            "",
        ]
    )
    for name, count in _count_sorted(stats.alphabet_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Computational transcription",
            "",
            f"- total `t_to_u_applied=true`: `{stats.t_to_u_count}`",
            "",
        ]
    )
    if stats.t_to_u_by_molecule:
        for name, count in _count_sorted(stats.t_to_u_by_molecule):
            lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Display cleaning",
            "",
        ]
    )
    if stats.transformation_counts:
        for name, count in _count_sorted(stats.transformation_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## QC",
            "",
            f"- Invalid character rows: `{stats.invalid_character_count}`",
            f"- Alignment-gap rows: `{stats.alignment_gaps_count}`",
            f"- Ambiguous base rows: `{stats.ambiguous_base_count}`",
            f"- Mixed T/U rows: `{stats.mixed_t_u_count}`",
            f"- Core below minimum length: `{stats.core_below_min_count}`",
            f"- Core above maximum length: `{stats.core_above_max_count}`",
            f"- Rows with any QC flag: `{stats.rows_with_any_qc_flag}`",
            f"- Rows with multiple QC flags: `{stats.rows_with_multiple_qc_flags}`",
            f"- Review-candidate rows: `{stats.review_candidate_rows}`",
            "",
        ]
    )
    for name, count in _count_sorted(stats.qc_flag_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Length",
            "",
            "Lengths are computed from the shared normalised representation,",
            "not from AptaDB source `Length`.",
            "",
            f"- sequence_length_full min / median / max: "
            f"`{full_min}` / `{full_med}` / `{full_max}`",
            f"- sequence_length_core min / median / max: "
            f"`{core_min}` / `{core_med}` / `{core_max}`",
            "",
            "### sequence_length_full buckets",
            "",
        ]
    )
    for name, count in _count_sorted(stats.length_full_buckets):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### sequence_length_core buckets", ""])
    for name, count in _count_sorted(stats.length_core_buckets):
        lines.append(f"- `{name}`: `{count}`")
    if stats.core_differs_from_full == 0:
        lines.extend(
            [
                "",
                "Full and core length distributions are identical because no",
                "trim was applied (`sequence_core == sequence_full`).",
            ]
        )
    lines.extend(
        [
            "",
            "## Construct / trim state",
            "",
            "AptaDB does not supply a reliable construct-scope annotation.",
            "Absence of a detected primer is not evidence of random-region-only.",
            "",
            "### construct_scope",
            "",
        ]
    )
    for name, count in _count_sorted(stats.construct_scope_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_status", ""])
    for name, count in _count_sorted(stats.trim_status_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_confidence", ""])
    for name, count in _count_sorted(stats.trim_confidence_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Constant-region inference",
            "",
            "Grouping uses shared `target_name_raw` plus publication identity",
            "(`publication` if nonempty, else `pubmed_id`). Rows without a",
            "usable target name are not grouped, even when they share a PMID.",
            "Newly inferred medium-confidence motifs are proposals only and",
            "were not applied. `config/constant_regions.yaml` was not modified.",
            "",
            f"- Candidate groups considered: `{stats.groups_considered}`",
            f"- Groups meeting minimum size: `{stats.groups_meeting_min_size}`",
            f"- 5′ proposals: `{stats.five_prime_proposals}`",
            f"- 3′ proposals: `{stats.three_prime_proposals}`",
            f"- Records associated with medium-confidence proposals: "
            f"`{stats.records_with_medium_confidence_proposal}`",
            f"- Previously approved high-confidence trims applied: "
            f"`{stats.high_confidence_trims_applied}`",
            f"- Records actually trimmed: `{stats.applied_trims}`",
            f"- Genuine proposal rows: `{stats.constant_region_proposals}`",
            f"- Known motif detections: `{stats.known_motif_detection_count}`",
            f"- Rows where sequence_core != sequence_full: "
            f"`{stats.core_differs_from_full}`",
            f"- Reason: `{stats.constant_region_reason}`",
            "",
            "### proposal sources",
            "",
        ]
    )
    if stats.proposal_source_counts:
        for name, count in _count_sorted(stats.proposal_source_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    if diagnostics is not None:
        lines.extend(
            [
                "",
                "### Tier-2 consensus diagnostics",
                "",
                f"- Groups total: `{diagnostics.groups_total}`",
                f"- Groups below min size: `{diagnostics.groups_below_min_size}`",
                f"- Qualifying 5′ groups: `{diagnostics.groups_qualifying_prefix}`",
                f"- Qualifying 3′ groups: `{diagnostics.groups_qualifying_suffix}`",
                f"- No qualifying 5′: `{diagnostics.groups_no_qualifying_prefix}`",
                f"- No qualifying 3′: `{diagnostics.groups_no_qualifying_suffix}`",
                f"- Skipped missing grouping evidence: "
                f"`{diagnostics.skipped_missing_group}`",
                f"- Group-size histogram: `{dict(diagnostics.group_size_histogram)}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Invariants",
            "",
            f"- sequence_raw unchanged: "
            f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
            f"- Records retained: `{stats.s2_rows}`",
            f"- Provenance unchanged: "
            f"`{'pass' if stats.provenance_preserved else 'fail'}`",
            "- S4 target/evidence fields remain blank",
            (
                f"- Raw input hashes unchanged: "
                f"`{'pass' if result.raw_sha_unchanged else 'fail'}`"
                if result.raw_sha_unchanged is not None
                else "- Raw input hashes unchanged: `not_checked`"
            ),
            f"- S1 inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            "",
            f"- S1 canonical hash before: `{result.s1_hash_before}`",
            f"- S1 canonical hash after: `{result.s1_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            (
                f"- Raw SHA-256: `{result.raw_sha256}`"
                if result.raw_sha256
                else "- Raw SHA-256: `not_checked`"
            ),
            "",
            "## Outputs",
            "",
            f"- Normalised: "
            f"`{_relative_display(result.output_normalised, repo_root)}`",
            f"- QC: `{_relative_display(result.output_qc, repo_root)}`",
            f"- Review candidates: "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Constant-region proposals: "
            f"`{_relative_display(result.output_proposals, repo_root)}`",
            f"- Report: `{_relative_display(result.output_report, repo_root)}`",
            "",
            "## Stage boundary",
            "",
            "AptaDB S2 sequence normalisation and constant-region proposal only.",
            "",
            "- No record was rejected or parked.",
            "- No target canonicalisation was performed.",
            "- No affinity/evidence decision was performed.",
            "- No leakage, clustering, balancing or partitioning was performed.",
            "- S3 has not started.",
            "- Newly inferred medium-confidence motifs were not applied.",
            "",
        ]
    )
    return "\n".join(lines)


def run_aptadb_s2(
    *,
    repo_root: Path,
    input_dir: Path,
    output_dir: Path,
    rules_path: Path,
    policy_path: Path,
    expected_rows: int | None = EXPECTED_APTADB_ROWS,
    check_deterministic_rerun: bool = False,
) -> S2RunResult:
    """Execute AptaDB S2 normalisation."""
    repo_root = repo_root.resolve()
    input_dir = input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    input_dir = input_dir.resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    rules_path = (
        rules_path if rules_path.is_absolute() else (repo_root / rules_path)
    ).resolve()
    policy_path = (
        policy_path if policy_path.is_absolute() else (repo_root / policy_path)
    ).resolve()

    canonical_path = input_dir / "aptadb_extracted.csv"
    sidecar_path = input_dir / "aptadb_source_metadata.csv"
    if not canonical_path.is_file():
        raise S2NormaliseError(f"Missing S1 canonical input: {canonical_path.name}")
    if not sidecar_path.is_file():
        raise S2NormaliseError(f"Missing S1 sidecar input: {sidecar_path.name}")

    raw_dir = repo_root / "data" / "raw" / "AptaDB"
    raw_paths = {
        name: raw_dir / name for name in EXPECTED_APTADB_RAW_SHA256
    }
    raw_sha_before: dict[str, str] = {}
    if expected_rows == EXPECTED_APTADB_ROWS:
        for name, path in raw_paths.items():
            if not path.is_file():
                raise S2NormaliseError(f"Missing registered AptaDB raw file: {name}")
            digest = _sha256_file(path)
            if digest != EXPECTED_APTADB_RAW_SHA256[name]:
                raise S2NormaliseError(
                    f"AptaDB raw {name} SHA-256 does not match registry expectation"
                )
            raw_sha_before[name] = digest

    s1_hash_before = _sha256_file(canonical_path)
    sidecar_hash_before = _sha256_file(sidecar_path)

    rules = load_normalisation_rules(rules_path)
    policy = load_aptadb_policy(policy_path)
    if policy.apply_approved_trims:
        raise S2NormaliseError("AptaDB S2 must not apply approved trims")

    canonical_rows = _read_corpus_csv(canonical_path)
    sidecar_rows = _read_sidecar_csv(sidecar_path)
    aligned_sidecar = _match_sidecar_one_to_one(canonical_rows, sidecar_rows)

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S2NormaliseError(
            f"S1 row count must be {expected_rows}; got {len(canonical_rows)}"
        )

    for index, row in enumerate(canonical_rows, start=1):
        if row["source_db"] != "aptadb":
            raise S2NormaliseError(f"row {index}: source_db must be aptadb")
        if row["source_dataset"] != "aptadb_official_export_2026-08":
            raise S2NormaliseError(
                f"row {index}: source_dataset must be aptadb_official_export_2026-08"
            )

    stats = AptaDBS2Stats()
    stats.s1_rows = len(canonical_rows)
    stats.source_metadata_rows = len(aligned_sidecar)
    stats.order_preserved = True
    stats.provenance_preserved = True
    stats.sequence_raw_unchanged = True
    stats.publication_unchanged = True

    normalised_rows: list[dict[str, str]] = []
    qc_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    row_results: list = []

    for s1_row, meta_row in zip(canonical_rows, aligned_sidecar, strict=True):
        result = normalise_aptadb_record(
            s1_row,
            meta_row,
            policy=policy,
            rules=rules,
        )
        if result.canonical["record_id"] != s1_row["record_id"]:
            stats.order_preserved = False
            raise S2NormaliseError("S2 altered record_id or row identity")
        if result.canonical["native_id"] != s1_row["native_id"]:
            raise S2NormaliseError("S2 altered native_id")
        if result.canonical["sequence_raw"] != s1_row["sequence_raw"]:
            stats.sequence_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter sequence_raw")
        if result.canonical["publication"] != s1_row["publication"]:
            stats.publication_unchanged = False
            raise S2NormaliseError("S2 must not alter publication")
        if result.canonical["pubmed_id"] != s1_row["pubmed_id"]:
            raise S2NormaliseError("S2 must not alter pubmed_id")
        if result.canonical["target_name_raw"] != s1_row["target_name_raw"]:
            raise S2NormaliseError("S2 must not alter target_name_raw")
        if result.canonical["sequence_core"] != result.canonical["sequence_full"]:
            raise S2NormaliseError(
                "AptaDB S2 must not apply trims; sequence_core must equal "
                "sequence_full"
            )
        normalised_rows.append(result.canonical)
        qc_rows.append(result.qc)
        row_results.append(result)
        if aptadb_is_review_candidate(result.canonical["qc_flags"]):
            review_rows.append(result.qc)
        update_aptadb_stats_from_row(stats, result)

    stats.s2_rows = len(normalised_rows)
    stats.unique_record_ids = len({row["record_id"] for row in normalised_rows})
    stats.unique_native_ids = len({row["native_id"] for row in normalised_rows})

    if expected_rows == EXPECTED_APTADB_ROWS:
        if stats.s2_rows != EXPECTED_APTADB_ROWS:
            raise S2NormaliseError(
                f"S2 must preserve {EXPECTED_APTADB_ROWS} rows; got {stats.s2_rows}"
            )
        if stats.unique_record_ids != EXPECTED_APTADB_ROWS:
            raise S2NormaliseError("S2 record_id values are not unique")
        if stats.s1_rows - stats.s2_rows != 0:
            raise S2NormaliseError("S2 row disappearance must be 0")
        for key, expected in EXPECTED_APTADB_MOLECULE.items():
            got = stats.molecule_type_counts.get(key, 0)
            if got != expected:
                raise S2NormaliseError(
                    f"molecule_type {key} expected {expected}; got {got}"
                )
        for key, expected in EXPECTED_APTADB_CHEMISTRY.items():
            got = stats.chemistry_counts.get(key, 0)
            if got != expected:
                raise S2NormaliseError(
                    f"chemistry {key} expected {expected}; got {got}"
                )
        if stats.core_differs_from_full != 0:
            raise S2NormaliseError(
                "AptaDB S2 applied a trim; sequence_core must equal sequence_full"
            )

    inference_inputs = []
    group_membership: dict[str, list[str]] = {}
    for row in normalised_rows:
        group_id = build_group_inference_key(
            source_db=row.get("source_db") or "aptadb",
            grouping_mode=policy.group_inference_key,
            experiment_group_id=row.get("experiment_group_id") or None,
            target_name_raw=row.get("target_name_raw") or None,
            publication=row.get("publication") or None,
            pubmed_id=row.get("pubmed_id") or None,
        )
        if group_id is not None:
            group_membership.setdefault(group_id, []).append(row["record_id"])
        inference_inputs.append(
            {
                "record_id": row["record_id"],
                "experiment_group_id": group_id,
                "sequence_full": row["sequence_full"] or None,
            }
        )
    inference_result = infer_group_constant_regions_with_diagnostics(
        inference_inputs, rules=rules
    )
    group_proposal_rows = build_aptadb_group_proposal_rows(inference_result.proposals)
    known_motif_proposals = build_aptadb_known_motif_proposals(row_results)
    all_proposals = group_proposal_rows + known_motif_proposals
    all_proposals.sort(key=lambda item: item["proposal_id"])
    assert_aptadb_genuine_proposals(all_proposals)

    stats.constant_region_proposals = len(all_proposals)
    stats.groups_considered = inference_result.diagnostics.groups_total
    stats.groups_meeting_min_size = (
        inference_result.diagnostics.groups_total
        - inference_result.diagnostics.groups_below_min_size
    )
    stats.five_prime_proposals = sum(
        1
        for row in group_proposal_rows
        if row["side"] == "five_prime" and row["proposal_source"] == "group_consensus"
    )
    stats.three_prime_proposals = sum(
        1
        for row in group_proposal_rows
        if row["side"] == "three_prime" and row["proposal_source"] == "group_consensus"
    )
    medium_groups = {
        row["experiment_group_id"]
        for row in group_proposal_rows
        if row["proposal_source"] == "group_consensus"
    }
    stats.records_with_medium_confidence_proposal = sum(
        len(group_membership.get(group_id, ())) for group_id in medium_groups
    )
    stats.high_confidence_trims_applied = 0
    stats.applied_trims = 0
    for row in all_proposals:
        source = row["proposal_source"]
        stats.proposal_source_counts[source] = (
            stats.proposal_source_counts.get(source, 0) + 1
        )
    stats.constant_region_reason = (
        f"tier2_grouping={policy.group_inference_key};"
        "proposals_only_not_applied"
    )

    # Re-assert that medium-confidence proposals did not mutate cores.
    for row in normalised_rows:
        if row["sequence_core"] != row["sequence_full"]:
            raise S2NormaliseError(
                "medium-confidence proposals must not mutate sequence_core"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_normalised = output_dir / "aptadb_normalised.csv"
    out_qc = output_dir / "aptadb_s2_qc.csv"
    out_review = output_dir / "aptadb_s2_review_candidates.csv"
    out_proposals = output_dir / "aptadb_constant_region_proposals.csv"
    out_report = output_dir / "aptadb_s2_report.md"

    write_corpus_csv_atomic(out_normalised, normalised_rows)
    write_csv_atomic(out_qc, APTADB_S2_QC_COLUMNS, qc_rows)
    write_csv_atomic(out_review, APTADB_S2_QC_COLUMNS, review_rows)
    write_csv_atomic(out_proposals, APTADB_CONSTANT_PROPOSAL_COLUMNS, all_proposals)

    s1_hash_after = _sha256_file(canonical_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    inputs_unchanged = (
        s1_hash_before == s1_hash_after
        and sidecar_hash_before == sidecar_hash_after
    )
    if not inputs_unchanged:
        raise S2NormaliseError("S1 inputs were modified during S2 execution")

    raw_sha_after_joined = None
    raw_sha_unchanged: bool | None = None
    if raw_sha_before:
        after_parts = []
        for name, path in raw_paths.items():
            digest = _sha256_file(path)
            if digest != raw_sha_before[name]:
                raise S2NormaliseError(f"AptaDB raw {name} SHA changed during S2")
            after_parts.append(f"{name}={digest}")
        raw_sha_after_joined = ";".join(after_parts)
        raw_sha_unchanged = True

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "normalised": _sha256_file(out_normalised),
            "qc": _sha256_file(out_qc),
            "review": _sha256_file(out_review),
            "proposals": _sha256_file(out_proposals),
        }
        second = run_aptadb_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=policy_path,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["normalised"] == _sha256_file(second.output_normalised)
            and first_hashes["qc"] == _sha256_file(second.output_qc)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["proposals"] == _sha256_file(second.output_proposals)
        )
        if not deterministic_ok:
            raise S2NormaliseError(
                "S2 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S2RunResult(
        source_key="aptadb",
        stats=stats,
        output_normalised=out_normalised,
        output_qc=out_qc,
        output_review=out_review,
        output_proposals=out_proposals,
        output_report=out_report,
        s1_hash_before=s1_hash_before,
        s1_hash_after=s1_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        raw_sha256=raw_sha_after_joined,
        raw_sha_unchanged=raw_sha_unchanged,
    )
    report_text = build_aptadb_s2_report(
        repo_root=repo_root,
        result=run_result,
        rules_path=rules_path,
        policy_path=policy_path,
        diagnostics=inference_result.diagnostics,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in report_text:
        raise S2NormaliseError("S2 report must not contain absolute repository paths")
    _write_text_atomic(out_report, report_text)
    return run_result


def build_riboaptamer_s2_report(
    *,
    repo_root: Path,
    result: S2RunResult,
    rules_path: Path,
    policy_path: Path,
) -> str:
    """Build an aggregate-only Markdown RiboAptamer S2 report (no sequences)."""
    stats = result.stats
    if not isinstance(stats, RiboAptamerS2Stats):
        raise S2NormaliseError("RiboAptamer report requires RiboAptamerS2Stats")
    full_min, full_med, full_max = summarise_riboaptamer_lengths(
        stats.length_full_values
    )
    core_min, core_med, core_max = summarise_riboaptamer_lengths(
        stats.length_core_values
    )
    regression_a = "PASS" if stats.truncation_regression_a_pass else "FAIL"
    regression_b = "PASS" if stats.truncation_regression_b_pass else "FAIL"
    regression_c = "PASS" if stats.truncation_regression_c_pass else "FAIL"
    scanned = ", ".join(f"`{name}`" for name in stats.known_motifs_scanned) or "(none)"
    lines = [
        "# RiboAptamer S2 normalisation report",
        "",
        "## Reconciliation",
        "",
        f"- Source key: `riboaptamer`",
        f"- Source dataset: `{EXPECTED_RIBOAPTAMER_SOURCE_DATASET}`",
        f"- S1 canonical rows: `{stats.s1_rows}`",
        f"- Source-metadata rows: `{stats.source_metadata_rows}`",
        f"- S2 output rows: `{stats.s2_rows}`",
        f"- Records dropped: `{stats.records_dropped}`",
        f"- Records parked: `{stats.records_parked}`",
        f"- Unique record_id values: `{stats.unique_record_ids}`",
        f"- Unique native_id values: `{stats.unique_native_ids}`",
        f"- Row disappearance: `{stats.s1_rows - stats.s2_rows}`",
        f"- S1 row order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        f"- S1 provenance preserved: "
        f"`{'pass' if stats.provenance_preserved else 'fail'}`",
        f"- sequence_raw unchanged: "
        f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
        f"- target_name_raw unchanged: "
        f"`{'pass' if stats.target_name_raw_unchanged else 'fail'}`",
        f"- notes unchanged: `{'pass' if stats.notes_unchanged else 'fail'}`",
        f"- Missing sequence rows: `{stats.missing_sequence_rows}`",
        f"- Nonempty sequence rows: `{stats.nonempty_sequence_rows}`",
        f"- Shared rules: `{_relative_display(rules_path, repo_root)}`",
        f"- Source policy: `{_relative_display(policy_path, repo_root)}`",
        "",
        "## Molecule / chemistry",
        "",
        "Experimental molecule type is fixed by the RiboAptamer source",
        "contract (`molecule_type=RNA`, `chemistry=RNA`). Source `Type`",
        "(`Proteins`, `Small molecules`, `Cells`, `Nucleic acids`) is a",
        "target-class field retained in the sidecar only. It is not used",
        "as `molecule_type`, `chemistry`, canonical `target_type`, or an",
        "S2/S3 parking rule.",
        "",
        "### Source Type (target class; unused at S2)",
        "",
    ]
    for name, count in _count_sorted(stats.source_type_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Canonical molecule_type", ""])
    for name, count in _count_sorted(stats.molecule_type_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Canonical chemistry", ""])
    for name, count in _count_sorted(stats.chemistry_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Reported alphabet",
            "",
            "Shared alphabet vocabulary is `RNA` / `DNA_T` / `mixed_T_U` /",
            "`ambiguous` / `invalid` (not a separate `RNA_U` token).",
            "",
        ]
    )
    for name, count in _count_sorted(stats.alphabet_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Computational transcription",
            "",
            f"- total `t_to_u_applied=true`: `{stats.t_to_u_count}`",
            "",
        ]
    )
    if stats.t_to_u_by_molecule:
        for name, count in _count_sorted(stats.t_to_u_by_molecule):
            lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Display cleaning",
            "",
        ]
    )
    if stats.transformation_counts:
        for name, count in _count_sorted(stats.transformation_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## QC",
            "",
            f"- Invalid character rows: `{stats.invalid_character_count}`",
            f"- Alignment-gap rows: `{stats.alignment_gaps_count}`",
            f"- Ambiguous base rows: `{stats.ambiguous_base_count}`",
            f"- Mixed T/U rows: `{stats.mixed_t_u_count}`",
            f"- Truncation / ellipsis rows (`truncated_sequence`): "
            f"`{stats.truncated_sequence_count}`",
            f"- Display-normalised sequences containing `...` or `…`: "
            f"`{stats.containing_ellipsis_count}`",
            f"- Display-normalised sequences ending in `.` / `...` / `…`: "
            f"`{stats.ending_period_or_ellipsis_count}`",
            f"- Core below minimum length: `{stats.core_below_min_count}`",
            f"- Core above maximum length: `{stats.core_above_max_count}`",
            f"- Rows with any QC flag: `{stats.rows_with_any_qc_flag}`",
            f"- Rows with multiple QC flags: `{stats.rows_with_multiple_qc_flags}`",
            f"- Review-candidate rows: `{stats.review_candidate_rows}`",
            "",
        ]
    )
    for name, count in _count_sorted(stats.qc_flag_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Length",
            "",
            "Lengths are computed from the shared normalised representation,",
            "not from the source `Length` column. These buckets are",
            "descriptive at S2; they do not filter records.",
            "",
            f"- sequence_length_full min / median / max: "
            f"`{full_min}` / `{full_med}` / `{full_max}`",
            f"- sequence_length_core min / median / max: "
            f"`{core_min}` / `{core_med}` / `{core_max}`",
            "",
            "### sequence_length_full buckets",
            "",
        ]
    )
    for name, count in _count_sorted(stats.length_full_buckets):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### sequence_length_core buckets", ""])
    for name, count in _count_sorted(stats.length_core_buckets):
        lines.append(f"- `{name}`: `{count}`")
    if stats.core_differs_from_full == 0:
        lines.extend(
            [
                "",
                "Full and core length distributions are identical because no",
                "trim was applied (`sequence_core == sequence_full`).",
            ]
        )
    lines.extend(
        [
            "",
            "## Construct / trim state",
            "",
            "Known-motif detection is recorded as a proposal only.",
            "Detection does not authorise trimming at S2.",
            "",
            "### construct_scope",
            "",
        ]
    )
    for name, count in _count_sorted(stats.construct_scope_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_status", ""])
    for name, count in _count_sorted(stats.trim_status_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_confidence", ""])
    for name, count in _count_sorted(stats.trim_confidence_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Constant-region detection",
            "",
            "group-wise inference disabled for RiboAptamer in this run.",
            "No `(Aptamer Name, PubMed)` grouping mode was added, and",
            "`experiment_group_id` / `target_name_raw` were not populated",
            "to exploit an existing grouping key. Known-motif detections",
            "are proposals only (`applied=false`).",
            "",
            f"- Approved known motifs scanned: {scanned}",
            f"- Records with known-motif detection: "
            f"`{stats.known_motif_detection_count}`",
            f"- Genuine proposal rows: `{stats.constant_region_proposals}`",
            f"- 5′ known-motif proposals: `{stats.five_prime_proposals}`",
            f"- 3′ known-motif proposals: `{stats.three_prime_proposals}`",
            f"- Group-consensus proposals: `0`",
            f"- Groups considered: `{stats.groups_considered}`",
            f"- Groups meeting minimum size: `{stats.groups_meeting_min_size}`",
            f"- Records associated with medium-confidence proposals: "
            f"`{stats.records_with_medium_confidence_proposal}`",
            f"- Previously approved high-confidence trims applied: "
            f"`{stats.high_confidence_trims_applied}`",
            f"- Records actually trimmed: `{stats.applied_trims}`",
            f"- Rows where sequence_core != sequence_full: "
            f"`{stats.core_differs_from_full}`",
            f"- Reason: `{stats.constant_region_reason}`",
            "",
            "### proposal sources",
            "",
        ]
    )
    if stats.proposal_source_counts:
        for name, count in _count_sorted(stats.proposal_source_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## Truncation regressions",
            "",
            "These guards detect accidental re-registration of the old",
            "truncated RiboAptamer export. They do not drop records.",
            "Diagnostics use the display-normalised sequence, not",
            "`sequence_raw`.",
            "",
            f"- Regression A (<1% ending in `.` / `...` / `…`): `{regression_a}` "
            f"({stats.ending_period_or_ellipsis_count}/{stats.s2_rows})",
            f"- Regression B (median full length > 20 nt): `{regression_b}` "
            f"(median `{full_med}`)",
            f"- Regression C (≤1 containing `...` or `…` anywhere): "
            f"`{regression_c}` "
            f"({stats.containing_ellipsis_count}/{stats.s2_rows})",
            "",
            "## Invariants",
            "",
            f"- sequence_raw unchanged: "
            f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
            f"- Records retained: `{stats.s2_rows}`",
            f"- Provenance unchanged: "
            f"`{'pass' if stats.provenance_preserved else 'fail'}`",
            "- S4 target/evidence/affinity/PDB fields remain blank",
            (
                f"- Raw input hash unchanged: "
                f"`{'pass' if result.raw_sha_unchanged else 'fail'}`"
                if result.raw_sha_unchanged is not None
                else "- Raw input hash unchanged: `not_checked`"
            ),
            f"- S1 inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            "",
            f"- S1 canonical hash before: `{result.s1_hash_before}`",
            f"- S1 canonical hash after: `{result.s1_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            (
                f"- Raw SHA-256: `{result.raw_sha256}`"
                if result.raw_sha256
                else "- Raw SHA-256: `not_checked`"
            ),
            "",
            "## Outputs",
            "",
            f"- Normalised: "
            f"`{_relative_display(result.output_normalised, repo_root)}`",
            f"- QC: `{_relative_display(result.output_qc, repo_root)}`",
            f"- Review candidates: "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Detected constants / proposals: "
            f"`{_relative_display(result.output_proposals, repo_root)}`",
            f"- Report: `{_relative_display(result.output_report, repo_root)}`",
            "",
            "## Stage boundary",
            "",
            "RiboAptamer S2 sequence normalisation and known-motif detection",
            "only.",
            "",
            "- No record was rejected or parked.",
            "- No target canonicalisation was performed.",
            "- No affinity/evidence/PDB decision was performed.",
            "- No leakage, clustering, balancing or partitioning was performed.",
            "- S3 has not started.",
            "- Known-motif detections were not applied as trims.",
            "- group-wise inference disabled for RiboAptamer in this run.",
            "",
        ]
    )
    return "\n".join(lines)


def run_riboaptamer_s2(
    *,
    repo_root: Path,
    input_dir: Path,
    output_dir: Path,
    rules_path: Path,
    policy_path: Path,
    expected_rows: int | None = EXPECTED_RIBOAPTAMER_ROWS,
    check_deterministic_rerun: bool = False,
) -> S2RunResult:
    """Execute RiboAptamer S2 normalisation."""
    repo_root = repo_root.resolve()
    input_dir = input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    input_dir = input_dir.resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    rules_path = (
        rules_path if rules_path.is_absolute() else (repo_root / rules_path)
    ).resolve()
    policy_path = (
        policy_path if policy_path.is_absolute() else (repo_root / policy_path)
    ).resolve()

    canonical_path = input_dir / "riboaptamer_extracted.csv"
    sidecar_path = input_dir / "riboaptamer_source_metadata.csv"
    if not canonical_path.is_file():
        raise S2NormaliseError(f"Missing S1 canonical input: {canonical_path.name}")
    if not sidecar_path.is_file():
        raise S2NormaliseError(f"Missing S1 sidecar input: {sidecar_path.name}")

    raw_path = repo_root / "data" / "raw" / "riboaptamer" / "all_sequences_509_rows.csv"
    raw_sha_before: str | None = None
    if expected_rows == EXPECTED_RIBOAPTAMER_ROWS:
        if not raw_path.is_file():
            raise S2NormaliseError("Missing registered RiboAptamer raw file")
        digest = _sha256_file(raw_path)
        if digest != EXPECTED_RIBOAPTAMER_RAW_SHA256:
            raise S2NormaliseError(
                "RiboAptamer raw SHA-256 does not match registry expectation"
            )
        raw_sha_before = digest

    s1_hash_before = _sha256_file(canonical_path)
    sidecar_hash_before = _sha256_file(sidecar_path)

    rules = load_normalisation_rules(rules_path)
    policy = load_riboaptamer_policy(policy_path)
    if policy.apply_approved_trims:
        raise S2NormaliseError("RiboAptamer S2 must not apply approved trims")
    if policy.group_inference_key != "disabled":
        raise S2NormaliseError(
            "RiboAptamer S2 must keep group-wise inference disabled"
        )

    canonical_rows = _read_corpus_csv(canonical_path)
    sidecar_rows = _read_sidecar_csv(sidecar_path)
    aligned_sidecar = _match_sidecar_one_to_one(canonical_rows, sidecar_rows)

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S2NormaliseError(
            f"S1 row count must be {expected_rows}; got {len(canonical_rows)}"
        )

    for index, row in enumerate(canonical_rows, start=1):
        if row["source_db"] != "riboaptamer":
            raise S2NormaliseError(f"row {index}: source_db must be riboaptamer")
        if expected_rows == EXPECTED_RIBOAPTAMER_ROWS:
            if row["source_dataset"] != EXPECTED_RIBOAPTAMER_SOURCE_DATASET:
                raise S2NormaliseError(
                    f"row {index}: source_dataset must be "
                    f"{EXPECTED_RIBOAPTAMER_SOURCE_DATASET}"
                )

    stats = RiboAptamerS2Stats()
    stats.s1_rows = len(canonical_rows)
    stats.source_metadata_rows = len(aligned_sidecar)
    stats.order_preserved = True
    stats.provenance_preserved = True
    stats.sequence_raw_unchanged = True
    stats.target_name_raw_unchanged = True
    stats.notes_unchanged = True
    stats.known_motifs_scanned = tuple(
        motif.name for motif in rules.known_non_core_motifs
    )
    stats.constant_region_reason = (
        "group-wise inference disabled for RiboAptamer in this run;"
        "known_motif_detection_only_not_applied"
    )

    normalised_rows: list[dict[str, str]] = []
    qc_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    row_results: list = []

    for s1_row, meta_row in zip(canonical_rows, aligned_sidecar, strict=True):
        result = normalise_riboaptamer_record(
            s1_row,
            meta_row,
            policy=policy,
            rules=rules,
        )
        if result.canonical["record_id"] != s1_row["record_id"]:
            stats.order_preserved = False
            raise S2NormaliseError("S2 altered record_id or row identity")
        if result.canonical["native_id"] != s1_row["native_id"]:
            raise S2NormaliseError("S2 altered native_id")
        if result.canonical["sequence_raw"] != s1_row["sequence_raw"]:
            stats.sequence_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter sequence_raw")
        if result.canonical["target_name_raw"] != s1_row["target_name_raw"]:
            stats.target_name_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter target_name_raw")
        if result.canonical["notes"] != s1_row["notes"]:
            stats.notes_unchanged = False
            raise S2NormaliseError("S2 must not alter notes")
        if result.canonical["source_db"] != s1_row["source_db"]:
            stats.provenance_preserved = False
            raise S2NormaliseError("S2 must not alter source_db")
        if result.canonical["source_dataset"] != s1_row["source_dataset"]:
            stats.provenance_preserved = False
            raise S2NormaliseError("S2 must not alter source_dataset")
        if result.canonical["pubmed_id"] != s1_row["pubmed_id"]:
            raise S2NormaliseError("S2 must not alter pubmed_id")
        if result.canonical["publication"] != s1_row["publication"]:
            raise S2NormaliseError("S2 must not alter publication")
        if result.canonical["sequence_core"] != result.canonical["sequence_full"]:
            raise S2NormaliseError(
                "RiboAptamer S2 must not apply trims; sequence_core must equal "
                "sequence_full"
            )
        if result.canonical["molecule_type"] != "RNA":
            raise S2NormaliseError(
                "RiboAptamer S2 molecule_type must remain RNA under the "
                "source contract"
            )
        if result.canonical["chemistry"] != "RNA":
            raise S2NormaliseError(
                "RiboAptamer S2 chemistry must remain RNA under the "
                "source contract"
            )
        length_full = result.canonical["sequence_length_full"]
        if length_full != "":
            if int(length_full) != len(result.canonical["sequence_full"]):
                raise S2NormaliseError(
                    "sequence_length_full must equal len(sequence_full)"
                )
            if int(result.canonical["sequence_length_core"]) != len(
                result.canonical["sequence_core"]
            ):
                raise S2NormaliseError(
                    "sequence_length_core must equal len(sequence_core)"
                )
        normalised_rows.append(result.canonical)
        qc_rows.append(result.qc)
        row_results.append(result)
        if riboaptamer_is_review_candidate(result.canonical["qc_flags"]):
            review_rows.append(result.qc)
        update_riboaptamer_stats_from_row(stats, result)

    stats.s2_rows = len(normalised_rows)
    stats.unique_record_ids = len({row["record_id"] for row in normalised_rows})
    stats.unique_native_ids = len({row["native_id"] for row in normalised_rows})
    stats.records_dropped = 0
    stats.records_parked = 0
    finalise_riboaptamer_truncation_regressions(stats)

    if expected_rows == EXPECTED_RIBOAPTAMER_ROWS:
        if stats.s2_rows != EXPECTED_RIBOAPTAMER_ROWS:
            raise S2NormaliseError(
                f"S2 must preserve {EXPECTED_RIBOAPTAMER_ROWS} rows; "
                f"got {stats.s2_rows}"
            )
        if stats.unique_record_ids != EXPECTED_RIBOAPTAMER_ROWS:
            raise S2NormaliseError("S2 record_id values are not unique")
        if stats.s1_rows - stats.s2_rows != 0:
            raise S2NormaliseError("S2 row disappearance must be 0")
        for key, expected in EXPECTED_RIBOAPTAMER_MOLECULE.items():
            got = stats.molecule_type_counts.get(key, 0)
            if got != expected:
                raise S2NormaliseError(
                    f"molecule_type {key} expected {expected}; got {got}"
                )
        for key, expected in EXPECTED_RIBOAPTAMER_CHEMISTRY.items():
            got = stats.chemistry_counts.get(key, 0)
            if got != expected:
                raise S2NormaliseError(
                    f"chemistry {key} expected {expected}; got {got}"
                )
        if stats.core_differs_from_full != 0:
            raise S2NormaliseError(
                "RiboAptamer S2 applied a trim; sequence_core must equal "
                "sequence_full"
            )
        nonempty_target = sum(
            1 for row in normalised_rows if row["target_name_raw"]
        )
        if nonempty_target:
            raise S2NormaliseError(
                "RiboAptamer S2 must not populate target_name_raw"
            )
        assert_riboaptamer_truncation_regressions(stats)

    known_motif_proposals = build_riboaptamer_known_motif_proposals(row_results)
    assert_riboaptamer_genuine_proposals(known_motif_proposals)

    stats.constant_region_proposals = len(known_motif_proposals)
    stats.groups_considered = 0
    stats.groups_meeting_min_size = 0
    stats.five_prime_proposals = sum(
        1 for row in known_motif_proposals if row["side"] == "five_prime"
    )
    stats.three_prime_proposals = sum(
        1 for row in known_motif_proposals if row["side"] == "three_prime"
    )
    stats.records_with_medium_confidence_proposal = 0
    stats.high_confidence_trims_applied = 0
    stats.applied_trims = 0
    for row in known_motif_proposals:
        source = row["proposal_source"]
        stats.proposal_source_counts[source] = (
            stats.proposal_source_counts.get(source, 0) + 1
        )

    for row in normalised_rows:
        if row["sequence_core"] != row["sequence_full"]:
            raise S2NormaliseError(
                "known-motif detections must not mutate sequence_core"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_normalised = output_dir / "riboaptamer_normalised.csv"
    out_qc = output_dir / "riboaptamer_s2_qc.csv"
    out_review = output_dir / "riboaptamer_s2_review_candidates.csv"
    out_proposals = output_dir / "detected_constants_riboaptamer.csv"
    out_report = output_dir / "riboaptamer_s2_report.md"

    write_corpus_csv_atomic(out_normalised, normalised_rows)
    write_csv_atomic(out_qc, RIBOAPTAMER_S2_QC_COLUMNS, qc_rows)
    write_csv_atomic(out_review, RIBOAPTAMER_S2_QC_COLUMNS, review_rows)
    write_csv_atomic(
        out_proposals, RIBOAPTAMER_CONSTANT_PROPOSAL_COLUMNS, known_motif_proposals
    )

    s1_hash_after = _sha256_file(canonical_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    inputs_unchanged = (
        s1_hash_before == s1_hash_after
        and sidecar_hash_before == sidecar_hash_after
    )
    if not inputs_unchanged:
        raise S2NormaliseError("S1 inputs were modified during S2 execution")

    raw_sha_after: str | None = None
    raw_sha_unchanged: bool | None = None
    if raw_sha_before is not None:
        digest = _sha256_file(raw_path)
        if digest != raw_sha_before:
            raise S2NormaliseError("RiboAptamer raw SHA changed during S2")
        raw_sha_after = digest
        raw_sha_unchanged = True

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "normalised": _sha256_file(out_normalised),
            "qc": _sha256_file(out_qc),
            "review": _sha256_file(out_review),
            "proposals": _sha256_file(out_proposals),
        }
        second = run_riboaptamer_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=policy_path,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["normalised"] == _sha256_file(second.output_normalised)
            and first_hashes["qc"] == _sha256_file(second.output_qc)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["proposals"] == _sha256_file(second.output_proposals)
        )
        if not deterministic_ok:
            raise S2NormaliseError(
                "S2 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S2RunResult(
        source_key="riboaptamer",
        stats=stats,
        output_normalised=out_normalised,
        output_qc=out_qc,
        output_review=out_review,
        output_proposals=out_proposals,
        output_report=out_report,
        s1_hash_before=s1_hash_before,
        s1_hash_after=s1_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        raw_sha256=raw_sha_after,
        raw_sha_unchanged=raw_sha_unchanged,
    )
    report_text = build_riboaptamer_s2_report(
        repo_root=repo_root,
        result=run_result,
        rules_path=rules_path,
        policy_path=policy_path,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in report_text:
        raise S2NormaliseError("S2 report must not contain absolute repository paths")
    _write_text_atomic(out_report, report_text)
    return run_result


def build_aptaindex_s2_report(
    *,
    repo_root: Path,
    result: S2RunResult,
    rules_path: Path,
    policy_path: Path,
) -> str:
    """Build an aggregate-only Markdown AptaIndex S2 report (no sequences)."""
    stats = result.stats
    if not isinstance(stats, AptaIndexS2Stats):
        raise S2NormaliseError("AptaIndex report requires AptaIndexS2Stats")
    full_min, full_med, full_max = summarise_aptaindex_lengths(
        stats.length_full_values
    )
    core_min, core_med, core_max = summarise_aptaindex_lengths(
        stats.length_core_values
    )
    scanned = (
        ", ".join(f"`{name}`" for name in stats.known_motifs_scanned) or "(none)"
    )
    lines = [
        "# AptaIndex S2 normalisation report",
        "",
        "Aggregate counts only. Restricted AptaIndex sequences are not included.",
        "",
        "## Reconciliation",
        "",
        f"- Source key: `aptaindex`",
        f"- Source dataset: `{EXPECTED_APTAINDEX_SOURCE_DATASET}`",
        f"- S1 canonical rows: `{stats.s1_rows}`",
        f"- Source-metadata rows: `{stats.source_metadata_rows}`",
        f"- S2 output rows: `{stats.s2_rows}`",
        f"- Records dropped: `{stats.records_dropped}`",
        f"- Records parked: `{stats.records_parked}`",
        f"- Unique record_id values: `{stats.unique_record_ids}`",
        f"- Unique native_id values: `{stats.unique_native_ids}`",
        f"- Row disappearance: `{stats.s1_rows - stats.s2_rows}`",
        f"- S1 row order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        f"- S1 provenance preserved: "
        f"`{'pass' if stats.provenance_preserved else 'fail'}`",
        f"- sequence_raw unchanged: "
        f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
        f"- target_name_raw unchanged: "
        f"`{'pass' if stats.target_name_raw_unchanged else 'fail'}`",
        f"- notes unchanged: `{'pass' if stats.notes_unchanged else 'fail'}`",
        f"- Shared rules: `{_relative_display(rules_path, repo_root)}`",
        f"- Source policy: `{_relative_display(policy_path, repo_root)}`",
        "",
        "## Sequence status",
        "",
        f"- Sequence missing: `{stats.missing_sequence_rows}`",
        f"- Peptide molecule rows (parser not applicable): `{stats.peptide_rows}`",
        f"- Non-empty nucleic-acid rows: `{stats.nonempty_nucleic_acid_rows}`",
        "",
        "## Parser coverage",
        "",
        "Full-consumption success requires that the entire source Sequence is",
        "accounted for by explicitly supported terminal, token, linkage,",
        "optional terminal-phosphate, allowlisted 5′ phosphate/thiol",
        "decoration, token-separating whitespace, uniform-family omitted",
        "prefix inheritance, or display-hyphen separators. Unknown material",
        "fails closed. No partial nucleotide sequence is emitted for failed",
        "parses. Syntax events are formatting/tokenisation provenance, not",
        "chemistry claims.",
        "",
        f"- Successful complete nucleic-acid parses: `{stats.successful_parses}`",
        f"- Unsupported/unparseable nucleic-acid rows: "
        f"`{stats.unsupported_nucleic_parses}`",
        f"- Inherited-prefix rows: `{stats.inherited_prefix_rows}`",
        "",
        "### Parser status",
        "",
    ]
    for name, count in _count_sorted(stats.parser_status_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Parser reason category", ""])
    for name, count in _count_sorted(stats.parser_reason_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Parser syntax events", ""])
    syntax_counts = stats.parser_syntax_event_counts
    if syntax_counts:
        for name, count in _count_sorted(syntax_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Source Type distribution",
            "",
            "Counts are read from the S1 sidecar (`aptaindex_type`). They are",
            "not hard-coded acceptance criteria.",
            "",
        ]
    )
    for name, count in _count_sorted(stats.source_type_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Type × token-family (successful parses)",
            "",
        ]
    )
    for name, count in _count_sorted(stats.type_token_family_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Mapping class", ""])
    for name, count in _count_sorted(stats.mapping_class_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Canonical molecule_type", ""])
    for name, count in _count_sorted(stats.molecule_type_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Canonical chemistry", ""])
    for name, count in _count_sorted(stats.chemistry_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### alphabet_as_reported", ""])
    for name, count in _count_sorted(stats.alphabet_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "Non-empty nucleic-acid chemical notation uses",
            "`alphabet_as_reported = chemical_notation` (governing-plan DECIDED",
            "value). Missing Sequence uses the shared `missing` contract.",
            "Source-declared peptide rows leave `alphabet_as_reported` empty",
            "because the source Sequence is amino-acid notation, not nucleotide",
            "chemical notation.",
            "",
            "## T / U",
            "",
            "Counts below are from successfully parsed nucleic-acid base strings",
            "before T→U conversion.",
            "",
            f"- T-only parsed representations: `{stats.parsed_t_only}`",
            f"- U-only parsed representations: `{stats.parsed_u_only}`",
            f"- Neither T nor U: `{stats.parsed_neither_t_u}`",
            f"- Mixed T+U: `{stats.mixed_t_u_count}`",
            f"- `t_to_u_applied=true`: `{stats.t_to_u_count}`",
            "",
            "## Lengths (successfully parsed / normalised nucleic-acid rows)",
            "",
            "Lengths are `len(sequence_full)` / `len(sequence_core)` only.",
            "Source Molecular Weight is not used. Length is not an S2 reject.",
            "",
            f"- sequence_length_full min/median/max: `{full_min}` / `{full_med}` / `{full_max}`",
            f"- sequence_length_core min/median/max: `{core_min}` / `{core_med}` / `{core_max}`",
            "",
            "### sequence_length_full buckets",
            "",
        ]
    )
    for name, count in _count_sorted(stats.length_full_buckets):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### sequence_length_core buckets", ""])
    for name, count in _count_sorted(stats.length_core_buckets):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Trimming",
            "",
            "AptaIndex has no source-specific library design in this milestone.",
            "Group-wise constant-region inference is disabled. Known-motif",
            "detections are proposals only and are not applied.",
            "",
            f"- Known motifs scanned: {scanned}",
            f"- No constants detected: `{stats.no_constants_detected_count}`",
            f"- Known-motif detection rows: `{stats.known_motif_detection_count}`",
            f"- Known-motif proposals (unapplied): `{stats.constant_region_proposals}`",
            f"- Medium-confidence group inference proposals: "
            f"`{stats.medium_confidence_inference_count}`",
            f"- Trim-to-short outcomes: `{stats.trim_to_short_count}`",
            f"- sequence_core differs from sequence_full: `{stats.core_differs_from_full}`",
            f"- Applied trims: `{stats.applied_trims}`",
            f"- Constant-region reason: `{stats.constant_region_reason}`",
            "",
            "### construct_scope",
            "",
        ]
    )
    for name, count in _count_sorted(stats.construct_scope_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_status", ""])
    for name, count in _count_sorted(stats.trim_status_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Other diagnostics",
            "",
            f"- L-nucleotide syntax: `{stats.l_nucleotide_count}`",
            f"- Inosine base: `{stats.inosine_count}`",
            f"- Phosphorothioate linkage: `{stats.linkage_phosphorothioate_count}`",
            f"- Mixed internucleotide linkage: `{stats.linkage_mixed_count}`",
            f"- Source Type / token disagreement: "
            f"`{stats.source_type_disagreement_count}`",
            f"- Unsupported/new source Type: `{stats.source_type_unsupported_count}`",
            f"- Review-candidate rows: `{stats.review_candidate_rows}`",
            "",
            "### qc_flags",
            "",
        ]
    )
    for name, count in _count_sorted(stats.qc_flag_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Integrity",
            "",
            f"- Deterministic rerun: "
            f"`{'pass' if result.deterministic_rerun_ok else ('not_run' if result.deterministic_rerun_ok is None else 'fail')}`",
            f"- S1 inputs unchanged: `{'pass' if result.inputs_unchanged else 'fail'}`",
            f"- S1 canonical hash before: `{result.s1_hash_before}`",
            f"- S1 canonical hash after: `{result.s1_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            (
                f"- Raw SHA-256: `{result.raw_sha256}`"
                if result.raw_sha256
                else "- Raw SHA-256: `not_checked`"
            ),
            "",
            "## Outputs",
            "",
            f"- Normalised: "
            f"`{_relative_display(result.output_normalised, repo_root)}`",
            f"- QC: `{_relative_display(result.output_qc, repo_root)}`",
            f"- Review candidates: "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Detected constants / proposals: "
            f"`{_relative_display(result.output_proposals, repo_root)}`",
            f"- Report: `{_relative_display(result.output_report, repo_root)}`",
            "",
            "## Stage boundary",
            "",
            "AptaIndex S2 chemical-notation parsing and sequence normalisation",
            "only.",
            "",
            "- No record was rejected or parked.",
            "- ssDNA was not parked.",
            "- Peptide records were retained, not rejected.",
            "- No target canonicalisation was performed.",
            "- No affinity/evidence decision was performed.",
            "- No leakage, clustering, balancing or partitioning was performed.",
            "- S3 has not started.",
            "- CHECKPOINT-1 was not generated.",
            "- Known-motif detections were not applied as trims.",
            "- group-wise inference disabled for AptaIndex in this run.",
            "",
        ]
    )
    return "\n".join(lines)


def run_aptaindex_s2(
    *,
    repo_root: Path,
    input_dir: Path,
    output_dir: Path,
    rules_path: Path,
    policy_path: Path,
    expected_rows: int | None = EXPECTED_APTAINDEX_ROWS,
    check_deterministic_rerun: bool = False,
) -> S2RunResult:
    """Execute AptaIndex S2 normalisation."""
    repo_root = repo_root.resolve()
    input_dir = input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    input_dir = input_dir.resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    rules_path = (
        rules_path if rules_path.is_absolute() else (repo_root / rules_path)
    ).resolve()
    policy_path = (
        policy_path if policy_path.is_absolute() else (repo_root / policy_path)
    ).resolve()

    canonical_path = input_dir / "aptaindex_extracted.csv"
    sidecar_path = input_dir / "aptaindex_source_metadata.csv"
    if not canonical_path.is_file():
        raise S2NormaliseError(f"Missing S1 canonical input: {canonical_path.name}")
    if not sidecar_path.is_file():
        raise S2NormaliseError(f"Missing S1 sidecar input: {sidecar_path.name}")

    raw_path = (
        repo_root / "data" / "raw" / "AptaIndex" / "aptamers-export-2026-07-22.csv"
    )
    raw_sha_before: str | None = None
    if expected_rows == EXPECTED_APTAINDEX_ROWS:
        if not raw_path.is_file():
            raise S2NormaliseError("Missing registered AptaIndex raw file")
        digest = _sha256_file(raw_path)
        if digest != EXPECTED_APTAINDEX_RAW_SHA256:
            raise S2NormaliseError(
                "AptaIndex raw SHA-256 does not match registry expectation"
            )
        raw_sha_before = digest

    s1_hash_before = _sha256_file(canonical_path)
    sidecar_hash_before = _sha256_file(sidecar_path)

    rules = load_normalisation_rules(rules_path)
    policy = load_aptaindex_policy(policy_path)
    if policy.apply_approved_trims:
        raise S2NormaliseError("AptaIndex S2 must not apply approved trims")
    if policy.group_inference_key != "disabled":
        raise S2NormaliseError(
            "AptaIndex S2 must keep group-wise inference disabled"
        )

    canonical_rows = _read_corpus_csv(canonical_path)
    sidecar_rows = _read_sidecar_csv(sidecar_path)
    aligned_sidecar = _match_sidecar_one_to_one(canonical_rows, sidecar_rows)

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S2NormaliseError(
            f"S1 row count must be {expected_rows}; got {len(canonical_rows)}"
        )

    for index, row in enumerate(canonical_rows, start=1):
        if row["source_db"] != "aptaindex":
            raise S2NormaliseError(f"row {index}: source_db must be aptaindex")
        if expected_rows == EXPECTED_APTAINDEX_ROWS:
            if row["source_dataset"] != EXPECTED_APTAINDEX_SOURCE_DATASET:
                raise S2NormaliseError(
                    f"row {index}: source_dataset must be "
                    f"{EXPECTED_APTAINDEX_SOURCE_DATASET}"
                )

    stats = AptaIndexS2Stats()
    stats.s1_rows = len(canonical_rows)
    stats.source_metadata_rows = len(aligned_sidecar)
    stats.order_preserved = True
    stats.provenance_preserved = True
    stats.sequence_raw_unchanged = True
    stats.target_name_raw_unchanged = True
    stats.notes_unchanged = True
    stats.known_motifs_scanned = tuple(
        motif.name for motif in rules.known_non_core_motifs
    )
    stats.constant_region_reason = (
        "group-wise inference disabled for AptaIndex in this run; "
        "known_motif_detection_only_not_applied"
    )

    normalised_rows: list[dict[str, str]] = []
    qc_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    row_results: list = []

    for s1_row, meta_row in zip(canonical_rows, aligned_sidecar, strict=True):
        result = normalise_aptaindex_record(
            s1_row,
            meta_row,
            policy=policy,
            rules=rules,
        )
        if result.canonical["record_id"] != s1_row["record_id"]:
            stats.order_preserved = False
            raise S2NormaliseError("S2 altered record_id or row identity")
        if result.canonical["native_id"] != s1_row["native_id"]:
            raise S2NormaliseError("S2 altered native_id")
        if result.canonical["sequence_raw"] != s1_row["sequence_raw"]:
            stats.sequence_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter sequence_raw")
        if result.canonical["target_name_raw"] != s1_row["target_name_raw"]:
            stats.target_name_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter target_name_raw")
        if result.canonical["notes"] != s1_row["notes"]:
            stats.notes_unchanged = False
            raise S2NormaliseError("S2 must not alter notes")
        if result.canonical["source_db"] != s1_row["source_db"]:
            stats.provenance_preserved = False
            raise S2NormaliseError("S2 must not alter source_db")
        if result.canonical["source_dataset"] != s1_row["source_dataset"]:
            stats.provenance_preserved = False
            raise S2NormaliseError("S2 must not alter source_dataset")
        if result.canonical["sequence_core"] != result.canonical["sequence_full"]:
            raise S2NormaliseError(
                "AptaIndex S2 must not apply trims; sequence_core must equal "
                "sequence_full"
            )
        for field in (
            "target_name",
            "target_uniprot",
            "target_type",
            "binding_evidence_type",
            "binding_evidence_score",
            "affinity_value",
            "affinity_unit",
            "affinity_type",
            "cluster_id",
            "partition",
        ):
            if result.canonical[field] != "":
                raise S2NormaliseError(
                    f"AptaIndex S2 must not populate later-stage field {field}"
                )
        length_full = result.canonical["sequence_length_full"]
        if length_full != "":
            if int(length_full) != len(result.canonical["sequence_full"]):
                raise S2NormaliseError(
                    "sequence_length_full must equal len(sequence_full)"
                )
            if int(result.canonical["sequence_length_core"]) != len(
                result.canonical["sequence_core"]
            ):
                raise S2NormaliseError(
                    "sequence_length_core must equal len(sequence_core)"
                )
        if (
            result.qc.get("parser_status") != "success"
            and result.canonical["sequence_full"] != ""
        ):
            raise S2NormaliseError(
                "parser failures must not emit a nucleotide sequence_full"
            )
        normalised_rows.append(result.canonical)
        qc_rows.append(result.qc)
        row_results.append(result)
        if aptaindex_is_review_candidate(result.canonical["qc_flags"]):
            review_rows.append(result.qc)
        update_aptaindex_stats_from_row(stats, result)

    stats.s2_rows = len(normalised_rows)
    stats.unique_record_ids = len({row["record_id"] for row in normalised_rows})
    stats.unique_native_ids = len({row["native_id"] for row in normalised_rows})
    stats.records_dropped = 0
    stats.records_parked = 0

    if expected_rows == EXPECTED_APTAINDEX_ROWS:
        if stats.s2_rows != EXPECTED_APTAINDEX_ROWS:
            raise S2NormaliseError(
                f"S2 must preserve {EXPECTED_APTAINDEX_ROWS} rows; "
                f"got {stats.s2_rows}"
            )
        if stats.unique_record_ids != EXPECTED_APTAINDEX_ROWS:
            raise S2NormaliseError("S2 record_id values are not unique")
        if stats.unique_native_ids != EXPECTED_APTAINDEX_ROWS:
            raise S2NormaliseError("S2 native_id values are not unique")
        if stats.s1_rows - stats.s2_rows != 0:
            raise S2NormaliseError("S2 row disappearance must be 0")
        if stats.core_differs_from_full != 0:
            raise S2NormaliseError(
                "AptaIndex S2 applied a trim; sequence_core must equal "
                "sequence_full"
            )
        s1_ids = [row["record_id"] for row in canonical_rows]
        s2_ids = [row["record_id"] for row in normalised_rows]
        if s1_ids != s2_ids:
            raise S2NormaliseError("S2 record_id order does not match S1")
        s1_native = [row["native_id"] for row in canonical_rows]
        s2_native = [row["native_id"] for row in normalised_rows]
        if s1_native != s2_native:
            raise S2NormaliseError("S2 native_id order does not match S1")

    known_motif_proposals = build_aptaindex_known_motif_proposals(row_results)
    assert_aptaindex_genuine_proposals(known_motif_proposals)

    stats.constant_region_proposals = len(known_motif_proposals)
    stats.groups_considered = 0
    stats.groups_meeting_min_size = 0
    stats.five_prime_proposals = sum(
        1 for row in known_motif_proposals if row["side"] == "five_prime"
    )
    stats.three_prime_proposals = sum(
        1 for row in known_motif_proposals if row["side"] == "three_prime"
    )
    stats.records_with_medium_confidence_proposal = 0
    stats.high_confidence_trims_applied = 0
    stats.applied_trims = 0
    for row in known_motif_proposals:
        source = row["proposal_source"]
        stats.proposal_source_counts[source] = (
            stats.proposal_source_counts.get(source, 0) + 1
        )

    for row in normalised_rows:
        if row["sequence_core"] != row["sequence_full"]:
            raise S2NormaliseError(
                "known-motif detections must not mutate sequence_core"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_normalised = output_dir / "aptaindex_normalised.csv"
    out_qc = output_dir / "aptaindex_s2_qc.csv"
    out_review = output_dir / "aptaindex_s2_review_candidates.csv"
    out_proposals = output_dir / "detected_constants_aptaindex.csv"
    out_report = output_dir / "aptaindex_s2_report.md"

    write_corpus_csv_atomic(
        out_normalised, normalised_rows, quoting=csv.QUOTE_ALL
    )
    write_csv_atomic(out_qc, APTAINDEX_S2_QC_COLUMNS, qc_rows)
    write_csv_atomic(out_review, APTAINDEX_S2_QC_COLUMNS, review_rows)
    write_csv_atomic(
        out_proposals, APTAINDEX_CONSTANT_PROPOSAL_COLUMNS, known_motif_proposals
    )

    s1_hash_after = _sha256_file(canonical_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    inputs_unchanged = (
        s1_hash_before == s1_hash_after
        and sidecar_hash_before == sidecar_hash_after
    )
    if not inputs_unchanged:
        raise S2NormaliseError("S1 inputs were modified during S2 execution")

    raw_sha_after: str | None = None
    raw_sha_unchanged: bool | None = None
    if raw_sha_before is not None:
        digest = _sha256_file(raw_path)
        if digest != raw_sha_before:
            raise S2NormaliseError("AptaIndex raw SHA changed during S2")
        raw_sha_after = digest
        raw_sha_unchanged = True

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "normalised": _sha256_file(out_normalised),
            "qc": _sha256_file(out_qc),
            "review": _sha256_file(out_review),
            "proposals": _sha256_file(out_proposals),
        }
        second = run_aptaindex_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=policy_path,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["normalised"] == _sha256_file(second.output_normalised)
            and first_hashes["qc"] == _sha256_file(second.output_qc)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["proposals"] == _sha256_file(second.output_proposals)
        )
        if not deterministic_ok:
            raise S2NormaliseError(
                "S2 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S2RunResult(
        source_key="aptaindex",
        stats=stats,
        output_normalised=out_normalised,
        output_qc=out_qc,
        output_review=out_review,
        output_proposals=out_proposals,
        output_report=out_report,
        s1_hash_before=s1_hash_before,
        s1_hash_after=s1_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        raw_sha256=raw_sha_after,
        raw_sha_unchanged=raw_sha_unchanged,
    )
    report_text = build_aptaindex_s2_report(
        repo_root=repo_root,
        result=run_result,
        rules_path=rules_path,
        policy_path=policy_path,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in report_text:
        raise S2NormaliseError("S2 report must not contain absolute repository paths")
    _write_text_atomic(out_report, report_text)
    return run_result


def build_ena_s2_report(
    *,
    repo_root: Path,
    result: S2RunResult,
    rules_path: Path,
    policy_path: Path,
    diagnostics: Any | None = None,
) -> str:
    """Build an aggregate-only Markdown ENA S2 report (no sequences or motifs)."""
    stats = result.stats
    if not isinstance(stats, EnaS2Stats):
        raise S2NormaliseError("ENA report requires EnaS2Stats")
    full_min, full_med, full_max = summarise_ena_lengths(stats.length_full_values)
    core_min, core_med, core_max = summarise_ena_lengths(stats.length_core_values)
    scanned = ", ".join(f"`{name}`" for name in stats.known_motifs_scanned) or "(none)"
    lines = [
        "# ENA S2 normalisation report",
        "",
        "## Reconciliation",
        "",
        f"- Source key: `ena`",
        f"- Source dataset: `{EXPECTED_ENA_SOURCE_DATASET}`",
        f"- S1 canonical rows: `{stats.s1_rows}`",
        f"- Source-metadata rows: `{stats.source_metadata_rows}`",
        f"- S2 output rows: `{stats.s2_rows}`",
        f"- Records dropped: `{stats.records_dropped}`",
        f"- Records parked: `{stats.records_parked}`",
        f"- Unique record_id values: `{stats.unique_record_ids}`",
        f"- Unique native_id values: `{stats.unique_native_ids}`",
        f"- Row disappearance: `{stats.s1_rows - stats.s2_rows}`",
        f"- S1 row order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        f"- S1 provenance preserved: "
        f"`{'pass' if stats.provenance_preserved else 'fail'}`",
        f"- sequence_raw unchanged: "
        f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
        f"- target_name_raw unchanged: "
        f"`{'pass' if stats.target_name_raw_unchanged else 'fail'}`",
        f"- Missing sequence rows: `{stats.missing_sequence_rows}`",
        f"- Nonempty sequence rows: `{stats.nonempty_sequence_rows}`",
        f"- Shared rules: `{_relative_display(rules_path, repo_root)}`",
        f"- Source policy: `{_relative_display(policy_path, repo_root)}`",
        "",
        "## Molecule / chemistry",
        "",
        "Experimental molecule type is fixed by the ENA source contract",
        "(`molecule_type=RNA`, `chemistry=RNA`). These 679 records are RNA",
        "aptamers. T alphabet does not mean ssDNA. Molecule type is never",
        "inferred from sequence letters. T→U on a T-encoded reviewed",
        "sequence is computational transcription of an RNA record.",
        "",
        "### Canonical molecule_type",
        "",
    ]
    for name, count in _count_sorted(stats.molecule_type_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Canonical chemistry", ""])
    for name, count in _count_sorted(stats.chemistry_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Reported alphabet",
            "",
            "Shared alphabet vocabulary is `RNA` / `DNA_T` / `mixed_T_U` /",
            "`ambiguous` / `invalid` (not a separate `RNA_U` token).",
            "",
        ]
    )
    for name, count in _count_sorted(stats.alphabet_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Computational transcription",
            "",
            f"- total `t_to_u_applied=true`: `{stats.t_to_u_count}`",
            "",
        ]
    )
    if stats.t_to_u_by_molecule:
        for name, count in _count_sorted(stats.t_to_u_by_molecule):
            lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Display cleaning",
            "",
        ]
    )
    if stats.transformation_counts:
        for name, count in _count_sorted(stats.transformation_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## QC",
            "",
            f"- Invalid character rows: `{stats.invalid_character_count}`",
            f"- Alignment-gap rows: `{stats.alignment_gaps_count}`",
            f"- Ambiguous base rows: `{stats.ambiguous_base_count}`",
            f"- Mixed T/U rows: `{stats.mixed_t_u_count}`",
            f"- Core below minimum length: `{stats.core_below_min_count}`",
            f"- Core above maximum length: `{stats.core_above_max_count}`",
            f"- Source vs S2 length mismatches (diagnostic only): "
            f"`{stats.length_mismatch_count}`",
            f"- Rows with any QC flag: `{stats.rows_with_any_qc_flag}`",
            f"- Rows with multiple QC flags: `{stats.rows_with_multiple_qc_flags}`",
            f"- Review-candidate rows: `{stats.review_candidate_rows}`",
            "",
        ]
    )
    for name, count in _count_sorted(stats.qc_flag_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Review reasons", ""])
    if stats.review_reason_counts:
        for name, count in _count_sorted(stats.review_reason_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## Length",
            "",
            "Lengths are computed from the shared normalised representation,",
            "not from the source `sequence_length` field. Source length is",
            "compared as a diagnostic only and is not repaired. These buckets",
            "are descriptive at S2; they do not filter records.",
            "",
            f"- sequence_length_full min / median / max: "
            f"`{full_min}` / `{full_med}` / `{full_max}`",
            f"- sequence_length_core min / median / max: "
            f"`{core_min}` / `{core_med}` / `{core_max}`",
            "",
            "### sequence_length_full buckets",
            "",
        ]
    )
    for name, count in _count_sorted(stats.length_full_buckets):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### sequence_length_core buckets", ""])
    for name, count in _count_sorted(stats.length_core_buckets):
        lines.append(f"- `{name}`: `{count}`")
    if stats.core_differs_from_full == 0:
        lines.extend(
            [
                "",
                "Full and core length distributions are identical because no",
                "trim was applied (`sequence_core == sequence_full`).",
            ]
        )
    lines.extend(
        [
            "",
            "## Construct / trim state",
            "",
            "Known-motif detection and group-consensus inference are recorded",
            "as proposals only. Detection does not authorise trimming at S2.",
            "Source `automatic_concern_flags=t7_promoter` and",
            "`sequence_quality_status=promoter_or_template_requires_review`",
            "are provenance, not trim authorisation.",
            "",
            "### construct_scope",
            "",
        ]
    )
    for name, count in _count_sorted(stats.construct_scope_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_status", ""])
    for name, count in _count_sorted(stats.trim_status_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_confidence", ""])
    for name, count in _count_sorted(stats.trim_confidence_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Experiment groups",
            "",
            "Primary grouping uses sidecar `experiment_group_id` only.",
            "Supporting `experiment_group_ids` are provenance and are not",
            "the grouping contract. Near-duplicate family IDs are not used",
            "as constant-inference groups. Canonical `experiment_group_id`",
            "remains empty under the live S2 schema.",
            "",
            f"- Primary experiment groups observed: `{stats.primary_experiment_groups}`",
            f"- Rows with populated primary group: "
            f"`{stats.populated_primary_experiment_groups}`",
            f"- Supporting group IDs after expansion (diagnostic only): "
            f"`{stats.supporting_group_ids_expanded}`",
            f"- Groups considered for inference: `{stats.groups_considered}`",
            f"- Groups meeting minimum size: `{stats.groups_meeting_min_size}`",
            f"- Groups skipped for insufficient size: `{stats.groups_below_min_size}`",
            f"- Records participating in eligible groups: "
            f"`{stats.records_in_eligible_groups}`",
            f"- Group-size histogram: `{dict(stats.group_size_histogram)}`",
            "",
            "## Constant-region inference",
            "",
            "Grouping uses shared mode `experiment_group_id` consumed from",
            "the S1 sidecar. Newly inferred medium-confidence motifs are",
            "proposals only and were not applied.",
            "`config/constant_regions.yaml` was not modified.",
            "",
            f"- Approved known motifs scanned: {scanned}",
            f"- Records with known-motif detection: "
            f"`{stats.known_motif_detection_count}`",
            f"- 5′ group-consensus proposals: `{stats.five_prime_proposals}`",
            f"- 3′ group-consensus proposals: `{stats.three_prime_proposals}`",
            f"- Records associated with medium-confidence proposals: "
            f"`{stats.records_with_medium_confidence_proposal}`",
            f"- Previously approved high-confidence trims applied: "
            f"`{stats.high_confidence_trims_applied}`",
            f"- Records actually trimmed: `{stats.applied_trims}`",
            f"- Genuine proposal rows: `{stats.constant_region_proposals}`",
            f"- Rows where sequence_core != sequence_full: "
            f"`{stats.core_differs_from_full}`",
            f"- Reason: `{stats.constant_region_reason}`",
            "",
            "### proposal sources",
            "",
        ]
    )
    if stats.proposal_source_counts:
        for name, count in _count_sorted(stats.proposal_source_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    if diagnostics is not None:
        lines.extend(
            [
                "",
                "### Tier-2 consensus diagnostics",
                "",
                f"- Groups total: `{diagnostics.groups_total}`",
                f"- Groups below min size: `{diagnostics.groups_below_min_size}`",
                f"- Qualifying 5′ groups: `{diagnostics.groups_qualifying_prefix}`",
                f"- Qualifying 3′ groups: `{diagnostics.groups_qualifying_suffix}`",
                f"- No qualifying 5′: `{diagnostics.groups_no_qualifying_prefix}`",
                f"- No qualifying 3′: `{diagnostics.groups_no_qualifying_suffix}`",
                f"- Skipped missing grouping evidence: "
                f"`{diagnostics.skipped_missing_group}`",
                f"- Group-size histogram: `{dict(diagnostics.group_size_histogram)}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Source promoter/template provenance",
            "",
            "Prior source-review promoter/template flags are retained in the",
            "sidecar and exposed as review-candidate reasons. They are not",
            "rejections and not automatic trims. Shared known-motif detection",
            "is an independent evidence channel.",
            "",
            f"- Source promoter/template concern rows: "
            f"`{stats.source_promoter_or_template_count}`",
            f"- Source T7 concern rows: `{stats.source_t7_concern_count}`",
            f"- Overlap source concern and shared known motif: "
            f"`{stats.overlap_source_and_shared_motif_count}`",
            f"- Source concern without shared motif: "
            f"`{stats.source_concern_without_shared_motif_count}`",
            f"- Shared motif without source concern: "
            f"`{stats.shared_motif_without_source_concern_count}`",
            "",
            "## Source correction and family provenance",
            "",
            "Previously applied ENA manual-review sequence corrections remain",
            "sidecar provenance. They are not new CHECKPOINT decisions.",
            "Near-duplicate families are preserved and are not used as",
            "constant-inference groups.",
            "",
            f"- Sidecar sequence_corrected_applied=1: "
            f"`{stats.sequence_corrections_applied}`",
            f"- Original blank family IDs: `{stats.blank_source_family_ids}`",
            f"- Original nonblank family IDs: `{stats.nonblank_source_family_ids}`",
            f"- Materialised singleton family IDs: "
            f"`{stats.materialised_singleton_family_ids}`",
            "",
            "## Duplicate diagnostic (no deduplication performed)",
            "",
            "diagnostic only — no deduplication performed. Formal",
            "679-versus-676 reconciliation remains CHECKPOINT-1.",
            "",
            f"- Distinct sequence_full values with count>1: "
            f"`{stats.exact_duplicate_sequence_full_values}`",
            f"- Records participating in those sequence_full values: "
            f"`{stats.records_in_exact_duplicate_sequence_full}`",
            f"- Distinct sequence_core values with count>1: "
            f"`{stats.exact_duplicate_sequence_core_values}`",
            f"- Records participating in those sequence_core values: "
            f"`{stats.records_in_exact_duplicate_sequence_core}`",
            "",
            "## Invariants",
            "",
            f"- sequence_raw unchanged: "
            f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
            f"- Records retained: `{stats.s2_rows}`",
            f"- Provenance unchanged: "
            f"`{'pass' if stats.provenance_preserved else 'fail'}`",
            "- S4 target/evidence/affinity/PDB fields remain blank",
            "- Canonical target/UniProt/family/Pfam remain blank",
            "- Binding evidence was not mapped onto E1–E5",
            "- No leakage, clustering, balancing or partitioning",
            (
                f"- Raw input hash unchanged: "
                f"`{'pass' if result.raw_sha_unchanged else 'fail'}`"
                if result.raw_sha_unchanged is not None
                else "- Raw input hash unchanged: `not_checked`"
            ),
            f"- S1 inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            "",
            f"- S1 canonical hash before: `{result.s1_hash_before}`",
            f"- S1 canonical hash after: `{result.s1_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            (
                f"- Raw SHA-256: `{result.raw_sha256}`"
                if result.raw_sha256
                else "- Raw SHA-256: `not_checked`"
            ),
            "",
            "## Outputs",
            "",
            f"- Normalised: "
            f"`{_relative_display(result.output_normalised, repo_root)}`",
            f"- QC: `{_relative_display(result.output_qc, repo_root)}`",
            f"- Review candidates: "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Constant-region proposals: "
            f"`{_relative_display(result.output_proposals, repo_root)}`",
        ]
    )
    if result.output_rule_membership is not None:
        lines.append(
            f"- Group-consensus membership: "
            f"`{_relative_display(result.output_rule_membership, repo_root)}`"
        )
    lines.extend(
        [
            f"- Report: `{_relative_display(result.output_report, repo_root)}`",
            "",
            "## Stage boundary",
            "",
            "ENA S2 sequence normalisation and constant-region proposal only.",
            "",
            "- No record was rejected or parked.",
            "- No target canonicalisation or aliasing was performed.",
            "- No affinity/evidence decision was performed.",
            "- No leakage, clustering, balancing or partitioning was performed.",
            "- S3 has not started.",
            "- CHECKPOINT-1 has not been generated.",
            "- Newly inferred medium-confidence motifs were not applied.",
            "- Known-motif detections were not applied as trims.",
            "- 679-versus-676 deduplication was not performed.",
            "- Global S4 has not been run.",
            "",
        ]
    )
    return "\n".join(lines)


def run_ena_s2(
    *,
    repo_root: Path,
    input_dir: Path,
    output_dir: Path,
    rules_path: Path,
    policy_path: Path,
    expected_rows: int | None = EXPECTED_ENA_ROWS,
    check_deterministic_rerun: bool = False,
) -> S2RunResult:
    """Execute ENA S2 normalisation."""
    assert_no_legacy_ena_normaliser_import()
    repo_root = repo_root.resolve()
    input_dir = input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    input_dir = input_dir.resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    rules_path = (
        rules_path if rules_path.is_absolute() else (repo_root / rules_path)
    ).resolve()
    policy_path = (
        policy_path if policy_path.is_absolute() else (repo_root / policy_path)
    ).resolve()

    canonical_path = input_dir / "ena_extracted.csv"
    sidecar_path = input_dir / "ena_source_metadata.csv"
    if not canonical_path.is_file():
        raise S2NormaliseError(f"Missing S1 canonical input: {canonical_path.name}")
    if not sidecar_path.is_file():
        raise S2NormaliseError(f"Missing S1 sidecar input: {sidecar_path.name}")

    raw_path = (
        repo_root / "data" / "raw" / "ENA" / "review_v2"
        / "ena_selected_after_manual_review.csv"
    )
    raw_sha_before: str | None = None
    if expected_rows == EXPECTED_ENA_ROWS:
        if not raw_path.is_file():
            raise S2NormaliseError("Missing registered ENA raw file")
        digest = _sha256_file(raw_path)
        if digest != EXPECTED_ENA_RAW_SHA256:
            raise S2NormaliseError(
                "ENA raw SHA-256 does not match registry expectation"
            )
        raw_sha_before = digest

    s1_hash_before = _sha256_file(canonical_path)
    sidecar_hash_before = _sha256_file(sidecar_path)

    rules = load_normalisation_rules(rules_path)
    policy = load_ena_policy(policy_path)
    if policy.apply_approved_trims or not policy.do_not_apply_inferred_trims:
        raise S2NormaliseError("ENA S2 must not apply approved or inferred trims")

    canonical_rows = _read_corpus_csv(canonical_path)
    sidecar_rows = _read_sidecar_csv(sidecar_path)
    aligned_sidecar = _match_sidecar_one_to_one(canonical_rows, sidecar_rows)

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S2NormaliseError(
            f"S1 row count must be {expected_rows}; got {len(canonical_rows)}"
        )

    for index, row in enumerate(canonical_rows, start=1):
        if row["source_db"] != "ena":
            raise S2NormaliseError(f"row {index}: source_db must be ena")
        if expected_rows == EXPECTED_ENA_ROWS:
            if row["source_dataset"] != EXPECTED_ENA_SOURCE_DATASET:
                raise S2NormaliseError(
                    f"row {index}: source_dataset must be "
                    f"{EXPECTED_ENA_SOURCE_DATASET}"
                )
        if row.get("experiment_group_id"):
            raise S2NormaliseError(
                "ENA S2 must not find canonical experiment_group_id populated"
            )
        if row.get("near_duplicate_family_id"):
            raise S2NormaliseError(
                "ENA S2 must not find canonical near_duplicate_family_id populated"
            )

    stats = EnaS2Stats()
    stats.s1_rows = len(canonical_rows)
    stats.source_metadata_rows = len(aligned_sidecar)
    stats.order_preserved = True
    stats.provenance_preserved = True
    stats.sequence_raw_unchanged = True
    stats.target_name_raw_unchanged = True
    stats.known_motifs_scanned = tuple(
        motif.name for motif in rules.known_non_core_motifs
    )

    normalised_rows: list[dict[str, str]] = []
    qc_rows: list[dict[str, str]] = []
    row_results: list = []
    primary_groups: dict[str, list[str]] = {}
    supporting_ids: set[str] = set()
    blank_family = 0
    nonblank_family = 0
    singleton_family = 0

    for s1_row, meta_row in zip(canonical_rows, aligned_sidecar, strict=True):
        result = normalise_ena_record(
            s1_row,
            meta_row,
            policy=policy,
            rules=rules,
        )
        if result.canonical["record_id"] != s1_row["record_id"]:
            stats.order_preserved = False
            raise S2NormaliseError("S2 altered record_id or row identity")
        if result.canonical["native_id"] != s1_row["native_id"]:
            raise S2NormaliseError("S2 altered native_id")
        if result.canonical["sequence_raw"] != s1_row["sequence_raw"]:
            stats.sequence_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter sequence_raw")
        if result.canonical["target_name_raw"] != s1_row["target_name_raw"]:
            stats.target_name_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter target_name_raw")
        if result.canonical["sequence_core"] != result.canonical["sequence_full"]:
            raise S2NormaliseError(
                "ENA S2 must not apply trims; sequence_core must equal "
                "sequence_full"
            )
        if result.canonical.get("experiment_group_id"):
            raise S2NormaliseError(
                "ENA S2 must not populate canonical experiment_group_id"
            )
        if result.canonical.get("near_duplicate_family_id"):
            raise S2NormaliseError(
                "ENA S2 must not populate canonical near_duplicate_family_id"
            )
        for field in (
            "target_name",
            "target_uniprot",
            "target_type",
            "target_family",
            "target_pfam",
            "binding_evidence_type",
            "binding_evidence_score",
            "cluster_id",
            "partition",
        ):
            if result.canonical.get(field):
                raise S2NormaliseError(f"ENA S2 must not populate {field}")

        primary = (result.sidecar_experiment_group_id or "").strip()
        if primary:
            primary_groups.setdefault(primary, []).append(result.canonical["record_id"])
        for token in split_supporting_group_ids(result.sidecar_experiment_group_ids):
            supporting_ids.add(token)
        source_family = (meta_row.get("near_duplicate_family_id") or "").strip()
        if source_family:
            nonblank_family += 1
        else:
            blank_family += 1
        if (meta_row.get("ena_source_family_id_was_blank") or "").strip() in {
            "1",
            "true",
        }:
            singleton_family += 1

        normalised_rows.append(result.canonical)
        qc_rows.append(result.qc)
        row_results.append(result)
        update_ena_stats_from_row(stats, result)

    stats.s2_rows = len(normalised_rows)
    stats.unique_record_ids = len({row["record_id"] for row in normalised_rows})
    stats.unique_native_ids = len({row["native_id"] for row in normalised_rows})
    stats.records_dropped = 0
    stats.records_parked = 0
    stats.primary_experiment_groups = len(primary_groups)
    stats.populated_primary_experiment_groups = sum(
        len(members) for members in primary_groups.values()
    )
    stats.supporting_group_ids_expanded = len(supporting_ids)
    stats.blank_source_family_ids = blank_family
    stats.nonblank_source_family_ids = nonblank_family
    stats.materialised_singleton_family_ids = singleton_family
    histogram: dict[str, int] = {}
    for members in primary_groups.values():
        bucket = group_size_bucket(len(members))
        histogram[bucket] = histogram.get(bucket, 0) + 1
    stats.group_size_histogram = dict(sorted(histogram.items()))

    if expected_rows == EXPECTED_ENA_ROWS:
        if stats.s2_rows != EXPECTED_ENA_ROWS:
            raise S2NormaliseError(
                f"S2 must preserve {EXPECTED_ENA_ROWS} rows; got {stats.s2_rows}"
            )
        if stats.unique_record_ids != EXPECTED_ENA_ROWS:
            raise S2NormaliseError("S2 record_id values are not unique")
        if stats.s1_rows - stats.s2_rows != 0:
            raise S2NormaliseError("S2 row disappearance must be 0")
        for key, expected in EXPECTED_ENA_MOLECULE.items():
            got = stats.molecule_type_counts.get(key, 0)
            if got != expected:
                raise S2NormaliseError(
                    f"molecule_type {key} expected {expected}; got {got}"
                )
        for key, expected in EXPECTED_ENA_CHEMISTRY.items():
            got = stats.chemistry_counts.get(key, 0)
            if got != expected:
                raise S2NormaliseError(
                    f"chemistry {key} expected {expected}; got {got}"
                )
        alphabet_got = {
            key: stats.alphabet_counts.get(key, 0)
            for key in EXPECTED_ENA_ALPHABET
        }
        extra_alphabets = {
            key: count
            for key, count in stats.alphabet_counts.items()
            if key not in EXPECTED_ENA_ALPHABET and count
        }
        if alphabet_got != EXPECTED_ENA_ALPHABET or extra_alphabets:
            raise S2NormaliseError(
                "ENA alphabet counts differ from S1 audit expectation "
                f"{EXPECTED_ENA_ALPHABET}; got {dict(stats.alphabet_counts)}"
            )
        if stats.t_to_u_count != EXPECTED_ENA_T_TO_U:
            raise S2NormaliseError(
                f"ENA T→U count expected {EXPECTED_ENA_T_TO_U}; "
                f"got {stats.t_to_u_count}"
            )
        if stats.mixed_t_u_count != 0:
            raise S2NormaliseError("ENA S2 found mixed T/U rows")
        if stats.ambiguous_base_count != 0:
            raise S2NormaliseError("ENA S2 found ambiguous-base rows")
        if stats.invalid_character_count != 0:
            raise S2NormaliseError("ENA S2 found invalid-character rows")
        if stats.core_differs_from_full != 0:
            raise S2NormaliseError(
                "ENA S2 applied a trim; sequence_core must equal sequence_full"
            )
        if stats.primary_experiment_groups != EXPECTED_ENA_PRIMARY_GROUPS:
            raise S2NormaliseError(
                "ENA primary experiment groups expected "
                f"{EXPECTED_ENA_PRIMARY_GROUPS}; got "
                f"{stats.primary_experiment_groups}"
            )
        if stats.sequence_corrections_applied != EXPECTED_ENA_SEQUENCE_CORRECTIONS:
            raise S2NormaliseError(
                "ENA sidecar sequence corrections expected "
                f"{EXPECTED_ENA_SEQUENCE_CORRECTIONS}; got "
                f"{stats.sequence_corrections_applied}"
            )

    inference_inputs = []
    group_membership: dict[str, list[str]] = {}
    inference_key_by_record: dict[str, str | None] = {}
    min_group_size = rules.constant_region_inference.minimum_group_size
    eligible_record_count = 0
    for row, result_row in zip(normalised_rows, row_results, strict=True):
        group_id = build_group_inference_key(
            source_db=row.get("source_db") or "ena",
            grouping_mode=policy.group_inference_key,
            experiment_group_id=result_row.sidecar_experiment_group_id or None,
            target_name_raw=None,
            publication=None,
            pubmed_id=None,
        )
        inference_key_by_record[row["record_id"]] = group_id
        if group_id is not None:
            group_membership.setdefault(group_id, []).append(row["record_id"])
        inference_inputs.append(
            {
                "record_id": row["record_id"],
                "experiment_group_id": group_id,
                "sequence_full": row["sequence_full"] or None,
            }
        )
    for members in group_membership.values():
        if len(members) >= min_group_size:
            eligible_record_count += len(members)

    inference_result = infer_group_constant_regions_with_diagnostics(
        inference_inputs, rules=rules
    )
    group_proposal_rows = build_ena_group_proposal_rows(inference_result.proposals)
    known_motif_proposals = build_ena_known_motif_proposals(row_results)
    all_proposals = group_proposal_rows + known_motif_proposals
    all_proposals.sort(key=lambda item: item["proposal_id"])
    assert_ena_genuine_proposals(all_proposals)

    medium_groups = {
        row["experiment_group_id"]
        for row in group_proposal_rows
        if row["proposal_source"] == "group_consensus"
    }
    annotate_group_consensus_on_qc(
        row_results,
        group_ids_with_proposals=medium_groups,
        inference_key_by_record=inference_key_by_record,
    )
    qc_rows = [row.qc for row in row_results]
    review_rows = [row.qc for row in row_results if ena_is_review_candidate(row.qc)]
    membership_rows = build_ena_membership_rows(
        group_proposal_rows=group_proposal_rows,
        group_membership=group_membership,
    )
    finalise_review_and_duplicate_stats(stats, row_results)

    stats.constant_region_proposals = len(all_proposals)
    stats.groups_considered = inference_result.diagnostics.groups_total
    stats.groups_below_min_size = inference_result.diagnostics.groups_below_min_size
    stats.groups_meeting_min_size = (
        inference_result.diagnostics.groups_total
        - inference_result.diagnostics.groups_below_min_size
    )
    stats.records_in_eligible_groups = eligible_record_count
    stats.five_prime_proposals = sum(
        1
        for row in group_proposal_rows
        if row["side"] == "five_prime" and row["proposal_source"] == "group_consensus"
    )
    stats.three_prime_proposals = sum(
        1
        for row in group_proposal_rows
        if row["side"] == "three_prime" and row["proposal_source"] == "group_consensus"
    )
    stats.records_with_medium_confidence_proposal = sum(
        len(group_membership.get(group_id, ())) for group_id in medium_groups
    )
    stats.high_confidence_trims_applied = 0
    stats.applied_trims = 0
    for row in all_proposals:
        source = row["proposal_source"]
        stats.proposal_source_counts[source] = (
            stats.proposal_source_counts.get(source, 0) + 1
        )
    stats.constant_region_reason = (
        f"tier2_grouping={policy.group_inference_key};"
        "sidecar_primary_experiment_group_id;"
        "proposals_only_not_applied"
    )

    if expected_rows == EXPECTED_ENA_ROWS:
        if stats.groups_considered != EXPECTED_ENA_PRIMARY_GROUPS:
            raise S2NormaliseError(
                "ENA inference groups must equal 25 primary experiment "
                f"groups; got {stats.groups_considered}"
            )
        if stats.supporting_group_ids_expanded == stats.primary_experiment_groups:
            # Supporting expansion is allowed to equal 25; it must not be  used
            # as grouping. The 28-ID expansion is the known larger set.
            pass
        if stats.groups_considered == stats.supporting_group_ids_expanded and (
            stats.supporting_group_ids_expanded != EXPECTED_ENA_PRIMARY_GROUPS
        ):
            raise S2NormaliseError(
                "ENA grouping appears to have used expanded supporting IDs"
            )

    for row in normalised_rows:
        if row["sequence_core"] != row["sequence_full"]:
            raise S2NormaliseError(
                "medium-confidence proposals must not mutate sequence_core"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_normalised = output_dir / "ena_normalised.csv"
    out_qc = output_dir / "ena_s2_qc.csv"
    out_review = output_dir / "ena_s2_review_candidates.csv"
    out_proposals = output_dir / "ena_constant_region_proposals.csv"
    out_membership = output_dir / "ena_constant_region_membership.csv"
    out_report = output_dir / "ena_s2_report.md"

    write_corpus_csv_atomic(out_normalised, normalised_rows)
    write_csv_atomic(out_qc, ENA_S2_QC_COLUMNS, qc_rows)
    write_csv_atomic(out_review, ENA_S2_QC_COLUMNS, review_rows)
    write_csv_atomic(out_proposals, ENA_CONSTANT_PROPOSAL_COLUMNS, all_proposals)
    write_csv_atomic(out_membership, ENA_MEMBERSHIP_COLUMNS, membership_rows)

    s1_hash_after = _sha256_file(canonical_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    inputs_unchanged = (
        s1_hash_before == s1_hash_after
        and sidecar_hash_before == sidecar_hash_after
    )
    if not inputs_unchanged:
        raise S2NormaliseError("S1 inputs were modified during S2 execution")
    stats.sidecar_unchanged = sidecar_hash_before == sidecar_hash_after

    raw_sha_after: str | None = None
    raw_sha_unchanged: bool | None = None
    if raw_sha_before is not None:
        raw_sha_after = _sha256_file(raw_path)
        if raw_sha_after != raw_sha_before:
            raise S2NormaliseError("ENA raw SHA changed during S2")
        raw_sha_unchanged = True

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "normalised": _sha256_file(out_normalised),
            "qc": _sha256_file(out_qc),
            "review": _sha256_file(out_review),
            "proposals": _sha256_file(out_proposals),
            "membership": _sha256_file(out_membership),
        }
        second = run_ena_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=policy_path,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["normalised"] == _sha256_file(second.output_normalised)
            and first_hashes["qc"] == _sha256_file(second.output_qc)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["proposals"] == _sha256_file(second.output_proposals)
            and second.output_rule_membership is not None
            and first_hashes["membership"]
            == _sha256_file(second.output_rule_membership)
        )
        if not deterministic_ok:
            raise S2NormaliseError(
                "S2 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S2RunResult(
        source_key="ena",
        stats=stats,
        output_normalised=out_normalised,
        output_qc=out_qc,
        output_review=out_review,
        output_proposals=out_proposals,
        output_report=out_report,
        s1_hash_before=s1_hash_before,
        s1_hash_after=s1_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        raw_sha256=raw_sha_after,
        raw_sha_unchanged=raw_sha_unchanged,
        output_rule_membership=out_membership,
    )
    report_text = build_ena_s2_report(
        repo_root=repo_root,
        result=run_result,
        rules_path=rules_path,
        policy_path=policy_path,
        diagnostics=inference_result.diagnostics,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in report_text:
        raise S2NormaliseError("S2 report must not contain absolute repository paths")
    _write_text_atomic(out_report, report_text)
    return run_result


def build_aptamerbase_s2_report(
    *,
    repo_root: Path,
    result: S2RunResult,
    rules_path: Path,
    policy_path: Path,
) -> str:
    """Build an aggregate-only Markdown AptamerBase S2 report (no sequences)."""
    stats = result.stats
    if not isinstance(stats, AptamerBaseS2Stats):
        raise S2NormaliseError("AptamerBase report requires AptamerBaseS2Stats")
    full_min, full_med, full_max = summarise_aptamerbase_lengths(
        stats.length_full_values
    )
    core_min, core_med, core_max = summarise_aptamerbase_lengths(
        stats.length_core_values
    )
    scanned = (
        ", ".join(f"`{name}`" for name in stats.known_motifs_scanned) or "(none)"
    )
    lines = [
        "# AptamerBase S2 normalisation report",
        "",
        "Aggregate counts only. Source sequences and modification strings are",
        "not included.",
        "",
        "## SOURCE CONTRACT",
        "",
        f"- Source key: `aptamerbase`",
        f"- Source dataset: `{EXPECTED_APTAMERBASE_SOURCE_DATASET}`",
        f"- CSV spine: `data/raw/aptamerbase/aptamerbase_aptamers.csv`",
        (
            f"- CSV SHA-256: `{result.raw_sha256}`"
            if result.raw_sha256
            else "- CSV SHA-256: `not_checked`"
        ),
        f"- Supporting RDF: `data/raw/aptamerbase/aptamerbase.freebase.extract.nt.gz`",
        f"- RDF SHA-256: `{EXPECTED_APTAMERBASE_RAW_RDF_SHA256}`",
        f"- RDF decompressed N-Triples statements: `{stats.rdf_statement_count}`",
        f"- S1 canonical rows: `{stats.s1_rows}`",
        f"- Source-metadata rows: `{stats.source_metadata_rows}`",
        f"- S2 output rows: `{stats.s2_rows}`",
        f"- Unique Freebase IDs: `{stats.unique_freebase_ids}`",
        f"- RDF subjects joined: `{stats.rdf_subjects_joined}`",
        f"- RDF join coverage: "
        f"`{'pass' if stats.rdf_join_coverage_ok else 'fail'}`",
        f"- S1 frozen canonical hash: `{EXPECTED_APTAMERBASE_S1_CANONICAL_SHA256}`",
        f"- S1 frozen sidecar hash: `{EXPECTED_APTAMERBASE_S1_SIDECAR_SHA256}`",
        f"- Shared rules: `{_relative_display(rules_path, repo_root)}`",
        f"- Source policy: `{_relative_display(policy_path, repo_root)}`",
        "",
        "## OBJECT GRAIN",
        "",
        "Source object class is taken from the S1 sidecar `aptamerbase_type`.",
        "Secondary-structure and predicted-secondary-structure objects are",
        "retained with `molecule_type=unknown` and `chemistry=unknown`. An",
        "incidental RDF RNA type does not convert a structure topic into an",
        "aptamer record. No S3 route is decided here.",
        "",
    ]
    for name, count in _count_sorted(stats.source_object_type_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            f"- Structure-topic rows: `{stats.structure_topic_rows}`",
            f"- Structure-topic rows with nonempty normalised sequence: "
            f"`{stats.structure_topic_nonempty_sequence}`",
            "",
            "## MOLECULE TYPE",
            "",
            "Experimental molecule type is RDF RNA/DNA typing, then the",
            "structure-topic override. Sequence alphabet does not establish or",
            "erase molecule type. Unresolved RDF IDs remain `unknown`.",
            "",
            "### Physical rows",
            "",
        ]
    )
    for name, count in _count_sorted(stats.molecule_type_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Unique Freebase IDs", ""])
    for name, count in _count_sorted(stats.molecule_type_unique_id_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            f"- Evidence source: `rdf_type` (structure topics: `source_object_type`)",
            f"- Unresolved / unknown physical rows: "
            f"`{stats.molecule_type_counts.get('unknown', 0)}`",
            "",
            "## ALPHABET / T→U",
            "",
            "`alphabet_as_reported` is the shared display-level classification",
            "before T→U. T→U is applied only after RDF has independently",
            "established RNA. RDF DNA printed in U is retained as ssDNA with a",
            "contradiction flag. Mixed T/U is not automatically transcribed.",
            "A/C/G-only sequences are not a separate canonical alphabet; they",
            "use the shared molecule-type tie-break (`RNA` or `DNA_T`).",
            "Invalid counts are post-display-clean remaining noncanonical",
            "characters, not a pre-clean diagnostic.",
            "",
        ]
    )
    for name, count in _count_sorted(stats.alphabet_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            f"- `t_to_u_applied=true`: `{stats.t_to_u_count}`",
            f"- RDF RNA × DNA_T alphabet (computational transcription candidates): "
            f"`{stats.rna_t_alphabet_count}`",
            f"- RDF DNA × U alphabet conflict rows: `{stats.dna_u_conflict_count}`",
            f"- RDF DNA × U alphabet conflict unique IDs: "
            f"`{stats.dna_u_conflict_unique_ids}`",
            f"- mixed T/U: `{stats.mixed_t_u_count}`",
            f"- ambiguous: `{stats.ambiguous_base_count}`",
            f"- invalid/noncanonical: `{stats.invalid_character_count}`",
            "",
            "## CHEMISTRY",
            "",
            "Chemistry is separate from molecule identity. Automatic mapping is",
            "limited to unmodified RNA/DNA backbones, terminal/conjugate-only",
            "metadata, and a closed 2′-fluoro-pyrimidine RNA allowlist.",
            "Spiegelmer/L-RNA, 2OMe, 2NH2, inverted-dT constructs, iso-G,",
            "pentynyl-dU and other unusual combinations remain `unknown` for",
            "review. DNA + 2F-like modification text is not auto-mapped.",
            "",
            "### Canonical chemistry",
            "",
        ]
    )
    for name, count in _count_sorted(stats.chemistry_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Chemistry class (aggregate, no source literals)", ""])
    for name, count in _count_sorted(stats.chemistry_class_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            f"- Automatic 2F-RNA assignments: `{stats.twof_rna_automatic_count}`",
            f"- Chemistry-review rows: `{stats.chemistry_review_count}`",
            f"- Spiegelmer/L-RNA review rows: `{stats.spiegelmer_count}`",
            f"- Terminal-conjugate diagnostic rows: `{stats.terminal_conjugate_count}`",
            f"- RDF modified type + source modification text: "
            f"`{stats.rdf_modified_with_text}`",
            f"- RDF modified type but blank text: `{stats.rdf_modified_without_text}`",
            f"- Modification text without RDF modified type: "
            f"`{stats.text_without_rdf_modified}`",
            "",
            "## SEQUENCE / LENGTH QC",
            "",
            "Canonical lengths are `len(sequence_full)` / `len(sequence_core)`.",
            "Source `aptamerbase_sequence_length` is compared as QC only.",
            "Invalid/ambiguous early-return paths may have an observable",
            "normalised string length without emitting shared core-length QC",
            "flags; those denominators are reported separately.",
            "",
            f"- Sequence missing after shared textual-null processing: "
            f"`{stats.missing_sequence_rows}`",
            f"- Nonempty normalised sequences: `{stats.nonempty_sequence_rows}`",
            f"- sequence_raw unchanged: "
            f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
            f"- target_name_raw unchanged and empty: "
            f"`{'pass' if stats.target_name_raw_unchanged else 'fail'}`",
            f"- Source-reported length mismatches: `{stats.length_mismatch_count}`",
            f"- Observable length outside 20–100 without shared core-length QC: "
            f"`{stats.observable_length_without_core_qc}`",
            f"- Shared `core_below_min_length` flags: `{stats.core_below_min_count}`",
            f"- Shared `core_above_max_length` flags: `{stats.core_above_max_count}`",
            f"- sequence_length_full min/median/max: "
            f"`{full_min}` / `{full_med}` / `{full_max}`",
            f"- sequence_length_core min/median/max: "
            f"`{core_min}` / `{core_med}` / `{core_max}`",
            "",
            "### Observable sequence_length_full buckets",
            "",
        ]
    )
    for name, count in _count_sorted(stats.length_full_buckets):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### sequence_length_core buckets", ""])
    for name, count in _count_sorted(stats.length_core_buckets):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## CONSTANTS",
            "",
            "Known-motif detection uses the shared motif library only.",
            "No AptamerBase-specific primer/T7 motifs were added. No trim is",
            "applied. Group-wise consensus inference is disabled because the",
            "S1 contract has no defensible experiment/publication grouping key.",
            "`label` is not used as a grouping or target field.",
            "",
            f"- Known motifs scanned: {scanned}",
            f"- Records with known-motif detection: "
            f"`{stats.known_motif_detection_count}`",
            f"- Known-motif proposals (unapplied): `{stats.constant_region_proposals}`",
            f"- 5′ known-motif proposals: `{stats.five_prime_proposals}`",
            f"- 3′ known-motif proposals: `{stats.three_prime_proposals}`",
            f"- Group-consensus proposals: `0`",
            f"- Groups considered: `{stats.groups_considered}`",
            f"- Applied trims: `{stats.applied_trims}`",
            f"- sequence_core differs from sequence_full: "
            f"`{stats.core_differs_from_full}`",
            f"- Constant-region reason: `{stats.constant_region_reason}`",
            "",
            "### construct_scope",
            "",
        ]
    )
    for name, count in _count_sorted(stats.construct_scope_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_status", ""])
    for name, count in _count_sorted(stats.trim_status_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## RELATIONSHIP / SOURCE-METADATA PRESERVATION",
            "",
            "Minimal-aptamer sidecar fields are retained as source provenance",
            "for later S5 clustering-validation evidence. They are not mapped",
            "into `near_duplicate_family_id`, `cluster_id`, dedup keys or",
            "target fields. No row consolidation occurred.",
            "",
            f"- Sidecar `has_minimal_aptamer` nonempty: "
            f"`{stats.sidecar_has_minimal_aptamer_nonempty}`",
            f"- Sidecar `is_minimal_aptamer_of` nonempty: "
            f"`{stats.sidecar_is_minimal_aptamer_of_nonempty}`",
            f"- Records dropped: `{stats.records_dropped}`",
            f"- Records parked: `{stats.records_parked}`",
            f"- Unique record_id values: `{stats.unique_record_ids}`",
            f"- S1 row order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
            "",
            "## DEFERRED",
            "",
            "The following remain empty / unperformed at S2:",
            "",
            "- target identity / `target_name` / `target_name_raw` (still empty)",
            "- UniProt / target type / family / Pfam",
            "- interaction participant",
            "- PMID / publication parsing from `label`",
            "- evidence ladder E1–E5 / `binding_evidence_score`",
            "- affinity normalisation",
            "- experimentally determined structure / PDB",
            "- leakage exclusion",
            "- filtering / parking / ssDNA S3 routing",
            "- deduplication / Freebase ID collapse",
            "- clustering / partition",
            "- CHECKPOINT-1",
            "- global S4",
            "",
            f"- Deferred S4 fields empty: "
            f"`{'pass' if stats.s4_fields_empty else 'fail'}`",
            "",
            "## Review candidates",
            "",
            f"- Review-candidate rows: `{stats.review_candidate_rows}`",
            "",
        ]
    )
    for name, count in _count_sorted(stats.review_reason_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### qc_flags", ""])
    for name, count in _count_sorted(stats.qc_flag_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Integrity",
            "",
            f"- Deterministic rerun: "
            f"`{'pass' if result.deterministic_rerun_ok else ('not_run' if result.deterministic_rerun_ok is None else 'fail')}`",
            f"- S1 inputs unchanged: `{'pass' if result.inputs_unchanged else 'fail'}`",
            f"- S1 canonical hash before: `{result.s1_hash_before}`",
            f"- S1 canonical hash after: `{result.s1_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            (
                f"- Raw CSV SHA-256 unchanged: "
                f"`{'pass' if result.raw_sha_unchanged else 'fail'}`"
                if result.raw_sha_unchanged is not None
                else "- Raw CSV SHA-256 unchanged: `not_checked`"
            ),
            "",
            "## Outputs",
            "",
            f"- Normalised: "
            f"`{_relative_display(result.output_normalised, repo_root)}`",
            f"- QC: `{_relative_display(result.output_qc, repo_root)}`",
            f"- Review candidates: "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Detected constants / proposals: "
            f"`{_relative_display(result.output_proposals, repo_root)}`",
            f"- Report: `{_relative_display(result.output_report, repo_root)}`",
            "",
            "## Stage boundary",
            "",
            "AptamerBase S2 RDF-supported sequence normalisation only.",
            "",
            "- No record was rejected, parked or dropped.",
            "- No Freebase ID or sequence duplicate was collapsed.",
            "- No trim was applied.",
            "- Group-wise constant inference was not run.",
            "- S3 has not started.",
            "- CHECKPOINT-1 was not generated.",
            "- No AptamerBase record is authorised for global S4.",
            "",
        ]
    )
    return "\n".join(lines)


def run_aptamerbase_s2(
    *,
    repo_root: Path,
    input_dir: Path,
    output_dir: Path,
    rules_path: Path,
    policy_path: Path,
    expected_rows: int | None = EXPECTED_APTAMERBASE_ROWS,
    check_deterministic_rerun: bool = False,
) -> S2RunResult:
    """Execute AptamerBase S2 normalisation."""
    repo_root = repo_root.resolve()
    input_dir = input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    input_dir = input_dir.resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    rules_path = (
        rules_path if rules_path.is_absolute() else (repo_root / rules_path)
    ).resolve()
    policy_path = (
        policy_path if policy_path.is_absolute() else (repo_root / policy_path)
    ).resolve()

    canonical_path = input_dir / "aptamerbase_extracted.csv"
    sidecar_path = input_dir / "aptamerbase_source_metadata.csv"
    if not canonical_path.is_file():
        raise S2NormaliseError(f"Missing S1 canonical input: {canonical_path.name}")
    if not sidecar_path.is_file():
        raise S2NormaliseError(f"Missing S1 sidecar input: {sidecar_path.name}")

    raw_csv_path = (
        repo_root / "data" / "raw" / "aptamerbase" / "aptamerbase_aptamers.csv"
    )
    raw_rdf_path = (
        repo_root
        / "data"
        / "raw"
        / "aptamerbase"
        / "aptamerbase.freebase.extract.nt.gz"
    )
    production = expected_rows == EXPECTED_APTAMERBASE_ROWS
    raw_sha_before: str | None = None
    if production:
        if not raw_csv_path.is_file():
            raise S2NormaliseError("Missing registered AptamerBase raw CSV")
        if not raw_rdf_path.is_file():
            raise S2NormaliseError("Missing registered AptamerBase supporting RDF")
        digest = _sha256_file(raw_csv_path)
        if digest != EXPECTED_APTAMERBASE_RAW_CSV_SHA256:
            raise S2NormaliseError(
                "AptamerBase raw CSV SHA-256 does not match the frozen contract"
            )
        rdf_digest = _sha256_file(raw_rdf_path)
        if rdf_digest != EXPECTED_APTAMERBASE_RAW_RDF_SHA256:
            raise S2NormaliseError(
                "AptamerBase supporting RDF SHA-256 does not match the "
                "frozen contract"
            )
        raw_sha_before = digest

    s1_hash_before = _sha256_file(canonical_path)
    sidecar_hash_before = _sha256_file(sidecar_path)
    if production:
        if s1_hash_before != EXPECTED_APTAMERBASE_S1_CANONICAL_SHA256:
            raise S2NormaliseError(
                "AptamerBase S1 canonical SHA-256 does not match the frozen "
                "accepted value; S2 must not proceed"
            )
        if sidecar_hash_before != EXPECTED_APTAMERBASE_S1_SIDECAR_SHA256:
            raise S2NormaliseError(
                "AptamerBase S1 sidecar SHA-256 does not match the frozen "
                "accepted value; S2 must not proceed"
            )

    rules = load_normalisation_rules(rules_path)
    policy = load_aptamerbase_policy(policy_path)
    if policy.apply_approved_trims:
        raise S2NormaliseError("AptamerBase S2 must not apply approved trims")
    if policy.group_inference_key != "disabled":
        raise S2NormaliseError(
            "AptamerBase S2 must keep group-wise inference disabled"
        )
    if not raw_rdf_path.is_file():
        raise S2NormaliseError("Missing AptamerBase supporting RDF for S2 join")

    rdf_index = load_aptamerbase_rdf_index(
        raw_rdf_path,
        rdf_type_predicate=policy.rdf_type_predicate,
        freebase_type_predicate=policy.freebase_type_predicate,
        modification_details_predicate=policy.modification_details_predicate,
        type_uris=policy.rdf_type_uris,
        expected_statements=(
            EXPECTED_APTAMERBASE_RDF_STATEMENTS if production else None
        ),
    )

    canonical_rows = _read_corpus_csv(canonical_path)
    sidecar_rows = _read_sidecar_csv(sidecar_path)
    aligned_sidecar = _match_sidecar_one_to_one(canonical_rows, sidecar_rows)

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S2NormaliseError(
            f"S1 row count must be {expected_rows}; got {len(canonical_rows)}"
        )

    for index, row in enumerate(canonical_rows, start=1):
        if row["source_db"] != "aptamerbase":
            raise S2NormaliseError(f"row {index}: source_db must be aptamerbase")
        if production and row["source_dataset"] != EXPECTED_APTAMERBASE_SOURCE_DATASET:
            raise S2NormaliseError(
                f"row {index}: source_dataset must be "
                f"{EXPECTED_APTAMERBASE_SOURCE_DATASET}"
            )

    stats = AptamerBaseS2Stats()
    stats.s1_rows = len(canonical_rows)
    stats.source_metadata_rows = len(aligned_sidecar)
    stats.rdf_statement_count = rdf_index.statement_count
    stats.order_preserved = True
    stats.provenance_preserved = True
    stats.sequence_raw_unchanged = True
    stats.target_name_raw_unchanged = True
    stats.notes_unchanged = True
    stats.known_motifs_scanned = tuple(
        motif.name for motif in rules.known_non_core_motifs
    )

    normalised_rows: list[dict[str, str]] = []
    qc_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    row_results: list = []
    rdf_typing_by_id: dict[str, str] = {}

    for s1_row, meta_row in zip(canonical_rows, aligned_sidecar, strict=True):
        source_id = meta_row.get(policy.source_id_field, "")
        facts = require_subject_facts(rdf_index, source_id)
        result = normalise_aptamerbase_record(
            s1_row,
            meta_row,
            facts,
            policy=policy,
            rules=rules,
        )
        previous_typing = rdf_typing_by_id.get(source_id)
        if previous_typing is None:
            rdf_typing_by_id[source_id] = result.rdf_molecule_type
        elif previous_typing != result.rdf_molecule_type:
            raise S2NormaliseError(
                "repeated Freebase ID received inconsistent RDF-derived typing"
            )
        if result.canonical["record_id"] != s1_row["record_id"]:
            stats.order_preserved = False
            raise S2NormaliseError("S2 altered record_id or row identity")
        if result.canonical["native_id"] != s1_row["native_id"]:
            raise S2NormaliseError("S2 altered native_id")
        if result.canonical["sequence_raw"] != s1_row["sequence_raw"]:
            stats.sequence_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter sequence_raw")
        if result.canonical["target_name_raw"] != s1_row["target_name_raw"]:
            stats.target_name_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter target_name_raw")
        if result.canonical["notes"] != s1_row["notes"]:
            stats.notes_unchanged = False
            raise S2NormaliseError("S2 must not alter notes")
        if result.canonical["source_db"] != s1_row["source_db"]:
            stats.provenance_preserved = False
            raise S2NormaliseError("S2 must not alter source_db")
        if result.canonical["source_dataset"] != s1_row["source_dataset"]:
            stats.provenance_preserved = False
            raise S2NormaliseError("S2 must not alter source_dataset")
        if result.canonical["sequence_core"] != result.canonical["sequence_full"]:
            raise S2NormaliseError(
                "AptamerBase S2 must not apply trims; sequence_core must equal "
                "sequence_full"
            )
        if not aptamerbase_s4_fields_are_empty(result.canonical):
            raise S2NormaliseError("AptamerBase S2 populated a deferred S4 field")
        length_full = result.canonical["sequence_length_full"]
        if length_full != "":
            if int(length_full) != len(result.canonical["sequence_full"]):
                raise S2NormaliseError(
                    "sequence_length_full must equal len(sequence_full)"
                )
            if int(result.canonical["sequence_length_core"]) != len(
                result.canonical["sequence_core"]
            ):
                raise S2NormaliseError(
                    "sequence_length_core must equal len(sequence_core)"
                )
        normalised_rows.append(result.canonical)
        qc_rows.append(result.qc)
        row_results.append(result)
        if aptamerbase_is_review_candidate(result.qc):
            review_rows.append(result.qc)
        update_aptamerbase_stats_from_row(stats, result)

    stats.s2_rows = len(normalised_rows)
    stats.unique_record_ids = len({row["record_id"] for row in normalised_rows})
    stats.unique_native_ids = len({row["native_id"] for row in normalised_rows})
    stats.records_dropped = 0
    stats.records_parked = 0
    finalise_aptamerbase_review_and_id_stats(stats, row_results)
    stats.s4_fields_empty = all(
        aptamerbase_s4_fields_are_empty(row) for row in normalised_rows
    )

    if production:
        if stats.s2_rows != EXPECTED_APTAMERBASE_ROWS:
            raise S2NormaliseError(
                f"S2 must preserve {EXPECTED_APTAMERBASE_ROWS} rows; "
                f"got {stats.s2_rows}"
            )
        if stats.unique_record_ids != EXPECTED_APTAMERBASE_ROWS:
            raise S2NormaliseError("S2 record_id values are not unique")
        if stats.unique_freebase_ids != EXPECTED_APTAMERBASE_UNIQUE_IDS:
            raise S2NormaliseError(
                "S2 unique Freebase ID count does not match the S1 contract"
            )
        if not stats.rdf_join_coverage_ok:
            raise S2NormaliseError("S2 RDF join coverage is incomplete")
        if stats.s1_rows - stats.s2_rows != 0:
            raise S2NormaliseError("S2 row disappearance must be 0")
        if stats.core_differs_from_full != 0 or stats.applied_trims != 0:
            raise S2NormaliseError(
                "AptamerBase S2 applied a trim; sequence_core must equal "
                "sequence_full"
            )
        nonempty_target = sum(1 for row in normalised_rows if row["target_name_raw"])
        if nonempty_target:
            raise S2NormaliseError(
                "AptamerBase S2 must not populate target_name_raw"
            )

    known_motif_proposals = build_aptamerbase_known_motif_proposals(row_results)
    assert_aptamerbase_genuine_proposals(known_motif_proposals)

    stats.constant_region_proposals = len(known_motif_proposals)
    stats.groups_considered = 0
    stats.groups_meeting_min_size = 0
    stats.five_prime_proposals = sum(
        1 for row in known_motif_proposals if row["side"] == "five_prime"
    )
    stats.three_prime_proposals = sum(
        1 for row in known_motif_proposals if row["side"] == "three_prime"
    )
    stats.records_with_medium_confidence_proposal = 0
    stats.high_confidence_trims_applied = 0
    stats.applied_trims = 0
    for row in known_motif_proposals:
        source = row["proposal_source"]
        stats.proposal_source_counts[source] = (
            stats.proposal_source_counts.get(source, 0) + 1
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_normalised = output_dir / "aptamerbase_normalised.csv"
    out_qc = output_dir / "aptamerbase_s2_qc.csv"
    out_review = output_dir / "aptamerbase_s2_review_candidates.csv"
    out_proposals = output_dir / "detected_constants_aptamerbase.csv"
    out_report = output_dir / "aptamerbase_s2_report.md"

    write_corpus_csv_atomic(out_normalised, normalised_rows)
    write_csv_atomic(out_qc, APTAMERBASE_S2_QC_COLUMNS, qc_rows)
    write_csv_atomic(out_review, APTAMERBASE_S2_QC_COLUMNS, review_rows)
    write_csv_atomic(
        out_proposals, APTAMERBASE_CONSTANT_PROPOSAL_COLUMNS, known_motif_proposals
    )

    s1_hash_after = _sha256_file(canonical_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    inputs_unchanged = (
        s1_hash_before == s1_hash_after
        and sidecar_hash_before == sidecar_hash_after
    )
    if not inputs_unchanged:
        raise S2NormaliseError("S1 inputs were modified during S2 execution")

    raw_sha_after: str | None = None
    raw_sha_unchanged: bool | None = None
    if raw_sha_before is not None:
        digest = _sha256_file(raw_csv_path)
        rdf_digest = _sha256_file(raw_rdf_path)
        if digest != raw_sha_before or rdf_digest != EXPECTED_APTAMERBASE_RAW_RDF_SHA256:
            raise S2NormaliseError("AptamerBase raw CSV/RDF SHA changed during S2")
        raw_sha_after = digest
        raw_sha_unchanged = True

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "normalised": _sha256_file(out_normalised),
            "qc": _sha256_file(out_qc),
            "review": _sha256_file(out_review),
            "proposals": _sha256_file(out_proposals),
        }
        second = run_aptamerbase_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=policy_path,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["normalised"] == _sha256_file(second.output_normalised)
            and first_hashes["qc"] == _sha256_file(second.output_qc)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["proposals"] == _sha256_file(second.output_proposals)
        )
        if not deterministic_ok:
            raise S2NormaliseError(
                "S2 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S2RunResult(
        source_key="aptamerbase",
        stats=stats,
        output_normalised=out_normalised,
        output_qc=out_qc,
        output_review=out_review,
        output_proposals=out_proposals,
        output_report=out_report,
        s1_hash_before=s1_hash_before,
        s1_hash_after=s1_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        raw_sha256=raw_sha_after,
        raw_sha_unchanged=raw_sha_unchanged,
    )
    report_text = build_aptamerbase_s2_report(
        repo_root=repo_root,
        result=run_result,
        rules_path=rules_path,
        policy_path=policy_path,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in report_text:
        raise S2NormaliseError("S2 report must not contain absolute repository paths")
    _write_text_atomic(out_report, report_text)
    return run_result


def _aptadiff_production_profile(source_key: str) -> dict[str, Any]:
    """Return frozen production S2 expectations for one AptaDiff source."""
    if source_key == "aptadiff_a":
        return {
            "expected_rows": EXPECTED_APTADIFF_A_ROWS,
            "source_dataset": EXPECTED_APTADIFF_A_SOURCE_DATASET,
            "raw_path": EXPECTED_APTADIFF_A_RAW_PATH,
            "raw_sha256": EXPECTED_APTADIFF_A_RAW_SHA256,
            "molecule": EXPECTED_APTADIFF_A_MOLECULE,
            "chemistry": EXPECTED_APTADIFF_A_CHEMISTRY,
            "alphabet": EXPECTED_APTADIFF_A_ALPHABET,
        }
    if source_key == "aptadiff_b":
        return {
            "expected_rows": EXPECTED_APTADIFF_B_ROWS,
            "source_dataset": EXPECTED_APTADIFF_B_SOURCE_DATASET,
            "raw_path": EXPECTED_APTADIFF_B_RAW_PATH,
            "raw_sha256": EXPECTED_APTADIFF_B_RAW_SHA256,
            "molecule": EXPECTED_APTADIFF_B_MOLECULE,
            "chemistry": EXPECTED_APTADIFF_B_CHEMISTRY,
            "alphabet": EXPECTED_APTADIFF_B_ALPHABET,
        }
    raise S2NormaliseError(
        f"Unknown AptaDiff S2 source_key={source_key!r}; expected "
        "aptadiff_a or aptadiff_b"
    )


def build_aptadiff_s2_report(
    *,
    repo_root: Path,
    result: S2RunResult,
    rules_path: Path,
    policy_path: Path,
) -> str:
    """Build an aggregate-only Markdown AptaDiff S2 report (no sequences)."""
    stats = result.stats
    if not isinstance(stats, AptaDiffS2Stats):
        raise S2NormaliseError("AptaDiff report requires AptaDiffS2Stats")
    profile = _aptadiff_production_profile(result.source_key)
    documented = aptadiff_expected_documented_target(result.source_key)
    full_min, full_med, full_max = summarise_aptadiff_lengths(stats.length_full_values)
    core_min, core_med, core_max = summarise_aptadiff_lengths(stats.length_core_values)
    lines = [
        f"# AptaDiff {result.source_key} S2 normalisation report",
        "",
        "## Reconciliation",
        "",
        f"- Source key: `{result.source_key}`",
        f"- Source dataset: `{profile['source_dataset']}`",
        f"- S1 canonical rows: `{stats.s1_rows}`",
        f"- Source-metadata rows: `{stats.source_metadata_rows}`",
        f"- S2 output rows: `{stats.s2_rows}`",
        f"- Records dropped: `{stats.records_dropped}`",
        f"- Records parked: `{stats.records_parked}`",
        f"- Unique record_id values: `{stats.unique_record_ids}`",
        f"- Unique native_id values: `{stats.unique_native_ids}`",
        f"- Row disappearance: `{stats.s1_rows - stats.s2_rows}`",
        f"- S1 row order preserved: "
        f"`{'pass' if stats.order_preserved else 'fail'}`",
        f"- S1 provenance preserved: "
        f"`{'pass' if stats.provenance_preserved else 'fail'}`",
        f"- sequence_raw unchanged: "
        f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
        f"- target_name_raw unchanged: "
        f"`{'pass' if stats.target_name_raw_unchanged else 'fail'}`",
        f"- notes unchanged: `{'pass' if stats.notes_unchanged else 'fail'}`",
        f"- Missing sequence rows: `{stats.missing_sequence_rows}`",
        f"- Nonempty sequence rows: `{stats.nonempty_sequence_rows}`",
        f"- Length-36 rows: `{stats.length_36_count}`",
        f"- Other lengths: `{stats.other_length_count}`",
        f"- Shared rules: `{_relative_display(rules_path, repo_root)}`",
        f"- Source policy: `{_relative_display(policy_path, repo_root)}`",
        "",
        "## Molecule / chemistry",
        "",
        "Experimental molecule type is fixed by Laura's reviewed AptaDiff",
        "source contract (`molecule_type=ssDNA`, `chemistry=DNA`). These",
        "are genuine DNA aptamer HT-SELEX libraries, not RNA molecules",
        "printed using T. Molecule identity is not inferred from sequence",
        "alphabet. Canonical S2 retains DNA; T→U is not applied.",
        "",
        f"- Documented target provenance (sidecar only): `{documented}`",
        "",
        "### Canonical molecule_type",
        "",
    ]
    for name, count in _count_sorted(stats.molecule_type_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Canonical chemistry", ""])
    for name, count in _count_sorted(stats.chemistry_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "### Documented target (sidecar provenance only)",
            "",
        ]
    )
    for name, count in _count_sorted(stats.documented_target_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Reported alphabet",
            "",
            "Shared alphabet vocabulary is `RNA` / `DNA_T` / `mixed_T_U` /",
            "`ambiguous` / `invalid`. Ordinary A/C/G/T rows are `DNA_T`.",
            "N-containing rows are `ambiguous` and remain ssDNA. N is not",
            "repaired. These rows are not rejected at S2.",
            "",
        ]
    )
    for name, count in _count_sorted(stats.alphabet_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Computational transcription",
            "",
            f"- total `t_to_u_applied=true`: `{stats.t_to_u_count}`",
            "- T→U is forbidden for AptaDiff A/B at canonical S2.",
            "",
            "## Display cleaning",
            "",
        ]
    )
    if stats.transformation_counts:
        for name, count in _count_sorted(stats.transformation_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## QC",
            "",
            f"- Invalid character rows: `{stats.invalid_character_count}`",
            f"- Alignment-gap rows: `{stats.alignment_gaps_count}`",
            f"- Ambiguous base rows: `{stats.ambiguous_base_count}`",
            f"- Mixed T/U rows: `{stats.mixed_t_u_count}`",
            f"- Core below minimum length: `{stats.core_below_min_count}`",
            f"- Core above maximum length: `{stats.core_above_max_count}`",
            f"- Rows with any QC flag: `{stats.rows_with_any_qc_flag}`",
            f"- Rows with multiple QC flags: `{stats.rows_with_multiple_qc_flags}`",
            f"- Review-candidate rows: `{stats.review_candidate_rows}`",
            "",
        ]
    )
    if stats.qc_flag_counts:
        for name, count in _count_sorted(stats.qc_flag_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## Length",
            "",
            "Registered P6 values are 36-nt variable regions. Lengths are",
            "computed from the shared normalised representation.",
            "",
            f"- sequence_length_full min / median / max: "
            f"`{full_min}` / `{full_med}` / `{full_max}`",
            f"- sequence_length_core min / median / max: "
            f"`{core_min}` / `{core_med}` / `{core_max}`",
            "",
            "### sequence_length_full buckets",
            "",
        ]
    )
    for name, count in _count_sorted(stats.length_full_buckets):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### sequence_length_core buckets", ""])
    for name, count in _count_sorted(stats.length_core_buckets):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "Full and core length distributions are identical because no",
            "trim was applied (`sequence_core == sequence_full`).",
            "",
            "## Construct / trim state",
            "",
            "Source contract: `construct_scope = random_region_only`.",
            "Experimental fixed primer regions were already excluded from",
            "the registered P6 `seq` values. Constant-region inference,",
            "known-motif trimming, group-wise consensus, and T7-promoter",
            "trimming are disabled. Shared selected-sequence motifs are",
            "not treated as residual primer sequence.",
            "",
            "### construct_scope",
            "",
        ]
    )
    for name, count in _count_sorted(stats.construct_scope_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_status", ""])
    for name, count in _count_sorted(stats.trim_status_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_confidence", ""])
    for name, count in _count_sorted(stats.trim_confidence_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Constant-region detection",
            "",
            "Constant-region inference is disabled by source contract.",
            "The proposal artefact is header-only.",
            "",
            f"- Genuine proposal rows: `{stats.constant_region_proposals}`",
            f"- Group-consensus proposals: `0`",
            f"- Groups considered: `{stats.groups_considered}`",
            f"- Groups meeting minimum size: `{stats.groups_meeting_min_size}`",
            f"- Previously approved high-confidence trims applied: "
            f"`{stats.high_confidence_trims_applied}`",
            f"- Records actually trimmed: `{stats.applied_trims}`",
            f"- Rows where sequence_core != sequence_full: "
            f"`{stats.core_differs_from_full}`",
            f"- Reason: `{stats.constant_region_reason}`",
            "",
            "### proposal sources",
            "",
            "- (none)",
            "",
            "## p6 / targets / evidence",
            "",
            f"- Sidecar p6 values copied into QC (uninterpreted): "
            f"`{stats.nonempty_p6_qc_rows}`",
            f"- Canonical affinity fields populated: "
            f"`{stats.nonempty_affinity_fields}`",
            f"- Canonical evidence fields populated: "
            f"`{stats.nonempty_evidence_fields}`",
            f"- Canonical target fields populated: "
            f"`{stats.nonempty_canonical_target_fields}`",
            "- `target_name_raw` remains empty as in S1.",
            "- Documented IGFBP3 / PTK7 identity remains sidecar provenance.",
            "- Binding evidence, affinity, leakage, and target eligibility",
            "  are not evaluated at S2.",
            "",
            "## Invariants",
            "",
            f"- sequence_raw unchanged: "
            f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
            f"- Records retained: `{stats.s2_rows}`",
            f"- Provenance unchanged: "
            f"`{'pass' if stats.provenance_preserved else 'fail'}`",
            "- S4 target/evidence/affinity/PDB fields remain blank",
            (
                f"- Raw input hash unchanged: "
                f"`{'pass' if result.raw_sha_unchanged else 'fail'}`"
                if result.raw_sha_unchanged is not None
                else "- Raw input hash unchanged: `not_checked`"
            ),
            f"- S1 inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            "",
            f"- S1 canonical hash before: `{result.s1_hash_before}`",
            f"- S1 canonical hash after: `{result.s1_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            (
                f"- Raw SHA-256: `{result.raw_sha256}`"
                if result.raw_sha256
                else "- Raw SHA-256: `not_checked`"
            ),
            "",
            "## Outputs",
            "",
            f"- Normalised: "
            f"`{_relative_display(result.output_normalised, repo_root)}`",
            f"- QC: `{_relative_display(result.output_qc, repo_root)}`",
            f"- Review candidates: "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Detected constants / proposals: "
            f"`{_relative_display(result.output_proposals, repo_root)}`",
            f"- Report: `{_relative_display(result.output_report, repo_root)}`",
            "",
            "## Stage boundary",
            "",
            f"{result.source_key} S2 sequence normalisation only.",
            "",
            "- No record was rejected or parked.",
            "- N-containing rows were retained and flagged, not repaired.",
            "- No target canonicalisation was performed.",
            "- No affinity/evidence/PDB decision was performed.",
            "- No leakage, clustering, balancing or partitioning was performed.",
            "- S3 has not started.",
            "- Constant-region inference was disabled by source contract.",
            "- Dataset A replication RNA-alphabet representation was not built.",
            "",
        ]
    )
    return "\n".join(lines)


def run_aptadiff_s2(
    *,
    repo_root: Path,
    source_key: str,
    input_dir: Path,
    output_dir: Path,
    rules_path: Path,
    policy_path: Path,
    expected_rows: int | None = None,
    check_deterministic_rerun: bool = False,
) -> S2RunResult:
    """Execute AptaDiff Dataset A or B S2 normalisation."""
    if source_key not in {"aptadiff_a", "aptadiff_b"}:
        raise S2NormaliseError(
            f"Unknown AptaDiff S2 source_key={source_key!r}; expected "
            "aptadiff_a or aptadiff_b"
        )
    profile = _aptadiff_production_profile(source_key)
    if expected_rows is None:
        expected_rows = int(profile["expected_rows"])

    repo_root = repo_root.resolve()
    input_dir = input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    input_dir = input_dir.resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    rules_path = (
        rules_path if rules_path.is_absolute() else (repo_root / rules_path)
    ).resolve()
    policy_path = (
        policy_path if policy_path.is_absolute() else (repo_root / policy_path)
    ).resolve()

    canonical_path = input_dir / f"{source_key}_extracted.csv"
    sidecar_path = input_dir / f"{source_key}_source_metadata.csv"
    if not canonical_path.is_file():
        raise S2NormaliseError(f"Missing S1 canonical input: {canonical_path.name}")
    if not sidecar_path.is_file():
        raise S2NormaliseError(f"Missing S1 sidecar input: {sidecar_path.name}")

    raw_path = repo_root / str(profile["raw_path"])
    raw_sha_before: str | None = None
    if expected_rows == profile["expected_rows"]:
        if not raw_path.is_file():
            raise S2NormaliseError(
                f"Missing registered {source_key} raw file"
            )
        digest = _sha256_file(raw_path)
        if digest != profile["raw_sha256"]:
            raise S2NormaliseError(
                f"{source_key} raw SHA-256 does not match registry expectation"
            )
        raw_sha_before = digest

    s1_hash_before = _sha256_file(canonical_path)
    sidecar_hash_before = _sha256_file(sidecar_path)

    rules = load_normalisation_rules(rules_path)
    policy = load_aptadiff_policy(policy_path)
    if policy.source_key != source_key:
        raise S2NormaliseError(
            f"policy source_key {policy.source_key!r} does not match "
            f"requested {source_key!r}"
        )
    if policy.apply_approved_trims:
        raise S2NormaliseError("AptaDiff S2 must not apply approved trims")
    if policy.group_inference_key != "disabled":
        raise S2NormaliseError(
            "AptaDiff S2 must keep group-wise inference disabled"
        )
    if policy.construct_scope != CONSTRUCT_SCOPE_RANDOM_REGION_ONLY:
        raise S2NormaliseError(
            "AptaDiff S2 construct_scope must be random_region_only"
        )

    canonical_rows = _read_corpus_csv(canonical_path)
    sidecar_rows = _read_sidecar_csv(sidecar_path)
    aligned_sidecar = _match_sidecar_one_to_one(canonical_rows, sidecar_rows)

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S2NormaliseError(
            f"S1 row count must be {expected_rows}; got {len(canonical_rows)}"
        )

    documented_target = aptadiff_expected_documented_target(source_key)
    for index, (row, meta) in enumerate(
        zip(canonical_rows, aligned_sidecar, strict=True), start=1
    ):
        if row["source_db"] != source_key:
            raise S2NormaliseError(
                f"row {index}: source_db must be {source_key}"
            )
        if expected_rows == profile["expected_rows"]:
            if row["source_dataset"] != profile["source_dataset"]:
                raise S2NormaliseError(
                    f"row {index}: source_dataset must be "
                    f"{profile['source_dataset']}"
                )
            if meta.get("aptadiff_documented_target") != documented_target:
                raise S2NormaliseError(
                    f"row {index}: documented target must remain {documented_target}"
                )

    stats = AptaDiffS2Stats()
    stats.s1_rows = len(canonical_rows)
    stats.source_metadata_rows = len(aligned_sidecar)
    stats.order_preserved = True
    stats.provenance_preserved = True
    stats.sequence_raw_unchanged = True
    stats.target_name_raw_unchanged = True
    stats.notes_unchanged = True
    stats.known_motifs_scanned = ()
    stats.constant_region_reason = CONSTANT_INFERENCE_DISABLED_REASON

    normalised_rows: list[dict[str, str]] = []
    qc_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []

    for s1_row, meta_row in zip(canonical_rows, aligned_sidecar, strict=True):
        result = normalise_aptadiff_record(
            s1_row,
            meta_row,
            policy=policy,
            rules=rules,
        )
        if result.canonical["record_id"] != s1_row["record_id"]:
            stats.order_preserved = False
            raise S2NormaliseError("S2 altered record_id or row identity")
        if result.canonical["native_id"] != s1_row["native_id"]:
            raise S2NormaliseError("S2 altered native_id")
        if result.canonical["sequence_raw"] != s1_row["sequence_raw"]:
            stats.sequence_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter sequence_raw")
        if result.canonical["target_name_raw"] != s1_row["target_name_raw"]:
            stats.target_name_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter target_name_raw")
        if result.canonical["notes"] != s1_row["notes"]:
            stats.notes_unchanged = False
            raise S2NormaliseError("S2 must not alter notes")
        if result.canonical["source_db"] != s1_row["source_db"]:
            stats.provenance_preserved = False
            raise S2NormaliseError("S2 must not alter source_db")
        if result.canonical["source_dataset"] != s1_row["source_dataset"]:
            stats.provenance_preserved = False
            raise S2NormaliseError("S2 must not alter source_dataset")
        if result.canonical["sequence_core"] != result.canonical["sequence_full"]:
            raise S2NormaliseError(
                "AptaDiff S2 must not apply trims; sequence_core must equal "
                "sequence_full"
            )
        if result.canonical["molecule_type"] != "ssDNA":
            raise S2NormaliseError(
                "AptaDiff S2 molecule_type must remain ssDNA under the "
                "source contract"
            )
        if result.canonical["chemistry"] != "DNA":
            raise S2NormaliseError(
                "AptaDiff S2 chemistry must remain DNA under the source contract"
            )
        if result.canonical["t_to_u_applied"] != "false":
            raise S2NormaliseError("AptaDiff S2 must not apply T→U")
        if result.canonical["sequence_full"] and (
            result.canonical["construct_scope"] != CONSTRUCT_SCOPE_RANDOM_REGION_ONLY
        ):
            raise S2NormaliseError(
                "AptaDiff S2 construct_scope must be random_region_only"
            )
        if result.canonical["detected_constant_5p"] or result.canonical[
            "detected_constant_3p"
        ]:
            raise S2NormaliseError(
                "AptaDiff S2 must not populate detected constant regions"
            )
        if not aptadiff_s4_fields_are_empty(result.canonical):
            raise S2NormaliseError(
                "AptaDiff S2 must not populate target/evidence/affinity fields"
            )
        length_full = result.canonical["sequence_length_full"]
        if length_full != "":
            if int(length_full) != len(result.canonical["sequence_full"]):
                raise S2NormaliseError(
                    "sequence_length_full must equal len(sequence_full)"
                )
            if int(result.canonical["sequence_length_core"]) != len(
                result.canonical["sequence_core"]
            ):
                raise S2NormaliseError(
                    "sequence_length_core must equal len(sequence_core)"
                )
        normalised_rows.append(result.canonical)
        qc_rows.append(result.qc)
        if aptadiff_is_review_candidate(result.canonical["qc_flags"]):
            review_rows.append(result.qc)
        update_aptadiff_stats_from_row(stats, result)

    stats.s2_rows = len(normalised_rows)
    stats.unique_record_ids = len({row["record_id"] for row in normalised_rows})
    stats.unique_native_ids = len({row["native_id"] for row in normalised_rows})
    stats.records_dropped = 0
    stats.records_parked = 0
    stats.constant_region_proposals = 0
    stats.groups_considered = 0
    stats.groups_meeting_min_size = 0
    stats.five_prime_proposals = 0
    stats.three_prime_proposals = 0
    stats.records_with_medium_confidence_proposal = 0
    stats.high_confidence_trims_applied = 0
    stats.applied_trims = 0
    stats.known_motif_detection_count = 0

    if expected_rows == profile["expected_rows"]:
        if stats.s2_rows != profile["expected_rows"]:
            raise S2NormaliseError(
                f"S2 must preserve {profile['expected_rows']} rows; "
                f"got {stats.s2_rows}"
            )
        if stats.unique_record_ids != profile["expected_rows"]:
            raise S2NormaliseError("S2 record_id values are not unique")
        if stats.s1_rows - stats.s2_rows != 0:
            raise S2NormaliseError("S2 row disappearance must be 0")
        for key, expected in profile["molecule"].items():
            got = stats.molecule_type_counts.get(key, 0)
            if got != expected:
                raise S2NormaliseError(
                    f"molecule_type {key} expected {expected}; got {got}"
                )
        for key, expected in profile["chemistry"].items():
            got = stats.chemistry_counts.get(key, 0)
            if got != expected:
                raise S2NormaliseError(
                    f"chemistry {key} expected {expected}; got {got}"
                )
        for key, expected in profile["alphabet"].items():
            got = stats.alphabet_counts.get(key, 0)
            if got != expected:
                raise S2NormaliseError(
                    f"alphabet {key} expected {expected}; got {got}"
                )
        if stats.t_to_u_count != 0:
            raise S2NormaliseError("AptaDiff S2 T→U count must be 0")
        if stats.applied_trims != 0 or stats.core_differs_from_full != 0:
            raise S2NormaliseError("AptaDiff S2 must not apply trims")
        if stats.length_36_count != profile["expected_rows"]:
            raise S2NormaliseError(
                f"every {source_key} S2 row must be length 36; "
                f"got {stats.length_36_count}"
            )
        nonempty_target = sum(1 for row in normalised_rows if row["target_name_raw"])
        if nonempty_target:
            raise S2NormaliseError(
                "AptaDiff S2 must not populate target_name_raw"
            )
        construct_ok = stats.construct_scope_counts.get(
            CONSTRUCT_SCOPE_RANDOM_REGION_ONLY, 0
        )
        if construct_ok != profile["expected_rows"]:
            raise S2NormaliseError(
                "every AptaDiff S2 row must have construct_scope="
                "random_region_only"
            )

    proposals = empty_constant_proposals()
    if proposals:
        raise S2NormaliseError(
            "AptaDiff S2 must emit an empty constant-region proposal artefact"
        )

    for row in normalised_rows:
        if row["sequence_core"] != row["sequence_full"]:
            raise S2NormaliseError(
                "AptaDiff S2 must keep sequence_core equal to sequence_full"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_normalised = output_dir / f"{source_key}_normalised.csv"
    out_qc = output_dir / f"{source_key}_s2_qc.csv"
    out_review = output_dir / f"{source_key}_s2_review_candidates.csv"
    out_proposals = output_dir / f"detected_constants_{source_key}.csv"
    out_report = output_dir / f"{source_key}_s2_report.md"

    write_corpus_csv_atomic(out_normalised, normalised_rows)
    write_csv_atomic(out_qc, APTADIFF_S2_QC_COLUMNS, qc_rows)
    write_csv_atomic(out_review, APTADIFF_S2_QC_COLUMNS, review_rows)
    write_csv_atomic(out_proposals, APTADIFF_CONSTANT_PROPOSAL_COLUMNS, proposals)

    s1_hash_after = _sha256_file(canonical_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    inputs_unchanged = (
        s1_hash_before == s1_hash_after
        and sidecar_hash_before == sidecar_hash_after
    )
    if not inputs_unchanged:
        raise S2NormaliseError("S1 inputs were modified during S2 execution")

    raw_sha_after: str | None = None
    raw_sha_unchanged: bool | None = None
    if raw_sha_before is not None:
        digest = _sha256_file(raw_path)
        if digest != raw_sha_before or digest != profile["raw_sha256"]:
            raise S2NormaliseError(f"{source_key} raw SHA changed during S2")
        raw_sha_after = digest
        raw_sha_unchanged = True

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "normalised": _sha256_file(out_normalised),
            "qc": _sha256_file(out_qc),
            "review": _sha256_file(out_review),
            "proposals": _sha256_file(out_proposals),
        }
        second = run_aptadiff_s2(
            repo_root=repo_root,
            source_key=source_key,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=policy_path,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["normalised"] == _sha256_file(second.output_normalised)
            and first_hashes["qc"] == _sha256_file(second.output_qc)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["proposals"] == _sha256_file(second.output_proposals)
        )
        if not deterministic_ok:
            raise S2NormaliseError(
                "S2 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S2RunResult(
        source_key=source_key,
        stats=stats,
        output_normalised=out_normalised,
        output_qc=out_qc,
        output_review=out_review,
        output_proposals=out_proposals,
        output_report=out_report,
        s1_hash_before=s1_hash_before,
        s1_hash_after=s1_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        raw_sha256=raw_sha_after,
        raw_sha_unchanged=raw_sha_unchanged,
    )
    report_text = build_aptadiff_s2_report(
        repo_root=repo_root,
        result=run_result,
        rules_path=rules_path,
        policy_path=policy_path,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in report_text:
        raise S2NormaliseError("S2 report must not contain absolute repository paths")
    forbidden_tokens = (
        canonical_rows[0]["sequence_raw"] if canonical_rows else ""
    )
    if forbidden_tokens and forbidden_tokens in report_text:
        raise S2NormaliseError("S2 report must not contain sequence values")
    _write_text_atomic(out_report, report_text)
    return run_result


def _ncbi_nuc_raw_hashes(repo_root: Path) -> dict[str, str]:
    """Return relative-path → SHA-256 for every registered NCBI GenBank file."""
    observed: dict[str, str] = {}
    for relative, expected in EXPECTED_NCBI_NUC_RAW_SHA256.items():
        path = repo_root / relative
        if not path.is_file():
            raise S2NormaliseError(f"Missing registered NCBI Nucleotide file: {relative}")
        digest = _sha256_file(path)
        if digest != expected:
            raise S2NormaliseError(
                f"NCBI Nucleotide raw SHA-256 does not match registry for {relative}"
            )
        observed[relative] = digest
    return observed


def build_ncbi_nuc_s2_report(
    *,
    repo_root: Path,
    result: S2RunResult,
    rules_path: Path,
    policy_path: Path,
) -> str:
    """Build an aggregate-only Markdown NCBI Nucleotide S2 report (no sequences)."""
    stats = result.stats
    if not isinstance(stats, NcbiNucS2Stats):
        raise S2NormaliseError("NCBI Nucleotide report requires NcbiNucS2Stats")
    full_min, full_med, full_max = summarise_ncbi_nuc_lengths(stats.length_full_values)
    core_min, core_med, core_max = summarise_ncbi_nuc_lengths(stats.length_core_values)
    scanned = ", ".join(f"`{name}`" for name in stats.known_motifs_scanned) or "(none)"
    lines = [
        "# NCBI Nucleotide S2 normalisation report",
        "",
        "Aggregate counts only. Deposited sequences are not included.",
        "",
        "## Reconciliation",
        "",
        f"- Source key: `ncbi_nuc`",
        f"- Source dataset: `{EXPECTED_NCBI_NUC_SOURCE_DATASET}`",
        f"- S1 canonical rows: `{stats.s1_rows}`",
        f"- Source-metadata rows: `{stats.source_metadata_rows}`",
        f"- S2 output rows: `{stats.s2_rows}`",
        f"- Records dropped: `{stats.records_dropped}`",
        f"- Records parked: `{stats.records_parked}`",
        f"- Unique record_id values: `{stats.unique_record_ids}`",
        f"- Unique native_id values: `{stats.unique_native_ids}`",
        f"- Row disappearance: `{stats.s1_rows - stats.s2_rows}`",
        f"- S1 row order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        f"- S1 provenance preserved: "
        f"`{'pass' if stats.provenance_preserved else 'fail'}`",
        f"- sequence_raw unchanged: "
        f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
        f"- target_name_raw unchanged: "
        f"`{'pass' if stats.target_name_raw_unchanged else 'fail'}`",
        f"- notes unchanged: `{'pass' if stats.notes_unchanged else 'fail'}`",
        f"- pubmed_id unchanged: `{'pass' if stats.pubmed_id_unchanged else 'fail'}`",
        f"- Missing sequence rows: `{stats.missing_sequence_rows}`",
        f"- Nonempty sequence rows: `{stats.nonempty_sequence_rows}`",
        f"- Shared rules: `{_relative_display(rules_path, repo_root)}`",
        f"- Source policy: `{_relative_display(policy_path, repo_root)}`",
        "",
        "## Molecule / chemistry",
        "",
        "Experimental molecule identity is accession-approved from structured",
        "GenBank evidence (LOCUS RNA state plus RNA-compatible `/mol_type`",
        "and RNA-aptamer source annotation for the five RNA records; LOCUS DNA",
        "plus `/mol_type=\"other DNA\"` for QT662269). Alphabet, patent titles,",
        "and ENA overlap are not used to assign molecule type. Remaining",
        "ACCESSION values stay `unknown`. Generic `DNA` is used where the",
        "live schema allows it; ssDNA is not inferred from canonical DNA",
        "aptamer convention.",
        "",
        "### Canonical molecule_type",
        "",
    ]
    for name, count in _count_sorted(stats.molecule_type_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### Canonical chemistry", ""])
    for name, count in _count_sorted(stats.chemistry_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Reported alphabet",
            "",
            "Shared alphabet vocabulary is `RNA` / `DNA_T` / `mixed_T_U` /",
            "`ambiguous` / `invalid`. A/C/G-only values use the shared",
            "classifier tie-break and do not manufacture molecule type.",
            "",
        ]
    )
    for name, count in _count_sorted(stats.alphabet_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Computational transcription",
            "",
            "T→U is applied only for the five source-supported RNA records.",
            "Unresolved T-alphabet records and the DNA record are not",
            "transcribed.",
            "",
            f"- total `t_to_u_applied=true`: `{stats.t_to_u_count}`",
            "",
        ]
    )
    if stats.t_to_u_by_molecule:
        for name, count in _count_sorted(stats.t_to_u_by_molecule):
            lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Display cleaning",
            "",
        ]
    )
    if stats.transformation_counts:
        for name, count in _count_sorted(stats.transformation_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## QC",
            "",
            f"- Invalid character rows: `{stats.invalid_character_count}`",
            f"- Alignment-gap rows: `{stats.alignment_gaps_count}`",
            f"- Ambiguous base rows: `{stats.ambiguous_base_count}`",
            f"- Mixed T/U rows: `{stats.mixed_t_u_count}`",
            f"- Core below minimum length: `{stats.core_below_min_count}`",
            f"- Core above maximum length: `{stats.core_above_max_count}`",
            f"- Source length mismatches: `{stats.length_mismatch_count}`",
            f"- Rows with any QC flag: `{stats.rows_with_any_qc_flag}`",
            f"- Rows with multiple QC flags: `{stats.rows_with_multiple_qc_flags}`",
            f"- Review-candidate rows: `{stats.review_candidate_rows}`",
            "",
        ]
    )
    for name, count in _count_sorted(stats.qc_flag_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### review reasons", ""])
    if stats.review_reason_counts:
        for name, count in _count_sorted(stats.review_reason_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## Length",
            "",
            "Lengths are computed from the shared normalised representation.",
            "These buckets are descriptive at S2; they do not filter records.",
            "",
            f"- sequence_length_full min / median / max: "
            f"`{full_min}` / `{full_med}` / `{full_max}`",
            f"- sequence_length_core min / median / max: "
            f"`{core_min}` / `{core_med}` / `{core_max}`",
            "",
            "### sequence_length_full buckets",
            "",
        ]
    )
    for name, count in _count_sorted(stats.length_full_buckets):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### sequence_length_core buckets", ""])
    for name, count in _count_sorted(stats.length_core_buckets):
        lines.append(f"- `{name}`: `{count}`")
    if stats.core_differs_from_full == 0:
        lines.extend(
            [
                "",
                "Full and core length distributions are identical because no",
                "trim was applied (`sequence_core == sequence_full`).",
            ]
        )
    lines.extend(
        [
            "",
            "## Construct / trim state",
            "",
            "Construct scope is assigned only from explicit GenBank source",
            "evidence (primer, reverse primer, poly-A fragment, or DNA",
            "transcription template). cDNA records with unresolved aptamer",
            "boundaries remain `unknown`. No aptamer core is extracted.",
            "",
            "### construct_scope",
            "",
        ]
    )
    for name, count in _count_sorted(stats.construct_scope_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### source_object_class", ""])
    for name, count in _count_sorted(stats.source_object_class_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_status", ""])
    for name, count in _count_sorted(stats.trim_status_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "### trim_confidence", ""])
    for name, count in _count_sorted(stats.trim_confidence_counts):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Constant-region detection",
            "",
            "group-wise inference disabled for ncbi_nuc in this run. No",
            "artificial grouping by target, title, molecule, accession",
            "prefix, or patent family was created. Known-motif detections",
            "are proposals only (`applied=false`).",
            "",
            f"- Approved known motifs scanned: {scanned}",
            f"- Records with known-motif detection: "
            f"`{stats.known_motif_detection_count}`",
            f"- Genuine proposal rows: `{stats.constant_region_proposals}`",
            f"- 5′ known-motif proposals: `{stats.five_prime_proposals}`",
            f"- 3′ known-motif proposals: `{stats.three_prime_proposals}`",
            f"- Group-consensus proposals: `0`",
            f"- Groups considered: `{stats.groups_considered}`",
            f"- Groups meeting minimum size: `{stats.groups_meeting_min_size}`",
            f"- Records associated with medium-confidence proposals: "
            f"`{stats.records_with_medium_confidence_proposal}`",
            f"- Previously approved high-confidence trims applied: "
            f"`{stats.high_confidence_trims_applied}`",
            f"- Records actually trimmed: `{stats.applied_trims}`",
            f"- Rows where sequence_core != sequence_full: "
            f"`{stats.core_differs_from_full}`",
            f"- Reason: `{stats.constant_region_reason}`",
            "",
            "### proposal sources",
            "",
        ]
    )
    if stats.proposal_source_counts:
        for name, count in _count_sorted(stats.proposal_source_counts):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## Invariants",
            "",
            f"- sequence_raw unchanged: "
            f"`{'pass' if stats.sequence_raw_unchanged else 'fail'}`",
            f"- Records retained: `{stats.s2_rows}`",
            f"- Provenance unchanged: "
            f"`{'pass' if stats.provenance_preserved else 'fail'}`",
            "- S4 target/evidence/affinity/PDB/cluster/partition fields remain blank",
            (
                f"- Raw input hashes unchanged: "
                f"`{'pass' if result.raw_sha_unchanged else 'fail'}`"
                if result.raw_sha_unchanged is not None
                else "- Raw input hashes unchanged: `not_checked`"
            ),
            f"- S1 inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            "",
            f"- S1 canonical hash before: `{result.s1_hash_before}`",
            f"- S1 canonical hash after: `{result.s1_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            (
                f"- Combined raw SHA-256 token: `{result.raw_sha256}`"
                if result.raw_sha256
                else "- Combined raw SHA-256 token: `not_checked`"
            ),
            "",
            "## Outputs",
            "",
            f"- Normalised: "
            f"`{_relative_display(result.output_normalised, repo_root)}`",
            f"- QC: `{_relative_display(result.output_qc, repo_root)}`",
            f"- Review candidates: "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Detected constants / proposals: "
            f"`{_relative_display(result.output_proposals, repo_root)}`",
            f"- Report: `{_relative_display(result.output_report, repo_root)}`",
            "",
            "## Stage boundary",
            "",
            "NCBI Nucleotide S2 sequence/molecule/construct normalisation only.",
            "",
            "- No record was rejected or parked.",
            "- No target extraction or canonicalisation was performed.",
            "- No affinity/evidence/PDB decision was performed.",
            "- No leakage, clustering, balancing or partitioning was performed.",
            "- No NCBI↔ENA deduplication was performed.",
            "- S3 has not started.",
            "- CHECKPOINT-1 has not been opened.",
            "- Known-motif detections were not applied as trims.",
            "- group-wise inference disabled for ncbi_nuc in this run.",
            "",
        ]
    )
    return "\n".join(lines)


def run_ncbi_nuc_s2(
    *,
    repo_root: Path,
    input_dir: Path,
    output_dir: Path,
    rules_path: Path,
    policy_path: Path,
    expected_rows: int | None = EXPECTED_NCBI_NUC_ROWS,
    check_deterministic_rerun: bool = False,
) -> S2RunResult:
    """Execute NCBI Nucleotide S2 normalisation."""
    repo_root = repo_root.resolve()
    input_dir = input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    input_dir = input_dir.resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    rules_path = (
        rules_path if rules_path.is_absolute() else (repo_root / rules_path)
    ).resolve()
    policy_path = (
        policy_path if policy_path.is_absolute() else (repo_root / policy_path)
    ).resolve()

    canonical_path = input_dir / "ncbi_nuc_extracted.csv"
    sidecar_path = input_dir / "ncbi_nuc_source_metadata.csv"
    if not canonical_path.is_file():
        raise S2NormaliseError(f"Missing S1 canonical input: {canonical_path.name}")
    if not sidecar_path.is_file():
        raise S2NormaliseError(f"Missing S1 sidecar input: {sidecar_path.name}")

    raw_sha_before: str | None = None
    if expected_rows == EXPECTED_NCBI_NUC_ROWS:
        observed_raw = _ncbi_nuc_raw_hashes(repo_root)
        raw_sha_before = "|".join(
            f"{path}:{digest}" for path, digest in sorted(observed_raw.items())
        )
        s1_expected = _sha256_file(canonical_path)
        sidecar_expected = _sha256_file(sidecar_path)
        if s1_expected != EXPECTED_NCBI_NUC_S1_CANONICAL_SHA256:
            raise S2NormaliseError(
                "ncbi_nuc S1 canonical SHA-256 does not match the accepted S1 freeze"
            )
        if sidecar_expected != EXPECTED_NCBI_NUC_S1_SIDECAR_SHA256:
            raise S2NormaliseError(
                "ncbi_nuc S1 sidecar SHA-256 does not match the accepted S1 freeze"
            )

    s1_hash_before = _sha256_file(canonical_path)
    sidecar_hash_before = _sha256_file(sidecar_path)

    rules = load_normalisation_rules(rules_path)
    policy = load_ncbi_nuc_policy(policy_path)
    if policy.apply_approved_trims:
        raise S2NormaliseError("ncbi_nuc S2 must not apply approved trims")
    if policy.group_inference_key != "disabled":
        raise S2NormaliseError("ncbi_nuc S2 must keep group-wise inference disabled")

    canonical_rows = _read_corpus_csv(canonical_path)
    sidecar_rows = _read_sidecar_csv(sidecar_path)
    aligned_sidecar = _match_sidecar_one_to_one(canonical_rows, sidecar_rows)

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S2NormaliseError(
            f"S1 row count must be {expected_rows}; got {len(canonical_rows)}"
        )

    for index, row in enumerate(canonical_rows, start=1):
        if row["source_db"] != "ncbi_nuc":
            raise S2NormaliseError(f"row {index}: source_db must be ncbi_nuc")
        if expected_rows == EXPECTED_NCBI_NUC_ROWS:
            if row["source_dataset"] != EXPECTED_NCBI_NUC_SOURCE_DATASET:
                raise S2NormaliseError(
                    f"row {index}: source_dataset must be "
                    f"{EXPECTED_NCBI_NUC_SOURCE_DATASET}"
                )
            if row["target_name_raw"] != "":
                raise S2NormaliseError("ncbi_nuc S2 must not populate target_name_raw")
            if row["accession"] != "":
                raise S2NormaliseError("ncbi_nuc canonical accession must remain empty")

    stats = NcbiNucS2Stats()
    stats.s1_rows = len(canonical_rows)
    stats.source_metadata_rows = len(aligned_sidecar)
    stats.order_preserved = True
    stats.provenance_preserved = True
    stats.sequence_raw_unchanged = True
    stats.target_name_raw_unchanged = True
    stats.notes_unchanged = True
    stats.pubmed_id_unchanged = True
    stats.known_motifs_scanned = tuple(
        motif.name for motif in rules.known_non_core_motifs
    )
    stats.constant_region_reason = (
        "group-wise inference disabled for ncbi_nuc in this run;"
        "known_motif_detection_only_not_applied"
    )

    normalised_rows: list[dict[str, str]] = []
    qc_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    row_results: list = []

    for s1_row, meta_row in zip(canonical_rows, aligned_sidecar, strict=True):
        result = normalise_ncbi_nuc_record(
            s1_row,
            meta_row,
            policy=policy,
            rules=rules,
        )
        if result.canonical["record_id"] != s1_row["record_id"]:
            stats.order_preserved = False
            raise S2NormaliseError("S2 altered record_id or row identity")
        if result.canonical["native_id"] != s1_row["native_id"]:
            raise S2NormaliseError("S2 altered native_id")
        if result.canonical["sequence_raw"] != s1_row["sequence_raw"]:
            stats.sequence_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter sequence_raw")
        if result.canonical["target_name_raw"] != s1_row["target_name_raw"]:
            stats.target_name_raw_unchanged = False
            raise S2NormaliseError("S2 must not alter target_name_raw")
        if result.canonical["notes"] != s1_row["notes"]:
            stats.notes_unchanged = False
            raise S2NormaliseError("S2 must not alter notes")
        if result.canonical["pubmed_id"] != s1_row["pubmed_id"]:
            stats.pubmed_id_unchanged = False
            raise S2NormaliseError("S2 must not alter pubmed_id")
        if result.canonical["publication"] != s1_row["publication"]:
            raise S2NormaliseError("S2 must not alter publication")
        if result.canonical["source_db"] != s1_row["source_db"]:
            stats.provenance_preserved = False
            raise S2NormaliseError("S2 must not alter source_db")
        if result.canonical["source_dataset"] != s1_row["source_dataset"]:
            stats.provenance_preserved = False
            raise S2NormaliseError("S2 must not alter source_dataset")
        if result.canonical["sequence_core"] != result.canonical["sequence_full"]:
            raise S2NormaliseError(
                "ncbi_nuc S2 must not apply trims; sequence_core must equal "
                "sequence_full"
            )
        if result.canonical["molecule_type"] == "ssDNA":
            raise S2NormaliseError(
                "ncbi_nuc must not coerce DNA to ssDNA"
            )
        length_full = result.canonical["sequence_length_full"]
        if length_full != "":
            if int(length_full) != len(result.canonical["sequence_full"]):
                raise S2NormaliseError(
                    "sequence_length_full must equal len(sequence_full)"
                )
            if int(result.canonical["sequence_length_core"]) != len(
                result.canonical["sequence_core"]
            ):
                raise S2NormaliseError(
                    "sequence_length_core must equal len(sequence_core)"
                )
        normalised_rows.append(result.canonical)
        qc_rows.append(result.qc)
        row_results.append(result)
        if ncbi_nuc_is_review_candidate(result.qc):
            review_rows.append(result.qc)
        update_ncbi_nuc_stats_from_row(stats, result)

    stats.s2_rows = len(normalised_rows)
    stats.unique_record_ids = len({row["record_id"] for row in normalised_rows})
    stats.unique_native_ids = len({row["native_id"] for row in normalised_rows})
    stats.records_dropped = 0
    stats.records_parked = 0
    finalise_ncbi_nuc_review_stats(stats, row_results)

    if expected_rows == EXPECTED_NCBI_NUC_ROWS:
        if stats.s2_rows != EXPECTED_NCBI_NUC_ROWS:
            raise S2NormaliseError(
                f"S2 must preserve {EXPECTED_NCBI_NUC_ROWS} rows; got {stats.s2_rows}"
            )
        if stats.unique_record_ids != EXPECTED_NCBI_NUC_ROWS:
            raise S2NormaliseError("S2 record_id values are not unique")
        if stats.s1_rows - stats.s2_rows != 0:
            raise S2NormaliseError("S2 row disappearance must be 0")
        for key, expected in EXPECTED_NCBI_NUC_MOLECULE.items():
            got = stats.molecule_type_counts.get(key, 0)
            if got != expected:
                raise S2NormaliseError(
                    f"molecule_type {key} expected {expected}; got {got}"
                )
        extra_molecules = [
            key
            for key, count in stats.molecule_type_counts.items()
            if key not in EXPECTED_NCBI_NUC_MOLECULE and count
        ]
        if extra_molecules:
            raise S2NormaliseError(
                f"unexpected molecule_type values: {extra_molecules}"
            )
        for key, expected in EXPECTED_NCBI_NUC_CHEMISTRY.items():
            got = stats.chemistry_counts.get(key, 0)
            if got != expected:
                raise S2NormaliseError(
                    f"chemistry {key} expected {expected}; got {got}"
                )
        if stats.t_to_u_count != EXPECTED_NCBI_NUC_T_TO_U:
            raise S2NormaliseError(
                f"ncbi_nuc T→U count expected {EXPECTED_NCBI_NUC_T_TO_U}; "
                f"got {stats.t_to_u_count}"
            )
        if stats.core_differs_from_full != 0:
            raise S2NormaliseError(
                "ncbi_nuc S2 applied a trim; sequence_core must equal sequence_full"
            )
        nonempty_target = sum(1 for row in normalised_rows if row["target_name_raw"])
        if nonempty_target:
            raise S2NormaliseError("ncbi_nuc S2 must not populate target_name_raw")

    known_motif_proposals = build_ncbi_nuc_known_motif_proposals(row_results)
    assert_ncbi_nuc_genuine_proposals(known_motif_proposals)

    stats.constant_region_proposals = len(known_motif_proposals)
    stats.groups_considered = 0
    stats.groups_meeting_min_size = 0
    stats.five_prime_proposals = sum(
        1 for row in known_motif_proposals if row["side"] == "five_prime"
    )
    stats.three_prime_proposals = sum(
        1 for row in known_motif_proposals if row["side"] == "three_prime"
    )
    stats.records_with_medium_confidence_proposal = 0
    stats.high_confidence_trims_applied = 0
    stats.applied_trims = 0
    for row in known_motif_proposals:
        source = row["proposal_source"]
        stats.proposal_source_counts[source] = (
            stats.proposal_source_counts.get(source, 0) + 1
        )

    for row in normalised_rows:
        if row["sequence_core"] != row["sequence_full"]:
            raise S2NormaliseError(
                "known-motif detections must not mutate sequence_core"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_normalised = output_dir / "ncbi_nuc_normalised.csv"
    out_qc = output_dir / "ncbi_nuc_s2_qc.csv"
    out_review = output_dir / "ncbi_nuc_s2_review_candidates.csv"
    out_proposals = output_dir / "detected_constants_ncbi_nuc.csv"
    out_report = output_dir / "ncbi_nuc_s2_report.md"

    write_corpus_csv_atomic(out_normalised, normalised_rows)
    write_csv_atomic(out_qc, NCBI_NUC_S2_QC_COLUMNS, qc_rows)
    write_csv_atomic(out_review, NCBI_NUC_S2_QC_COLUMNS, review_rows)
    write_csv_atomic(
        out_proposals, NCBI_NUC_CONSTANT_PROPOSAL_COLUMNS, known_motif_proposals
    )

    s1_hash_after = _sha256_file(canonical_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    inputs_unchanged = (
        s1_hash_before == s1_hash_after
        and sidecar_hash_before == sidecar_hash_after
    )
    if not inputs_unchanged:
        raise S2NormaliseError("S1 inputs were modified during S2 execution")

    raw_sha_after: str | None = None
    raw_sha_unchanged: bool | None = None
    if raw_sha_before is not None:
        observed_after = _ncbi_nuc_raw_hashes(repo_root)
        digest = "|".join(
            f"{path}:{value}" for path, value in sorted(observed_after.items())
        )
        if digest != raw_sha_before:
            raise S2NormaliseError("NCBI Nucleotide raw SHA-256 values changed during S2")
        raw_sha_after = digest
        raw_sha_unchanged = True

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "normalised": _sha256_file(out_normalised),
            "qc": _sha256_file(out_qc),
            "review": _sha256_file(out_review),
            "proposals": _sha256_file(out_proposals),
        }
        second = run_ncbi_nuc_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=policy_path,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["normalised"] == _sha256_file(second.output_normalised)
            and first_hashes["qc"] == _sha256_file(second.output_qc)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["proposals"] == _sha256_file(second.output_proposals)
        )
        if not deterministic_ok:
            raise S2NormaliseError(
                "S2 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S2RunResult(
        source_key="ncbi_nuc",
        stats=stats,
        output_normalised=out_normalised,
        output_qc=out_qc,
        output_review=out_review,
        output_proposals=out_proposals,
        output_report=out_report,
        s1_hash_before=s1_hash_before,
        s1_hash_after=s1_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        raw_sha256=raw_sha_after,
        raw_sha_unchanged=raw_sha_unchanged,
    )
    report_text = build_ncbi_nuc_s2_report(
        repo_root=repo_root,
        result=run_result,
        rules_path=rules_path,
        policy_path=policy_path,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in report_text:
        raise S2NormaliseError("S2 report must not contain absolute repository paths")
    forbidden_tokens = (
        canonical_rows[0]["sequence_raw"] if canonical_rows else ""
    )
    if forbidden_tokens and forbidden_tokens in report_text:
        raise S2NormaliseError("S2 report must not contain sequence values")
    _write_text_atomic(out_report, report_text)
    return run_result


def run_s2_normalisation(
    *,
    repo_root: Path,
    source_key: str,
    input_dir: Path,
    output_dir: Path,
    rules_path: Path,
    source_policy: Path,
    expected_rows: int | None = None,
    check_deterministic_rerun: bool = False,
) -> S2RunResult:
    """Dispatch S2 normalisation for one source key."""
    if source_key == "aptabase":
        return run_aptabase_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=source_policy,
            expected_rows=(
                EXPECTED_APTABASE_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "utexas":
        return run_utexas_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=source_policy,
            expected_rows=(
                EXPECTED_UTEXAS_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "aptadb":
        return run_aptadb_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=source_policy,
            expected_rows=(
                EXPECTED_APTADB_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "riboaptamer":
        return run_riboaptamer_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=source_policy,
            expected_rows=(
                EXPECTED_RIBOAPTAMER_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "aptaindex":
        return run_aptaindex_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=source_policy,
            expected_rows=(
                EXPECTED_APTAINDEX_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "ena":
        return run_ena_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=source_policy,
            expected_rows=(
                EXPECTED_ENA_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "aptamerbase":
        return run_aptamerbase_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=source_policy,
            expected_rows=(
                EXPECTED_APTAMERBASE_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key in {"aptadiff_a", "aptadiff_b"}:
        return run_aptadiff_s2(
            repo_root=repo_root,
            source_key=source_key,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=source_policy,
            expected_rows=expected_rows,
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "ncbi_nuc":
        return run_ncbi_nuc_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            policy_path=source_policy,
            expected_rows=(
                EXPECTED_NCBI_NUC_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    raise S2NormaliseError(f"Unknown S2 source_key={source_key!r}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "S2: normalise extracted source sequences into the canonical corpus "
            "with QC artefacts. Does not filter or park records."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source key to normalise (e.g. aptabase)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Directory containing S1 outputs (default: data/interim/extracted)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory beneath data/interim "
            "(default: data/interim/normalised)"
        ),
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=None,
        help="Shared sequence-normalisation rules JSON",
    )
    parser.add_argument(
        "--source-policy",
        type=Path,
        default=None,
        help="Source-specific normalisation policy JSON",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detected)",
    )
    parser.add_argument(
        "--expected-rows",
        type=int,
        default=None,
        help="Override expected row count (tests only)",
    )
    parser.add_argument(
        "--check-deterministic-rerun",
        action="store_true",
        help="Re-run once and require byte-identical outputs",
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
            raise S2NormaliseError(f"Repository root does not exist: {repo_root}")

        input_dir = (
            args.input_dir
            if args.input_dir is not None
            else Path("data/interim/extracted")
        )
        output_dir = (
            args.output_dir
            if args.output_dir is not None
            else Path("data/interim/normalised")
        )
        rules_path = (
            args.rules
            if args.rules is not None
            else Path("config/sequence_normalisation_rules.json")
        )
        if args.source_policy is not None:
            policy_path = args.source_policy
        elif args.source == "aptabase":
            policy_path = Path("config/source_normalisation/aptabase.json")
        elif args.source == "utexas":
            policy_path = Path("config/source_normalisation/utexas.json")
        elif args.source == "aptadb":
            policy_path = Path("config/source_normalisation/aptadb.json")
        elif args.source == "riboaptamer":
            policy_path = Path("config/source_normalisation/riboaptamer.json")
        elif args.source == "aptaindex":
            policy_path = Path("config/source_normalisation/aptaindex.json")
        elif args.source == "ena":
            policy_path = Path("config/source_normalisation/ena.json")
        elif args.source == "aptamerbase":
            policy_path = Path("config/source_normalisation/aptamerbase.json")
        elif args.source == "aptadiff_a":
            policy_path = Path("config/source_normalisation/aptadiff_a.json")
        elif args.source == "aptadiff_b":
            policy_path = Path("config/source_normalisation/aptadiff_b.json")
        elif args.source == "ncbi_nuc":
            policy_path = Path("config/source_normalisation/ncbi_nuc.json")
        else:
            raise S2NormaliseError(
                "--source-policy is required for unrecognised sources"
            )

        result = run_s2_normalisation(
            repo_root=repo_root,
            source_key=args.source,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=rules_path,
            source_policy=policy_path,
            expected_rows=args.expected_rows,
            check_deterministic_rerun=args.check_deterministic_rerun,
        )
    except (
        S2NormaliseError,
        AptaBaseS2Error,
        AptamerBaseS2Error,
        AptamerBaseRdfError,
        AptaDiffS2Error,
        UTexasS2Error,
        AptaDBS2Error,
        RiboAptamerS2Error,
        AptaIndexS2Error,
        EnaS2Error,
        NcbiNucS2Error,
        CorpusSchemaError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    stats = result.stats
    # Aggregate counts only — never print sequence values.
    extra = ""
    if isinstance(stats, UTexasS2Stats):
        extra = (
            f"\nmolecule_type_counts={dict(sorted(stats.molecule_type_counts.items()))}"
            f"\nchemistry_counts={dict(sorted(stats.chemistry_counts.items()))}"
            f"\ncore_differs_from_full={stats.core_differs_from_full}"
            f"\napplied_trims={stats.applied_trims}"
        )
    elif isinstance(stats, AptaDBS2Stats):
        extra = (
            f"\nmolecule_type_counts={dict(sorted(stats.molecule_type_counts.items()))}"
            f"\nchemistry_counts={dict(sorted(stats.chemistry_counts.items()))}"
            f"\nt_to_u_count={stats.t_to_u_count}"
            f"\ncore_differs_from_full={stats.core_differs_from_full}"
            f"\napplied_trims={stats.applied_trims}"
        )
    elif isinstance(stats, RiboAptamerS2Stats):
        extra = (
            f"\nmolecule_type_counts={dict(sorted(stats.molecule_type_counts.items()))}"
            f"\nchemistry_counts={dict(sorted(stats.chemistry_counts.items()))}"
            f"\nalphabet_counts={dict(sorted(stats.alphabet_counts.items()))}"
            f"\nt_to_u_count={stats.t_to_u_count}"
            f"\nknown_motif_detection_count={stats.known_motif_detection_count}"
            f"\ncore_differs_from_full={stats.core_differs_from_full}"
            f"\napplied_trims={stats.applied_trims}"
            f"\ncontaining_ellipsis_count={stats.containing_ellipsis_count}"
        )
    elif isinstance(stats, AptaIndexS2Stats):
        extra = (
            f"\nmissing_sequence_rows={stats.missing_sequence_rows}"
            f"\npeptide_rows={stats.peptide_rows}"
            f"\nnonempty_nucleic_acid_rows={stats.nonempty_nucleic_acid_rows}"
            f"\nsuccessful_parses={stats.successful_parses}"
            f"\nunsupported_nucleic_parses={stats.unsupported_nucleic_parses}"
            f"\nmolecule_type_counts={dict(sorted(stats.molecule_type_counts.items()))}"
            f"\nchemistry_counts={dict(sorted(stats.chemistry_counts.items()))}"
            f"\nalphabet_counts={dict(sorted(stats.alphabet_counts.items()))}"
            f"\nmapping_class_counts={dict(sorted(stats.mapping_class_counts.items()))}"
            f"\nt_to_u_count={stats.t_to_u_count}"
            f"\nmixed_t_u_count={stats.mixed_t_u_count}"
            f"\ncore_differs_from_full={stats.core_differs_from_full}"
            f"\napplied_trims={stats.applied_trims}"
        )
    elif isinstance(stats, EnaS2Stats):
        extra = (
            f"\nmolecule_type_counts={dict(sorted(stats.molecule_type_counts.items()))}"
            f"\nchemistry_counts={dict(sorted(stats.chemistry_counts.items()))}"
            f"\nalphabet_counts={dict(sorted(stats.alphabet_counts.items()))}"
            f"\nt_to_u_count={stats.t_to_u_count}"
            f"\nprimary_experiment_groups={stats.primary_experiment_groups}"
            f"\ngroups_meeting_min_size={stats.groups_meeting_min_size}"
            f"\nknown_motif_detection_count={stats.known_motif_detection_count}"
            f"\ncore_differs_from_full={stats.core_differs_from_full}"
            f"\napplied_trims={stats.applied_trims}"
            f"\nreview_candidate_rows={stats.review_candidate_rows}"
        )
    elif isinstance(stats, AptamerBaseS2Stats):
        extra = (
            f"\nmolecule_type_counts={dict(sorted(stats.molecule_type_counts.items()))}"
            f"\nchemistry_counts={dict(sorted(stats.chemistry_counts.items()))}"
            f"\nalphabet_counts={dict(sorted(stats.alphabet_counts.items()))}"
            f"\nsource_object_type_counts="
            f"{dict(sorted(stats.source_object_type_counts.items()))}"
            f"\nt_to_u_count={stats.t_to_u_count}"
            f"\nrna_t_alphabet_count={stats.rna_t_alphabet_count}"
            f"\ndna_u_conflict_count={stats.dna_u_conflict_count}"
            f"\nknown_motif_detection_count={stats.known_motif_detection_count}"
            f"\ncore_differs_from_full={stats.core_differs_from_full}"
            f"\napplied_trims={stats.applied_trims}"
            f"\nreview_candidate_rows={stats.review_candidate_rows}"
        )
    elif isinstance(stats, AptaDiffS2Stats):
        extra = (
            f"\nmolecule_type_counts={dict(sorted(stats.molecule_type_counts.items()))}"
            f"\nchemistry_counts={dict(sorted(stats.chemistry_counts.items()))}"
            f"\nalphabet_counts={dict(sorted(stats.alphabet_counts.items()))}"
            f"\nt_to_u_count={stats.t_to_u_count}"
            f"\nambiguous_base_count={stats.ambiguous_base_count}"
            f"\nlength_36_count={stats.length_36_count}"
            f"\ncore_differs_from_full={stats.core_differs_from_full}"
            f"\napplied_trims={stats.applied_trims}"
            f"\nreview_candidate_rows={stats.review_candidate_rows}"
        )
    elif isinstance(stats, NcbiNucS2Stats):
        extra = (
            f"\nmolecule_type_counts={dict(sorted(stats.molecule_type_counts.items()))}"
            f"\nchemistry_counts={dict(sorted(stats.chemistry_counts.items()))}"
            f"\nalphabet_counts={dict(sorted(stats.alphabet_counts.items()))}"
            f"\nt_to_u_count={stats.t_to_u_count}"
            f"\nambiguous_base_count={stats.ambiguous_base_count}"
            f"\nconstruct_scope_counts="
            f"{dict(sorted(stats.construct_scope_counts.items()))}"
            f"\nknown_motif_detection_count={stats.known_motif_detection_count}"
            f"\ncore_differs_from_full={stats.core_differs_from_full}"
            f"\napplied_trims={stats.applied_trims}"
            f"\nreview_candidate_rows={stats.review_candidate_rows}"
        )
    print(
        f"source={result.source_key}\n"
        f"s1_rows={stats.s1_rows}\n"
        f"source_metadata_rows={stats.source_metadata_rows}\n"
        f"s2_rows={stats.s2_rows}\n"
        f"unique_record_ids={stats.unique_record_ids}\n"
        f"missing_sequence_rows={stats.missing_sequence_rows}\n"
        f"nonempty_sequence_rows={stats.nonempty_sequence_rows}\n"
        f"t_to_u_count={stats.t_to_u_count}\n"
        f"review_candidate_rows={stats.review_candidate_rows}\n"
        f"constant_region_proposals={stats.constant_region_proposals}"
        f"{extra}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

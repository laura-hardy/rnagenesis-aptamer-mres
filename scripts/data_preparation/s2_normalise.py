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
from typing import Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptabase_s2 import (  # noqa: E402
    CONSTANT_PROPOSAL_COLUMNS,
    S2_QC_COLUMNS,
    AptaBaseS2Error,
    AptaBaseS2Stats,
    assert_no_legacy_cleaner_import,
    is_review_candidate,
    load_aptabase_policy,
    normalise_aptabase_record,
    update_stats_from_row,
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


class S2NormaliseError(ValueError):
    """Hard failure during S2 normalisation orchestration."""


@dataclass(frozen=True)
class S2RunResult:
    """Aggregate outcome of one S2 normalisation run."""

    source_key: str
    stats: AptaBaseS2Stats | UTexasS2Stats | AptaDBS2Stats
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

    normalised_rows: list[dict[str, str]] = []
    qc_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []

    for s1_row, meta_row in zip(canonical_rows, aligned_sidecar, strict=True):
        result = normalise_aptabase_record(
            s1_row,
            meta_row,
            policy=policy,
            rules=rules,
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

    # Full equals core for every nonmissing record; no approved trim.
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
        UTexasS2Error,
        AptaDBS2Error,
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

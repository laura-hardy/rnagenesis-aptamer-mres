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
from typing import Sequence

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
from common.constant_region_inference import (  # noqa: E402
    infer_group_constant_regions,
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


class S2NormaliseError(ValueError):
    """Hard failure during S2 normalisation orchestration."""


@dataclass(frozen=True)
class S2RunResult:
    """Aggregate outcome of one S2 normalisation run."""

    source_key: str
    stats: AptaBaseS2Stats
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
        else:
            raise S2NormaliseError(
                "--source-policy is required for non-aptabase sources"
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
        CorpusSchemaError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    stats = result.stats
    # Aggregate counts only — never print sequence values.
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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

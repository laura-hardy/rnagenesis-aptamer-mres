#!/usr/bin/env python3
"""S3: per-source eligibility classification and CHECKPOINT-1 artefacts.

Consumes S2 normalised output, source-metadata, leakage exclusion set and target
aliases. Assigns provisional accept/park/reject decisions and stops before S4.
Does not perform target normalisation, UniProt mapping, evidence scoring,
affinity interpretation, deduplication, clustering, balancing or partitioning.
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

from adapters.aptabase_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    LEAKAGE_MATCH_COLUMNS,
    LOCAL_DETAIL_COLUMNS,
    REASON_COUNT_COLUMNS,
    AptaBaseS3Error,
    AptaBaseS3Stats,
    assert_no_legacy_cleaner_import,
    build_local_detail_row,
    classify_aptabase_record,
    update_stats_from_row,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    CorpusSchemaError,
    validate_column_order,
    write_corpus_csv_atomic,
)
from common.eligibility import (  # noqa: E402
    EligibilityError,
    load_eligibility_policy,
    load_sequence_leakage_index,
    load_target_alias_rules,
    review_sort_key,
)
from s0_build_registry import find_repo_root  # noqa: E402

EXPECTED_APTABASE_ROWS = 610

PIPELINE_STOP_STATEMENT = (
    "PIPELINE STOP: AptaBase CHECKPOINT-1 is awaiting manual review.\n"
    "No record is authorised to proceed to S4."
)


class S3ClassifyError(ValueError):
    """Hard failure during S3 eligibility orchestration."""


@dataclass(frozen=True)
class S3RunResult:
    """Aggregate outcome of one S3 classification run."""

    source_key: str
    stats: AptaBaseS3Stats
    output_canonical: Path
    output_decisions: Path
    output_review: Path
    output_local_detail: Path
    output_summary: Path
    output_reason_counts: Path
    output_leakage_matches: Path
    s2_hash_before: str
    s2_hash_after: str
    qc_hash_before: str
    qc_hash_after: str
    sidecar_hash_before: str
    sidecar_hash_after: str
    inputs_unchanged: bool
    deterministic_rerun_ok: bool | None
    s2_integrity_ok: bool


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
        raise S3ClassifyError(
            "S3 output directory must lie beneath data/interim/: "
            f"{output_dir}"
        ) from exc
    raw_root = (repo_root / "data" / "raw").resolve()
    try:
        resolved.relative_to(raw_root)
    except ValueError:
        pass
    else:
        raise S3ClassifyError(
            f"Refusing to write S3 outputs under data/raw/: {output_dir}"
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
    rows: Sequence[Mapping[str, str]],
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
            raise S3ClassifyError(f"S2 canonical CSV has no header: {path.name}")
        validate_column_order(list(reader.fieldnames))
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        for column in CORPUS_COLUMNS:
            value = row.get(column)
            if value is None:
                raise S3ClassifyError(
                    f"S2 row {index} missing column {column!r}"
                )
            row[column] = value
    return rows


def _read_sidecar_csv(path: Path, *, label: str) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise S3ClassifyError(f"{label} CSV has no header: {path.name}")
        if "record_id" not in reader.fieldnames:
            raise S3ClassifyError(f"{label} CSV missing record_id")
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        if not row.get("record_id"):
            raise S3ClassifyError(f"{label} row {index} has blank record_id")
        for key, value in list(row.items()):
            row[key] = "" if value is None else value
    return rows


def _match_sidecar_one_to_one(
    canonical_rows: Sequence[dict[str, str]],
    sidecar_rows: Sequence[dict[str, str]],
    *,
    label: str,
) -> list[dict[str, str]]:
    """Return sidecar rows aligned to canonical order; hard-fail on mismatch."""
    if len(canonical_rows) != len(sidecar_rows):
        raise S3ClassifyError(
            f"S2 canonical and {label} row counts must match: "
            f"{len(canonical_rows)} vs {len(sidecar_rows)}"
        )

    by_id: dict[str, dict[str, str]] = {}
    for row in sidecar_rows:
        record_id = row["record_id"]
        if record_id in by_id:
            raise S3ClassifyError(
                f"Duplicate {label} record_id: {record_id!r}"
            )
        by_id[record_id] = row

    aligned: list[dict[str, str]] = []
    for canonical in canonical_rows:
        record_id = canonical["record_id"]
        if record_id not in by_id:
            raise S3ClassifyError(
                f"Missing {label} row for record_id={record_id!r}"
            )
        aligned.append(by_id[record_id])

    extra = set(by_id) - {row["record_id"] for row in canonical_rows}
    if extra:
        raise S3ClassifyError(
            f"Extra {label} record_id values not in canonical: {len(extra)}"
        )
    return aligned


def _count_sorted(mapping: Mapping[str, int]) -> list[tuple[str, int]]:
    return sorted(mapping.items(), key=lambda item: item[0])


def _nested_count_lines(
    mapping: Mapping[str, Mapping[str, int]],
) -> list[str]:
    lines: list[str] = []
    for decision in sorted(mapping):
        inner = mapping[decision]
        for key, count in _count_sorted(inner):
            lines.append(f"- `{decision}` / `{key}`: `{count}`")
    if not lines:
        lines.append("- (none)")
    return lines


def build_aptabase_checkpoint1_summary(
    *,
    repo_root: Path,
    result: S3RunResult,
    policy_path: Path,
    leakage_path: Path,
    aliases_path: Path,
) -> str:
    """Build an aggregate-only Markdown CHECKPOINT-1 summary (no sequences)."""
    stats = result.stats
    lines = [
        "# AptaBase CHECKPOINT-1 summary",
        "",
        "## Totals",
        "",
        f"- Total records: `{stats.s3_rows}`",
        f"- Unique record IDs: `{stats.unique_record_ids}`",
        f"- S2 order preserved: `{'pass' if stats.order_preserved else 'fail'}`",
        "",
        "## Proposed decisions",
        "",
    ]
    for name, count in _count_sorted(stats.decision_counts):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(["", "## Primary reasons", ""])
    for name, count in _count_sorted(stats.primary_reason_counts):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(["", "## Review priorities", ""])
    for name, count in _count_sorted(stats.review_priority_counts):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(
        [
            "",
            "## Manual review queue",
            "",
            f"- `manual_review_required=true`: "
            f"`{stats.manual_review_required_true_count}`",
            f"- `manual_review_required=false`: "
            f"`{stats.manual_review_required_false_count}`",
            f"- Mechanical missing-sequence rejects excluded from manual review: "
            f"`{stats.missing_sequence_excluded_from_review_count}`",
            "",
            "## Leakage",
            "",
            f"- Sequence leakage matches: `{stats.sequence_leakage_count}`",
            f"- Target leakage matches: `{stats.target_leakage_count}`",
            f"- Both sequence and target leakage: `{stats.both_leakage_count}`",
            "",
            "## Condition tallies",
            "",
            f"- Missing sequences: `{stats.missing_sequence_count}`",
            f"- Source-invalid records: `{stats.source_invalid_count}`",
            f"- Core below minimum: `{stats.core_below_minimum_count}`",
            f"- Invalid sequences: `{stats.invalid_sequence_count}`",
            f"- Ambiguous sequences: `{stats.ambiguous_sequence_count}`",
            f"- Mixed T/U: `{stats.mixed_t_u_count}`",
            f"- Trim/construct review: `{stats.trim_review_count}`",
            f"- Core above maximum: `{stats.core_above_maximum_count}`",
            f"- ssDNA: `{stats.ssdna_count}`",
            f"- Unknown molecule type: `{stats.unknown_molecule_count}`",
            f"- Missing targets: `{stats.missing_target_count}`",
            f"- Technically eligible RNA: `{stats.technically_eligible_rna_count}`",
            f"- Records with multiple eligibility reasons: "
            f"`{stats.multiple_reasons_count}`",
            "",
            "## Molecule type by decision",
            "",
        ]
    )
    lines.extend(_nested_count_lines(stats.molecule_type_by_decision))

    lines.extend(["", "## Alphabet by decision", ""])
    lines.extend(_nested_count_lines(stats.alphabet_by_decision))

    lines.extend(["", "## Core-length bucket by decision", ""])
    lines.extend(_nested_count_lines(stats.core_length_bucket_by_decision))

    lines.extend(
        [
            "",
            "## Invalid / ambiguous / mixed by decision",
            "",
            "### Invalid character",
            "",
        ]
    )
    for name, count in _count_sorted(stats.invalid_by_decision):
        lines.append(f"- `{name}`: `{count}`")
    if not stats.invalid_by_decision:
        lines.append("- (none)")

    lines.extend(["", "### Ambiguous base", ""])
    for name, count in _count_sorted(stats.ambiguous_by_decision):
        lines.append(f"- `{name}`: `{count}`")
    if not stats.ambiguous_by_decision:
        lines.append("- (none)")

    lines.extend(["", "### Mixed T/U", ""])
    for name, count in _count_sorted(stats.mixed_by_decision):
        lines.append(f"- `{name}`: `{count}`")
    if not stats.mixed_by_decision:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## Integrity",
            "",
            f"- S2 canonical hash before: `{result.s2_hash_before}`",
            f"- S2 canonical hash after: `{result.s2_hash_after}`",
            f"- S2 QC hash before: `{result.qc_hash_before}`",
            f"- S2 QC hash after: `{result.qc_hash_after}`",
            f"- Source-metadata hash before: `{result.sidecar_hash_before}`",
            f"- Source-metadata hash after: `{result.sidecar_hash_after}`",
            f"- S2 input integrity: "
            f"`{'pass' if result.s2_integrity_ok else 'fail'}`",
            f"- Inputs unchanged: "
            f"`{'pass' if result.inputs_unchanged else 'fail'}`",
            (
                f"- Deterministic rerun result: "
                f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
                if result.deterministic_rerun_ok is not None
                else "- Deterministic rerun result: `not_checked`"
            ),
            "",
            "## Inputs",
            "",
            f"- Eligibility policy: `{_relative_display(policy_path, repo_root)}`",
            f"- Leakage exclusion set: "
            f"`{_relative_display(leakage_path, repo_root)}`",
            f"- Target aliases: `{_relative_display(aliases_path, repo_root)}`",
            "",
            "## Outputs",
            "",
            f"- Canonical: `{_relative_display(result.output_canonical, repo_root)}`",
            f"- Decisions: `{_relative_display(result.output_decisions, repo_root)}`",
            f"- Checkpoint review (sequence-free index): "
            f"`{_relative_display(result.output_review, repo_root)}`",
            f"- Checkpoint local detail (sequence-bearing scientific review): "
            f"`{_relative_display(result.output_local_detail, repo_root)}`",
            f"- Reason counts: "
            f"`{_relative_display(result.output_reason_counts, repo_root)}`",
            f"- Leakage matches: "
            f"`{_relative_display(result.output_leakage_matches, repo_root)}`",
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
            "",
            "## Local-detail warning",
            "",
            "WARNING: `aptabase_checkpoint1_local_detail.csv` contains source "
            "and canonical sequences for manual scientific review. It must "
            "remain beneath ignored `data/` and must never be staged or tracked.",
            "",
            "## Pipeline stop",
            "",
            PIPELINE_STOP_STATEMENT,
            "",
        ]
    )
    return "\n".join(lines)


def _assert_accept_invariants(decision_rows: Sequence[Mapping[str, str]]) -> None:
    """Hard-fail if any proposed accept violates RNA eligibility invariants."""
    for row in decision_rows:
        if row["proposed_decision"] != "proposed_accept":
            continue
        if row["molecule_type"] != "RNA":
            raise S3ClassifyError("proposed accept contains non-RNA molecule_type")
        if row["primary_reason"] != "technically_eligible_rna":
            raise S3ClassifyError(
                "proposed accept primary_reason must be technically_eligible_rna"
            )
        if row["sequence_leakage_match"] == "true":
            raise S3ClassifyError("proposed accept matched sequence leakage")
        if row["target_leakage_match"] == "true":
            raise S3ClassifyError("proposed accept matched target leakage")
        flags = {part for part in row["qc_flags"].split("|") if part}
        if flags & {
            "invalid_character",
            "ambiguous_base",
            "mixed_t_u",
            "trim_requires_review",
            "known_promoter_detected",
        }:
            raise S3ClassifyError(
                "proposed accept has unresolved sequence/trim QC flags"
            )
        if row["trim_status"] == "review_required":
            raise S3ClassifyError("proposed accept has trim_status=review_required")
        try:
            core_len = int(row["sequence_length_core"])
        except ValueError as exc:
            raise S3ClassifyError(
                "proposed accept has non-integer sequence_length_core"
            ) from exc
        if not (20 <= core_len <= 100):
            raise S3ClassifyError(
                "proposed accept core length outside 20–100 nt policy"
            )
        if row["molecule_type"] in {"ssDNA", "unknown"}:
            raise S3ClassifyError("ssDNA/unknown must never be accepted")


def _assert_reject_park_invariants(decision_rows: Sequence[Mapping[str, str]]) -> None:
    for row in decision_rows:
        decision = row["proposed_decision"]
        primary = row["primary_reason"]
        if primary == "missing_sequence" and decision != "proposed_reject":
            raise S3ClassifyError("missing sequence must never be accepted or parked")
        if primary == "core_below_minimum" and decision != "proposed_reject":
            raise S3ClassifyError("core below minimum must never be accepted or parked")
        if primary == "core_above_maximum_requires_review" and decision == (
            "proposed_accept"
        ):
            raise S3ClassifyError("core above maximum must never be accepted")
        if decision == "proposed_accept" and primary in {
            "ssdna_not_eligible_for_rna_training",
            "molecule_type_unresolved",
            "invalid_sequence_requires_review",
            "ambiguous_sequence_requires_review",
            "mixed_t_u_requires_review",
        }:
            raise S3ClassifyError(
                f"Invalid accept for primary_reason={primary}"
            )
        if row["checkpoint_status"] != "pending_checkpoint_1_review":
            raise S3ClassifyError("Unexpected checkpoint_status at S3")


def run_aptabase_s3(
    *,
    repo_root: Path,
    input_dir: Path,
    source_metadata_dir: Path,
    leakage_set: Path,
    target_aliases: Path,
    eligibility_policy: Path,
    output_dir: Path,
    expected_rows: int | None = EXPECTED_APTABASE_ROWS,
    check_deterministic_rerun: bool = False,
) -> S3RunResult:
    """Execute AptaBase S3 eligibility classification and CHECKPOINT-1."""
    assert_no_legacy_cleaner_import()
    repo_root = repo_root.resolve()
    input_dir = (
        input_dir if input_dir.is_absolute() else (repo_root / input_dir)
    ).resolve()
    source_metadata_dir = (
        source_metadata_dir
        if source_metadata_dir.is_absolute()
        else (repo_root / source_metadata_dir)
    ).resolve()
    leakage_set = (
        leakage_set if leakage_set.is_absolute() else (repo_root / leakage_set)
    ).resolve()
    target_aliases = (
        target_aliases
        if target_aliases.is_absolute()
        else (repo_root / target_aliases)
    ).resolve()
    eligibility_policy = (
        eligibility_policy
        if eligibility_policy.is_absolute()
        else (repo_root / eligibility_policy)
    ).resolve()
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    canonical_path = input_dir / "aptabase_normalised.csv"
    qc_path = input_dir / "aptabase_s2_qc.csv"
    sidecar_path = source_metadata_dir / "aptabase_source_metadata.csv"
    for path, label in (
        (canonical_path, "S2 canonical"),
        (qc_path, "S2 QC"),
        (sidecar_path, "source-metadata"),
    ):
        if not path.is_file():
            raise S3ClassifyError(f"Missing {label} input: {path.name}")

    s2_hash_before = _sha256_file(canonical_path)
    qc_hash_before = _sha256_file(qc_path)
    sidecar_hash_before = _sha256_file(sidecar_path)

    policy = load_eligibility_policy(eligibility_policy)
    if policy.source_key != "aptabase":
        raise S3ClassifyError(
            f"Eligibility policy source_key must be aptabase; got {policy.source_key!r}"
        )
    leakage_index = load_sequence_leakage_index(leakage_set)
    alias_rules = load_target_alias_rules(target_aliases)

    canonical_rows = _read_corpus_csv(canonical_path)
    qc_rows = _read_sidecar_csv(qc_path, label="S2 QC")
    sidecar_rows = _read_sidecar_csv(sidecar_path, label="source-metadata")
    aligned_qc = _match_sidecar_one_to_one(
        canonical_rows, qc_rows, label="S2 QC"
    )
    aligned_sidecar = _match_sidecar_one_to_one(
        canonical_rows, sidecar_rows, label="source-metadata"
    )

    if expected_rows is not None and len(canonical_rows) != expected_rows:
        raise S3ClassifyError(
            f"S2 row count must be {expected_rows}; got {len(canonical_rows)}"
        )

    stats = AptaBaseS3Stats()
    stats.s2_rows = len(canonical_rows)
    stats.order_preserved = True

    s3_canonical: list[dict[str, str]] = []
    decision_rows: list[dict[str, str]] = []
    leakage_rows: list[dict[str, str]] = []
    # Parallel list aligned to S2/canonical order; reordered later for review.
    local_detail_by_id: dict[str, dict[str, str]] = {}

    for s2_row, qc_row, meta_row in zip(
        canonical_rows, aligned_qc, aligned_sidecar, strict=True
    ):
        result = classify_aptabase_record(
            s2_row,
            qc_row,
            meta_row,
            policy=policy,
            leakage_index=leakage_index,
            target_alias_rules=alias_rules,
        )
        if result.canonical["record_id"] != s2_row["record_id"]:
            stats.order_preserved = False
            raise S3ClassifyError("S3 altered record_id or row identity")
        for column in CORPUS_COLUMNS:
            if result.canonical[column] != s2_row[column]:
                raise S3ClassifyError(
                    f"S3 altered S2 canonical field {column!r}"
                )
        s3_canonical.append(result.canonical)
        decision_rows.append(result.decision)
        leakage_rows.extend(result.leakage_rows)
        local_detail_by_id[result.canonical["record_id"]] = build_local_detail_row(
            canonical=result.canonical,
            s2_qc=qc_row,
            source_metadata=meta_row,
            decision=result.decision,
        )
        update_stats_from_row(stats, result)

    stats.s3_rows = len(s3_canonical)
    stats.unique_record_ids = len({row["record_id"] for row in s3_canonical})

    if expected_rows == EXPECTED_APTABASE_ROWS:
        if stats.s3_rows != EXPECTED_APTABASE_ROWS:
            raise S3ClassifyError(
                f"S3 must preserve {EXPECTED_APTABASE_ROWS} rows; got {stats.s3_rows}"
            )
        if stats.unique_record_ids != EXPECTED_APTABASE_ROWS:
            raise S3ClassifyError("S3 record_id values are not unique")
        if len(decision_rows) != EXPECTED_APTABASE_ROWS:
            raise S3ClassifyError("Decision row count mismatch")

    if len({row["record_id"] for row in decision_rows}) != len(decision_rows):
        raise S3ClassifyError("Decision sidecar contains duplicate record_id values")

    for row in decision_rows:
        if row["proposed_decision"] not in {
            "proposed_accept",
            "proposed_park",
            "proposed_reject",
        }:
            raise S3ClassifyError(
                f"Unknown proposed_decision {row['proposed_decision']!r}"
            )
        if not row["primary_reason"]:
            raise S3ClassifyError("Decision row missing primary_reason")

    _assert_accept_invariants(decision_rows)
    _assert_reject_park_invariants(decision_rows)

    # Leakage file must reconcile to decision leakage flags.
    seq_leak_decisions = sum(
        1 for row in decision_rows if row["sequence_leakage_match"] == "true"
    )
    tgt_leak_decisions = sum(
        1 for row in decision_rows if row["target_leakage_match"] == "true"
    )
    seq_leak_file = sum(1 for row in leakage_rows if row["match_scope"] == "sequence")
    tgt_leak_file = sum(1 for row in leakage_rows if row["match_scope"] == "target")
    if seq_leak_decisions != seq_leak_file or seq_leak_decisions != (
        stats.sequence_leakage_count
    ):
        raise S3ClassifyError("Sequence leakage counts do not reconcile")
    if tgt_leak_decisions != tgt_leak_file or tgt_leak_decisions != (
        stats.target_leakage_count
    ):
        raise S3ClassifyError("Target leakage counts do not reconcile")

    # Reason counts must reconcile to total rows.
    reason_count_rows: list[dict[str, str]] = []
    combo_counts: dict[tuple[str, str], int] = {}
    for row in decision_rows:
        key = (row["proposed_decision"], row["primary_reason"])
        combo_counts[key] = combo_counts.get(key, 0) + 1
    for (decision, reason), count in sorted(combo_counts.items()):
        reason_count_rows.append(
            {
                "proposed_decision": decision,
                "primary_reason": reason,
                "record_count": str(count),
            }
        )
    if sum(int(row["record_count"]) for row in reason_count_rows) != len(decision_rows):
        raise S3ClassifyError("Reason counts do not reconcile to decision rows")

    review_rows = sorted(decision_rows, key=review_sort_key)
    if len(review_rows) != len(decision_rows):
        raise S3ClassifyError("Checkpoint review row count mismatch")

    # Local-detail rows follow the same review ordering as the sequence-free index.
    local_detail_rows: list[dict[str, str]] = []
    for review_row in review_rows:
        record_id = review_row["record_id"]
        if record_id not in local_detail_by_id:
            raise S3ClassifyError(
                f"Missing local-detail row for record_id={record_id!r}"
            )
        local_detail_rows.append(local_detail_by_id[record_id])
    if len(local_detail_rows) != len(decision_rows):
        raise S3ClassifyError("Local-detail row count mismatch")
    for review_row, detail_row in zip(review_rows, local_detail_rows, strict=True):
        if review_row["record_id"] != detail_row["record_id"]:
            raise S3ClassifyError(
                "Local-detail ordering does not match sequence-free review"
            )

    # Guard: no sequence columns in review/decision artefacts.
    forbidden_seq_cols = {
        "sequence_raw",
        "sequence_full",
        "sequence_core",
        "sequence_compare_full",
        "sequence_compare_core",
    }
    for col in forbidden_seq_cols:
        if col in DECISION_COLUMNS or col in LEAKAGE_MATCH_COLUMNS:
            raise S3ClassifyError(f"Sequence column leaked into sidecar schema: {col}")
    for col in ("sequence_raw", "sequence_full", "sequence_core"):
        if col not in LOCAL_DETAIL_COLUMNS:
            raise S3ClassifyError(
                f"Local-detail schema missing required sequence column: {col}"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_canonical = output_dir / "aptabase_s3_canonical.csv"
    out_decisions = output_dir / "aptabase_s3_decisions.csv"
    out_review = output_dir / "aptabase_checkpoint1_review.csv"
    out_local_detail = output_dir / "aptabase_checkpoint1_local_detail.csv"
    out_reason_counts = output_dir / "aptabase_checkpoint1_reason_counts.csv"
    out_leakage = output_dir / "aptabase_leakage_matches.csv"
    out_summary = output_dir / "aptabase_checkpoint1_summary.md"

    write_corpus_csv_atomic(out_canonical, s3_canonical)
    write_csv_atomic(out_decisions, DECISION_COLUMNS, decision_rows)
    write_csv_atomic(out_review, DECISION_COLUMNS, review_rows)
    write_csv_atomic(out_local_detail, LOCAL_DETAIL_COLUMNS, local_detail_rows)
    write_csv_atomic(out_reason_counts, REASON_COUNT_COLUMNS, reason_count_rows)
    write_csv_atomic(out_leakage, LEAKAGE_MATCH_COLUMNS, leakage_rows)

    s2_hash_after = _sha256_file(canonical_path)
    qc_hash_after = _sha256_file(qc_path)
    sidecar_hash_after = _sha256_file(sidecar_path)
    inputs_unchanged = (
        s2_hash_before == s2_hash_after
        and qc_hash_before == qc_hash_after
        and sidecar_hash_before == sidecar_hash_after
    )
    if not inputs_unchanged:
        raise S3ClassifyError("S2/source inputs were modified during S3 execution")

    s2_integrity_ok = True
    # Canonical output must be byte-identical to S2 input.
    if _sha256_file(out_canonical) != s2_hash_before:
        raise S3ClassifyError(
            "S3 canonical output is not byte-identical to S2 normalised input"
        )

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_hashes = {
            "canonical": _sha256_file(out_canonical),
            "decisions": _sha256_file(out_decisions),
            "review": _sha256_file(out_review),
            "local_detail": _sha256_file(out_local_detail),
            "reason_counts": _sha256_file(out_reason_counts),
            "leakage": _sha256_file(out_leakage),
        }
        second = run_aptabase_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            leakage_set=leakage_set,
            target_aliases=target_aliases,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            first_hashes["canonical"] == _sha256_file(second.output_canonical)
            and first_hashes["decisions"] == _sha256_file(second.output_decisions)
            and first_hashes["review"] == _sha256_file(second.output_review)
            and first_hashes["local_detail"]
            == _sha256_file(second.output_local_detail)
            and first_hashes["reason_counts"]
            == _sha256_file(second.output_reason_counts)
            and first_hashes["leakage"] == _sha256_file(second.output_leakage_matches)
        )
        if not deterministic_ok:
            raise S3ClassifyError(
                "S3 outputs were not byte-identical across deterministic rerun"
            )

    run_result = S3RunResult(
        source_key="aptabase",
        stats=stats,
        output_canonical=out_canonical,
        output_decisions=out_decisions,
        output_review=out_review,
        output_local_detail=out_local_detail,
        output_summary=out_summary,
        output_reason_counts=out_reason_counts,
        output_leakage_matches=out_leakage,
        s2_hash_before=s2_hash_before,
        s2_hash_after=s2_hash_after,
        qc_hash_before=qc_hash_before,
        qc_hash_after=qc_hash_after,
        sidecar_hash_before=sidecar_hash_before,
        sidecar_hash_after=sidecar_hash_after,
        inputs_unchanged=inputs_unchanged,
        deterministic_rerun_ok=deterministic_ok,
        s2_integrity_ok=s2_integrity_ok,
    )
    summary_text = build_aptabase_checkpoint1_summary(
        repo_root=repo_root,
        result=run_result,
        policy_path=eligibility_policy,
        leakage_path=leakage_set,
        aliases_path=target_aliases,
    )
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise S3ClassifyError(
            "CHECKPOINT-1 summary must not contain absolute repository paths"
        )
    if PIPELINE_STOP_STATEMENT not in summary_text:
        raise S3ClassifyError("CHECKPOINT-1 summary missing pipeline stop statement")
    _write_text_atomic(out_summary, summary_text)
    return run_result


def run_s3_classification(
    *,
    repo_root: Path,
    source_key: str,
    input_dir: Path,
    source_metadata_dir: Path,
    leakage_set: Path,
    target_aliases: Path,
    eligibility_policy: Path,
    output_dir: Path,
    expected_rows: int | None = None,
    check_deterministic_rerun: bool = False,
) -> S3RunResult:
    """Dispatch S3 classification for one source key."""
    if source_key == "aptabase":
        return run_aptabase_s3(
            repo_root=repo_root,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            leakage_set=leakage_set,
            target_aliases=target_aliases,
            eligibility_policy=eligibility_policy,
            output_dir=output_dir,
            expected_rows=(
                EXPECTED_APTABASE_ROWS if expected_rows is None else expected_rows
            ),
            check_deterministic_rerun=check_deterministic_rerun,
        )
    raise S3ClassifyError(f"Unknown S3 source_key={source_key!r}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "S3: classify normalised source records into provisional "
            "accept/park/reject decisions and emit CHECKPOINT-1 artefacts."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source key to classify (e.g. aptabase)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Directory containing S2 outputs (default: data/interim/normalised)",
    )
    parser.add_argument(
        "--source-metadata-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing S1 source-metadata sidecar "
            "(default: data/interim/extracted)"
        ),
    )
    parser.add_argument(
        "--leakage-set",
        type=Path,
        default=None,
        help="Leakage exclusion set CSV",
    )
    parser.add_argument(
        "--target-aliases",
        type=Path,
        default=None,
        help="Tracked target-alias CSV",
    )
    parser.add_argument(
        "--eligibility-policy",
        type=Path,
        default=None,
        help="Source-specific eligibility policy JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory beneath data/interim "
            "(default: data/interim/checkpoints/aptabase_cp1)"
        ),
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
            raise S3ClassifyError(f"Repository root does not exist: {repo_root}")

        input_dir = (
            args.input_dir
            if args.input_dir is not None
            else Path("data/interim/normalised")
        )
        source_metadata_dir = (
            args.source_metadata_dir
            if args.source_metadata_dir is not None
            else Path("data/interim/extracted")
        )
        leakage_set = (
            args.leakage_set
            if args.leakage_set is not None
            else Path("data/interim/leakage_exclusion_set.csv")
        )
        target_aliases = (
            args.target_aliases
            if args.target_aliases is not None
            else Path("config/leakage_target_aliases.csv")
        )
        if args.eligibility_policy is not None:
            policy_path = args.eligibility_policy
        elif args.source == "aptabase":
            policy_path = Path("config/source_eligibility/aptabase.json")
        else:
            raise S3ClassifyError(
                "--eligibility-policy is required for non-aptabase sources"
            )
        output_dir = (
            args.output_dir
            if args.output_dir is not None
            else Path("data/interim/checkpoints/aptabase_cp1")
        )

        result = run_s3_classification(
            repo_root=repo_root,
            source_key=args.source,
            input_dir=input_dir,
            source_metadata_dir=source_metadata_dir,
            leakage_set=leakage_set,
            target_aliases=target_aliases,
            eligibility_policy=policy_path,
            output_dir=output_dir,
            expected_rows=args.expected_rows,
            check_deterministic_rerun=args.check_deterministic_rerun,
        )
    except (
        S3ClassifyError,
        AptaBaseS3Error,
        EligibilityError,
        CorpusSchemaError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    stats = result.stats
    # Aggregate counts only — never print sequence values.
    print(
        f"source={result.source_key}\n"
        f"s2_rows={stats.s2_rows}\n"
        f"s3_rows={stats.s3_rows}\n"
        f"unique_record_ids={stats.unique_record_ids}\n"
        f"proposed_accept={stats.decision_counts.get('proposed_accept', 0)}\n"
        f"proposed_park={stats.decision_counts.get('proposed_park', 0)}\n"
        f"proposed_reject={stats.decision_counts.get('proposed_reject', 0)}\n"
        f"sequence_leakage={stats.sequence_leakage_count}\n"
        f"target_leakage={stats.target_leakage_count}\n"
        f"both_leakage={stats.both_leakage_count}\n"
        f"multiple_reasons={stats.multiple_reasons_count}\n"
        f"inputs_unchanged={'pass' if result.inputs_unchanged else 'fail'}\n"
        f"s2_integrity={'pass' if result.s2_integrity_ok else 'fail'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

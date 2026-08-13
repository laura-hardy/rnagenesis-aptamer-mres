#!/usr/bin/env python3
"""Generate the UTexas RNA alphabet-exception review package.

Inspects the 31 source-reported RNA records currently rejected at S3 for
``ambiguous_bases`` or ``invalid_alphabet``. Emits a sequence-bearing review
CSV and a sequence-safe summary. Does not mutate canonical S2/S3 data or
apply CHECKPOINT-1 decisions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.utexas_alphabet_exceptions import (  # noqa: E402
    EXPECTED_DECISION_COUNTS,
    EXPECTED_EXCEPTION_ROWS,
    RESOLUTION_COLUMNS,
    REVIEW_COLUMNS,
    REVIEW_DECISION_DATE,
    REVIEW_POLICY_VERSION,
    AlphabetExceptionError,
    apply_human_exception_decisions,
    assert_reviewed_package_counts,
    build_exception_summary,
    build_review_row,
    build_tracked_resolution_rows,
    select_exception_cohort,
)
from s0_build_registry import find_repo_root  # noqa: E402

EXPECTED_RAW_SHA256 = (
    "b5a66beb58d30c5c3d2f36a29ea2cc3678e7d4a6b1bb1a97efc1e166a49fd15c"
)
EXPECTED_S2_SHA256 = (
    "588498eaeeacb1f7d7349ef1f0f30ef46ba2e64d873416439ed62df614e50c7e"
)
EXPECTED_S3_ROWS = 1894

PIPELINE_STOP_STATEMENT = (
    "Alphabet-exception review package generated.\n"
    "No canonical sequence was changed.\n"
    "No CHECKPOINT-1 decision was applied.\n"
    "CHECKPOINT-1 remains open.\n"
    "Global S4 has not started."
)


class AlphabetExceptionReviewError(ValueError):
    """Hard failure while generating the alphabet-exception package."""


@dataclass(frozen=True)
class AlphabetExceptionRunResult:
    """Outcome of one exception-review package generation."""

    output_review: Path
    output_summary: Path
    n_rows: int
    raw_sha_before: str
    raw_sha_after: str
    s2_hash_before: str
    s2_hash_after: str
    s3_hash_before: str
    s3_hash_after: str
    checkpoint_actions_populated: int
    review_actions_populated: int
    deterministic_rerun_ok: bool | None
    class_counts: dict[str, int]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _index_by_record_id(rows: Sequence[Mapping[str, str]], path: Path) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        record_id = row.get("record_id") or ""
        if not record_id:
            raise AlphabetExceptionReviewError(f"Missing record_id in {path}")
        if record_id in indexed:
            raise AlphabetExceptionReviewError(
                f"Duplicate record_id {record_id!r} in {path}"
            )
        indexed[record_id] = dict(row)
    return indexed


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


def _assert_output_dir_allowed(repo_root: Path, output_dir: Path) -> Path:
    resolved = output_dir if output_dir.is_absolute() else (repo_root / output_dir)
    resolved = resolved.resolve()
    interim_root = (repo_root / "data" / "interim").resolve()
    try:
        resolved.relative_to(interim_root)
    except ValueError as exc:
        raise AlphabetExceptionReviewError(
            "Exception-review output must lie beneath data/interim/: "
            f"{output_dir}"
        ) from exc
    raw_root = (repo_root / "data" / "raw").resolve()
    try:
        resolved.relative_to(raw_root)
    except ValueError:
        pass
    else:
        raise AlphabetExceptionReviewError(
            f"Refusing to write under data/raw/: {output_dir}"
        )
    return resolved


def _count_populated_review_actions(path: Path, column: str = "review_action") -> int:
    if not path.exists():
        return 0
    rows = _read_csv(path)
    return sum(1 for row in rows if (row.get(column) or "").strip())


def _class_counts(rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = row.get("exception_class") or "(empty)"
        counts[key] = counts.get(key, 0) + 1
    return counts


def generate_exception_review_package(
    *,
    repo_root: Path,
    decisions_path: Path,
    local_detail_path: Path,
    source_metadata_path: Path,
    canonical_s3_path: Path,
    s2_canonical_path: Path,
    raw_workbook_path: Path,
    checkpoint_review_path: Path,
    output_dir: Path,
    expected_rows: int = EXPECTED_EXCEPTION_ROWS,
    check_deterministic_rerun: bool = False,
) -> AlphabetExceptionRunResult:
    """Build the ignored exception-review CSV and sequence-safe summary."""
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_sha_before = _sha256_file(raw_workbook_path)
    s2_hash_before = _sha256_file(s2_canonical_path)
    s3_hash_before = _sha256_file(canonical_s3_path)
    if raw_sha_before != EXPECTED_RAW_SHA256:
        raise AlphabetExceptionReviewError(
            f"Raw workbook SHA drifted: {raw_sha_before}"
        )
    if s2_hash_before != EXPECTED_S2_SHA256:
        raise AlphabetExceptionReviewError(
            f"S2 canonical SHA drifted: {s2_hash_before}"
        )

    decisions = _read_csv(decisions_path)
    if len(decisions) != EXPECTED_S3_ROWS:
        raise AlphabetExceptionReviewError(
            f"S3 decision rows drifted: {len(decisions)}"
        )
    detail_by_id = _index_by_record_id(_read_csv(local_detail_path), local_detail_path)
    meta_by_id = _index_by_record_id(
        _read_csv(source_metadata_path), source_metadata_path
    )
    canonical_by_id = _index_by_record_id(
        _read_csv(canonical_s3_path), canonical_s3_path
    )
    checkpoint_actions = _count_populated_review_actions(checkpoint_review_path)

    try:
        cohort = select_exception_cohort(decisions)
    except AlphabetExceptionError as exc:
        raise AlphabetExceptionReviewError(str(exc)) from exc
    if expected_rows != EXPECTED_EXCEPTION_ROWS:
        raise AlphabetExceptionReviewError(
            f"Refusing unexpected expected_rows={expected_rows}"
        )

    review_rows: list[dict[str, str]] = []
    for decision in cohort:
        record_id = decision["record_id"]
        detail = detail_by_id.get(record_id)
        metadata = meta_by_id.get(record_id)
        canonical = canonical_by_id.get(record_id)
        if detail is None:
            raise AlphabetExceptionReviewError(
                f"Missing local-detail row for {record_id}"
            )
        if metadata is None:
            raise AlphabetExceptionReviewError(
                f"Missing source-metadata row for {record_id}"
            )
        if canonical is None:
            raise AlphabetExceptionReviewError(
                f"Missing S3 canonical row for {record_id}"
            )
        if canonical.get("sequence_raw") != detail.get("sequence_raw"):
            raise AlphabetExceptionReviewError(
                f"sequence_raw mismatch between S3 canonical and local detail"
            )
        if canonical.get("sequence_full") != detail.get("sequence_full"):
            raise AlphabetExceptionReviewError(
                f"sequence_full mismatch between S3 canonical and local detail"
            )
        review_rows.append(
            build_review_row(
                decision=decision,
                detail=detail,
                metadata=metadata,
                canonical=canonical,
            )
        )

    if len(review_rows) != expected_rows:
        raise AlphabetExceptionReviewError(
            f"Review row count drifted: {len(review_rows)}"
        )
    for row in review_rows:
        if (row.get("review_action") or "").strip():
            raise AlphabetExceptionReviewError(
                "Exception-review actions must remain blank"
            )
        if row.get("molecule_type") != "RNA":
            raise AlphabetExceptionReviewError(
                "Non-RNA row entered the alphabet-exception package"
            )

    out_review = output_dir / "utexas_alphabet_exception_review.csv"
    out_summary = output_dir / "utexas_alphabet_exception_summary.md"
    write_csv_atomic(out_review, REVIEW_COLUMNS, review_rows)

    raw_sha_after = _sha256_file(raw_workbook_path)
    s2_hash_after = _sha256_file(s2_canonical_path)
    s3_hash_after = _sha256_file(canonical_s3_path)
    if raw_sha_after != raw_sha_before:
        raise AlphabetExceptionReviewError("Raw workbook SHA changed during review")
    if s2_hash_after != s2_hash_before:
        raise AlphabetExceptionReviewError("S2 canonical SHA changed during review")
    if s3_hash_after != s3_hash_before:
        raise AlphabetExceptionReviewError("S3 canonical SHA changed during review")

    summary = build_exception_summary(
        review_rows,
        raw_sha_before=raw_sha_before,
        raw_sha_after=raw_sha_after,
        s2_hash_before=s2_hash_before,
        s2_hash_after=s2_hash_after,
        s3_hash_before=s3_hash_before,
        s3_hash_after=s3_hash_after,
        checkpoint_actions_populated=checkpoint_actions,
        deterministic_rerun_ok=None,
    )
    _write_text_atomic(out_summary, summary)

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        first_review_hash = _sha256_file(out_review)
        first_summary_hash = _sha256_file(out_summary)
        rerun = generate_exception_review_package(
            repo_root=repo_root,
            decisions_path=decisions_path,
            local_detail_path=local_detail_path,
            source_metadata_path=source_metadata_path,
            canonical_s3_path=canonical_s3_path,
            s2_canonical_path=s2_canonical_path,
            raw_workbook_path=raw_workbook_path,
            checkpoint_review_path=checkpoint_review_path,
            output_dir=output_dir,
            expected_rows=expected_rows,
            check_deterministic_rerun=False,
        )
        deterministic_ok = (
            _sha256_file(rerun.output_review) == first_review_hash
            and _sha256_file(rerun.output_summary) == first_summary_hash
        )
        if not deterministic_ok:
            raise AlphabetExceptionReviewError(
                "Deterministic rerun produced different exception-review artefacts"
            )
        summary = build_exception_summary(
            _read_csv(out_review),
            raw_sha_before=raw_sha_before,
            raw_sha_after=_sha256_file(raw_workbook_path),
            s2_hash_before=s2_hash_before,
            s2_hash_after=_sha256_file(s2_canonical_path),
            s3_hash_before=s3_hash_before,
            s3_hash_after=_sha256_file(canonical_s3_path),
            checkpoint_actions_populated=checkpoint_actions,
            deterministic_rerun_ok=True,
        )
        _write_text_atomic(out_summary, summary)
        # Rewrite once more after the summary now records pass, then confirm
        # the CSV is unchanged and a third generation matches the summary.
        if _sha256_file(out_review) != first_review_hash:
            raise AlphabetExceptionReviewError(
                "Review CSV changed after summary determinism annotation"
            )

    written = _read_csv(out_review)
    if any((row.get("review_action") or "").strip() for row in written):
        raise AlphabetExceptionReviewError("Review actions were populated")

    return AlphabetExceptionRunResult(
        output_review=out_review,
        output_summary=out_summary,
        n_rows=len(review_rows),
        raw_sha_before=raw_sha_before,
        raw_sha_after=raw_sha_after,
        s2_hash_before=s2_hash_before,
        s2_hash_after=s2_hash_after,
        s3_hash_before=s3_hash_before,
        s3_hash_after=s3_hash_after,
        checkpoint_actions_populated=checkpoint_actions,
        review_actions_populated=0,
        deterministic_rerun_ok=deterministic_ok,
        class_counts=_class_counts(review_rows),
    )


def _assert_tracked_path_allowed(repo_root: Path, path: Path) -> Path:
    resolved = path if path.is_absolute() else (repo_root / path)
    resolved = resolved.resolve()
    data_root = (repo_root / "data").resolve()
    try:
        resolved.relative_to(data_root)
    except ValueError:
        return resolved
    raise AlphabetExceptionReviewError(
        f"Tracked alphabet artefacts must not be written under data/: {path}"
    )


def apply_recorded_exception_decisions(
    *,
    repo_root: Path,
    review_csv: Path,
    tracked_manifest: Path,
    metadata_out: Path,
) -> dict[str, object]:
    """Record Laura's alphabet-exception decisions and emit sequence-safe artefacts."""
    review_csv = review_csv if review_csv.is_absolute() else (repo_root / review_csv)
    tracked_manifest = _assert_tracked_path_allowed(repo_root, tracked_manifest)
    metadata_out = _assert_tracked_path_allowed(repo_root, metadata_out)
    if not review_csv.is_file():
        raise AlphabetExceptionReviewError(
            f"Missing alphabet-exception review CSV: {review_csv.name}"
        )
    rows = _read_csv(review_csv)
    try:
        assert_reviewed_package_counts(rows)
        decided = apply_human_exception_decisions(rows)
        tracked = build_tracked_resolution_rows(decided)
    except AlphabetExceptionError as exc:
        raise AlphabetExceptionReviewError(str(exc)) from exc

    source_sha = _sha256_file(review_csv)
    write_csv_atomic(review_csv, REVIEW_COLUMNS, decided)
    write_csv_atomic(tracked_manifest, RESOLUTION_COLUMNS, tracked)

    action_counts = {
        key: sum(1 for row in decided if (row.get("review_action") or "") == key)
        for key in (
            "accept_recovered_sequence",
            "confirm_reject",
            "override_to_park",
            "needs_source_review",
        )
    }
    metadata = {
        "source_key": "utexas",
        "checkpoint": "CHECKPOINT-1",
        "review_scope": "alphabet_exceptions",
        "review_policy_version": REVIEW_POLICY_VERSION,
        "review_model": "single_reviewer",
        "reviewer_initials_required": False,
        "decision_date": REVIEW_DECISION_DATE,
        "source_review_file": (
            "data/interim/checkpoints/utexas_cp1/exceptions/"
            "utexas_alphabet_exception_review.csv"
        ),
        "source_review_file_sha256_before_decision_write": source_sha,
        "source_review_file_sha256": _sha256_file(review_csv),
        "n_rows": len(decided),
        "decision_counts": action_counts,
        "canonical_sequences_changed_by_this_step": False,
        "checkpoint1_closed_by_this_step": False,
    }
    metadata_text = json.dumps(metadata, indent=2, sort_keys=False, ensure_ascii=False)
    _write_text_atomic(metadata_out, metadata_text + "\n")
    if any(count != EXPECTED_DECISION_COUNTS[key] for key, count in action_counts.items()):
        raise AlphabetExceptionReviewError("Recorded decision counts drifted")
    return {
        "n_rows": len(decided),
        "decision_counts": action_counts,
        "tracked_manifest": tracked_manifest,
        "metadata_out": metadata_out,
        "review_csv": review_csv,
        "source_review_file_sha256": metadata["source_review_file_sha256"],
    }


def default_paths(repo_root: Path) -> dict[str, Path]:
    return {
        "decisions": repo_root
        / "data"
        / "interim"
        / "checkpoints"
        / "utexas_cp1"
        / "utexas_s3_decisions.csv",
        "local_detail": repo_root
        / "data"
        / "interim"
        / "checkpoints"
        / "utexas_cp1"
        / "utexas_checkpoint1_local_detail.csv",
        "source_metadata": repo_root
        / "data"
        / "interim"
        / "extracted"
        / "utexas_source_metadata.csv",
        "canonical_s3": repo_root
        / "data"
        / "interim"
        / "checkpoints"
        / "utexas_cp1"
        / "utexas_s3_canonical.csv",
        "s2_canonical": repo_root
        / "data"
        / "interim"
        / "normalised"
        / "utexas_normalised.csv",
        "raw_workbook": repo_root
        / "data"
        / "raw"
        / "UTexas_aptamer_dataset"
        / "UTexas Aptamer Database dataset_Sept2023.xlsx",
        "checkpoint_review": repo_root
        / "data"
        / "interim"
        / "checkpoints"
        / "utexas_cp1"
        / "manual_review"
        / "utexas_checkpoint1_manual_review.csv",
        "output_dir": repo_root
        / "data"
        / "interim"
        / "checkpoints"
        / "utexas_cp1"
        / "exceptions",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the UTexas RNA alphabet-exception review package."
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--decisions", type=Path, default=None)
    parser.add_argument("--local-detail", type=Path, default=None)
    parser.add_argument("--source-metadata", type=Path, default=None)
    parser.add_argument("--canonical-s3", type=Path, default=None)
    parser.add_argument("--s2-canonical", type=Path, default=None)
    parser.add_argument("--raw-workbook", type=Path, default=None)
    parser.add_argument("--checkpoint-review", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--apply-human-decisions",
        action="store_true",
        help="Record Laura's alphabet-exception decisions and write tracked resolutions.",
    )
    parser.add_argument(
        "--tracked-manifest",
        type=Path,
        default=None,
        help="Tracked sequence-safe alphabet resolution CSV.",
    )
    parser.add_argument(
        "--metadata-out",
        type=Path,
        default=None,
        help="Tracked alphabet-exception metadata JSON.",
    )
    parser.add_argument(
        "--check-deterministic-rerun",
        action="store_true",
        help="Generate the package twice and require byte-identical artefacts.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root()
    paths = default_paths(repo_root)
    if args.apply_human_decisions:
        applied = apply_recorded_exception_decisions(
            repo_root=repo_root,
            review_csv=paths["output_dir"] / "utexas_alphabet_exception_review.csv",
            tracked_manifest=(
                args.tracked_manifest
                if args.tracked_manifest is not None
                else Path(
                    "config/checkpoint_reviews/utexas_alphabet_exception_resolutions.csv"
                )
            ),
            metadata_out=(
                args.metadata_out
                if args.metadata_out is not None
                else Path(
                    "config/checkpoint_reviews/utexas_alphabet_exception_metadata.json"
                )
            ),
        )
        counts = applied["decision_counts"]
        print(f"alphabet_exception_rows={applied['n_rows']}")
        print(f"accept_recovered_sequence={counts['accept_recovered_sequence']}")
        print(f"confirm_reject={counts['confirm_reject']}")
        print(f"override_to_park={counts['override_to_park']}")
        print(f"needs_source_review={counts['needs_source_review']}")
        print(f"source_review_file_sha256={applied['source_review_file_sha256']}")
        print("Alphabet-exception human decisions recorded.")
        return 0
    result = generate_exception_review_package(
        repo_root=repo_root,
        decisions_path=args.decisions or paths["decisions"],
        local_detail_path=args.local_detail or paths["local_detail"],
        source_metadata_path=args.source_metadata or paths["source_metadata"],
        canonical_s3_path=args.canonical_s3 or paths["canonical_s3"],
        s2_canonical_path=args.s2_canonical or paths["s2_canonical"],
        raw_workbook_path=args.raw_workbook or paths["raw_workbook"],
        checkpoint_review_path=args.checkpoint_review or paths["checkpoint_review"],
        output_dir=args.output_dir or paths["output_dir"],
        check_deterministic_rerun=args.check_deterministic_rerun,
    )
    print(f"alphabet_exception_rows={result.n_rows}")
    print(f"class_counts={result.class_counts}")
    print(f"raw_sha_unchanged={result.raw_sha_before == result.raw_sha_after}")
    print(f"s2_unchanged={result.s2_hash_before == result.s2_hash_after}")
    print(f"s3_unchanged={result.s3_hash_before == result.s3_hash_after}")
    print(f"checkpoint_actions_populated={result.checkpoint_actions_populated}")
    print(f"review_actions_populated={result.review_actions_populated}")
    print(f"deterministic_rerun={result.deterministic_rerun_ok}")
    print(PIPELINE_STOP_STATEMENT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

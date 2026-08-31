"""Fail-closed validation of a CHECKPOINT-1 human-review package.

Does not apply decisions, mutate canonical outputs, or start S4.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadb_checkpoint1_review import (  # noqa: E402
    AptaDBCheckpoint1ReviewError,
    read_csv_rows,
    validate_review_package,
)
from s0_build_registry import find_repo_root  # noqa: E402

SUPPORTED_SOURCES = ("aptadb", "riboaptamer")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate CHECKPOINT-1 review files without applying them."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source key (aptadb or riboaptamer)",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=None,
        help="CHECKPOINT-1 directory",
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
    if args.source not in SUPPORTED_SOURCES:
        print(
            f"ERROR: unsupported source_key={args.source!r}; "
            f"supported: {', '.join(SUPPORTED_SOURCES)}",
            file=sys.stderr,
        )
        return 1
    repo_root = (
        args.repo_root.resolve()
        if args.repo_root is not None
        else find_repo_root(Path(__file__).resolve())
    )
    if args.source == "riboaptamer":
        default_checkpoint = Path("data/interim/checkpoints/riboaptamer_cp1")
        queue_name = "riboaptamer_checkpoint1_manual_review.csv"
        group_name = "riboaptamer_checkpoint1_constant_group_review.csv"
        bulk_name = "riboaptamer_checkpoint1_bulk_audit_confirmation.csv"
    else:
        default_checkpoint = Path("data/interim/checkpoints/aptadb_cp1")
        queue_name = "aptadb_checkpoint1_manual_review.csv"
        group_name = "aptadb_checkpoint1_constant_group_review.csv"
        bulk_name = "aptadb_checkpoint1_bulk_audit_confirmation.csv"
    checkpoint_dir = (
        args.checkpoint_dir
        if args.checkpoint_dir is not None
        else default_checkpoint
    )
    if not checkpoint_dir.is_absolute():
        checkpoint_dir = (repo_root / checkpoint_dir).resolve()
    review_dir = checkpoint_dir / "manual_review"
    queue_path = review_dir / queue_name
    group_path = review_dir / group_name
    bulk_path = review_dir / bulk_name
    try:
        if not queue_path.is_file():
            raise AptaDBCheckpoint1ReviewError(
                "Missing record-level review CSV; prepare CHECKPOINT-1 first"
            )
        queue_rows = read_csv_rows(queue_path)
        group_rows = read_csv_rows(group_path) if group_path.is_file() else []
        bulk_rows = read_csv_rows(bulk_path) if bulk_path.is_file() else []
        bulk = bulk_rows[0] if bulk_rows else None
        report = validate_review_package(
            queue_rows=queue_rows,
            group_rows=group_rows,
            bulk_confirmation=bulk,
        )
    except AptaDBCheckpoint1ReviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"source={args.source}\n"
        f"total_review_records={report.total_review_records}\n"
        f"unresolved_manual_decisions={report.unresolved_manual_decisions}\n"
        f"unresolved_constant_groups={report.unresolved_constant_groups}\n"
        f"unresolved_exceptions={report.unresolved_exceptions}\n"
        f"audit_only_unconfirmed={report.audit_only_unconfirmed}\n"
        f"ready_for_application={report.ready_for_application}\n"
        f"blocking_issues={len(report.blocking_issues)}\n"
        "CHECKPOINT-1 is not closed\n"
        "No human decisions have been applied\n"
        "S4 remains blocked"
    )
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

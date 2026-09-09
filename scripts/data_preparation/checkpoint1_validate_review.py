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

from adapters.ena_checkpoint1_review import (  # noqa: E402
    EnaCheckpoint1ReviewError,
    read_csv_rows as read_ena_csv_rows,
    validate_ena_review_package,
)
from adapters.aptadb_checkpoint1_review import (  # noqa: E402
    AptaDBCheckpoint1ReviewError,
    read_csv_rows,
    validate_review_package,
)
from s0_build_registry import find_repo_root  # noqa: E402

SUPPORTED_SOURCES = ("aptadb", "riboaptamer", "aptaindex", "ena", "aptamerbase")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate CHECKPOINT-1 review files without applying them."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source key (aptadb, riboaptamer, aptaindex, ena, or aptamerbase)",
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
    exception_name = ""
    reconciliation_name = ""
    if args.source == "riboaptamer":
        default_checkpoint = Path("data/interim/checkpoints/riboaptamer_cp1")
        queue_name = "riboaptamer_checkpoint1_manual_review.csv"
        group_name = "riboaptamer_checkpoint1_constant_group_review.csv"
        bulk_name = "riboaptamer_checkpoint1_bulk_audit_confirmation.csv"
    elif args.source == "aptaindex":
        default_checkpoint = Path("data/interim/checkpoints/aptaindex_cp1")
        queue_name = "aptaindex_checkpoint1_manual_review.csv"
        group_name = "aptaindex_checkpoint1_constant_group_review.csv"
        bulk_name = "aptaindex_checkpoint1_bulk_audit_confirmation.csv"
    elif args.source == "ena":
        default_checkpoint = Path("data/interim/checkpoints/ena_cp1")
        queue_name = "ena_checkpoint1_manual_review.csv"
        group_name = "ena_checkpoint1_constant_rule_review.csv"
        bulk_name = "ena_checkpoint1_bulk_audit_confirmation.csv"
        exception_name = "ena_checkpoint1_constant_exceptions.csv"
        reconciliation_name = "ena_checkpoint1_legacy_collapse_reconciliation.csv"
    elif args.source == "aptamerbase":
        default_checkpoint = Path("data/interim/checkpoints/aptamerbase_cp1")
        queue_name = "aptamerbase_checkpoint1_manual_review.csv"
        group_name = "aptamerbase_checkpoint1_constant_group_review.csv"
        bulk_name = "aptamerbase_checkpoint1_bulk_audit_confirmation.csv"
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
        if args.source == "ena":
            queue_rows = read_ena_csv_rows(queue_path)
            group_rows = read_ena_csv_rows(group_path) if group_path.is_file() else []
            bulk_rows = read_ena_csv_rows(bulk_path) if bulk_path.is_file() else []
            exception_path = review_dir / exception_name
            reconciliation_path = review_dir / reconciliation_name
            exception_rows = (
                read_ena_csv_rows(exception_path) if exception_path.is_file() else []
            )
            reconciliation_rows = (
                read_ena_csv_rows(reconciliation_path)
                if reconciliation_path.is_file()
                else []
            )
            bulk = bulk_rows[0] if bulk_rows else None
            report = validate_ena_review_package(
                queue_rows=queue_rows,
                rule_rows=group_rows,
                exception_rows=exception_rows,
                reconciliation_rows=reconciliation_rows,
                bulk_confirmation=bulk,
            )
        else:
            if args.source == "riboaptamer":
                from adapters.riboaptamer_checkpoint1_review import (
                    normalise_riboaptamer_review_rows,
                    read_riboaptamer_review_csv,
                )

                queue_rows = normalise_riboaptamer_review_rows(
                    read_riboaptamer_review_csv(queue_path)
                )
            else:
                queue_rows = read_csv_rows(queue_path)
            group_rows = read_csv_rows(group_path) if group_path.is_file() else []
            bulk_rows = read_csv_rows(bulk_path) if bulk_path.is_file() else []
            bulk = bulk_rows[0] if bulk_rows else None
            report = validate_review_package(
                queue_rows=queue_rows,
                group_rows=group_rows,
                bulk_confirmation=bulk,
            )
    except (AptaDBCheckpoint1ReviewError, EnaCheckpoint1ReviewError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"source={args.source}\n"
        f"total_review_records={report.total_review_records}\n"
        f"unresolved_manual_decisions={report.unresolved_manual_decisions}\n"
        f"unresolved_judgement_required={getattr(report, 'unresolved_judgement_required', 0)}\n"
        f"unresolved_constant_groups={report.unresolved_constant_groups}\n"
        f"unresolved_exceptions={report.unresolved_exceptions}\n"
        f"audit_only_rows={getattr(report, 'audit_only_rows', 0)}\n"
        f"audit_only_unconfirmed={report.audit_only_unconfirmed}\n"
        f"bulk_audit_confirmed={str(getattr(report, 'bulk_audit_confirmed', False)).lower()}\n"
        f"ready_for_application={report.ready_for_application}\n"
        f"blocking_issues={len(report.blocking_issues)}"
    )
    if args.source == "ena":
        print(
            "unresolved_reconciliation_groups="
            f"{getattr(report, 'unresolved_reconciliation_groups', 0)}"
        )
    metadata_rel = Path(
        f"config/checkpoint_reviews/{args.source}_checkpoint1_metadata.json"
    )
    metadata_path = repo_root / metadata_rel
    if metadata_path.is_file():
        import json

        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        closed = bool(payload.get("checkpoint_closed"))
        print(f"checkpoint_closed={str(closed).lower()}")
        print(f"s4_started={str(bool(payload.get('s4_started'))).lower()}")
        if closed and report.ok:
            print("CHECKPOINT-1 CLOSED: human review has been applied and validated")
            print("S4 remains blocked until a later global handoff is executed")
            return 0
    print("CHECKPOINT-1 is not closed")
    print("No human decisions have been applied")
    print("S4 remains blocked")
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""S5A exact scientific deduplication.

Collapses frozen S4 primary relationships on
``(sequence_core, canonical_target_name)`` and merges provenance.

Does not cluster sequences, install or invoke MMseqs2/CD-HIT, merge S4
target dictionary IDs globally, resolve NCBI/ENA duplicates, balance
targets, or assign FT/REF/EVAL.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s4_scientific_common import (  # noqa: E402
    ScientificProposalError,
    assert_no_sequence_leak,
    write_text_atomic,
)
from adapters.s5_exact_dedup import (  # noqa: E402
    CORPUS_DEDUP_COLUMNS,
    DICTIONARY_CONFLICT_COLUMNS,
    GROUP_COLUMNS,
    MEMBERSHIP_COLUMNS,
    MULTI_TARGET_COLUMNS,
    OVERLAP_MATRIX_COLUMNS,
    S5ExactDedupError,
    build_s5a_report,
    exact_deduplicate,
    expected_count_errors,
)
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402

DEFAULT_CONFIG = Path("config/global_s5a_exact_dedup.json")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _resolve(root: Path, relative: str) -> Path:
    return (root / relative).resolve()


def _verify_hashes(root: Path, expected: Mapping[str, Sequence[str]]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for name, spec in expected.items():
        rel, digest = spec
        path = _resolve(root, rel)
        got = sha256_file(path)
        observed[name] = got
        if got != digest:
            raise S5ExactDedupError(
                f"{name} SHA-256 mismatch: expected {digest}, got {got}"
            )
    return observed


def _payload_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_git_ls_files_data_empty(root: Path) -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "data"],
        cwd=root,
        text=True,
    ).strip()
    if tracked:
        raise S5ExactDedupError("git ls-files data is not empty")


def run_s5a_exact_dedup(
    *,
    config_path: Path,
    repo_root: Path | None = None,
    enforce_expected_counts: bool = True,
    verify_s4_hashes: bool = True,
    repeat_for_determinism: bool = True,
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config = json.loads(_resolve(root, str(config_path)).read_text(encoding="utf-8"))
    hashes_before = {}
    if verify_s4_hashes:
        hashes_before = _verify_hashes(root, config["expected_hashes"])
        _assert_git_ls_files_data_empty(root)

    relationship_path = _resolve(root, config["reviewed_relationships_csv"])
    combined_path = _resolve(root, config["combined_input_csv"])
    relationship_rows = _read_csv(relationship_path)
    combined_rows = _read_csv(combined_path)
    combined_by_record_id = {
        row["record_id"]: row for row in combined_rows if row.get("record_id")
    }
    if len(combined_by_record_id) != len(combined_rows):
        raise S5ExactDedupError("combined input record_id values are not unique")

    result = exact_deduplicate(
        relationship_rows,
        combined_by_record_id=combined_by_record_id,
        overlap_source_keys=config.get("overlap_source_keys"),
    )
    if enforce_expected_counts:
        errors = expected_count_errors(result.diagnostics, config["expected_counts"])
        if errors:
            raise S5ExactDedupError(
                "S5A expected-count regression:\n" + "\n".join(errors)
            )

    if repeat_for_determinism:
        shuffled = list(relationship_rows)
        shuffled.reverse()
        repeat = exact_deduplicate(
            shuffled,
            combined_by_record_id=combined_by_record_id,
            overlap_source_keys=config.get("overlap_source_keys"),
        )
        comparable = (
            ("corpus_dedup", result.corpus_dedup, repeat.corpus_dedup),
            ("membership", result.membership, repeat.membership),
            ("duplicate_groups", result.duplicate_groups, repeat.duplicate_groups),
            (
                "dictionary_id_conflicts",
                result.dictionary_id_conflicts,
                repeat.dictionary_id_conflicts,
            ),
            (
                "multi_target_sequences",
                result.multi_target_sequences,
                repeat.multi_target_sequences,
            ),
            ("overlap_matrix", result.overlap_matrix, repeat.overlap_matrix),
        )
        for label, first, second in comparable:
            if first != second:
                raise S5ExactDedupError(
                    f"S5A outputs are not order-independent: {label} differed"
                )

    output_dir = _resolve(root, config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "corpus_dedup_csv": output_dir / "corpus_dedup.csv",
        "membership_csv": output_dir / "exact_duplicate_membership.csv",
        "groups_csv": output_dir / "exact_duplicate_groups.csv",
        "dictionary_conflicts_csv": output_dir / "target_dictionary_id_conflicts.csv",
        "multi_target_csv": output_dir / "multi_target_sequence_report.csv",
        "overlap_matrix_csv": output_dir / "exact_overlap_matrix.csv",
        "report_md": output_dir / "s5a_exact_dedup_report.md",
    }
    write_corpus_csv_atomic(
        outputs["corpus_dedup_csv"],
        result.corpus_dedup,
        columns=CORPUS_DEDUP_COLUMNS,
    )
    write_corpus_csv_atomic(
        outputs["membership_csv"],
        result.membership,
        columns=MEMBERSHIP_COLUMNS,
    )
    write_corpus_csv_atomic(
        outputs["groups_csv"],
        result.duplicate_groups,
        columns=GROUP_COLUMNS,
    )
    write_corpus_csv_atomic(
        outputs["dictionary_conflicts_csv"],
        result.dictionary_id_conflicts,
        columns=DICTIONARY_CONFLICT_COLUMNS,
    )
    write_corpus_csv_atomic(
        outputs["multi_target_csv"],
        result.multi_target_sequences,
        columns=MULTI_TARGET_COLUMNS,
    )
    write_corpus_csv_atomic(
        outputs["overlap_matrix_csv"],
        result.overlap_matrix,
        columns=OVERLAP_MATRIX_COLUMNS,
    )
    report = build_s5a_report(result)
    assert_no_sequence_leak(report, label="s5a_exact_dedup_report.md")
    write_text_atomic(outputs["report_md"], report)

    output_hashes = {name: _payload_hash(path) for name, path in outputs.items()}
    hashes_after = {}
    if verify_s4_hashes:
        hashes_after = _verify_hashes(root, config["expected_hashes"])
        if hashes_after != hashes_before:
            raise S5ExactDedupError("S4 hashes changed during S5A")
        _assert_git_ls_files_data_empty(root)

    return {
        "ok": True,
        "diagnostics": result.diagnostics,
        "output_paths": {name: str(path) for name, path in outputs.items()},
        "output_hashes": output_hashes,
        "s4_hashes_before": hashes_before,
        "s4_hashes_after": hashes_after,
        "n_dictionary_id_conflicts": len(result.dictionary_id_conflicts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="S5A exact scientific (sequence, target) deduplication"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--skip-expected-counts",
        action="store_true",
        help="Do not enforce live S4 regression counts (synthetic use only)",
    )
    parser.add_argument(
        "--skip-s4-hash-gate",
        action="store_true",
        help="Do not verify frozen S4 hashes (synthetic use only)",
    )
    args = parser.parse_args()
    try:
        result = run_s5a_exact_dedup(
            config_path=args.config,
            enforce_expected_counts=not args.skip_expected_counts,
            verify_s4_hashes=not args.skip_s4_hash_gate,
        )
    except (S5ExactDedupError, ScientificProposalError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "n_input_relationships": result["diagnostics"]["n_input_relationships"],
                "n_scientific_identities": result["diagnostics"]["n_scientific_identities"],
                "n_exact_duplicate_groups": result["diagnostics"][
                    "n_exact_duplicate_groups"
                ],
                "n_membership_rows": result["diagnostics"]["n_membership_rows"],
                "n_target_dictionary_id_conflict_groups": result["diagnostics"][
                    "n_target_dictionary_id_conflict_groups"
                ],
                "output_hashes": result["output_hashes"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

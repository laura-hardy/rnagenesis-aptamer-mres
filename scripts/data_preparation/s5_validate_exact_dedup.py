#!/usr/bin/env python3
"""S5B exact-dedup validation, schema reconciliation, and scientific freeze.

Validates frozen S5A outputs against the original 1460 primary S4
relationships. Does not cluster, rewrite S4/S5A scientific files, or
begin S6/S7.
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
    write_json_atomic,
    write_text_atomic,
)
from adapters.s5_validate_exact_dedup import (  # noqa: E402
    S5ValidateError,
    build_s5b_report,
    scan_paths_for_sequence_leak,
    validate_exact_dedup,
)
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402

DEFAULT_CONFIG = Path("config/global_s5b_exact_dedup_validation.json")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _resolve(root: Path, relative: str) -> Path:
    return (root / relative).resolve()


def _payload_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_hashes(root: Path, expected: Mapping[str, Sequence[str]]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for name, spec in expected.items():
        rel, digest = spec
        path = _resolve(root, rel)
        got = sha256_file(path)
        observed[name] = got
        if got != digest:
            raise S5ValidateError(
                f"{name} SHA-256 mismatch: expected {digest}, got {got}"
            )
    return observed


def _assert_git_ls_files_data_empty(root: Path) -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "data"],
        cwd=root,
        text=True,
    ).strip()
    if tracked:
        raise S5ValidateError("git ls-files data is not empty")


def run_s5b_validation(
    *,
    config_path: Path,
    repo_root: Path | None = None,
    verify_hashes: bool = True,
    write_outputs: bool = True,
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config = json.loads(_resolve(root, str(config_path)).read_text(encoding="utf-8"))
    s4_hashes = {}
    s5a_hashes = {}
    if verify_hashes:
        s4_hashes = _verify_hashes(root, config["expected_s4_hashes"])
        s5a_hashes = _verify_hashes(root, config["expected_s5a_hashes"])
        _assert_git_ls_files_data_empty(root)

    relationship_rows = _read_csv(_resolve(root, config["reviewed_relationships_csv"]))
    record_map_rows = _read_csv(_resolve(root, config["record_map_csv"]))
    parked_audit_rows = _read_csv(_resolve(root, config["parked_audit_csv"]))
    output_dir = _resolve(root, config["s5a_output_dir"])
    corpus_rows = _read_csv(output_dir / "corpus_dedup.csv")
    membership_rows = _read_csv(output_dir / "exact_duplicate_membership.csv")
    group_rows = _read_csv(output_dir / "exact_duplicate_groups.csv")
    conflict_rows = _read_csv(output_dir / "target_dictionary_id_conflicts.csv")

    result = validate_exact_dedup(
        relationship_rows=relationship_rows,
        corpus_rows=corpus_rows,
        membership_rows=membership_rows,
        group_rows=group_rows,
        dictionary_conflict_rows=conflict_rows,
        record_map_rows=record_map_rows,
        parked_audit_rows=parked_audit_rows,
        expected=config.get("expected_counts"),
        enforce_live_counts=True,
        regression_relationship_id=config.get(
            "regression_relationship_id", "aptamerbase:1110|2"
        ),
    )

    scan_paths = [
        _resolve(root, rel) for rel in config.get("sequence_safety_scan_paths", [])
    ]
    scan_paths = [path for path in scan_paths if path.exists()]
    leaked = scan_paths_for_sequence_leak(scan_paths)
    if leaked:
        result.errors.append(
            "sequence leak in tracked S5 files: " + ", ".join(str(path) for path in leaked)
        )
        result.ok = False
    sequence_safety = {
        "n_paths_scanned": len(scan_paths),
        "n_leaks": len(leaked),
        "leaked_paths": [str(path) for path in leaked],
        "historical_log_sequences_present": True,
    }

    report = build_s5b_report(
        result,
        s4_hashes=s4_hashes,
        s5a_hashes=s5a_hashes,
        sequence_safety=sequence_safety,
    )
    assert_no_sequence_leak(report, label="s5b_validation_report.md")

    output_paths: dict[str, str] = {}
    if write_outputs:
        report_path = _resolve(root, config["output_report_md"])
        summary_path = _resolve(root, config["output_summary_json"])
        write_text_atomic(report_path, report)
        summary = {
            "ok": result.ok,
            "errors": result.errors,
            "diagnostics": result.diagnostics,
            "s4_hashes": s4_hashes,
            "s5a_hashes": s5a_hashes,
            "sequence_safety": sequence_safety,
            "s5a_freeze_hashes": s5a_hashes,
        }
        write_json_atomic(summary_path, summary)
        output_paths = {
            "report_md": str(report_path),
            "summary_json": str(summary_path),
            "report_sha256": _payload_hash(report_path),
            "summary_sha256": _payload_hash(summary_path),
        }
        if verify_hashes:
            s4_after = _verify_hashes(root, config["expected_s4_hashes"])
            s5a_after = _verify_hashes(root, config["expected_s5a_hashes"])
            if s4_after != s4_hashes:
                raise S5ValidateError("S4 hashes changed during S5B")
            if s5a_after != s5a_hashes:
                raise S5ValidateError("S5A scientific outputs changed during S5B")
            _assert_git_ls_files_data_empty(root)

    if not result.ok:
        raise S5ValidateError(
            "S5B validation NO-GO:\n" + "\n".join(result.errors)
        )
    return {
        "ok": True,
        "diagnostics": result.diagnostics,
        "s4_hashes": s4_hashes,
        "s5a_hashes": s5a_hashes,
        "sequence_safety": sequence_safety,
        "output_paths": output_paths,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="S5B exact-dedup validation and scientific freeze"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--skip-hash-gate",
        action="store_true",
        help="Do not verify frozen S4/S5A hashes (synthetic use only)",
    )
    args = parser.parse_args()
    try:
        result = run_s5b_validation(
            config_path=args.config,
            verify_hashes=not args.skip_hash_gate,
        )
    except (S5ValidateError, ScientificProposalError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "n_input_relationships": result["diagnostics"]["n_input_relationships"],
                "n_scientific_identities": result["diagnostics"]["n_scientific_identities"],
                "n_membership_rows": result["diagnostics"]["n_membership_rows"],
                "donor_decision_distribution": result["diagnostics"][
                    "donor_decision_distribution"
                ],
                "row_identity": result["diagnostics"]["row_identity"],
                "ena_readiness": result["diagnostics"]["ena_readiness"],
                "s5a_hashes": result["s5a_hashes"],
                "output_paths": result["output_paths"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

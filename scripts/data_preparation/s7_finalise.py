#!/usr/bin/env python3
"""GLOBAL S7D — final corpus assembly, diagnostics, reporting, and validation.

Copies frozen S7A/S7B/S7C artefacts into ignored ``data/processed/``, writes
TRAIN-only ``corpus_final.txt``, concatenates authoritative parked/rejected
lanes, and re-runs integrity gates. Does not alter frozen splits or start
modelling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s7_final_build import (  # noqa: E402
    AUDIT_PAYLOAD_NAMES,
    SCIENTIFIC_PAYLOAD_NAMES,
    S7DFinalBuildError,
    run_s7d_final_build,
)
from s0_build_registry import find_repo_root  # noqa: E402

DEFAULT_CONFIG = Path("config/global_s7d_final_build.json")


def _payload_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compare_payloads(first: Path, second: Path) -> None:
    for name in SCIENTIFIC_PAYLOAD_NAMES + AUDIT_PAYLOAD_NAMES:
        left = first / name
        right = second / name
        if not left.is_file() or not right.is_file():
            raise S7DFinalBuildError(f"determinism payload missing: {name}")
        if _payload_hash(left) != _payload_hash(right):
            raise S7DFinalBuildError(
                f"S7D payload {name} is not byte-identical across reruns"
            )
    left_repl = first / "corpus_replication_datasetA.csv"
    right_repl = second / "corpus_replication_datasetA.csv"
    if left_repl.is_file() or right_repl.is_file():
        if not left_repl.is_file() or not right_repl.is_file():
            raise S7DFinalBuildError("Dataset A replication presence differed across reruns")
        if _payload_hash(left_repl) != _payload_hash(right_repl):
            raise S7DFinalBuildError(
                "corpus_replication_datasetA.csv is not byte-identical across reruns"
            )


def run_with_config(
    *,
    config_path: Path,
    repo_root: Path | None = None,
    verify_hashes: bool = True,
    enforce_expected_counts: bool = True,
    write_outputs: bool = True,
    repeat_for_determinism: bool = True,
    run_sequence_safety: bool = True,
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    config = json.loads((root / config_path).read_text(encoding="utf-8"))
    output_dir = (root / config["output_dir"]).resolve()
    determinism_ok = True
    if write_outputs and repeat_for_determinism:
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="s7d_a_", dir=str(output_dir)
        ) as first_dir, tempfile.TemporaryDirectory(
            prefix="s7d_b_", dir=str(output_dir)
        ) as second_dir:
            run_s7d_final_build(
                config=config,
                repo_root=root,
                output_dir=Path(first_dir),
                verify_hashes=verify_hashes,
                enforce_expected_counts=enforce_expected_counts,
                write_outputs=True,
                run_sequence_safety=False,
            )
            run_s7d_final_build(
                config=config,
                repo_root=root,
                output_dir=Path(second_dir),
                verify_hashes=verify_hashes,
                enforce_expected_counts=enforce_expected_counts,
                write_outputs=True,
                run_sequence_safety=False,
            )
            _compare_payloads(Path(first_dir), Path(second_dir))
    result = run_s7d_final_build(
        config=config,
        repo_root=root,
        output_dir=output_dir if write_outputs else output_dir,
        verify_hashes=verify_hashes,
        enforce_expected_counts=enforce_expected_counts,
        write_outputs=write_outputs,
        run_sequence_safety=run_sequence_safety,
    )
    result["determinism_ok"] = determinism_ok
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="S7D final corpus build and validation")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--skip-hash-gate", action="store_true")
    parser.add_argument("--skip-expected-counts", action="store_true")
    parser.add_argument("--skip-determinism-repeat", action="store_true")
    parser.add_argument("--skip-sequence-safety", action="store_true")
    args = parser.parse_args()
    try:
        result = run_with_config(
            config_path=args.config,
            verify_hashes=not args.skip_hash_gate,
            enforce_expected_counts=not args.skip_expected_counts,
            repeat_for_determinism=not args.skip_determinism_repeat,
            run_sequence_safety=not args.skip_sequence_safety,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "s7d_final_build",
                    "corpus_final_sha256": result["output_hashes"].get("corpus_final.csv"),
                    "corpus_final_txt_sha256": result["output_hashes"].get("corpus_final.txt"),
                    "n_scientific_identities": result["schema"]["n_scientific_identities"],
                    "n_distinct_sequence_core": result["schema"]["n_distinct_sequence_core"],
                    "n_final_clusters": result["schema"]["n_final_clusters"],
                    "corpus_final_txt_lines": result["corpus_final_txt"]["line_count"],
                    "e5_promoted": False,
                    "non_protein_promoted": False,
                    "model_fine_tuning_started": False,
                    "determinism_ok": result["determinism_ok"],
                    "new_s7d_tracked_sequence_leaks": result["sequence_safety"][
                        "new_s7d_tracked_sequence_leaks"
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except S7DFinalBuildError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

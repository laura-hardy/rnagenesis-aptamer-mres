#!/usr/bin/env python3
"""CLI entry point for Aim 3 Stage 1 hard filtering."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aim3_pipeline.config import load_stage1_config  # noqa: E402
from aim3_pipeline.io import resolve_input_files  # noqa: E402
from aim3_pipeline.stage1_hard_filter import (  # noqa: E402
    EditDistanceDependencyError,
    RNAImportError,
    run_stage1_hard_filter,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Aim 3 Stage 1 hard filtering on RNAGenesis-style raw sequence files."
        )
    )
    parser.add_argument(
        "--input-glob",
        required=True,
        help='Glob for input sequence files (e.g. "results/phase2_medium_test/*.txt").',
    )
    parser.add_argument(
        "--condition",
        required=True,
        help="Condition label recorded in outputs (e.g. unadapted_medium_test).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for Stage 1 CSV/JSON/FASTA outputs.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs" / "stage1_hard_filter_default.json",
        help="Path to Stage 1 JSON config.",
    )
    parser.add_argument(
        "--reference-corpus",
        type=Path,
        default=None,
        help="Optional reference/training corpus (FASTA, CSV, or plain text).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of sequences to process (smoke tests).",
    )
    parser.add_argument(
        "--skip-mfe",
        action="store_true",
        help="Skip ViennaRNA MFE calculation (quick tests only).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = args.config.expanduser().resolve()
    if not config_path.is_file():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        config = load_stage1_config(config_path)
        input_files = resolve_input_files(args.input_glob)
        reference_corpus = (
            args.reference_corpus.expanduser().resolve()
            if args.reference_corpus
            else None
        )
        if reference_corpus is not None and not reference_corpus.is_file():
            print(f"Reference corpus not found: {reference_corpus}", file=sys.stderr)
            return 1

        df = run_stage1_hard_filter(
            input_files=input_files,
            condition=args.condition,
            config=config,
            output_dir=args.output_dir.expanduser().resolve(),
            config_path=config_path,
            input_glob=args.input_glob,
            reference_corpus=reference_corpus,
            limit=args.limit,
            skip_mfe=args.skip_mfe,
        )
    except (RNAImportError, EditDistanceDependencyError, FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    passed = int(df["stage1_pass"].sum())
    total = len(df)
    print(f"Processed {total} sequences for condition={args.condition}")
    print(f"Stage 1 passed: {passed} ({passed / total:.2%})" if total else "Stage 1 passed: 0")
    print(f"Wrote outputs to {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

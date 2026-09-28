#!/usr/bin/env python3
"""Build the NDM-1 RNA D9 reference layer.

Does not modify frozen RNA corpus files, S0b outputs, or S7D authorities.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.ndm1_rna_references import (  # noqa: E402
    Ndm1RnaError,
    run_ndm1_rna_build,
)
from s0_build_registry import find_repo_root  # noqa: E402

DEFAULT_CONFIG = Path("config/ndm1_rna_reference_build.json")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify von Laer 2013 D9 NDM-1 RNA references from the dissertation."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--repo-root", default="")
    parser.add_argument("--skip-leakage", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    root = Path(args.repo_root).resolve() if args.repo_root else find_repo_root()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    config = json.loads(config_path.read_text(encoding="utf-8"))
    result = run_ndm1_rna_build(
        config=config,
        repo_root=root,
        write_outputs=not args.dry_run,
        run_leakage=not args.skip_leakage,
    )
    counts = result["counts"]
    leakage = result["leakage"]
    print(
        "ndm1_rna_references "
        f"records={counts['reference_records']} "
        f"positive={counts['positive_references']} "
        f"weak={counts['weak_binding_references']} "
        f"no_binding={counts['no_detectable_binding_references']} "
        f"exact_leakage={leakage['any_exact']} "
        f"near_leakage={leakage['any_identity_ge_threshold']}"
    )
    return result


if __name__ == "__main__":
    try:
        main()
    except Ndm1RnaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

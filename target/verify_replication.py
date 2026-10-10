#!/usr/bin/env python3
"""Compare two NDM-1 target runs using prespecified reproducibility criteria."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


EXACT_FIELDS = (
    "pocket_number",
    "alpha_sphere_count_parsed",
    "lining_residues",
    "core_overlap",
    "extended_overlap",
    "zn1_overlap",
    "zn2_overlap",
)


def load_selected(run_dir: Path) -> dict:
    path = run_dir / "results" / "selected_pocket.json"
    return json.loads(path.read_text(encoding="utf-8"))


def compare(reference: dict, replication: dict) -> dict:
    exact = {field: reference[field] == replication[field] for field in EXACT_FIELDS}
    dimension_delta = abs(
        reference["characteristic_dimension_A"] - replication["characteristic_dimension_A"]
    )
    reference_volume = reference["volume_A3"]
    volume_relative_difference = abs(reference_volume - replication["volume_A3"]) / reference_volume
    passed = (
        all(exact.values())
        and math.isclose(dimension_delta, 0.0, abs_tol=1e-6)
        and volume_relative_difference <= 0.10
    )
    return {
        "status": "pass" if passed else "fail",
        "exact_field_matches": exact,
        "characteristic_dimension_absolute_difference_A": dimension_delta,
        "characteristic_dimension_tolerance_A": 1e-6,
        "fpocket_volume_relative_difference": volume_relative_difference,
        "fpocket_volume_relative_tolerance": 0.10,
        "note": (
            "fpocket Volume is stochastic and does not participate in pocket selection; "
            "the 10% bound is a QC check, not a scientific acceptance threshold"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_run", type=Path)
    parser.add_argument("replication_run", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare(load_selected(args.reference_run), load_selected(args.replication_run))
    serialised = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialised, encoding="utf-8")
    print(serialised, end="")
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

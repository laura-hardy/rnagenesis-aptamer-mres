#!/usr/bin/env python3
"""Prepare and freeze the approved NDM-1 5ZGX chain-A pocket target.

This workflow deliberately performs target-only computations.  It never reads
aptamer sequences or scores.  It prepares two coordinate files from an RCSB
PDB download, runs fpocket once on the protein-only file, applies the
prespecified catalytic-residue overlap rule, and writes machine-readable
provenance and an AptaRank target configuration.

The characteristic pocket dimension follows the AptaRank paper workflow:
principal-axis extents are calculated from fpocket alpha-sphere centres as
``2 * singular_value / sqrt(n_spheres)`` and the largest extent is primary.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np


PDB_ID = "5ZGX"
CHAIN_ID = "A"
TARGET_CONFIG_ID = "NDM1_5ZGX_A_CATALYTIC_GROOVE_POCKET_V1"
RCSB_DOWNLOAD_URL = "https://files.rcsb.org/download/5ZGX.pdb"
EXPECTED_RAW_PDB_SHA256 = "2e185a205c9be0bf76484e8ffb96ae225880723ed68eaaf25dffbbccaf01ff51"
FPOCKET_VOLUME_ITERATIONS = 300

# Literature-defined metal-coordination residues, PDB author numbering.
CORE_RESIDUES = frozenset({120, 122, 124, 189, 208, 250})
ZN1_RESIDUES = frozenset({120, 122, 189})
ZN2_RESIDUES = frozenset({124, 208, 250})

# Independently defined residues lining the wider catalytic groove.  These are
# used only to resolve a core-overlap tie and to document site coverage.
EXTENDED_RESIDUES = frozenset({65, 67, 70, 73, 93, 123, 211, 219, 220})

ALLOWED_MASTER_HETERO_RESNAMES = frozenset({"ZN", "OH"})
REMOVED_HETERO_RESNAMES = frozenset({"EDO", "HOH"})


class TargetPreparationError(RuntimeError):
    """Raised when a frozen target-preparation requirement is not met."""


@dataclass(frozen=True)
class AtomRecord:
    line: str
    record_type: str
    atom_name: str
    altloc: str
    resname: str
    chain: str
    resseq: int
    icode: str
    occupancy: float
    serial: int

    @property
    def atom_key(self) -> tuple[str, int, str, str, str]:
        return (self.chain, self.resseq, self.icode, self.resname, self.atom_name)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_atom_record(line: str) -> AtomRecord:
    if len(line) < 60 or line[0:6].strip() not in {"ATOM", "HETATM"}:
        raise ValueError("Not an ATOM/HETATM PDB record")
    try:
        return AtomRecord(
            line=line.rstrip("\n"),
            record_type=line[0:6].strip(),
            atom_name=line[12:16].strip(),
            altloc=line[16:17],
            resname=line[17:20].strip(),
            chain=line[21:22],
            resseq=int(line[22:26]),
            icode=line[26:27],
            occupancy=float(line[54:60] or "0"),
            serial=int(line[6:11]),
        )
    except (TypeError, ValueError) as exc:
        raise TargetPreparationError(f"Could not parse PDB coordinate record: {line!r}") from exc


def _altloc_rank(atom: AtomRecord) -> tuple[float, int, int]:
    """Prefer highest occupancy; then blank, then A, deterministically."""
    return (atom.occupancy, int(atom.altloc == " "), int(atom.altloc == "A"))


def select_atom_conformers(atoms: Iterable[AtomRecord]) -> list[AtomRecord]:
    selected: dict[tuple[str, int, str, str, str], AtomRecord] = {}
    for atom in atoms:
        current = selected.get(atom.atom_key)
        if current is None or _altloc_rank(atom) > _altloc_rank(current):
            selected[atom.atom_key] = atom
    return sorted(selected.values(), key=lambda atom: atom.serial)


def _normalise_selected_altloc(line: str) -> str:
    if len(line) < 17:
        return line
    return line[:16] + " " + line[17:]


def _write_coordinate_file(path: Path, remarks: list[str], atoms: list[AtomRecord]) -> None:
    lines = [f"REMARK 950 {remark}" for remark in remarks]
    lines.extend(_normalise_selected_altloc(atom.line) for atom in atoms)
    lines.extend(["TER", "END"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def prepare_structures(raw_pdb: Path, output_dir: Path) -> dict[str, object]:
    text = raw_pdb.read_text(encoding="ascii")
    if PDB_ID not in text[:2000].upper():
        raise TargetPreparationError(f"{raw_pdb} does not identify PDB {PDB_ID}")
    if "X-RAY DIFFRACTION" not in text or "0.95 ANGSTROMS" not in text:
        raise TargetPreparationError("5ZGX method/resolution metadata did not match the frozen target")

    all_atoms = [
        parse_atom_record(line)
        for line in text.splitlines()
        if line.startswith(("ATOM  ", "HETATM"))
    ]
    chain_atoms = [atom for atom in all_atoms if atom.chain == CHAIN_ID]
    protein_atoms = select_atom_conformers(
        atom for atom in chain_atoms if atom.record_type == "ATOM"
    )
    master_hetero = select_atom_conformers(
        atom
        for atom in chain_atoms
        if atom.record_type == "HETATM" and atom.resname in ALLOWED_MASTER_HETERO_RESNAMES
    )

    if len(protein_atoms) <= 100:
        raise TargetPreparationError(f"Prepared protein has only {len(protein_atoms)} atoms")
    residue_numbers = {atom.resseq for atom in protein_atoms}
    required = CORE_RESIDUES | EXTENDED_RESIDUES
    missing = sorted(required - residue_numbers)
    if missing:
        raise TargetPreparationError(f"Required author-numbered residues absent from chain A: {missing}")
    insertion_codes = sorted({atom.icode.strip() for atom in protein_atoms if atom.icode.strip()})
    if insertion_codes:
        raise TargetPreparationError(f"Unexpected insertion codes in chain A: {insertion_codes}")

    master_path = output_dir / "prepared" / "5ZGX_A_biological_master.pdb"
    fpocket_input_path = output_dir / "prepared" / "5ZGX_A_fpocket_input.pdb"
    _write_coordinate_file(
        master_path,
        [
            "5ZGX CHAIN A; AUTHOR NUMBERING PRESERVED.",
            "ALTERNATE LOCATIONS RESOLVED BY OCCUPANCY; TIES PREFER BLANK THEN A.",
            "EDO AND HOH REMOVED; CATALYTIC ZN AND BRIDGING OH RETAINED.",
        ],
        sorted(protein_atoms + master_hetero, key=lambda atom: atom.serial),
    )
    _write_coordinate_file(
        fpocket_input_path,
        [
            "5ZGX CHAIN A; AUTHOR NUMBERING PRESERVED.",
            "PROTEIN-ONLY INPUT MATCHING APTARANK STRIP_HETATM TRUE.",
            "ALTERNATE LOCATIONS RESOLVED BY OCCUPANCY; TIES PREFER BLANK THEN A.",
        ],
        protein_atoms,
    )

    hetero_counts: dict[str, int] = {}
    for atom in chain_atoms:
        if atom.record_type == "HETATM":
            hetero_counts[atom.resname] = hetero_counts.get(atom.resname, 0) + 1

    return {
        "raw_coordinate_records": len(chain_atoms),
        "prepared_protein_atoms": len(protein_atoms),
        "prepared_master_hetero_atoms": len(master_hetero),
        "modeled_residue_count": len(residue_numbers),
        "modeled_residue_min": min(residue_numbers),
        "modeled_residue_max": max(residue_numbers),
        "raw_chain_a_hetero_atom_counts": dict(sorted(hetero_counts.items())),
        "master_path": master_path,
        "fpocket_input_path": fpocket_input_path,
    }


def fpocket_version(fpocket_bin: Path) -> str:
    completed = subprocess.run(
        [str(fpocket_bin)], text=True, capture_output=True, check=False
    )
    match = re.search(r"fpocket\s+([0-9]+(?:\.[0-9]+)+)", completed.stdout + completed.stderr)
    if not match:
        raise TargetPreparationError("Could not determine fpocket version")
    return match.group(1)


def run_fpocket(fpocket_bin: Path, fpocket_input_path: Path, logs_dir: Path) -> Path:
    expected_output = fpocket_input_path.with_name(fpocket_input_path.stem + "_out")
    if expected_output.exists():
        raise TargetPreparationError(
            f"Refusing to overwrite existing fpocket output: {expected_output}"
        )
    completed = subprocess.run(
        [
            str(fpocket_bin), "-f", str(fpocket_input_path),
            "-v", str(FPOCKET_VOLUME_ITERATIONS),
        ],
        cwd=fpocket_input_path.parent,
        text=True,
        capture_output=True,
        check=False,
    )
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "fpocket.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (logs_dir / "fpocket.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise TargetPreparationError(
            f"fpocket failed with exit code {completed.returncode}; see {logs_dir}"
        )
    if not expected_output.is_dir():
        raise TargetPreparationError(f"fpocket did not create {expected_output}")
    return expected_output


def parse_fpocket_info(path: Path) -> dict[int, dict[str, float]]:
    pockets: dict[int, dict[str, float]] = {}
    current: int | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"\s*Pocket\s+(\d+)\s*:?\s*$", raw_line, flags=re.IGNORECASE)
        if heading:
            current = int(heading.group(1))
            pockets.setdefault(current, {})
            continue
        if current is None or ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        number = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", value)
        if number:
            pockets[current][key.strip()] = float(number.group(0))
    if not pockets:
        raise TargetPreparationError(f"No pocket blocks parsed from {path}")
    return pockets


def _descriptor(descriptors: dict[str, float], wanted: str) -> float:
    for key, value in descriptors.items():
        if key.strip().lower() == wanted.lower():
            return value
    raise TargetPreparationError(f"fpocket descriptor {wanted!r} was not present")


def parse_lining_residues(path: Path) -> set[int]:
    residues: set[int] = set()
    for line in path.read_text(encoding="ascii").splitlines():
        if not line.startswith(("ATOM  ", "HETATM")):
            continue
        atom = parse_atom_record(line)
        if atom.chain == CHAIN_ID and atom.record_type == "ATOM":
            residues.add(atom.resseq)
    if not residues:
        raise TargetPreparationError(f"No chain-A protein residues parsed from {path}")
    return residues


def parse_pqr_coordinates(path: Path) -> np.ndarray:
    coords: list[tuple[float, float, float]] = []
    for line in path.read_text(encoding="ascii").splitlines():
        if not line.startswith(("ATOM  ", "HETATM")):
            continue
        try:
            coords.append((float(line[30:38]), float(line[38:46]), float(line[46:54])))
            continue
        except ValueError:
            fields = line.split()
            try:
                coords.append((float(fields[5]), float(fields[6]), float(fields[7])))
            except (IndexError, ValueError) as exc:
                raise TargetPreparationError(f"Could not parse PQR coordinates: {line!r}") from exc
    if len(coords) < 3:
        raise TargetPreparationError(f"Only {len(coords)} alpha-sphere centres parsed from {path}")
    return np.asarray(coords, dtype=float)


def pocket_geometry(coords: np.ndarray, volume_a3: float) -> dict[str, object]:
    centred = coords - coords.mean(axis=0)
    _u, singular_values, _vh = np.linalg.svd(centred, full_matrices=False)
    extents = 2.0 * singular_values / math.sqrt(len(coords))
    equivalent_diameter = 2.0 * ((3.0 * volume_a3) / (4.0 * math.pi)) ** (1.0 / 3.0)
    ratio = max(float(extents[0]), equivalent_diameter) / min(float(extents[0]), equivalent_diameter)
    return {
        "alpha_sphere_count_parsed": int(len(coords)),
        "principal_axis_extents_A": [float(value) for value in extents],
        "characteristic_dimension_A": float(extents[0]),
        "equivalent_sphere_diameter_A": float(equivalent_diameter),
        "dimension_ratio": float(ratio),
        "odd_shape_warning": bool(ratio > 2.0),
    }


def inventory_pockets(fpocket_output: Path) -> list[dict[str, object]]:
    info_path = fpocket_output / "5ZGX_A_fpocket_input_info.txt"
    descriptors_by_number = parse_fpocket_info(info_path)
    inventory: list[dict[str, object]] = []
    for number in sorted(descriptors_by_number):
        pocket_dir = fpocket_output / "pockets"
        atm_path = pocket_dir / f"pocket{number}_atm.pdb"
        vert_path = pocket_dir / f"pocket{number}_vert.pqr"
        if not atm_path.is_file() or not vert_path.is_file():
            raise TargetPreparationError(f"Missing fpocket files for pocket {number}")
        descriptors = descriptors_by_number[number]
        lining = parse_lining_residues(atm_path)
        volume = _descriptor(descriptors, "Volume")
        geometry = pocket_geometry(parse_pqr_coordinates(vert_path), volume)
        inventory.append({
            "pocket_number": number,
            "fpocket_score": _descriptor(descriptors, "Score"),
            "druggability_score": _descriptor(descriptors, "Druggability Score"),
            "volume_A3": volume,
            "lining_residues": sorted(lining),
            "core_overlap": sorted(lining & CORE_RESIDUES),
            "extended_overlap": sorted(lining & EXTENDED_RESIDUES),
            "zn1_overlap": sorted(lining & ZN1_RESIDUES),
            "zn2_overlap": sorted(lining & ZN2_RESIDUES),
            **geometry,
        })
    return inventory


def select_pocket(inventory: list[dict[str, object]]) -> dict[str, object]:
    if not inventory:
        raise TargetPreparationError("No fpocket cavities available for selection")
    max_core = max(len(row["core_overlap"]) for row in inventory)
    if max_core == 0:
        raise TargetPreparationError("No fpocket cavity overlaps a core catalytic residue")
    core_tied = [row for row in inventory if len(row["core_overlap"]) == max_core]
    max_extended = max(len(row["extended_overlap"]) for row in core_tied)
    finalists = [row for row in core_tied if len(row["extended_overlap"]) == max_extended]
    if len(finalists) != 1:
        ids = [row["pocket_number"] for row in finalists]
        raise TargetPreparationError(
            "Prespecified core then extended residue overlap did not identify a unique pocket; "
            f"tied pockets: {ids}. Do not resolve this using candidate scores."
        )
    selected = finalists[0]
    if not selected["zn1_overlap"] or not selected["zn2_overlap"]:
        raise TargetPreparationError(
            f"Pocket {selected['pocket_number']} does not overlap both zinc subsites"
        )
    return selected


def write_inventory_csv(path: Path, inventory: list[dict[str, object]]) -> None:
    fields = [
        "pocket_number", "selected", "fpocket_score", "druggability_score", "volume_A3",
        "alpha_sphere_count_parsed", "characteristic_dimension_A",
        "equivalent_sphere_diameter_A", "dimension_ratio", "odd_shape_warning",
        "principal_axis_extents_A", "core_overlap", "extended_overlap", "zn1_overlap",
        "zn2_overlap", "lining_residues",
    ]
    selected = select_pocket(inventory)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in inventory:
            serialised = dict(row)
            serialised["selected"] = row["pocket_number"] == selected["pocket_number"]
            for field in (
                "principal_axis_extents_A", "core_overlap", "extended_overlap", "zn1_overlap",
                "zn2_overlap", "lining_residues",
            ):
                serialised[field] = "|".join(map(str, serialised[field]))
            writer.writerow({field: serialised[field] for field in fields})


def write_aptarank_target(path: Path) -> None:
    path.write_text(
        "target_name: NDM-1\n"
        "source: pdb\n"
        f"id: {PDB_ID}\n"
        f"chain: {CHAIN_ID}\n"
        "binding_mode: pocket\n"
        "strip_hetatm: true\n"
        f"target_site_residues: [{', '.join(map(str, sorted(CORE_RESIDUES)))}]\n",
        encoding="utf-8",
    )


def write_run_report(path: Path, selected: dict[str, object], pocket_count: int) -> None:
    path.write_text(
        "# Frozen NDM-1 target result\n\n"
        "The score-blind target-preparation workflow selected fpocket cavity "
        f"**{selected['pocket_number']} of {pocket_count}** for PDB 5ZGX chain A. "
        "Selection was based only on overlap with prespecified catalytic-groove residues.\n\n"
        "## Geometry\n\n"
        f"- Volume: **{selected['volume_A3']:.3f} A^3**\n"
        f"- Characteristic dimension: **{selected['characteristic_dimension_A']:.3f} A**\n"
        f"- Equivalent-sphere diameter: **{selected['equivalent_sphere_diameter_A']:.3f} A**\n"
        f"- Principal-axis extents: **{', '.join(f'{value:.3f}' for value in selected['principal_axis_extents_A'])} A**\n"
        f"- fpocket score: **{selected['fpocket_score']:.3f}**\n"
        f"- Druggability score (descriptive only): **{selected['druggability_score']:.3f}**\n"
        f"- Shape cross-check ratio: **{selected['dimension_ratio']:.3f}**; "
        f"odd-shape warning: **{str(selected['odd_shape_warning']).lower()}**\n\n"
        "The fpocket and druggability scores did not select the site and must not be used "
        "to justify the biological site choice. fpocket estimates `Volume` by Monte Carlo "
        "sampling, so its exact value can vary slightly between replications; pocket identity, "
        "lining residues and the alpha-sphere characteristic dimension are the reproducibility "
        "criteria.\n\n"
        "## Residue overlap\n\n"
        f"- Core anchors present: `{', '.join(map(str, selected['core_overlap']))}`\n"
        f"- Zn1 group present: `{', '.join(map(str, selected['zn1_overlap']))}`\n"
        f"- Zn2 group present: `{', '.join(map(str, selected['zn2_overlap']))}`\n"
        f"- Extended groove residues present: `{', '.join(map(str, selected['extended_overlap']))}`\n"
        f"- Complete fpocket lining set: `{', '.join(map(str, selected['lining_residues']))}`\n\n"
        "Residues absent from fpocket's lining-atom file remain part of the prespecified "
        "literature anchor set; absence is not interpreted as evidence about RNA contacts.\n\n"
        "## Interpretation\n\n"
        "The frozen configuration operationalises an RNA loop engaging the shallow NDM-1 "
        "catalytic groove. It is a target-level geometric measurement, not docking or a "
        "prediction of binding, affinity, inhibition, selectivity, or contact residues.\n",
        encoding="utf-8",
    )


def write_sha256_manifest(path: Path, root: Path) -> None:
    rows = []
    for artifact in sorted(root.rglob("*")):
        if artifact.is_file() and artifact != path:
            rows.append(f"{sha256_file(artifact)}  {artifact.relative_to(root)}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-pdb", type=Path, required=True, help="Unmodified RCSB 5ZGX PDB file")
    parser.add_argument("--fpocket-bin", type=Path, required=True, help="fpocket 4.0 executable")
    parser.add_argument("--output-dir", type=Path, required=True, help="New, empty output directory")
    args = parser.parse_args()

    raw_pdb = args.raw_pdb.resolve()
    fpocket_bin = args.fpocket_bin.resolve()
    output_dir = args.output_dir.resolve()
    if not raw_pdb.is_file():
        raise TargetPreparationError(f"Raw PDB not found: {raw_pdb}")
    observed_raw_hash = sha256_file(raw_pdb)
    if observed_raw_hash != EXPECTED_RAW_PDB_SHA256:
        raise TargetPreparationError(
            "Raw 5ZGX hash differs from the frozen RCSB coordinate release: "
            f"expected {EXPECTED_RAW_PDB_SHA256}, observed {observed_raw_hash}"
        )
    if not fpocket_bin.is_file():
        raise TargetPreparationError(f"fpocket executable not found: {fpocket_bin}")
    if output_dir.exists():
        raise TargetPreparationError(f"Output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)

    source_dir = output_dir / "source"
    source_dir.mkdir()
    frozen_source = source_dir / "5ZGX.pdb"
    shutil.copyfile(raw_pdb, frozen_source)

    version = fpocket_version(fpocket_bin)
    if version != "4.0":
        raise TargetPreparationError(f"Expected fpocket 4.0, observed {version}")

    preparation = prepare_structures(frozen_source, output_dir)
    fpocket_output = run_fpocket(
        fpocket_bin, Path(preparation["fpocket_input_path"]), output_dir / "logs"
    )
    inventory = inventory_pockets(fpocket_output)
    selected = select_pocket(inventory)

    results_dir = output_dir / "results"
    results_dir.mkdir()
    inventory_path = results_dir / "pocket_inventory.csv"
    selected_path = results_dir / "selected_pocket.json"
    report_path = results_dir / "run_report.md"
    write_inventory_csv(inventory_path, inventory)
    write_json(selected_path, selected)
    write_run_report(report_path, selected, len(inventory))

    aptarank_path = output_dir / "aptarank_target_5zgx.txt"
    write_aptarank_target(aptarank_path)

    artifact_hashes = {
        str(path.relative_to(output_dir)): sha256_file(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file()
    }
    provenance = {
        "schema_version": "1.0.0",
        "target_config_id": TARGET_CONFIG_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_data_read": False,
        "candidate_scores_used_for_selection": False,
        "target": {
            "canonical_name": "New Delhi metallo-beta-lactamase-1 (NDM-1)",
            "pdb_id": PDB_ID,
            "chain": CHAIN_ID,
            "binding_mode": "pocket",
            "operational_site_description": "shallow catalytic groove",
            "residue_numbering": "PDB author residue numbering",
            "core_selection_residues": sorted(CORE_RESIDUES),
            "tie_break_residues": sorted(EXTENDED_RESIDUES),
            "zn1_residues": sorted(ZN1_RESIDUES),
            "zn2_residues": sorted(ZN2_RESIDUES),
        },
        "source": {
            "download_url": RCSB_DOWNLOAD_URL,
            "expected_and_observed_sha256": observed_raw_hash,
            "experimental_method": "X-RAY DIFFRACTION",
            "resolution_A": 0.95,
        },
        "preparation_policy": {
            "chain_selection": "chain A only",
            "alternate_locations": "highest occupancy; ties prefer blank then A",
            "biological_master": "protein plus ZN and OH; EDO and HOH removed",
            "fpocket_input": "protein only; all HETATM removed",
            "aptarank_strip_hetatm": True,
        },
        "selection_rule": {
            "primary": "maximum count overlap with core_selection_residues",
            "tie_break": "maximum count overlap with tie_break_residues",
            "unresolved_tie": "fail closed",
            "validity_requirement": "selected pocket overlaps at least one Zn1 and one Zn2 residue",
            "automatic_highest_fpocket_score_fallback": False,
            "uses_fpocket_score": False,
            "uses_fpocket_volume": False,
        },
        "software": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "fpocket": version,
            "fpocket_command": (
                "fpocket -f prepared/5ZGX_A_fpocket_input.pdb "
                f"-v {FPOCKET_VOLUME_ITERATIONS}"
            ),
            "fpocket_volume_iterations": FPOCKET_VOLUME_ITERATIONS,
            "fpocket_volume_note": (
                "fpocket Volume is a stochastic Monte Carlo estimate; it is descriptive and "
                "used only for the equivalent-sphere cross-check, not pocket selection"
            ),
            "workflow_source_sha256": sha256_file(Path(__file__).resolve()),
            "environment_file_sha256": sha256_file(Path(__file__).with_name("environment.yml")),
        },
        "structure_summary": {
            key: value
            for key, value in preparation.items()
            if key not in {"master_path", "fpocket_input_path"}
        },
        "fpocket_summary": {
            "pocket_count": len(inventory),
            "selected_pocket_number": selected["pocket_number"],
            "selected_pocket": selected,
        },
        "artifact_sha256_before_provenance": artifact_hashes,
    }
    provenance_path = output_dir / "target_configuration.json"
    write_json(provenance_path, provenance)
    manifest_path = output_dir / "MANIFEST.sha256"
    write_sha256_manifest(manifest_path, output_dir)

    print(json.dumps({
        "status": "complete",
        "output_dir": str(output_dir),
        "selected_pocket_number": selected["pocket_number"],
        "characteristic_dimension_A": selected["characteristic_dimension_A"],
        "volume_A3": selected["volume_A3"],
        "core_overlap": selected["core_overlap"],
        "extended_overlap": selected["extended_overlap"],
        "target_configuration_sha256": sha256_file(provenance_path),
        "manifest_sha256": sha256_file(manifest_path),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

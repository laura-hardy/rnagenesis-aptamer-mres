#!/usr/bin/env python3
"""Materialise blank CHECKPOINT-2 supplemental evidence-consistency review.

Creates the ignored 9-row C2EC* package. Does not record human decisions,
modify the frozen 3-row evidence review, mutate affinity/target/relationship
review, mutate machine proposals, apply CHECKPOINT-2, or run S5.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.checkpoint2_evidence import (  # noqa: E402
    DECISION_ID_ORDERING,
    EVIDENCE_CONSISTENCY_FILE,
    EVIDENCE_CONSISTENCY_REVIEW_COLUMNS,
    EXPECTED_CORRECTED_DISTRIBUTION,
    EXPECTED_DECISION_IDS,
    EXPECTED_GROUP_COUNTS,
    EXPECTED_TRANSITIONS,
    EXPECTED_UNIQUE_RECORDS,
    expected_record_ids,
    materialise_evidence_consistency_review,
    original_evidence_membership,
    validate_group_spec,
)
from adapters.s4_scientific_common import (  # noqa: E402
    HUMAN_FIELDS,
    ScientificProposalError,
    assert_no_sequence_leak,
    write_json_atomic,
    write_text_atomic,
)
from checkpoint2_validate_review import validate_checkpoint2_package  # noqa: E402
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402

REQUIRED_HASHES = {
    "combined_input": (
        "data/interim/global_s4/combined_global_s4_input.csv",
        "24c49bcdb5f313bd9242f4a7b90671150263de532bcb1c55597d82766b55dbf0",
    ),
    "target_review": (
        "data/interim/global_s4/checkpoint2/checkpoint2_target_dictionary_review.csv",
        "ce7c64137b0d0764c137d85b606a500db29139c78c2db753ad4efd250a7ed765",
    ),
    "relationship_review": (
        "data/interim/global_s4/checkpoint2/checkpoint2_relationship_review.csv",
        "a65bfb1eadee660a83cd51ea8d162ba1c1290706a3b720797211a7a0b4d776b9",
    ),
    "evidence_review": (
        "data/interim/global_s4/checkpoint2/checkpoint2_evidence_review.csv",
        "2116183dc4db64f1939149d68e9416f36db8e9b747b4b1d7fbffca1c3c840718",
    ),
    "affinity_review": (
        "data/interim/global_s4/checkpoint2/checkpoint2_affinity_review.csv",
        "08dc960c0c8626f89a4bfdc36c17b029ebbb48d830d12a040c19c6c45a4597f4",
    ),
    "evidence_affinity": (
        "data/interim/global_s4/evidence_affinity_proposals.csv",
        "98753d5ea536e78a33bea0dea62f64db8e58fc25678d728f71b9e115498e413b",
    ),
    "relationship_scientific": (
        "data/interim/global_s4/relationship_scientific_proposals.csv",
        "be18f87a894691801e3beb625bbe5c5ddb23ecff69cd14a48fc21c081ff5b899",
    ),
    "target_dictionary": (
        "data/interim/global_s4/target_dictionary_scientific_proposed.csv",
        "de6cc7ee3164d4a16f91a83980ae4715f0f2e0836aed9db74c994c103045c829",
    ),
    "leakage_proposals": (
        "data/interim/global_s4/leakage_match_proposals.csv",
        "8840028d065a9530f1f90e1a8a41c27904f05466acbd0bb366c1cd51f93d813e",
    ),
    "leakage_review": (
        "data/interim/global_s4/checkpoint2/checkpoint2_leakage_review.csv",
        "9adb73232c363ed440dc776c3c8669784e7232ec8e67f7b55bcf4c0627bfacf7",
    ),
    "routing_preview": (
        "data/interim/global_s4/routing_preview.csv",
        "36026e64ce8d36ab760ab443448bfc0685394802577fce499357920a12060796",
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _human_fields_blank(rows: Sequence[Mapping[str, str]]) -> bool:
    for row in rows:
        for field in HUMAN_FIELDS:
            if (row.get(field) or "").strip():
                return False
    return True


def _readme_after_materialisation(text: str) -> str:
    updated = text
    if "- evidence consistency:" not in updated:
        updated = updated.replace(
            "- leakage: 0",
            "- evidence consistency: 9\n- leakage: 0",
        )
    note = (
        "Milestone 4F.2 materialised a separate 9-row supplemental "
        "evidence-consistency review (`checkpoint2_evidence_consistency_review.csv`). "
        "All C2EC human fields remain blank. The frozen 3-row evidence review "
        "was not modified. Affinity review is unchanged. 49 evidence-affinity "
        "inconsistency records remain blocking. CHECKPOINT-2 has not been applied.\n"
    )
    if "Milestone 4F.2" not in updated:
        updated = updated.rstrip() + "\n\n" + note
    return updated if updated.endswith("\n") else updated + "\n"


def materialise_live_evidence_consistency_package(
    *,
    repo_root: Path,
    package_dir: Path | None = None,
    evidence_path: Path | None = None,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    package_dir = package_dir or (repo_root / "data/interim/global_s4/checkpoint2")
    evidence_path = evidence_path or (
        repo_root / "data/interim/global_s4/evidence_affinity_proposals.csv"
    )
    live_path = package_dir / EVIDENCE_CONSISTENCY_FILE
    validate_group_spec()
    hashes: dict[str, str] = {}
    for name, (relative, expected) in REQUIRED_HASHES.items():
        path = repo_root / relative
        got = sha256_file(path)
        hashes[name] = got
        if got != expected:
            raise ScientificProposalError(f"{name} SHA-256 mismatch: {got}")

    evidence_rows = _read_csv(evidence_path)
    affinity_rows = _read_csv(package_dir / "checkpoint2_affinity_review.csv")
    original_evidence_rows = _read_csv(package_dir / "checkpoint2_evidence_review.csv")
    existing_rows = _read_csv(live_path) if live_path.is_file() else []
    original_map = original_evidence_membership(original_evidence_rows, evidence_rows)
    overlap = sorted(set(expected_record_ids()) & set(original_map))
    if overlap:
        raise ScientificProposalError(
            "C2EC records overlap closed C2E0001-C2E0003: " + "|".join(overlap)
        )

    materialised = materialise_evidence_consistency_review(
        evidence_rows,
        affinity_rows,
        original_evidence_rows,
        existing_rows,
        columns=EVIDENCE_CONSISTENCY_REVIEW_COLUMNS,
    )
    if [row["decision_id"] for row in materialised] != list(EXPECTED_DECISION_IDS):
        raise ScientificProposalError("live C2EC decision IDs drifted")
    if not existing_rows and not _human_fields_blank(materialised):
        raise ScientificProposalError("first materialisation populated human fields")

    write_corpus_csv_atomic(
        live_path, materialised, columns=EVIDENCE_CONSISTENCY_REVIEW_COLUMNS
    )
    post_sha = sha256_file(live_path)
    hashes["evidence_consistency_review"] = post_sha
    rematerialised = materialise_evidence_consistency_review(
        evidence_rows,
        affinity_rows,
        original_evidence_rows,
        _read_csv(live_path),
        columns=EVIDENCE_CONSISTENCY_REVIEW_COLUMNS,
    )
    write_corpus_csv_atomic(
        live_path, rematerialised, columns=EVIDENCE_CONSISTENCY_REVIEW_COLUMNS
    )
    idempotent_sha = sha256_file(live_path)
    if idempotent_sha != post_sha:
        raise ScientificProposalError("evidence-consistency materialisation is not idempotent")

    for name, (relative, expected) in REQUIRED_HASHES.items():
        got = sha256_file(repo_root / relative)
        if got != expected:
            raise ScientificProposalError(
                f"{name} changed during evidence-consistency materialisation: {got}"
            )

    validator = validate_checkpoint2_package(package_dir)
    if validator["errors"]:
        raise ScientificProposalError(f"validator errors: {validator['errors']}")
    completion = validator["evidence_consistency_completion"]
    if completion.get("blank") != 9 or completion.get("resolved") != 0:
        raise ScientificProposalError(
            f"expected supplemental 0 resolved / 9 blank, got {completion}"
        )
    if validator["unresolved_decisions"] != 9:
        raise ScientificProposalError(
            f"expected unresolved=9, got {validator['unresolved_decisions']}"
        )
    if validator["n_evidence_affinity_inconsistencies"] != EXPECTED_UNIQUE_RECORDS:
        raise ScientificProposalError(
            "expected 49 evidence-affinity flags, got "
            f"{validator['n_evidence_affinity_inconsistencies']}"
        )
    if validator["ready_for_application"]:
        raise ScientificProposalError("package must not be ready for application")
    if validator["target_completion"].get("blank", 0) != 0:
        raise ScientificProposalError("target review is no longer complete")
    by_file = validator["decision_counts_by_file"]
    if by_file.get("checkpoint2_evidence_review.csv", {}).get("BLANK", 0):
        raise ScientificProposalError("original evidence review is no longer complete")
    if by_file.get("checkpoint2_affinity_review.csv", {}).get("BLANK", 0):
        raise ScientificProposalError("affinity review is no longer complete")

    readme_path = package_dir / "README.md"
    if readme_path.is_file():
        write_text_atomic(readme_path, _readme_after_materialisation(readme_path.read_text(encoding="utf-8")))

    groups = [
        {
            "decision_id": row["decision_id"],
            "n_records": int(row["n_records"]),
            "source_db": row["source_db"],
            "machine_evidence_level": row["evidence_level_proposed"],
            "corrected_evidence_level": row["corrected_evidence_level_proposed"],
            "affinity_decision_id": row["affinity_decision_id"],
            "reviewed_affinity_outcome": row["reviewed_affinity_outcome"],
            "record_ids": row["record_ids"].split("|") if row.get("record_ids") else [],
            "human_fields_blank": not any(
                (row.get(field) or "").strip() for field in HUMAN_FIELDS
            ),
        }
        for row in rematerialised
    ]
    payload = {
        "milestone": "4F.2",
        "n_rows": 9,
        "n_unique_records": EXPECTED_UNIQUE_RECORDS,
        "decision_ids": list(EXPECTED_DECISION_IDS),
        "decision_id_ordering": list(DECISION_ID_ORDERING),
        "group_counts": dict(EXPECTED_GROUP_COUNTS),
        "corrected_distribution": dict(EXPECTED_CORRECTED_DISTRIBUTION),
        "transitions": {
            f"{src}->{dst}": count for (src, dst), count in EXPECTED_TRANSITIONS.items()
        },
        "human_fields_blank": _human_fields_blank(rematerialised),
        "human_decisions_recorded": False,
        "original_evidence_review_frozen": True,
        "affinity_review_unchanged": True,
        "groups": groups,
        "hashes": hashes,
        "validator": {
            "ready_for_application": validator["ready_for_application"],
            "unresolved_decisions": validator["unresolved_decisions"],
            "evidence_consistency_completion": completion,
            "n_evidence_affinity_inconsistencies": validator[
                "n_evidence_affinity_inconsistencies"
            ],
            "target_blank": validator["target_completion"]["blank"],
        },
        "checkpoint2_applied": False,
        "combined_input_modified": False,
        "s5_run": False,
    }
    write_json_atomic(
        package_dir / "human_review" / "evidence_consistency_materialisation_manifest.json",
        payload,
    )
    note_lines = [
        "# CHECKPOINT-2 supplemental evidence-consistency review",
        "",
        "Milestone 4F.2 materialised a **blank** 9-row supplemental evidence-consistency",
        "package. Human decisions were **not** recorded. The frozen 3-row evidence",
        "review (`C2E0001`–`C2E0003`) was not modified. Affinity review is unchanged.",
        "Machine proposal tables were not mutated. CHECKPOINT-2 was not applied.",
        "S5 was not run. Combined input is unchanged.",
        "",
        "These 49 records are a cross-grain reconciliation between completed evidence",
        "and completed affinity review, not a reopening of the E4/E5 threshold grain.",
        "",
        "## Decision-ID ordering",
        "",
        "Independent of CSV row order:",
        "",
    ]
    for item in DECISION_ID_ORDERING:
        note_lines.append(f"- {item}")
    note_lines.extend(
        [
            "",
            "Within `C2A0004B`, the E3 remainder subgroup (`C2EC0003`) is assigned",
            "before the E5 annotation-only subgroup (`C2EC0004`).",
            "",
            "## Group counts",
            "",
            "```text",
            "C2EC0001 = 4",
            "C2EC0002 = 9",
            "C2EC0003 = 19",
            "C2EC0004 = 6",
            "C2EC0005 = 3",
            "C2EC0006 = 2",
            "C2EC0007 = 2",
            "C2EC0008 = 3",
            "C2EC0009 = 1",
            "----------------",
            "total unique = 49",
            "```",
            "",
            "## Corrected evidence proposals (not applied)",
            "",
            "```text",
            "E2 = 9 records",
            "E3 = 30 records",
            "E4 = 0 records",
            "E5 = 10 records",
            "",
            "E4 -> E2 =  9",
            "E2 -> E3 = 30",
            "E2 -> E5 = 10",
            "```",
            "",
            "Human fields `manual_decision`, `manual_evidence_level`, and",
            "`manual_notes` are blank on all 9 rows.",
            "",
            "Effective-evidence precedence (projection only): completed C2EC*",
            "correction, else completed C2E0001–C2E0003, else machine evidence.",
            "Blank supplemental rows do not yet change effective evidence.",
            "",
            "Validator: supplemental resolved 0 / blank 9. Unresolved human",
            "decisions 9. Evidence-affinity flags 49. `ready_for_application = false`.",
            "",
            f"Supplemental SHA-256: `{post_sha}`",
            "Original evidence-review SHA-256:",
            "`2116183dc4db64f1939149d68e9416f36db8e9b747b4b1d7fbffca1c3c840718`",
            "",
        ]
    )
    note = "\n".join(note_lines)
    assert_no_sequence_leak(note, label="evidence consistency note")
    write_text_atomic(
        package_dir / "human_review" / "evidence_consistency_materialisation_note.md",
        note,
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Materialise the blank CHECKPOINT-2 supplemental evidence-consistency "
            "review without recording decisions"
        )
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args()
    repo_root = args.repo_root or SCRIPT_DIR.parents[1]
    result = materialise_live_evidence_consistency_package(repo_root=repo_root)
    print(
        json.dumps(
            {
                "n_rows": result["n_rows"],
                "n_unique_records": result["n_unique_records"],
                "decision_ids": result["decision_ids"],
                "hashes": result["hashes"],
                "validator": result["validator"],
                "human_fields_blank": result["human_fields_blank"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

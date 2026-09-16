#!/usr/bin/env python3
"""Materialise CHECKPOINT-2 affinity review splits. Does not record decisions.

Rewrites the ignored affinity-review CSV from one coarse group per parse
pattern into one scientifically coherent review row per subgroup. Human
affinity fields stay blank. Combined input, other review grains, and
machine proposal tables are not modified. CHECKPOINT-2 is not applied.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.checkpoint2_affinity import (  # noqa: E402
    AFFINITY_HUMAN_FIELDS,
    EXPECTED_LIVE_AFFINITY_DECISION_IDS,
    UNSPLIT_AFFINITY_DECISION_IDS,
    collect_affinity_park_record_ids,
    dry_run_affinity_semantics,
    materialise_affinity_review_splits,
)
from adapters.s4_scientific_common import (  # noqa: E402
    ScientificProposalError,
    write_json_atomic,
    write_text_atomic,
)
from checkpoint2_prepare_review import AFFINITY_REVIEW_COLUMNS  # noqa: E402
from checkpoint2_validate_review import validate_checkpoint2_package  # noqa: E402
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402

PRE_AFFINITY_SHA256 = "ec7da21e3d7fbe2ba17715b477bf3e6c000a92b04ea8ea303a8020f3e5e732c8"
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

PRISTINE_NAME = "checkpoint2_affinity_review_pre_split.csv"


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
        for field in AFFINITY_HUMAN_FIELDS:
            if (row.get(field) or "").strip():
                return False
    return True


def preserve_pristine(live_path: Path, pristine_path: Path, *, expected_sha: str) -> str:
    live_sha = sha256_file(live_path)
    if pristine_path.is_file():
        existing = sha256_file(pristine_path)
        if existing == expected_sha:
            return existing
        raise ScientificProposalError(
            f"existing pristine {pristine_path} has unexpected SHA-256 {existing}"
        )
    if live_sha != expected_sha:
        raise ScientificProposalError(
            "cannot create pristine copy: live affinity review is not the "
            f"19-row pre-split package ({live_sha})"
        )
    pristine_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(live_path, pristine_path)
    copied = sha256_file(pristine_path)
    if copied != expected_sha:
        raise ScientificProposalError("pristine copy SHA-256 drifted during write")
    return copied


def _readme_after_split(text: str) -> str:
    updated = text.replace("Affinity (19) remains blank.", "Affinity (31) remains blank.")
    if "- affinity: 19" in updated:
        updated = updated.replace("- affinity: 19", "- affinity: 31")
    note = (
        "Milestone 4E.3 materialised the 19-row affinity package into 31 "
        "scientifically coherent review rows. All affinity human fields remain "
        "blank. Evidence-affinity inconsistencies remain blocking. CHECKPOINT-2 "
        "has not been applied.\n"
    )
    if "Milestone 4E.3" not in updated:
        updated = updated.rstrip() + "\n\n" + note
    if "pristine/checkpoint2_affinity_review_pre_split.csv" not in updated:
        updated = updated.replace(
            "`pristine/checkpoint2_relationship_review.csv`",
            "`pristine/checkpoint2_relationship_review.csv`\n"
            "`pristine/checkpoint2_affinity_review_pre_split.csv`",
        )
    return updated if updated.endswith("\n") else updated + "\n"


def materialise_live_affinity_package(
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
    live_path = package_dir / "checkpoint2_affinity_review.csv"
    pristine_path = package_dir / "pristine" / PRISTINE_NAME
    hashes: dict[str, str] = {}
    for name, (relative, expected) in REQUIRED_HASHES.items():
        path = repo_root / relative
        got = sha256_file(path)
        hashes[name] = got
        if got != expected:
            raise ScientificProposalError(f"{name} SHA-256 mismatch: {got}")

    live_rows = _read_csv(live_path)
    live_sha = sha256_file(live_path)
    hashes["affinity_review_pre"] = live_sha
    if not _human_fields_blank(live_rows):
        raise ScientificProposalError("affinity human fields are not blank; refusing to split")

    if live_sha == PRE_AFFINITY_SHA256:
        if len(live_rows) != 19:
            raise ScientificProposalError(
                f"pre-split affinity review must have 19 rows, got {len(live_rows)}"
            )
    elif live_path.is_file() and pristine_path.is_file():
        if sha256_file(pristine_path) != PRE_AFFINITY_SHA256:
            raise ScientificProposalError("pristine pre-split affinity hash mismatch")
    else:
        raise ScientificProposalError(
            "affinity review is not the 19-row pre-split package and no valid pristine exists"
        )

    pristine_sha = preserve_pristine(
        live_path if live_sha == PRE_AFFINITY_SHA256 else pristine_path,
        pristine_path,
        expected_sha=PRE_AFFINITY_SHA256,
    )
    hashes["affinity_review_pristine"] = pristine_sha

    target_rows = _read_csv(package_dir / "checkpoint2_target_dictionary_review.csv")
    relationship_rows = _read_csv(package_dir / "checkpoint2_relationship_review.csv")
    evidence_rows = _read_csv(evidence_path)
    scientific_rows = _read_csv(
        repo_root / "data/interim/global_s4/relationship_scientific_proposals.csv"
    )
    parked = collect_affinity_park_record_ids(
        target_review_rows=target_rows,
        relationship_review_rows=relationship_rows,
        relationship_scientific_rows=scientific_rows,
    )
    materialised, proposal = materialise_affinity_review_splits(
        live_rows,
        evidence_rows,
        columns=AFFINITY_REVIEW_COLUMNS,
        parked_record_ids=parked,
    )
    ids = [row["decision_id"] for row in materialised]
    if ids != list(EXPECTED_LIVE_AFFINITY_DECISION_IDS):
        raise ScientificProposalError(
            f"live affinity decision IDs drifted: {ids}"
        )
    if set(proposal.unsplit_decision_ids) != set(UNSPLIT_AFFINITY_DECISION_IDS):
        raise ScientificProposalError(
            f"unsplit set drifted: {proposal.unsplit_decision_ids}"
        )
    if not _human_fields_blank(materialised):
        raise ScientificProposalError("materialisation populated affinity human fields")

    write_corpus_csv_atomic(live_path, materialised, columns=AFFINITY_REVIEW_COLUMNS)
    post_sha = sha256_file(live_path)
    hashes["affinity_review_post"] = post_sha
    rematerialised, _proposal = materialise_affinity_review_splits(
        _read_csv(live_path),
        evidence_rows,
        columns=AFFINITY_REVIEW_COLUMNS,
        parked_record_ids=parked,
    )
    write_corpus_csv_atomic(live_path, rematerialised, columns=AFFINITY_REVIEW_COLUMNS)
    idempotent_sha = sha256_file(live_path)
    if idempotent_sha != post_sha:
        raise ScientificProposalError("affinity materialisation is not idempotent")

    validator = validate_checkpoint2_package(package_dir)
    if validator["errors"]:
        raise ScientificProposalError(f"validator errors: {validator['errors']}")
    if validator["affinity_completion"].get("blank") != 31:
        raise ScientificProposalError(
            f"expected 31 blank affinity rows, got {validator['affinity_completion']}"
        )
    if validator["unresolved_decisions"] != 31:
        raise ScientificProposalError(
            f"expected unresolved=31, got {validator['unresolved_decisions']}"
        )
    if validator["ready_for_application"]:
        raise ScientificProposalError("package must not be ready for application")
    if validator["target_completion"].get("blank", 0) != 0:
        raise ScientificProposalError("target review is no longer complete")

    dry_run = dry_run_affinity_semantics(materialised, evidence_rows)
    readme_path = package_dir / "README.md"
    if readme_path.is_file():
        write_text_atomic(readme_path, _readme_after_split(readme_path.read_text(encoding="utf-8")))

    groups = [
        {
            "parent_decision_id": group.old_decision_id,
            "decision_id": group.proposed_decision_id,
            "subgroup": group.subgroup,
            "review_consequence": group.proposed_outcome,
            "transform_rule": group.transform_rule,
            "n_records": group.n_records,
            "record_ids": list(group.record_ids),
            "raw_examples": list(group.raw_examples),
            "park_provenance_record_ids": [
                item for item in group.record_ids if item in parked
            ],
        }
        for group in proposal.groups
    ]
    payload = {
        "milestone": "4E.3",
        "n_pre_split_rows": 19,
        "n_post_split_rows": 31,
        "human_affinity_fields_blank": True,
        "unsplit_decision_ids": list(proposal.unsplit_decision_ids),
        "split_decision_ids": list(proposal.split_decision_ids),
        "decision_ids": ids,
        "groups": groups,
        "hashes": hashes,
        "validator": {
            "ready_for_application": validator["ready_for_application"],
            "unresolved_decisions": validator["unresolved_decisions"],
            "affinity_completion": validator["affinity_completion"],
            "target_blank": validator["target_completion"]["blank"],
        },
        "outcome_class_review_row_counts": dry_run["outcome_class_review_row_counts"],
        "outcome_class_record_counts": dry_run["outcome_class_record_counts"],
        "n_evidence_affinity_inconsistency_records": dry_run[
            "n_evidence_affinity_inconsistency_records"
        ],
        "evidence_affinity_inconsistency_by_decision": dry_run[
            "evidence_affinity_inconsistency_by_decision"
        ],
        "application_blocked_by_evidence_affinity_inconsistency": dry_run[
            "application_blocked_by_evidence_affinity_inconsistency"
        ],
        "checkpoint2_applied": False,
        "combined_input_modified": False,
        "s5_run": False,
    }
    write_json_atomic(
        package_dir / "human_review" / "affinity_split_materialisation_manifest.json",
        payload,
    )
    note = "\n".join(
        [
            "# CHECKPOINT-2 affinity-review split materialisation",
            "",
            "Milestone 4E.3 rewrote the ignored affinity-review CSV from 19 coarse",
            "parse groups into 31 scientifically coherent review rows.",
            "No human affinity decisions were recorded. Combined input is unchanged.",
            "Target, relationship, and evidence review were not modified.",
            "CHECKPOINT-2 was not applied. S5 was not run.",
            "",
            "Pristine 19-row package:",
            f"`pristine/{PRISTINE_NAME}`",
            f"SHA-256: `{pristine_sha}`",
            "",
            f"Post-split SHA-256: `{post_sha}`",
            "",
            "Unresolved CHECKPOINT-2 decisions: 31. Affinity blank: 31.",
            "`ready_for_application = false`.",
            "",
        ]
    )
    write_text_atomic(
        package_dir / "human_review" / "affinity_split_materialisation_note.md",
        note,
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialise CHECKPOINT-2 affinity review splits without recording decisions"
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args()
    repo_root = args.repo_root or SCRIPT_DIR.parents[1]
    result = materialise_live_affinity_package(repo_root=repo_root)
    print(json.dumps(
        {
            "n_post_split_rows": result["n_post_split_rows"],
            "hashes": result["hashes"],
            "validator": result["validator"],
            "outcome_class_review_row_counts": result["outcome_class_review_row_counts"],
            "outcome_class_record_counts": result["outcome_class_record_counts"],
            "n_evidence_affinity_inconsistency_records": result[
                "n_evidence_affinity_inconsistency_records"
            ],
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

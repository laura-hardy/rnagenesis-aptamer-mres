#!/usr/bin/env python3
"""Record the 9 authorised CHECKPOINT-2 evidence-consistency decisions.

Fills ignored supplemental C2EC human fields only. Does not mutate the
frozen 3-row evidence review, affinity/target/relationship review,
machine proposal tables, combined input, or apply CHECKPOINT-2.
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

from adapters.checkpoint2_evidence import (  # noqa: E402
    EVIDENCE_CONSISTENCY_FILE,
    EVIDENCE_CONSISTENCY_REVIEW_COLUMNS,
    EXPECTED_DECISION_IDS,
    EXPECTED_DECISION_LEVEL_COUNTS,
    EXPECTED_GROUP_COUNTS,
    EXPECTED_GROUPS,
    EXPECTED_NEW_EVIDENCE_PARKS,
    EXPECTED_TARGET_PARKED_INDEPENDENT,
    EXPECTED_UNIQUE_RECORDS,
    apply_evidence_consistency_decisions,
    collect_consistency_flag_record_ids,
    compare_consistency_review_to_pristine,
    dry_run_supplemental_routing,
    expected_decision_levels,
    expected_record_ids,
    original_evidence_membership,
    summarise_member_outcomes,
    target_parked_member_ids,
    validate_group_spec,
)
from adapters.s4_scientific_common import (  # noqa: E402
    EVIDENCE_SCORE_BY_LEVEL,
    ScientificProposalError,
    assert_human_fields_blank,
    assert_no_sequence_leak,
    write_json_atomic,
    write_text_atomic,
)
from checkpoint2_validate_review import validate_checkpoint2_package  # noqa: E402
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402

PRE_RECORDING_SHA256 = (
    "0b16b918c6963068ee8334e5d72dc64f82cb0663c1bd091d61afe18a94fdb3d9"
)
PRISTINE_NAME = "checkpoint2_evidence_consistency_review_pre_recording.csv"
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

AUTHORISED_EVIDENCE_CONSISTENCY_DECISIONS: dict[str, dict[str, str]] = {
    "C2EC0001": {
        "manual_decision": "override_evidence",
        "manual_evidence_level": "E2",
        "manual_notes": (
            "Affinity review recovered genuine target-specific Kd values from "
            "the mojibake µM source text. Quantitative aptamer-target affinity "
            "supports E2."
        ),
    },
    "C2EC0002": {
        "manual_decision": "override_evidence",
        "manual_evidence_level": "E3",
        "manual_notes": (
            "The machine E2 arose from numeric/caption text that is not a "
            "row-specific Kd. A named aptamer-target binding assay remains "
            "locally preserved, supporting qualitative binding E3."
        ),
    },
    "C2EC0003": {
        "manual_decision": "override_evidence",
        "manual_evidence_level": "E3",
        "manual_notes": (
            "The parsed quantitative value belongs to a control, comparison, "
            "group statement, titration concentration, figure or another aptamer. "
            "After removing it, direct or functional qualitative aptamer-target "
            "interaction remains locally supported."
        ),
    },
    "C2EC0004": {
        "manual_decision": "override_evidence",
        "manual_evidence_level": "E5",
        "manual_notes": (
            "The quantitative material is not an aptamer-target affinity "
            "measurement. After its removal, no local aptamer-target binding "
            "or target-specific selection evidence remains; only "
            "publication/database association supports E5."
        ),
    },
    "C2EC0005": {
        "manual_decision": "override_evidence",
        "manual_evidence_level": "E5",
        "manual_notes": (
            'RDF "no binding" was incorrectly treated as a '
            "dissociation-constant value. It supports neither E2 nor E3. "
            "No stronger selection/publication provenance is locally "
            "preserved, so E5 applies. Do not encode no-binding as zero Kd."
        ),
    },
    "C2EC0006": {
        "manual_decision": "override_evidence",
        "manual_evidence_level": "E3",
        "manual_notes": (
            "The reported percentages are measured aptamer-target binding "
            "fractions. They are not affinity constants, so not E2, but they "
            "support qualitative binding E3."
        ),
    },
    "C2EC0007": {
        "manual_decision": "override_evidence",
        "manual_evidence_level": "E2",
        "manual_notes": (
            "Affinity review recovered explicit target-specific Kd values "
            "with uncertainty. These genuine quantitative affinities support E2."
        ),
    },
    "C2EC0008": {
        "manual_decision": "override_evidence",
        "manual_evidence_level": "E2",
        "manual_notes": (
            "Affinity review deterministically recovered explicit target-specific "
            "nM Kd values. These genuine quantitative affinities support E2."
        ),
    },
    "C2EC0009": {
        "manual_decision": "override_evidence",
        "manual_evidence_level": "E5",
        "manual_notes": (
            "TBD is a missing placeholder, not quantitative affinity. Remaining "
            "local provenance is patent/database target association only, "
            "supporting E5."
        ),
    },
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


def preserve_pristine(live_path: Path, pristine_path: Path, *, expected_sha: str) -> str:
    if pristine_path.is_file():
        existing = sha256_file(pristine_path)
        if existing == expected_sha:
            return existing
        raise ScientificProposalError(
            f"existing pristine {pristine_path} has unexpected SHA-256 {existing}"
        )
    live_sha = sha256_file(live_path)
    if live_sha != expected_sha:
        raise ScientificProposalError(
            "cannot create pre-recording pristine: live supplemental review is not "
            f"the blank 9-row package ({live_sha})"
        )
    pristine_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(live_path, pristine_path)
    copied = sha256_file(pristine_path)
    if copied != expected_sha:
        raise ScientificProposalError("pristine copy SHA-256 drifted during write")
    return copied


def _readme_after_recording(text: str) -> str:
    updated = text.replace(
        "All C2EC human fields remain blank. The frozen 3-row evidence review "
        "was not modified. Affinity review is unchanged. 49 evidence-affinity "
        "inconsistency records remain blocking. CHECKPOINT-2 has not been applied.",
        "Milestone 4F.3 recorded all 9 C2EC decisions as override_evidence. "
        "The frozen 3-row evidence review was not modified. Affinity review is "
        "unchanged. Evidence-affinity flags 49 → 0. "
        "`ready_for_application = true`. CHECKPOINT-2 has not been applied.",
    )
    note = (
        "Milestone 4F.3 recorded all 9 supplemental evidence-consistency "
        "decisions (9 override_evidence; 3 E2 / 3 E3 / 3 E5). Record outcomes: "
        "9 E2, 30 E3, 10 E5. Evidence-affinity flags 49 → 0. "
        "`ready_for_application = true`. CHECKPOINT-2 has not been applied.\n"
    )
    if "Milestone 4F.3" not in updated:
        updated = updated.rstrip() + "\n\n" + note
    return updated if updated.endswith("\n") else updated + "\n"


def _integrity_gate(
    *,
    live_rows: Sequence[Mapping[str, str]],
    evidence_rows: Sequence[Mapping[str, str]],
    affinity_rows: Sequence[Mapping[str, str]],
    original_evidence_rows: Sequence[Mapping[str, str]],
    live_sha: str,
) -> None:
    if live_sha != PRE_RECORDING_SHA256:
        raise ScientificProposalError(
            f"pre-recording supplemental SHA-256 mismatch: {live_sha}"
        )
    if len(live_rows) != 9:
        raise ScientificProposalError(f"expected 9 supplemental rows, got {len(live_rows)}")
    if [row.get("decision_id") for row in live_rows] != list(EXPECTED_DECISION_IDS):
        raise ScientificProposalError("live C2EC decision IDs drifted")
    for row in live_rows:
        assert_human_fields_blank(
            row, label=f"evidence consistency {row.get('decision_id')}"
        )
    members = expected_record_ids()
    if len(set(members)) != EXPECTED_UNIQUE_RECORDS:
        raise ScientificProposalError("frozen member inventory drifted")
    live_members: list[str] = []
    for row in live_rows:
        live_members.extend(
            item for item in (row.get("record_ids") or "").split("|") if item
        )
    if set(live_members) != set(members) or len(live_members) != EXPECTED_UNIQUE_RECORDS:
        raise ScientificProposalError("live membership is not the frozen 49 records")
    original_map = original_evidence_membership(original_evidence_rows, evidence_rows)
    overlap = sorted(set(members) & set(original_map))
    if overlap:
        raise ScientificProposalError(
            "C2EC records overlap closed C2E0001-C2E0003: " + "|".join(overlap)
        )
    flags = collect_consistency_flag_record_ids(
        evidence_rows,
        affinity_rows,
        supplemental_rows=live_rows,
        original_evidence_rows=original_evidence_rows,
    )
    if len(flags) != EXPECTED_UNIQUE_RECORDS:
        raise ScientificProposalError(
            f"pre-recording expected 49 evidence-affinity flags, got {len(flags)}"
        )
    if set(flags) != set(members):
        raise ScientificProposalError(
            "pre-recording flags do not match the frozen 49-record inventory"
        )


def record_live_evidence_consistency_decisions(*, repo_root: Path) -> dict[str, object]:
    repo_root = repo_root.resolve()
    package_dir = repo_root / "data/interim/global_s4/checkpoint2"
    live_path = package_dir / EVIDENCE_CONSISTENCY_FILE
    pristine_path = package_dir / "pristine" / PRISTINE_NAME
    validate_group_spec()
    hashes: dict[str, str] = {}
    for name, (relative, expected) in REQUIRED_HASHES.items():
        got = sha256_file(repo_root / relative)
        hashes[name] = got
        if got != expected:
            raise ScientificProposalError(f"{name} SHA-256 mismatch: {got}")

    live_rows = _read_csv(live_path)
    live_sha = sha256_file(live_path)
    hashes["evidence_consistency_review_pre"] = live_sha
    evidence_rows = _read_csv(
        repo_root / "data/interim/global_s4/evidence_affinity_proposals.csv"
    )
    affinity_rows = _read_csv(package_dir / "checkpoint2_affinity_review.csv")
    original_evidence_rows = _read_csv(package_dir / "checkpoint2_evidence_review.csv")
    _integrity_gate(
        live_rows=live_rows,
        evidence_rows=evidence_rows,
        affinity_rows=affinity_rows,
        original_evidence_rows=original_evidence_rows,
        live_sha=live_sha,
    )

    pristine_sha = preserve_pristine(
        live_path, pristine_path, expected_sha=PRE_RECORDING_SHA256
    )
    hashes["evidence_consistency_review_pristine"] = pristine_sha

    for decision_id, fields in AUTHORISED_EVIDENCE_CONSISTENCY_DECISIONS.items():
        assert_no_sequence_leak(
            fields.get("manual_notes", ""), label=f"{decision_id} notes"
        )
    recorded = apply_evidence_consistency_decisions(
        live_rows, AUTHORISED_EVIDENCE_CONSISTENCY_DECISIONS
    )
    write_corpus_csv_atomic(
        live_path, recorded, columns=EVIDENCE_CONSISTENCY_REVIEW_COLUMNS
    )
    post_sha = sha256_file(live_path)
    hashes["evidence_consistency_review_post"] = post_sha
    if post_sha == PRE_RECORDING_SHA256:
        raise ScientificProposalError(
            "supplemental review hash did not change after recording"
        )
    compare_consistency_review_to_pristine(recorded, _read_csv(pristine_path))

    for name, (relative, expected) in REQUIRED_HASHES.items():
        got = sha256_file(repo_root / relative)
        if got != expected:
            raise ScientificProposalError(
                f"{name} changed during evidence-consistency recording: {got}"
            )

    outcomes = summarise_member_outcomes(
        evidence_rows,
        recorded,
        original_evidence_rows,
    )
    flags = collect_consistency_flag_record_ids(
        evidence_rows,
        affinity_rows,
        supplemental_rows=recorded,
        original_evidence_rows=original_evidence_rows,
    )
    if flags:
        kinds: list[str] = []
        for record_id in flags:
            kinds.append(record_id)
        raise ScientificProposalError(
            "evidence-affinity flags remain after recording: " + "|".join(flags)
        )

    target_rows = _read_csv(package_dir / "checkpoint2_target_dictionary_review.csv")
    relationship_scientific = _read_csv(
        repo_root / "data/interim/global_s4/relationship_scientific_proposals.csv"
    )
    parked_members = target_parked_member_ids(target_rows, relationship_scientific)
    if set(parked_members) != set(EXPECTED_TARGET_PARKED_INDEPENDENT):
        raise ScientificProposalError(
            f"independent target parks drifted: {parked_members}"
        )
    routing_rows = _read_csv(repo_root / "data/interim/global_s4/routing_preview.csv")
    routing = dry_run_supplemental_routing(
        supplemental_rows=recorded,
        routing_rows=routing_rows,
        machine_evidence_rows=evidence_rows,
        original_evidence_rows=original_evidence_rows,
        target_parked_record_ids=parked_members,
    )

    validator = validate_checkpoint2_package(package_dir)
    if validator["errors"]:
        raise ScientificProposalError(f"validator errors: {validator['errors']}")
    completion = validator["evidence_consistency_completion"]
    if completion.get("blank") != 0 or completion.get("resolved") != 9:
        raise ScientificProposalError(
            f"expected supplemental 9 resolved / 0 blank, got {completion}"
        )
    if validator["unresolved_decisions"] != 0:
        raise ScientificProposalError(
            f"expected unresolved=0, got {validator['unresolved_decisions']}"
        )
    if validator["n_evidence_affinity_inconsistencies"] != 0:
        raise ScientificProposalError(
            "expected 0 evidence-affinity flags, got "
            f"{validator['n_evidence_affinity_inconsistencies']}"
        )
    if validator["application_blocked_by_evidence_affinity_inconsistency"]:
        raise ScientificProposalError(
            "validator still blocks application on evidence-affinity inconsistency"
        )
    if not validator["ready_for_application"]:
        blockers = {
            "unresolved_decisions": validator["unresolved_decisions"],
            "errors": validator["errors"],
            "n_evidence_affinity_inconsistencies": validator[
                "n_evidence_affinity_inconsistencies"
            ],
            "target_blank": validator["target_completion"].get("blank"),
            "affinity_blank": validator["affinity_completion"].get("blank"),
            "evidence_consistency": completion,
        }
        raise ScientificProposalError(
            "ready_for_application remains false: " + json.dumps(blockers)
        )
    by_file = validator["decision_counts_by_file"]
    if by_file.get("checkpoint2_evidence_review.csv", {}).get("BLANK", 0):
        raise ScientificProposalError("original evidence review is no longer complete")
    if by_file.get("checkpoint2_affinity_review.csv", {}).get("BLANK", 0):
        raise ScientificProposalError("affinity review is no longer complete")
    if validator["target_completion"].get("blank", 0) != 0:
        raise ScientificProposalError("target review is no longer complete")

    readme_path = package_dir / "README.md"
    if readme_path.is_file():
        write_text_atomic(readme_path, _readme_after_recording(readme_path.read_text(encoding="utf-8")))

    decision_rows = []
    for group in EXPECTED_GROUPS:
        level = expected_decision_levels()[group.decision_id]
        decision_rows.append(
            {
                "decision_id": group.decision_id,
                "n_records": len(group.record_ids),
                "manual_decision": "override_evidence",
                "manual_evidence_level": level,
                "evidence_score": EVIDENCE_SCORE_BY_LEVEL[level],
                "record_ids": list(group.record_ids),
            }
        )
    payload = {
        "milestone": "4F.3",
        "n_rows": 9,
        "n_unique_records": EXPECTED_UNIQUE_RECORDS,
        "decision_ids": list(EXPECTED_DECISION_IDS),
        "decision_counts": dict(EXPECTED_DECISION_LEVEL_COUNTS),
        "group_counts": dict(EXPECTED_GROUP_COUNTS),
        "decisions": decision_rows,
        "record_outcomes": outcomes,
        "n_evidence_affinity_inconsistencies_pre": 49,
        "n_evidence_affinity_inconsistencies_post": 0,
        "routing_dry_run": {
            "applied": False,
            "pass_e2_n": len(routing["pass_e2"]),
            "pass_e3_n": len(routing["pass_e3"]),
            "fail_e5_n": len(routing["fail_e5"]),
            "new_evidence_parks": routing["new_evidence_parks"],
            "independent_parks": routing["independent_parks"],
            "target_parked_independent": list(EXPECTED_TARGET_PARKED_INDEPENDENT),
        },
        "hashes": hashes,
        "validator": {
            "ready_for_application": validator["ready_for_application"],
            "unresolved_decisions": validator["unresolved_decisions"],
            "errors": validator["errors"],
            "evidence_consistency_completion": completion,
            "n_evidence_affinity_inconsistencies": validator[
                "n_evidence_affinity_inconsistencies"
            ],
            "target_blank": validator["target_completion"]["blank"],
            "affinity_blank": validator["affinity_completion"].get("blank"),
        },
        "scientific_boundary": {
            "checkpoint2_applied": False,
            "combined_input_modified": False,
            "proposal_tables_bulk_applied": False,
            "target_review_modified": False,
            "relationship_review_modified": False,
            "original_evidence_review_modified": False,
            "affinity_review_modified": False,
            "leakage_review_modified": False,
            "s5_run": False,
        },
    }
    write_json_atomic(
        package_dir / "human_review" / "evidence_consistency_recording_manifest.json",
        payload,
    )
    levels = expected_decision_levels()
    note_lines = [
        "# CHECKPOINT-2 supplemental evidence-consistency recording",
        "",
        "Sequence-safe human-review metadata for Milestone 4F.3.",
        "Decisions were recorded into the ignored supplemental C2EC CSV only.",
        "",
        "CHECKPOINT-2 has **not** been applied. Combined input is unchanged.",
        "Machine proposal tables were not mutated. The frozen 3-row evidence",
        "review (`C2E0001`–`C2E0003`) was not modified. Target, relationship,",
        "affinity, and leakage review files were not modified. S5 was not run.",
        "",
        "## Decision IDs (9)",
        "",
        ", ".join(EXPECTED_DECISION_IDS),
        "",
        "All nine are `override_evidence`. No E4 supplemental decision.",
        "",
        "## Decision counts",
        "",
        "```text",
        "override_evidence E2 = 3 decisions / 9 records",
        "override_evidence E3 = 3 decisions / 30 records",
        "override_evidence E5 = 3 decisions / 10 records",
        "E4                    = 0",
        "--------------------------------",
        "total                 = 9 decisions / 49 records",
        "```",
        "",
        "## Record-level evidence outcomes (49)",
        "",
        "```text",
        "E2 =  9",
        "E3 = 30",
        "E4 =  0",
        "E5 = 10",
        "",
        "E4 -> E2 =  9",
        "E2 -> E3 = 30",
        "E2 -> E5 = 10",
        "```",
        "",
        "Effective-evidence precedence (projection only): completed C2EC*",
        "correction, else completed C2E0001–C2E0003, else machine evidence.",
        "Only these 49 member records change effective evidence.",
        "",
        "## Evidence-affinity consistency",
        "",
        "Flags 49 → 0. Zero remaining false-positive E2 with reviewed",
        "`exclude_non_affinity`. Zero remaining exact quantitative reviewed",
        "affinity with effective evidence weaker than E2.",
        "",
        "## Routing dry-run (not applied)",
        "",
        "9 corrected E2 records pass the E4 inclusion threshold.",
        "30 corrected E3 records pass. 10 corrected E5 records fail unless",
        "already parked elsewhere. New evidence parks from otherwise",
        "protein-primary context:",
        "",
    ]
    for record_id in EXPECTED_NEW_EVIDENCE_PARKS:
        note_lines.append(f"- `{record_id}`")
    note_lines.extend(
        [
            "",
            "Existing independent parks remain authoritative:",
            "AptaBase peptides in C2EC0001 remain `park_non_protein`;",
            "`aptadb:383`–`aptadb:386` remain target-parked (`TD0259`);",
            "AptamerBase C2EC0005 remains target-type held;",
            "RiboAptamer C2EC0006 remains cell/`park_non_protein`;",
            "UTexas C2EC0009 remains target-unresolved.",
            "",
            "## Review completion",
            "",
            "```text",
            "target                 = 205 / 205",
            "relationship           = 107 / 107",
            "evidence               =   3 / 3",
            "affinity               =  31 / 31",
            "evidence consistency   =   9 / 9",
            "",
            "unresolved human decisions = 0",
            "evidence-affinity flags     = 0",
            "errors                      = none",
            "ready_for_application      = true",
            "```",
            "",
            "CHECKPOINT-2 was not applied in this milestone.",
            "",
            f"Pre-recording SHA-256: `{PRE_RECORDING_SHA256}`",
            f"Pristine: `pristine/{PRISTINE_NAME}`",
            f"Post-recording SHA-256: `{post_sha}`",
            "",
            "Original evidence-review SHA-256:",
            "`2116183dc4db64f1939149d68e9416f36db8e9b747b4b1d7fbffca1c3c840718`",
            "",
        ]
    )
    for group in EXPECTED_GROUPS:
        level = levels[group.decision_id]
        score = EVIDENCE_SCORE_BY_LEVEL[level]
        note_lines.extend(
            [
                f"## {group.decision_id} — `override_evidence` {level} (score {score})",
                "",
                f"{len(group.record_ids)} records. Affinity `{group.affinity_decision_id}`.",
                AUTHORISED_EVIDENCE_CONSISTENCY_DECISIONS[group.decision_id]["manual_notes"],
                "",
            ]
        )
    note = "\n".join(note_lines)
    assert_no_sequence_leak(note, label="evidence consistency recording note")
    write_text_atomic(
        package_dir / "human_review" / "evidence_consistency_recording_note.md",
        note,
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Record the 9 authorised CHECKPOINT-2 supplemental "
            "evidence-consistency decisions without applying CHECKPOINT-2"
        )
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args()
    repo_root = args.repo_root or SCRIPT_DIR.parents[1]
    result = record_live_evidence_consistency_decisions(repo_root=repo_root)
    print(
        json.dumps(
            {
                "n_rows": result["n_rows"],
                "n_unique_records": result["n_unique_records"],
                "decision_counts": result["decision_counts"],
                "record_outcomes": result["record_outcomes"],
                "n_evidence_affinity_inconsistencies_pre": result[
                    "n_evidence_affinity_inconsistencies_pre"
                ],
                "n_evidence_affinity_inconsistencies_post": result[
                    "n_evidence_affinity_inconsistencies_post"
                ],
                "routing_dry_run": result["routing_dry_run"],
                "hashes": result["hashes"],
                "validator": result["validator"],
                "scientific_boundary": result["scientific_boundary"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

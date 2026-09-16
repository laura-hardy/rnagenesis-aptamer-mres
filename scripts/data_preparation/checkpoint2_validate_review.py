"""Fail-closed CHECKPOINT-2 review validator."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from adapters.checkpoint2_affinity import (
    validate_affinity_review_row,
)
from adapters.checkpoint2_dictionary import (
    INACTIVE_REASON_PARKED_ONLY,
    INACTIVE_REASON_SUPERSEDED,
    project_effective_target_relationships,
    validate_inactive_target_decision,
)
from adapters.checkpoint2_evidence import (
    EVIDENCE_CONSISTENCY_FILE,
    collect_consistency_flag_record_ids,
    summarise_evidence_consistency,
)
from adapters.s4_scientific_common import (
    AFFINITY_DECISION_VOCAB,
    AFFINITY_EXTRA_HUMAN_FIELDS,
    CONFIRM_AFFINITY_SCALAR,
    EVIDENCE_DECISION_VOCAB,
    EXCLUDE_NON_AFFINITY,
    HUMAN_FIELDS,
    INACTIVE_TARGET_DECISION,
    LEAKAGE_DECISION_VOCAB,
    MANUAL_DECISION_VOCAB,
    RELATIONSHIP_DECISION_VOCAB,
    RETAIN_AFFINITY_RAW,
    TARGET_DECISION_VOCAB,
    TARGET_FAMILY_VOCAB,
    TARGET_TYPE_VOCAB,
    EVIDENCE_LEVELS,
    EVIDENCE_SCORE_BY_LEVEL,
    EVIDENCE_TYPE_BY_LEVEL,
)

REQUIRED_FILES = (
    "checkpoint2_target_dictionary_review.csv",
    "checkpoint2_relationship_review.csv",
    "checkpoint2_evidence_review.csv",
    "checkpoint2_affinity_review.csv",
    "checkpoint2_leakage_review.csv",
)

FILE_DECISION_VOCAB = {
    "checkpoint2_target_dictionary_review.csv": TARGET_DECISION_VOCAB,
    "checkpoint2_relationship_review.csv": RELATIONSHIP_DECISION_VOCAB,
    "checkpoint2_evidence_review.csv": EVIDENCE_DECISION_VOCAB,
    "checkpoint2_affinity_review.csv": AFFINITY_DECISION_VOCAB,
    "checkpoint2_leakage_review.csv": LEAKAGE_DECISION_VOCAB,
    EVIDENCE_CONSISTENCY_FILE: EVIDENCE_DECISION_VOCAB,
}

OVERRIDE_REQUIRED = {
    "override": ("manual_target_name", "manual_target_type"),
    "override_evidence": ("manual_evidence_level",),
    "retain_despite_false_positive_leakage": ("manual_notes",),
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _blank(value: str | None) -> bool:
    return not (value or "").strip()


def _sibling_csv(package_dir: Path, name: str) -> list[dict[str, str]] | None:
    path = package_dir.parent / name
    if path.is_file():
        return _read_csv(path)
    return None


def validate_checkpoint2_package(
    package_dir: Path,
    *,
    machine_relationship_rows: Sequence[Mapping[str, str]] | None = None,
    dictionary_rows: Sequence[Mapping[str, str]] | None = None,
    evidence_affinity_rows: Sequence[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Validate a CHECKPOINT-2 package.

    A freshly generated blank package must report unresolved decisions and
    `ready_for_application = false`.

    ``exclude_no_active_relationship`` is a completed target-review decision
    and counts toward resolution, but it is valid only when the reviewed
    relationship projection shows zero effective resolved relationships for
    that dictionary identity. It does not make the package ready while
    ordinary target, evidence, or affinity rows remain blank.

    Affinity rows are completed by an affinity-specific outcome even when
    the normalised scalar is blank. Evidence-affinity inconsistencies block
    application without mutating the closed evidence review. A supplemental
    evidence-consistency package, once present, is part of completion: blank
    C2EC* rows keep the package unready even if every original grain is filled.
    """
    package_dir = Path(package_dir)
    errors: list[str] = []
    warnings: list[str] = []
    unresolved = 0
    n_decisions = 0
    populated_human = 0
    by_file: dict[str, dict[str, int]] = {}
    evidence_review_rows: list[dict[str, str]] = []
    evidence_consistency_rows: list[dict[str, str]] | None = None
    target_counts = {
        "approve_proposal": 0,
        "override": 0,
        "park_unresolved": 0,
        INACTIVE_TARGET_DECISION: 0,
        "other_resolved": 0,
        "blank": 0,
        INACTIVE_REASON_SUPERSEDED: 0,
        INACTIVE_REASON_PARKED_ONLY: 0,
    }
    affinity_counts = {
        CONFIRM_AFFINITY_SCALAR: 0,
        RETAIN_AFFINITY_RAW: 0,
        EXCLUDE_NON_AFFINITY: 0,
        "park_unresolved": 0,
        "blank": 0,
        "other_resolved": 0,
    }
    inactive_target_rows: list[tuple[str, int, dict[str, str]]] = []
    target_rows: list[dict[str, str]] = []
    relationship_rows: list[dict[str, str]] = []
    affinity_rows: list[dict[str, str]] = []
    affinity_has_decision = False
    review_files = list(REQUIRED_FILES)
    if (package_dir / EVIDENCE_CONSISTENCY_FILE).is_file():
        review_files.append(EVIDENCE_CONSISTENCY_FILE)

    for name in review_files:
        path = package_dir / name
        if not path.is_file():
            errors.append(f"missing {name}")
            continue
        rows = _read_csv(path)
        n_decisions += len(rows)
        file_counts: dict[str, int] = {}
        if name == "checkpoint2_target_dictionary_review.csv":
            target_rows = rows
        elif name == "checkpoint2_relationship_review.csv":
            relationship_rows = rows
        elif name == "checkpoint2_affinity_review.csv":
            affinity_rows = rows
        elif name == "checkpoint2_evidence_review.csv":
            evidence_review_rows = rows
        elif name == EVIDENCE_CONSISTENCY_FILE:
            evidence_consistency_rows = rows
        grain_vocab = FILE_DECISION_VOCAB.get(name, MANUAL_DECISION_VOCAB)
        extra_human = AFFINITY_EXTRA_HUMAN_FIELDS if name == "checkpoint2_affinity_review.csv" else ()
        for index, row in enumerate(rows, start=2):
            decision = (row.get("manual_decision") or "").strip()
            file_counts[decision or "BLANK"] = file_counts.get(decision or "BLANK", 0) + 1
            human_values = [row.get(field, "") for field in HUMAN_FIELDS]
            human_values.extend(row.get(field, "") for field in extra_human)
            if any((value or "").strip() for value in human_values):
                populated_human += 1
            if not decision:
                unresolved += 1
                if name == "checkpoint2_target_dictionary_review.csv":
                    target_counts["blank"] += 1
                if name == "checkpoint2_affinity_review.csv":
                    affinity_counts["blank"] += 1
                continue
            if decision not in MANUAL_DECISION_VOCAB:
                errors.append(f"{name}:{index} invalid manual_decision")
            elif decision not in grain_vocab:
                errors.append(f"{name}:{index} {decision} is not valid on this review grain")
            if name == "checkpoint2_affinity_review.csv":
                affinity_has_decision = True
                if decision in affinity_counts:
                    affinity_counts[decision] += 1
                else:
                    affinity_counts["other_resolved"] += 1
                errors.extend(
                    validate_affinity_review_row(row, line=f"{name}:{index}")
                )
            if decision == INACTIVE_TARGET_DECISION:
                if name != "checkpoint2_target_dictionary_review.csv":
                    errors.append(
                        f"{name}:{index} {INACTIVE_TARGET_DECISION} is a target-dictionary action"
                    )
                else:
                    target_counts[INACTIVE_TARGET_DECISION] += 1
                    inactive_target_rows.append((name, index, row))
            elif name == "checkpoint2_target_dictionary_review.csv":
                if decision in target_counts:
                    target_counts[decision] += 1
                else:
                    target_counts["other_resolved"] += 1
            if name != "checkpoint2_affinity_review.csv":
                required_fields = OVERRIDE_REQUIRED.get(decision, ())
                for field in required_fields:
                    if _blank(row.get(field)):
                        errors.append(f"{name}:{index} {decision} missing {field}")
            target_type = (row.get("manual_target_type") or "").strip()
            if target_type and target_type not in TARGET_TYPE_VOCAB:
                errors.append(f"{name}:{index} invalid manual_target_type")
            family = (row.get("manual_target_family") or "").strip()
            if family and family not in TARGET_FAMILY_VOCAB:
                errors.append(f"{name}:{index} invalid manual_target_family")
            evidence = (row.get("manual_evidence_level") or "").strip()
            if evidence and evidence not in EVIDENCE_LEVELS:
                errors.append(f"{name}:{index} invalid manual_evidence_level")
            uniprot = (row.get("manual_uniprot") or "").strip()
            if uniprot and target_type and target_type not in {"protein", "peptide"}:
                if "justified" not in (row.get("manual_notes") or "").casefold():
                    errors.append(
                        f"{name}:{index} non-protein UniProt without explicit justification"
                    )
            if evidence:
                if (
                    row.get("manual_notes")
                    and "score" in row
                    and row.get("manual_evidence_score")
                    and row.get("manual_evidence_score") != str(EVIDENCE_SCORE_BY_LEVEL[evidence])
                ):
                    errors.append(f"{name}:{index} evidence score/type mismatch")
            if name != "checkpoint2_affinity_review.csv":
                affinity_unit = (row.get("manual_affinity_unit") or "").strip()
                affinity_value = (row.get("manual_affinity_value") or "").strip()
                if affinity_value and not affinity_unit:
                    errors.append(f"{name}:{index} affinity value without unit")
            if decision == "confirm_multi_target_expansion":
                action = (row.get("manual_relationship_action") or "").strip()
                if action not in {"", "confirm_multi_target_expansion"}:
                    errors.append(f"{name}:{index} inconsistent multi-target action")
        by_file[name] = file_counts

    if inactive_target_rows:
        machine_rows = machine_relationship_rows
        dict_rows = dictionary_rows
        if machine_rows is None:
            machine_rows = _sibling_csv(package_dir, "relationship_scientific_proposals.csv")
        if dict_rows is None:
            dict_rows = _sibling_csv(package_dir, "target_dictionary_scientific_proposed.csv")
        if machine_rows is None or dict_rows is None:
            errors.append(
                f"{INACTIVE_TARGET_DECISION} requires relationship and dictionary "
                "proposal tables to prove zero active relationships"
            )
        else:
            projection, _resolutions = project_effective_target_relationships(
                machine_rows,
                relationship_rows,
                dict_rows,
                target_rows,
            )
            for name, index, row in inactive_target_rows:
                try:
                    reason = validate_inactive_target_decision(row, projection)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{name}:{index} {exc}")
                    continue
                if reason in target_counts:
                    target_counts[reason] += 1

    inconsistency_records: list[str] = []
    if affinity_has_decision:
        evidence_rows = evidence_affinity_rows
        if evidence_rows is None:
            evidence_rows = _sibling_csv(package_dir, "evidence_affinity_proposals.csv")
        if evidence_rows is None:
            warnings.append(
                "affinity decisions present but evidence_affinity_proposals.csv "
                "was not available for consistency checking"
            )
        else:
            inconsistency_records = list(
                collect_consistency_flag_record_ids(
                    evidence_rows,
                    affinity_rows,
                    supplemental_rows=evidence_consistency_rows or (),
                    original_evidence_rows=evidence_review_rows,
                )
            )

    blocked = bool(inconsistency_records)
    ready = (
        unresolved == 0
        and not errors
        and n_decisions > 0
        and not blocked
    )
    result = {
        "ready_for_application": ready,
        "unresolved_decisions": unresolved,
        "n_decisions": n_decisions,
        "populated_human_fields": populated_human,
        "errors": errors,
        "warnings": warnings,
        "fail_closed_blank_package": unresolved > 0 and populated_human == 0,
        "decision_counts_by_file": by_file,
        "target_completion": target_counts,
        "affinity_completion": affinity_counts,
        "evidence_affinity_inconsistency_records": inconsistency_records,
        "n_evidence_affinity_inconsistencies": len(inconsistency_records),
        "application_blocked_by_evidence_affinity_inconsistency": blocked,
        "evidence_consistency_completion": summarise_evidence_consistency(
            evidence_consistency_rows
        ),
        "completion_semantics": {
            "approve_proposal": "resolved; enters effective target dictionary",
            "override": "resolved; enters effective target dictionary",
            INACTIVE_TARGET_DECISION: (
                "resolved; excluded from effective target dictionary; "
                "not a scientific rejection"
            ),
            "park_unresolved": "resolved scientific deferral; not an effective dictionary entry",
            "human_derived_relationship_override": (
                "new dictionary identity from a relationship override; "
                "still requires a target-level decision before it is resolved"
            ),
            CONFIRM_AFFINITY_SCALAR: (
                "resolved affinity; exact normalised scalar only if safe per record"
            ),
            RETAIN_AFFINITY_RAW: (
                "resolved affinity; raw/qualifier retained; canonical scalar blank"
            ),
            EXCLUDE_NON_AFFINITY: (
                "resolved non-affinity; canonical affinity blank; cannot trigger E2"
            ),
        },
    }
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate a CHECKPOINT-2 review package")
    parser.add_argument("--package-dir", type=Path, required=True)
    args = parser.parse_args()
    result = validate_checkpoint2_package(args.package_dir)
    print(json.dumps(result, indent=2))
    return 0 if result["errors"] == [] else 1


if __name__ == "__main__":
    raise SystemExit(main())

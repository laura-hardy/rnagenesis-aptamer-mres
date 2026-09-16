#!/usr/bin/env python3
"""Record the 31 authorised CHECKPOINT-2 affinity decisions.

Fills ignored affinity-review human fields only. Does not mutate
target/relationship/evidence review, machine proposal tables, combined
input, or apply CHECKPOINT-2.
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
    inconsistency_kind,
    project_affinity_reviews,
    summarise_affinity_projection,
    validate_affinity_review_row,
)
from adapters.s4_scientific_common import (  # noqa: E402
    CONFIRM_AFFINITY_SCALAR,
    EXCLUDE_NON_AFFINITY,
    RETAIN_AFFINITY_RAW,
    ScientificProposalError,
    assert_no_sequence_leak,
    fill_row,
    write_json_atomic,
    write_text_atomic,
)
from checkpoint2_prepare_review import AFFINITY_REVIEW_COLUMNS  # noqa: E402
from checkpoint2_validate_review import validate_checkpoint2_package  # noqa: E402
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402

PRE_RECORDING_AFFINITY_SHA256 = (
    "518f8f262b0133cc5938c0b3ce0166ba200102abd9b59790e6e9122fb39cec25"
)
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
    "leakage_review": (
        "data/interim/global_s4/checkpoint2/checkpoint2_leakage_review.csv",
        "9adb73232c363ed440dc776c3c8669784e7232ec8e67f7b55bcf4c0627bfacf7",
    ),
}
PRISTINE_NAME = "checkpoint2_affinity_review_pre_recording.csv"

# Live reason tokens. Semantic milestone labels are recorded in notes.
AUTHORISED_AFFINITY_DECISIONS: dict[str, dict[str, str]] = {
    "C2A0001": {
        "manual_decision": EXCLUDE_NON_AFFINITY,
        "manual_affinity_non_affinity_reason": "missing_value",
        "manual_notes": (
            "N/A denotes unavailable affinity, not a numeric Kd and not zero. "
            "Semantic reason: missing_or_not_available."
        ),
    },
    "C2A0002": {
        "manual_decision": CONFIRM_AFFINITY_SCALAR,
        "manual_affinity_type": "Kd",
        "manual_affinity_transform_rule": "mojibake_micro_M",
        "manual_notes": (
            "AptaBase source text preserves the micro-unit as mojibake "
            "micro-M. This deterministically represents micromolar. Apply each "
            "record's own numeric value times 10^-6 M; do not use one "
            "group-level scalar."
        ),
    },
    "C2A0003": {
        "manual_decision": EXCLUDE_NON_AFFINITY,
        "manual_affinity_non_affinity_reason": "assay_caption",
        "manual_notes": (
            "Assay-caption text with no row-specific quantitative Kd. "
            "Semantic reason: assay_caption_not_affinity."
        ),
    },
    "C2A0004A": {
        "manual_decision": EXCLUDE_NON_AFFINITY,
        "manual_affinity_non_affinity_reason": "assay_caption",
        "manual_notes": (
            "Figure/assay/application captions, biological effects, and "
            "EC50/Km/MTT/migration prose are not row-specific aptamer "
            "binding affinity. Semantic reason: assay_caption_not_affinity."
        ),
    },
    "C2A0004B": {
        "manual_decision": EXCLUDE_NON_AFFINITY,
        "manual_affinity_non_affinity_reason": "mentioned_foreign_kd",
        "manual_notes": (
            "Cited Kd belongs to a control, literature comparison, other aptamer, "
            "group statement, or figure, not this record's aptamer-target "
            "affinity. Semantic reason: foreign_or_non_row_affinity."
        ),
    },
    "C2A0005": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_affinity_qualifier": "<",
        "manual_affinity_transform_rule": "parse_inequality_bound",
        "manual_notes": (
            "Reported Kd values are upper-bound inequalities. Preserve each "
            "operator and normalized bound in provenance; do not treat the "
            "bound as an exact Kd."
        ),
    },
    "C2A0006": {
        "manual_decision": EXCLUDE_NON_AFFINITY,
        "manual_affinity_non_affinity_reason": "lod",
        "manual_notes": (
            "LOD/date-token 5-Jan is not a Kd or range. Semantic reason: "
            "lod_not_binding_affinity."
        ),
    },
    "C2A0007": {
        "manual_decision": EXCLUDE_NON_AFFINITY,
        "manual_affinity_non_affinity_reason": "lod",
        "manual_notes": (
            "LOD concentration is not canonical binding affinity. Semantic "
            "reason: lod_not_binding_affinity."
        ),
    },
    "C2A0008": {
        "manual_decision": EXCLUDE_NON_AFFINITY,
        "manual_affinity_non_affinity_reason": "lod",
        "manual_notes": (
            "LOD 1mM is not canonical binding affinity. Semantic reason: "
            "lod_not_binding_affinity."
        ),
    },
    "C2A0009A": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_affinity_range_status": "list",
        "manual_notes": (
            "Multiple clone-specific Kd values (npBACE 360 and 280 nM). "
            "Retain the list; do not collapse to one scalar."
        ),
    },
    "C2A0009B": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_affinity_range_status": "range",
        "manual_notes": (
            "True reported Kd ranges. Retain lower/upper bounds; do not "
            "collapse to a midpoint."
        ),
    },
    "C2A0010": {
        "manual_decision": EXCLUDE_NON_AFFINITY,
        "manual_affinity_non_affinity_reason": "no_binding",
        "manual_notes": (
            "Source reports no binding. Do not encode as zero Kd. Semantic "
            "reason: no_binding_not_affinity."
        ),
    },
    "C2A0011": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_notes": (
            "RDF source contains numeric dissociation-constant literals without "
            "an explicit unit predicate. Magnitude patterns are insufficient "
            "to assert a source unit. Do not infer nM or M."
        ),
    },
    "C2A0012": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_affinity_range_status": "list",
        "manual_notes": (
            "Multiple RDF Kd values retained raw. 0.0 placeholders must not "
            "be interpreted as exact zero-affinity measurements without source "
            "support."
        ),
    },
    "C2A0013A": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_affinity_qualifier": ">",
        "manual_affinity_transform_rule": "parse_inequality_bound",
        "manual_notes": (
            "Reported Kd values are lower-bound inequalities. Preserve each "
            "record's > bound; do not store the bound as an exact affinity."
        ),
    },
    "C2A0013B": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_affinity_range_status": "list",
        "manual_notes": (
            "Pipe-delimited multiple Kd/error values retained raw. No exact "
            "scalar."
        ),
    },
    "C2A0013C": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_notes": (
            "Central-value-plus-error forms retained raw. Do not flatten "
            "uncertainty to an exact scalar at this reviewed grain."
        ),
    },
    "C2A0014A": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_affinity_qualifier": "approximate",
        "manual_notes": (
            "Approximate Kd (~) retained raw. No exact canonical scalar."
        ),
    },
    "C2A0014B": {
        "manual_decision": EXCLUDE_NON_AFFINITY,
        "manual_affinity_non_affinity_reason": "binding_percentage",
        "manual_notes": (
            "Binding percentage is not a Kd. Semantic reason: "
            "binding_percentage_not_affinity."
        ),
    },
    "C2A0014C": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_affinity_range_status": "range",
        "manual_notes": (
            "100~500 nM is a true range in this source value, not an "
            "approximation prefix. No midpoint."
        ),
    },
    "C2A0015": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_notes": (
            "Inequality operators differ per record (<= versus >>). Qualifiers "
            "are derived per record from raw text; no single group-level "
            "qualifier. No exact scalar."
        ),
    },
    "C2A0016A": {
        "manual_decision": CONFIRM_AFFINITY_SCALAR,
        "manual_affinity_type": "Kd",
        "manual_affinity_transform_rule": "central_value_uncertainty",
        "manual_notes": (
            "Use the explicitly reported central nM value as the quantitative "
            "Kd while preserving the +/- uncertainty in reviewed provenance."
        ),
    },
    "C2A0016B": {
        "manual_decision": CONFIRM_AFFINITY_SCALAR,
        "manual_affinity_type": "Kd",
        "manual_affinity_transform_rule": "glued_unit",
        "manual_notes": (
            "The numeric value and nM unit are unambiguous despite missing "
            "whitespace. Normalize each record independently."
        ),
    },
    "C2A0016C": {
        "manual_decision": EXCLUDE_NON_AFFINITY,
        "manual_affinity_non_affinity_reason": "missing_value",
        "manual_notes": (
            "Kd: NA denotes unavailable affinity, not a numeric Kd. Semantic "
            "reason: missing_or_not_available."
        ),
    },
    "C2A0016D": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_notes": (
            "The source contains valid quantitative affinity information but "
            "more than one value/type/condition per record, including Kd1/Kd2, "
            "slash lists, ligand- or species-specific pairs, and mixed Ki/Kd "
            "or Kd/IC50. Preserve per-record raw affinity semantics; do not "
            "collapse to one Kd scalar. riboaptamer:481 remains "
            "relationship-parked."
        ),
    },
    "C2A0016E": {
        "manual_decision": EXCLUDE_NON_AFFINITY,
        "manual_affinity_non_affinity_reason": "rate",
        "manual_notes": (
            "Values in 1/s are rates, not dissociation constants. Semantic "
            "reason: rate_not_binding_affinity."
        ),
    },
    "C2A0017": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_notes": (
            "Kd: 325 has no recoverable unit. Do not infer nM from "
            "neighbouring records."
        ),
    },
    "C2A0018A": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_notes": (
            "Multiple or condition-specific Kd values retained raw. No scalar."
        ),
    },
    "C2A0018B": {
        "manual_decision": CONFIRM_AFFINITY_SCALAR,
        "manual_affinity_type": "Kd",
        "manual_affinity_transform_rule": "scientific_notation",
        "manual_notes": (
            "2 x 10^-5 M is one exact scientific-notation scalar, not a "
            "numeric range. Normalize to 2e-5 M per record."
        ),
    },
    "C2A0018C": {
        "manual_decision": RETAIN_AFFINITY_RAW,
        "manual_affinity_type": "Kd",
        "manual_affinity_range_status": "range",
        "manual_notes": (
            "Genuine Kd ranges retained with lower/upper semantics. No midpoint."
        ),
    },
    "C2A0019": {
        "manual_decision": EXCLUDE_NON_AFFINITY,
        "manual_affinity_non_affinity_reason": "placeholder",
        "manual_notes": (
            "TBD is nonempty placeholder text, not quantitative affinity. "
            "Semantic reason: missing_or_not_available. Live reason token: "
            "placeholder."
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


def _human_blank(rows: Sequence[Mapping[str, str]]) -> bool:
    for row in rows:
        for field in AFFINITY_HUMAN_FIELDS:
            if (row.get(field) or "").strip():
                return False
    return True


def authorised_affinity_decision_counts() -> dict[str, int]:
    counts = {
        CONFIRM_AFFINITY_SCALAR: 0,
        RETAIN_AFFINITY_RAW: 0,
        EXCLUDE_NON_AFFINITY: 0,
        "park_unresolved": 0,
    }
    for fields in AUTHORISED_AFFINITY_DECISIONS.values():
        decision = fields["manual_decision"]
        counts[decision] = counts.get(decision, 0) + 1
    return counts


def apply_authorised_affinity_decisions(
    rows: Sequence[Mapping[str, str]],
    *,
    columns: Sequence[str] = AFFINITY_REVIEW_COLUMNS,
) -> list[dict[str, str]]:
    """Fill authorised human fields. Machine columns are preserved."""
    if len(rows) != len(AUTHORISED_AFFINITY_DECISIONS):
        raise ScientificProposalError(
            f"expected {len(AUTHORISED_AFFINITY_DECISIONS)} affinity rows, got {len(rows)}"
        )
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        decision_id = (row.get("decision_id") or "").strip()
        fields = AUTHORISED_AFFINITY_DECISIONS.get(decision_id)
        if fields is None:
            raise ScientificProposalError(f"unauthorised affinity decision id {decision_id}")
        if decision_id in seen:
            raise ScientificProposalError(f"duplicate affinity decision id {decision_id}")
        seen.add(decision_id)
        updated = dict(row)
        for field in AFFINITY_HUMAN_FIELDS:
            updated[field] = fields.get(field, "")
        filled = fill_row(columns, updated)
        errors = validate_affinity_review_row(filled, line=decision_id)
        if errors:
            raise ScientificProposalError("; ".join(errors))
        assert_no_sequence_leak(
            filled.get("manual_notes", ""), label=f"{decision_id} notes"
        )
        if filled["manual_decision"] == "park_unresolved":
            raise ScientificProposalError(f"{decision_id} must not be parked")
        out.append(filled)
    missing = sorted(set(AUTHORISED_AFFINITY_DECISIONS) - seen)
    if missing:
        raise ScientificProposalError(f"missing authorised affinity ids: {missing}")
    counts = authorised_affinity_decision_counts()
    if counts != {
        CONFIRM_AFFINITY_SCALAR: 4,
        RETAIN_AFFINITY_RAW: 15,
        EXCLUDE_NON_AFFINITY: 12,
        "park_unresolved": 0,
    }:
        raise ScientificProposalError(f"authorised decision counts drifted: {counts}")
    return out


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
            "cannot create pre-recording pristine: live affinity review is not "
            f"the blank 31-row package ({live_sha})"
        )
    pristine_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(live_path, pristine_path)
    copied = sha256_file(pristine_path)
    if copied != expected_sha:
        raise ScientificProposalError("pristine copy SHA-256 drifted during write")
    return copied


def _readme_after_recording(text: str) -> str:
    updated = text.replace("Affinity (31) remains blank.", "Affinity (31/31) is recorded.")
    note = (
        "Milestone 4E.4 recorded all 31 affinity decisions "
        "(4 confirm_affinity_scalar, 15 retain_affinity_raw, "
        "12 exclude_non_affinity, 0 park). Human affinity review is complete. "
        "49 evidence-affinity inconsistency records remain blocking. "
        "CHECKPOINT-2 has not been applied.\n"
    )
    if "Milestone 4E.4" not in updated:
        updated = updated.rstrip() + "\n\n" + note
    return updated if updated.endswith("\n") else updated + "\n"


def record_live_affinity_decisions(*, repo_root: Path) -> dict[str, object]:
    repo_root = repo_root.resolve()
    package_dir = repo_root / "data/interim/global_s4/checkpoint2"
    live_path = package_dir / "checkpoint2_affinity_review.csv"
    pristine_path = package_dir / "pristine" / PRISTINE_NAME
    hashes: dict[str, str] = {}
    for name, (relative, expected) in REQUIRED_HASHES.items():
        got = sha256_file(repo_root / relative)
        hashes[name] = got
        if got != expected:
            raise ScientificProposalError(f"{name} SHA-256 mismatch: {got}")

    live_rows = _read_csv(live_path)
    live_sha = sha256_file(live_path)
    hashes["affinity_review_pre"] = live_sha
    if live_sha != PRE_RECORDING_AFFINITY_SHA256:
        raise ScientificProposalError(
            f"pre-recording affinity SHA-256 mismatch: {live_sha}"
        )
    if len(live_rows) != 31:
        raise ScientificProposalError(f"expected 31 affinity rows, got {len(live_rows)}")
    if not _human_blank(live_rows):
        raise ScientificProposalError("affinity human fields are not blank")

    pristine_sha = preserve_pristine(
        live_path, pristine_path, expected_sha=PRE_RECORDING_AFFINITY_SHA256
    )
    hashes["affinity_review_pristine"] = pristine_sha

    recorded = apply_authorised_affinity_decisions(live_rows)
    write_corpus_csv_atomic(live_path, recorded, columns=AFFINITY_REVIEW_COLUMNS)
    post_sha = sha256_file(live_path)
    hashes["affinity_review_post"] = post_sha
    if post_sha == PRE_RECORDING_AFFINITY_SHA256:
        raise ScientificProposalError("affinity review hash did not change after recording")

    evidence_rows = _read_csv(
        repo_root / "data/interim/global_s4/evidence_affinity_proposals.csv"
    )
    projected, flags = project_affinity_reviews(evidence_rows, recorded)
    summary = summarise_affinity_projection(projected)
    unique_by_status: dict[str, set[str]] = {
        "exact_scalar": set(),
        "retain_raw": set(),
        "exclude_non_affinity": set(),
        "park": set(),
    }
    scalar_records: list[dict[str, str]] = []
    seen_scalar: set[str] = set()
    for row in projected:
        record_id = (row.get("record_id") or "").strip()
        status = (row.get("affinity_review_status") or "").strip()
        if status == "exact_scalar":
            unique_by_status["exact_scalar"].add(record_id)
            if record_id and record_id not in seen_scalar:
                seen_scalar.add(record_id)
                scalar_records.append(
                    {
                        "record_id": record_id,
                        "review_decision_id": row.get("review_decision_id", ""),
                        "affinity_value_raw": row.get("affinity_value_raw", ""),
                        "affinity_value_molar": row.get("affinity_value_molar", ""),
                        "transform_rule": row.get("transform_rule", ""),
                        "canonical_affinity_value": row.get("canonical_affinity_value", ""),
                        "canonical_affinity_unit": row.get("canonical_affinity_unit", ""),
                    }
                )
        elif status == "retain_raw":
            unique_by_status["retain_raw"].add(record_id)
            if (row.get("affinity_value_molar") or "").strip() or (
                row.get("canonical_affinity_value") or ""
            ).strip():
                raise ScientificProposalError(
                    f"{record_id} retain-raw must not carry a canonical scalar"
                )
        elif status == "exclude_non_affinity":
            unique_by_status["exclude_non_affinity"].add(record_id)
            if (row.get("canonical_affinity_value") or "").strip() or (
                row.get("canonical_affinity_unit") or ""
            ).strip():
                raise ScientificProposalError(
                    f"{record_id} non-affinity populated canonical affinity"
                )
        elif status == "park_unresolved":
            unique_by_status["park"].add(record_id)

    record_counts = {key: len(value) for key, value in unique_by_status.items()}
    if record_counts != {
        "exact_scalar": 11,
        "retain_raw": 741,
        "exclude_non_affinity": 114,
        "park": 0,
    }:
        raise ScientificProposalError(f"record-grain counts drifted: {record_counts}")
    if len(scalar_records) != 11:
        raise ScientificProposalError(f"expected 11 exact-scalar records, got {len(scalar_records)}")
    if any(not item["affinity_value_molar"] for item in scalar_records):
        raise ScientificProposalError("exact-scalar record missing molar value")

    flag_records = list(
        dict.fromkeys(item.get("record_id", "") for item in flags if item.get("record_id"))
    )
    if len(flag_records) != 49:
        raise ScientificProposalError(
            f"expected 49 evidence-affinity flags, got {len(flag_records)}"
        )
    flag_by_decision: dict[str, dict[str, object]] = {}
    for row in flags:
        decision_id = (row.get("review_decision_id") or "").strip()
        record_id = (row.get("record_id") or "").strip()
        kind = inconsistency_kind({**row, "evidence_affinity_inconsistency": "evidence_affinity_inconsistency"})
        entry = flag_by_decision.setdefault(decision_id, {"record_ids": [], "kinds": []})
        ids = entry["record_ids"]
        kinds = entry["kinds"]
        if record_id and record_id not in ids:
            ids.append(record_id)
        if kind and kind not in kinds:
            kinds.append(kind)

    validator = validate_checkpoint2_package(package_dir)
    if validator["errors"]:
        raise ScientificProposalError(f"validator errors: {validator['errors']}")
    if validator["unresolved_decisions"] != 0:
        raise ScientificProposalError(
            f"expected unresolved=0, got {validator['unresolved_decisions']}"
        )
    if validator["affinity_completion"].get("blank") != 0:
        raise ScientificProposalError("affinity review still has blank rows")
    if validator["target_completion"].get("blank", 0) != 0:
        raise ScientificProposalError("target review is no longer complete")
    if validator["ready_for_application"]:
        raise ScientificProposalError(
            "validator defect: ready_for_application=true while 49 "
            "evidence-affinity inconsistencies remain"
        )
    if not validator["application_blocked_by_evidence_affinity_inconsistency"]:
        raise ScientificProposalError(
            "validator did not block application on evidence-affinity inconsistency"
        )
    if validator["n_evidence_affinity_inconsistencies"] != 49:
        raise ScientificProposalError(
            "validator flag count drifted: "
            f"{validator['n_evidence_affinity_inconsistencies']}"
        )

    readme_path = package_dir / "README.md"
    if readme_path.is_file():
        write_text_atomic(readme_path, _readme_after_recording(readme_path.read_text(encoding="utf-8")))

    payload = {
        "milestone": "4E.4",
        "n_affinity_rows": 31,
        "decision_ids": list(AUTHORISED_AFFINITY_DECISIONS),
        "decision_counts": authorised_affinity_decision_counts(),
        "record_grain_counts": record_counts,
        "n_projected_rows": len(projected),
        "deterministic_scalar_recovery_records": scalar_records,
        "n_evidence_affinity_inconsistency_records": 49,
        "evidence_affinity_inconsistency_by_decision": {
            decision_id: {
                "n_records": len(item["record_ids"]),  # type: ignore[arg-type]
                "record_ids": item["record_ids"],
                "kinds": item["kinds"],
            }
            for decision_id, item in flag_by_decision.items()
        },
        "hashes": hashes,
        "validator": {
            "ready_for_application": validator["ready_for_application"],
            "unresolved_decisions": validator["unresolved_decisions"],
            "affinity_completion": validator["affinity_completion"],
            "application_blocked_by_evidence_affinity_inconsistency": validator[
                "application_blocked_by_evidence_affinity_inconsistency"
            ],
            "n_evidence_affinity_inconsistencies": validator[
                "n_evidence_affinity_inconsistencies"
            ],
        },
        "scientific_boundary": {
            "checkpoint2_applied": False,
            "combined_input_modified": False,
            "proposal_tables_bulk_applied": False,
            "target_review_modified": False,
            "relationship_review_modified": False,
            "evidence_review_modified": False,
            "s5_run": False,
            "evidence_affinity_flags_reconciled": False,
            "affinity_parks": 0,
        },
        "summary": summary,
    }
    write_json_atomic(
        package_dir / "human_review" / "affinity_recording_manifest.json",
        payload,
    )
    counts = authorised_affinity_decision_counts()
    scalar_ids = [
        decision_id
        for decision_id, fields in AUTHORISED_AFFINITY_DECISIONS.items()
        if fields["manual_decision"] == CONFIRM_AFFINITY_SCALAR
    ]
    raw_ids = [
        decision_id
        for decision_id, fields in AUTHORISED_AFFINITY_DECISIONS.items()
        if fields["manual_decision"] == RETAIN_AFFINITY_RAW
    ]
    exclude_ids = [
        decision_id
        for decision_id, fields in AUTHORISED_AFFINITY_DECISIONS.items()
        if fields["manual_decision"] == EXCLUDE_NON_AFFINITY
    ]
    note = "\n".join(
        [
            "# CHECKPOINT-2 affinity recording",
            "",
            "Sequence-safe human-review metadata for Milestone 4E.4.",
            "Decisions were recorded into the ignored affinity review CSV only.",
            "",
            "CHECKPOINT-2 has **not** been applied. Combined input is unchanged.",
            "Machine proposal tables were not bulk-updated. Target, relationship,",
            "and evidence review files were not modified. The 49 evidence-affinity",
            "inconsistency records remain blocking. Milestone 5 was not run.",
            "",
            "## Decision IDs (31)",
            "",
            ", ".join(AUTHORISED_AFFINITY_DECISIONS),
            "",
            f"confirm_affinity_scalar: {', '.join(scalar_ids)}",
            f"retain_affinity_raw: {', '.join(raw_ids)}",
            f"exclude_non_affinity: {', '.join(exclude_ids)}",
            "park_unresolved: none",
            "",
            "## Decision counts",
            "",
            "```text",
            f"confirm_affinity_scalar = {counts[CONFIRM_AFFINITY_SCALAR]}",
            f"retain_affinity_raw     = {counts[RETAIN_AFFINITY_RAW]}",
            f"exclude_non_affinity    = {counts[EXCLUDE_NON_AFFINITY]}",
            "park_unresolved         = 0",
            "--------------------------------",
            "total                   = 31",
            "```",
            "",
            "Affinity review: 31 resolved / 0 blank.",
            "Target review remains 205/205. Relationship review remains 107/107.",
            "Evidence review remains 3/3.",
            "Unresolved CHECKPOINT-2 human decisions: 0.",
            "`ready_for_application` remains false because 49 evidence-affinity",
            "inconsistencies remain unreconciled.",
            "",
            "Exact-scalar transforms (11 records): `mojibake_micro_M` (C2A0002),",
            "`central_value_uncertainty` (C2A0016A), `glued_unit` (C2A0016B),",
            "`scientific_notation` (C2A0018B). No group-level numeric scalar",
            "was stored. No affinity parks.",
            "",
            "Evidence-affinity flags retained intentionally (49 unique records):",
            "C2A0004A 9, C2A0004B 25, C2A0010 3, C2A0014B 2, C2A0019 1",
            "(machine E2 / reviewed non-affinity);",
            "C2A0002 4, C2A0016A 2, C2A0016B 3",
            "(machine E4 / reviewed exact quantitative affinity).",
            "C2A0018B is exact scalar + machine E2 and is consistent.",
            "",
            f"Pre-recording SHA-256: `{PRE_RECORDING_AFFINITY_SHA256}`",
            f"Pristine: `pristine/{PRISTINE_NAME}`",
            f"Post-recording SHA-256: `{post_sha}`",
            "",
        ]
    )
    write_text_atomic(
        package_dir / "human_review" / "affinity_recording_note.md",
        note,
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record the 31 authorised CHECKPOINT-2 affinity decisions"
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args()
    repo_root = args.repo_root or SCRIPT_DIR.parents[1]
    result = record_live_affinity_decisions(repo_root=repo_root)
    print(
        json.dumps(
            {
                "n_affinity_rows": result["n_affinity_rows"],
                "decision_counts": result["decision_counts"],
                "record_grain_counts": result["record_grain_counts"],
                "n_evidence_affinity_inconsistency_records": result[
                    "n_evidence_affinity_inconsistency_records"
                ],
                "hashes": result["hashes"],
                "validator": result["validator"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

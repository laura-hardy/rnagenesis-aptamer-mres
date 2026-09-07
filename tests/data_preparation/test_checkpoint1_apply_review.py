"""Tests for CHECKPOINT-1 review application and closure (synthetic only).

Every literal nucleotide string in this file is shorter than 20 nt. Does not
read real AptaBase checkpoint data or import the legacy cleaner.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from checkpoint1_apply_review import (  # noqa: E402
    CHECKPOINT_CLOSED_STATEMENT,
    MANIFEST_COLUMNS,
    Checkpoint1ApplyError,
    apply_aptabase_checkpoint1_review,
    main,
)
from checkpoint1_prepare_review import (  # noqa: E402
    MANUAL_REVIEW_COLUMNS,
    prepare_aptabase_checkpoint1_review,
    write_csv_atomic,
)

SEQ_LEAK_RE = re.compile(r"[ACGTUacgtu]{20,}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _base_review(
    record_id: str,
    *,
    decision: str,
    primary: str,
    priority: str,
    required: str,
    secondary: str = "",
) -> dict[str, str]:
    return {
        "record_id": record_id,
        "native_id": record_id.split(":")[-1],
        "aptamer_name": f"name-{record_id}",
        "target_name_raw": "demo_target",
        "proposed_decision": decision,
        "primary_reason": primary,
        "secondary_reasons": secondary,
        "manual_review_required": required,
        "manual_review_priority": priority,
        "checkpoint_status": "pending_checkpoint_1_review",
        "molecule_type": "RNA",
        "alphabet_as_reported": "RNA",
        "sequence_length_full": "8",
        "sequence_length_core": "8",
        "construct_scope": "full_equals_core_untrimmed",
        "trim_status": "not_trimmed",
        "sequence_leakage_match": "false",
        "sequence_leakage_identity": "",
        "sequence_leakage_reference_id": "",
        "sequence_leakage_target": "",
        "target_leakage_match": "false",
        "target_leakage_canonical_target": "",
        "target_leakage_match_type": "",
        "source_record_validity": "valid",
        "qc_flags": "",
        "notes": "",
    }


def _base_detail(
    review: dict[str, str],
    *,
    sequence: str = "ACGUACGU",
) -> dict[str, str]:
    length = str(len(sequence)) if sequence else ""
    return {
        "record_id": review["record_id"],
        "native_id": review["native_id"],
        "aptamer_name": review["aptamer_name"],
        "target_name_raw": review["target_name_raw"],
        "target_general_raw": "general",
        "target_specific_raw": "specific",
        "publication": "Demo",
        "proposed_decision": review["proposed_decision"],
        "primary_reason": review["primary_reason"],
        "secondary_reasons": review["secondary_reasons"],
        "manual_review_required": review["manual_review_required"],
        "manual_review_priority": review["manual_review_priority"],
        "checkpoint_status": review["checkpoint_status"],
        "sequence_raw": sequence,
        "sequence_full": sequence,
        "sequence_core": sequence,
        "sequence_length_full": length,
        "sequence_length_core": length,
        "molecule_type": review["molecule_type"],
        "alphabet_as_reported": review["alphabet_as_reported"],
        "t_to_u_applied": "false",
        "construct_scope": review["construct_scope"],
        "trim_status": review["trim_status"],
        "detected_constant_5p": "",
        "detected_constant_3p": "",
        "source_record_validity": review["source_record_validity"],
        "source_parse_warnings": "",
        "reported_length_raw": length,
        "reported_length_difference": "0",
        "gc_reported_raw": "50",
        "gc_calculated_s2": "50.0",
        "gc_difference_percentage_points": "0.0",
        "sequence_leakage_match": review["sequence_leakage_match"],
        "sequence_leakage_identity": "",
        "sequence_leakage_reference_id": "",
        "target_leakage_match": review["target_leakage_match"],
        "target_leakage_canonical_target": "",
        "qc_flags": review["qc_flags"],
        "notes": "",
    }


def _fixture_rows() -> list[dict[str, str]]:
    """Compact fixture covering accept/park/reject + no-review paths."""
    return [
        _base_review(
            "aptabase:a1",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            priority="medium",
            required="true",
            secondary="minor_diagnostic",
        ),
        _base_review(
            "aptabase:p1",
            decision="proposed_park",
            primary="molecule_type_unresolved",
            priority="medium",
            required="true",
        ),
        _base_review(
            "aptabase:r1",
            decision="proposed_reject",
            primary="core_below_minimum",
            priority="low",
            required="true",
        ),
        _base_review(
            "aptabase:p2",
            decision="proposed_park",
            primary="ssdna_not_eligible_for_rna_training",
            priority="medium",
            required="true",
        ),
        _base_review(
            "aptabase:a2",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            priority="medium",
            required="true",
        ),
        _base_review(
            "aptabase:a3",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            priority="medium",
            required="true",
        ),
        _base_review(
            "aptabase:p3",
            decision="proposed_park",
            primary="invalid_sequence_requires_review",
            priority="high",
            required="true",
        ),
        # no-review accept
        _base_review(
            "aptabase:nr_a",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            priority="none",
            required="false",
        ),
        # no-review reject
        _base_review(
            "aptabase:nr_r",
            decision="proposed_reject",
            primary="missing_sequence",
            priority="none",
            required="false",
        ),
        # no-review park (edge case)
        _base_review(
            "aptabase:nr_p",
            decision="proposed_park",
            primary="molecule_type_unresolved",
            priority="none",
            required="false",
        ),
    ]


def _make_tree(tmp_path: Path, review_rows: list[dict[str, str]] | None = None):
    rows = review_rows if review_rows is not None else _fixture_rows()
    repo = tmp_path / "repo"
    (repo / "docs" / "data_curation").mkdir(parents=True)
    (repo / "scripts" / "data_preparation").mkdir(parents=True)
    (repo / "config" / "checkpoint_reviews").mkdir(parents=True)
    (repo / ".git").mkdir()
    checkpoint = repo / "data" / "interim" / "checkpoints" / "aptabase_cp1"
    checkpoint.mkdir(parents=True)
    details = [_base_detail(row) for row in rows]
    review_fields = list(rows[0].keys())
    detail_fields = list(details[0].keys())
    _write_csv(checkpoint / "aptabase_checkpoint1_review.csv", review_fields, rows)
    _write_csv(
        checkpoint / "aptabase_checkpoint1_local_detail.csv",
        detail_fields,
        details,
    )
    # Minimal S3 artefacts referenced by apply (canonical/decisions may be stubs).
    _write_csv(
        checkpoint / "aptabase_s3_canonical.csv",
        ["record_id", "sequence_core"],
        [{"record_id": r["record_id"], "sequence_core": "ACGUACGU"} for r in rows],
    )
    _write_csv(
        checkpoint / "aptabase_s3_decisions.csv",
        review_fields,
        rows,
    )
    return repo, checkpoint, rows


def _prepare_and_complete(
    repo: Path,
    checkpoint: Path,
    *,
    actions: dict[str, tuple[str, str]],
) -> Path:
    """Prepare pristine package then complete review fields for active rows."""
    manual_dir = checkpoint / "manual_review"
    prepare_aptabase_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=manual_dir,
        expected_active_rows=sum(
            1
            for row in _read_review(checkpoint)
            if row["manual_review_required"] == "true"
        ),
        expected_total_rows=len(_read_review(checkpoint)),
        enforce_expected_batch_counts=False,
    )
    review_path = manual_dir / "aptabase_checkpoint1_manual_review.csv"
    rows = list(csv.DictReader(review_path.open(encoding="utf-8", newline="")))
    completed: list[dict[str, str]] = []
    for row in rows:
        action, note = actions[row["record_id"]]
        updated = dict(row)
        updated["review_action"] = action
        updated["reviewer_note"] = note
        updated["reviewer_initials"] = ""
        completed.append(updated)
    write_csv_atomic(review_path, MANUAL_REVIEW_COLUMNS, completed)
    return review_path


def _read_review(checkpoint: Path) -> list[dict[str, str]]:
    path = checkpoint / "aptabase_checkpoint1_review.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _default_actions() -> dict[str, tuple[str, str]]:
    return {
        "aptabase:a1": ("confirm_current", ""),
        "aptabase:p1": ("confirm_current", ""),
        "aptabase:r1": ("confirm_current", ""),
        "aptabase:p2": ("override_to_accept", "justify accept override"),
        "aptabase:a2": ("override_to_park", "justify park override"),
        "aptabase:a3": ("override_to_reject", "justify reject override"),
        "aptabase:p3": ("needs_source_review", "need source check"),
    }


def _run_apply(
    repo: Path,
    checkpoint: Path,
    review_path: Path,
    *,
    expected_active: int,
    expected_total: int,
) -> object:
    return apply_aptabase_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        review_file=review_path,
        output_dir=checkpoint / "resolved",
        tracked_manifest=repo
        / "config"
        / "checkpoint_reviews"
        / "aptabase_checkpoint1_resolutions.csv",
        metadata_out=repo
        / "config"
        / "checkpoint_reviews"
        / "aptabase_checkpoint1_metadata.json",
        pristine_dir=checkpoint / "closure_validation" / "pristine",
        expected_active_rows=expected_active,
        expected_total_rows=expected_total,
        enforce_expected_batch_counts=False,
        verify_pipeline_integrity=False,
    )


def _mutate_completed(
    review_path: Path,
    record_id: str,
    **fields: str,
) -> None:
    rows = list(csv.DictReader(review_path.open(encoding="utf-8", newline="")))
    out: list[dict[str, str]] = []
    for row in rows:
        updated = dict(row)
        if updated["record_id"] == record_id:
            updated.update(fields)
        out.append(updated)
    write_csv_atomic(review_path, MANUAL_REVIEW_COLUMNS, out)


# ---------------------------------------------------------------------------
# Review-file integrity
# ---------------------------------------------------------------------------


def test_valid_completed_review_passes(tmp_path: Path) -> None:
    repo, checkpoint, rows = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    before = review_path.read_bytes()
    result = _run_apply(
        repo,
        checkpoint,
        review_path,
        expected_active=7,
        expected_total=10,
    )
    assert result.stats.total_records == 10
    assert review_path.read_bytes() == before


def test_changed_sequence_field_fails(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    _mutate_completed(review_path, "aptabase:a1", sequence_core="UUUUUUUU")
    with pytest.raises(Checkpoint1ApplyError, match="sequence_core"):
        _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_changed_target_field_fails(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    _mutate_completed(review_path, "aptabase:a1", target_name_raw="CHANGED")
    with pytest.raises(Checkpoint1ApplyError, match="target_name_raw"):
        _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_changed_proposed_decision_fails(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    _mutate_completed(review_path, "aptabase:a1", proposed_decision="proposed_park")
    with pytest.raises(Checkpoint1ApplyError, match="proposed_decision"):
        _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_changed_primary_reason_fails(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    _mutate_completed(review_path, "aptabase:a1", primary_reason="core_below_minimum")
    with pytest.raises(Checkpoint1ApplyError, match="primary_reason"):
        _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_changed_secondary_reason_fails(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    _mutate_completed(review_path, "aptabase:a1", secondary_reasons="altered")
    with pytest.raises(Checkpoint1ApplyError, match="secondary_reasons"):
        _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_changed_record_id_fails(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    rows = list(csv.DictReader(review_path.open(encoding="utf-8", newline="")))
    out: list[dict[str, str]] = []
    for row in rows:
        updated = dict(row)
        if updated["record_id"] == "aptabase:a1":
            updated["record_id"] = "aptabase:ZZZ"
        out.append(updated)
    write_csv_atomic(review_path, MANUAL_REVIEW_COLUMNS, out)
    with pytest.raises(Checkpoint1ApplyError):
        _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_missing_review_row_fails(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    rows = list(csv.DictReader(review_path.open(encoding="utf-8", newline="")))
    rows = [r for r in rows if r["record_id"] != "aptabase:a1"]
    write_csv_atomic(review_path, MANUAL_REVIEW_COLUMNS, rows)
    with pytest.raises(Checkpoint1ApplyError, match="Active review row count|Missing"):
        _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_extra_review_row_fails(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    rows = list(csv.DictReader(review_path.open(encoding="utf-8", newline="")))
    extra = dict(rows[0])
    extra["record_id"] = "aptabase:EXTRA"
    rows.append(extra)
    write_csv_atomic(review_path, MANUAL_REVIEW_COLUMNS, rows)
    with pytest.raises(Checkpoint1ApplyError, match="Active review row count|Extra"):
        _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_duplicate_review_row_fails(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    rows = list(csv.DictReader(review_path.open(encoding="utf-8", newline="")))
    rows.append(dict(rows[0]))
    write_csv_atomic(review_path, MANUAL_REVIEW_COLUMNS, rows)
    with pytest.raises(Checkpoint1ApplyError, match="Duplicate|Active review row count"):
        _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_changed_review_order_fails(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    _mutate_completed(review_path, "aptabase:a1", review_order="999")
    with pytest.raises(Checkpoint1ApplyError, match="review_order"):
        _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_spreadsheet_boolean_and_numeric_coercion_accepted(tmp_path: Path) -> None:
    """Excel-style FALSE/TRUE and numeric reformatting on immutable fields pass."""
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    rows = list(csv.DictReader(review_path.open(encoding="utf-8", newline="")))
    out: list[dict[str, str]] = []
    for row in rows:
        updated = dict(row)
        if updated["record_id"] == "aptabase:a1":
            updated["t_to_u_applied"] = "FALSE"
            updated["sequence_leakage_match"] = "FALSE"
            updated["target_leakage_match"] = "FALSE"
            updated["reported_length_raw"] = "8"
            updated["gc_calculated_s2"] = "50"
        out.append(updated)
    write_csv_atomic(review_path, MANUAL_REVIEW_COLUMNS, out)
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    assert result.stats.pristine_comparison_ok is True


def test_spreadsheet_cannot_mask_real_immutable_drift(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    _mutate_completed(review_path, "aptabase:a1", molecule_type="DNA")
    with pytest.raises(Checkpoint1ApplyError, match="molecule_type"):
        _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_only_permitted_review_columns_may_differ(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    # Changing a permitted field alone must still pass (already does via default).
    _mutate_completed(
        review_path,
        "aptabase:a1",
        reviewer_initials="AB",
        reviewer_note="optional note",
    )
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:a1"]["reviewer_initials"] == "AB"


# ---------------------------------------------------------------------------
# Review-action validation
# ---------------------------------------------------------------------------


def test_empty_active_review_action_fails(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    actions = _default_actions()
    actions["aptabase:a1"] = ("", "")
    review_path = _prepare_and_complete(repo, checkpoint, actions=actions)
    with pytest.raises(Checkpoint1ApplyError, match="Empty review_action"):
        _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_unknown_review_action_fails(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    actions = _default_actions()
    actions["aptabase:a1"] = ("approve_somehow", "x")
    review_path = _prepare_and_complete(repo, checkpoint, actions=actions)
    with pytest.raises(Checkpoint1ApplyError, match="Unknown review_action"):
        _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_confirm_current_blank_note_passes(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:a1"]["review_action"] == "confirm_current"
    assert by_id["aptabase:a1"]["reviewer_note"] == ""


@pytest.mark.parametrize(
    "action",
    [
        "override_to_accept",
        "override_to_park",
        "override_to_reject",
        "needs_source_review",
    ],
)
def test_override_and_source_review_empty_note_passes(
    tmp_path: Path, action: str
) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    actions = _default_actions()
    actions["aptabase:p1"] = (action, "")
    review_path = _prepare_and_complete(repo, checkpoint, actions=actions)
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:p1"]["review_action"] == action
    assert by_id["aptabase:p1"]["reviewer_note"] == ""


def test_supplied_notes_preserved_and_hashed(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    resolution = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    manifest = {
        r["record_id"]: r
        for r in csv.DictReader(result.tracked_manifest.open(encoding="utf-8"))
    }
    note = "justify accept override"
    assert resolution["aptabase:p2"]["reviewer_note"] == note
    assert manifest["aptabase:p2"]["reviewer_note_present"] == "true"
    assert manifest["aptabase:p2"]["reviewer_note_sha256"] == hashlib.sha256(
        note.encode("utf-8")
    ).hexdigest()
    assert resolution["aptabase:a1"]["reviewer_note"] == ""
    assert manifest["aptabase:a1"]["reviewer_note_present"] == "false"
    assert manifest["aptabase:a1"]["reviewer_note_sha256"] == ""


def test_blank_reviewer_initials_pass(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    assert result.stats.blank_initials_rows == 7


def test_all_reviewer_initials_blank_pass(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    rows = list(csv.DictReader(review_path.open(encoding="utf-8", newline="")))
    assert all(not (r["reviewer_initials"] or "").strip() for r in rows)
    _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)


def test_nonempty_initials_preserved_but_not_required(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    _mutate_completed(review_path, "aptabase:a1", reviewer_initials="XY")
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:a1"]["reviewer_initials"] == "XY"
    assert result.stats.blank_initials_rows == 6


# ---------------------------------------------------------------------------
# Resolution mapping
# ---------------------------------------------------------------------------


def test_confirm_proposed_accept_to_accept(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:a1"]["resolved_decision"] == "accept"
    assert by_id["aptabase:a1"]["checkpoint1_resolution_status"] == "approved_for_s4"


def test_confirm_proposed_park_to_park(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:p1"]["resolved_decision"] == "park"
    assert (
        by_id["aptabase:p1"]["checkpoint1_resolution_status"]
        == "parked_after_checkpoint1"
    )


def test_confirm_proposed_reject_to_reject(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:r1"]["resolved_decision"] == "reject"


def test_override_park_to_accept(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:p2"]["resolved_decision"] == "accept"
    assert by_id["aptabase:p2"]["override_applied"] == "true"


def test_override_accept_to_park(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:a2"]["resolved_decision"] == "park"


def test_override_accept_to_reject(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:a3"]["resolved_decision"] == "reject"


def test_needs_source_review_maps_to_park_status(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:p3"]["resolved_decision"] == "park"
    assert by_id["aptabase:p3"]["checkpoint1_resolution_status"] == "needs_source_review"
    assert by_id["aptabase:p3"]["authorised_for_s4"] == "false"
    assert by_id["aptabase:p3"]["override_applied"] == "false"


def test_no_review_accept_approved_for_s4(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:nr_a"]["review_action"] == "not_required"
    assert by_id["aptabase:nr_a"]["resolved_decision"] == "accept"
    assert by_id["aptabase:nr_a"]["checkpoint1_resolution_status"] == "approved_for_s4"
    assert by_id["aptabase:nr_a"]["authorised_for_s4"] == "true"


def test_no_review_reject_rejected(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:nr_r"]["resolved_decision"] == "reject"
    assert (
        by_id["aptabase:nr_r"]["checkpoint1_resolution_status"]
        == "rejected_after_checkpoint1"
    )


def test_no_review_park_handled_safely(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_resolution.open(encoding="utf-8"))
    }
    assert by_id["aptabase:nr_p"]["resolved_decision"] == "park"
    assert by_id["aptabase:nr_p"]["authorised_for_s4"] == "false"


def test_only_accepts_authorised_for_s4(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    rows = list(csv.DictReader(result.output_resolution.open(encoding="utf-8")))
    for row in rows:
        if row["resolved_decision"] == "accept":
            assert row["authorised_for_s4"] == "true"
        else:
            assert row["authorised_for_s4"] == "false"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def test_manifest_one_row_per_record(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    rows = list(csv.DictReader(result.tracked_manifest.open(encoding="utf-8")))
    assert len(rows) == 10
    assert len({r["record_id"] for r in rows}) == 10


def test_manifest_no_sequence_or_target_or_note_content(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    text = result.tracked_manifest.read_text(encoding="utf-8")
    header = text.splitlines()[0].split(",")
    assert header == list(MANIFEST_COLUMNS)
    assert "sequence" not in text.lower().split(",")[0]
    for col in (
        "sequence_raw",
        "sequence_full",
        "sequence_core",
        "target_name_raw",
        "reviewer_note",
    ):
        assert col not in header
    assert "justify accept override" not in text


def test_manifest_note_sha_and_empty(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    rows = {
        r["record_id"]: r
        for r in csv.DictReader(result.tracked_manifest.open(encoding="utf-8"))
    }
    assert rows["aptabase:a1"]["reviewer_note_present"] == "false"
    assert rows["aptabase:a1"]["reviewer_note_sha256"] == ""
    note = "justify accept override"
    assert rows["aptabase:p2"]["reviewer_note_present"] == "true"
    assert rows["aptabase:p2"]["reviewer_note_sha256"] == hashlib.sha256(
        note.encode("utf-8")
    ).hexdigest()


def test_manifest_override_boolean_and_lowercase(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    rows = list(csv.DictReader(result.tracked_manifest.open(encoding="utf-8")))
    by_id = {r["record_id"]: r for r in rows}
    assert by_id["aptabase:p2"]["override_applied"] == "true"
    assert by_id["aptabase:p3"]["override_applied"] == "false"
    assert by_id["aptabase:a1"]["override_applied"] == "false"
    assert by_id["aptabase:nr_a"]["override_applied"] == "false"
    for row in rows:
        assert row["authorised_for_s4"] in {"true", "false"}
        assert row["override_applied"] in {"true", "false"}
        assert row["reviewer_note_present"] in {"true", "false"}
        assert row["manual_review_required"] in {"true", "false"}


def test_manifest_deterministic_ordering(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    s3_ids = [r["record_id"] for r in _read_review(checkpoint)]
    manifest_ids = [
        r["record_id"]
        for r in csv.DictReader(result.tracked_manifest.open(encoding="utf-8"))
    ]
    assert manifest_ids == s3_ids


# ---------------------------------------------------------------------------
# Output / integration
# ---------------------------------------------------------------------------


def test_id_files_reconcile(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    s4 = list(csv.DictReader(result.output_s4_ids.open(encoding="utf-8")))
    parked = list(csv.DictReader(result.output_parked_ids.open(encoding="utf-8")))
    rejected = list(csv.DictReader(result.output_rejected_ids.open(encoding="utf-8")))
    full = list(csv.DictReader(result.output_resolution.open(encoding="utf-8")))
    assert len(s4) + len(parked) + len(rejected) == 10
    assert all(r["resolved_decision"] == "accept" for r in s4)
    assert {r["record_id"] for r in s4} == {
        r["record_id"] for r in full if r["authorised_for_s4"] == "true"
    }
    assert {r["record_id"] for r in parked} == {
        r["record_id"] for r in full if r["resolved_decision"] == "park"
    }
    assert {r["record_id"] for r in rejected} == {
        r["record_id"] for r in full if r["resolved_decision"] == "reject"
    }


def test_atomic_deterministic_rerun_and_cwd(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    first = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    hashes = {
        "resolution": _sha256(first.output_resolution),
        "s4": _sha256(first.output_s4_ids),
        "parked": _sha256(first.output_parked_ids),
        "rejected": _sha256(first.output_rejected_ids),
        "summary": _sha256(first.output_summary),
        "manifest": _sha256(first.tracked_manifest),
        "metadata": _sha256(first.metadata_out),
    }
    review_before = review_path.read_bytes()
    second = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    assert _sha256(second.output_resolution) == hashes["resolution"]
    assert _sha256(second.output_s4_ids) == hashes["s4"]
    assert _sha256(second.output_parked_ids) == hashes["parked"]
    assert _sha256(second.output_rejected_ids) == hashes["rejected"]
    assert _sha256(second.output_summary) == hashes["summary"]
    assert _sha256(second.tracked_manifest) == hashes["manifest"]
    assert _sha256(second.metadata_out) == hashes["metadata"]
    assert review_path.read_bytes() == review_before

    # Running from another cwd via CLI.
    other = tmp_path / "othercwd"
    other.mkdir()
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "aptabase",
                "--repo-root",
                str(repo),
                "--checkpoint-dir",
                str(checkpoint.relative_to(repo)),
                "--review-file",
                str(review_path.relative_to(repo)),
                "--output-dir",
                str((checkpoint / "resolved").relative_to(repo)),
                "--tracked-manifest",
                "config/checkpoint_reviews/aptabase_checkpoint1_resolutions.csv",
                "--metadata-out",
                "config/checkpoint_reviews/aptabase_checkpoint1_metadata.json",
                "--expected-active-rows",
                "7",
                "--expected-total-rows",
                "10",
                "--skip-expected-batch-counts",
                "--skip-pipeline-integrity",
            ]
        )
    # Change cwd and ensure relative resolution still works when repo-root set.
    old = Path.cwd()
    try:
        os.chdir(other)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code2 = main(
                [
                    "--source",
                    "aptabase",
                    "--repo-root",
                    str(repo),
                    "--checkpoint-dir",
                    "data/interim/checkpoints/aptabase_cp1",
                    "--review-file",
                    "data/interim/checkpoints/aptabase_cp1/manual_review/"
                    "aptabase_checkpoint1_manual_review.csv",
                    "--output-dir",
                    "data/interim/checkpoints/aptabase_cp1/resolved",
                    "--tracked-manifest",
                    "config/checkpoint_reviews/aptabase_checkpoint1_resolutions.csv",
                    "--metadata-out",
                    "config/checkpoint_reviews/aptabase_checkpoint1_metadata.json",
                    "--expected-active-rows",
                    "7",
                    "--expected-total-rows",
                    "10",
                    "--skip-expected-batch-counts",
                    "--skip-pipeline-integrity",
                ]
            )
    finally:
        os.chdir(old)
    assert code == 0
    assert code2 == 0
    assert "ACGUACGU" not in stdout.getvalue()
    assert "justify" not in stdout.getvalue()


def test_no_absolute_paths_in_tracked_outputs(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    abs_root = str(repo.resolve())
    for path in (result.tracked_manifest, result.metadata_out, result.output_summary):
        text = path.read_text(encoding="utf-8")
        assert abs_root not in text


def test_summary_and_metadata_conventions(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    before = _sha256(review_path)
    result = _run_apply(
        repo, checkpoint, review_path, expected_active=7, expected_total=10
    )
    summary = result.output_summary.read_text(encoding="utf-8")
    assert CHECKPOINT_CLOSED_STATEMENT in summary
    meta = json.loads(result.metadata_out.read_text(encoding="utf-8"))
    assert meta["review_model"] == "single_reviewer"
    assert meta["reviewer_initials_required"] is False
    assert meta["reviewer_notes_required"] is False
    assert meta["review_file_sha256"] == before
    assert meta["checkpoint_status"] == "closed"
    assert meta["next_stage"] == "S4_target_normalisation"
    assert "reviewer_name" not in meta


def test_unknown_source_fails() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(["--source", "ena"])
    assert code == 1
    assert "Unsupported source_key" in stderr.getvalue()
    assert "aptaindex" in stderr.getvalue()


def test_input_files_remain_byte_identical(tmp_path: Path) -> None:
    repo, checkpoint, _ = _make_tree(tmp_path)
    review_path = _prepare_and_complete(repo, checkpoint, actions=_default_actions())
    hashes = {
        "review": _sha256(review_path),
        "s3_review": _sha256(checkpoint / "aptabase_checkpoint1_review.csv"),
        "local": _sha256(checkpoint / "aptabase_checkpoint1_local_detail.csv"),
        "canonical": _sha256(checkpoint / "aptabase_s3_canonical.csv"),
        "decisions": _sha256(checkpoint / "aptabase_s3_decisions.csv"),
    }
    _run_apply(repo, checkpoint, review_path, expected_active=7, expected_total=10)
    assert _sha256(review_path) == hashes["review"]
    assert _sha256(checkpoint / "aptabase_checkpoint1_review.csv") == hashes["s3_review"]
    assert _sha256(checkpoint / "aptabase_checkpoint1_local_detail.csv") == hashes["local"]
    assert _sha256(checkpoint / "aptabase_s3_canonical.csv") == hashes["canonical"]
    assert _sha256(checkpoint / "aptabase_s3_decisions.csv") == hashes["decisions"]


def test_utexas_overlay_parks_complex_constructs_and_rejects_iupac() -> None:
    from adapters.utexas_alphabet_exceptions import (
        AlphabetResolution,
        SUGGESTED_CONFIRM_REJECT,
        SUGGESTED_OVERRIDE_PARK,
        REASON_COMPLEX_PARK,
        REASON_IUPAC_REJECT,
    )
    from checkpoint1_apply_review import (
        COMPLEX_CONSTRUCT_REASON,
        _overlay_utexas_alphabet_resolutions,
        resolve_no_review_row,
    )

    iupac = resolve_no_review_row(
        {
            "record_id": "utexas:iupac",
            "native_id": "iupac",
            "proposed_decision": "proposed_reject",
            "primary_reason": "ambiguous_bases",
            "secondary_reasons": "",
        }
    )
    malformed = resolve_no_review_row(
        {
            "record_id": "utexas:malformed",
            "native_id": "malformed",
            "proposed_decision": "proposed_reject",
            "primary_reason": "invalid_alphabet",
            "secondary_reasons": "",
        }
    )
    complex_row = resolve_no_review_row(
        {
            "record_id": "utexas:complex",
            "native_id": "complex",
            "proposed_decision": "proposed_reject",
            "primary_reason": "invalid_alphabet",
            "secondary_reasons": "",
        }
    )
    accept = resolve_no_review_row(
        {
            "record_id": "utexas:ok",
            "native_id": "ok",
            "proposed_decision": "proposed_accept",
            "primary_reason": "technically_eligible_rna",
            "secondary_reasons": "trim_construct_unresolved",
        }
    )
    rows = [iupac, malformed, complex_row, accept]
    alphabet = {
        "utexas:iupac": AlphabetResolution(
            record_id="utexas:iupac",
            decision=SUGGESTED_CONFIRM_REJECT,
            transformation_profile="",
            expected_recovered_length=None,
            review_note=REASON_IUPAC_REJECT,
        ),
        "utexas:malformed": AlphabetResolution(
            record_id="utexas:malformed",
            decision=SUGGESTED_CONFIRM_REJECT,
            transformation_profile="",
            expected_recovered_length=None,
            review_note="Sequence field is corrupted/unrecoverable",
        ),
        "utexas:complex": AlphabetResolution(
            record_id="utexas:complex",
            decision=SUGGESTED_OVERRIDE_PARK,
            transformation_profile="",
            expected_recovered_length=None,
            review_note=REASON_COMPLEX_PARK,
        ),
    }
    _overlay_utexas_alphabet_resolutions(rows, alphabet)
    by_id = {row["record_id"]: row for row in rows}
    assert by_id["utexas:iupac"]["resolved_decision"] == "reject"
    assert by_id["utexas:iupac"]["authorised_for_s4"] == "false"
    assert by_id["utexas:malformed"]["resolved_decision"] == "reject"
    assert by_id["utexas:complex"]["resolved_decision"] == "park"
    assert by_id["utexas:complex"]["resolved_reason"] == COMPLEX_CONSTRUCT_REASON
    assert by_id["utexas:complex"]["authorised_for_s4"] == "false"
    assert by_id["utexas:ok"]["resolved_decision"] == "accept"
    assert by_id["utexas:ok"]["authorised_for_s4"] == "true"
    ids = [row["record_id"] for row in rows]
    assert len(ids) == len(set(ids))
    assert {row["resolved_decision"] for row in rows} <= {"accept", "park", "reject"}
    assert sum(1 for row in rows if row["authorised_for_s4"] == "true") == 1

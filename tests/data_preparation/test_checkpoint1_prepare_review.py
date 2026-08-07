"""Tests for CHECKPOINT-1 manual-review package preparation (synthetic only).

Every literal nucleotide string in this file is shorter than 20 nt. Does not
read real AptaBase checkpoint data or import the legacy cleaner.
"""

from __future__ import annotations

import csv
import hashlib
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from checkpoint1_prepare_review import (  # noqa: E402
    INDEX_COLUMNS,
    MANUAL_REVIEW_COLUMNS,
    SEQUENCE_COLUMNS,
    Checkpoint1ReviewError,
    assign_review_batch,
    main,
    prepare_aptabase_checkpoint1_review,
    write_csv_atomic,
)


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


def _make_tree(
    tmp_path: Path,
    review_rows: list[dict[str, str]],
    detail_rows: list[dict[str, str]] | None = None,
) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    # Markers for find_repo_root when used via CLI.
    (repo / "docs" / "data_curation").mkdir(parents=True)
    (repo / "scripts" / "data_preparation").mkdir(parents=True)
    (repo / ".git").mkdir()
    checkpoint = repo / "data" / "interim" / "checkpoints" / "aptabase_cp1"
    checkpoint.mkdir(parents=True)
    details = detail_rows if detail_rows is not None else [
        _base_detail(row) for row in review_rows
    ]
    # Use union of keys present; keep stable column order from first detail.
    review_fields = list(review_rows[0].keys())
    detail_fields = list(details[0].keys())
    _write_csv(checkpoint / "aptabase_checkpoint1_review.csv", review_fields, review_rows)
    _write_csv(
        checkpoint / "aptabase_checkpoint1_local_detail.csv",
        detail_fields,
        details,
    )
    output = checkpoint / "manual_review"
    return repo, checkpoint, output


def _run(
    repo: Path,
    checkpoint: Path,
    output: Path,
    *,
    expected_active: int,
    expected_total: int,
) -> object:
    return prepare_aptabase_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=output,
        expected_active_rows=expected_active,
        expected_total_rows=expected_total,
        enforce_expected_batch_counts=False,
    )


def _fixture_all_batches() -> list[dict[str, str]]:
    """One required row per batch plus excluded no-review rows."""
    rows = [
        _base_review(
            "aptabase:r1",
            decision="proposed_reject",
            primary="core_below_minimum",
            priority="low",
            required="true",
        ),
        _base_review(
            "aptabase:r2",
            decision="proposed_reject",
            primary="source_record_invalid",
            priority="high",
            required="true",
        ),
        _base_review(
            "aptabase:a1",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            priority="low",
            required="true",
        ),
        _base_review(
            "aptabase:p1",
            decision="proposed_park",
            primary="molecule_type_unresolved",
            priority="medium",
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
            "aptabase:p3",
            decision="proposed_park",
            primary="invalid_sequence_requires_review",
            priority="high",
            required="true",
        ),
        _base_review(
            "aptabase:p4",
            decision="proposed_park",
            primary="core_above_maximum_requires_review",
            priority="medium",
            required="true",
        ),
        _base_review(
            "aptabase:p5",
            decision="proposed_park",
            primary="mixed_t_u_requires_review",
            priority="high",
            required="true",
        ),
        _base_review(
            "aptabase:p6",
            decision="proposed_park",
            primary="trim_or_construct_requires_review",
            priority="high",
            required="true",
        ),
        _base_review(
            "aptabase:p7",
            decision="proposed_park",
            primary="ambiguous_sequence_requires_review",
            priority="medium",
            required="true",
        ),
        # Excluded from active queue.
        _base_review(
            "aptabase:m1",
            decision="proposed_reject",
            primary="missing_sequence",
            priority="none",
            required="false",
        ),
        _base_review(
            "aptabase:a0",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            priority="none",
            required="false",
        ),
    ]
    return rows


def test_assign_exactly_one_batch_per_review_required_record() -> None:
    for row in _fixture_all_batches():
        if row["manual_review_required"] != "true":
            continue
        batch = assign_review_batch(row)
        assert batch.startswith(("01_", "02_", "03_", "04_", "05_", "06_", "07_", "08_", "09_"))


def test_missing_sequence_rejects_excluded(tmp_path: Path) -> None:
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    result = _run(repo, checkpoint, output, expected_active=10, expected_total=12)
    with result.output_queue.open(encoding="utf-8", newline="") as handle:
        queue = list(csv.DictReader(handle))
    assert all(row["primary_reason"] != "missing_sequence" for row in queue)
    assert result.stats.no_review_records == 2


def test_nonmissing_rejects_in_reject_review_batch(tmp_path: Path) -> None:
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    result = _run(repo, checkpoint, output, expected_active=10, expected_total=12)
    with result.output_queue.open(encoding="utf-8", newline="") as handle:
        queue = list(csv.DictReader(handle))
    reject_batch = [row for row in queue if row["review_batch"] == "01_reject_review"]
    assert len(reject_batch) == 2
    assert {row["primary_reason"] for row in reject_batch} == {
        "core_below_minimum",
        "source_record_invalid",
    }


def test_diagnostic_accepts_included(tmp_path: Path) -> None:
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    result = _run(repo, checkpoint, output, expected_active=10, expected_total=12)
    with result.output_queue.open(encoding="utf-8", newline="") as handle:
        queue = list(csv.DictReader(handle))
    accepts = [row for row in queue if row["review_batch"] == "02_accept_with_diagnostics"]
    assert len(accepts) == 1
    assert accepts[0]["proposed_decision"] == "proposed_accept"


def test_clean_no_review_accepts_excluded(tmp_path: Path) -> None:
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    result = _run(repo, checkpoint, output, expected_active=10, expected_total=12)
    with result.output_queue.open(encoding="utf-8", newline="") as handle:
        ids = {row["record_id"] for row in csv.DictReader(handle)}
    assert "aptabase:a0" not in ids


@pytest.mark.parametrize(
    ("primary", "batch"),
    [
        ("molecule_type_unresolved", "03_park_unresolved_molecule"),
        ("ssdna_not_eligible_for_rna_training", "04_park_ssdna"),
        ("invalid_sequence_requires_review", "05_park_invalid_sequence"),
        ("core_above_maximum_requires_review", "06_park_overlength"),
        ("mixed_t_u_requires_review", "07_park_mixed_t_u"),
        ("trim_or_construct_requires_review", "08_park_trim_construct"),
        ("ambiguous_sequence_requires_review", "09_park_ambiguous"),
    ],
)
def test_park_batching(primary: str, batch: str) -> None:
    row = _base_review(
        "aptabase:x",
        decision="proposed_park",
        primary=primary,
        priority="medium",
        required="true",
    )
    assert assign_review_batch(row) == batch


def test_unexpected_primary_reason_fails() -> None:
    row = _base_review(
        "aptabase:bad",
        decision="proposed_park",
        primary="not_a_real_reason",
        priority="medium",
        required="true",
    )
    with pytest.raises(Checkpoint1ReviewError, match="belongs to no batch"):
        assign_review_batch(row)


def test_duplicate_record_id_fails(tmp_path: Path) -> None:
    row = _base_review(
        "aptabase:1",
        decision="proposed_accept",
        primary="technically_eligible_rna",
        priority="low",
        required="true",
    )
    rows = [row, dict(row)]
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    with pytest.raises(Checkpoint1ReviewError, match="Duplicate"):
        _run(repo, checkpoint, output, expected_active=1, expected_total=2)


def test_missing_local_detail_record_fails(tmp_path: Path) -> None:
    rows = [
        _base_review(
            "aptabase:1",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            priority="low",
            required="true",
        ),
        _base_review(
            "aptabase:2",
            decision="proposed_park",
            primary="molecule_type_unresolved",
            priority="medium",
            required="true",
        ),
    ]
    details = [_base_detail(rows[0])]
    repo, checkpoint, output = _make_tree(tmp_path, rows, details)
    with pytest.raises(Checkpoint1ReviewError, match="row counts must match"):
        _run(repo, checkpoint, output, expected_active=2, expected_total=2)


def test_extra_local_detail_record_fails(tmp_path: Path) -> None:
    rows = [
        _base_review(
            "aptabase:1",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            priority="low",
            required="true",
        )
    ]
    extra_review = _base_review(
        "aptabase:2",
        decision="proposed_park",
        primary="molecule_type_unresolved",
        priority="medium",
        required="true",
    )
    details = [_base_detail(rows[0]), _base_detail(extra_review)]
    repo, checkpoint, output = _make_tree(tmp_path, rows, details)
    with pytest.raises(Checkpoint1ReviewError, match="row counts must match"):
        _run(repo, checkpoint, output, expected_active=1, expected_total=1)


def test_queue_has_sequences_index_does_not(tmp_path: Path) -> None:
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    result = _run(repo, checkpoint, output, expected_active=10, expected_total=12)
    queue_fields = list(csv.DictReader(result.output_queue.open()).fieldnames or [])
    index_fields = list(csv.DictReader(result.output_index.open()).fieldnames or [])
    assert queue_fields == list(MANUAL_REVIEW_COLUMNS)
    assert index_fields == list(INDEX_COLUMNS)
    for col in SEQUENCE_COLUMNS:
        assert col in queue_fields
        assert col not in index_fields


def test_sequence_values_copied_exactly(tmp_path: Path) -> None:
    review = _base_review(
        "aptabase:1",
        decision="proposed_accept",
        primary="technically_eligible_rna",
        priority="low",
        required="true",
    )
    clean = _base_review(
        "aptabase:2",
        decision="proposed_accept",
        primary="technically_eligible_rna",
        priority="none",
        required="false",
    )
    details = [
        _base_detail(review, sequence="acguACGU"),
        _base_detail(clean),
    ]
    details[0]["sequence_raw"] = "acguACGU"
    details[0]["sequence_full"] = "ACGUACGU"
    details[0]["sequence_core"] = "ACGU"
    repo, checkpoint, output = _make_tree(tmp_path, [review, clean], details)
    result = _run(repo, checkpoint, output, expected_active=1, expected_total=2)
    with result.output_queue.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["sequence_raw"] == "acguACGU"
    assert row["sequence_full"] == "ACGUACGU"
    assert row["sequence_core"] == "ACGU"


def test_review_fields_initially_empty(tmp_path: Path) -> None:
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    result = _run(repo, checkpoint, output, expected_active=10, expected_total=12)
    with result.output_queue.open(encoding="utf-8", newline="") as handle:
        queue = list(csv.DictReader(handle))
    for row in queue:
        assert row["review_action"] == ""
        assert row["reviewer_note"] == ""
        assert row["reviewer_initials"] == ""


def test_deterministic_review_ordering(tmp_path: Path) -> None:
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    result = _run(repo, checkpoint, output, expected_active=10, expected_total=12)
    with result.output_queue.open(encoding="utf-8", newline="") as handle:
        queue = list(csv.DictReader(handle))
    assert [row["review_order"] for row in queue] == [str(i) for i in range(1, 11)]
    batches = [row["review_batch"] for row in queue]
    assert batches == sorted(batches)
    # Within first reject batch, high priority before low.
    reject = [row for row in queue if row["review_batch"] == "01_reject_review"]
    assert reject[0]["manual_review_priority"] == "high"
    assert reject[1]["manual_review_priority"] == "low"


def test_atomic_write_failure_leaves_no_partial(tmp_path: Path) -> None:
    path = tmp_path / "aptabase_checkpoint1_manual_review.csv"
    path.write_text("prior\n", encoding="utf-8")

    class Broken(dict):
        def get(self, key: str, default: str = "") -> str:  # type: ignore[override]
            if key == "reviewer_note":
                raise RuntimeError("boom")
            return super().get(key, default)

    broken = Broken({column: "" for column in MANUAL_REVIEW_COLUMNS})
    with pytest.raises(RuntimeError, match="boom"):
        write_csv_atomic(path, MANUAL_REVIEW_COLUMNS, [broken])
    assert path.read_text(encoding="utf-8") == "prior\n"
    leftovers = list(tmp_path.glob(".aptabase_checkpoint1_manual_review.csv.*.tmp"))
    assert leftovers == []


def test_byte_identical_rerun(tmp_path: Path) -> None:
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    first = _run(repo, checkpoint, output, expected_active=10, expected_total=12)
    hashes = {
        first.output_queue: _sha256(first.output_queue),
        first.output_index: _sha256(first.output_index),
        first.output_summary: _sha256(first.output_summary),
    }
    second = _run(repo, checkpoint, output, expected_active=10, expected_total=12)
    for path, digest in hashes.items():
        assert _sha256(path) == digest
    assert _sha256(second.output_queue) == hashes[first.output_queue]


def test_running_from_another_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    result = prepare_aptabase_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=Path("data/interim/checkpoints/aptabase_cp1"),
        output_dir=Path("data/interim/checkpoints/aptabase_cp1/manual_review"),
        expected_active_rows=10,
        expected_total_rows=12,
        enforce_expected_batch_counts=False,
    )
    assert result.stats.active_review_rows == 10
    assert result.output_queue.is_file()


def test_no_absolute_paths_or_sequence_printing(tmp_path: Path) -> None:
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        result = _run(repo, checkpoint, output, expected_active=10, expected_total=12)
    combined = (
        stdout.getvalue()
        + stderr.getvalue()
        + result.output_summary.read_text(encoding="utf-8")
        + result.output_index.read_text(encoding="utf-8")
    )
    assert str(repo.resolve()) not in combined
    assert "ACGU" not in combined
    assert "acgu" not in combined


def test_inputs_remain_byte_identical(tmp_path: Path) -> None:
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    hashes = {
        checkpoint / "aptabase_checkpoint1_review.csv": _sha256(
            checkpoint / "aptabase_checkpoint1_review.csv"
        ),
        checkpoint / "aptabase_checkpoint1_local_detail.csv": _sha256(
            checkpoint / "aptabase_checkpoint1_local_detail.csv"
        ),
    }
    _run(repo, checkpoint, output, expected_active=10, expected_total=12)
    for path, digest in hashes.items():
        assert _sha256(path) == digest


def test_summary_counts_reconcile_and_pipeline_stop(tmp_path: Path) -> None:
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    result = _run(repo, checkpoint, output, expected_active=10, expected_total=12)
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "Active review rows: `10`" in summary
    assert "No-review records: `2`" in summary
    assert "Total checkpoint records: `12`" in summary
    assert "No review action has yet been recorded." in summary
    assert "PIPELINE STOP: AptaBase CHECKPOINT-1 remains pending manual review." in summary
    assert "No record is authorised to proceed to S4." in summary
    assert sum(result.stats.batch_counts.values()) == 10


def test_cli_main_aggregate_only(tmp_path: Path) -> None:
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
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
                "data/interim/checkpoints/aptabase_cp1",
                "--output-dir",
                "data/interim/checkpoints/aptabase_cp1/manual_review",
                "--expected-active-rows",
                "10",
                "--expected-total-rows",
                "12",
                "--skip-expected-batch-counts",
            ]
        )
    assert code == 0
    out = stdout.getvalue()
    assert "active_review_rows=10" in out
    assert "ACGU" not in out
    assert "ACGU" not in stderr.getvalue()


def test_no_real_aptabase_data_read_in_tests(tmp_path: Path) -> None:
    # Guard: this suite builds only under tmp_path and never opens repo data/.
    real_checkpoint = (
        REPO_ROOT / "data" / "interim" / "checkpoints" / "aptabase_cp1"
    )
    rows = _fixture_all_batches()
    repo, checkpoint, output = _make_tree(tmp_path, rows)
    before = None
    if real_checkpoint.exists():
        # Not reading contents; only ensure our run targets tmp paths.
        before = real_checkpoint
    result = _run(repo, checkpoint, output, expected_active=10, expected_total=12)
    assert str(tmp_path) in str(result.output_queue)
    assert before is None or result.output_queue != (
        real_checkpoint / "manual_review" / "aptabase_checkpoint1_manual_review.csv"
    )

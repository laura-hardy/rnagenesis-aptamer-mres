"""Tests for the generic S3 classification runner (synthetic fixtures only).

Every literal nucleotide string in this file is shorter than 20 nt except where
length thresholds are tested with strings built at runtime. Does not read real
AptaBase source data or import the legacy cleaner.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptabase import SIDECAR_COLUMNS  # noqa: E402
from adapters.aptabase_s2 import S2_QC_COLUMNS  # noqa: E402
from adapters.aptabase_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    LEAKAGE_MATCH_COLUMNS,
    LOCAL_DETAIL_COLUMNS,
)
from common.corpus_schema import CORPUS_COLUMNS, empty_corpus_record  # noqa: E402
from common.leakage_matching import comparison_form  # noqa: E402
from s3_classify import (  # noqa: E402
    S3ClassifyError,
    main,
    run_aptabase_s3,
    run_s3_classification,
    write_csv_atomic,
)

POLICY_PATH = REPO_ROOT / "config" / "source_eligibility" / "aptabase.json"
ALIASES_PATH = REPO_ROOT / "config" / "leakage_target_aliases.csv"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _s2_row(
    native_id: str,
    sequence: str,
    *,
    molecule_type: str = "RNA",
    alphabet: str = "RNA",
    target: str = "demo_target",
    qc_flags: str = "",
    trim_status: str = "not_trimmed",
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"aptabase:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": (
                "missing" if sequence == "" else "full_equals_core_untrimmed"
            ),
            "trim_status": "not_applicable" if sequence == "" else trim_status,
            "molecule_type": "unknown" if sequence == "" else molecule_type,
            "alphabet_as_reported": "missing" if sequence == "" else alphabet,
            "t_to_u_applied": "false",
            "target_name_raw": target,
            "source_db": "aptabase",
            "source_dataset": "demo_ds",
            "contributing_sources": "aptabase",
            "contributing_datasets": "demo_ds",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "publication": "Demo",
            "qc_flags": qc_flags,
            "notes": json.dumps(
                {"aptamer_name": f"name-{native_id}"}, separators=(",", ":")
            ),
        }
    )
    return record


def _qc_row(canonical: dict[str, str]) -> dict[str, str]:
    row = {column: "" for column in S2_QC_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "aptamer_name": f"name-{canonical['native_id']}",
            "target_name_raw": canonical["target_name_raw"],
            "alphabet_as_reported": canonical["alphabet_as_reported"],
            "molecule_type": canonical["molecule_type"],
            "t_to_u_applied": canonical["t_to_u_applied"],
            "sequence_length_full": canonical["sequence_length_full"],
            "sequence_length_core": canonical["sequence_length_core"],
            "reported_length_raw": canonical["sequence_length_full"],
            "reported_length_difference": "0",
            "gc_reported_raw": "50",
            "gc_calculated_s2": "50.0",
            "gc_difference_percentage_points": "0.0",
            "construct_scope": canonical["construct_scope"],
            "trim_status": canonical["trim_status"],
            "qc_flags": canonical["qc_flags"],
        }
    )
    return row


def _meta_row(canonical: dict[str, str], **overrides: str) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "aptabase_record_id": canonical["native_id"],
            "aptabase_aptamer_name": f"name-{canonical['native_id']}",
            "aptabase_target_general": canonical["target_name_raw"],
            "aptabase_target_specific": f"specific-{canonical['native_id']}",
            "aptabase_sequence_raw": canonical["sequence_raw"],
            "aptabase_record_validity": "valid",
            "aptabase_parse_warnings": "",
        }
    )
    row.update(overrides)
    return row


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _write_leakage(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "exclusion_id",
        "reference_id",
        "target_name",
        "evaluation_role",
        "sequence_compare_full",
        "sequence_compare_core",
        "status",
    ]
    _write_csv(path, fieldnames, rows)


def _make_tree(
    tmp_path: Path,
    *,
    n_rows: int = 3,
    include_missing: bool = True,
    leak_first: bool = False,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    repo_root = tmp_path / "repo"
    input_dir = repo_root / "data" / "interim" / "normalised"
    meta_dir = repo_root / "data" / "interim" / "extracted"
    output_dir = repo_root / "data" / "interim" / "checkpoints" / "aptabase_cp1"
    leakage_path = repo_root / "data" / "interim" / "leakage_exclusion_set.csv"
    aliases_path = ALIASES_PATH

    canonical_rows: list[dict[str, str]] = []
    qc_rows: list[dict[str, str]] = []
    meta_rows: list[dict[str, str]] = []
    for i in range(1, n_rows + 1):
        if include_missing and i == n_rows:
            seq = ""
            mol, alph, target = "unknown", "missing", ""
        elif i == 1:
            seq = _rna(25)
            mol, alph, target = "RNA", "RNA", "demo_target"
        else:
            seq = _rna(30)
            mol, alph, target = "ssDNA", "DNA_T", "other_target"
            seq = ("ACGT" * 10)[:30]
        row = _s2_row(
            str(i),
            seq,
            molecule_type=mol,
            alphabet=alph,
            target=target,
        )
        canonical_rows.append(row)
        qc_rows.append(_qc_row(row))
        meta_rows.append(_meta_row(row))

    _write_csv(input_dir / "aptabase_normalised.csv", list(CORPUS_COLUMNS), canonical_rows)
    _write_csv(input_dir / "aptabase_s2_qc.csv", list(S2_QC_COLUMNS), qc_rows)
    _write_csv(meta_dir / "aptabase_source_metadata.csv", list(SIDECAR_COLUMNS), meta_rows)

    leak_rows: list[dict[str, str]] = []
    if leak_first:
        seq = canonical_rows[0]["sequence_full"]
        cmp = comparison_form(seq)
        leak_rows.append(
            {
                "exclusion_id": "ex1",
                "reference_id": "ref1",
                "target_name": "NDM-1",
                "evaluation_role": "positive",
                "sequence_compare_full": cmp,
                "sequence_compare_core": cmp,
                "status": "resolved",
            }
        )
    else:
        # Harmless non-matching short exclusion entry.
        leak_rows.append(
            {
                "exclusion_id": "ex_none",
                "reference_id": "ref_none",
                "target_name": "NDM-1",
                "evaluation_role": "positive",
                "sequence_compare_full": "AAAA",
                "sequence_compare_core": "AAAA",
                "status": "resolved",
            }
        )
    _write_leakage(leakage_path, leak_rows)
    return repo_root, input_dir, meta_dir, output_dir, leakage_path, aliases_path


def test_42_45_46_canonical_unchanged_and_later_fields_empty(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=3)
    before = _sha256(input_dir / "aptabase_normalised.csv")
    result = run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=3,
    )
    assert _sha256(result.output_canonical) == before
    assert _sha256(input_dir / "aptabase_normalised.csv") == before
    with result.output_canonical.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    forbidden = {
        "chemistry",
        "target_name",
        "target_uniprot",
        "binding_evidence_score",
        "cluster_id",
        "partition",
    }
    for row in rows:
        for field in forbidden:
            assert row[field] == ""


def test_42_43_44_review_ordering_and_no_sequences(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=3)
    result = run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=3,
    )
    with result.output_review.open(encoding="utf-8", newline="") as handle:
        review = list(csv.DictReader(handle))
        fieldnames = list(handle.fieldnames or []) if False else list(DECISION_COLUMNS)
    assert len(review) == 3
    assert list(csv.DictReader(result.output_review.open()).fieldnames) == list(
        DECISION_COLUMNS
    )
    for col in ("sequence_raw", "sequence_full", "sequence_core"):
        assert col not in fieldnames
    priorities = [row["manual_review_priority"] for row in review]
    order = {"high": 0, "medium": 1, "low": 2, "none": 3}
    assert priorities == sorted(priorities, key=lambda p: order[p])


def test_47_48_reason_and_leakage_counts_reconcile(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(
        tmp_path, n_rows=3, leak_first=True
    )
    result = run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=3,
    )
    with result.output_reason_counts.open(encoding="utf-8", newline="") as handle:
        reason_rows = list(csv.DictReader(handle))
    total = sum(int(row["record_count"]) for row in reason_rows)
    assert total == 3
    with result.output_leakage_matches.open(encoding="utf-8", newline="") as handle:
        leak_rows = list(csv.DictReader(handle))
    assert sum(1 for row in leak_rows if row["match_scope"] == "sequence") == (
        result.stats.sequence_leakage_count
    )
    for row in leak_rows:
        for col in LEAKAGE_MATCH_COLUMNS:
            assert col in row
        assert "ACGU" not in "".join(row.values())


def test_49_50_atomic_and_deterministic_rerun(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=3)
    first = run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=3,
    )
    paths = [
        first.output_canonical,
        first.output_decisions,
        first.output_review,
        first.output_local_detail,
        first.output_reason_counts,
        first.output_leakage_matches,
        first.output_summary,
    ]
    hashes = {path: _sha256(path) for path in paths}
    second = run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=3,
    )
    for path, digest in hashes.items():
        assert _sha256(path) == digest
    assert _sha256(second.output_canonical) == hashes[first.output_canonical]
    assert _sha256(second.output_local_detail) == hashes[first.output_local_detail]
    assert _sha256(second.output_summary) == hashes[first.output_summary]


def test_50_deterministic_rerun_flag(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=2)
    result = run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=2,
        check_deterministic_rerun=True,
    )
    assert result.deterministic_rerun_ok is True


def test_51_running_from_another_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=2)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    result = run_aptabase_s3(
        repo_root=repo,
        input_dir=Path("data/interim/normalised"),
        source_metadata_dir=Path("data/interim/extracted"),
        leakage_set=Path("data/interim/leakage_exclusion_set.csv"),
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=Path("data/interim/checkpoints/aptabase_cp1"),
        expected_rows=2,
    )
    assert result.stats.s3_rows == 2
    assert result.output_canonical.is_file()


def test_52_53_no_absolute_paths_or_sequence_printing(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=2)
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        result = run_aptabase_s3(
            repo_root=repo,
            input_dir=input_dir,
            source_metadata_dir=meta_dir,
            leakage_set=leak,
            target_aliases=aliases,
            eligibility_policy=POLICY_PATH,
            output_dir=out_dir,
            expected_rows=2,
        )
    text = stdout.getvalue() + result.output_summary.read_text(encoding="utf-8")
    assert str(repo.resolve()) not in text
    assert "ACGU" not in text
    assert "ACGT" not in text


def test_55_inputs_remain_byte_identical(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=2)
    hashes = {
        input_dir / "aptabase_normalised.csv": _sha256(
            input_dir / "aptabase_normalised.csv"
        ),
        input_dir / "aptabase_s2_qc.csv": _sha256(input_dir / "aptabase_s2_qc.csv"),
        meta_dir / "aptabase_source_metadata.csv": _sha256(
            meta_dir / "aptabase_source_metadata.csv"
        ),
    }
    run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=2,
    )
    for path, digest in hashes.items():
        assert _sha256(path) == digest


def test_56_unknown_source_adapter_rejected(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=1)
    with pytest.raises(S3ClassifyError, match="Unknown S3 source_key"):
        run_s3_classification(
            repo_root=repo,
            source_key="riboaptamer",
            input_dir=input_dir,
            source_metadata_dir=meta_dir,
            leakage_set=leak,
            target_aliases=aliases,
            eligibility_policy=POLICY_PATH,
            output_dir=out_dir,
            expected_rows=1,
        )


def test_57_missing_sidecar_row_fails(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=2)
    meta_path = meta_dir / "aptabase_source_metadata.csv"
    rows = list(csv.DictReader(meta_path.open(encoding="utf-8", newline="")))
    _write_csv(meta_path, list(SIDECAR_COLUMNS), rows[:1])
    with pytest.raises(S3ClassifyError, match="row counts must match"):
        run_aptabase_s3(
            repo_root=repo,
            input_dir=input_dir,
            source_metadata_dir=meta_dir,
            leakage_set=leak,
            target_aliases=aliases,
            eligibility_policy=POLICY_PATH,
            output_dir=out_dir,
            expected_rows=2,
        )


def test_58_extra_sidecar_row_fails(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=1)
    meta_path = meta_dir / "aptabase_source_metadata.csv"
    rows = list(csv.DictReader(meta_path.open(encoding="utf-8", newline="")))
    extra = dict(rows[0])
    extra["record_id"] = "aptabase:999"
    extra["aptabase_record_id"] = "999"
    _write_csv(meta_path, list(SIDECAR_COLUMNS), rows + [extra])
    with pytest.raises(S3ClassifyError, match="row counts must match"):
        run_aptabase_s3(
            repo_root=repo,
            input_dir=input_dir,
            source_metadata_dir=meta_dir,
            leakage_set=leak,
            target_aliases=aliases,
            eligibility_policy=POLICY_PATH,
            output_dir=out_dir,
            expected_rows=1,
        )


def test_59_duplicate_sidecar_row_fails(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=1)
    # Keep counts matched but duplicate IDs via QC file.
    qc_path = input_dir / "aptabase_s2_qc.csv"
    rows = list(csv.DictReader(qc_path.open(encoding="utf-8", newline="")))
    _write_csv(qc_path, list(S2_QC_COLUMNS), rows + rows)
    # Also duplicate canonical to keep counts equal, then fail on duplicate id.
    can_path = input_dir / "aptabase_normalised.csv"
    can_rows = list(csv.DictReader(can_path.open(encoding="utf-8", newline="")))
    _write_csv(can_path, list(CORPUS_COLUMNS), can_rows + can_rows)
    meta_path = meta_dir / "aptabase_source_metadata.csv"
    meta_rows = list(csv.DictReader(meta_path.open(encoding="utf-8", newline="")))
    _write_csv(meta_path, list(SIDECAR_COLUMNS), meta_rows + meta_rows)
    with pytest.raises(S3ClassifyError, match="Duplicate"):
        run_aptabase_s3(
            repo_root=repo,
            input_dir=input_dir,
            source_metadata_dir=meta_dir,
            leakage_set=leak,
            target_aliases=aliases,
            eligibility_policy=POLICY_PATH,
            output_dir=out_dir,
            expected_rows=2,
        )


def test_cli_main_aggregate_only(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=2)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "aptabase",
                "--repo-root",
                str(repo),
                "--input-dir",
                "data/interim/normalised",
                "--source-metadata-dir",
                "data/interim/extracted",
                "--leakage-set",
                "data/interim/leakage_exclusion_set.csv",
                "--target-aliases",
                str(aliases),
                "--eligibility-policy",
                str(POLICY_PATH),
                "--output-dir",
                "data/interim/checkpoints/aptabase_cp1",
                "--expected-rows",
                "2",
            ]
        )
    assert code == 0
    out = stdout.getvalue()
    assert "s3_rows=2" in out
    assert "ACGU" not in out
    assert "PIPELINE STOP" in (
        out_dir / "aptabase_checkpoint1_summary.md"
    ).read_text(encoding="utf-8")


def test_local_detail_contains_all_records_and_matches_review_order(
    tmp_path: Path,
) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=3)
    result = run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=3,
    )
    with result.output_local_detail.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert list(reader.fieldnames or []) == list(LOCAL_DETAIL_COLUMNS)
        detail = list(reader)
    with result.output_review.open(encoding="utf-8", newline="") as handle:
        review = list(csv.DictReader(handle))
    assert len(detail) == 3
    assert len(review) == 3
    assert [row["record_id"] for row in detail] == [
        row["record_id"] for row in review
    ]


def test_local_detail_has_sequences_review_does_not(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=3)
    result = run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=3,
    )
    review_fields = list(csv.DictReader(result.output_review.open()).fieldnames or [])
    detail_fields = list(
        csv.DictReader(result.output_local_detail.open()).fieldnames or []
    )
    for col in ("sequence_raw", "sequence_full", "sequence_core"):
        assert col not in review_fields
        assert col in detail_fields
        assert col not in DECISION_COLUMNS


def test_local_detail_preserves_source_and_canonical_sequences(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=3)
    # Use an exact short source sequence distinct from a cleaned form.
    can_path = input_dir / "aptabase_normalised.csv"
    meta_path = meta_dir / "aptabase_source_metadata.csv"
    can_rows = list(csv.DictReader(can_path.open(encoding="utf-8", newline="")))
    meta_rows = list(csv.DictReader(meta_path.open(encoding="utf-8", newline="")))
    source_raw = "acguACGU"
    can_rows[0]["sequence_raw"] = source_raw
    can_rows[0]["sequence_full"] = "ACGUACGU"
    can_rows[0]["sequence_core"] = "ACGUAC"
    can_rows[0]["sequence_length_full"] = "8"
    can_rows[0]["sequence_length_core"] = "6"
    can_rows[0]["molecule_type"] = "RNA"
    can_rows[0]["alphabet_as_reported"] = "RNA"
    can_rows[0]["construct_scope"] = "full_equals_core_untrimmed"
    can_rows[0]["trim_status"] = "not_trimmed"
    can_rows[0]["qc_flags"] = "core_below_min_length"
    meta_rows[0]["aptabase_sequence_raw"] = source_raw
    meta_rows[0]["aptabase_target_general"] = "general-A"
    meta_rows[0]["aptabase_target_specific"] = "specific-A"
    _write_csv(can_path, list(CORPUS_COLUMNS), can_rows)
    _write_csv(meta_path, list(SIDECAR_COLUMNS), meta_rows)
    qc_path = input_dir / "aptabase_s2_qc.csv"
    qc_rows = list(csv.DictReader(qc_path.open(encoding="utf-8", newline="")))
    qc_rows[0]["sequence_length_full"] = "8"
    qc_rows[0]["sequence_length_core"] = "6"
    qc_rows[0]["molecule_type"] = "RNA"
    qc_rows[0]["alphabet_as_reported"] = "RNA"
    qc_rows[0]["qc_flags"] = "core_below_min_length"
    _write_csv(qc_path, list(S2_QC_COLUMNS), qc_rows)

    result = run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=3,
    )
    with result.output_local_detail.open(encoding="utf-8", newline="") as handle:
        detail_by_id = {row["record_id"]: row for row in csv.DictReader(handle)}
    with result.output_decisions.open(encoding="utf-8", newline="") as handle:
        decisions_by_id = {row["record_id"]: row for row in csv.DictReader(handle)}
    row = detail_by_id["aptabase:1"]
    assert row["sequence_raw"] == source_raw
    assert row["sequence_full"] == "ACGUACGU"
    assert row["sequence_core"] == "ACGUAC"
    assert row["target_general_raw"] == "general-A"
    assert row["target_specific_raw"] == "specific-A"
    decision = decisions_by_id["aptabase:1"]
    assert row["proposed_decision"] == decision["proposed_decision"]
    assert row["primary_reason"] == decision["primary_reason"]
    assert row["secondary_reasons"] == decision["secondary_reasons"]
    assert row["manual_review_required"] == decision["manual_review_required"]
    assert row["manual_review_priority"] == decision["manual_review_priority"]


def test_local_detail_missing_sequence_remains_empty(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=3)
    result = run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=3,
    )
    with result.output_local_detail.open(encoding="utf-8", newline="") as handle:
        detail = list(csv.DictReader(handle))
    missing = [row for row in detail if row["primary_reason"] == "missing_sequence"]
    assert missing
    for row in missing:
        assert row["sequence_raw"] == ""
        assert row["sequence_full"] == ""
        assert row["sequence_core"] == ""


def test_local_detail_deterministic_no_paths_under_output_dir(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=3)
    first = run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=3,
    )
    digest = _sha256(first.output_local_detail)
    text = first.output_local_detail.read_text(encoding="utf-8")
    assert str(repo.resolve()) not in text
    assert str(out_dir.resolve()) not in text
    assert first.output_local_detail.parent == out_dir.resolve() or (
        first.output_local_detail.parent == out_dir
    )
    second = run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=3,
    )
    assert _sha256(second.output_local_detail) == digest


def test_local_detail_atomic_write_failure_leaves_no_partial(tmp_path: Path) -> None:
    path = tmp_path / "aptabase_checkpoint1_local_detail.csv"
    path.write_text("prior\n", encoding="utf-8")

    class Broken(dict):
        def get(self, key: str, default: str = "") -> str:  # type: ignore[override]
            if key == "notes":
                raise RuntimeError("boom")
            return super().get(key, default)

    broken = Broken({column: "" for column in LOCAL_DETAIL_COLUMNS})
    with pytest.raises(RuntimeError, match="boom"):
        write_csv_atomic(path, LOCAL_DETAIL_COLUMNS, [broken])
    assert path.read_text(encoding="utf-8") == "prior\n"
    leftovers = list(tmp_path.glob(".aptabase_checkpoint1_local_detail.csv.*.tmp"))
    assert leftovers == []


def test_local_detail_no_sequence_printed_and_inputs_unchanged(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=2)
    hashes = {
        input_dir / "aptabase_normalised.csv": _sha256(
            input_dir / "aptabase_normalised.csv"
        ),
        input_dir / "aptabase_s2_qc.csv": _sha256(input_dir / "aptabase_s2_qc.csv"),
        meta_dir / "aptabase_source_metadata.csv": _sha256(
            meta_dir / "aptabase_source_metadata.csv"
        ),
    }
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        result = run_aptabase_s3(
            repo_root=repo,
            input_dir=input_dir,
            source_metadata_dir=meta_dir,
            leakage_set=leak,
            target_aliases=aliases,
            eligibility_policy=POLICY_PATH,
            output_dir=out_dir,
            expected_rows=2,
        )
    combined = stdout.getvalue() + stderr.getvalue()
    assert "ACGU" not in combined
    assert "ACGT" not in combined
    assert result.output_local_detail.is_file()
    for path, digest in hashes.items():
        assert _sha256(path) == digest


def test_summary_mentions_local_detail_and_manual_review_queue(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir, leak, aliases = _make_tree(tmp_path, n_rows=3)
    result = run_aptabase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=leak,
        target_aliases=aliases,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=3,
    )
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "aptabase_checkpoint1_local_detail.csv" in summary
    assert "manual_review_required=true" in summary
    assert "manual_review_required=false" in summary
    assert "Mechanical missing-sequence rejects excluded" in summary
    assert "must never be staged or tracked" in summary
    assert "PIPELINE STOP: AptaBase CHECKPOINT-1 is awaiting manual review." in summary
    assert "ACGU" not in summary
    assert "ACGT" not in summary

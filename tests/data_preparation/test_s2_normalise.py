"""Tests for the generic S2 normalisation runner (synthetic fixtures only).

Every literal nucleotide string in this file is shorter than 20 nt.
Does not read real AptaBase source data or import the legacy cleaner.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptabase import SIDECAR_COLUMNS  # noqa: E402
from adapters.aptabase_s2 import S2_QC_COLUMNS  # noqa: E402
from common.corpus_schema import CORPUS_COLUMNS, empty_corpus_record  # noqa: E402
from s2_normalise import (  # noqa: E402
    S2NormaliseError,
    run_aptabase_s2,
    run_s2_normalisation,
)


POLICY_PATH = REPO_ROOT / "config" / "source_normalisation" / "aptabase.json"
RULES_PATH = REPO_ROOT / "config" / "sequence_normalisation_rules.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _s1_row(native_id: str, sequence_raw: str = "ACGUAC") -> dict[str, str]:
    record = empty_corpus_record()
    record.update(
        {
            "record_id": f"aptabase:{native_id}",
            "sequence_raw": sequence_raw,
            "source_db": "aptabase",
            "source_dataset": "demo_ds",
            "contributing_sources": "aptabase",
            "contributing_datasets": "demo_ds",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "target_name_raw": "demo_target",
            "publication": "Demo",
            "notes": json.dumps(
                {"aptamer_name": f"name-{native_id}"},
                separators=(",", ":"),
            ),
        }
    )
    return record


def _sidecar_row(native_id: str, **overrides: str) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row["record_id"] = f"aptabase:{native_id}"
    row["aptabase_record_id"] = native_id
    row["aptabase_aptamer_name"] = f"name-{native_id}"
    row["aptabase_sequence_raw"] = overrides.pop(
        "aptabase_sequence_raw", "ACGUAC"
    )
    row.update(overrides)
    return row


def _write_inputs(
    input_dir: Path,
    canonical_rows: list[dict[str, str]],
    sidecar_rows: list[dict[str, str]],
) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    with (input_dir / "aptabase_extracted.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(CORPUS_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        for row in canonical_rows:
            writer.writerow({col: row.get(col, "") for col in CORPUS_COLUMNS})
    with (input_dir / "aptabase_source_metadata.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(SIDECAR_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        for row in sidecar_rows:
            writer.writerow({col: row.get(col, "") for col in SIDECAR_COLUMNS})


def _make_pair(
    tmp_path: Path,
    n_rows: int = 3,
    *,
    include_missing: bool = True,
) -> tuple[Path, Path, Path]:
    """Return ``(repo_root, input_dir, output_dir)`` under a synthetic tree."""
    repo_root = tmp_path / "repo"
    input_dir = repo_root / "data" / "interim" / "extracted"
    output_dir = repo_root / "data" / "interim" / "normalised"
    canonical: list[dict[str, str]] = []
    sidecar: list[dict[str, str]] = []
    for i in range(1, n_rows + 1):
        seq = "" if (include_missing and i == n_rows) else "ACGUAC"
        canonical.append(_s1_row(str(i), seq))
        sidecar.append(
            _sidecar_row(
                str(i),
                aptabase_sequence_raw=seq,
                aptabase_aptamer_name=(
                    "RNA aptamer demo" if i == 1 else f"name-{i}"
                ),
            )
        )
    _write_inputs(input_dir, canonical, sidecar)
    return repo_root, input_dir, output_dir


def test_42_one_to_one_canonical_sidecar_matching(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(tmp_path, n_rows=3)
    result = run_aptabase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=3,
    )
    assert result.stats.s1_rows == 3
    assert result.stats.s2_rows == 3
    assert result.stats.source_metadata_rows == 3


def test_43_missing_sidecar_record_fails(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(tmp_path, n_rows=2)
    rows = list(csv.DictReader((input_dir / "aptabase_source_metadata.csv").open()))
    _write_inputs(
        input_dir,
        [_s1_row("1"), _s1_row("2")],
        [rows[0]],
    )
    with pytest.raises(S2NormaliseError, match="row counts|Missing"):
        run_aptabase_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=RULES_PATH,
            policy_path=POLICY_PATH,
            expected_rows=2,
        )


def test_44_extra_sidecar_record_fails(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(tmp_path, n_rows=1)
    _write_inputs(
        input_dir,
        [_s1_row("1")],
        [_sidecar_row("1"), _sidecar_row("2")],
    )
    with pytest.raises(S2NormaliseError, match="row counts|Extra"):
        run_aptabase_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=RULES_PATH,
            policy_path=POLICY_PATH,
            expected_rows=1,
        )


def test_45_duplicate_sidecar_record_fails(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(tmp_path, n_rows=2)
    _write_inputs(
        input_dir,
        [_s1_row("1"), _s1_row("2")],
        [_sidecar_row("1"), _sidecar_row("1")],
    )
    with pytest.raises(S2NormaliseError, match="Duplicate"):
        run_aptabase_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=RULES_PATH,
            policy_path=POLICY_PATH,
            expected_rows=2,
        )


def test_46_input_order_preserved(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(
        tmp_path, n_rows=4, include_missing=False
    )
    result = run_aptabase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=4,
    )
    with result.output_normalised.open(encoding="utf-8", newline="") as handle:
        out_ids = [row["record_id"] for row in csv.DictReader(handle)]
    assert out_ids == [f"aptabase:{i}" for i in range(1, 5)]
    assert result.stats.order_preserved is True


def test_47_configurable_synthetic_row_count(tmp_path: Path) -> None:
    for n in (1, 2, 5):
        nested = tmp_path / f"n{n}"
        repo_root, input_dir, output_dir = _make_pair(
            nested, n_rows=n, include_missing=False
        )
        result = run_aptabase_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=RULES_PATH,
            policy_path=POLICY_PATH,
            expected_rows=n,
        )
        assert result.stats.s2_rows == n


def test_48_later_stage_fields_rejected(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(
        tmp_path, n_rows=1, include_missing=False
    )
    result = run_aptabase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=1,
    )
    with result.output_normalised.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    for field in (
        "chemistry",
        "target_name",
        "affinity_value",
        "experiment_group_id",
        "cluster_id",
        "partition",
    ):
        assert row[field] == ""


def test_49_qc_output_has_no_sequence_columns(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(tmp_path, n_rows=2)
    result = run_aptabase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
    )
    with result.output_qc.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert list(reader.fieldnames or []) == list(S2_QC_COLUMNS)
        assert "sequence_raw" not in (reader.fieldnames or [])
        assert "sequence_full" not in (reader.fieldnames or [])
        assert "sequence_core" not in (reader.fieldnames or [])


def test_50_review_file_only_flagged_rows(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(tmp_path, n_rows=2)
    result = run_aptabase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
    )
    with result.output_review.open(encoding="utf-8", newline="") as handle:
        review_rows = list(csv.DictReader(handle))
    assert review_rows
    for row in review_rows:
        assert row["qc_flags"]


def test_51_empty_constant_proposal_output(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(tmp_path, n_rows=2)
    result = run_aptabase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
    )
    text = result.output_proposals.read_text(encoding="utf-8")
    lines = text.strip().splitlines()
    assert len(lines) == 1
    assert result.stats.constant_region_proposals == 0


def test_52_missing_group_ids_not_pooled(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(
        tmp_path, n_rows=5, include_missing=False
    )
    result = run_aptabase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=5,
    )
    assert result.stats.records_with_experiment_group_id == 0
    assert result.stats.eligible_groups == 0
    assert result.stats.constant_region_reason == "no_experiment_group_id"


def test_53_atomic_output_writing(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(tmp_path, n_rows=2)
    result = run_aptabase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
    )
    leftovers = list(output_dir.glob(".*.tmp"))
    assert leftovers == []
    assert result.output_normalised.exists()


def test_54_deterministic_rerun(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(tmp_path, n_rows=3)
    first = run_aptabase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=3,
    )
    h1 = {
        "n": _sha256(first.output_normalised),
        "q": _sha256(first.output_qc),
        "r": _sha256(first.output_review),
        "p": _sha256(first.output_proposals),
        "m": _sha256(first.output_report),
    }
    second = run_aptabase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=3,
    )
    assert _sha256(second.output_normalised) == h1["n"]
    assert _sha256(second.output_qc) == h1["q"]
    assert _sha256(second.output_review) == h1["r"]
    assert _sha256(second.output_proposals) == h1["p"]
    assert _sha256(second.output_report) == h1["m"]


def test_55_running_from_another_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, input_dir, output_dir = _make_pair(tmp_path, n_rows=2)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    result = run_s2_normalisation(
        repo_root=repo_root,
        source_key="aptabase",
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        source_policy=POLICY_PATH,
        expected_rows=2,
    )
    assert result.stats.s2_rows == 2


def test_56_no_absolute_path_in_outputs(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(tmp_path, n_rows=2)
    result = run_aptabase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
    )
    abs_root = str(repo_root.resolve())
    report = result.output_report.read_text(encoding="utf-8")
    assert abs_root not in report
    qc_text = result.output_qc.read_text(encoding="utf-8")
    assert abs_root not in qc_text


def test_57_no_source_sequence_printed(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(
        tmp_path, n_rows=1, include_missing=False
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_aptabase_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=RULES_PATH,
            policy_path=POLICY_PATH,
            expected_rows=1,
        )
    printed = buf.getvalue()
    assert "ACGUAC" not in printed


def test_58_no_real_source_data_read_by_tests(tmp_path: Path) -> None:
    # Synthetic fixture paths only; real raw cleaned CSV is never opened here.
    real = REPO_ROOT / "data" / "raw" / "aptabase" / "aptabase_cleaned.csv"
    before = _sha256(real) if real.exists() else None
    repo_root, input_dir, output_dir = _make_pair(tmp_path, n_rows=2)
    run_aptabase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
    )
    if before is not None:
        assert _sha256(real) == before


def test_59_no_import_of_legacy_cleaner() -> None:
    assert "aptabase_cleaning" not in sys.modules
    import adapters.aptabase_s2 as mod

    assert "aptabase_cleaning" not in sys.modules
    assert not hasattr(mod, "clean_sequence")


def test_60_input_files_remain_byte_identical(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _make_pair(tmp_path, n_rows=2)
    c_path = input_dir / "aptabase_extracted.csv"
    s_path = input_dir / "aptabase_source_metadata.csv"
    before_c = _sha256(c_path)
    before_s = _sha256(s_path)
    result = run_aptabase_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
    )
    assert _sha256(c_path) == before_c
    assert _sha256(s_path) == before_s
    assert result.inputs_unchanged is True

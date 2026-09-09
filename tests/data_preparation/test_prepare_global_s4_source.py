"""Tests for global-S4 source handoff preparation (synthetic only).

Every literal nucleotide string in this file is shorter than 20 nt. Does not
read real AptaBase checkpoint or raw source data.
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

from common.corpus_schema import CORPUS_COLUMNS  # noqa: E402
from prepare_global_s4_source import (  # noqa: E402
    HANDOFF_CLOSED_STATEMENT,
    GlobalS4HandoffError,
    load_source_config,
    main,
    prepare_global_s4_source,
)

SEQ_LEAK_RE = re.compile(r"[ACGTUacgtu]{20,}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _empty_corpus(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in CORPUS_COLUMNS}
    row.update(overrides)
    return row


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


RESOLUTION_COLUMNS = [
    "record_id",
    "proposed_decision",
    "resolved_decision",
    "checkpoint1_resolution_status",
    "authorised_for_s4",
]

AUTH_ID_COLUMNS = [
    "record_id",
    "resolved_decision",
    "checkpoint1_resolution_status",
]


def _base_records() -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    """Return canonical rows, resolution rows, and authorised ID order."""
    # Mix of accept/park/reject; two accepts authorised.
    specs = [
        ("src:a1", "accept", "approved_for_s4", "true", "ACGUACGU", "Target A"),
        ("src:r1", "reject", "rejected_after_checkpoint1", "false", "GGCCGGCC", "Target R"),
        ("src:a2", "accept", "approved_for_s4", "true", "UUGGAACC", "Target B"),
        ("src:p1", "park", "parked_after_checkpoint1", "false", "AAUUGGCC", "Target P"),
        ("src:a3", "accept", "approved_for_s4", "false", "CCGGAAUU", "Target C"),
    ]
    canonical: list[dict[str, str]] = []
    resolutions: list[dict[str, str]] = []
    authorised: list[str] = []
    for record_id, resolved, status, auth, seq, target in specs:
        canonical.append(
            _empty_corpus(
                record_id=record_id,
                sequence_raw=seq,
                sequence_full=seq,
                sequence_core=seq,
                sequence_length_full=str(len(seq)),
                sequence_length_core=str(len(seq)),
                molecule_type="RNA",
                alphabet_as_reported="RNA",
                t_to_u_applied="false",
                target_name_raw=target,
                target_name="",
                target_type="",
                target_uniprot="",
                source_db="demo",
                source_dataset="demo_set",
                contributing_sources="demo",
                contributing_datasets="demo_set",
                corroboration_count="1",
                redistribution_status="unknown",
                independently_attested_by_permissive_source="false",
                native_id=record_id.split(":")[-1],
            )
        )
        resolutions.append(
            {
                "record_id": record_id,
                "proposed_decision": f"proposed_{resolved}",
                "resolved_decision": resolved,
                "checkpoint1_resolution_status": status,
                "authorised_for_s4": auth,
            }
        )
        if auth == "true":
            authorised.append(record_id)
    return canonical, resolutions, authorised


def _make_tree(
    tmp_path: Path,
    *,
    expected: int | None = None,
    source_key: str = "demo",
) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "config" / "global_s4_sources").mkdir(parents=True)
    (repo / "config" / "checkpoint_reviews").mkdir(parents=True)
    (repo / "data" / "interim" / "checkpoints" / "demo_cp1" / "resolved").mkdir(
        parents=True
    )
    (repo / "data" / "interim" / "global_s4_ready").mkdir(parents=True)
    (repo / "data" / "raw" / "demo").mkdir(parents=True)
    (repo / "data" / "raw" / "demo" / "raw.csv").write_text(
        "record_id,sequence\nraw:1,ACGU\n",
        encoding="utf-8",
    )

    canonical, resolutions, authorised = _base_records()
    if expected is None:
        expected = len(authorised)

    canon_path = repo / "data/interim/checkpoints/demo_cp1/demo_s3_canonical.csv"
    res_path = repo / "config/checkpoint_reviews/demo_checkpoint1_resolutions.csv"
    auth_path = (
        repo / "data/interim/checkpoints/demo_cp1/resolved/demo_s4_authorised_ids.csv"
    )
    _write_csv(canon_path, list(CORPUS_COLUMNS), canonical)
    _write_csv(res_path, RESOLUTION_COLUMNS, resolutions)
    auth_rows = [
        {
            "record_id": record_id,
            "resolved_decision": "accept",
            "checkpoint1_resolution_status": "approved_for_s4",
        }
        for record_id in authorised
    ]
    _write_csv(auth_path, AUTH_ID_COLUMNS, auth_rows)

    config = {
        "source_key": source_key,
        "handoff_status": "ready_for_global_s4",
        "authoritative_stage": "CHECKPOINT-1",
        "checkpoint_status": "closed",
        "canonical_input": "data/interim/checkpoints/demo_cp1/demo_s3_canonical.csv",
        "resolution_manifest": "config/checkpoint_reviews/demo_checkpoint1_resolutions.csv",
        "authorised_ids_input": (
            "data/interim/checkpoints/demo_cp1/resolved/demo_s4_authorised_ids.csv"
        ),
        "authorisation_field": "authorised_for_s4",
        "expected_authorised_records": expected,
        "global_s4_handoff_output": "data/interim/global_s4_ready/demo_global_s4_input.csv",
        "global_s4_handoff_summary": (
            "data/interim/global_s4_ready/demo_global_s4_handoff_summary.md"
        ),
        "target_metadata": {
            "canonical_raw_field": "target_name_raw",
            "source_specific_field": "demo_target_specific",
            "source_general_field": "demo_target_general",
            "source_general_is_categorical": True,
            "specific_target_present_in_authorised_records": expected,
            "specific_target_missing_in_authorised_records": 0,
        },
        "provisional_source_observations": {
            "Protein": 1,
            "Peptide": 1,
        },
        "global_s4_rules": {
            "final_target_normalisation_performed_here": False,
            "final_target_type_assignment_performed_here": False,
            "uniprot_resolution_performed_here": False,
            "target_family_assignment_performed_here": False,
            "evidence_threshold_performed_here": False,
            "global_leakage_application_performed_here": False,
            "checkpoint2_emitted_here": False,
        },
    }
    config_path = repo / "config/global_s4_sources/demo.json"
    _write_json(config_path, config)
    return repo, config_path


def _run(repo: Path, config_path: Path):
    return prepare_global_s4_source(source_config=config_path, repo_root=repo)


def test_authorised_records_selected(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    result = _run(repo, config)
    rows = list(csv.DictReader(result.output_csv.open(encoding="utf-8")))
    assert [r["record_id"] for r in rows] == ["src:a1", "src:a2"]
    assert result.stats.handoff_records == 2


def test_unauthorised_records_excluded(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    result = _run(repo, config)
    ids = {r["record_id"] for r in csv.DictReader(result.output_csv.open(encoding="utf-8"))}
    assert "src:r1" not in ids
    assert "src:p1" not in ids
    assert "src:a3" not in ids  # accept but authorised_for_s4=false


def test_exact_expected_count_enforced(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path, expected=3)
    with pytest.raises(GlobalS4HandoffError, match="Expected 3"):
        _run(repo, config)


def test_resolution_canonical_id_disagreement_fails(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    res_path = repo / "config/checkpoint_reviews/demo_checkpoint1_resolutions.csv"
    rows = list(csv.DictReader(res_path.open(encoding="utf-8")))
    rows[0]["record_id"] = "src:missing"
    _write_csv(res_path, RESOLUTION_COLUMNS, rows)
    with pytest.raises(GlobalS4HandoffError, match="disagree"):
        _run(repo, config)


def test_authorised_id_file_disagreement_fails(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    auth_path = (
        repo / "data/interim/checkpoints/demo_cp1/resolved/demo_s4_authorised_ids.csv"
    )
    rows = list(csv.DictReader(auth_path.open(encoding="utf-8")))
    rows[0]["record_id"] = "src:other"
    _write_csv(auth_path, AUTH_ID_COLUMNS, rows)
    with pytest.raises(GlobalS4HandoffError, match="disagree"):
        _run(repo, config)


def test_duplicate_canonical_ids_fail(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    canon_path = repo / "data/interim/checkpoints/demo_cp1/demo_s3_canonical.csv"
    rows = list(csv.DictReader(canon_path.open(encoding="utf-8")))
    rows[1]["record_id"] = rows[0]["record_id"]
    _write_csv(canon_path, list(CORPUS_COLUMNS), rows)
    with pytest.raises(GlobalS4HandoffError, match="duplicate"):
        _run(repo, config)


def test_duplicate_resolution_ids_fail(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    res_path = repo / "config/checkpoint_reviews/demo_checkpoint1_resolutions.csv"
    rows = list(csv.DictReader(res_path.open(encoding="utf-8")))
    rows[1]["record_id"] = rows[0]["record_id"]
    _write_csv(res_path, RESOLUTION_COLUMNS, rows)
    with pytest.raises(GlobalS4HandoffError, match="duplicate"):
        _run(repo, config)


def test_missing_resolution_fails(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    res_path = repo / "config/checkpoint_reviews/demo_checkpoint1_resolutions.csv"
    rows = list(csv.DictReader(res_path.open(encoding="utf-8")))
    _write_csv(res_path, RESOLUTION_COLUMNS, rows[1:])
    with pytest.raises(GlobalS4HandoffError, match="disagree|missing"):
        _run(repo, config)


def test_extra_resolution_fails(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    res_path = repo / "config/checkpoint_reviews/demo_checkpoint1_resolutions.csv"
    rows = list(csv.DictReader(res_path.open(encoding="utf-8")))
    extra = dict(rows[0])
    extra["record_id"] = "src:extra"
    rows.append(extra)
    _write_csv(res_path, RESOLUTION_COLUMNS, rows)
    with pytest.raises(GlobalS4HandoffError, match="disagree|extra"):
        _run(repo, config)


def test_accepted_but_not_authorised_excluded(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    result = _run(repo, config)
    ids = [r["record_id"] for r in csv.DictReader(result.output_csv.open(encoding="utf-8"))]
    assert "src:a3" not in ids


def test_authorised_non_accept_fails(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    res_path = repo / "config/checkpoint_reviews/demo_checkpoint1_resolutions.csv"
    rows = list(csv.DictReader(res_path.open(encoding="utf-8")))
    for row in rows:
        if row["record_id"] == "src:a1":
            row["resolved_decision"] = "park"
            row["checkpoint1_resolution_status"] = "parked_after_checkpoint1"
    _write_csv(res_path, RESOLUTION_COLUMNS, rows)
    with pytest.raises(GlobalS4HandoffError, match="resolved_decision"):
        _run(repo, config)


def test_authorised_wrong_status_fails(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    res_path = repo / "config/checkpoint_reviews/demo_checkpoint1_resolutions.csv"
    rows = list(csv.DictReader(res_path.open(encoding="utf-8")))
    for row in rows:
        if row["record_id"] == "src:a1":
            row["checkpoint1_resolution_status"] = "needs_source_review"
    _write_csv(res_path, RESOLUTION_COLUMNS, rows)
    with pytest.raises(GlobalS4HandoffError, match="checkpoint1_resolution_status"):
        _run(repo, config)


def test_canonical_row_order_preserved(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    result = _run(repo, config)
    canon_ids = [
        r["record_id"]
        for r in csv.DictReader(
            (repo / "data/interim/checkpoints/demo_cp1/demo_s3_canonical.csv").open(
                encoding="utf-8"
            )
        )
    ]
    auth_path = (
        repo / "data/interim/checkpoints/demo_cp1/resolved/demo_s4_authorised_ids.csv"
    )
    auth_set = {
        r["record_id"] for r in csv.DictReader(auth_path.open(encoding="utf-8"))
    }
    expected = [record_id for record_id in canon_ids if record_id in auth_set]
    out_ids = [
        r["record_id"]
        for r in csv.DictReader(result.output_csv.open(encoding="utf-8"))
    ]
    assert out_ids == expected


def test_handoff_set_equals_authorised_ids(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    result = _run(repo, config)
    auth_set = {
        r["record_id"]
        for r in csv.DictReader(
            (
                repo
                / "data/interim/checkpoints/demo_cp1/resolved/demo_s4_authorised_ids.csv"
            ).open(encoding="utf-8")
        )
    }
    out_set = {
        r["record_id"]
        for r in csv.DictReader(result.output_csv.open(encoding="utf-8"))
    }
    assert out_set == auth_set


def test_every_canonical_field_unchanged(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    result = _run(repo, config)
    canon = {
        r["record_id"]: r
        for r in csv.DictReader(
            (repo / "data/interim/checkpoints/demo_cp1/demo_s3_canonical.csv").open(
                encoding="utf-8"
            )
        )
    }
    for row in csv.DictReader(result.output_csv.open(encoding="utf-8")):
        source = canon[row["record_id"]]
        for column in CORPUS_COLUMNS:
            assert row[column] == source[column]


def test_target_fields_remain_unchanged(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    result = _run(repo, config)
    for row in csv.DictReader(result.output_csv.open(encoding="utf-8")):
        assert row["target_name"] == ""
        assert row["target_type"] == ""
        assert row["target_uniprot"] == ""
        assert row["target_family"] == ""
        assert row["target_name_raw"] in {"Target A", "Target B"}


def test_evidence_fields_remain_unchanged(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    result = _run(repo, config)
    for row in csv.DictReader(result.output_csv.open(encoding="utf-8")):
        assert row["binding_evidence_type"] == ""
        assert row["binding_evidence_score"] == ""
        assert row["affinity_value"] == ""


def test_sequence_fields_remain_unchanged(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    result = _run(repo, config)
    by_id = {
        r["record_id"]: r
        for r in csv.DictReader(result.output_csv.open(encoding="utf-8"))
    }
    assert by_id["src:a1"]["sequence_core"] == "ACGUACGU"
    assert by_id["src:a2"]["sequence_core"] == "UUGGAACC"


def test_no_deduplication(tmp_path: Path) -> None:
    # Two authorised records with identical sequences remain two rows.
    repo, config = _make_tree(tmp_path)
    canon_path = repo / "data/interim/checkpoints/demo_cp1/demo_s3_canonical.csv"
    rows = list(csv.DictReader(canon_path.open(encoding="utf-8")))
    for row in rows:
        if row["record_id"] in {"src:a1", "src:a2"}:
            row["sequence_raw"] = "ACGUACGU"
            row["sequence_full"] = "ACGUACGU"
            row["sequence_core"] = "ACGUACGU"
    _write_csv(canon_path, list(CORPUS_COLUMNS), rows)
    result = _run(repo, config)
    out = list(csv.DictReader(result.output_csv.open(encoding="utf-8")))
    assert len(out) == 2
    assert out[0]["sequence_core"] == out[1]["sequence_core"]


def test_no_clustering(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    result = _run(repo, config)
    for row in csv.DictReader(result.output_csv.open(encoding="utf-8")):
        assert row["cluster_id"] == ""
        assert row["near_duplicate_family_id"] == ""
        assert row["is_cluster_representative"] == ""


def test_no_raw_data_access(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    raw = repo / "data/raw/demo/raw.csv"
    before = raw.read_bytes()
    opened: list[str] = []
    real_open = Path.open

    def tracking_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        opened.append(str(self))
        return real_open(self, *args, **kwargs)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(Path, "open", tracking_open)
    try:
        _run(repo, config)
    finally:
        monkey.undo()
    assert not any("/raw/" in path or "data/raw" in path for path in opened)
    assert raw.read_bytes() == before


def test_atomic_write(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    result = _run(repo, config)
    assert result.output_csv.exists()
    assert result.output_summary.exists()
    assert not list(result.output_csv.parent.glob(f".{result.output_csv.name}.*.tmp"))


def test_deterministic_rerun(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    first = _run(repo, config)
    h1 = _sha256(first.output_csv)
    h1s = _sha256(first.output_summary)
    second = _run(repo, config)
    assert _sha256(second.output_csv) == h1
    assert _sha256(second.output_summary) == h1s


def test_works_from_another_cwd(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    old = Path.cwd()
    stdout = io.StringIO()
    try:
        os.chdir(other)
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            code = main(
                [
                    "--source-config",
                    "config/global_s4_sources/demo.json",
                    "--repo-root",
                    str(repo),
                ]
            )
    finally:
        os.chdir(old)
    assert code == 0
    assert "ACGUACGU" not in stdout.getvalue()
    assert SEQ_LEAK_RE.search(stdout.getvalue()) is None


def test_no_absolute_paths_written(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    result = _run(repo, config)
    abs_root = str(repo.resolve())
    assert abs_root not in result.output_summary.read_text(encoding="utf-8")


def test_no_sequence_values_printed(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        main(
            [
                "--source-config",
                str(config),
                "--repo-root",
                str(repo),
            ]
        )
    text = stdout.getvalue()
    assert "ACGUACGU" not in text
    assert "UUGGAACC" not in text
    assert SEQ_LEAK_RE.search(text) is None


def test_config_validation(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    del payload["expected_authorised_records"]
    _write_json(config, payload)
    with pytest.raises(GlobalS4HandoffError, match="missing required"):
        load_source_config(config)


def test_unknown_source_config_failure(tmp_path: Path) -> None:
    repo, _ = _make_tree(tmp_path)
    with pytest.raises(GlobalS4HandoffError, match="Unknown source config"):
        prepare_global_s4_source(
            source_config=repo / "config/global_s4_sources/missing.json",
            repo_root=repo,
        )


def test_output_parent_directory_created_safely(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    out_dir = repo / "data/interim/global_s4_ready"
    # Remove so the utility must recreate.
    for path in out_dir.glob("*"):
        path.unlink()
    out_dir.rmdir()
    result = _run(repo, config)
    assert result.output_csv.parent.exists()
    assert result.output_csv.exists()


def test_summary_contains_expected_aggregate_counts(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path, source_key="aptabase")
    result = _run(repo, config)
    text = result.output_summary.read_text(encoding="utf-8")
    assert "S3 records = `5`" in text
    assert "CHECKPOINT-1 authorised = `2`" in text
    assert "global-S4 handoff records = `2`" in text
    assert "Protein` = `1`" in text or "`Protein` = `1`" in text
    assert HANDOFF_CLOSED_STATEMENT in text


def test_handoff_output_equals_exact_authorised_subset(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    result = _run(repo, config)
    canon_rows = list(
        csv.DictReader(
            (repo / "data/interim/checkpoints/demo_cp1/demo_s3_canonical.csv").open(
                encoding="utf-8"
            )
        )
    )
    canon = {r["record_id"]: r for r in canon_rows}
    auth_set = {
        r["record_id"]
        for r in csv.DictReader(
            (
                repo
                / "data/interim/checkpoints/demo_cp1/resolved/demo_s4_authorised_ids.csv"
            ).open(encoding="utf-8")
        )
    }
    expected_ids = [r["record_id"] for r in canon_rows if r["record_id"] in auth_set]
    out = list(csv.DictReader(result.output_csv.open(encoding="utf-8")))
    assert [r["record_id"] for r in out] == expected_ids
    for row in out:
        for column in CORPUS_COLUMNS:
            assert row[column] == canon[row["record_id"]][column]


def test_input_files_remain_byte_identical(tmp_path: Path) -> None:
    repo, config = _make_tree(tmp_path)
    paths = [
        repo / "data/interim/checkpoints/demo_cp1/demo_s3_canonical.csv",
        repo / "config/checkpoint_reviews/demo_checkpoint1_resolutions.csv",
        repo / "data/interim/checkpoints/demo_cp1/resolved/demo_s4_authorised_ids.csv",
    ]
    before = {p: p.read_bytes() for p in paths}
    _run(repo, config)
    for path in paths:
        assert path.read_bytes() == before[path]


def test_handoff_joins_sequence_safe_source_metadata(tmp_path: Path) -> None:
    repo, config_path = _make_tree(tmp_path, source_key="utexas")
    sidecar = repo / "data/interim/extracted/utexas_source_metadata.csv"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        sidecar,
        ["record_id", "utexas_kd_nm", "utexas_affinity", "utexas_aptamer_sequence"],
        [
            {
                "record_id": "src:a1",
                "utexas_kd_nm": "12.5",
                "utexas_affinity": "high",
                "utexas_aptamer_sequence": "ACGUACGU",
            },
            {
                "record_id": "src:a2",
                "utexas_kd_nm": "0.4",
                "utexas_affinity": "nM",
                "utexas_aptamer_sequence": "UUGGAACC",
            },
            {
                "record_id": "src:r1",
                "utexas_kd_nm": "",
                "utexas_affinity": "",
                "utexas_aptamer_sequence": "GGCCGGCC",
            },
            {
                "record_id": "src:p1",
                "utexas_kd_nm": "",
                "utexas_affinity": "",
                "utexas_aptamer_sequence": "AAUUGGCC",
            },
            {
                "record_id": "src:a3",
                "utexas_kd_nm": "9",
                "utexas_affinity": "weak",
                "utexas_aptamer_sequence": "CCGGAAUU",
            },
        ],
    )
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["emit_target_evidence_boundary"] = True
    payload["handoff_extra_fields"] = ["utexas_kd_nm", "utexas_affinity"]
    payload["target_metadata"]["source_metadata_path"] = (
        "data/interim/extracted/utexas_source_metadata.csv"
    )
    payload["handoff_ready_statement"] = (
        "UTexas is ready to be retrieved as one input to the future "
        "corpus-wide S4 merge."
    )
    config_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    result = _run(repo, config_path)
    rows = list(csv.DictReader(result.output_csv.open(encoding="utf-8")))
    assert [r["record_id"] for r in rows] == ["src:a1", "src:a2"]
    assert rows[0]["utexas_kd_nm"] == "12.5"
    assert rows[1]["utexas_affinity"] == "nM"
    assert "utexas_aptamer_sequence" not in rows[0]
    for row in rows:
        assert row["target_name"] == ""
        assert row["binding_evidence_score"] == ""
    text = result.output_summary.read_text(encoding="utf-8")
    assert "target_name remains unresolved" in text
    assert "Kd/Affinity evidence not scored" in text
    assert SEQ_LEAK_RE.search(text) is None


def test_riboaptamer_handoff_uses_applied_canonical_and_preserves_source_metadata(
    tmp_path: Path,
) -> None:
    repo, config_path = _make_tree(tmp_path)
    canonical, _resolutions, authorised = _base_records()
    applied_dir = repo / "data/interim/checkpoints/riboaptamer_cp1/resolved"
    applied_dir.mkdir(parents=True)
    sidecar_dir = repo / "data/interim/extracted"
    sidecar_dir.mkdir(parents=True)
    applied_path = applied_dir / "riboaptamer_checkpoint1_applied_canonical.csv"
    pre_review = (
        repo
        / "data/interim/checkpoints/riboaptamer_cp1/riboaptamer_s3_canonical.csv"
    )
    pre_review.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(applied_path, list(CORPUS_COLUMNS), canonical)
    mutated = []
    for row in canonical:
        copy = dict(row)
        if row["record_id"] == authorised[0]:
            copy["sequence_core"] = "AAAAAAAA"
        mutated.append(copy)
    _write_csv(pre_review, list(CORPUS_COLUMNS), mutated)
    _write_csv(
        sidecar_dir / "riboaptamer_source_metadata.csv",
        [
            "record_id",
            "riboaptamer_sequence_name",
            "riboaptamer_aptamer_name",
            "riboaptamer_category",
            "riboaptamer_type",
            "riboaptamer_article_name",
            "riboaptamer_description",
            "riboaptamer_affinity_kd",
            "riboaptamer_pubmed_link",
            "riboaptamer_mmcif_download_url",
            "riboaptamer_sequence",
        ],
        [
            {
                "record_id": row["record_id"],
                "riboaptamer_sequence_name": f"seq-{row['record_id']}",
                "riboaptamer_aptamer_name": f"name-{row['record_id']}",
                "riboaptamer_category": "Mammalian",
                "riboaptamer_type": "Proteins",
                "riboaptamer_article_name": "Demo article",
                "riboaptamer_description": "descriptive target text",
                "riboaptamer_affinity_kd": "Kd: 1 nM",
                "riboaptamer_pubmed_link": "https://pubmed.ncbi.nlm.nih.gov/1",
                "riboaptamer_mmcif_download_url": "https://example.invalid/a.cif",
                "riboaptamer_sequence": "GGCCGGCC",
            }
            for row in canonical
        ],
    )
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["source_key"] = "riboaptamer"
    payload["canonical_input"] = (
        "data/interim/checkpoints/riboaptamer_cp1/resolved/"
        "riboaptamer_checkpoint1_applied_canonical.csv"
    )
    payload["emit_target_evidence_boundary"] = True
    payload["handoff_extra_fields"] = [
        "riboaptamer_sequence_name",
        "riboaptamer_aptamer_name",
        "riboaptamer_category",
        "riboaptamer_type",
        "riboaptamer_article_name",
        "riboaptamer_description",
        "riboaptamer_affinity_kd",
        "riboaptamer_pubmed_link",
        "riboaptamer_mmcif_download_url",
    ]
    payload["target_metadata"]["source_metadata_path"] = (
        "data/interim/extracted/riboaptamer_source_metadata.csv"
    )
    payload["handoff_ready_statement"] = (
        "RiboAptamer is ready to be retrieved as one input to the future "
        "corpus-wide S4 merge. Category is a prior only. Source Type is a "
        "target-class prior and must be checked against the resolved target."
    )
    config_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    bad = dict(payload)
    bad["handoff_extra_fields"] = list(payload["handoff_extra_fields"]) + [
        "riboaptamer_sequence"
    ]
    bad_path = repo / "config/global_s4_sources/demo_bad.json"
    _write_json(bad_path, bad)
    with pytest.raises(GlobalS4HandoffError, match="sequence-bearing"):
        prepare_global_s4_source(source_config=bad_path, repo_root=repo)

    result = prepare_global_s4_source(source_config=config_path, repo_root=repo)
    rows = list(csv.DictReader(result.output_csv.open(encoding="utf-8")))
    by_id = {row["record_id"]: row for row in canonical}
    assert rows[0]["sequence_core"] == by_id[rows[0]["record_id"]]["sequence_core"]
    assert rows[0]["sequence_core"] != "AAAAAAAA"
    assert rows[0]["riboaptamer_sequence_name"].startswith("seq-")
    assert rows[0]["riboaptamer_type"] == "Proteins"
    assert rows[0]["riboaptamer_affinity_kd"] == "Kd: 1 nM"
    assert "riboaptamer_sequence" not in rows[0]
    assert rows[0]["target_name"] == ""
    assert rows[0]["target_type"] == ""
    assert rows[0]["binding_evidence_score"] == ""
    text = result.output_summary.read_text(encoding="utf-8")
    assert "target_name remains unresolved" in text
    assert "protein/non-protein filtering not performed" in text
    assert "leakage not applied" in text
    assert SEQ_LEAK_RE.search(text) is None
    assert "applied_canonical" in payload["canonical_input"]


def test_ena_live_source_config_loads() -> None:
    path = REPO_ROOT / "config" / "global_s4_sources" / "ena.json"
    config = load_source_config(path)
    assert config["source_key"] == "ena"
    assert config["source_dataset"] == "ena_selected_v2_2026-08"
    assert config["expected_authorised_records"] == 675
    assert config["authorisation_field"] == "authorised_for_s4"
    assert config["checkpoint_status"] == "closed"
    assert config["global_s4_run"] is False
    assert config["canonical_input"].endswith(
        "ena_checkpoint1_applied_canonical.csv"
    )
    assert "resolved/" in config["canonical_input"]
    assert config["resolution_manifest"] == (
        "config/checkpoint_reviews/ena_checkpoint1_resolutions.csv"
    )
    extras = config["handoff_extra_fields"]
    assert "target" in extras
    assert "experiment_group_id" in extras
    assert "sequence_original" in extras
    assert "sequence" not in extras
    aliases = config["handoff_extra_field_aliases"]
    assert aliases["target_type"] == "ena_source_target_type"
    assert aliases["binding_evidence_type"] == "ena_source_binding_evidence_type"
    assert aliases["experiment_group_id"] == "ena_source_experiment_group_id"
    assert aliases["near_duplicate_family_id"] == (
        "ena_source_near_duplicate_family_id"
    )
    rules = config["global_s4_rules"]
    assert rules["final_target_normalisation_performed_here"] is False
    assert rules["evidence_threshold_performed_here"] is False
    assert rules["global_leakage_application_performed_here"] is False
    text = path.read_text(encoding="utf-8")
    assert SEQ_LEAK_RE.search(text) is None
    assert "GGCCGAA" not in text


ENA_SIDECAR_COLUMNS = [
    "record_id",
    "target",
    "target_original",
    "target_type",
    "binding_evidence_type",
    "experiment_group_id",
    "experiment_group_ids",
    "near_duplicate_family_id",
    "near_duplicate_family_size",
    "ena_effective_near_duplicate_family_id",
    "ena_effective_near_duplicate_family_size",
    "ena_source_family_id_was_blank",
    "sequence_original",
    "manual_sequence_corrected",
    "review_unit_id",
    "source_database",
]


def _ena_sidecar_row(record_id: str, **overrides: str) -> dict[str, str]:
    native = record_id.split(":")[-1]
    row = {
        "record_id": record_id,
        "target": f"target-{native}",
        "target_original": f"orig-{native}",
        "target_type": "protein",
        "binding_evidence_type": "selection_context",
        "experiment_group_id": "g1",
        "experiment_group_ids": "g1|g2",
        "near_duplicate_family_id": "",
        "near_duplicate_family_size": "1",
        "ena_effective_near_duplicate_family_id": f"ena_singleton_{native}",
        "ena_effective_near_duplicate_family_size": "1",
        "ena_source_family_id_was_blank": "true",
        "sequence_original": "ACGUACGU",
        "manual_sequence_corrected": "",
        "review_unit_id": native,
        "source_database": "ENA",
    }
    row.update(overrides)
    return row


def _ena_handoff_tree(tmp_path: Path, *, expected: int | None = None) -> tuple[Path, Path]:
    repo, config_path = _make_tree(tmp_path, source_key="ena", expected=expected)
    canonical, _resolutions, authorised = _base_records()
    applied_dir = repo / "data/interim/checkpoints/ena_cp1/resolved"
    applied_dir.mkdir(parents=True, exist_ok=True)
    sidecar_dir = repo / "data/interim/extracted"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    pre_review = repo / "data/interim/checkpoints/ena_cp1/ena_s3_canonical.csv"
    pre_review.parent.mkdir(parents=True, exist_ok=True)

    applied = []
    mutated_prereview = []
    for row in canonical:
        applied_row = dict(row)
        pre_row = dict(row)
        if row["record_id"] == "src:a1":
            applied_row["sequence_full"] = "ACGUACGU"
            applied_row["sequence_core"] = "GUAC"
            applied_row["sequence_length_full"] = "8"
            applied_row["sequence_length_core"] = "4"
            applied_row["trim_status"] = "primers_removed"
            applied_row["detected_constant_5p"] = "AC"
            applied_row["detected_constant_3p"] = "GU"
            pre_row["sequence_full"] = "ACGUACGU"
            pre_row["sequence_core"] = "ACGUACGU"
            pre_row["trim_status"] = "no_constants_detected"
        if row["record_id"] == "src:a2":
            applied_row["sequence_raw"] = "ACGTTGCA"
            applied_row["sequence_full"] = "ACGUUGCA"
            applied_row["sequence_core"] = "ACGUUGCA"
            applied_row["sequence_length_full"] = "8"
            applied_row["sequence_length_core"] = "8"
            applied_row["molecule_type"] = "RNA"
            applied_row["chemistry"] = "RNA"
            applied_row["alphabet_as_reported"] = "DNA_T"
            applied_row["t_to_u_applied"] = "true"
        if row["record_id"] == "src:a3":
            applied_row["sequence_full"] = "ACGUUGCA"
            applied_row["sequence_core"] = "ACGUUGCA"
        applied.append(applied_row)
        mutated_prereview.append(pre_row)
    applied_path = applied_dir / "ena_checkpoint1_applied_canonical.csv"
    _write_csv(applied_path, list(CORPUS_COLUMNS), applied)
    _write_csv(pre_review, list(CORPUS_COLUMNS), mutated_prereview)

    sidecar_rows = []
    for row in applied:
        overrides: dict[str, str] = {}
        if row["record_id"] == "src:a2":
            overrides["sequence_original"] = "ACGTTGCA"
            overrides["near_duplicate_family_id"] = "fam_t"
            overrides["ena_effective_near_duplicate_family_id"] = "fam_t"
            overrides["ena_source_family_id_was_blank"] = "false"
            overrides["target_type"] = "enzyme"
        sidecar_rows.append(_ena_sidecar_row(row["record_id"], **overrides))
    _write_csv(sidecar_dir / "ena_source_metadata.csv", ENA_SIDECAR_COLUMNS, sidecar_rows)

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["source_key"] = "ena"
    payload["source_dataset"] = "ena_selected_v2_2026-08"
    payload["canonical_input"] = (
        "data/interim/checkpoints/ena_cp1/resolved/"
        "ena_checkpoint1_applied_canonical.csv"
    )
    payload["global_s4_run"] = False
    payload["emit_target_evidence_boundary"] = True
    payload["handoff_extra_fields"] = [
        "target",
        "target_original",
        "target_type",
        "binding_evidence_type",
        "experiment_group_id",
        "experiment_group_ids",
        "near_duplicate_family_id",
        "ena_effective_near_duplicate_family_id",
        "ena_source_family_id_was_blank",
        "sequence_original",
        "review_unit_id",
        "source_database",
    ]
    payload["handoff_extra_field_aliases"] = {
        "target_type": "ena_source_target_type",
        "binding_evidence_type": "ena_source_binding_evidence_type",
        "experiment_group_id": "ena_source_experiment_group_id",
        "near_duplicate_family_id": "ena_source_near_duplicate_family_id",
    }
    payload["handoff_summary_provenance_counts"] = {
        "source_family_blank_field": "ena_source_family_id_was_blank",
        "source_family_blank_true_value": "true",
        "source_nonblank_family_field": "ena_source_near_duplicate_family_id",
        "primary_experiment_group_field": "ena_source_experiment_group_id",
        "trim_status_value": "primers_removed",
        "report_t_to_u_applied": True,
        "report_duplicate_sequence_identities": True,
    }
    payload["handoff_summary_additional_notes"] = [
        "authorised_for_s4=true / inclusion in this handoff means only technically eligible after ENA sequence/molecule/construct review and prepared as an input to the future corpus-wide global S4 stage.",
        "It does not mean protein target confirmed, target canonicalised, UniProt resolved, evidence threshold passed, leakage cleared, final corpus included, deduplicated, clustered, balanced, or partitioned.",
        "Global S4 has not been run.",
    ]
    payload["handoff_ready_statement"] = (
        "ENA CHECKPOINT-1 is closed and this source is prepared as one input "
        "to the future corpus-wide global S4 stage."
    )
    payload["target_metadata"]["source_metadata_path"] = (
        "data/interim/extracted/ena_source_metadata.csv"
    )
    payload["target_metadata"]["source_specific_field"] = "target"
    payload["target_metadata"]["source_general_field"] = "ena_source_target_type"
    _write_json(config_path, payload)
    return repo, config_path


def test_ena_selects_exactly_authorised_and_excludes_unauthorised(
    tmp_path: Path,
) -> None:
    repo, config_path = _ena_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    rows = list(csv.DictReader(result.output_csv.open(encoding="utf-8")))
    ids = [row["record_id"] for row in rows]
    assert ids == ["src:a1", "src:a2"]
    assert "src:r1" not in ids
    assert "src:p1" not in ids
    assert "src:a3" not in ids
    assert result.stats.handoff_records == 2
    assert len({row["record_id"] for row in rows}) == 2


def test_ena_sidecar_join_is_one_to_one_and_preserves_extras(
    tmp_path: Path,
) -> None:
    repo, config_path = _ena_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    rows = list(csv.DictReader(result.output_csv.open(encoding="utf-8")))
    by_id = {row["record_id"]: row for row in rows}
    assert by_id["src:a1"]["target"] == "target-a1"
    assert by_id["src:a1"]["ena_source_target_type"] == "protein"
    assert by_id["src:a1"]["ena_source_binding_evidence_type"] == (
        "selection_context"
    )
    assert by_id["src:a1"]["ena_source_experiment_group_id"] == "g1"
    assert by_id["src:a1"]["experiment_group_ids"] == "g1|g2"
    assert by_id["src:a1"]["ena_source_family_id_was_blank"] == "true"
    assert by_id["src:a2"]["ena_source_near_duplicate_family_id"] == "fam_t"
    assert by_id["src:a2"]["ena_source_family_id_was_blank"] == "false"
    assert by_id["src:a2"]["sequence_original"] == "ACGTTGCA"
    assert "target_type" not in by_id["src:a1"] or by_id["src:a1"]["target_type"] == ""
    assert by_id["src:a1"]["target_type"] == ""
    assert by_id["src:a1"]["binding_evidence_type"] == ""
    assert by_id["src:a1"]["experiment_group_id"] == ""
    assert by_id["src:a1"]["near_duplicate_family_id"] == ""


def test_ena_s4_canonical_fields_remain_empty(tmp_path: Path) -> None:
    repo, config_path = _ena_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    for row in csv.DictReader(result.output_csv.open(encoding="utf-8")):
        assert row["target_name"] == ""
        assert row["target_uniprot"] == ""
        assert row["target_type"] == ""
        assert row["target_type_source"] == ""
        assert row["target_family"] == ""
        assert row["target_pfam"] == ""
        assert row["pdb_id"] == ""
        assert row["binding_evidence_type"] == ""
        assert row["binding_evidence_score"] == ""
        assert row["affinity_value"] == ""
        assert row["cluster_id"] == ""
        assert row["is_cluster_representative"] == ""
        assert row["partition"] == ""


def test_ena_uses_applied_reviewed_core_not_prereview(tmp_path: Path) -> None:
    repo, config_path = _ena_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    by_id = {
        row["record_id"]: row
        for row in csv.DictReader(result.output_csv.open(encoding="utf-8"))
    }
    assert by_id["src:a1"]["sequence_core"] == "GUAC"
    assert by_id["src:a1"]["sequence_full"] == "ACGUACGU"
    assert by_id["src:a1"]["trim_status"] == "primers_removed"
    pre = {
        row["record_id"]: row
        for row in csv.DictReader(
            (repo / "data/interim/checkpoints/ena_cp1/ena_s3_canonical.csv").open(
                encoding="utf-8"
            )
        )
    }
    assert pre["src:a1"]["sequence_core"] == "ACGUACGU"
    assert by_id["src:a1"]["sequence_core"] != pre["src:a1"]["sequence_core"]


def test_ena_t_to_u_provenance_retained(tmp_path: Path) -> None:
    repo, config_path = _ena_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    by_id = {
        row["record_id"]: row
        for row in csv.DictReader(result.output_csv.open(encoding="utf-8"))
    }
    row = by_id["src:a2"]
    assert row["molecule_type"] == "RNA"
    assert row["chemistry"] == "RNA"
    assert row["alphabet_as_reported"] == "DNA_T"
    assert row["t_to_u_applied"] == "true"
    assert row["sequence_raw"] == "ACGTTGCA"
    assert row["sequence_full"] == "ACGUUGCA"
    assert row["sequence_core"] == "ACGUUGCA"


def test_ena_duplicate_identities_remain(tmp_path: Path) -> None:
    repo, config_path = _ena_handoff_tree(tmp_path)
    canon_path = (
        repo
        / "data/interim/checkpoints/ena_cp1/resolved/"
        / "ena_checkpoint1_applied_canonical.csv"
    )
    rows = list(csv.DictReader(canon_path.open(encoding="utf-8")))
    for row in rows:
        if row["record_id"] in {"src:a1", "src:a2"}:
            row["sequence_full"] = "ACGUACGU"
            row["sequence_core"] = "ACGUACGU"
            row["t_to_u_applied"] = "false"
            row["alphabet_as_reported"] = "RNA"
    _write_csv(canon_path, list(CORPUS_COLUMNS), rows)
    result = _run(repo, config_path)
    out = list(csv.DictReader(result.output_csv.open(encoding="utf-8")))
    assert len(out) == 2
    assert out[0]["record_id"] != out[1]["record_id"]
    assert out[0]["sequence_full"] == out[1]["sequence_full"] == "ACGUACGU"
    assert out[0]["sequence_core"] == out[1]["sequence_core"]
    text = result.output_summary.read_text(encoding="utf-8")
    assert "diagnostic only — no deduplication performed" in text


def test_ena_handoff_deterministic(tmp_path: Path) -> None:
    repo, config_path = _ena_handoff_tree(tmp_path)
    first = _run(repo, config_path)
    h1 = _sha256(first.output_csv)
    h1s = _sha256(first.output_summary)
    second = _run(repo, config_path)
    assert _sha256(second.output_csv) == h1
    assert _sha256(second.output_summary) == h1s


def test_ena_expected_authorised_count_mismatch_hard_fails(tmp_path: Path) -> None:
    repo, config_path = _ena_handoff_tree(tmp_path, expected=675)
    with pytest.raises(GlobalS4HandoffError, match="Expected 675"):
        _run(repo, config_path)


def test_colliding_extra_without_alias_hard_fails(tmp_path: Path) -> None:
    repo, config_path = _ena_handoff_tree(tmp_path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["handoff_extra_field_aliases"] = {}
    _write_json(config_path, payload)
    with pytest.raises(GlobalS4HandoffError, match="handoff_extra_field_aliases"):
        _run(repo, config_path)


def test_ena_summary_is_sequence_free_and_states_s4_boundary(
    tmp_path: Path,
) -> None:
    repo, config_path = _ena_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    text = result.output_summary.read_text(encoding="utf-8")
    assert SEQ_LEAK_RE.search(text) is None
    assert "ACGUACGU" not in text
    assert "ACGTTGCA" not in text
    assert "target_name remains unresolved" in text
    assert "Global S4 has not been run." in text
    assert "protein target confirmed" in text
    assert "materialised singletons = `1`" in text
    assert "source-nonblank family rows = `1`" in text
    assert "distinct primary experiment groups = `1`" in text
    assert "reviewed trimmed records = `1`" in text
    assert "T-transcribed records = `1`" in text
    assert str(repo.resolve()) not in text


APTAMERBASE_SIDECAR_COLUMNS = [
    "record_id",
    "native_id",
    "aptamerbase_type",
    "aptamerbase_id",
    "aptamerbase_label",
    "aptamerbase_sequence",
    "aptamerbase_sequence_length",
    "aptamerbase_has_mutational_analysis",
    "aptamerbase_has_experimentally_determined_structure",
    "aptamerbase_has_minimal_aptamer",
    "aptamerbase_is_minimal_aptamer_of",
    "aptamerbase_has_application",
    "aptamerbase_has_modification_details",
    "aptamerbase_has_secondary_structure",
    "aptamerbase_has_predicted_secondary_structure",
    "aptamerbase_has_sequence_pattern",
]

APTAMERBASE_QC_COLUMNS = [
    "record_id",
    "source_object_type",
    "molecule_evidence_source",
    "rdf_has_rna",
    "rdf_has_dna",
    "rdf_has_modified_nucleic_acid",
]

APTAMERBASE_EXTRA_FIELDS = [
    "aptamerbase_id",
    "aptamerbase_label",
    "aptamerbase_type",
    "aptamerbase_sequence_length",
    "aptamerbase_has_mutational_analysis",
    "aptamerbase_has_experimentally_determined_structure",
    "aptamerbase_has_minimal_aptamer",
    "aptamerbase_is_minimal_aptamer_of",
    "aptamerbase_has_application",
    "aptamerbase_has_modification_details",
    "aptamerbase_has_secondary_structure",
    "aptamerbase_has_predicted_secondary_structure",
    "aptamerbase_has_sequence_pattern",
]


def _aptamerbase_specs() -> list[dict[str, str]]:
    """Synthetic AptamerBase CHECKPOINT rows. Sequences are <20 nt."""
    return [
        {
            "record_id": "aptamerbase:0001",
            "resolved": "accept",
            "status": "approved_for_s4",
            "auth": "true",
            "seq": "ACGUACGU",
            "core": "GUAC",
            "molecule": "RNA",
            "chemistry": "RNA",
            "trim_status": "t7_removed",
            "object_type": "aptamer",
            "freebase": "http://rdf.freebase.com/ns/m.aaa",
            "label": "demo-label-1",
            "minimal_of": "",
            "has_minimal": "http://rdf.freebase.com/ns/m.ccc",
        },
        {
            "record_id": "aptamerbase:0002",
            "resolved": "accept",
            "status": "approved_for_s4",
            "auth": "true",
            "seq": "GGCCGGCC",
            "core": "GGCCGGCC",
            "molecule": "RNA",
            "chemistry": "2F-RNA",
            "trim_status": "no_constants_detected",
            "object_type": "aptamer",
            "freebase": "http://rdf.freebase.com/ns/m.aaa",
            "label": "demo-label-2",
            "minimal_of": "http://rdf.freebase.com/ns/m.aaa",
            "has_minimal": "",
        },
        {
            "record_id": "aptamerbase:0003",
            "resolved": "accept",
            "status": "approved_for_s4",
            "auth": "true",
            "seq": "AAUUGGCC",
            "core": "AAUUGGCC",
            "molecule": "RNA",
            "chemistry": "2NH2-RNA",
            "trim_status": "no_constants_detected",
            "object_type": "aptamer",
            "freebase": "http://rdf.freebase.com/ns/m.bbb",
            "label": "demo-label-3",
            "minimal_of": "",
            "has_minimal": "",
        },
        {
            "record_id": "aptamerbase:0004",
            "resolved": "accept",
            "status": "approved_for_s4",
            "auth": "true",
            "seq": "CCGGAAUU",
            "core": "CCGGAAUU",
            "molecule": "RNA",
            "chemistry": "mixed",
            "trim_status": "no_constants_detected",
            "object_type": "aptamer",
            "freebase": "http://rdf.freebase.com/ns/m.ddd",
            "label": "",
            "minimal_of": "",
            "has_minimal": "",
        },
        {
            "record_id": "aptamerbase:ss01",
            "resolved": "park",
            "status": "parked_after_checkpoint1",
            "auth": "false",
            "seq": "ACGTTGCA",
            "core": "ACGTTGCA",
            "molecule": "ssDNA",
            "chemistry": "DNA",
            "trim_status": "no_constants_detected",
            "object_type": "aptamer",
            "freebase": "http://rdf.freebase.com/ns/m.ssdna",
            "label": "ssdna-label",
            "minimal_of": "",
            "has_minimal": "",
        },
        {
            "record_id": "aptamerbase:unk1",
            "resolved": "park",
            "status": "parked_after_checkpoint1",
            "auth": "false",
            "seq": "ACGUUGCA",
            "core": "ACGUUGCA",
            "molecule": "unknown",
            "chemistry": "unknown",
            "trim_status": "no_constants_detected",
            "object_type": "aptamer",
            "freebase": "http://rdf.freebase.com/ns/m.unk",
            "label": "unknown-mol",
            "minimal_of": "",
            "has_minimal": "",
        },
        {
            "record_id": "aptamerbase:ch01",
            "resolved": "park",
            "status": "parked_after_checkpoint1",
            "auth": "false",
            "seq": "UUGGAACC",
            "core": "UUGGAACC",
            "molecule": "RNA",
            "chemistry": "unknown",
            "trim_status": "no_constants_detected",
            "object_type": "aptamer",
            "freebase": "http://rdf.freebase.com/ns/m.chem",
            "label": "chem-unknown",
            "minimal_of": "",
            "has_minimal": "",
        },
        {
            "record_id": "aptamerbase:st01",
            "resolved": "reject",
            "status": "rejected_after_checkpoint1",
            "auth": "false",
            "seq": "GGCCAATT",
            "core": "GGCCAATT",
            "molecule": "unknown",
            "chemistry": "unknown",
            "trim_status": "no_constants_detected",
            "object_type": "secondary_structure",
            "freebase": "http://rdf.freebase.com/ns/m.struct",
            "label": "structure-object",
            "minimal_of": "",
            "has_minimal": "",
        },
    ]


def _aptamerbase_sidecar_row(spec: dict[str, str]) -> dict[str, str]:
    native = spec["record_id"].split(":")[-1]
    return {
        "record_id": spec["record_id"],
        "native_id": native,
        "aptamerbase_type": "http://rdf.freebase.com/ns/base.aptamer.aptamer",
        "aptamerbase_id": spec["freebase"],
        "aptamerbase_label": spec["label"],
        "aptamerbase_sequence": spec["seq"],
        "aptamerbase_sequence_length": str(len(spec["seq"])),
        "aptamerbase_has_mutational_analysis": "false",
        "aptamerbase_has_experimentally_determined_structure": (
            "true" if spec["record_id"] == "aptamerbase:0001" else "false"
        ),
        "aptamerbase_has_minimal_aptamer": spec["has_minimal"],
        "aptamerbase_is_minimal_aptamer_of": spec["minimal_of"],
        "aptamerbase_has_application": "",
        "aptamerbase_has_modification_details": (
            "2F" if spec["chemistry"] == "2F-RNA" else ""
        ),
        "aptamerbase_has_secondary_structure": "",
        "aptamerbase_has_predicted_secondary_structure": "",
        "aptamerbase_has_sequence_pattern": "",
    }


def _aptamerbase_qc_row(spec: dict[str, str]) -> dict[str, str]:
    return {
        "record_id": spec["record_id"],
        "source_object_type": spec["object_type"],
        "molecule_evidence_source": "rdf_type",
        "rdf_has_rna": "true" if spec["molecule"] == "RNA" else "false",
        "rdf_has_dna": "true" if spec["molecule"] == "ssDNA" else "false",
        "rdf_has_modified_nucleic_acid": (
            "true" if spec["chemistry"] in {"2F-RNA", "2NH2-RNA", "mixed"} else "false"
        ),
    }


def _aptamerbase_handoff_tree(
    tmp_path: Path, *, expected: int | None = None
) -> tuple[Path, Path]:
    repo, config_path = _make_tree(tmp_path, source_key="aptamerbase", expected=expected)
    specs = _aptamerbase_specs()
    if expected is None:
        expected = sum(1 for spec in specs if spec["auth"] == "true")

    applied_dir = repo / "data/interim/checkpoints/aptamerbase_cp1/resolved"
    applied_dir.mkdir(parents=True, exist_ok=True)
    pre_review = (
        repo / "data/interim/checkpoints/aptamerbase_cp1/aptamerbase_s3_canonical.csv"
    )
    pre_review.parent.mkdir(parents=True, exist_ok=True)
    sidecar_dir = repo / "data/interim/extracted"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    qc_dir = repo / "data/interim/normalised"
    qc_dir.mkdir(parents=True, exist_ok=True)

    applied: list[dict[str, str]] = []
    mutated_prereview: list[dict[str, str]] = []
    resolutions: list[dict[str, str]] = []
    authorised: list[str] = []
    for spec in specs:
        applied_row = _empty_corpus(
            record_id=spec["record_id"],
            sequence_raw=spec["seq"],
            sequence_full=spec["seq"],
            sequence_core=spec["core"],
            sequence_length_full=str(len(spec["seq"])),
            sequence_length_core=str(len(spec["core"])),
            molecule_type=spec["molecule"],
            chemistry=spec["chemistry"],
            alphabet_as_reported="RNA" if spec["molecule"] == "RNA" else "DNA_T",
            t_to_u_applied="false",
            trim_status=spec["trim_status"],
            target_name_raw="",
            target_name="",
            target_type="",
            target_uniprot="",
            source_db="aptamerbase",
            source_dataset="aptamerbase_export_2026-06-24",
            contributing_sources="aptamerbase",
            contributing_datasets="aptamerbase_export_2026-06-24",
            corroboration_count="1",
            redistribution_status="unknown",
            independently_attested_by_permissive_source="false",
            native_id=spec["record_id"].split(":")[-1],
        )
        pre_row = dict(applied_row)
        if spec["record_id"] == "aptamerbase:0001":
            pre_row["sequence_core"] = spec["seq"]
            pre_row["sequence_length_core"] = str(len(spec["seq"]))
            pre_row["trim_status"] = "no_constants_detected"
        applied.append(applied_row)
        mutated_prereview.append(pre_row)
        resolutions.append(
            {
                "record_id": spec["record_id"],
                "proposed_decision": f"proposed_{spec['resolved']}",
                "resolved_decision": spec["resolved"],
                "checkpoint1_resolution_status": spec["status"],
                "authorised_for_s4": spec["auth"],
            }
        )
        if spec["auth"] == "true":
            authorised.append(spec["record_id"])

    applied_path = applied_dir / "aptamerbase_checkpoint1_applied_canonical.csv"
    _write_csv(applied_path, list(CORPUS_COLUMNS), applied)
    _write_csv(pre_review, list(CORPUS_COLUMNS), mutated_prereview)
    res_path = repo / "config/checkpoint_reviews/demo_checkpoint1_resolutions.csv"
    _write_csv(res_path, RESOLUTION_COLUMNS, resolutions)
    auth_path = applied_dir / "aptamerbase_checkpoint1_s4_authorised_ids.csv"
    _write_csv(
        auth_path,
        AUTH_ID_COLUMNS,
        [
            {
                "record_id": record_id,
                "resolved_decision": "accept",
                "checkpoint1_resolution_status": "approved_for_s4",
            }
            for record_id in authorised
        ],
    )
    _write_csv(
        sidecar_dir / "aptamerbase_source_metadata.csv",
        APTAMERBASE_SIDECAR_COLUMNS,
        [_aptamerbase_sidecar_row(spec) for spec in specs],
    )
    _write_csv(
        qc_dir / "aptamerbase_s2_qc.csv",
        APTAMERBASE_QC_COLUMNS,
        [_aptamerbase_qc_row(spec) for spec in specs],
    )

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["source_key"] = "aptamerbase"
    payload["source_dataset"] = "aptamerbase_export_2026-06-24"
    payload["canonical_input"] = (
        "data/interim/checkpoints/aptamerbase_cp1/resolved/"
        "aptamerbase_checkpoint1_applied_canonical.csv"
    )
    payload["authorised_ids_input"] = (
        "data/interim/checkpoints/aptamerbase_cp1/resolved/"
        "aptamerbase_checkpoint1_s4_authorised_ids.csv"
    )
    payload["expected_authorised_records"] = expected
    payload["global_s4_run"] = False
    payload["physical_row_join_key"] = "record_id"
    payload["emit_target_evidence_boundary"] = True
    payload["emit_source_metadata_only_disclaimer"] = True
    payload["handoff_extra_fields"] = list(APTAMERBASE_EXTRA_FIELDS)
    payload["additional_source_metadata_joins"] = [
        {
            "path": "data/interim/normalised/aptamerbase_s2_qc.csv",
            "fields": [
                "source_object_type",
                "molecule_evidence_source",
                "rdf_has_rna",
                "rdf_has_dna",
                "rdf_has_modified_nucleic_acid",
            ],
        }
    ]
    payload["required_nonempty_handoff_fields"] = ["aptamerbase_id"]
    payload["require_empty_canonical_fields"] = [
        "target_name_raw",
        "target_name",
        "target_uniprot",
        "target_type",
        "target_type_source",
        "target_family",
        "target_pfam",
        "pdb_id",
        "binding_evidence_type",
        "binding_evidence_score",
        "affinity_value",
        "affinity_unit",
        "affinity_type",
        "cluster_id",
        "is_cluster_representative",
        "partition",
    ]
    payload["handoff_summary_provenance_counts"] = {
        "trim_status_value": "t7_removed",
        "report_duplicate_sequence_identities": True,
        "unique_count_fields": ["aptamerbase_id"],
        "duplicate_group_fields": ["aptamerbase_id"],
        "nonempty_count_fields": [
            "aptamerbase_label",
            "aptamerbase_has_minimal_aptamer",
            "aptamerbase_is_minimal_aptamer_of",
        ],
        "true_value_count_fields": [
            "aptamerbase_has_experimentally_determined_structure",
            "rdf_has_rna",
        ],
        "value_count_fields": ["molecule_type", "chemistry", "source_object_type"],
    }
    payload["handoff_summary_count_labels"] = {
        "unique_aptamerbase_id": "unique Freebase IDs",
        "duplicate_aptamerbase_id_groups": "duplicated Freebase-ID groups",
        "duplicate_aptamerbase_id_rows": "rows in duplicated Freebase-ID groups",
    }
    payload["handoff_summary_additional_notes"] = [
        "authorised_for_s4=true / inclusion in this handoff means only technically eligible after AptamerBase sequence/molecule/chemistry/construct review.",
        "Canonical target_name_raw is deliberately empty.",
        "Global S4 has not been run.",
    ]
    payload["handoff_ready_statement"] = (
        "AptamerBase CHECKPOINT-1 is closed and this source is prepared as "
        "one input to the future corpus-wide global S4 stage. Global S4 has "
        "not been run."
    )
    payload["future_enrichment_join"] = {
        "physical_row_key": "record_id",
        "source_freebase_id_field": "aptamerbase_id",
        "join_path": (
            "record_id -> S1 sidecar AptamerBase Freebase ID -> "
            "AptamerBase interaction/experiment graph/tables"
        ),
        "freebase_id_is_not": ["record_id", "native_id", "target ID", "dedup key"],
    }
    payload["future_global_s4_prerequisites"] = [
        "Before AptamerBase target/evidence normalisation begins, hash-pin the original-authors interaction and experiment companion tables (or equivalent RDF graph representation) and join them by Freebase ID/interaction relationships."
    ]
    payload["target_metadata"]["source_metadata_path"] = (
        "data/interim/extracted/aptamerbase_source_metadata.csv"
    )
    payload["target_metadata"]["canonical_raw_field"] = "target_name_raw"
    payload["target_metadata"]["specific_target_present_in_authorised_records"] = 0
    payload["target_metadata"]["specific_target_missing_in_authorised_records"] = expected
    payload["global_s4_rules"]["final_target_normalisation_performed_here"] = False
    _write_json(config_path, payload)
    return repo, config_path


def test_aptamerbase_live_source_config_loads() -> None:
    path = REPO_ROOT / "config" / "global_s4_sources" / "aptamerbase.json"
    config = load_source_config(path)
    assert config["source_key"] == "aptamerbase"
    assert config["source_dataset"] == "aptamerbase_export_2026-06-24"
    assert config["expected_authorised_records"] == 881
    assert config["authorisation_field"] == "authorised_for_s4"
    assert config["checkpoint_status"] == "closed"
    assert config["global_s4_run"] is False
    assert config["physical_row_join_key"] == "record_id"
    assert config["canonical_input"].endswith(
        "aptamerbase_checkpoint1_applied_canonical.csv"
    )
    assert "resolved/" in config["canonical_input"]
    assert "aptamerbase_s3_canonical.csv" not in config["canonical_input"]
    assert "aptamerbase_id" in config["handoff_extra_fields"]
    assert "aptamerbase_label" in config["handoff_extra_fields"]
    assert "aptamerbase_sequence" not in config["handoff_extra_fields"]
    assert "target_name_raw" in config["require_empty_canonical_fields"]
    assert config["required_nonempty_handoff_fields"] == ["aptamerbase_id"]
    extra_join_fields = config["additional_source_metadata_joins"][0]["fields"]
    assert "rdf_has_rna" in extra_join_fields
    assert "rdf_has_modified_nucleic_acid" in extra_join_fields
    assert "aptamerbase_interactions.csv" not in path.read_text(encoding="utf-8")
    assert "aptamerbase_experiments.csv" not in path.read_text(encoding="utf-8")
    rules = config["global_s4_rules"]
    assert rules["final_target_normalisation_performed_here"] is False
    assert rules["evidence_threshold_performed_here"] is False
    text = path.read_text(encoding="utf-8")
    assert SEQ_LEAK_RE.search(text) is None


def test_aptamerbase_selects_only_authorised_and_excludes_parks(
    tmp_path: Path,
) -> None:
    repo, config_path = _aptamerbase_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    rows = list(csv.DictReader(result.output_csv.open(encoding="utf-8")))
    ids = [row["record_id"] for row in rows]
    assert ids == [
        "aptamerbase:0001",
        "aptamerbase:0002",
        "aptamerbase:0003",
        "aptamerbase:0004",
    ]
    assert "aptamerbase:ss01" not in ids
    assert "aptamerbase:unk1" not in ids
    assert "aptamerbase:ch01" not in ids
    assert "aptamerbase:st01" not in ids
    assert result.stats.handoff_records == 4
    assert len({row["record_id"] for row in rows}) == 4


def test_aptamerbase_uses_applied_canonical_not_prereview_s3(
    tmp_path: Path,
) -> None:
    repo, config_path = _aptamerbase_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    by_id = {
        row["record_id"]: row
        for row in csv.DictReader(result.output_csv.open(encoding="utf-8"))
    }
    assert by_id["aptamerbase:0001"]["sequence_core"] == "GUAC"
    assert by_id["aptamerbase:0001"]["trim_status"] == "t7_removed"
    pre = {
        row["record_id"]: row
        for row in csv.DictReader(
            (
                repo
                / "data/interim/checkpoints/aptamerbase_cp1/aptamerbase_s3_canonical.csv"
            ).open(encoding="utf-8")
        )
    }
    assert pre["aptamerbase:0001"]["sequence_core"] == "ACGUACGU"
    assert by_id["aptamerbase:0001"]["sequence_core"] != pre[
        "aptamerbase:0001"
    ]["sequence_core"]


def test_aptamerbase_freebase_id_required_and_nonempty(tmp_path: Path) -> None:
    repo, config_path = _aptamerbase_handoff_tree(tmp_path)
    sidecar = repo / "data/interim/extracted/aptamerbase_source_metadata.csv"
    rows = list(csv.DictReader(sidecar.open(encoding="utf-8")))
    for row in rows:
        if row["record_id"] == "aptamerbase:0002":
            row["aptamerbase_id"] = ""
    _write_csv(sidecar, APTAMERBASE_SIDECAR_COLUMNS, rows)
    with pytest.raises(GlobalS4HandoffError, match="required and nonempty"):
        _run(repo, config_path)


def test_aptamerbase_sidecar_join_is_one_to_one_by_record_id(
    tmp_path: Path,
) -> None:
    repo, config_path = _aptamerbase_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    rows = list(csv.DictReader(result.output_csv.open(encoding="utf-8")))
    by_id = {row["record_id"]: row for row in rows}
    assert by_id["aptamerbase:0001"]["aptamerbase_label"] == "demo-label-1"
    assert by_id["aptamerbase:0002"]["rdf_has_rna"] == "true"
    assert by_id["aptamerbase:0002"]["source_object_type"] == "aptamer"
    assert by_id["aptamerbase:0003"]["chemistry"] == "2NH2-RNA"
    assert "aptamerbase_sequence" not in by_id["aptamerbase:0001"]


def test_aptamerbase_repeated_freebase_ids_do_not_collapse_rows(
    tmp_path: Path,
) -> None:
    repo, config_path = _aptamerbase_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    rows = list(csv.DictReader(result.output_csv.open(encoding="utf-8")))
    assert len(rows) == 4
    freebases = [row["aptamerbase_id"] for row in rows]
    assert freebases.count("http://rdf.freebase.com/ns/m.aaa") == 2
    assert rows[0]["record_id"] != rows[1]["record_id"]
    text = result.output_summary.read_text(encoding="utf-8")
    assert "unique Freebase IDs = `3`" in text
    assert "duplicated Freebase-ID groups = `1`" in text
    assert "physical rows were not collapsed" in text


def test_aptamerbase_minimal_aptamer_relationships_preserved(
    tmp_path: Path,
) -> None:
    repo, config_path = _aptamerbase_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    by_id = {
        row["record_id"]: row
        for row in csv.DictReader(result.output_csv.open(encoding="utf-8"))
    }
    assert by_id["aptamerbase:0001"]["aptamerbase_has_minimal_aptamer"] == (
        "http://rdf.freebase.com/ns/m.ccc"
    )
    assert by_id["aptamerbase:0002"]["aptamerbase_is_minimal_aptamer_of"] == (
        "http://rdf.freebase.com/ns/m.aaa"
    )
    assert by_id["aptamerbase:0001"]["cluster_id"] == ""
    assert by_id["aptamerbase:0002"]["near_duplicate_family_id"] == ""


def test_aptamerbase_label_does_not_populate_target_name_raw(
    tmp_path: Path,
) -> None:
    repo, config_path = _aptamerbase_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    for row in csv.DictReader(result.output_csv.open(encoding="utf-8")):
        assert row["target_name_raw"] == ""
        assert row["aptamerbase_label"] != row["target_name_raw"] or row[
            "aptamerbase_label"
        ] == ""


def test_aptamerbase_s4_target_evidence_fields_remain_empty(
    tmp_path: Path,
) -> None:
    repo, config_path = _aptamerbase_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    for row in csv.DictReader(result.output_csv.open(encoding="utf-8")):
        assert row["target_name_raw"] == ""
        assert row["target_name"] == ""
        assert row["target_uniprot"] == ""
        assert row["target_type"] == ""
        assert row["target_type_source"] == ""
        assert row["target_family"] == ""
        assert row["target_pfam"] == ""
        assert row["pdb_id"] == ""
        assert row["binding_evidence_type"] == ""
        assert row["binding_evidence_score"] == ""
        assert row["affinity_value"] == ""
        assert row["affinity_unit"] == ""
        assert row["affinity_type"] == ""
        assert row["cluster_id"] == ""
        assert row["is_cluster_representative"] == ""
        assert row["partition"] == ""


def test_aptamerbase_excludes_ssdna_unknown_molecule_chemistry_parks(
    tmp_path: Path,
) -> None:
    repo, config_path = _aptamerbase_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    rows = list(csv.DictReader(result.output_csv.open(encoding="utf-8")))
    assert all(row["molecule_type"] != "ssDNA" for row in rows)
    assert all(row["molecule_type"] != "unknown" for row in rows)
    assert all(row["chemistry"] != "unknown" for row in rows)
    assert all(row["source_object_type"] == "aptamer" for row in rows)


def test_aptamerbase_retains_reviewed_chemistries_and_trim(
    tmp_path: Path,
) -> None:
    repo, config_path = _aptamerbase_handoff_tree(tmp_path)
    result = _run(repo, config_path)
    by_id = {
        row["record_id"]: row
        for row in csv.DictReader(result.output_csv.open(encoding="utf-8"))
    }
    assert by_id["aptamerbase:0001"]["chemistry"] == "RNA"
    assert by_id["aptamerbase:0002"]["chemistry"] == "2F-RNA"
    assert by_id["aptamerbase:0003"]["chemistry"] == "2NH2-RNA"
    assert by_id["aptamerbase:0004"]["chemistry"] == "mixed"
    assert by_id["aptamerbase:0001"]["sequence_core"] == "GUAC"
    assert by_id["aptamerbase:0001"]["trim_status"] == "t7_removed"
    trimmed = [
        row for row in by_id.values() if row["trim_status"] == "t7_removed"
    ]
    assert len(trimmed) == 1
    text = result.output_summary.read_text(encoding="utf-8")
    assert "`chemistry` `RNA` = `1`" in text
    assert "`chemistry` `2F-RNA` = `1`" in text
    assert "`chemistry` `2NH2-RNA` = `1`" in text
    assert "`chemistry` `mixed` = `1`" in text
    assert "reviewed trimmed records = `1`" in text


def test_aptamerbase_sequence_bearing_sidecar_field_rejected(
    tmp_path: Path,
) -> None:
    repo, config_path = _aptamerbase_handoff_tree(tmp_path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["handoff_extra_fields"] = list(payload["handoff_extra_fields"]) + [
        "aptamerbase_sequence"
    ]
    _write_json(config_path, payload)
    with pytest.raises(GlobalS4HandoffError, match="sequence-bearing"):
        _run(repo, config_path)


def test_aptamerbase_handoff_deterministic(tmp_path: Path) -> None:
    repo, config_path = _aptamerbase_handoff_tree(tmp_path)
    first = _run(repo, config_path)
    h1 = _sha256(first.output_csv)
    h1s = _sha256(first.output_summary)
    second = _run(repo, config_path)
    assert _sha256(second.output_csv) == h1
    assert _sha256(second.output_summary) == h1s


def test_aptamerbase_does_not_invoke_global_s4(tmp_path: Path) -> None:
    import prepare_global_s4_source as mod

    assert not hasattr(mod, "run_global_s4")
    assert not hasattr(mod, "normalise_targets")
    assert not hasattr(mod, "score_evidence")
    repo, config_path = _aptamerbase_handoff_tree(tmp_path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["global_s4_run"] is False
    result = _run(repo, config_path)
    text = result.output_summary.read_text(encoding="utf-8")
    assert "Global S4 has not been run." in text
    assert SEQ_LEAK_RE.search(text) is None
    assert "SOURCE METADATA ONLY" in text
    assert "interaction and experiment companion tables" in text
    assert str(repo.resolve()) not in text


def test_aptamerbase_expected_count_mismatch_hard_fails(tmp_path: Path) -> None:
    repo, config_path = _aptamerbase_handoff_tree(tmp_path, expected=881)
    with pytest.raises(GlobalS4HandoffError, match="Expected 881"):
        _run(repo, config_path)


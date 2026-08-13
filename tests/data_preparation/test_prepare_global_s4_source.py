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

"""Tests for corpus-wide global-S4 combined-input concatenation (synthetic only).

Every literal nucleotide string in this file is shorter than 20 nt. Does not
read live source handoff CSVs or other biological artefacts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from combine_global_s4_input import (  # noqa: E402
    CombinedInputError,
    combine_global_s4_input,
    load_combined_config,
    main,
)
from common.corpus_schema import CORPUS_COLUMNS  # noqa: E402

SEQ_LEAK_RE = re.compile(r"[ACGTUacgtu]{20,}")
LIVE_CONTRACT = REPO_ROOT / "config" / "global_s4_combined_input.json"
EXPECTED_SOURCE_ORDER = [
    "aptabase",
    "utexas",
    "aptadb",
    "riboaptamer",
    "aptaindex",
    "ena",
    "aptamerbase",
    "ncbi_nuc",
]
EXPECTED_SOURCE_COUNTS = {
    "aptabase": 162,
    "utexas": 468,
    "aptadb": 151,
    "riboaptamer": 397,
    "aptaindex": 221,
    "ena": 675,
    "aptamerbase": 881,
    "ncbi_nuc": 5,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _empty_corpus(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in CORPUS_COLUMNS}
    row.update(overrides)
    return row


def _write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
    *,
    quoting: int = csv.QUOTE_MINIMAL,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            lineterminator="\n",
            quoting=quoting,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _source_pointer(source_key: str, expected: int) -> dict:
    return {
        "source_key": source_key,
        "canonical_input": f"data/interim/checkpoints/{source_key}_cp1/{source_key}.csv",
        "resolution_manifest": f"config/checkpoint_reviews/{source_key}.csv",
        "authorised_ids_input": (
            f"data/interim/checkpoints/{source_key}_cp1/ids.csv"
        ),
        "authorisation_field": "authorised_for_s4",
        "expected_authorised_records": expected,
        "global_s4_handoff_output": (
            f"data/interim/global_s4_ready/{source_key}_global_s4_input.csv"
        ),
    }


def _record(
    *,
    source_key: str,
    native_id: str,
    seq: str,
    extra: dict[str, str] | None = None,
    **overrides: str,
) -> dict[str, str]:
    row = _empty_corpus(
        record_id=f"{source_key}:{native_id}",
        sequence_raw=seq,
        sequence_full=seq,
        sequence_core=seq,
        sequence_length_full=str(len(seq)),
        sequence_length_core=str(len(seq)),
        molecule_type="RNA",
        alphabet_as_reported="RNA",
        t_to_u_applied="false",
        source_db=source_key,
        source_dataset=f"{source_key}_set",
        contributing_sources=source_key,
        contributing_datasets=f"{source_key}_set",
        corroboration_count="1",
        redistribution_status="unknown",
        independently_attested_by_permissive_source="false",
        native_id=native_id,
    )
    row.update(overrides)
    if extra:
        row.update(extra)
    return row


def _install_source(
    repo: Path,
    *,
    source_key: str,
    rows: list[dict[str, str]],
    extras: list[str],
    expected: int | None = None,
    quoting: int = csv.QUOTE_MINIMAL,
) -> None:
    count = expected if expected is not None else len(rows)
    _write_json(
        repo / "config" / "global_s4_sources" / f"{source_key}.json",
        _source_pointer(source_key, count),
    )
    columns = list(CORPUS_COLUMNS) + extras
    _write_csv(
        repo / "data/interim/global_s4_ready" / f"{source_key}_global_s4_input.csv",
        columns,
        rows,
        quoting=quoting,
    )


def _combined_config(
    sources: list[dict],
    *,
    expected: int,
    zeros: list[dict] | None = None,
) -> dict:
    return {
        "contract_id": "global_s4_combined_input",
        "combination_mode": "row_preserving_concatenation",
        "expected_combined_records": expected,
        "output_csv": "data/interim/global_s4/combined_global_s4_input.csv",
        "output_summary": "data/interim/global_s4/combined_global_s4_input_summary.md",
        "output_manifest": "data/interim/global_s4/combined_global_s4_input_manifest.json",
        "completeness_fields": [
            "target_name_raw",
            "target_name",
            "target_uniprot",
            "redistribution_status",
        ],
        "must_remain_empty_canonical_fields": [
            "target_name",
            "target_uniprot",
            "target_type",
            "binding_evidence_type",
            "affinity_value",
            "cluster_id",
            "is_cluster_representative",
            "partition",
        ],
        "contributing_sources": sources,
        "zero_authorised_sources": zeros or [],
        "scientific_boundary": {
            "target_extraction_performed_here": False,
            "cross_source_deduplication_performed_here": False,
        },
    }


def _source_entry(
    source_key: str,
    expected: int,
    *,
    extras: list[str] | None = None,
    prefix: str | None = None,
    redistribution: str | None = None,
) -> dict:
    item: dict = {
        "source_key": source_key,
        "source_config": f"config/global_s4_sources/{source_key}.json",
        "expected_records": expected,
        "record_id_prefix": prefix or f"{source_key}:",
        "principal_extra_fields": extras or [],
    }
    if redistribution is not None:
        item["require_redistribution_status"] = redistribution
    return item


def _run(repo: Path, config_path: Path):
    return combine_global_s4_input(
        combined_config=config_path,
        repo_root=repo,
    )


def test_live_contract_is_sequence_safe_and_explicitly_ordered() -> None:
    payload = json.loads(LIVE_CONTRACT.read_text(encoding="utf-8"))
    assert payload["expected_combined_records"] == 2960
    keys = [item["source_key"] for item in payload["contributing_sources"]]
    assert keys == EXPECTED_SOURCE_ORDER
    counts = {
        item["source_key"]: item["expected_records"]
        for item in payload["contributing_sources"]
    }
    assert counts == EXPECTED_SOURCE_COUNTS
    assert sum(counts.values()) == 2960
    zeros = [item["source_key"] for item in payload["zero_authorised_sources"]]
    assert zeros == ["aptadiff_a", "aptadiff_b"]
    for item in payload["zero_authorised_sources"]:
        assert item["expected_records"] == 0
        assert item["contribute_rows"] is False
    text = LIVE_CONTRACT.read_text(encoding="utf-8")
    assert SEQ_LEAK_RE.search(text) is None
    assert "sequence_raw" not in text


def test_configured_source_order_not_alphabetical(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    zeta = [
        _record(source_key="zeta", native_id="z1", seq="ACGUACGU", extra={"zeta_note": "z"}),
        _record(source_key="zeta", native_id="z2", seq="GGCCGGCC", extra={"zeta_note": "zz"}),
    ]
    alpha = [
        _record(
            source_key="alpha", native_id="a1", seq="UUGGAACC", extra={"alpha_note": "a"}
        )
    ]
    _install_source(repo, source_key="zeta", rows=zeta, extras=["zeta_note"])
    _install_source(repo, source_key="alpha", rows=alpha, extras=["alpha_note"])
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config(
            [
                _source_entry("zeta", 2, extras=["zeta_note"]),
                _source_entry("alpha", 1, extras=["alpha_note"]),
            ],
            expected=3,
            zeros=[
                {
                    "source_key": "empty_src",
                    "expected_records": 0,
                    "status": "ready_zero_authorised",
                    "contribute_rows": False,
                }
            ],
        ),
    )
    result = _run(repo, config_path)
    rows = list(csv.DictReader(result.output_csv.open(encoding="utf-8", newline="")))
    assert [row["record_id"] for row in rows] == [
        "zeta:z1",
        "zeta:z2",
        "alpha:a1",
    ]
    assert list(rows[0].keys())[: len(CORPUS_COLUMNS)] == list(CORPUS_COLUMNS)
    assert list(rows[0].keys())[len(CORPUS_COLUMNS) :] == ["zeta_note", "alpha_note"]
    assert result.source_boundaries["zeta"] == {
        "start_row": 1,
        "end_row": 2,
        "records": 2,
    }
    assert result.source_boundaries["alpha"] == {
        "start_row": 3,
        "end_row": 3,
        "records": 1,
    }


def test_within_source_handoff_order_is_preserved(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    rows = [
        _record(source_key="src", native_id="later", seq="CCGGAAUU"),
        _record(source_key="src", native_id="earlier", seq="AAUUGGCC"),
    ]
    _install_source(repo, source_key="src", rows=rows, extras=[])
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config([_source_entry("src", 2)], expected=2),
    )
    result = _run(repo, config_path)
    loaded = list(csv.DictReader(result.output_csv.open(encoding="utf-8", newline="")))
    assert [row["record_id"] for row in loaded] == ["src:later", "src:earlier"]


def test_exact_source_count_reconciliation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    left = [_record(source_key="left", native_id="1", seq="ACGUACGU")]
    right = [
        _record(source_key="right", native_id="1", seq="GGCCGGCC"),
        _record(source_key="right", native_id="2", seq="UUGGAACC"),
    ]
    _install_source(repo, source_key="left", rows=left, extras=[])
    _install_source(repo, source_key="right", rows=right, extras=[])
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config(
            [_source_entry("left", 1), _source_entry("right", 2)],
            expected=3,
        ),
    )
    result = _run(repo, config_path)
    assert result.combined_rows == 3
    assert result.unique_ids == 3


def test_aggregate_expected_count_mismatch_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _install_source(
        repo,
        source_key="src",
        rows=[_record(source_key="src", native_id="1", seq="ACGUACGU")],
        extras=[],
    )
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config([_source_entry("src", 1)], expected=2),
    )
    with pytest.raises(CombinedInputError, match="expected_combined_records"):
        load_combined_config(config_path)


def test_duplicate_record_id_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    left = [_record(source_key="left", native_id="same", seq="ACGUACGU")]
    right = [_record(source_key="right", native_id="same", seq="GGCCGGCC")]
    right[0]["record_id"] = "left:same"
    _install_source(repo, source_key="left", rows=left, extras=[])
    _install_source(repo, source_key="right", rows=right, extras=[])
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config(
            [
                _source_entry("left", 1, prefix="left:"),
                _source_entry("right", 1, prefix="left:"),
            ],
            expected=2,
        ),
    )
    with pytest.raises(CombinedInputError, match="collision"):
        _run(repo, config_path)


def test_incorrect_source_db_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    row = _record(source_key="src", native_id="1", seq="ACGUACGU")
    row["source_db"] = "other"
    _install_source(repo, source_key="src", rows=[row], extras=[])
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config([_source_entry("src", 1)], expected=1),
    )
    with pytest.raises(CombinedInputError, match="source_db"):
        _run(repo, config_path)


def test_canonical_columns_are_copied_exactly(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    row = _record(
        source_key="src",
        native_id="1",
        seq="ACGUACGU",
        target_name_raw="Raw Target",
        publication="Paper 1",
        qc_flags="flag_a",
        notes="keep me",
    )
    _install_source(repo, source_key="src", rows=[row], extras=[])
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config([_source_entry("src", 1)], expected=1),
    )
    result = _run(repo, config_path)
    loaded = list(csv.DictReader(result.output_csv.open(encoding="utf-8", newline="")))
    for column in CORPUS_COLUMNS:
        assert loaded[0][column] == row[column]


def test_source_specific_extra_column_union(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    left = [
        _record(
            source_key="left",
            native_id="1",
            seq="ACGUACGU",
            extra={"left_kd": "12.5"},
        )
    ]
    right = [
        _record(
            source_key="right",
            native_id="1",
            seq="GGCCGGCC",
            extra={"right_type": "protein"},
        )
    ]
    _install_source(repo, source_key="left", rows=left, extras=["left_kd"])
    _install_source(repo, source_key="right", rows=right, extras=["right_type"])
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config(
            [
                _source_entry("left", 1, extras=["left_kd"]),
                _source_entry("right", 1, extras=["right_type"]),
            ],
            expected=2,
        ),
    )
    result = _run(repo, config_path)
    loaded = list(csv.DictReader(result.output_csv.open(encoding="utf-8", newline="")))
    extras = list(loaded[0].keys())[len(CORPUS_COLUMNS) :]
    assert extras == ["left_kd", "right_type"]
    assert loaded[0]["left_kd"] == "12.5"
    assert loaded[0]["right_type"] == ""
    assert loaded[1]["left_kd"] == ""
    assert loaded[1]["right_type"] == "protein"


def test_incompatible_extra_column_collision_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    left = [
        _record(
            source_key="left",
            native_id="1",
            seq="ACGUACGU",
            extra={"shared_meta": "from-left"},
        )
    ]
    right = [
        _record(
            source_key="right",
            native_id="1",
            seq="GGCCGGCC",
            extra={"shared_meta": "from-right"},
        )
    ]
    _install_source(repo, source_key="left", rows=left, extras=["shared_meta"])
    _install_source(repo, source_key="right", rows=right, extras=["shared_meta"])
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config(
            [
                _source_entry("left", 1, extras=["shared_meta"]),
                _source_entry("right", 1, extras=["shared_meta"]),
            ],
            expected=2,
        ),
    )
    with pytest.raises(CombinedInputError, match="collision"):
        _run(repo, config_path)


def test_missing_required_handoff_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_json(
        repo / "config" / "global_s4_sources" / "src.json",
        _source_pointer("src", 1),
    )
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config([_source_entry("src", 1)], expected=1),
    )
    with pytest.raises(CombinedInputError, match="Missing required source handoff"):
        _run(repo, config_path)


def test_zero_authorised_sources_do_not_fabricate_rows(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    rows = [_record(source_key="src", native_id="1", seq="ACGUACGU")]
    _install_source(repo, source_key="src", rows=rows, extras=[])
    decoy = [
        _record(source_key="empty_src", native_id="decoy", seq="UUUUAAAA")
    ]
    _write_csv(
        repo / "data/interim/global_s4_ready/empty_src_global_s4_input.csv",
        list(CORPUS_COLUMNS),
        decoy,
    )
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config(
            [_source_entry("src", 1)],
            expected=1,
            zeros=[
                {
                    "source_key": "empty_src",
                    "expected_records": 0,
                    "status": "ready_zero_authorised",
                    "contribute_rows": False,
                }
            ],
        ),
    )
    result = _run(repo, config_path)
    loaded = list(csv.DictReader(result.output_csv.open(encoding="utf-8", newline="")))
    assert len(loaded) == 1
    assert loaded[0]["record_id"] == "src:1"
    text = result.output_summary.read_text(encoding="utf-8")
    assert "`empty_src` = `0`" in text
    assert "no rows fabricated" in text
    assert "empty_src:decoy" not in text


def test_deterministic_byte_identical_rerun(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    rows = [
        _record(
            source_key="src",
            native_id="1",
            seq="ACGUACGU",
            extra={"src_note": "hello"},
        )
    ]
    _install_source(repo, source_key="src", rows=rows, extras=["src_note"])
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config(
            [_source_entry("src", 1, extras=["src_note"])],
            expected=1,
        ),
    )
    first = _run(repo, config_path)
    csv_bytes = first.output_csv.read_bytes()
    summary_bytes = first.output_summary.read_bytes()
    manifest_bytes = first.output_manifest.read_bytes()
    second = _run(repo, config_path)
    assert second.output_csv.read_bytes() == csv_bytes
    assert second.output_summary.read_bytes() == summary_bytes
    assert second.output_manifest.read_bytes() == manifest_bytes
    assert first.csv_sha256 == second.csv_sha256 == _sha256(first.output_csv)


def test_embedded_cr_quoting_round_trip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    row = _record(
        source_key="idx",
        native_id="1",
        seq="ACGUACGU",
        extra={"idx_ref": "line1\rstill same record"},
        redistribution_status="restricted",
    )
    _install_source(
        repo,
        source_key="idx",
        rows=[row],
        extras=["idx_ref"],
        quoting=csv.QUOTE_ALL,
    )
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config(
            [
                _source_entry(
                    "idx",
                    1,
                    extras=["idx_ref"],
                    redistribution="restricted",
                )
            ],
            expected=1,
        ),
    )
    result = _run(repo, config_path)
    with result.output_csv.open("r", encoding="utf-8", newline="") as handle:
        loaded = list(csv.DictReader(handle))
    assert len(loaded) == 1
    assert loaded[0]["idx_ref"] == "line1\rstill same record"
    assert loaded[0]["redistribution_status"] == "restricted"


def test_canonical_s4_fields_not_populated_from_source_extras(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    row = _record(
        source_key="db",
        native_id="1",
        seq="ACGUACGU",
        extra={
            "db_uniprot_id": "P12345",
            "db_affinity": "3 nM",
            "db_pdb": "1ABC",
        },
        target_name_raw="Protein X",
    )
    _install_source(
        repo,
        source_key="db",
        rows=[row],
        extras=["db_uniprot_id", "db_affinity", "db_pdb"],
    )
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config(
            [
                _source_entry(
                    "db",
                    1,
                    extras=["db_uniprot_id", "db_affinity", "db_pdb"],
                )
            ],
            expected=1,
        ),
    )
    result = _run(repo, config_path)
    loaded = list(csv.DictReader(result.output_csv.open(encoding="utf-8", newline="")))
    assert loaded[0]["db_uniprot_id"] == "P12345"
    assert loaded[0]["db_affinity"] == "3 nM"
    assert loaded[0]["db_pdb"] == "1ABC"
    assert loaded[0]["target_uniprot"] == ""
    assert loaded[0]["affinity_value"] == ""
    assert loaded[0]["pdb_id"] == ""
    assert loaded[0]["target_name"] == ""
    assert loaded[0]["binding_evidence_type"] == ""


def test_provenance_fields_are_not_globally_altered(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    left = [
        _record(
            source_key="left",
            native_id="1",
            seq="ACGUACGU",
            contributing_sources="left",
            corroboration_count="1",
        )
    ]
    right = [
        _record(
            source_key="right",
            native_id="1",
            seq="ACGUACGU",
            contributing_sources="right",
            corroboration_count="1",
        )
    ]
    _install_source(repo, source_key="left", rows=left, extras=[])
    _install_source(repo, source_key="right", rows=right, extras=[])
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config(
            [_source_entry("left", 1), _source_entry("right", 1)],
            expected=2,
        ),
    )
    result = _run(repo, config_path)
    loaded = list(csv.DictReader(result.output_csv.open(encoding="utf-8", newline="")))
    assert loaded[0]["contributing_sources"] == "left"
    assert loaded[1]["contributing_sources"] == "right"
    assert loaded[0]["corroboration_count"] == "1"
    assert loaded[1]["corroboration_count"] == "1"
    text = result.output_summary.read_text(encoding="utf-8")
    assert "contributing_sources remains the source-local handoff value" in text
    assert "corroboration_count was not increased" in text
    assert "diagnostic only — no cross-source deduplication performed" in text
    assert SEQ_LEAK_RE.search(text) is None
    manifest = json.loads(result.output_manifest.read_text(encoding="utf-8"))
    assert SEQ_LEAK_RE.search(json.dumps(manifest)) is None


def test_cli_writes_combined_input(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    rows = [_record(source_key="src", native_id="1", seq="ACGUACGU")]
    _install_source(repo, source_key="src", rows=rows, extras=[])
    config_path = repo / "config" / "global_s4_combined_input.json"
    _write_json(
        config_path,
        _combined_config([_source_entry("src", 1)], expected=1),
    )
    assert (
        main(
            [
                "--combined-config",
                str(config_path),
                "--repo-root",
                str(repo),
            ]
        )
        == 0
    )
    output = repo / "data/interim/global_s4/combined_global_s4_input.csv"
    assert output.is_file()
    loaded = list(csv.DictReader(output.open(encoding="utf-8", newline="")))
    assert len(loaded) == 1

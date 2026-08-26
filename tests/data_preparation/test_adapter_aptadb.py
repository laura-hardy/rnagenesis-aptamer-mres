"""Tests for the AptaDB S1 adapter (synthetic fixtures only, plus optional aggregates)."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadb import (  # noqa: E402
    APTAMER_LEADING_COLUMNS,
    APTAMER_TRAILING_COLUMNS,
    INTERACTION_LEADING_COLUMNS,
    PROTEIN_INPUT_COLUMNS,
    SIDECAR_COLUMNS,
    AptaDBAdapterError,
    extract_aptadb,
)
from common.corpus_schema import S1_FORBIDDEN_FIELDS  # noqa: E402
from s0_build_registry import REQUIRED_COLUMNS  # noqa: E402
from s1_extract import S1ExtractError, run_s1_extraction  # noqa: E402

INTERACTION_COLUMNS = list(INTERACTION_LEADING_COLUMNS) + [""]
APTAMER_COLUMNS = (
    list(APTAMER_LEADING_COLUMNS)
    + ["Molarity of 1 ug/ul solution"]
    + list(APTAMER_TRAILING_COLUMNS)
)


def _hash_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            lineterminator="\n",
            extrasaction="raise",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _blank_interaction(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in INTERACTION_COLUMNS}
    row.update(overrides)
    return row


def _blank_aptamer(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in APTAMER_COLUMNS}
    row.update(overrides)
    return row


def _blank_protein(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in PROTEIN_INPUT_COLUMNS}
    row.update(overrides)
    return row


def _write_triplet(
    tmp_path: Path,
    *,
    interactions: list[dict[str, str]],
    aptamers: list[dict[str, str]],
    proteins: list[dict[str, str]],
) -> tuple[Path, Path, Path]:
    interaction_path = tmp_path / "interaction.csv"
    aptamer_path = tmp_path / "aptamer.csv"
    protein_path = tmp_path / "protein.csv"
    _write_csv(interaction_path, INTERACTION_COLUMNS, interactions)
    _write_csv(aptamer_path, APTAMER_COLUMNS, aptamers)
    _write_csv(protein_path, list(PROTEIN_INPUT_COLUMNS), proteins)
    return interaction_path, aptamer_path, protein_path


def _extract(
    tmp_path: Path,
    *,
    interactions: list[dict[str, str]],
    aptamers: list[dict[str, str]],
    proteins: list[dict[str, str]],
):
    i_path, a_path, p_path = _write_triplet(
        tmp_path,
        interactions=interactions,
        aptamers=aptamers,
        proteins=proteins,
    )
    return extract_aptadb(
        interaction_path=i_path,
        aptamer_path=a_path,
        protein_path=p_path,
        source_dataset="aptadb_demo",
        redistribution_status="unknown",
        expected_interaction_rows=len(interactions),
        expected_aptamer_rows=len(aptamers),
        expected_protein_rows=len(proteins),
    )


def _protein_pair() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    aptamer = _blank_aptamer(
        Apta_index="Apta_1",
        Sequence="ACGUACGU",
        **{"Aptamer Chemistry": "RNA"},
        **{"Aptamer description": "demo RNA"},
    )
    protein = _blank_protein(
        **{"Uni-port ID": "P00001"},
        **{"Protein names": "Demo protein"},
        **{"Entry name": "DEMO_HUMAN"},
    )
    interaction = _blank_interaction(
        Index="1",
        Apta_index="Apta_1",
        TargetID="P00001",
        Sequence="ACGUACGU",
        **{"Target chemistry": "Protein"},
        **{"Reference(pubmed ID)": "11111111"},
        **{"Binding Conditions/Buffer": "PBS"},
    )
    return interaction, aptamer, protein


def test_unique_index_becomes_unique_record_id(tmp_path: Path) -> None:
    interaction, aptamer, protein = _protein_pair()
    second = _blank_interaction(
        Index="2",
        Apta_index="Apta_1",
        TargetID="P00001",
        Sequence="ACGUACGU",
        **{"Target chemistry": "Protein"},
        **{"Reference(pubmed ID)": "22222222"},
    )
    result = _extract(
        tmp_path,
        interactions=[interaction, second],
        aptamers=[aptamer],
        proteins=[protein],
    )
    assert [row["record_id"] for row in result.canonical_rows] == [
        "aptadb:1",
        "aptadb:2",
    ]
    assert [row["native_id"] for row in result.canonical_rows] == ["1", "2"]
    assert result.stats.unique_record_ids == 2


def test_aptamer_join_success_uses_aptamer_sequence(tmp_path: Path) -> None:
    interaction, aptamer, protein = _protein_pair()
    result = _extract(
        tmp_path,
        interactions=[interaction],
        aptamers=[aptamer],
        proteins=[protein],
    )
    assert result.canonical_rows[0]["sequence_raw"] == "ACGUACGU"
    assert result.sidecar_rows[0]["aptadb_aptamer_sequence"] == "ACGUACGU"
    assert result.sidecar_rows[0]["aptadb_sequence_agreement"] == "exact"
    assert result.stats.aptamer_joins == 1
    assert result.stats.failed_aptamer_joins == 0


def test_missing_aptamer_join_hard_fails(tmp_path: Path) -> None:
    interaction, aptamer, protein = _protein_pair()
    interaction["Apta_index"] = "Apta_missing"
    with pytest.raises(AptaDBAdapterError, match="does not join aptamer.csv"):
        _extract(
            tmp_path,
            interactions=[interaction],
            aptamers=[aptamer],
            proteins=[protein],
        )


def test_protein_join_success_copies_protein_names(tmp_path: Path) -> None:
    interaction, aptamer, protein = _protein_pair()
    result = _extract(
        tmp_path,
        interactions=[interaction],
        aptamers=[aptamer],
        proteins=[protein],
    )
    assert result.canonical_rows[0]["target_name_raw"] == "Demo protein"
    assert result.sidecar_rows[0]["aptadb_protein_join_status"] == "joined"
    assert result.sidecar_rows[0]["aptadb_target_name_source"] == "protein_names"
    assert result.sidecar_rows[0]["aptadb_uniprot_id"] == "P00001"


def test_missing_protein_join_hard_fails(tmp_path: Path) -> None:
    interaction, aptamer, protein = _protein_pair()
    interaction["TargetID"] = "P99999"
    with pytest.raises(AptaDBAdapterError, match="does not join protein.csv"):
        _extract(
            tmp_path,
            interactions=[interaction],
            aptamers=[aptamer],
            proteins=[protein],
        )


def test_sequence_disagreement_hard_fails(tmp_path: Path) -> None:
    interaction, aptamer, protein = _protein_pair()
    interaction["Sequence"] = "ACGUAAAA"
    with pytest.raises(AptaDBAdapterError, match="Sequence disagreement"):
        _extract(
            tmp_path,
            interactions=[interaction],
            aptamers=[aptamer],
            proteins=[protein],
        )


def test_duplicate_apta_target_pair_kept_separate_by_index(tmp_path: Path) -> None:
    aptamer = _blank_aptamer(Apta_index="Apta_9", Sequence="ACGTACGT")
    protein = _blank_protein(**{"Uni-port ID": "P00009"}, **{"Protein names": "X"})
    first = _blank_interaction(
        Index="10",
        Apta_index="Apta_9",
        TargetID="P00009",
        Sequence="ACGTACGT",
        **{"Target chemistry": "Protein"},
        **{"Reference(pubmed ID)": "1"},
    )
    second = _blank_interaction(
        Index="11",
        Apta_index="Apta_9",
        TargetID="P00009",
        Sequence="ACGTACGT",
        **{"Target chemistry": "Protein"},
        **{"Reference(pubmed ID)": "2"},
    )
    result = _extract(
        tmp_path,
        interactions=[first, second],
        aptamers=[aptamer],
        proteins=[protein],
    )
    assert result.stats.canonical_rows == 2
    assert {row["record_id"] for row in result.canonical_rows} == {
        "aptadb:10",
        "aptadb:11",
    }


def test_nonprotein_does_not_invent_target_name(tmp_path: Path) -> None:
    aptamer = _blank_aptamer(
        Apta_index="Apta_3",
        Sequence="ACGTACGT",
        **{"Aptamer Chemistry": "DNA"},
    )
    interaction = _blank_interaction(
        Index="3",
        Apta_index="Apta_3",
        TargetID="6140",
        Sequence="ACGTACGT",
        **{"Target chemistry": "Molecule"},
        **{"Reference(pubmed ID)": "333"},
    )
    result = _extract(
        tmp_path,
        interactions=[interaction],
        aptamers=[aptamer],
        proteins=[_blank_protein(**{"Uni-port ID": "P00001"})],
    )
    row = result.canonical_rows[0]
    assert row["target_name_raw"] == ""
    assert row["target_uniprot"] == ""
    assert result.sidecar_rows[0]["aptadb_target_id"] == "6140"
    assert (
        result.sidecar_rows[0]["aptadb_target_name_source"]
        == "unresolved_missing_lookup_table"
    )
    assert result.sidecar_rows[0]["aptadb_protein_join_status"] == "not_applicable"


def test_no_sequence_normalisation_at_s1(tmp_path: Path) -> None:
    raw = "acgt T"
    aptamer = _blank_aptamer(Apta_index="Apta_4", Sequence=raw)
    interaction = _blank_interaction(
        Index="4",
        Apta_index="Apta_4",
        TargetID="cell-1",
        Sequence=raw,
        **{"Target chemistry": "Cell"},
    )
    result = _extract(
        tmp_path,
        interactions=[interaction],
        aptamers=[aptamer],
        proteins=[_blank_protein(**{"Uni-port ID": "P00001"})],
    )
    assert result.canonical_rows[0]["sequence_raw"] == raw
    assert result.canonical_rows[0]["sequence_full"] == ""
    assert result.canonical_rows[0]["molecule_type"] == ""
    assert result.canonical_rows[0]["t_to_u_applied"] == ""


def test_unlinked_aptamer_reconciled_outside_canonical(tmp_path: Path) -> None:
    interaction, aptamer, protein = _protein_pair()
    unlinked = _blank_aptamer(
        Apta_index="Apta_99",
        Sequence="GGCCGGCC",
        **{"Aptamer Chemistry": "DNA"},
    )
    result = _extract(
        tmp_path,
        interactions=[interaction],
        aptamers=[aptamer, unlinked],
        proteins=[protein],
    )
    assert result.stats.canonical_rows == 1
    assert result.stats.unlinked_aptamers == 1
    assert result.unlinked_rows[0]["apta_index"] == "Apta_99"
    assert result.unlinked_rows[0]["planned_s3_reason"] == "missing_target"
    assert "aptadb:99" not in {row["record_id"] for row in result.canonical_rows}


def test_publication_not_filled_from_pmid(tmp_path: Path) -> None:
    interaction, aptamer, protein = _protein_pair()
    result = _extract(
        tmp_path,
        interactions=[interaction],
        aptamers=[aptamer],
        proteins=[protein],
    )
    assert result.canonical_rows[0]["pubmed_id"] == "11111111"
    assert result.canonical_rows[0]["publication"] == ""


def test_s1_forbidden_fields_remain_empty(tmp_path: Path) -> None:
    interaction, aptamer, protein = _protein_pair()
    result = _extract(
        tmp_path,
        interactions=[interaction],
        aptamers=[aptamer],
        proteins=[protein],
    )
    row = result.canonical_rows[0]
    for field in S1_FORBIDDEN_FIELDS:
        assert row[field] == "", field
    notes = json.loads(row["notes"])
    assert notes["aptamer_id"] == "Apta_1"


def test_unnamed_trailing_field_preserved(tmp_path: Path) -> None:
    interaction, aptamer, protein = _protein_pair()
    interaction[""] = "14571"
    result = _extract(
        tmp_path,
        interactions=[interaction],
        aptamers=[aptamer],
        proteins=[protein],
    )
    assert result.sidecar_rows[0]["aptadb_interaction_unnamed_trailing"] == "14571"
    assert result.stats.unnamed_trailing_nonempty == 1


def test_latin1_reader_used_for_non_utf8_aptamer_header(tmp_path: Path) -> None:
    interaction, aptamer, protein = _protein_pair()
    i_path, a_path, p_path = _write_triplet(
        tmp_path,
        interactions=[interaction],
        aptamers=[aptamer],
        proteins=[protein],
    )
    # Replace the ASCII molarity header token with a latin-1 micro-like byte.
    text = a_path.read_bytes().replace(
        b"Molarity of 1 ug/ul solution",
        b"Molarity of 1 " + bytes([0xA6]) + b"g/" + bytes([0xA6]) + b"l solution",
    )
    a_path.write_bytes(text)
    result = extract_aptadb(
        interaction_path=i_path,
        aptamer_path=a_path,
        protein_path=p_path,
        source_dataset="aptadb_demo",
        redistribution_status="unknown",
        expected_interaction_rows=1,
        expected_aptamer_rows=1,
        expected_protein_rows=1,
    )
    assert result.stats.canonical_rows == 1


def _install_aptadb_registry(
    repo: Path,
    *,
    interaction: Path,
    aptamer: Path,
    protein: Path,
) -> Path:
    spec = repo / "config" / "source_registry.csv"
    rows = []
    for path, n_rows in (
        (interaction, sum(1 for _ in interaction.open(encoding="utf-8")) - 1),
        (aptamer, sum(1 for _ in aptamer.open(encoding="utf-8")) - 1),
        (protein, sum(1 for _ in protein.open(encoding="utf-8")) - 1),
    ):
        rel = path.relative_to(repo).as_posix()
        rows.append(
            {
                "source_key": "aptadb",
                "source_dataset": "aptadb_official_export_2026-08",
                "path": rel,
                "sha256": _hash_path(path),
                "n_rows_expected": str(n_rows),
                "snapshot_date": "2026-08-04",
                "tier": "1",
                "redistribution_status": "unknown",
                "notes": "synthetic",
            }
        )
    _write_csv(spec, list(REQUIRED_COLUMNS), rows)
    return spec


def test_s1_runner_resolves_three_registered_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    raw = repo / "data" / "raw" / "AptaDB"
    raw.mkdir(parents=True)
    (repo / "data" / "interim" / "extracted").mkdir(parents=True)
    interaction, aptamer, protein = _protein_pair()
    unlinked = _blank_aptamer(Apta_index="Apta_7", Sequence="GGCC")
    _write_csv(raw / "interaction.csv", INTERACTION_COLUMNS, [interaction])
    _write_csv(raw / "aptamer.csv", APTAMER_COLUMNS, [aptamer, unlinked])
    _write_csv(raw / "protein.csv", list(PROTEIN_INPUT_COLUMNS), [protein])
    spec = _install_aptadb_registry(
        repo,
        interaction=raw / "interaction.csv",
        aptamer=raw / "aptamer.csv",
        protein=raw / "protein.csv",
    )
    result = run_s1_extraction(
        repo_root=repo,
        source_key="aptadb",
        registry_spec=spec,
        output_dir=Path("data/interim/extracted"),
        check_deterministic_rerun=True,
    )
    assert result.registered_paths == (
        "data/raw/AptaDB/interaction.csv",
        "data/raw/AptaDB/aptamer.csv",
        "data/raw/AptaDB/protein.csv",
    )
    assert result.stats.canonical_rows == 1
    assert result.output_unlinked is not None
    unlinked_rows = list(
        csv.DictReader(result.output_unlinked.open(encoding="utf-8", newline=""))
    )
    assert len(unlinked_rows) == 1
    assert unlinked_rows[0]["apta_index"] == "Apta_7"
    canonical = list(
        csv.DictReader(result.output_canonical.open(encoding="utf-8", newline=""))
    )
    assert canonical[0]["record_id"] == "aptadb:1"
    assert result.deterministic_rerun_ok is True
    report = result.output_report.read_text(encoding="utf-8")
    assert "ACGUACGU" not in report
    assert str(repo) not in report
    sidecar = list(
        csv.DictReader(result.output_sidecar.open(encoding="utf-8", newline=""))
    )
    assert list(sidecar[0].keys()) == list(SIDECAR_COLUMNS)


def test_s1_runner_single_file_sources_still_require_one_path(
    tmp_path: Path,
) -> None:
    """AptaBase/UTexas dispatch still rejects multi-file rows for those keys."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "data" / "raw" / "aptabase").mkdir(parents=True)
    (repo / "data" / "interim" / "extracted").mkdir(parents=True)
    first = repo / "data" / "raw" / "aptabase" / "a.csv"
    second = repo / "data" / "raw" / "aptabase" / "b.csv"
    _write_csv(first, ["record_id"], [{"record_id": "1"}])
    _write_csv(second, ["record_id"], [{"record_id": "2"}])
    _write_csv(
        repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            {
                "source_key": "aptabase",
                "source_dataset": "aptabase_demo_v1",
                "path": "data/raw/aptabase/a.csv",
                "sha256": _hash_path(first),
                "n_rows_expected": "1",
                "snapshot_date": "2026-08-05",
                "tier": "1",
                "redistribution_status": "unknown",
                "notes": "synthetic",
            },
            {
                "source_key": "aptabase",
                "source_dataset": "aptabase_demo_v1",
                "path": "data/raw/aptabase/b.csv",
                "sha256": _hash_path(second),
                "n_rows_expected": "1",
                "snapshot_date": "2026-08-05",
                "tier": "1",
                "redistribution_status": "unknown",
                "notes": "synthetic",
            },
        ],
    )
    with pytest.raises(S1ExtractError, match="expects a single registered path"):
        run_s1_extraction(
            repo_root=repo,
            source_key="aptabase",
            registry_spec=repo / "config" / "source_registry.csv",
            output_dir=Path("data/interim/extracted"),
        )


@pytest.mark.skipif(
    not (
        REPO_ROOT
        / "data/raw/AptaDB/interaction.csv"
    ).is_file(),
    reason="AptaDB raw exports are local-only",
)
def test_real_data_aggregate_assertions_without_sequences() -> None:
    interaction = REPO_ROOT / "data/raw/AptaDB/interaction.csv"
    aptamer = REPO_ROOT / "data/raw/AptaDB/aptamer.csv"
    protein = REPO_ROOT / "data/raw/AptaDB/protein.csv"
    result = extract_aptadb(
        interaction_path=interaction,
        aptamer_path=aptamer,
        protein_path=protein,
        source_dataset="aptadb_official_export_2026-08",
        redistribution_status="unknown",
    )
    assert result.stats.input_rows == 1350
    assert result.stats.canonical_rows == 1350
    assert result.stats.unique_record_ids == 1350
    assert result.stats.aptamer_joins == 1350
    assert result.stats.sequence_mismatches == 0
    assert result.stats.protein_interactions == 639
    assert result.stats.protein_joins == 639
    assert result.stats.proteins_represented == 194
    assert result.stats.unlinked_aptamers == 37
    assert result.stats.nonempty_publication == 0
    assert all(row["source_db"] == "aptadb" for row in result.canonical_rows)
    ids = [row["record_id"] for row in result.canonical_rows]
    assert ids[0] == "aptadb:1"
    assert ids[-1] == "aptadb:1350"
    assert len(set(ids)) == 1350

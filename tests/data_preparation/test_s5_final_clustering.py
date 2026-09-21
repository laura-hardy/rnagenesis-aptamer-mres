"""Synthetic tests for S5E leakage-safe final cluster construction.

Every literal nucleotide string in this file is shorter than 20 nt.
Tests do not read live biological S5 CSVs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s5_exact_dedup import scientific_identity_id  # noqa: E402
from adapters.s5_final_clustering import (  # noqa: E402
    AUTHORISED_PARAMETERS,
    FROZEN_CORPUS_DEDUP_NAME,
    MERGE_MMSEQS_ONLY,
    MERGE_MMSEQS_PLUS_ENA,
    S5FinalClusteringError,
    assemble_final_clustering,
    assert_not_frozen_s5_path,
    build_family_containment,
    compare_final_runs,
    derive_ena_must_link_cohort,
    enforce_authorised_parameters,
    membership_signature,
)
from adapters.s5_sequence_clustering import (  # noqa: E402
    build_cluster_rows,
    make_sequence_id,
    project_unique_sequence_cores,
    sequence_core_digest,
)


SEQ_A = "ACGUACGUAA"
SEQ_B = "UGCAUGCAUU"
SEQ_C = "GGAAUCCGAU"
SEQ_D = "CCUUAGGAUC"
SEQ_E = "AUAUCGGAUC"
assert all(len(seq) < 20 for seq in (SEQ_A, SEQ_B, SEQ_C, SEQ_D, SEQ_E))


def _identity(sequence_core: str, target: str) -> str:
    return scientific_identity_id(sequence_core, target)


def _corpus_row(
    *,
    sequence_core: str,
    target: str,
    record_id: str,
    source_db: str = "aptamerbase",
    **fields: str,
) -> dict[str, str]:
    identity = _identity(sequence_core, target)
    row = {
        "scientific_identity_id": identity,
        "record_id": record_id,
        "sequence_core": sequence_core,
        "canonical_target_name": target,
        "source_db": source_db,
        "contributing_sources": source_db,
        "member_count": "1",
        "cluster_id": "",
        "is_cluster_representative": "",
        "partition": "",
    }
    row.update(fields)
    return row


def _ena_membership(
    row: dict[str, str], family_id: str, size: str, *, experiment: str = "g1"
) -> dict[str, str]:
    return {
        "scientific_identity_id": row["scientific_identity_id"],
        "source_db": "ena",
        "sequence_core": row["sequence_core"],
        "canonical_target_name": row["canonical_target_name"],
        "experiment_group_id": experiment,
        "ena_effective_near_duplicate_family_id": family_id,
        "ena_effective_near_duplicate_family_size": size,
    }


def _fake_cluster_tsv(sequence_rows: list[dict[str, str]], groups: list[list[str]]) -> str:
    by_core = {row["sequence_core"]: row["sequence_id"] for row in sequence_rows}
    lines = []
    for group in groups:
        rep = by_core[group[0]]
        for member_core in group:
            lines.append(f"{rep}\t{by_core[member_core]}")
    return "\n".join(lines) + "\n"


def _mmseqs_rows(corpus: list[dict[str, str]], groups: list[list[str]]) -> list[dict[str, str]]:
    sequence_rows, _map = project_unique_sequence_cores(corpus)
    from adapters.s5_sequence_clustering import parse_mmseqs_cluster_tsv

    pairs = parse_mmseqs_cluster_tsv(
        _fake_cluster_tsv(sequence_rows, groups),
        input_sequence_ids=[row["sequence_id"] for row in sequence_rows],
    )
    return build_cluster_rows(pairs, sequence_rows)


def test_two_mmseqs_clusters_linked_by_one_family_become_one_final_cluster() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="ena:2", source_db="ena"),
        _corpus_row(sequence_core=SEQ_C, target="VEGF", record_id="apt:1"),
    ]
    membership = [
        _ena_membership(rows[0], "ndfam_synthetic01", "2"),
        _ena_membership(rows[1], "ndfam_synthetic01", "2"),
    ]
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=_mmseqs_rows(rows, [[SEQ_A], [SEQ_B], [SEQ_C]]),
        membership_rows=membership,
    )
    assert result.diagnostics["n_mmseqs_clusters"] == 3
    assert result.diagnostics["n_final_clusters"] == 2
    by_core = {
        row["sequence_core_sha256"]: row["cluster_id"] for row in result.clusters_final
    }
    assert by_core[sequence_core_digest(SEQ_A)] == by_core[sequence_core_digest(SEQ_B)]
    assert by_core[sequence_core_digest(SEQ_C)] != by_core[sequence_core_digest(SEQ_A)]
    merged = next(
        row for row in result.cluster_summary if row["merge_basis"] == MERGE_MMSEQS_PLUS_ENA
    )
    assert merged["n_mmseqs_components"] == "2"
    assert "ndfam_synthetic01" in merged["ena_family_must_link_ids"]


def test_three_components_transitively_join() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="ena:2", source_db="ena"),
        _corpus_row(sequence_core=SEQ_C, target="EGFR", record_id="ena:3", source_db="ena"),
        _corpus_row(sequence_core=SEQ_D, target="VEGF", record_id="apt:1"),
    ]
    membership = [
        _ena_membership(rows[0], "ndfam_ab", "2"),
        _ena_membership(rows[1], "ndfam_ab", "2"),
        _ena_membership(rows[1], "ndfam_bc", "2"),
        _ena_membership(rows[2], "ndfam_bc", "2"),
    ]
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=_mmseqs_rows(rows, [[SEQ_A], [SEQ_B], [SEQ_C], [SEQ_D]]),
        membership_rows=membership,
    )
    finals = {row["cluster_id"] for row in result.clusters_final}
    abc = {
        next(r["cluster_id"] for r in result.clusters_final if r["sequence_id"] == make_sequence_id(core))
        for core in (SEQ_A, SEQ_B, SEQ_C)
    }
    assert len(abc) == 1
    assert result.diagnostics["n_final_clusters"] == 2
    assert make_sequence_id(SEQ_D) not in {
        row["sequence_id"]
        for row in result.clusters_final
        if row["cluster_id"] == next(iter(abc))
    }
    assert len(finals) == 2


def test_unrelated_mmseqs_clusters_remain_separate() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="ena:2", source_db="ena"),
        _corpus_row(sequence_core=SEQ_C, target="VEGF", record_id="apt:1"),
        _corpus_row(sequence_core=SEQ_D, target="TNF", record_id="apt:2"),
    ]
    membership = [
        _ena_membership(rows[0], "ndfam_ab", "2"),
        _ena_membership(rows[1], "ndfam_ab", "2"),
    ]
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=_mmseqs_rows(rows, [[SEQ_A], [SEQ_B], [SEQ_C], [SEQ_D]]),
        membership_rows=membership,
    )
    by_id = {row["sequence_id"]: row["cluster_id"] for row in result.clusters_final}
    assert by_id[make_sequence_id(SEQ_C)] != by_id[make_sequence_id(SEQ_D)]
    assert by_id[make_sequence_id(SEQ_C)] != by_id[make_sequence_id(SEQ_A)]
    only = [row for row in result.cluster_summary if row["merge_basis"] == MERGE_MMSEQS_ONLY]
    assert len(only) == 2


def test_materialised_singleton_creates_no_must_link() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="ena:2", source_db="ena"),
    ]
    membership = [
        _ena_membership(rows[0], "ena_singleton_ru1", "1"),
        _ena_membership(rows[1], "ena_singleton_ru2", "1"),
    ]
    cohort, must_links, diag = derive_ena_must_link_cohort(membership)
    assert must_links == []
    assert diag["n_real_multi_member_family_ids_represented"] == 0
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=_mmseqs_rows(rows, [[SEQ_A], [SEQ_B]]),
        membership_rows=membership,
    )
    assert result.diagnostics["n_final_clusters"] == 2
    assert all(row["merge_basis"] == MERGE_MMSEQS_ONLY for row in result.cluster_summary)


def test_singleton_may_share_global_similarity_cluster() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="apt:1"),
    ]
    membership = [_ena_membership(rows[0], "ena_singleton_ru1", "1")]
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=_mmseqs_rows(rows, [[SEQ_A, SEQ_B]]),
        membership_rows=membership,
    )
    assert result.diagnostics["n_final_clusters"] == 1
    assert result.diagnostics["ena_descriptive"]["treated_as_cannot_link"] is False
    assert result.diagnostics["ena_descriptive"]["treated_as_validation_failure"] is False


def test_declared_family_with_one_surviving_core_creates_no_union() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="apt:1"),
    ]
    membership = [_ena_membership(rows[0], "ndfam_lone", "2")]
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=_mmseqs_rows(rows, [[SEQ_A], [SEQ_B]]),
        membership_rows=membership,
    )
    assert result.diagnostics["n_real_multi_member_family_ids_represented"] == 1
    assert result.diagnostics["n_families_with_ge2_retained_s5_ena_cores"] == 0
    assert result.diagnostics["n_final_clusters"] == 2


def test_mmseqs_cluster_is_never_split() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="ena:2", source_db="ena"),
        _corpus_row(sequence_core=SEQ_C, target="VEGF", record_id="apt:1"),
    ]
    membership = [
        _ena_membership(rows[0], "ndfam_ac", "2"),
        _ena_membership(rows[2], "ndfam_ac", "2"),
    ]
    mmseqs = _mmseqs_rows(rows, [[SEQ_A, SEQ_B], [SEQ_C]])
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=mmseqs,
        membership_rows=membership,
    )
    mmseqs_of_ab = {
        row["sequence_cluster_id_mmseqs"]
        for row in result.clusters_final
        if row["sequence_id"] in {make_sequence_id(SEQ_A), make_sequence_id(SEQ_B)}
    }
    assert len(mmseqs_of_ab) == 1
    finals_of_ab = {
        row["cluster_id"]
        for row in result.clusters_final
        if row["sequence_id"] in {make_sequence_id(SEQ_A), make_sequence_id(SEQ_B)}
    }
    assert len(finals_of_ab) == 1
    assert result.diagnostics["mmseqs_clusters_preserved_as_subsets"] is True


def test_scientific_identities_and_multi_target_rows_remain() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_A, target="VEGF", record_id="apt:1"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="ena:2", source_db="ena"),
    ]
    membership = [
        _ena_membership(rows[0], "ndfam_ab", "2"),
        _ena_membership(rows[2], "ndfam_ab", "2"),
    ]
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=_mmseqs_rows(rows, [[SEQ_A], [SEQ_B]]),
        membership_rows=membership,
        expected_counts={
            "n_scientific_identities": 3,
            "n_distinct_sequence_core": 2,
            "n_shared_sequence_cores": 1,
            "n_shared_core_identities": 2,
        },
    )
    assert result.diagnostics["scientific_identities_before"] == 3
    assert result.diagnostics["scientific_identities_after"] == 3
    identities = {row["scientific_identity_id"] for row in result.clustered_corpus}
    assert len(identities) == 3
    cores = [
        row for row in result.clustered_corpus if row["sequence_core"] == SEQ_A
    ]
    assert len(cores) == 2
    assert {row["canonical_target_name"] for row in cores} == {"EGFR", "VEGF"}
    assert len({row["cluster_id"] for row in cores}) == 1


def test_union_edge_order_does_not_change_cluster_id() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="ena:2", source_db="ena"),
        _corpus_row(sequence_core=SEQ_C, target="EGFR", record_id="ena:3", source_db="ena"),
    ]
    membership = [
        _ena_membership(rows[0], "ndfam_ab", "2"),
        _ena_membership(rows[1], "ndfam_ab", "2"),
        _ena_membership(rows[1], "ndfam_bc", "2"),
        _ena_membership(rows[2], "ndfam_bc", "2"),
    ]
    mmseqs = _mmseqs_rows(rows, [[SEQ_A], [SEQ_B], [SEQ_C]])
    first = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=mmseqs,
        membership_rows=membership,
        shuffle_seed=None,
    )
    second = assemble_final_clustering(
        corpus_rows=list(reversed(rows)),
        mmseqs_cluster_rows=list(reversed(mmseqs)),
        membership_rows=list(reversed(membership)),
        shuffle_seed=99,
    )
    compare_final_runs(first, second)
    assert membership_signature(first.clusters_final) == membership_signature(
        second.clusters_final
    )


def test_ununioned_final_id_equals_mmseqs_cluster_id() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="apt:1"),
    ]
    mmseqs = _mmseqs_rows(rows, [[SEQ_A], [SEQ_B]])
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=mmseqs,
        membership_rows=[],
    )
    for row in result.clusters_final:
        assert row["cluster_id"] == row["sequence_cluster_id_mmseqs"]
        assert row["merge_basis"] == MERGE_MMSEQS_ONLY


def test_largest_mmseqs_component_wins_representative() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="ena:2", source_db="ena"),
        _corpus_row(sequence_core=SEQ_C, target="EGFR", record_id="ena:3", source_db="ena"),
    ]
    membership = [
        _ena_membership(rows[0], "ndfam_all", "3"),
        _ena_membership(rows[1], "ndfam_all", "3"),
        _ena_membership(rows[2], "ndfam_all", "3"),
    ]
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=_mmseqs_rows(rows, [[SEQ_A, SEQ_B], [SEQ_C]]),
        membership_rows=membership,
    )
    assert result.diagnostics["n_final_clusters"] == 1
    summary = result.cluster_summary[0]
    assert summary["representative_sequence_id"] == make_sequence_id(SEQ_A)
    reps = [
        row
        for row in result.clustered_corpus
        if row["is_cluster_representative"] == "true"
    ]
    assert len(reps) == 1
    seq_reps = [
        row
        for row in result.clusters_final
        if row["member_is_final_sequence_representative"] == "true"
    ]
    assert len(seq_reps) == 1


def test_representative_size_tie_breaks_on_sequence_hash() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="ena:2", source_db="ena"),
    ]
    membership = [
        _ena_membership(rows[0], "ndfam_ab", "2"),
        _ena_membership(rows[1], "ndfam_ab", "2"),
    ]
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=_mmseqs_rows(rows, [[SEQ_A], [SEQ_B]]),
        membership_rows=membership,
    )
    expected = min(make_sequence_id(SEQ_A), make_sequence_id(SEQ_B))
    if sequence_core_digest(SEQ_A) < sequence_core_digest(SEQ_B):
        expected = make_sequence_id(SEQ_A)
    else:
        expected = make_sequence_id(SEQ_B)
    assert result.cluster_summary[0]["representative_sequence_id"] == expected


def test_multi_target_representative_core_uses_smallest_scientific_id() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="VEGF", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:2", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="ena:3", source_db="ena"),
    ]
    membership = [
        _ena_membership(rows[1], "ndfam_ab", "2"),
        _ena_membership(rows[2], "ndfam_ab", "2"),
    ]
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=_mmseqs_rows(rows, [[SEQ_A, SEQ_B]]),
        membership_rows=membership,
    )
    reps = [
        row
        for row in result.clustered_corpus
        if row["is_cluster_representative"] == "true"
    ]
    assert len(reps) == 1
    expected = min(_identity(SEQ_A, "EGFR"), _identity(SEQ_A, "VEGF"))
    assert reps[0]["scientific_identity_id"] == expected
    assert reps[0]["sequence_core"] == SEQ_A


def test_exactly_one_representative_per_final_cluster() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
        _corpus_row(sequence_core=SEQ_C, target="TNF", record_id="apt:1"),
    ]
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=_mmseqs_rows(rows, [[SEQ_A, SEQ_B], [SEQ_C]]),
        membership_rows=[],
    )
    by_cluster: dict[str, int] = {}
    for row in result.clustered_corpus:
        if row["is_cluster_representative"] == "true":
            by_cluster[row["cluster_id"]] = by_cluster.get(row["cluster_id"], 0) + 1
    assert set(by_cluster) == {row["cluster_id"] for row in result.clustered_corpus}
    assert all(count == 1 for count in by_cluster.values())


def test_split_must_link_family_fails_closure() -> None:
    cohort = [
        {
            "ena_family_id": "ndfam_split",
            "declared_multi_member": "true",
            "n_s5_ena_sequence_cores": "2",
            "must_link_applied": "true",
            "sequence_ids": f"{make_sequence_id(SEQ_A)}|{make_sequence_id(SEQ_B)}",
        }
    ]
    seq_to_final = {
        make_sequence_id(SEQ_A): "S5C_one",
        make_sequence_id(SEQ_B): "S5C_two",
    }
    mmseqs = {
        make_sequence_id(SEQ_A): "S5C_one",
        make_sequence_id(SEQ_B): "S5C_two",
    }
    with pytest.raises(S5FinalClusteringError, match="not contained after union"):
        build_family_containment(cohort, seq_to_final, mmseqs)


def test_parameter_enforcement_rejects_cdhit_selection_and_s6_keys() -> None:
    with pytest.raises(S5FinalClusteringError):
        enforce_authorised_parameters({**AUTHORISED_PARAMETERS, "cd_hit_selected": True})
    with pytest.raises(S5FinalClusteringError):
        enforce_authorised_parameters({**AUTHORISED_PARAMETERS, "balancing": True})
    enforce_authorised_parameters(AUTHORISED_PARAMETERS)


def test_authorised_config_file_matches_required_parameters() -> None:
    config = json.loads(
        (REPO_ROOT / "config" / "global_s5e_final_clustering.json").read_text(
            encoding="utf-8"
        )
    )
    enforce_authorised_parameters(config)
    assert config["cd_hit_selected"] is False
    assert config["materialised_singletons_as_cannot_link"] is False
    assert config["family_constraint_semantics"] == "positive_must_link_only"


def test_freeze_refuses_to_overwrite_s5c_and_s5a(tmp_path: Path) -> None:
    with pytest.raises(S5FinalClusteringError):
        assert_not_frozen_s5_path(tmp_path / FROZEN_CORPUS_DEDUP_NAME)
    with pytest.raises(S5FinalClusteringError):
        assert_not_frozen_s5_path(tmp_path / "clusters.tsv")
    with pytest.raises(S5FinalClusteringError):
        assert_not_frozen_s5_path(tmp_path / "corpus_clustered.csv")
    assert_not_frozen_s5_path(tmp_path / "clusters_final.tsv")


def test_different_family_ids_may_share_a_similarity_cluster() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="ena:2", source_db="ena"),
    ]
    membership = [
        _ena_membership(rows[0], "ndfam_one", "2"),
        _ena_membership(rows[1], "ndfam_two", "2"),
    ]
    result = assemble_final_clustering(
        corpus_rows=rows,
        mmseqs_cluster_rows=_mmseqs_rows(rows, [[SEQ_A, SEQ_B]]),
        membership_rows=membership,
    )
    assert result.diagnostics["n_final_clusters"] == 1
    assert result.diagnostics["ena_descriptive"]["treated_as_validation_failure"] is False

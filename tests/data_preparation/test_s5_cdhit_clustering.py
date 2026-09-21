"""Synthetic tests for S5D ENA validation, CD-HIT parsing, and adjudication.

Every literal nucleotide string in this file is shorter than 20 nt.
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

from adapters.s5_cdhit_clustering import (  # noqa: E402
    AUTHORISED_CDHIT_PARAMETERS,
    S5CdHitError,
    assemble_cdhit_clustering,
    build_cdhit_cluster_rows,
    build_comparison_fasta_rows,
    comparison_nucleotides,
    enforce_cdhit_parameters,
    interpret_cdhit_rna_u_preflight,
    parse_cdhit_clstr,
    scientific_representatives_cdhit,
)
from adapters.s5_ena_clustering_validation import (  # noqa: E402
    DECISION_ACCEPT_CDHIT,
    DECISION_BOTH_FAIL,
    DECISION_GROUND_TRUTH_CONTRADICTION,
    adjudicate_clustering_methods,
    ena_validation_pass_from_clusters,
    pairwise_graph_status,
    validate_ena_families,
)
from adapters.s5_exact_dedup import scientific_identity_id  # noqa: E402
from adapters.s5_sequence_clustering import (  # noqa: E402
    PREFLIGHT_FAR_ID,
    PREFLIGHT_MIXED_ID,
    PREFLIGHT_T_ID,
    PREFLIGHT_U_DUP_ID,
    PREFLIGHT_U_ID,
    PREFLIGHT_U_NEAR_ID,
    build_cluster_rows,
    make_sequence_id,
    parse_mmseqs_cluster_tsv,
    project_unique_sequence_cores,
    sequence_core_digest,
    stable_cluster_id,
)

SEQ_A = "ACGUACGUAA"
SEQ_B = "UGCAUGCAUU"
SEQ_C = "GGAAUCCGAU"
SEQ_A_NEAR = "ACGUACGUAC"
assert all(len(seq) < 20 for seq in (SEQ_A, SEQ_B, SEQ_C, SEQ_A_NEAR))


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
        "experiment_group_id": fields.get("experiment_group_id", ""),
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


def _clstr(groups: list[list[str]], sequence_rows: list[dict[str, str]]) -> str:
    by_core = {row["sequence_core"]: row["sequence_id"] for row in sequence_rows}
    lines: list[str] = []
    for index, group in enumerate(groups):
        lines.append(f">Cluster {index}")
        for member_i, core in enumerate(group):
            seq_id = by_core[core]
            length = len(core)
            if member_i == 0:
                lines.append(f"0\t{length}nt, >{seq_id}... *")
            else:
                lines.append(f"{member_i}\t{length}nt, >{seq_id}... at +/95.00%")
    return "\n".join(lines) + "\n"


def test_ena_family_entirely_one_cluster_passes() -> None:
    result = ena_validation_pass_from_clusters(
        family_to_clusters={"ndfam_ok": ["c1", "c1"]},
        singleton_to_cluster_ena_cores={"ena_singleton_a": 1},
    )
    assert result["family_containment_pass"] is True
    assert result["split_family_ids"] == []
    assert result["singleton_ena_internal_failures"] == []


def test_ena_family_split_fails() -> None:
    result = ena_validation_pass_from_clusters(
        family_to_clusters={"ndfam_split": ["c1", "c2"]},
        singleton_to_cluster_ena_cores={},
    )
    assert result["family_containment_pass"] is False
    assert result["split_family_ids"] == ["ndfam_split"]


def test_materialised_singleton_vs_another_ena_core_is_failure() -> None:
    result = ena_validation_pass_from_clusters(
        family_to_clusters={"ndfam_ok": ["c1"]},
        singleton_to_cluster_ena_cores={"ena_singleton_a": 2},
    )
    assert result["singleton_ena_internal_failures"] == ["ena_singleton_a"]


def test_singleton_clustered_only_with_non_ena_is_not_ena_internal_failure() -> None:
    result = ena_validation_pass_from_clusters(
        family_to_clusters={"ndfam_ok": ["c1"]},
        singleton_to_cluster_ena_cores={"ena_singleton_a": 1},
        singleton_non_ena_only={"ena_singleton_a": True},
    )
    assert result["singleton_ena_internal_failures"] == []
    assert result["singleton_non_ena_neighbours_not_failures"] == ["ena_singleton_a"]


def test_out_of_s5_family_members_are_not_counted() -> None:
    result = ena_validation_pass_from_clusters(
        family_to_clusters={"ndfam_live": ["c1"], "ndfam_parked": ["c9", "c8"]},
        singleton_to_cluster_ena_cores={},
        out_of_s5_family_ids=["ndfam_parked"],
    )
    assert result["family_containment_pass"] is True
    assert result["out_of_s5_ignored"] == ["ndfam_parked"]
    assert "ndfam_parked" not in result["split_family_ids"]


def test_validate_ena_families_split_and_singleton_categories() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="ena:2", source_db="ena"),
        _corpus_row(sequence_core=SEQ_C, target="VEGF", record_id="ena:3", source_db="ena"),
        _corpus_row(sequence_core=SEQ_A_NEAR, target="TNF", record_id="apt:1", source_db="aptamerbase"),
    ]
    membership = [
        _ena_membership(rows[0], "ndfam_synthetic01", "2"),
        _ena_membership(rows[1], "ndfam_synthetic01", "2"),
        _ena_membership(rows[2], "ena_singleton_ru3", "1"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    clstr = _clstr([[SEQ_A], [SEQ_B, SEQ_A_NEAR], [SEQ_C]], sequence_rows)
    assembled = assemble_cdhit_clustering(
        corpus_rows=rows, clstr_text=clstr, membership_rows=membership
    )
    validation = validate_ena_families(
        membership_rows=membership,
        clustered_corpus=assembled.clustered_corpus,
        cluster_rows=assembled.cluster_rows,
    )
    assert validation.metrics["n_multi_member_families_with_at_least_two_s5_members"] == 1
    assert validation.metrics["n_multi_member_families_split_across_gt1_cluster"] == 1
    singleton = validation.singleton_rows[0]
    assert singleton["ena_internal_status"] == "isolated_from_every_other_ena_core"


def test_singleton_with_only_non_ena_neighbour() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="apt:1", source_db="aptamerbase"),
    ]
    membership = [_ena_membership(rows[0], "ena_singleton_ru1", "1")]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    clstr = _clstr([[SEQ_A, SEQ_B]], sequence_rows)
    assembled = assemble_cdhit_clustering(
        corpus_rows=rows, clstr_text=clstr, membership_rows=membership
    )
    validation = validate_ena_families(
        membership_rows=membership,
        clustered_corpus=assembled.clustered_corpus,
        cluster_rows=assembled.cluster_rows,
    )
    assert validation.singleton_rows[0]["ena_internal_status"] == (
        "cluster_only_with_non_ena_sequences"
    )
    assert validation.metrics["n_ena_internal_singleton_conflicts"] == 0


def test_cdhit_parse_every_input_sequence_exactly_once() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    pairs = parse_cdhit_clstr(
        _clstr([[SEQ_A], [SEQ_B]], sequence_rows),
        input_sequence_ids=[row["sequence_id"] for row in sequence_rows],
    )
    assert {member for _rep, member in pairs} == {
        row["sequence_id"] for row in sequence_rows
    }


def test_cdhit_duplicate_assignment_fails() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    sid_a = make_sequence_id(SEQ_A)
    text = (
        f">Cluster 0\n0\t10nt, >{sid_a}... *\n"
        f">Cluster 1\n0\t10nt, >{sid_a}... *\n"
    )
    with pytest.raises(S5CdHitError, match="duplicate"):
        parse_cdhit_clstr(
            text, input_sequence_ids=[row["sequence_id"] for row in sequence_rows]
        )


def test_cdhit_missing_member_fails() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    sid_a = make_sequence_id(SEQ_A)
    text = f">Cluster 0\n0\t10nt, >{sid_a}... *\n"
    with pytest.raises(S5CdHitError, match="missing"):
        parse_cdhit_clstr(
            text, input_sequence_ids=[row["sequence_id"] for row in sequence_rows]
        )


def test_cdhit_unknown_member_fails() -> None:
    rows = [_corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1")]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    sid_a = make_sequence_id(SEQ_A)
    text = (
        f">Cluster 0\n0\t10nt, >{sid_a}... *\n"
        "1\t10nt, >S5SEQ_deadbeef... at +/90.00%\n"
    )
    with pytest.raises(S5CdHitError, match="unknown"):
        parse_cdhit_clstr(
            text, input_sequence_ids=[row["sequence_id"] for row in sequence_rows]
        )


def test_u_to_t_comparison_preserves_length_and_ids() -> None:
    rows = [_corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1")]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    original_core = sequence_rows[0]["sequence_core"]
    projected, diagnostics = build_comparison_fasta_rows(sequence_rows)
    assert diagnostics["length_preserved"] is True
    assert diagnostics["one_to_one_sequence_ids"] is True
    assert projected[0]["sequence_id"] == sequence_rows[0]["sequence_id"]
    assert len(projected[0]["sequence_core"]) == len(original_core)
    assert sequence_rows[0]["sequence_core"] == original_core
    assert "U" in original_core
    assert "U" not in projected[0]["sequence_core"]
    assert comparison_nucleotides(original_core) == projected[0]["sequence_core"]


def test_comparison_sequence_does_not_leak_into_clustered_corpus() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    assembled = assemble_cdhit_clustering(
        corpus_rows=rows,
        clstr_text=_clstr([[SEQ_A], [SEQ_B]], sequence_rows),
    )
    assert {row["sequence_core"] for row in assembled.clustered_corpus} == {SEQ_A, SEQ_B}
    assert all("T" not in row["sequence_core"] for row in assembled.clustered_corpus)


def test_stable_cluster_id_ignores_member_order_and_is_method_independent() -> None:
    hashes = [
        sequence_core_digest(SEQ_A),
        sequence_core_digest(SEQ_B),
    ]
    assert stable_cluster_id(hashes) == stable_cluster_id(list(reversed(hashes)))
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    sid_a = make_sequence_id(SEQ_A)
    sid_b = make_sequence_id(SEQ_B)
    mmseqs_pairs = parse_mmseqs_cluster_tsv(
        f"{sid_a}\t{sid_a}\n{sid_a}\t{sid_b}\n",
        input_sequence_ids=[row["sequence_id"] for row in sequence_rows],
    )
    cdhit_pairs = parse_cdhit_clstr(
        _clstr([[SEQ_A, SEQ_B]], sequence_rows),
        input_sequence_ids=[row["sequence_id"] for row in sequence_rows],
    )
    mmseqs_rows = build_cluster_rows(mmseqs_pairs, sequence_rows)
    cdhit_rows = build_cdhit_cluster_rows(cdhit_pairs, sequence_rows)
    assert {row["cluster_id"] for row in mmseqs_rows} == {
        row["cluster_id"] for row in cdhit_rows
    }


def test_broadcast_and_one_scientific_representative() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_A, target="VEGF", record_id="syn:2"),
        _corpus_row(sequence_core=SEQ_B, target="TNF", record_id="syn:3"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    assembled = assemble_cdhit_clustering(
        corpus_rows=rows,
        clstr_text=_clstr([[SEQ_A, SEQ_B]], sequence_rows),
    )
    assert len(assembled.clustered_corpus) == 3
    reps = [
        row
        for row in assembled.clustered_corpus
        if row["is_cluster_representative"] == "true"
    ]
    assert len(reps) == 1
    shared = [row for row in assembled.clustered_corpus if row["sequence_core"] == SEQ_A]
    assert {row["cluster_id"] for row in assembled.clustered_corpus} == {
        assembled.clustered_corpus[0]["cluster_id"]
    }
    chosen = scientific_representatives_cdhit(assembled.clustered_corpus)
    assert reps[0]["scientific_identity_id"] == min(
        row["scientific_identity_id"] for row in shared
    )
    assert list(chosen.values()) == [reps[0]["scientific_identity_id"]]


def test_adjudication_poor_mmseqs_passing_cdhit_selects_cdhit() -> None:
    mmseqs = {
        "n_multi_member_families_with_at_least_two_s5_members": 16,
        "n_multi_member_families_contained_in_one_cluster": 8,
        "n_multi_member_families_split_across_gt1_cluster": 8,
        "n_families_incompatible_with_90_percent_global_identity": 0,
        "n_ena_internal_singleton_conflicts": 0,
        "n_singleton_conflicts_documented_experiment_or_target_scope": 0,
    }
    cdhit = {
        "n_multi_member_families_with_at_least_two_s5_members": 16,
        "n_multi_member_families_contained_in_one_cluster": 16,
        "n_multi_member_families_split_across_gt1_cluster": 0,
        "n_families_incompatible_with_90_percent_global_identity": 0,
        "n_ena_internal_singleton_conflicts": 2,
        "n_singleton_conflicts_documented_experiment_or_target_scope": 2,
    }
    result = adjudicate_clustering_methods(
        mmseqs_metrics=mmseqs,
        cdhit_metrics=cdhit,
        cdhit_mechanical_ok=True,
    )
    assert result["decision"] == DECISION_ACCEPT_CDHIT
    assert result["accept_cdhit"] is True
    assert result["parameter_tuning_path_exists"] is False
    assert result["third_algorithm_invented"] is False
    assert result["mmseqs_selected_because_it_ran_first"] is False


def test_adjudication_both_fail_is_nogo() -> None:
    metrics = {
        "n_multi_member_families_with_at_least_two_s5_members": 16,
        "n_multi_member_families_contained_in_one_cluster": 8,
        "n_multi_member_families_split_across_gt1_cluster": 8,
        "n_families_incompatible_with_90_percent_global_identity": 0,
        "n_ena_internal_singleton_conflicts": 0,
        "n_singleton_conflicts_documented_experiment_or_target_scope": 0,
    }
    result = adjudicate_clustering_methods(
        mmseqs_metrics=metrics,
        cdhit_metrics={
            **metrics,
            "n_multi_member_families_contained_in_one_cluster": 10,
            "n_multi_member_families_split_across_gt1_cluster": 6,
        },
        cdhit_mechanical_ok=True,
    )
    assert result["decision"] == DECISION_BOTH_FAIL
    assert result["case"] == "B"
    assert result["create_final_artefacts"] is False


def test_adjudication_ground_truth_contradiction() -> None:
    metrics = {
        "n_multi_member_families_with_at_least_two_s5_members": 16,
        "n_multi_member_families_contained_in_one_cluster": 8,
        "n_multi_member_families_split_across_gt1_cluster": 8,
        "n_families_incompatible_with_90_percent_global_identity": 3,
        "n_ena_internal_singleton_conflicts": 0,
        "n_singleton_conflicts_documented_experiment_or_target_scope": 0,
    }
    result = adjudicate_clustering_methods(
        mmseqs_metrics=metrics,
        cdhit_metrics={
            **metrics,
            "n_multi_member_families_contained_in_one_cluster": 16,
            "n_multi_member_families_split_across_gt1_cluster": 0,
        },
        cdhit_mechanical_ok=True,
    )
    assert result["decision"] == DECISION_GROUND_TRUTH_CONTRADICTION
    assert result["accept_cdhit"] is False
    assert result["create_final_artefacts"] is False


def test_no_parameter_tuning_path() -> None:
    enforce_cdhit_parameters(AUTHORISED_CDHIT_PARAMETERS)
    with pytest.raises(S5CdHitError, match="0.90"):
        enforce_cdhit_parameters({**AUTHORISED_CDHIT_PARAMETERS, "identity_threshold": 0.85})
    with pytest.raises(S5CdHitError, match="word size"):
        enforce_cdhit_parameters({**AUTHORISED_CDHIT_PARAMETERS, "word_size": 5})
    with pytest.raises(S5CdHitError, match="flag"):
        enforce_cdhit_parameters(
            {**AUTHORISED_CDHIT_PARAMETERS, "extra_cdhit_flags": ["-aS", "0.8"]}
        )
    config = json.loads(
        (REPO_ROOT / "config" / "global_s5d_ena_validation_cdhit.json").read_text(
            encoding="utf-8"
        )
    )
    enforce_cdhit_parameters(config)
    assert "parameter_tuning" in config["does_not"]


def test_pairwise_graph_classifies_all_pairs_connected_and_disconnected() -> None:
    cores = {"a": SEQ_A, "b": SEQ_A, "c": SEQ_C}

    def lookup(left: str, right: str) -> float:
        if cores[left] == cores[right]:
            return 1.0
        return 0.2

    all_pairs = pairwise_graph_status(["a", "b"], lookup)
    disconnected = pairwise_graph_status(["a", "c"], lookup)
    assert all_pairs["status"] == "all_pairs_ge_0.90"
    assert disconnected["status"] == "disconnected_at_0.90"


def test_cdhit_preflight_interpreter_accepts_native_u() -> None:
    pairs = [
        (PREFLIGHT_U_ID, PREFLIGHT_U_ID),
        (PREFLIGHT_U_ID, PREFLIGHT_U_DUP_ID),
        (PREFLIGHT_U_ID, PREFLIGHT_U_NEAR_ID),
        (PREFLIGHT_U_ID, PREFLIGHT_T_ID),
        (PREFLIGHT_U_ID, PREFLIGHT_MIXED_ID),
        (PREFLIGHT_FAR_ID, PREFLIGHT_FAR_ID),
    ]
    result = interpret_cdhit_rna_u_preflight(pairs)
    assert result["go"] is True
    assert result["native_u_works"] is True
    assert result["input_transcoded_u_to_t"] is False

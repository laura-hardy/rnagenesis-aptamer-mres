"""Synthetic tests for S5C 90% sequence-identity clustering.

Every literal nucleotide string in this file is shorter than 20 nt.
Longer MMseqs preflight sequences are concatenated at runtime. Tests do
not read live biological S5A CSVs.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s5_exact_dedup import scientific_identity_id  # noqa: E402
from adapters.s5_sequence_clustering import (  # noqa: E402
    AUTHORISED_PARAMETERS,
    FROZEN_CORPUS_DEDUP_NAME,
    S5SequenceClusteringError,
    assemble_clustering,
    assert_not_corpus_dedup_path,
    build_cluster_rows,
    clustering_sort_key,
    compare_cluster_runs,
    enforce_authorised_parameters,
    interpret_rna_u_preflight,
    make_sequence_id,
    parse_mmseqs_cluster_tsv,
    preflight_synthetic_sequences,
    project_unique_sequence_cores,
    render_fasta,
    scientific_representatives,
    sequence_core_digest,
    stable_cluster_id,
    PREFLIGHT_FAR_ID,
    PREFLIGHT_MIXED_ID,
    PREFLIGHT_T_ID,
    PREFLIGHT_U_DUP_ID,
    PREFLIGHT_U_ID,
    PREFLIGHT_U_NEAR_ID,
)


SEQ_A = "ACGUACGUAA"
SEQ_B = "UGCAUGCAUU"
SEQ_C = "GGAAUCCGAU"
assert len(SEQ_A) < 20 and len(SEQ_B) < 20 and len(SEQ_C) < 20


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


def _fake_cluster_tsv(sequence_rows: list[dict[str, str]], groups: list[list[str]]) -> str:
    by_core = {row["sequence_core"]: row["sequence_id"] for row in sequence_rows}
    lines = []
    for group in groups:
        rep = by_core[group[0]]
        for member_core in group:
            lines.append(f"{rep}\t{by_core[member_core]}")
    return "\n".join(lines) + "\n"


def test_repeated_core_across_targets_projects_one_sequence_row() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_A, target="VEGF", record_id="syn:2"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="syn:3"),
    ]
    sequence_rows, identity_map = project_unique_sequence_cores(rows)
    assert len(sequence_rows) == 2
    by_core = {row["sequence_core"]: row for row in sequence_rows}
    assert by_core[SEQ_A]["n_scientific_identities"] == "2"
    assert len(identity_map) == 3
    assert {row["sequence_id"] for row in sequence_rows} == {
        make_sequence_id(SEQ_A),
        make_sequence_id(SEQ_B),
    }


def test_unique_cores_produce_one_row_each() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="syn:2"),
        _corpus_row(sequence_core=SEQ_C, target="VEGF", record_id="syn:3"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    assert len(sequence_rows) == 3
    assert len({row["sequence_id"] for row in sequence_rows}) == 3


def test_sequence_ids_are_deterministic_and_order_independent() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
    ]
    shuffled = list(rows)
    random.Random(0).shuffle(shuffled)
    first, _ = project_unique_sequence_cores(rows)
    second, _ = project_unique_sequence_cores(shuffled)
    assert first == second
    assert first[0]["sequence_id"] == make_sequence_id(first[0]["sequence_core"])
    assert first[0]["sequence_id"].startswith("S5SEQ_")
    assert len({row["sequence_id"] for row in first}) == 2


def test_fasta_ordering_is_sha256_then_sequence_id() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
        _corpus_row(sequence_core=SEQ_C, target="TNF", record_id="syn:3"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    fasta = render_fasta(list(reversed(sequence_rows)))
    headers = [line[1:] for line in fasta.splitlines() if line.startswith(">")]
    expected = [
        row["sequence_id"]
        for row in sorted(sequence_rows, key=clustering_sort_key)
    ]
    assert headers == expected
    assert "EGFR" not in fasta and "VEGF" not in fasta and "TNF" not in fasta


def test_mmseqs_parse_every_input_sequence_exactly_once() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    tsv = _fake_cluster_tsv(sequence_rows, [[SEQ_A], [SEQ_B]])
    pairs = parse_mmseqs_cluster_tsv(
        tsv,
        input_sequence_ids=[row["sequence_id"] for row in sequence_rows],
    )
    assert {member for _rep, member in pairs} == {
        row["sequence_id"] for row in sequence_rows
    }


def test_duplicate_membership_fails() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    sid_a = make_sequence_id(SEQ_A)
    sid_b = make_sequence_id(SEQ_B)
    tsv = f"{sid_a}\t{sid_a}\n{sid_a}\t{sid_b}\n{sid_a}\t{sid_a}\n"
    with pytest.raises(S5SequenceClusteringError, match="duplicate"):
        parse_mmseqs_cluster_tsv(
            tsv,
            input_sequence_ids=[row["sequence_id"] for row in sequence_rows],
        )


def test_missing_sequence_fails() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    sid_a = make_sequence_id(SEQ_A)
    tsv = f"{sid_a}\t{sid_a}\n"
    with pytest.raises(S5SequenceClusteringError, match="missing"):
        parse_mmseqs_cluster_tsv(
            tsv,
            input_sequence_ids=[row["sequence_id"] for row in sequence_rows],
        )


def test_unknown_output_sequence_id_fails() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    sid_a = make_sequence_id(SEQ_A)
    tsv = f"{sid_a}\t{sid_a}\n{sid_a}\tS5SEQ_deadbeef\n"
    with pytest.raises(S5SequenceClusteringError, match="unknown"):
        parse_mmseqs_cluster_tsv(
            tsv,
            input_sequence_ids=[row["sequence_id"] for row in sequence_rows],
        )


def test_stable_cluster_id_ignores_member_order() -> None:
    hashes = [
        sequence_core_digest(SEQ_A),
        sequence_core_digest(SEQ_B),
        sequence_core_digest(SEQ_C),
    ]
    first = stable_cluster_id(hashes)
    second = stable_cluster_id(list(reversed(hashes)))
    assert first == second
    assert first.startswith("S5C_")
    assert first != stable_cluster_id(hashes[:2])


def test_different_membership_yields_different_cluster_id() -> None:
    assert stable_cluster_id([sequence_core_digest(SEQ_A)]) != stable_cluster_id(
        [sequence_core_digest(SEQ_B)]
    )


def test_broadcast_shared_core_same_cluster_and_retains_identities() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_A, target="VEGF", record_id="syn:2"),
        _corpus_row(sequence_core=SEQ_B, target="TNF", record_id="syn:3"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    tsv = _fake_cluster_tsv(sequence_rows, [[SEQ_A, SEQ_B]])
    result = assemble_clustering(corpus_rows=rows, mmseqs_cluster_tsv=tsv)
    assert len(result.clustered_corpus) == 3
    assert len({row["scientific_identity_id"] for row in result.clustered_corpus}) == 3
    assert all(row["cluster_id"] for row in result.clustered_corpus)
    shared = [
        row for row in result.clustered_corpus if row["sequence_core"] == SEQ_A
    ]
    assert {row["cluster_id"] for row in shared} == {
        result.clustered_corpus[0]["cluster_id"]
    }
    assert {row["cluster_id"] for row in result.clustered_corpus} == {
        result.clustered_corpus[0]["cluster_id"]
    }


def test_one_scientific_representative_per_cluster_is_deterministic() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_A, target="VEGF", record_id="syn:2"),
        _corpus_row(sequence_core=SEQ_B, target="TNF", record_id="syn:3"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    tsv = _fake_cluster_tsv(sequence_rows, [[SEQ_A], [SEQ_B]])
    result = assemble_clustering(corpus_rows=rows, mmseqs_cluster_tsv=tsv)
    reps = [
        row
        for row in result.clustered_corpus
        if row["is_cluster_representative"] == "true"
    ]
    assert len(reps) == 2
    shared = [row for row in result.clustered_corpus if row["sequence_core"] == SEQ_A]
    chosen = min(row["scientific_identity_id"] for row in shared)
    shared_rep = [
        row for row in shared if row["is_cluster_representative"] == "true"
    ]
    assert len(shared_rep) == 1
    assert shared_rep[0]["scientific_identity_id"] == chosen
    assert all(row["record_id"] != chosen for row in shared_rep)


def test_shared_representative_core_uses_smallest_scientific_identity_id() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="ZZZ", record_id="syn:z"),
        _corpus_row(sequence_core=SEQ_A, target="AAA", record_id="syn:a"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    tsv = _fake_cluster_tsv(sequence_rows, [[SEQ_A]])
    result = assemble_clustering(corpus_rows=list(reversed(rows)), mmseqs_cluster_tsv=tsv)
    ids = [row["scientific_identity_id"] for row in result.clustered_corpus]
    chosen = min(ids)
    true_rows = [
        row
        for row in result.clustered_corpus
        if row["is_cluster_representative"] == "true"
    ]
    assert len(true_rows) == 1
    assert true_rows[0]["scientific_identity_id"] == chosen
    chosen_map = scientific_representatives(result.clustered_corpus)
    assert list(chosen_map.values()) == [chosen]


def test_schema_keys_on_scientific_identity_id_not_donor_record_id() -> None:
    rows = [
        _corpus_row(
            sequence_core=SEQ_A,
            target="EGFR",
            record_id="syn:shared",
        ),
        _corpus_row(
            sequence_core=SEQ_B,
            target="VEGF",
            record_id="syn:shared",
        ),
    ]
    assert rows[0]["record_id"] == rows[1]["record_id"]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    tsv = _fake_cluster_tsv(sequence_rows, [[SEQ_A], [SEQ_B]])
    result = assemble_clustering(corpus_rows=rows, mmseqs_cluster_tsv=tsv)
    identities = [row["scientific_identity_id"] for row in result.clustered_corpus]
    assert len(identities) == 2
    assert len(set(identities)) == 2
    assert [row["record_id"] for row in result.clustered_corpus].count("syn:shared") == 2


def test_freeze_refuses_to_overwrite_corpus_dedup(tmp_path: Path) -> None:
    forbidden = tmp_path / FROZEN_CORPUS_DEDUP_NAME
    with pytest.raises(S5SequenceClusteringError, match="corpus_dedup"):
        assert_not_corpus_dedup_path(forbidden)
    assert_not_corpus_dedup_path(tmp_path / "corpus_clustered.csv")


def test_parameter_enforcement_rejects_unauthorised_values() -> None:
    enforce_authorised_parameters(
        {
            "min_seq_id": 0.90,
            "coverage": 0.80,
            "cov_mode": 1,
            "sensitivity": 7.5,
            "sequence_field": "sequence_core",
        }
    )
    with pytest.raises(S5SequenceClusteringError, match="min_seq_id"):
        enforce_authorised_parameters(
            {
                **AUTHORISED_PARAMETERS,
                "min_seq_id": 0.8,
            }
        )
    with pytest.raises(S5SequenceClusteringError, match="coverage"):
        enforce_authorised_parameters({**AUTHORISED_PARAMETERS, "coverage": 0.9})
    with pytest.raises(S5SequenceClusteringError, match="cov_mode"):
        enforce_authorised_parameters({**AUTHORISED_PARAMETERS, "cov_mode": 0})
    with pytest.raises(S5SequenceClusteringError, match="sensitivity"):
        enforce_authorised_parameters({**AUTHORISED_PARAMETERS, "sensitivity": 4.0})
    with pytest.raises(S5SequenceClusteringError, match="sequence_field"):
        enforce_authorised_parameters(
            {**AUTHORISED_PARAMETERS, "sequence_field": "sequence_full"}
        )
    with pytest.raises(S5SequenceClusteringError, match="forbidden"):
        enforce_authorised_parameters({**AUTHORISED_PARAMETERS, "balancing": True})


def test_authorised_config_file_matches_required_parameters() -> None:
    config = json.loads(
        (REPO_ROOT / "config" / "global_s5c_sequence_clustering.json").read_text(
            encoding="utf-8"
        )
    )
    enforce_authorised_parameters(config)
    assert config["does_not"]


def test_compare_cluster_runs_detects_membership_change() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    first = build_cluster_rows(
        parse_mmseqs_cluster_tsv(
            _fake_cluster_tsv(sequence_rows, [[SEQ_A], [SEQ_B]]),
            input_sequence_ids=[row["sequence_id"] for row in sequence_rows],
        ),
        sequence_rows,
    )
    second = build_cluster_rows(
        parse_mmseqs_cluster_tsv(
            _fake_cluster_tsv(sequence_rows, [[SEQ_A, SEQ_B]]),
            input_sequence_ids=[row["sequence_id"] for row in sequence_rows],
        ),
        sequence_rows,
    )
    with pytest.raises(S5SequenceClusteringError, match="membership"):
        compare_cluster_runs(first, second)


def test_assemble_does_not_drop_identities_when_sequences_cluster() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
        _corpus_row(sequence_core=SEQ_C, target="TNF", record_id="syn:3"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    tsv = _fake_cluster_tsv(sequence_rows, [[SEQ_A, SEQ_B], [SEQ_C]])
    result = assemble_clustering(corpus_rows=rows, mmseqs_cluster_tsv=tsv)
    assert len(result.clustered_corpus) == 3
    assert result.diagnostics["n_clusters"] == 2
    assert result.diagnostics["n_reduction_due_to_near_sequence_clustering"] == 1


def test_mmseqs_sequence_representative_is_preserved() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="syn:1"),
        _corpus_row(sequence_core=SEQ_B, target="VEGF", record_id="syn:2"),
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    tsv = _fake_cluster_tsv(sequence_rows, [[SEQ_A, SEQ_B]])
    result = assemble_clustering(corpus_rows=rows, mmseqs_cluster_tsv=tsv)
    seq_reps = [
        row
        for row in result.cluster_rows
        if row["member_is_mmseqs_representative"] == "true"
    ]
    assert len(seq_reps) == 1
    assert seq_reps[0]["member_sequence_id"] == make_sequence_id(SEQ_A)
    assert all(
        row["mmseqs_representative_sequence_id"] == make_sequence_id(SEQ_A)
        for row in result.clustered_corpus
    )


def test_rna_u_preflight_interpreter_accepts_faithful_nucleotide_output() -> None:
    pairs = [
        (PREFLIGHT_U_ID, PREFLIGHT_U_ID),
        (PREFLIGHT_U_ID, PREFLIGHT_U_DUP_ID),
        (PREFLIGHT_U_ID, PREFLIGHT_U_NEAR_ID),
        (PREFLIGHT_U_ID, PREFLIGHT_T_ID),
        (PREFLIGHT_U_ID, PREFLIGHT_MIXED_ID),
        (PREFLIGHT_FAR_ID, PREFLIGHT_FAR_ID),
    ]
    result = interpret_rna_u_preflight(pairs)
    assert result["go"] is True
    assert result["u_internally_equivalent_to_t"] is True
    assert result["input_transcoded_u_to_t"] is False
    assert result["derived_u_to_t_corpus_created"] is False


def test_rna_u_preflight_interpreter_fails_if_u_sequences_do_not_cluster() -> None:
    pairs = [
        (PREFLIGHT_U_ID, PREFLIGHT_U_ID),
        (PREFLIGHT_U_DUP_ID, PREFLIGHT_U_DUP_ID),
        (PREFLIGHT_U_NEAR_ID, PREFLIGHT_U_NEAR_ID),
        (PREFLIGHT_T_ID, PREFLIGHT_T_ID),
        (PREFLIGHT_MIXED_ID, PREFLIGHT_MIXED_ID),
        (PREFLIGHT_FAR_ID, PREFLIGHT_FAR_ID),
    ]
    result = interpret_rna_u_preflight(pairs)
    assert result["go"] is False


def test_preflight_synthetic_sequences_are_runtime_constructed() -> None:
    sequences = preflight_synthetic_sequences()
    assert all(len(seq) >= 20 for seq in sequences.values())
    assert "U" in sequences[PREFLIGHT_U_ID]
    assert "T" not in sequences[PREFLIGHT_U_ID]
    assert "U" not in sequences[PREFLIGHT_T_ID]


def test_ena_family_diagnostics_are_descriptive_only() -> None:
    rows = [
        _corpus_row(sequence_core=SEQ_A, target="EGFR", record_id="ena:1", source_db="ena"),
        _corpus_row(sequence_core=SEQ_B, target="EGFR", record_id="ena:2", source_db="ena"),
        _corpus_row(sequence_core=SEQ_C, target="VEGF", record_id="apt:1", source_db="aptamerbase"),
    ]
    membership = [
        {
            "scientific_identity_id": rows[0]["scientific_identity_id"],
            "source_db": "ena",
            "sequence_core": SEQ_A,
            "ena_effective_near_duplicate_family_id": "ndfam_synthetic01",
            "ena_effective_near_duplicate_family_size": "2",
        },
        {
            "scientific_identity_id": rows[1]["scientific_identity_id"],
            "source_db": "ena",
            "sequence_core": SEQ_B,
            "ena_effective_near_duplicate_family_id": "ndfam_synthetic01",
            "ena_effective_near_duplicate_family_size": "2",
        },
    ]
    sequence_rows, _map = project_unique_sequence_cores(rows)
    tsv = _fake_cluster_tsv(sequence_rows, [[SEQ_A], [SEQ_B], [SEQ_C]])
    result = assemble_clustering(
        corpus_rows=rows,
        mmseqs_cluster_tsv=tsv,
        membership_rows=membership,
    )
    ena = result.diagnostics["ena_family_diagnostics"]
    assert ena["adjudication"] == "deferred_to_s5d"
    assert ena["n_multi_member_families_with_at_least_two_s5_members"] == 1
    assert ena["n_multi_member_families_split_across_gt1_cluster"] == 1

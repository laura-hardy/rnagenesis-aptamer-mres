"""Synthetic tests for S7B whole-cluster FT/REF/EVAL partition preview.

Every literal nucleotide string in this file is shorter than 20 nt.
Tests do not read live biological S5/S7A CSVs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s5_exact_dedup import scientific_identity_id  # noqa: E402
from adapters.s5_final_clustering import enforce_authorised_parameters  # noqa: E402
from adapters.s6_profile import fit_univariate_gmm  # noqa: E402
from adapters.s7_partition import (  # noqa: E402
    COMPARISON_TUPLE_FIELDS,
    PRIMARY_CRITERIA,
    ObjectiveScore,
    QuotaTriple,
    S7PartitionError,
    apply_assignment_to_identities,
    assign_length_regimes,
    assignment_signature,
    build_cluster_features,
    cluster_processing_order,
    derive_integer_quotas,
    greedy_assign,
    input_unmutated,
    integrity_gates,
    js_divergence,
    load_frozen_s6_gmm,
    optimise_partition,
    pairwise_local_search,
    score_assignment,
    select_preview_assignment,
    states_from_assignment,
    verify_frozen_identities,
)
from adapters.s7_target_cap import select_target_cap  # noqa: E402
from s7_partition import run_s7b_partition_apply, run_s7b_partition_preview  # noqa: E402

BASES = "ACGU"
SYNTHETIC_GMM = {
    "n_components": 2,
    "means": [30.0, 80.0],
    "variances": [4.0, 4.0],
    "weights": [0.5, 0.5],
}


def _seq(index: int) -> str:
    chars: list[str] = []
    value = index
    for _ in range(8):
        chars.append(BASES[value % 4])
        value //= 4
    seq = "A" + "".join(chars)
    assert len(seq) < 20
    return seq


def _row(
    *,
    index: int,
    target: str,
    cluster_id: str,
    evidence_level: str = "E2",
    source_db: str = "srcA",
    target_family: str = "unknown",
    target_type: str = "protein",
    partition: str = "",
    length: int = 30,
    core: str | None = None,
) -> dict[str, str]:
    sequence_core = core or _seq(index)
    return {
        "scientific_identity_id": scientific_identity_id(sequence_core, target),
        "cluster_id": cluster_id,
        "canonical_target_name": target,
        "sequence_core": sequence_core,
        "sequence_length_core": str(length),
        "evidence_level": evidence_level,
        "source_db": source_db,
        "contributing_sources": f"{source_db}|extra_ignored",
        "target_family": target_family,
        "target_type": target_type,
        "partition": partition,
        "record_id": f"synthetic:{index}",
        "sequence_core_sha256": hashlib.sha256(sequence_core.encode("utf-8")).hexdigest(),
    }


def _features(rows: list[dict[str, str]], gmm: dict | None = None):
    regimes = assign_length_regimes(rows, gmm or SYNTHETIC_GMM)
    return build_cluster_features(rows, regimes)


def _quotas(n_ft: int, n_ref: int, n_eval: int) -> QuotaTriple:
    return QuotaTriple(n_ft, n_ref, n_eval, sse=0)


def _run_preview(tmp_path: Path, rows: list[dict[str, str]]) -> dict[str, Any]:
    corpus_path = tmp_path / "corpus_post_cap.csv"
    fieldnames = list(rows[0].keys())
    with corpus_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    bimodality = tmp_path / "bimodality.json"
    bimodality.write_text(json.dumps({"gmm_2": SYNTHETIC_GMM}), encoding="utf-8")
    output_dir = tmp_path / "preview"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "contract_id": "global_s7b_partition",
                "milestone": "S7B_partition_preview_dry_run",
                "mode": "preview",
                "authoritative_corpus": str(corpus_path.relative_to(tmp_path)),
                "expected_input_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
                "partition_fractions": {"FT": 0.80, "REF": 0.10, "EVAL": 0.10},
                "length_regime": {
                    "s6_bimodality_json": str(bimodality.relative_to(tmp_path)),
                    "assignment_method": "gmm_k2_maximum_posterior",
                    "refit_on_post_cap": False,
                },
                "random_baseline_seeds": [1, 2],
                "write_authoritative_partitioned_corpus": False,
                "freeze_ref": False,
                "freeze_eval": False,
                "output_dir": str(output_dir.relative_to(tmp_path)),
                "does_not": [
                    "write_authoritative_partitioned_corpus",
                    "write_corpus_final",
                    "freeze_ref",
                    "freeze_eval",
                    "populate_partition_on_s7a_input",
                    "create_train_validation_split",
                    "promote_e5",
                    "promote_non_protein",
                ],
                "sequence_safety_scan_paths": [],
            }
        ),
        encoding="utf-8",
    )
    result = run_s7b_partition_preview(
        config_path=config_path,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=True,
        write_outputs=True,
        run_random_baseline=True,
    )
    return {"result": result, "config_corpus": corpus_path}


def test_all_clusters_assigned_exactly_once() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    result = optimise_partition(features, space, _quotas(6, 1, 1))
    assert set(result["assignment"]) == set(features)
    assert len(result["assignment"]) == 8


def test_exact_cluster_quotas_respected() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    result = optimise_partition(features, space, _quotas(6, 1, 1))
    assert Counter(result["assignment"].values()) == {"FT": 6, "REF": 1, "EVAL": 1}


def test_no_cluster_split() -> None:
    rows = [
        _row(index=0, target="T0", cluster_id="c_multi", evidence_level="E2"),
        _row(index=1, target="T1", cluster_id="c_multi", evidence_level="E3"),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"c{i:02d}") for i in range(7))
    features, space = _features(rows)
    result = optimise_partition(features, space, _quotas(6, 1, 1))
    mapped = apply_assignment_to_identities(rows, result["assignment"])
    multi = [row for row in mapped if row["cluster_id"] == "c_multi"]
    assert len({item["proposed_partition"] for item in multi}) == 1


def test_every_identity_follows_its_cluster() -> None:
    rows = [
        _row(index=0, target="T0", cluster_id="c_keep"),
        _row(index=1, target="T1", cluster_id="c_keep"),
    ]
    rows.extend(_row(index=20 + i, target=f"U{i}", cluster_id=f"s{i:02d}") for i in range(7))
    features, space = _features(rows)
    result = optimise_partition(features, space, _quotas(6, 1, 1))
    mapped = apply_assignment_to_identities(rows, result["assignment"])
    by_identity = {row["scientific_identity_id"]: row["proposed_partition"] for row in mapped}
    for row in rows:
        assert by_identity[row["scientific_identity_id"]] == result["assignment"][row["cluster_id"]]


def test_every_core_follows_its_cluster() -> None:
    shared = _seq(99)
    rows = [
        _row(index=0, target="T0", cluster_id="c_core", core=shared, length=30),
        _row(index=1, target="T1", cluster_id="c_core", core=shared, length=30),
    ]
    rows.extend(_row(index=30 + i, target=f"U{i}", cluster_id=f"s{i:02d}") for i in range(7))
    features, space = _features(rows)
    result = optimise_partition(features, space, _quotas(6, 1, 1))
    partitions = {
        result["assignment"][row["cluster_id"]]
        for row in rows
        if row["sequence_core"] == shared
    }
    assert partitions == {result["assignment"]["c_core"]}
    integrity = integrity_gates(rows, result["assignment"], features, _quotas(6, 1, 1))
    assert integrity["cores_cross_partitions"] == 0


def test_integer_quota_derivation_80_10_10() -> None:
    winners = derive_integer_quotas(10)
    assert [item.as_tuple for item in winners] == [(8, 1, 1)]
    live = derive_integer_quotas(794)
    tuples = [item.as_tuple for item in live]
    assert all(sum(item) == 794 for item in tuples)
    assert tuples[0][0] == 635


def test_tied_optimal_ref_eval_quota_treatment() -> None:
    winners = derive_integer_quotas(15)
    tuples = [item.as_tuple for item in winners]
    assert (12, 1, 2) in tuples
    assert (12, 2, 1) in tuples
    live = derive_integer_quotas(794)
    live_tuples = [item.as_tuple for item in live]
    assert (635, 79, 80) in live_tuples
    assert (635, 80, 79) in live_tuples
    assert len({item.sse for item in live}) == 1


def test_target_distributions_use_identity_grain() -> None:
    rows = [
        _row(index=0, target="DOM", cluster_id="c_dom"),
        _row(index=1, target="DOM", cluster_id="c_dom"),
        _row(index=2, target="OTH", cluster_id="c_dom"),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"s{i:02d}") for i in range(5))
    features, _space = _features(rows)
    assert features["c_dom"].target_counts["DOM"] == 2
    assert features["c_dom"].target_counts["OTH"] == 1
    assert features["c_dom"].n_identities == 3


def test_evidence_distributions_use_identity_grain() -> None:
    rows = [
        _row(index=0, target="T0", cluster_id="c_ev", evidence_level="E2"),
        _row(index=1, target="T1", cluster_id="c_ev", evidence_level="E3"),
        _row(index=2, target="T2", cluster_id="c_ev", evidence_level="E4"),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"s{i:02d}") for i in range(5))
    features, _space = _features(rows)
    assert features["c_ev"].evidence_counts == {"E2": 1, "E3": 1, "E4": 1}


def test_source_distributions_use_identity_grain_source_db() -> None:
    rows = [
        _row(index=0, target="T0", cluster_id="c_src", source_db="ena"),
        _row(index=1, target="T1", cluster_id="c_src", source_db="ena"),
        _row(index=2, target="T2", cluster_id="c_src", source_db="utexas"),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"s{i:02d}") for i in range(5))
    features, space = _features(rows)
    assert features["c_src"].source_counts == {"ena": 2, "utexas": 1}
    assert "extra_ignored" not in space.sources


def test_length_regime_uses_distinct_core_grain() -> None:
    shared = _seq(7)
    rows = [
        _row(index=0, target="T0", cluster_id="c_len", core=shared, length=30),
        _row(index=1, target="T1", cluster_id="c_len", core=shared, length=30),
        _row(index=2, target="T2", cluster_id="c_long", length=80),
    ]
    rows.extend(
        _row(index=20 + i, target=f"U{i}", cluster_id=f"s{i:02d}", length=30) for i in range(5)
    )
    features, space = _features(rows)
    assert features["c_len"].n_cores == 1
    assert features["c_len"].length_counts == {"short": 1}
    assert features["c_long"].length_counts == {"long": 1}
    assert space.global_length["short"] + space.global_length["long"] == space.n_cores
    assert space.n_cores == 7


def test_target_family_absent_from_primary_objective() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    assignment = greedy_assign(features, space, _quotas(6, 1, 1))
    score = score_assignment(assignment, features, space)
    payload = score.as_dict()
    assert payload["target_family_in_primary_objective"] is False
    assert payload["arbitrary_manually_chosen_criterion_weights"] is None
    assert "family" not in PRIMARY_CRITERIA
    assert "target_family" not in COMPARISON_TUPLE_FIELDS
    for feature in features.values():
        feature.family_counts = {"enzyme": feature.n_identities}
    score_after = score_assignment(assignment, features, space)
    assert score_after.comparison_tuple(assignment)[:3] == score.comparison_tuple(assignment)[:3]


def test_multi_target_cluster_contributes_full_vector() -> None:
    rows = [
        _row(index=0, target="TA", cluster_id="c_mix"),
        _row(index=1, target="TB", cluster_id="c_mix"),
        _row(index=2, target="TC", cluster_id="c_mix"),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"s{i:02d}") for i in range(5))
    features, _space = _features(rows)
    assert features["c_mix"].multi_target is True
    assert features["c_mix"].target_counts == {"TA": 1, "TB": 1, "TC": 1}
    states = states_from_assignment(
        {"c_mix": "FT", **{f"s{i:02d}": "FT" for i in range(5)}},
        features,
    )
    assert states["FT"].target["TA"] == 1
    assert states["FT"].target["TB"] == 1
    assert states["FT"].target["TC"] == 1


def test_multi_source_cluster_contributes_full_vector() -> None:
    rows = [
        _row(index=0, target="T0", cluster_id="c_ms", source_db="ena"),
        _row(index=1, target="T1", cluster_id="c_ms", source_db="riboaptamer"),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"s{i:02d}") for i in range(6))
    features, _space = _features(rows)
    assert features["c_ms"].multi_source is True
    assert features["c_ms"].source_counts == {"ena": 1, "riboaptamer": 1}


def test_jsd_support_includes_absent_categories() -> None:
    global_p = [0.5, 0.25, 0.25]
    partition_p = [1.0, 0.0, 0.0]
    value = js_divergence(partition_p, global_p, log_base=2)
    assert 0.0 < value < 1.0
    assert value == js_divergence(global_p, partition_p, log_base=2)


def test_worst_criterion_minimax_objective() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    balanced = {f"c{i:02d}": "FT" for i in range(6)}
    balanced["c06"] = "REF"
    balanced["c07"] = "EVAL"
    good = score_assignment(balanced, features, space)
    worse = ObjectiveScore(
        d_target=0.30,
        d_evidence=0.05,
        d_length=0.05,
        d_source=0.05,
        j_target={"FT": 0.01, "REF": 0.01, "EVAL": 0.30},
        j_evidence={"FT": 0.05, "REF": 0.04, "EVAL": 0.03},
        j_length={"FT": 0.05, "REF": 0.04, "EVAL": 0.03},
        j_source={"FT": 0.05, "REF": 0.04, "EVAL": 0.03},
    )
    better = ObjectiveScore(
        d_target=0.20,
        d_evidence=0.19,
        d_length=0.18,
        d_source=0.17,
        j_target={"FT": 0.1, "REF": 0.2, "EVAL": 0.1},
        j_evidence={"FT": 0.19, "REF": 0.1, "EVAL": 0.1},
        j_length={"FT": 0.18, "REF": 0.1, "EVAL": 0.1},
        j_source={"FT": 0.17, "REF": 0.1, "EVAL": 0.1},
    )
    assert better.o1 < worse.o1
    assert better.comparison_tuple(balanced)[:3] < worse.comparison_tuple(balanced)[:3]
    assert good.o1 == max(good.d_target, good.d_evidence, good.d_length, good.d_source)


def test_descending_divergence_lexicographic_tie_break() -> None:
    left = ObjectiveScore(
        d_target=0.20,
        d_evidence=0.15,
        d_length=0.01,
        d_source=0.01,
        j_target={"FT": 0.2, "REF": 0.1, "EVAL": 0.1},
        j_evidence={"FT": 0.15, "REF": 0.1, "EVAL": 0.1},
        j_length={"FT": 0.01, "REF": 0.01, "EVAL": 0.01},
        j_source={"FT": 0.01, "REF": 0.01, "EVAL": 0.01},
    )
    right = ObjectiveScore(
        d_target=0.20,
        d_evidence=0.10,
        d_length=0.10,
        d_source=0.09,
        j_target={"FT": 0.2, "REF": 0.1, "EVAL": 0.1},
        j_evidence={"FT": 0.1, "REF": 0.1, "EVAL": 0.1},
        j_length={"FT": 0.1, "REF": 0.1, "EVAL": 0.1},
        j_source={"FT": 0.09, "REF": 0.09, "EVAL": 0.09},
    )
    assignment = {"c1": "FT"}
    assert left.o1 == right.o1
    assert right.lex_vector < left.lex_vector
    assert right.comparison_tuple(assignment) < left.comparison_tuple(assignment)


def test_sum_divergence_tie_break() -> None:
    higher = ObjectiveScore(
        d_target=0.20,
        d_evidence=0.10,
        d_length=0.05,
        d_source=0.04,
        j_target={"FT": 0.2, "REF": 0.1, "EVAL": 0.1},
        j_evidence={"FT": 0.1, "REF": 0.1, "EVAL": 0.1},
        j_length={"FT": 0.05, "REF": 0.05, "EVAL": 0.05},
        j_source={"FT": 0.04, "REF": 0.04, "EVAL": 0.04},
    )
    lower = ObjectiveScore(
        d_target=0.20,
        d_evidence=0.10,
        d_length=0.05,
        d_source=0.03,
        j_target={"FT": 0.2, "REF": 0.1, "EVAL": 0.1},
        j_evidence={"FT": 0.1, "REF": 0.1, "EVAL": 0.1},
        j_length={"FT": 0.05, "REF": 0.05, "EVAL": 0.05},
        j_source={"FT": 0.03, "REF": 0.03, "EVAL": 0.03},
    )
    assignment = {"c1": "FT"}
    assert lower.o3 < higher.o3
    assert lower.comparison_tuple(assignment) < higher.comparison_tuple(assignment)
    assert COMPARISON_TUPLE_FIELDS[2] == "O3_sum_primary_D"


def test_stable_assignment_tie_break_is_deterministic() -> None:
    score = ObjectiveScore(
        d_target=0.1,
        d_evidence=0.1,
        d_length=0.1,
        d_source=0.1,
        j_target={"FT": 0.1, "REF": 0.1, "EVAL": 0.1},
        j_evidence={"FT": 0.1, "REF": 0.1, "EVAL": 0.1},
        j_length={"FT": 0.1, "REF": 0.1, "EVAL": 0.1},
        j_source={"FT": 0.1, "REF": 0.1, "EVAL": 0.1},
    )
    first = {"c_b": "FT", "c_a": "REF"}
    second = {"c_a": "FT", "c_b": "REF"}
    assert assignment_signature(first) != assignment_signature(second)
    assert (score.comparison_tuple(first) < score.comparison_tuple(second)) == (
        assignment_signature(first) < assignment_signature(second)
    )
    assert score.comparison_tuple(first) == score.comparison_tuple(
        dict(reversed(list(first.items())))
    )


def test_greedy_placement_respects_capacity() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    assignment = greedy_assign(features, space, _quotas(6, 1, 1))
    counts = Counter(assignment.values())
    assert counts == {"FT": 6, "REF": 1, "EVAL": 1}
    order = cluster_processing_order(features)
    assert order == sorted(features)


def test_local_swaps_never_violate_capacity() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    start = greedy_assign(features, space, _quotas(6, 1, 1))
    improved, _accepted, _passes, _converged = pairwise_local_search(start, features, space)
    assert Counter(improved.values()) == {"FT": 6, "REF": 1, "EVAL": 1}


def test_only_strictly_improving_swaps_accepted() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    start = greedy_assign(features, space, _quotas(6, 1, 1))
    start_key = score_assignment(start, features, space).comparison_tuple(start)
    improved, accepted, _passes, _converged = pairwise_local_search(start, features, space)
    improved_key = score_assignment(improved, features, space).comparison_tuple(improved)
    if accepted:
        assert improved_key < start_key
    else:
        assert improved_key == start_key
        assert improved == start


def test_local_search_terminates_deterministically() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    start = greedy_assign(features, space, _quotas(6, 1, 1))
    first, _accepted_a, passes_a, converged_a = pairwise_local_search(start, features, space)
    second, accepted_b, passes_b, converged_b = pairwise_local_search(first, features, space)
    assert accepted_b == 0
    assert passes_b == 1
    assert first == second
    assert passes_a >= 1
    assert converged_a is True
    assert converged_b is True


def test_input_row_order_does_not_change_final_assignment() -> None:
    rows = [
        _row(
            index=i,
            target=f"T{i}",
            cluster_id=f"c{i:02d}",
            evidence_level="E2" if i < 5 else "E3",
        )
        for i in range(8)
    ]
    features, space = _features(rows)
    first = select_preview_assignment(features, space, derive_integer_quotas(8))
    features_b, space_b = _features(list(reversed(rows)))
    second = select_preview_assignment(features_b, space_b, derive_integer_quotas(8))
    assert first["assignment"] == second["assignment"]


def test_simultaneous_equal_scientific_solutions_resolve_deterministically() -> None:
    winners = derive_integer_quotas(15)
    rows = [
        _row(
            index=i,
            target=f"T{i}",
            cluster_id=f"c{i:02d}",
            evidence_level="E2",
            source_db="srcA",
            length=30,
        )
        for i in range(15)
    ]
    features, space = _features(rows)
    first = select_preview_assignment(features, space, winners)
    second = select_preview_assignment(features, space, list(reversed(list(winners))))
    assert first["assignment"] == second["assignment"]
    assert first["quotas"].as_tuple == second["quotas"].as_tuple


def test_no_partition_field_written_to_s7a_input(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    snapshot = [dict(row) for row in rows]
    payload = _run_preview(tmp_path, rows)
    corpus_path = Path(payload["config_corpus"])
    with corpus_path.open(newline="", encoding="utf-8") as handle:
        written = list(csv.DictReader(handle))
    assert all(row["partition"] == "" for row in written)
    assert input_unmutated(written, snapshot)


def test_e5_and_non_protein_cannot_be_introduced() -> None:
    e5_rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(4)]
    e5_rows[0]["evidence_level"] = "E5"
    with pytest.raises(S7PartitionError, match="E5"):
        verify_frozen_identities(e5_rows)
    non_protein = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(4)]
    non_protein[0]["target_type"] = "small_molecule"
    with pytest.raises(S7PartitionError, match="protein"):
        verify_frozen_identities(non_protein)


def test_no_sequence_values_written_into_preview_metadata(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    payload = _run_preview(tmp_path, rows)
    output_dir = Path(payload["result"]["output_paths"]["cluster_partition_preview_csv"]).parent
    for path in output_dir.iterdir():
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".csv":
            with path.open(newline="", encoding="utf-8") as handle:
                fields = list(csv.DictReader(handle).fieldnames or [])
            assert "sequence_core" not in fields
            assert "sequence_raw" not in fields
            assert "sequence_full" not in fields
        for row in rows:
            assert row["sequence_core"] not in text


def test_existing_s5_s6_s7a_regression_interfaces_remain_intact() -> None:
    assert callable(select_target_cap)
    assert callable(fit_univariate_gmm)
    assert callable(enforce_authorised_parameters)
    gmm1 = fit_univariate_gmm([20.0, 21.0, 22.0], n_components=1)
    assert gmm1["n_components"] == 1
    rows = [_row(index=i, target=f"U{i:03d}", cluster_id=f"c{i:03d}") for i in range(50)]
    result = select_target_cap(rows, max_target_fraction=Decimal("0.03"))
    assert result.steps == []
    assert enforce_authorised_parameters is not None


def test_core_cannot_map_to_two_clusters() -> None:
    shared = _seq(3)
    rows = [
        _row(index=0, target="T0", cluster_id="c_a", core=shared),
        _row(index=1, target="T1", cluster_id="c_b", core=shared),
    ]
    with pytest.raises(S7PartitionError, match="more than one cluster"):
        verify_frozen_identities(rows)


def test_frozen_s6_gmm_loader_rejects_unsorted_means() -> None:
    with pytest.raises(S7PartitionError, match="ascending"):
        load_frozen_s6_gmm(
            {
                "gmm_2": {
                    "means": [80.0, 30.0],
                    "variances": [4.0, 4.0],
                    "weights": [0.5, 0.5],
                }
            }
        )


def test_length_regime_uses_frozen_gmm_not_median() -> None:
    rows = [
        _row(index=0, target="T0", cluster_id="c0", length=50),
        _row(index=1, target="T1", cluster_id="c1", length=51),
        _row(index=2, target="T2", cluster_id="c2", length=30),
        _row(index=3, target="T3", cluster_id="c3", length=80),
    ]
    regimes = assign_length_regimes(rows, SYNTHETIC_GMM)
    assert regimes[_seq(2)] == "short"
    assert regimes[_seq(3)] == "long"
    assert regimes[_seq(0)] == "short"
    assert regimes[_seq(1)] == "short"


def _shared_s7b_policy() -> dict[str, object]:
    return {
        "partition_fractions": {"FT": 0.80, "REF": 0.10, "EVAL": 0.10},
        "length_regime": {
            "assignment_method": "gmm_k2_maximum_posterior",
            "refit_on_post_cap": False,
        },
        "random_baseline_seeds": [1, 2],
        "sequence_safety_scan_paths": [],
    }


def _write_synthetic_s7b_inputs(tmp_path: Path, rows: list[dict[str, str]]) -> dict[str, Path]:
    corpus_path = tmp_path / "data" / "interim" / "s7a_target_cap" / "corpus_post_cap.csv"
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    with corpus_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    bimodality = tmp_path / "data" / "interim" / "deduplicated" / "s6_profile" / "bimodality.json"
    bimodality.parent.mkdir(parents=True, exist_ok=True)
    bimodality.write_text(json.dumps({"gmm_2": SYNTHETIC_GMM}), encoding="utf-8")
    return {
        "corpus_path": corpus_path,
        "bimodality": bimodality,
        "preview_dir": tmp_path / "data" / "interim" / "s7b_partition_preview",
        "apply_dir": tmp_path / "data" / "interim" / "s7b_partition",
    }


def _preview_config_payload(paths: dict[str, Path]) -> dict[str, object]:
    return {
        "contract_id": "global_s7b_partition",
        "milestone": "S7B_partition_preview_dry_run",
        "mode": "preview",
        "authoritative_corpus": str(paths["corpus_path"]),
        "expected_input_sha256": hashlib.sha256(paths["corpus_path"].read_bytes()).hexdigest(),
        "write_authoritative_partitioned_corpus": False,
        "freeze_ref": False,
        "freeze_eval": False,
        "output_dir": str(paths["preview_dir"]),
        "does_not": [
            "write_authoritative_partitioned_corpus",
            "write_corpus_final",
            "freeze_ref",
            "freeze_eval",
            "populate_partition_on_s7a_input",
            "create_train_validation_split",
            "promote_e5",
            "promote_non_protein",
        ],
        **_shared_s7b_policy(),
        "length_regime": {
            "s6_bimodality_json": str(paths["bimodality"]),
            "assignment_method": "gmm_k2_maximum_posterior",
            "refit_on_post_cap": False,
        },
    }


def _approval_from_preview(preview_payload: dict[str, Any], preview_dir: Path) -> dict[str, Any]:
    quotas = preview_payload["selected_quotas"]
    score = preview_payload["score"]
    identity_rows = preview_payload["tables"]["partition_identity_summary.csv"]
    core_rows = preview_payload["tables"]["partition_core_summary.csv"]
    identities = {row["partition"]: int(row["n_identities"]) for row in identity_rows}
    cores = {row["partition"]: int(row["n_distinct_cores"]) for row in core_rows}
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(preview_dir.iterdir())
        if path.is_file()
    }
    return {
        "decision_date": "2026-09-21",
        "review_status": "approved_for_application_and_freeze",
        "frozen_input_sha256": preview_payload["input_sha256"],
        "approved_cluster_quotas": {
            "FT": quotas.n_FT,
            "REF": quotas.n_REF,
            "EVAL": quotas.n_EVAL,
        },
        "approved_identities": identities,
        "approved_cores": cores,
        "approved_objective": {
            "O1": score.o1,
            "D_target": score.d_target,
            "D_evidence": score.d_evidence,
            "D_length": score.d_length,
            "D_source": score.d_source,
            "O3": score.o3,
        },
        "reviewed_preview_hashes": hashes,
        "usage": {
            "audit_record_only": True,
            "used_for_scientific_assignment": False,
        },
    }


def test_select_preview_assignment_does_not_accept_approval_input() -> None:
    import inspect

    assert "approval" not in inspect.signature(select_preview_assignment).parameters
    assert "approval" not in inspect.signature(optimise_partition).parameters


def test_application_writes_partitioned_corpus_and_freezes_ref_eval(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    paths = _write_synthetic_s7b_inputs(tmp_path, rows)
    preview_config = tmp_path / "preview.json"
    preview_config.write_text(json.dumps(_preview_config_payload(paths)), encoding="utf-8")
    preview_payload = run_s7b_partition_preview(
        config_path=preview_config,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=True,
        write_outputs=True,
        run_random_baseline=False,
    )
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(
        json.dumps(_approval_from_preview(preview_payload, paths["preview_dir"])),
        encoding="utf-8",
    )
    freeze_path = tmp_path / "freeze.json"
    apply_config = tmp_path / "apply.json"
    apply_config.write_text(
        json.dumps(
            {
                "contract_id": "global_s7b_partition",
                "milestone": "S7B_partition_application_and_freeze",
                "mode": "apply",
                "authoritative_corpus": str(paths["corpus_path"]),
                "expected_input_sha256": preview_payload["input_sha256"],
                "write_authoritative_partitioned_corpus": True,
                "freeze_ref": True,
                "freeze_eval": True,
                "preview_output_dir": str(paths["preview_dir"]),
                "output_dir": str(paths["apply_dir"]),
                "approval_record": str(approval_path),
                "freeze_record": str(freeze_path),
                "does_not": [
                    "write_corpus_final",
                    "create_train_validation_split",
                    "promote_e5",
                    "promote_non_protein",
                    "rewrite_s5",
                    "rewrite_s6",
                    "rewrite_s7a",
                    "start_s7c",
                ],
                **_shared_s7b_policy(),
                "length_regime": {
                    "s6_bimodality_json": str(paths["bimodality"]),
                    "assignment_method": "gmm_k2_maximum_posterior",
                    "refit_on_post_cap": False,
                },
            }
        ),
        encoding="utf-8",
    )
    payload = run_s7b_partition_apply(
        config_path=apply_config,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=True,
        write_outputs=True,
        run_random_baseline=False,
    )
    corpus_path = Path(payload["output_paths"]["corpus_partitioned_csv"])
    with corpus_path.open(newline="", encoding="utf-8") as handle:
        written = list(csv.DictReader(handle))
    assert len(written) == 8
    assert all(row["partition"] in {"FT", "REF", "EVAL"} for row in written)
    assert payload["parity"]["semantic_mismatches_total"] == 0
    assert payload["approval_used_for_scientific_assignment"] is False
    assert payload["ref_frozen"] is True
    assert payload["eval_frozen"] is True
    assert payload["assignment"] == preview_payload["assignment"]
    assert freeze_path.is_file()
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert freeze["REF"]["frozen"] is True
    assert freeze["EVAL"]["frozen"] is True
    assert freeze["FT"]["train_validation_split"] is False
    assert freeze["s7c_started"] is False
    assert not (paths["apply_dir"] / "corpus_final.csv").exists()
    assert not (tmp_path / "corpus_final.txt").exists()
    preview_after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths["preview_dir"].iterdir())
        if path.is_file()
    }
    assert preview_after == payload["preview_hashes"]


def test_application_does_not_use_approval_for_assignment(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    paths = _write_synthetic_s7b_inputs(tmp_path, rows)
    preview_config = tmp_path / "preview.json"
    preview_config.write_text(json.dumps(_preview_config_payload(paths)), encoding="utf-8")
    preview_payload = run_s7b_partition_preview(
        config_path=preview_config,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=False,
        write_outputs=True,
        run_random_baseline=False,
    )
    approval = _approval_from_preview(preview_payload, paths["preview_dir"])
    approval["approved_cluster_quotas"] = {"FT": 1, "REF": 1, "EVAL": 6}
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    apply_config = tmp_path / "apply.json"
    apply_config.write_text(
        json.dumps(
            {
                "contract_id": "global_s7b_partition",
                "milestone": "S7B_partition_application_and_freeze",
                "mode": "apply",
                "authoritative_corpus": str(paths["corpus_path"]),
                "expected_input_sha256": preview_payload["input_sha256"],
                "write_authoritative_partitioned_corpus": True,
                "freeze_ref": True,
                "freeze_eval": True,
                "preview_output_dir": str(paths["preview_dir"]),
                "output_dir": str(paths["apply_dir"]),
                "approval_record": str(approval_path),
                "does_not": [
                    "write_corpus_final",
                    "create_train_validation_split",
                    "promote_e5",
                    "promote_non_protein",
                    "rewrite_s5",
                    "rewrite_s6",
                    "rewrite_s7a",
                    "start_s7c",
                ],
                **_shared_s7b_policy(),
                "length_regime": {
                    "s6_bimodality_json": str(paths["bimodality"]),
                    "assignment_method": "gmm_k2_maximum_posterior",
                    "refit_on_post_cap": False,
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(S7PartitionError, match="approval/application semantic mismatches"):
        run_s7b_partition_apply(
            config_path=apply_config,
            repo_root=tmp_path,
            verify_hashes=False,
            enforce_expected_counts=False,
            repeat_for_determinism=False,
            write_outputs=True,
            run_random_baseline=False,
        )
    assert not (paths["apply_dir"] / "corpus_partitioned.csv").exists()
    assert preview_payload["assignment"] != {}


def test_application_refuses_to_overwrite_preview_dir(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    paths = _write_synthetic_s7b_inputs(tmp_path, rows)
    apply_config = tmp_path / "apply.json"
    apply_config.write_text(
        json.dumps(
            {
                "contract_id": "global_s7b_partition",
                "milestone": "S7B_partition_application_and_freeze",
                "mode": "apply",
                "authoritative_corpus": str(paths["corpus_path"]),
                "expected_input_sha256": "synthetic",
                "write_authoritative_partitioned_corpus": True,
                "freeze_ref": True,
                "freeze_eval": True,
                "preview_output_dir": str(paths["preview_dir"]),
                "output_dir": str(paths["preview_dir"]),
                "does_not": [
                    "write_corpus_final",
                    "create_train_validation_split",
                    "promote_e5",
                    "promote_non_protein",
                    "rewrite_s5",
                    "rewrite_s6",
                    "rewrite_s7a",
                    "start_s7c",
                ],
                **_shared_s7b_policy(),
                "length_regime": {
                    "s6_bimodality_json": str(paths["bimodality"]),
                    "assignment_method": "gmm_k2_maximum_posterior",
                    "refit_on_post_cap": False,
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(S7PartitionError, match="must not write to the reviewed preview directory"):
        run_s7b_partition_apply(
            config_path=apply_config,
            repo_root=tmp_path,
            verify_hashes=False,
            enforce_expected_counts=False,
            repeat_for_determinism=False,
            write_outputs=False,
            require_preview_parity=False,
            require_approval_parity=False,
        )


def test_application_preserves_non_partition_fields(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    snapshot = [dict(row) for row in rows]
    paths = _write_synthetic_s7b_inputs(tmp_path, rows)
    preview_config = tmp_path / "preview.json"
    preview_config.write_text(json.dumps(_preview_config_payload(paths)), encoding="utf-8")
    preview_payload = run_s7b_partition_preview(
        config_path=preview_config,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=False,
        write_outputs=True,
        run_random_baseline=False,
    )
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(
        json.dumps(_approval_from_preview(preview_payload, paths["preview_dir"])),
        encoding="utf-8",
    )
    apply_config = tmp_path / "apply.json"
    apply_config.write_text(
        json.dumps(
            {
                "contract_id": "global_s7b_partition",
                "milestone": "S7B_partition_application_and_freeze",
                "mode": "apply",
                "authoritative_corpus": str(paths["corpus_path"]),
                "expected_input_sha256": preview_payload["input_sha256"],
                "write_authoritative_partitioned_corpus": True,
                "freeze_ref": True,
                "freeze_eval": True,
                "preview_output_dir": str(paths["preview_dir"]),
                "output_dir": str(paths["apply_dir"]),
                "approval_record": str(approval_path),
                "does_not": [
                    "write_corpus_final",
                    "create_train_validation_split",
                    "promote_e5",
                    "promote_non_protein",
                    "rewrite_s5",
                    "rewrite_s6",
                    "rewrite_s7a",
                    "start_s7c",
                ],
                **_shared_s7b_policy(),
                "length_regime": {
                    "s6_bimodality_json": str(paths["bimodality"]),
                    "assignment_method": "gmm_k2_maximum_posterior",
                    "refit_on_post_cap": False,
                },
            }
        ),
        encoding="utf-8",
    )
    payload = run_s7b_partition_apply(
        config_path=apply_config,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=False,
        write_outputs=True,
        run_random_baseline=False,
    )
    written_path = Path(payload["output_paths"]["corpus_partitioned_csv"])
    with written_path.open(newline="", encoding="utf-8") as handle:
        written = list(csv.DictReader(handle))
    by_id = {row["scientific_identity_id"]: row for row in snapshot}
    for row in written:
        original = by_id[row["scientific_identity_id"]]
        for key, value in original.items():
            if key == "partition":
                continue
            assert row[key] == value
        assert row["partition"] in {"FT", "REF", "EVAL"}
    assert input_unmutated(rows, snapshot)

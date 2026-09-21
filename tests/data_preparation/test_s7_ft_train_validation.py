"""Synthetic tests for S7C FT-only train/validation split preview and application.

Every literal nucleotide string in this file is shorter than 20 nt.
Tests do not read live biological S5/S7A/S7B CSVs except the optional
S7B assignment-fingerprint regression, which uses the shared optimiser
on synthetic rows only.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
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
from adapters.s7_ft_train_validation import (  # noqa: E402
    COMPARISON_TUPLE_FIELDS,
    S7C_COMPARISON_TUPLE_FIELDS,
    S7C_OBJECTIVE_PROFILE,
    S7C_PLACEMENT_LABELS,
    S7C_REPORT_LABELS,
    S7CSplitError,
    TRAIN_LABEL,
    VALIDATION_LABEL,
    assert_ref_eval_matches_expected,
    assert_ref_eval_unchanged,
    blank_partition_copy,
    build_s7c_preview_tables,
    derive_integer_quota_pairs,
    family_jsd_by_partition,
    frozen_ref_eval_expected,
    s7c_integrity_gates,
    s7c_target_diagnostics,
    score_s7c_assignment,
    select_s7c_assignment,
    snapshot_ref_eval_freeze,
    verify_ft_split_input,
)
from adapters.s7_partition import (  # noqa: E402
    OBJECTIVE_PROFILE_ABSDEV,
    OBJECTIVE_PROFILE_JSD,
    PRIMARY_CRITERIA,
    assignment_signature,
    build_cluster_features,
    counts_to_probs,
    greedy_assign,
    input_unmutated,
    js_divergence,
    load_frozen_s6_gmm,
    max_abs_proportion_deviation,
    ObjectiveScore,
    optimise_partition,
    pairwise_local_search,
    QuotaTriple,
    states_from_assignment,
)
from adapters.s7_target_cap import select_target_cap  # noqa: E402
from s7_ft_train_validation import (  # noqa: E402
    run_s7c_ft_split_apply,
    run_s7c_ft_split_preview,
)

BASES = "ACGU"
SYNTHETIC_GMM = {
    "n_components": 2,
    "means": [30.0, 80.0],
    "variances": [4.0, 4.0],
    "weights": [0.5, 0.5],
}
S7B_SYNTHETIC_ASSIGNMENT_FINGERPRINT = (
    "c00:EVAL|c01:FT|c02:FT|c03:FT|c04:FT|c05:FT|c06:FT|c07:REF"
)


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
    partition: str = "FT",
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


def _features(rows: list[dict[str, str]]):
    working = blank_partition_copy(rows)
    from adapters.s7_partition import assign_length_regimes

    regimes = assign_length_regimes(working, SYNTHETIC_GMM)
    return build_cluster_features(working, regimes)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _s7c_preview_config_payload(paths: dict[str, Path], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "contract_id": "global_s7c_ft_train_validation",
        "milestone": "S7C_ft_train_validation_preview_dry_run",
        "mode": "preview",
        "ft_csv": str(paths["ft_path"]),
        "ref_csv": str(paths["ref_path"]),
        "eval_csv": str(paths["eval_path"]),
        "expected_ft_sha256": hashlib.sha256(paths["ft_path"].read_bytes()).hexdigest(),
        "expected_ref_sha256": hashlib.sha256(paths["ref_path"].read_bytes()).hexdigest(),
        "expected_eval_sha256": hashlib.sha256(paths["eval_path"].read_bytes()).hexdigest(),
        "split_fractions": {"TRAIN": 0.90, "VALIDATION": 0.10},
        "length_regime": {
            "s6_bimodality_json": str(paths["bimodality"]),
            "assignment_method": "gmm_k2_maximum_posterior",
            "refit_on_post_cap": False,
        },
        "random_baseline_seeds": [1, 2],
        "write_authoritative_train_validation": False,
        "freeze_ft_train": False,
        "freeze_ft_validation": False,
        "alter_top_level_partition": False,
        "preview_output_dir": str(paths["output_dir"]),
        "does_not": [
            "write_ft_train_csv",
            "write_ft_validation_csv",
            "write_corpus_final",
            "alter_ft_csv",
            "alter_ref_csv",
            "alter_eval_csv",
            "alter_top_level_partition",
            "start_fine_tuning",
            "use_validation_for_model_decision",
            "promote_e5",
            "promote_non_protein",
        ],
        "sequence_safety_scan_paths": [],
    }
    if extra:
        payload.update(extra)
    return payload


def _write_s7c_inputs(tmp_path: Path, ft_rows: list[dict[str, str]]) -> dict[str, Path]:
    ft_path = tmp_path / "ft.csv"
    ref_path = tmp_path / "ref.csv"
    eval_path = tmp_path / "eval.csv"
    _write_csv(ft_path, ft_rows)
    ref_rows = [
        _row(index=900, target="REF_T", cluster_id="ref_c", partition="REF"),
    ]
    eval_rows = [
        _row(index=901, target="EVAL_T", cluster_id="eval_c", partition="EVAL"),
    ]
    _write_csv(ref_path, ref_rows)
    _write_csv(eval_path, eval_rows)
    bimodality = tmp_path / "bimodality.json"
    bimodality.write_text(json.dumps({"gmm_2": SYNTHETIC_GMM}), encoding="utf-8")
    output_dir = tmp_path / "preview"
    return {
        "ft_path": ft_path,
        "ref_path": ref_path,
        "eval_path": eval_path,
        "bimodality": bimodality,
        "output_dir": output_dir,
    }


def _run_preview(tmp_path: Path, rows: list[dict[str, str]], **kwargs: Any) -> dict[str, Any]:
    paths = _write_s7c_inputs(tmp_path, rows)
    config_path = tmp_path / "config.json"
    payload = _s7c_preview_config_payload(paths)
    ref_rows = list(csv.DictReader(paths["ref_path"].open(newline="", encoding="utf-8")))
    eval_rows = list(csv.DictReader(paths["eval_path"].open(newline="", encoding="utf-8")))
    snap = snapshot_ref_eval_freeze(
        ref_rows,
        eval_rows,
        ref_sha256=hashlib.sha256(paths["ref_path"].read_bytes()).hexdigest(),
        eval_sha256=hashlib.sha256(paths["eval_path"].read_bytes()).hexdigest(),
    )
    payload.update(
        {
            "expected_ref_identity_set_hash": snap.ref_identity_set_hash,
            "expected_ref_cluster_set_hash": snap.ref_cluster_set_hash,
            "expected_eval_identity_set_hash": snap.eval_identity_set_hash,
            "expected_eval_cluster_set_hash": snap.eval_cluster_set_hash,
            "expected_ref_clusters": 1,
            "expected_eval_clusters": 1,
        }
    )
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    result = run_s7c_ft_split_preview(
        config_path=config_path,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=True,
        write_outputs=True,
        run_random_baseline=True,
        verify_ref_eval_freeze=True,
        **kwargs,
    )
    return {"result": result, "paths": paths, "snapshot": snap}


def test_only_ft_clusters_may_enter_the_split() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    observed = verify_ft_split_input(rows)
    assert observed["n_final_clusters"] == 8
    mixed = rows + [_row(index=99, target="TX", cluster_id="c_x", partition="HOLD")]
    with pytest.raises(S7CSplitError, match="only partition=FT"):
        verify_ft_split_input(mixed)


def test_ref_clusters_rejected_if_supplied() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(4)]
    rows.append(_row(index=50, target="R", cluster_id="ref_c", partition="REF"))
    with pytest.raises(S7CSplitError, match="REF"):
        verify_ft_split_input(rows)
    disguised = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(4)]
    disguised.append(_row(index=51, target="R2", cluster_id="ref_c", partition="FT"))
    with pytest.raises(S7CSplitError, match="REF clusters"):
        verify_ft_split_input(disguised, ref_cluster_ids=["ref_c"])


def test_eval_clusters_rejected_if_supplied() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(4)]
    rows.append(_row(index=60, target="E", cluster_id="eval_c", partition="EVAL"))
    with pytest.raises(S7CSplitError, match="EVAL"):
        verify_ft_split_input(rows)
    disguised = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(4)]
    disguised.append(_row(index=61, target="E2", cluster_id="eval_c", partition="FT"))
    with pytest.raises(S7CSplitError, match="EVAL clusters"):
        verify_ft_split_input(disguised, eval_cluster_ids=["eval_c"])


def test_every_ft_cluster_assigned_exactly_once() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    result = select_s7c_assignment(features, space, derive_integer_quota_pairs(8))
    assert set(result["assignment"]) == set(features)
    assert len(result["assignment"]) == 8
    assert set(result["assignment"].values()) <= set(S7C_REPORT_LABELS)


def test_no_ft_cluster_split() -> None:
    rows = [
        _row(index=0, target="T0", cluster_id="c_multi", evidence_level="E2"),
        _row(index=1, target="T1", cluster_id="c_multi", evidence_level="E3"),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"c{i:02d}") for i in range(7))
    features, space = _features(rows)
    result = select_s7c_assignment(features, space, derive_integer_quota_pairs(8))
    labels = {result["assignment"]["c_multi"]}
    assert len(labels) == 1


def test_every_ft_identity_follows_its_cluster() -> None:
    rows = [
        _row(index=0, target="T0", cluster_id="c_multi"),
        _row(index=1, target="T1", cluster_id="c_multi"),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"c{i:02d}") for i in range(7))
    features, space = _features(rows)
    result = select_s7c_assignment(features, space, derive_integer_quota_pairs(8))
    integrity = s7c_integrity_gates(rows, result["assignment"], features, result["quotas"])
    assert integrity["identities_assigned_exactly_once"] is True
    mapped = {row["scientific_identity_id"]: result["assignment"][row["cluster_id"]] for row in rows}
    assert mapped[rows[0]["scientific_identity_id"]] == mapped[rows[1]["scientific_identity_id"]]


def test_every_ft_core_follows_its_cluster() -> None:
    shared_core = _seq(0)
    rows = [
        _row(index=0, target="T0", cluster_id="c_core", core=shared_core),
        _row(index=1, target="T1", cluster_id="c_core", core=shared_core),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"c{i:02d}") for i in range(7))
    features, space = _features(rows)
    result = select_s7c_assignment(features, space, derive_integer_quota_pairs(8))
    integrity = s7c_integrity_gates(rows, result["assignment"], features, result["quotas"])
    assert integrity["cores_cross_partitions"] == 0
    assert features["c_core"].n_cores == 1


def test_integer_90_10_quota_derivation() -> None:
    winners = derive_integer_quota_pairs(8)
    assert [item.as_tuple for item in winners] == [(7, 1)]
    live = derive_integer_quota_pairs(635)
    tuples = [item.as_tuple for item in live]
    assert all(sum(item) == 635 for item in tuples)
    assert all(item[0] + item[1] == 635 for item in tuples)


def test_tied_optimal_quota_configurations_retained() -> None:
    live = derive_integer_quota_pairs(635)
    live_tuples = [item.as_tuple for item in live]
    assert (571, 64) in live_tuples
    assert (572, 63) in live_tuples
    assert len({item.sse for item in live}) == 1
    small = derive_integer_quota_pairs(15)
    small_tuples = [item.as_tuple for item in small]
    assert (13, 2) in small_tuples
    assert (14, 1) in small_tuples


def test_target_identity_grain_distribution() -> None:
    rows = [
        _row(index=0, target="DOM", cluster_id="c_dom"),
        _row(index=1, target="DOM", cluster_id="c_dom"),
        _row(index=2, target="OTH", cluster_id="c_dom"),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"s{i:02d}") for i in range(5))
    features, space = _features(rows)
    assert features["c_dom"].target_counts["DOM"] == 2
    assert features["c_dom"].target_counts["OTH"] == 1
    assert space.global_target["DOM"] == 2


def test_evidence_identity_grain_distribution() -> None:
    rows = [
        _row(index=0, target="T0", cluster_id="c_ev", evidence_level="E2"),
        _row(index=1, target="T1", cluster_id="c_ev", evidence_level="E3"),
        _row(index=2, target="T2", cluster_id="c_ev", evidence_level="E4"),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"s{i:02d}") for i in range(5))
    features, space = _features(rows)
    assert features["c_ev"].evidence_counts == {"E2": 1, "E3": 1, "E4": 1}
    assert space.global_evidence["E2"] >= 1


def test_source_identity_grain_distribution() -> None:
    rows = [
        _row(index=0, target="T0", cluster_id="c_src", source_db="ena"),
        _row(index=1, target="T1", cluster_id="c_src", source_db="ena"),
    ]
    rows.extend(
        _row(index=10 + i, target=f"U{i}", cluster_id=f"s{i:02d}", source_db="aptabase")
        for i in range(6)
    )
    features, space = _features(rows)
    assert features["c_src"].source_counts == {"ena": 2}
    assert space.global_source["ena"] == 2
    assert "extra_ignored" not in space.global_source


def test_length_distinct_core_grain() -> None:
    rows = [
        _row(index=0, target="T0", cluster_id="c_len", length=30, core=_seq(0)),
        _row(index=1, target="T1", cluster_id="c_len", length=30, core=_seq(0)),
        _row(index=2, target="T2", cluster_id="c_long", length=80),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"s{i:02d}") for i in range(5))
    features, space = _features(rows)
    assert features["c_len"].n_cores == 1
    assert features["c_len"].length_counts["short"] == 1
    assert features["c_long"].length_counts["long"] == 1
    assert space.global_length["short"] + space.global_length["long"] == space.n_cores


def test_target_family_excluded_from_primary_objective() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    result = select_s7c_assignment(features, space, derive_integer_quota_pairs(8))
    payload = result["score"].as_dict()
    assert payload["target_family_in_primary_objective"] is False
    assert payload["arbitrary_manually_chosen_criterion_weights"] is None
    assert "family" not in PRIMARY_CRITERIA
    assert "target_family" not in COMPARISON_TUPLE_FIELDS
    assert "target_family" not in S7C_COMPARISON_TUPLE_FIELDS
    assert result["score"].profile == S7C_OBJECTIVE_PROFILE == OBJECTIVE_PROFILE_ABSDEV
    for feature in features.values():
        feature.family_counts = {"enzyme": feature.n_identities}
    score_after = score_s7c_assignment(result["assignment"], features, space)
    assert score_after.comparison_tuple(result["assignment"])[:5] == result["score"].comparison_tuple(
        result["assignment"]
    )[:5]


def test_multi_target_cluster_full_vector() -> None:
    rows = [
        _row(index=0, target="TA", cluster_id="c_mix"),
        _row(index=1, target="TB", cluster_id="c_mix"),
        _row(index=2, target="TC", cluster_id="c_mix"),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"s{i:02d}") for i in range(5))
    features, space = _features(rows)
    assert features["c_mix"].multi_target is True
    assert features["c_mix"].target_counts == {"TA": 1, "TB": 1, "TC": 1}
    assignment = {"c_mix": TRAIN_LABEL, **{f"s{i:02d}": TRAIN_LABEL for i in range(5)}}
    states = states_from_assignment(
        assignment, features, space, partition_labels=S7C_REPORT_LABELS
    )
    assert states[TRAIN_LABEL].target["TA"] == 1
    assert states[TRAIN_LABEL].target["TB"] == 1
    assert states[TRAIN_LABEL].target["TC"] == 1


def test_multi_source_cluster_full_vector() -> None:
    rows = [
        _row(index=0, target="T0", cluster_id="c_ms", source_db="ena"),
        _row(index=1, target="T1", cluster_id="c_ms", source_db="riboaptamer"),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"s{i:02d}") for i in range(6))
    features, space = _features(rows)
    assert features["c_ms"].multi_source is True
    assert features["c_ms"].source_counts == {"ena": 1, "riboaptamer": 1}


def test_jsd_uses_full_ft_support() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    result = select_s7c_assignment(features, space, derive_integer_quota_pairs(8))
    states = states_from_assignment(
        result["assignment"], features, space, partition_labels=S7C_REPORT_LABELS
    )
    val_targets = states[VALIDATION_LABEL].target
    assert len(space.targets) == 8
    missing = [name for name in space.targets if val_targets.get(name, 0) == 0]
    assert missing
    global_p = counts_to_probs(space.global_target, space.targets)
    val_p = counts_to_probs(val_targets, space.targets)
    assert val_p is not None
    assert len(val_p) == len(global_p) == len(space.targets)
    assert js_divergence(val_p, global_p) >= 0.0
    assert len(val_p) == len(space.targets)
    assert pytest.approx(result["score"].j_target[VALIDATION_LABEL], rel=1e-9, abs=1e-12) == js_divergence(
        val_p, global_p
    )


def test_minimax_objective() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    result = select_s7c_assignment(features, space, derive_integer_quota_pairs(8))
    score = result["score"]
    assert score.r1 == max(score.m_target, score.m_evidence, score.m_length, score.m_source)
    assert score.m_target == max(score.a_target.values())
    assert score.m_evidence == max(score.a_evidence.values())
    assert score.o1 == max(score.d_target, score.d_evidence, score.d_length, score.d_source)
    assert score.scientific_prefix()[0] == score.r1


def test_lexicographic_divergence_tie_break() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    score = select_s7c_assignment(features, space, derive_integer_quota_pairs(8))["score"]
    m_lex = score.m_lex_vector
    assert m_lex == tuple(sorted(m_lex, reverse=True))
    assert score.scientific_prefix()[1] == m_lex
    d_lex = score.lex_vector
    assert d_lex == tuple(sorted(d_lex, reverse=True))
    assert score.scientific_prefix()[3] == d_lex


def test_sum_divergence_tie_break() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    score = select_s7c_assignment(features, space, derive_integer_quota_pairs(8))["score"]
    assert score.r3 == score.m_target + score.m_evidence + score.m_length + score.m_source
    assert score.scientific_prefix()[2] == score.r3
    assert score.o3 == score.d_target + score.d_evidence + score.d_length + score.d_source
    assert score.scientific_prefix()[4] == score.o3


def test_stable_assignment_tie_break() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    first = select_s7c_assignment(features, space, derive_integer_quota_pairs(8))
    second = select_s7c_assignment(features, space, derive_integer_quota_pairs(8))
    assert first["assignment"] == second["assignment"]
    assert first["comparison_tuple"][-1] == assignment_signature(first["assignment"])
    assert S7C_PLACEMENT_LABELS == ("TRAIN", "VALIDATION")


def test_greedy_capacity_enforcement() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    quotas = derive_integer_quota_pairs(8)[0]
    assignment = greedy_assign(
        features,
        space,
        quotas,
        partition_labels=S7C_REPORT_LABELS,
        placement_labels=S7C_PLACEMENT_LABELS,
        objective_profile=OBJECTIVE_PROFILE_ABSDEV,
    )
    assert Counter(assignment.values()) == quotas.as_dict()


def test_local_swap_quota_preservation() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    quotas = derive_integer_quota_pairs(8)[0]
    start = greedy_assign(
        features,
        space,
        quotas,
        partition_labels=S7C_REPORT_LABELS,
        placement_labels=S7C_PLACEMENT_LABELS,
        objective_profile=OBJECTIVE_PROFILE_ABSDEV,
    )
    improved, _accepted, _passes, _converged = pairwise_local_search(
        start,
        features,
        space,
        partition_labels=S7C_REPORT_LABELS,
        placement_labels=S7C_PLACEMENT_LABELS,
        log_prefix="S7C",
        objective_profile=OBJECTIVE_PROFILE_ABSDEV,
    )
    assert Counter(improved.values()) == quotas.as_dict()


def test_only_strict_improvement_swaps() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    quotas = derive_integer_quota_pairs(8)[0]
    start = greedy_assign(
        features,
        space,
        quotas,
        partition_labels=S7C_REPORT_LABELS,
        placement_labels=S7C_PLACEMENT_LABELS,
        objective_profile=OBJECTIVE_PROFILE_ABSDEV,
    )
    start_key = score_s7c_assignment(start, features, space).comparison_tuple(start)
    improved, accepted, _passes, _converged = pairwise_local_search(
        start,
        features,
        space,
        partition_labels=S7C_REPORT_LABELS,
        placement_labels=S7C_PLACEMENT_LABELS,
        log_prefix="S7C",
        objective_profile=OBJECTIVE_PROFILE_ABSDEV,
    )
    improved_key = score_s7c_assignment(improved, features, space).comparison_tuple(improved)
    if accepted:
        assert improved_key < start_key
    else:
        assert improved_key == start_key
        assert improved == start


def test_deterministic_termination() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    quotas = derive_integer_quota_pairs(8)[0]
    start = greedy_assign(
        features,
        space,
        quotas,
        partition_labels=S7C_REPORT_LABELS,
        placement_labels=S7C_PLACEMENT_LABELS,
        objective_profile=OBJECTIVE_PROFILE_ABSDEV,
    )
    first, _accepted_a, passes_a, converged_a = pairwise_local_search(
        start,
        features,
        space,
        partition_labels=S7C_REPORT_LABELS,
        placement_labels=S7C_PLACEMENT_LABELS,
        log_prefix="S7C",
        objective_profile=OBJECTIVE_PROFILE_ABSDEV,
    )
    second, accepted_b, passes_b, converged_b = pairwise_local_search(
        first,
        features,
        space,
        partition_labels=S7C_REPORT_LABELS,
        placement_labels=S7C_PLACEMENT_LABELS,
        log_prefix="S7C",
        objective_profile=OBJECTIVE_PROFILE_ABSDEV,
    )
    assert accepted_b == 0
    assert passes_b == 1
    assert first == second
    assert passes_a >= 1
    assert converged_a is True
    assert converged_b is True


def test_input_row_order_invariance() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    first = select_s7c_assignment(features, space, derive_integer_quota_pairs(8))
    reversed_features, reversed_space = _features(list(reversed(rows)))
    second = select_s7c_assignment(
        reversed_features, reversed_space, derive_integer_quota_pairs(8)
    )
    assert first["assignment"] == second["assignment"]


def test_ref_hash_guard(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    paths = _write_s7c_inputs(tmp_path, rows)
    payload = _s7c_preview_config_payload(paths)
    payload["expected_ref_sha256"] = "0" * 64
    payload["expected_ref_clusters"] = 1
    payload["expected_eval_clusters"] = 1
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(S7CSplitError, match="REF/EVAL freeze guard failed"):
        run_s7c_ft_split_preview(
            config_path=config_path,
            repo_root=tmp_path,
            verify_hashes=False,
            enforce_expected_counts=False,
            repeat_for_determinism=False,
            write_outputs=False,
            run_random_baseline=False,
            verify_ref_eval_freeze=True,
        )


def test_eval_hash_guard(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    paths = _write_s7c_inputs(tmp_path, rows)
    payload = _s7c_preview_config_payload(paths)
    payload["expected_eval_sha256"] = "1" * 64
    payload["expected_ref_clusters"] = 1
    payload["expected_eval_clusters"] = 1
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(S7CSplitError, match="REF/EVAL freeze guard failed"):
        run_s7c_ft_split_preview(
            config_path=config_path,
            repo_root=tmp_path,
            verify_hashes=False,
            enforce_expected_counts=False,
            repeat_for_determinism=False,
            write_outputs=False,
            run_random_baseline=False,
            verify_ref_eval_freeze=True,
        )


def test_ref_semantic_set_guard() -> None:
    ref_rows = [_row(index=1, target="R", cluster_id="ref_c", partition="REF")]
    eval_rows = [_row(index=2, target="E", cluster_id="eval_c", partition="EVAL")]
    snap = snapshot_ref_eval_freeze(
        ref_rows, eval_rows, ref_sha256="aa", eval_sha256="bb"
    )
    expected = {
        "ref_sha256": "aa",
        "eval_sha256": "bb",
        "ref_identity_set_hash": "deadbeef",
        "ref_cluster_set_hash": snap.ref_cluster_set_hash,
        "eval_identity_set_hash": snap.eval_identity_set_hash,
        "eval_cluster_set_hash": snap.eval_cluster_set_hash,
        "n_ref_clusters": 1,
        "n_eval_clusters": 1,
    }
    with pytest.raises(S7CSplitError, match="ref_identity_set_hash"):
        assert_ref_eval_matches_expected(snap, expected)


def test_eval_semantic_set_guard() -> None:
    ref_rows = [_row(index=1, target="R", cluster_id="ref_c", partition="REF")]
    eval_rows = [_row(index=2, target="E", cluster_id="eval_c", partition="EVAL")]
    snap = snapshot_ref_eval_freeze(
        ref_rows, eval_rows, ref_sha256="aa", eval_sha256="bb"
    )
    expected = {
        "ref_sha256": "aa",
        "eval_sha256": "bb",
        "ref_identity_set_hash": snap.ref_identity_set_hash,
        "ref_cluster_set_hash": snap.ref_cluster_set_hash,
        "eval_identity_set_hash": snap.eval_identity_set_hash,
        "eval_cluster_set_hash": "cafebabe",
        "n_ref_clusters": 1,
        "n_eval_clusters": 1,
    }
    with pytest.raises(S7CSplitError, match="eval_cluster_set_hash"):
        assert_ref_eval_matches_expected(snap, expected)
    other = snapshot_ref_eval_freeze(
        ref_rows, eval_rows, ref_sha256="aa", eval_sha256="changed"
    )
    with pytest.raises(S7CSplitError, match="changed during S7C"):
        assert_ref_eval_unchanged(snap, other)


def test_ft_csv_input_is_not_modified(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    snapshot = [dict(row) for row in rows]
    payload = _run_preview(tmp_path, rows)
    ft_path = payload["paths"]["ft_path"]
    reloaded = list(csv.DictReader(ft_path.open(newline="", encoding="utf-8")))
    assert reloaded == snapshot
    assert input_unmutated(rows, snapshot)
    assert all(row["partition"] == "FT" for row in reloaded)


def test_preview_does_not_alter_top_level_partition(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    payload = _run_preview(tmp_path, rows)
    result = payload["result"]
    assert result["integrity"]["top_level_partition_altered"] is False
    cluster_rows = result["tables"]["cluster_ft_split_preview.csv"]
    assert all("proposed_ft_split" in row for row in cluster_rows)
    assert all(row["proposed_ft_split"] in S7C_REPORT_LABELS for row in cluster_rows)
    assert not (payload["paths"]["output_dir"] / "ft_train.csv").exists()
    assert not (payload["paths"]["output_dir"] / "ft_validation.csv").exists()
    ft_reloaded = list(csv.DictReader(payload["paths"]["ft_path"].open(newline="", encoding="utf-8")))
    assert {row["partition"] for row in ft_reloaded} == {"FT"}


def test_e5_and_non_protein_cannot_be_introduced() -> None:
    e5 = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(3)]
    e5.append(_row(index=9, target="TX", cluster_id="c_e5", evidence_level="E5"))
    with pytest.raises(S7CSplitError, match="E5"):
        verify_ft_split_input(e5)
    non_protein = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(3)]
    non_protein.append(
        _row(index=9, target="TX", cluster_id="c_np", target_type="small_molecule")
    )
    with pytest.raises(S7CSplitError, match="protein"):
        verify_ft_split_input(non_protein)


def test_no_sequence_values_in_preview_metadata(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    payload = _run_preview(tmp_path, rows)
    output_dir = payload["paths"]["output_dir"]
    sequences = {_seq(i) for i in range(8)}
    for path in output_dir.iterdir():
        text = path.read_text(encoding="utf-8")
        for seq in sequences:
            assert seq not in text
        if path.suffix == ".csv":
            header = text.splitlines()[0]
            assert "sequence_raw" not in header
            assert "sequence_full" not in header
            assert "sequence_core," not in header + ","
            assert not header.startswith("sequence_core")


def test_s7a_s5_s6_interfaces_remain_intact() -> None:
    assert callable(select_target_cap)
    assert callable(fit_univariate_gmm)
    assert callable(enforce_authorised_parameters)
    gmm1 = fit_univariate_gmm([20.0, 21.0, 22.0], n_components=1)
    assert gmm1["n_components"] == 1
    load_frozen_s6_gmm({"gmm_2": SYNTHETIC_GMM})


def test_frozen_s7b_assignment_unchanged_after_shared_refactor() -> None:
    rows = [
        {
            "scientific_identity_id": scientific_identity_id(_seq(i), f"T{i}"),
            "cluster_id": f"c{i:02d}",
            "canonical_target_name": f"T{i}",
            "sequence_core": _seq(i),
            "sequence_length_core": "30",
            "evidence_level": "E2",
            "source_db": "srcA",
            "contributing_sources": "srcA|extra_ignored",
            "target_family": "unknown",
            "target_type": "protein",
            "partition": "",
            "record_id": f"synthetic:{i}",
            "sequence_core_sha256": hashlib.sha256(_seq(i).encode("utf-8")).hexdigest(),
        }
        for i in range(8)
    ]
    from adapters.s7_partition import assign_length_regimes

    regimes = assign_length_regimes(rows, SYNTHETIC_GMM)
    features, space = build_cluster_features(rows, regimes)
    result = optimise_partition(features, space, QuotaTriple(6, 1, 1, sse=0))
    assert assignment_signature(result["assignment"]) == S7B_SYNTHETIC_ASSIGNMENT_FINGERPRINT


def test_preview_reports_target_diagnostics(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    payload = _run_preview(tmp_path, rows)
    diag = s7c_target_diagnostics(rows, payload["result"]["assignment"])
    assert "targets_only_train" in diag
    assert "targets_only_validation" in diag
    assert "targets_shared" in diag
    assert diag["targets_represented"][TRAIN_LABEL] + diag["targets_absent_from_train"] == diag["n_targets"]


def test_tied_quota_optimisation_selects_by_scientific_objective() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(15)]
    features, space = _features(rows)
    candidates = derive_integer_quota_pairs(15)
    assert len(candidates) == 2
    selected = select_s7c_assignment(features, space, candidates)
    assert selected["quotas"].as_tuple in {item.as_tuple for item in candidates}
    all_keys = [item["comparison_tuple"] for item in selected["all_quota_results"]]
    assert selected["comparison_tuple"] == min(all_keys)


def test_live_frozen_expected_hashes_are_wired() -> None:
    expected = frozen_ref_eval_expected({})
    assert expected["n_ref_clusters"] == 80
    assert expected["n_eval_clusters"] == 79
    assert len(expected["ref_sha256"]) == 64
    assert len(expected["eval_sha256"]) == 64


def _absdev_score(**overrides: Any) -> ObjectiveScore:
    payload: dict[str, Any] = {
        "d_target": 0.10,
        "d_evidence": 0.08,
        "d_length": 0.06,
        "d_source": 0.04,
        "j_target": {TRAIN_LABEL: 0.10, VALIDATION_LABEL: 0.09},
        "j_evidence": {TRAIN_LABEL: 0.08, VALIDATION_LABEL: 0.07},
        "j_length": {TRAIN_LABEL: 0.06, VALIDATION_LABEL: 0.05},
        "j_source": {TRAIN_LABEL: 0.04, VALIDATION_LABEL: 0.03},
        "a_target": {TRAIN_LABEL: 0.20, VALIDATION_LABEL: 0.18},
        "a_evidence": {TRAIN_LABEL: 0.12, VALIDATION_LABEL: 0.11},
        "a_length": {TRAIN_LABEL: 0.05, VALIDATION_LABEL: 0.04},
        "a_source": {TRAIN_LABEL: 0.03, VALIDATION_LABEL: 0.02},
        "m_target": 0.20,
        "m_evidence": 0.12,
        "m_length": 0.05,
        "m_source": 0.03,
        "profile": OBJECTIVE_PROFILE_ABSDEV,
    }
    payload.update(overrides)
    return ObjectiveScore(**payload)


def test_max_abs_deviation_uses_complete_support() -> None:
    support = ("A", "B", "C")
    global_p = [0.50, 0.30, 0.20]
    counts = {"A": 5, "B": 5, "C": 0}
    value = max_abs_proportion_deviation(counts, support, global_p)
    assert len(support) == 3
    assert pytest.approx(value) == 0.20


def test_absent_category_contributes_full_ft_proportion() -> None:
    support = ("common", "rare")
    global_p = [0.90, 0.10]
    counts = {"common": 10}
    value = max_abs_proportion_deviation(counts, support, global_p)
    assert pytest.approx(value) == 0.10
    empty = max_abs_proportion_deviation({}, support, global_p)
    assert pytest.approx(empty) == 0.90


def test_r1_is_max_of_four_m() -> None:
    score = _absdev_score(m_target=0.11, m_evidence=0.22, m_length=0.05, m_source=0.07)
    assert score.r1 == 0.22
    assert score.scientific_prefix()[0] == 0.22


def test_sorted_m_lexicographic_tie_break() -> None:
    left = _absdev_score(m_target=0.20, m_evidence=0.15, m_length=0.01, m_source=0.01)
    right = _absdev_score(m_target=0.20, m_evidence=0.10, m_length=0.10, m_source=0.09)
    assignment = {"c1": TRAIN_LABEL, "c2": VALIDATION_LABEL}
    assert left.r1 == right.r1
    assert right.m_lex_vector < left.m_lex_vector
    assert right.comparison_tuple(assignment) < left.comparison_tuple(assignment)


def test_r3_sum_tie_break() -> None:
    higher = _absdev_score(m_target=0.20, m_evidence=0.10, m_length=0.05, m_source=0.04)
    lower = _absdev_score(m_target=0.20, m_evidence=0.10, m_length=0.05, m_source=0.03)
    assignment = {"c1": TRAIN_LABEL}
    assert lower.r1 == higher.r1
    assert lower.m_lex_vector < higher.m_lex_vector or lower.r3 < higher.r3
    assert lower.comparison_tuple(assignment) < higher.comparison_tuple(assignment)


def test_jsd_used_only_after_absolute_deviation_hierarchy() -> None:
    shared_m = dict(m_target=0.20, m_evidence=0.10, m_length=0.05, m_source=0.04)
    worse_jsd = _absdev_score(**shared_m, d_target=0.90, d_evidence=0.01, d_length=0.01, d_source=0.01)
    better_jsd = _absdev_score(**shared_m, d_target=0.10, d_evidence=0.09, d_length=0.08, d_source=0.07)
    assignment = {"c1": TRAIN_LABEL}
    assert worse_jsd.scientific_prefix()[:3] == better_jsd.scientific_prefix()[:3]
    assert better_jsd.comparison_tuple(assignment) < worse_jsd.comparison_tuple(assignment)
    abs_beats_jsd = _absdev_score(
        m_target=0.30,
        m_evidence=0.01,
        m_length=0.01,
        m_source=0.01,
        d_target=0.001,
        d_evidence=0.001,
        d_length=0.001,
        d_source=0.001,
    )
    better_abs = _absdev_score(
        m_target=0.20,
        m_evidence=0.19,
        m_length=0.18,
        m_source=0.17,
        d_target=0.99,
        d_evidence=0.98,
        d_length=0.97,
        d_source=0.96,
    )
    assert better_abs.comparison_tuple(assignment) < abs_beats_jsd.comparison_tuple(assignment)


def test_no_manual_criterion_weights_in_s7c_tuple() -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    features, space = _features(rows)
    score = select_s7c_assignment(features, space, derive_integer_quota_pairs(8))["score"]
    payload = score.as_dict()
    assert payload["arbitrary_manually_chosen_criterion_weights"] is None
    assert list(score.comparison_tuple_fields) == list(S7C_COMPARISON_TUPLE_FIELDS)
    assert "weight" not in "".join(S7C_COMPARISON_TUPLE_FIELDS).lower()
    assert score.profile == OBJECTIVE_PROFILE_ABSDEV
    assert OBJECTIVE_PROFILE_JSD != OBJECTIVE_PROFILE_ABSDEV


def test_length_absdev_uses_distinct_core_grain() -> None:
    rows = [
        _row(index=0, target="T0", cluster_id="c_len", length=30, core=_seq(0)),
        _row(index=1, target="T1", cluster_id="c_len", length=30, core=_seq(0)),
        _row(index=2, target="T2", cluster_id="c_long", length=80),
    ]
    rows.extend(_row(index=10 + i, target=f"U{i}", cluster_id=f"s{i:02d}") for i in range(5))
    features, space = _features(rows)
    assignment = {
        "c_len": VALIDATION_LABEL,
        "c_long": TRAIN_LABEL,
        **{f"s{i:02d}": TRAIN_LABEL for i in range(5)},
    }
    score = score_s7c_assignment(assignment, features, space)
    states = states_from_assignment(
        assignment, features, space, partition_labels=S7C_REPORT_LABELS
    )
    val_cores = states[VALIDATION_LABEL].n_cores
    val_ids = states[VALIDATION_LABEL].n_identities
    assert features["c_len"].n_cores == 1
    assert val_cores == 1
    assert val_ids == 2
    expected = max_abs_proportion_deviation(
        states[VALIDATION_LABEL].length, space.length_regimes, space.length_probs
    )
    assert pytest.approx(score.a_length[VALIDATION_LABEL]) == expected


def test_identity_grain_absdev_for_target_evidence_source() -> None:
    rows = [
        _row(index=0, target="DOM", cluster_id="c_dom", evidence_level="E2", source_db="ena"),
        _row(index=1, target="DOM", cluster_id="c_dom", evidence_level="E3", source_db="ena"),
        _row(index=2, target="OTH", cluster_id="c_oth", evidence_level="E4", source_db="aptabase"),
    ]
    rows.extend(
        _row(
            index=10 + i,
            target=f"U{i}",
            cluster_id=f"s{i:02d}",
            evidence_level="E2",
            source_db="aptabase",
        )
        for i in range(5)
    )
    features, space = _features(rows)
    assignment = {
        "c_dom": VALIDATION_LABEL,
        "c_oth": TRAIN_LABEL,
        **{f"s{i:02d}": TRAIN_LABEL for i in range(5)},
    }
    score = score_s7c_assignment(assignment, features, space)
    states = states_from_assignment(
        assignment, features, space, partition_labels=S7C_REPORT_LABELS
    )
    assert states[VALIDATION_LABEL].n_identities == 2
    assert pytest.approx(score.a_target[VALIDATION_LABEL]) == max_abs_proportion_deviation(
        states[VALIDATION_LABEL].target, space.targets, space.target_probs
    )
    assert pytest.approx(score.a_evidence[VALIDATION_LABEL]) == max_abs_proportion_deviation(
        states[VALIDATION_LABEL].evidence, space.evidence, space.evidence_probs
    )
    assert pytest.approx(score.a_source[VALIDATION_LABEL]) == max_abs_proportion_deviation(
        states[VALIDATION_LABEL].source, space.sources, space.source_probs
    )


def test_preview_writes_absolute_deviation_table(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    payload = _run_preview(tmp_path, rows)
    output_dir = payload["paths"]["output_dir"]
    abs_path = output_dir / "absolute_deviation_metrics.csv"
    assert abs_path.exists()
    text = abs_path.read_text(encoding="utf-8")
    assert "M_worst_subset" in text
    assert "R1" in text
    score = payload["result"]["score"]
    assert score.profile == OBJECTIVE_PROFILE_ABSDEV
    assert not (output_dir / "ft_train.csv").exists()
    assert not (output_dir / "ft_validation.csv").exists()


def _approval_from_s7c_preview(preview_payload: dict[str, Any], preview_dir: Path) -> dict[str, Any]:
    quotas = preview_payload["selected_quotas"]
    score = preview_payload["score"]
    identity_train = preview_payload["tables"]["train_identity_summary.csv"][0]
    identity_val = preview_payload["tables"]["validation_identity_summary.csv"][0]
    core_train = preview_payload["tables"]["train_core_summary.csv"][0]
    core_val = preview_payload["tables"]["validation_core_summary.csv"][0]
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(preview_dir.iterdir())
        if path.is_file()
    }
    return {
        "decision_date": "2026-09-21",
        "frozen_ft_sha256": preview_payload["input_sha256"],
        "v1": {
            "review_status": "not_approved",
            "reason": "raw-JSD cross-criterion minimax caused target-support cardinality to dominate and yielded inadequate source comparability",
        },
        "v2": {
            "review_status": "approved_for_application_and_freeze",
            "frozen_ft_sha256": preview_payload["input_sha256"],
            "approved_cluster_quotas": {
                "TRAIN": quotas.n_TRAIN,
                "VALIDATION": quotas.n_VALIDATION,
            },
            "approved_identities": {
                "TRAIN": int(identity_train["n_identities"]),
                "VALIDATION": int(identity_val["n_identities"]),
            },
            "approved_cores": {
                "TRAIN": int(core_train["n_distinct_cores"]),
                "VALIDATION": int(core_val["n_distinct_cores"]),
            },
            "reviewed_preview": {
                "targets_represented": {
                    "TRAIN": int(identity_train["n_canonical_targets_represented"]),
                    "VALIDATION": int(identity_val["n_canonical_targets_represented"]),
                }
            },
            "approved_objective": {
                "R1": score.r1,
                "R3": score.r3,
                "M_target": score.m_target,
                "M_evidence": score.m_evidence,
                "M_length": score.m_length,
                "M_source": score.m_source,
                "D_target": score.d_target,
                "D_evidence": score.d_evidence,
                "D_length": score.d_length,
                "D_source": score.d_source,
            },
            "reviewed_preview_hashes": hashes,
            "usage": {
                "audit_record_only": True,
                "used_for_scientific_assignment": False,
            },
        },
        "usage": {
            "audit_record_only": True,
            "used_for_scientific_assignment": False,
        },
    }


def _s7c_apply_config_payload(
    paths: dict[str, Path],
    preview_payload: dict[str, Any],
    *,
    approval_path: Path,
    freeze_path: Path,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ref_rows = list(csv.DictReader(paths["ref_path"].open(newline="", encoding="utf-8")))
    eval_rows = list(csv.DictReader(paths["eval_path"].open(newline="", encoding="utf-8")))
    snap = snapshot_ref_eval_freeze(
        ref_rows,
        eval_rows,
        ref_sha256=hashlib.sha256(paths["ref_path"].read_bytes()).hexdigest(),
        eval_sha256=hashlib.sha256(paths["eval_path"].read_bytes()).hexdigest(),
    )
    payload = {
        "contract_id": "global_s7c_ft_train_validation",
        "milestone": "S7C_ft_train_validation_application_and_freeze",
        "mode": "apply",
        "ft_csv": str(paths["ft_path"]),
        "ref_csv": str(paths["ref_path"]),
        "eval_csv": str(paths["eval_path"]),
        "expected_ft_sha256": preview_payload["input_sha256"],
        "expected_ref_sha256": snap.ref_sha256,
        "expected_eval_sha256": snap.eval_sha256,
        "expected_ref_identity_set_hash": snap.ref_identity_set_hash,
        "expected_ref_cluster_set_hash": snap.ref_cluster_set_hash,
        "expected_eval_identity_set_hash": snap.eval_identity_set_hash,
        "expected_eval_cluster_set_hash": snap.eval_cluster_set_hash,
        "expected_ref_clusters": 1,
        "expected_eval_clusters": 1,
        "split_fractions": {"TRAIN": 0.90, "VALIDATION": 0.10},
        "length_regime": {
            "s6_bimodality_json": str(paths["bimodality"]),
            "assignment_method": "gmm_k2_maximum_posterior",
            "refit_on_post_cap": False,
        },
        "write_authoritative_train_validation": True,
        "freeze_ft_train": True,
        "freeze_ft_validation": True,
        "alter_top_level_partition": False,
        "preview_output_dir": str(paths["output_dir"]),
        "output_dir": str(paths["apply_dir"]),
        "approval_record": str(approval_path),
        "freeze_record": str(freeze_path),
        "does_not": [
            "write_corpus_final",
            "alter_ft_csv",
            "alter_ref_csv",
            "alter_eval_csv",
            "alter_top_level_partition",
            "start_fine_tuning",
            "start_s7d",
            "use_validation_for_model_decision",
            "promote_e5",
            "promote_non_protein",
        ],
        "sequence_safety_scan_paths": [],
    }
    if extra:
        payload.update(extra)
    return payload


def test_select_s7c_assignment_does_not_accept_approval_input() -> None:
    import inspect

    assert "approval" not in inspect.signature(select_s7c_assignment).parameters


def test_application_writes_train_validation_and_freezes(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    payload = _run_preview(tmp_path, rows)
    paths = payload["paths"]
    apply_dir = tmp_path / "data" / "interim" / "s7c_ft_split"
    paths["apply_dir"] = apply_dir
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(
        json.dumps(_approval_from_s7c_preview(payload["result"], paths["output_dir"])),
        encoding="utf-8",
    )
    freeze_path = tmp_path / "freeze.json"
    apply_config = tmp_path / "apply.json"
    apply_config.write_text(
        json.dumps(
            _s7c_apply_config_payload(
                paths,
                payload["result"],
                approval_path=approval_path,
                freeze_path=freeze_path,
            )
        ),
        encoding="utf-8",
    )
    result = run_s7c_ft_split_apply(
        config_path=apply_config,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=True,
        write_outputs=True,
        run_random_baseline=False,
        verify_ref_eval_freeze=True,
    )
    train_path = Path(result["output_paths"]["ft_train_csv"])
    val_path = Path(result["output_paths"]["ft_validation_csv"])
    with train_path.open(newline="", encoding="utf-8") as handle:
        train_rows = list(csv.DictReader(handle))
    with val_path.open(newline="", encoding="utf-8") as handle:
        val_rows = list(csv.DictReader(handle))
    assert train_rows
    assert val_rows
    assert all(row["partition"] == "FT" for row in train_rows + val_rows)
    assert all(row["ft_split"] == TRAIN_LABEL for row in train_rows)
    assert all(row["ft_split"] == VALIDATION_LABEL for row in val_rows)
    assert result["parity"]["semantic_mismatches_total"] == 0
    assert result["approval_used_for_scientific_assignment"] is False
    assert result["ft_train_frozen"] is True
    assert result["ft_validation_frozen"] is True
    assert result["assignment"] == payload["result"]["assignment"]
    assert freeze_path.is_file()
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert freeze["TRAIN"]["frozen"] is True
    assert freeze["VALIDATION"]["frozen"] is True
    assert freeze["REF"]["frozen"] is True
    assert freeze["EVAL"]["frozen"] is True
    assert freeze["s7d_started"] is False
    assert freeze["model_fine_tuning_started"] is False
    assert not (apply_dir / "corpus_final.csv").exists()
    assert not (apply_dir / "corpus_final.txt").exists()
    preview_after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths["output_dir"].iterdir())
        if path.is_file()
    }
    assert preview_after == result["preview_hashes"]
    assert hashlib.sha256(paths["ft_path"].read_bytes()).hexdigest() == payload["result"]["input_sha256"]


def test_application_does_not_use_approval_for_assignment(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    payload = _run_preview(tmp_path, rows)
    paths = payload["paths"]
    paths["apply_dir"] = tmp_path / "data" / "interim" / "s7c_ft_split"
    approval = _approval_from_s7c_preview(payload["result"], paths["output_dir"])
    approval["v2"]["approved_cluster_quotas"] = {"TRAIN": 1, "VALIDATION": 7}
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    apply_config = tmp_path / "apply.json"
    apply_config.write_text(
        json.dumps(
            _s7c_apply_config_payload(
                paths,
                payload["result"],
                approval_path=approval_path,
                freeze_path=tmp_path / "freeze.json",
            )
        ),
        encoding="utf-8",
    )
    with pytest.raises(S7CSplitError, match="approval/application semantic mismatches"):
        run_s7c_ft_split_apply(
            config_path=apply_config,
            repo_root=tmp_path,
            verify_hashes=False,
            enforce_expected_counts=False,
            repeat_for_determinism=False,
            write_outputs=True,
            run_random_baseline=False,
            verify_ref_eval_freeze=True,
        )
    assert not (paths["apply_dir"] / "ft_train.csv").exists()
    assert not (paths["apply_dir"] / "ft_validation.csv").exists()


def test_application_refuses_to_overwrite_preview_dir(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    paths = _write_s7c_inputs(tmp_path, rows)
    apply_config = tmp_path / "apply.json"
    apply_config.write_text(
        json.dumps(
            {
                "contract_id": "global_s7c_ft_train_validation",
                "milestone": "S7C_ft_train_validation_application_and_freeze",
                "mode": "apply",
                "ft_csv": str(paths["ft_path"]),
                "ref_csv": str(paths["ref_path"]),
                "eval_csv": str(paths["eval_path"]),
                "expected_ft_sha256": "synthetic",
                "write_authoritative_train_validation": True,
                "freeze_ft_train": True,
                "freeze_ft_validation": True,
                "preview_output_dir": str(paths["output_dir"]),
                "output_dir": str(paths["output_dir"]),
                "does_not": [
                    "write_corpus_final",
                    "alter_ft_csv",
                    "alter_ref_csv",
                    "alter_eval_csv",
                    "alter_top_level_partition",
                    "start_fine_tuning",
                    "start_s7d",
                    "use_validation_for_model_decision",
                    "promote_e5",
                    "promote_non_protein",
                ],
                "length_regime": {
                    "s6_bimodality_json": str(paths["bimodality"]),
                    "assignment_method": "gmm_k2_maximum_posterior",
                    "refit_on_post_cap": False,
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(S7CSplitError, match="must not write to the reviewed preview directory"):
        run_s7c_ft_split_apply(
            config_path=apply_config,
            repo_root=tmp_path,
            verify_hashes=False,
            enforce_expected_counts=False,
            repeat_for_determinism=False,
            write_outputs=False,
            require_preview_parity=False,
            require_approval_parity=False,
            verify_ref_eval_freeze=False,
        )


def test_application_preserves_non_ft_split_fields(tmp_path: Path) -> None:
    rows = [_row(index=i, target=f"T{i}", cluster_id=f"c{i:02d}") for i in range(8)]
    snapshot = [dict(row) for row in rows]
    payload = _run_preview(tmp_path, rows)
    paths = payload["paths"]
    paths["apply_dir"] = tmp_path / "data" / "interim" / "s7c_ft_split"
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(
        json.dumps(_approval_from_s7c_preview(payload["result"], paths["output_dir"])),
        encoding="utf-8",
    )
    apply_config = tmp_path / "apply.json"
    apply_config.write_text(
        json.dumps(
            _s7c_apply_config_payload(
                paths,
                payload["result"],
                approval_path=approval_path,
                freeze_path=tmp_path / "freeze.json",
            )
        ),
        encoding="utf-8",
    )
    result = run_s7c_ft_split_apply(
        config_path=apply_config,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=False,
        write_outputs=True,
        run_random_baseline=False,
        verify_ref_eval_freeze=True,
    )
    train_path = Path(result["output_paths"]["ft_train_csv"])
    val_path = Path(result["output_paths"]["ft_validation_csv"])
    with train_path.open(newline="", encoding="utf-8") as handle:
        written = list(csv.DictReader(handle))
    with val_path.open(newline="", encoding="utf-8") as handle:
        written.extend(list(csv.DictReader(handle)))
    by_id = {row["scientific_identity_id"]: row for row in snapshot}
    for row in written:
        original = by_id[row["scientific_identity_id"]]
        for key, value in original.items():
            assert row[key] == value
        assert row["partition"] == "FT"
        assert row["ft_split"] in {TRAIN_LABEL, VALIDATION_LABEL}
    assert input_unmutated(rows, snapshot)

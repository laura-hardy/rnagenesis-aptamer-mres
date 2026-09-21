"""Synthetic tests for S7A whole-cluster 3% target-cap selection.

Every literal nucleotide string in this file is shorter than 20 nt.
Tests do not read live biological S5 CSVs.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s5_exact_dedup import scientific_identity_id  # noqa: E402
from adapters.s7_target_cap import (  # noqa: E402
    ACTIVE_MAX_TARGET_FRACTION,
    S7TargetCapError,
    exceeds_cap,
    format_share_value,
    identity_share,
    independent_target_distribution,
    input_unmutated,
    select_target_cap,
)
from s7_target_cap import (  # noqa: E402
    run_s7a_target_cap_apply,
    run_s7a_target_cap_preview,
)

FRACTION = ACTIVE_MAX_TARGET_FRACTION
BASES = "ACGU"


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
    evidence_level: str = "E4",
    target_type: str = "protein",
    partition: str = "",
) -> dict[str, str]:
    core = _seq(index)
    identity = scientific_identity_id(core, target)
    return {
        "scientific_identity_id": identity,
        "cluster_id": cluster_id,
        "canonical_target_name": target,
        "sequence_core": core,
        "evidence_level": evidence_level,
        "target_type": target_type,
        "partition": partition,
        "record_id": f"synthetic:{index}",
    }


def _fill_singletons(start_index: int, n: int, *, prefix: str = "U") -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for offset in range(n):
        index = start_index + offset
        rows.append(
            _row(
                index=index,
                target=f"{prefix}{offset:03d}",
                cluster_id=f"c_{prefix.lower()}_{offset:03d}",
            )
        )
    return rows


def test_no_target_above_3_percent_zero_removals() -> None:
    rows = _fill_singletons(0, 50) + _fill_singletons(50, 50, prefix="V")
    snapshot = [dict(row) for row in rows]
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    assert result.steps == []
    assert result.output_n_identities == 100
    assert result.cap_gate_pass
    assert input_unmutated(rows, snapshot)


def test_equality_at_exactly_3_percent_zero_removal() -> None:
    rows = [_row(index=i, target="EQ", cluster_id="c_eq") for i in range(3)]
    rows.extend(_fill_singletons(3, 97))
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    assert identity_share(3, 100) == FRACTION
    assert not exceeds_cap(3, 100, FRACTION)
    assert result.steps == []
    assert result.output_n_identities == 100


def test_largest_target_pure_cluster_selected_first() -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_small") for i in range(2)]
    rows.extend(_row(index=10 + i, target="DOM", cluster_id="c_large") for i in range(5))
    rows.extend(_row(index=20 + i, target="DOM", cluster_id="c_mid") for i in range(3))
    rows.extend(_fill_singletons(30, 90))
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    assert result.steps[0].cluster_id == "c_large"
    assert result.steps[0].cluster_type == "target_pure"
    assert result.steps[0].trigger_target_identities_removed == 5
    assert result.steps[0].collateral_identities_removed == 0


def test_deterministic_cluster_id_tie_break_for_equal_pure_clusters() -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_b") for i in range(4)]
    rows.extend(_row(index=10 + i, target="DOM", cluster_id="c_a") for i in range(4))
    rows.extend(_fill_singletons(20, 92))
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    assert result.steps[0].cluster_id == "c_a"
    again = select_target_cap(list(reversed(rows)), max_target_fraction=FRACTION)
    assert [step.cluster_id for step in again.steps] == [
        step.cluster_id for step in result.steps
    ]


def test_denominator_recomputed_after_every_removal() -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c1") for i in range(3)]
    rows.extend(_row(index=10 + i, target="DOM", cluster_id="c2") for i in range(3))
    rows.extend(_fill_singletons(20, 94))
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    assert len(result.steps) >= 2
    assert result.steps[0].denominator_before == 100
    assert result.steps[0].denominator_after == 97
    assert result.steps[1].denominator_before == 97


def test_recomputation_changes_whether_another_removal_is_required() -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_x") for i in range(3)]
    rows.extend(_row(index=10 + i, target="DOM", cluster_id="c_y") for i in range(3))
    rows.extend(_fill_singletons(20, 94))
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    first = result.steps[0]
    assert identity_share(first.trigger_target_count_after, 100) == FRACTION
    assert identity_share(first.trigger_target_count_after, first.denominator_after) > FRACTION
    assert len(result.steps) == 2


def test_mixed_clusters_not_used_while_target_pure_option_exists() -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_pure") for i in range(4)]
    rows.extend(_row(index=10 + i, target="DOM", cluster_id="c_mixed") for i in range(6))
    rows.extend(_row(index=20 + i, target="OTH", cluster_id="c_mixed") for i in range(2))
    rows.extend(_fill_singletons(30, 88))
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    assert result.steps[0].cluster_id == "c_pure"
    assert result.steps[0].cluster_type == "target_pure"


def test_mixed_fallback_uses_least_collateral_identities() -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_mix_high") for i in range(5)]
    rows.extend(_row(index=10 + i, target="COL_A", cluster_id="c_mix_high") for i in range(2))
    rows.extend(_row(index=20 + i, target="DOM", cluster_id="c_mix_low") for i in range(4))
    rows.append(_row(index=30, target="COL_B", cluster_id="c_mix_low"))
    rows.extend(_fill_singletons(40, 88))
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    mixed_steps = [step for step in result.steps if step.cluster_type == "mixed"]
    assert mixed_steps[0].cluster_id == "c_mix_low"
    assert mixed_steps[0].collateral_identities_removed == 1


def test_deterministic_cluster_id_tie_break_for_equal_mixed_collateral() -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_mix_b") for i in range(4)]
    rows.append(_row(index=10, target="COL1", cluster_id="c_mix_b"))
    rows.extend(_row(index=20 + i, target="DOM", cluster_id="c_mix_a") for i in range(4))
    rows.append(_row(index=30, target="COL2", cluster_id="c_mix_a"))
    rows.extend(_fill_singletons(40, 90))
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    mixed_steps = [step for step in result.steps if step.cluster_type == "mixed"]
    assert mixed_steps[0].cluster_id == "c_mix_a"
    assert mixed_steps[0].collateral_identities_removed == 1


def test_entire_cluster_removed_never_partial_identities() -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_whole") for i in range(5)]
    rows.extend(_fill_singletons(10, 95))
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    removed = set(result.removed_identity_ids)
    cluster_ids = {
        row["scientific_identity_id"] for row in rows if row["cluster_id"] == "c_whole"
    }
    assert cluster_ids <= removed
    retained_clusters = {
        row["cluster_id"]
        for row in rows
        if row["scientific_identity_id"] in set(result.retained_identity_ids)
    }
    assert "c_whole" not in retained_clusters


def test_all_targets_rechecked_after_every_removal() -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c1") for i in range(3)]
    rows.extend(_row(index=10 + i, target="DOM", cluster_id="c2") for i in range(3))
    rows.extend(_fill_singletons(20, 94))
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    remaining = {row["scientific_identity_id"] for row in rows}
    for step in result.steps:
        remaining -= {
            row["scientific_identity_id"]
            for row in rows
            if row["cluster_id"] == step.cluster_id
        }
        live_rows = [row for row in rows if row["scientific_identity_id"] in remaining]
        counts = Counter(row["canonical_target_name"] for row in live_rows)
        n = len(live_rows)
        independent_max = max(identity_share(count, n) for count in counts.values())
        assert step.max_target_share_after == independent_max
        over = [target for target, count in counts.items() if exceeds_cap(count, n, FRACTION)]
        if step.step_number < len(result.steps):
            assert over == [step.trigger_target] or len(over) == 1
        else:
            assert over == []
    assert result.cap_gate_pass
    assert result.max_target_share <= FRACTION


def test_final_hard_gate_max_target_share() -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_big") for i in range(8)]
    rows.extend(_fill_singletons(20, 92))
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    assert result.max_target_share <= FRACTION
    assert result.cap_gate_pass
    retained = [
        row
        for row in rows
        if row["scientific_identity_id"] in set(result.retained_identity_ids)
    ]
    independent = independent_target_distribution(retained)
    assert all(row["exceeds_cap"] == "false" for row in independent)


def test_all_identities_accounted_retained_or_removed() -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_a") for i in range(6)]
    rows.extend(_fill_singletons(10, 94))
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    all_ids = {row["scientific_identity_id"] for row in rows}
    assert set(result.retained_identity_ids) | set(result.removed_identity_ids) == all_ids
    assert not (set(result.retained_identity_ids) & set(result.removed_identity_ids))


def test_no_change_to_input_records() -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_a") for i in range(6)]
    rows.extend(_fill_singletons(10, 94))
    snapshot = [dict(row) for row in rows]
    select_target_cap(rows, max_target_fraction=FRACTION)
    assert input_unmutated(rows, snapshot)


def test_partition_fields_are_not_populated() -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_a") for i in range(6)]
    rows.extend(_fill_singletons(10, 94))
    result = select_target_cap(rows, max_target_fraction=FRACTION)
    by_id = {row["scientific_identity_id"]: row for row in rows}
    for identity in list(result.retained_identity_ids) + list(result.removed_identity_ids):
        assert by_id[identity]["partition"] == ""


def test_ambiguous_simultaneous_overrepresented_targets_fail_closed() -> None:
    rows = [_row(index=i, target="ALPHA", cluster_id="c_alpha") for i in range(5)]
    rows.extend(_row(index=10 + i, target="BETA", cluster_id="c_beta") for i in range(5))
    rows.extend(_fill_singletons(20, 90))
    with pytest.raises(S7TargetCapError, match="fail closed"):
        select_target_cap(rows, max_target_fraction=FRACTION)


def test_preview_runner_writes_sequence_free_artefacts(tmp_path: Path) -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_a") for i in range(6)]
    rows.extend(_fill_singletons(10, 94))
    corpus_path = tmp_path / "corpus_clustered_final.csv"
    with corpus_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    yaml_path = tmp_path / "curation_config.yaml"
    yaml_path.write_text(
        "MAX_TARGET_FRACTION: 0.03\nTRAINING_SEQUENCE_COLUMN: sequence_core\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "preview"
    config_path = tmp_path / "global_s7a_target_cap.json"
    config_path.write_text(
        json.dumps(
            {
                "contract_id": "global_s7a_target_cap",
                "milestone": "S7A_target_cap_preview_dry_run",
                "mode": "preview",
                "s5e_config": "config/global_s5e_final_clustering.json",
                "s6_config": "config/global_s6_profile.json",
                "curation_config": str(yaml_path),
                "authoritative_corpus": str(corpus_path),
                "expected_input_sha256": "synthetic",
                "max_target_fraction": 0.03,
                "training_sequence_column": "sequence_core",
                "cap_unit": "final_cluster",
                "denominator_semantics": "current_post_removal_identity_count",
                "cluster_integrity": "never_split_cluster",
                "target_pure_first": True,
                "recompute_after_every_removal": True,
                "simultaneous_overrepresented_target_ordering": "fail_closed_unspecified",
                "no_e5_promotion": True,
                "no_non_protein_promotion": True,
                "no_partitioning": True,
                "write_authoritative_capped_corpus": False,
                "output_dir": str(output_dir),
                "sequence_safety_scan_paths": [],
            }
        ),
        encoding="utf-8",
    )
    payload = run_s7a_target_cap_preview(
        config_path=config_path,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=True,
        write_outputs=True,
    )
    report = Path(payload["output_paths"]["preview_report_md"]).read_text(encoding="utf-8")
    trace = Path(payload["output_paths"]["removal_trace_csv"]).read_text(encoding="utf-8")
    assert rows[0]["sequence_core"] not in report
    assert rows[0]["sequence_core"] not in trace
    assert payload["cap_gate"] == "PASS"
    assert not (tmp_path / "corpus_final.csv").exists()


def _write_synthetic_s7a_inputs(tmp_path: Path, rows: list[dict[str, str]]) -> dict[str, Path]:
    corpus_path = tmp_path / "data" / "interim" / "deduplicated" / "corpus_clustered_final.csv"
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    with corpus_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    yaml_path = tmp_path / "curation_config.yaml"
    yaml_path.write_text(
        "MAX_TARGET_FRACTION: 0.03\nTRAINING_SEQUENCE_COLUMN: sequence_core\n",
        encoding="utf-8",
    )
    preview_dir = tmp_path / "data" / "interim" / "s7a_target_cap_preview"
    apply_dir = tmp_path / "data" / "interim" / "s7a_target_cap"
    return {
        "corpus_path": corpus_path,
        "yaml_path": yaml_path,
        "preview_dir": preview_dir,
        "apply_dir": apply_dir,
    }


def _shared_s7a_policy() -> dict[str, object]:
    return {
        "s5e_config": "config/global_s5e_final_clustering.json",
        "s6_config": "config/global_s6_profile.json",
        "max_target_fraction": 0.03,
        "training_sequence_column": "sequence_core",
        "cap_unit": "final_cluster",
        "denominator_semantics": "current_post_removal_identity_count",
        "cluster_integrity": "never_split_cluster",
        "target_pure_first": True,
        "recompute_after_every_removal": True,
        "simultaneous_overrepresented_target_ordering": "fail_closed_unspecified",
        "no_e5_promotion": True,
        "no_non_protein_promotion": True,
        "no_partitioning": True,
        "sequence_safety_scan_paths": [],
    }


def test_select_target_cap_does_not_accept_approval_input() -> None:
    import inspect

    assert "approval" not in inspect.signature(select_target_cap).parameters


def test_application_runner_writes_post_cap_corpus(tmp_path: Path) -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_a") for i in range(6)]
    rows.extend(_fill_singletons(10, 94))
    paths = _write_synthetic_s7a_inputs(tmp_path, rows)
    preview_config = tmp_path / "preview.json"
    preview_config.write_text(
        json.dumps(
            {
                "contract_id": "global_s7a_target_cap",
                "milestone": "S7A_target_cap_preview_dry_run",
                "mode": "preview",
                "curation_config": str(paths["yaml_path"]),
                "authoritative_corpus": str(paths["corpus_path"]),
                "expected_input_sha256": "synthetic",
                "write_authoritative_capped_corpus": False,
                "output_dir": str(paths["preview_dir"]),
                **_shared_s7a_policy(),
            }
        ),
        encoding="utf-8",
    )
    preview_payload = run_s7a_target_cap_preview(
        config_path=preview_config,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=True,
        write_outputs=True,
    )
    preview_result = preview_payload["result"]
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(
        json.dumps(
            {
                "decision_date": "2026-09-21",
                "review_status": "approved_for_application",
                "max_target_fraction": 0.03,
                "frozen_input_sha256": preview_payload["input_sha256"],
                "reviewed_preview": {
                    "input_identities": preview_result.input_n_identities,
                    "proposed_removed_clusters": len(preview_result.removed_cluster_ids),
                    "proposed_removed_identities": len(preview_result.removed_identity_ids),
                    "expected_post_cap_identities": preview_result.output_n_identities,
                    "expected_post_cap_clusters": preview_result.output_n_clusters,
                    "expected_max_target_share": format_share_value(
                        preview_result.max_target_share
                    ),
                    "selected_cluster_ids": list(preview_result.removed_cluster_ids),
                },
                "usage": {
                    "audit_record_only": True,
                    "used_for_cluster_selection": False,
                },
            }
        ),
        encoding="utf-8",
    )
    apply_config = tmp_path / "apply.json"
    apply_config.write_text(
        json.dumps(
            {
                "contract_id": "global_s7a_target_cap",
                "milestone": "S7A_target_cap_application",
                "mode": "apply",
                "curation_config": str(paths["yaml_path"]),
                "authoritative_corpus": str(paths["corpus_path"]),
                "expected_input_sha256": "synthetic",
                "write_authoritative_capped_corpus": True,
                "preview_output_dir": str(paths["preview_dir"]),
                "output_dir": str(paths["apply_dir"]),
                "approval_record": str(approval_path),
                **_shared_s7a_policy(),
            }
        ),
        encoding="utf-8",
    )
    payload = run_s7a_target_cap_apply(
        config_path=apply_config,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=True,
        write_outputs=True,
    )
    corpus_path = Path(payload["output_paths"]["corpus_post_cap_csv"])
    with corpus_path.open(newline="", encoding="utf-8") as handle:
        written = list(csv.DictReader(handle))
    assert len(written) == preview_result.output_n_identities
    assert {row["scientific_identity_id"] for row in written} == set(
        preview_result.retained_identity_ids
    )
    assert all(row["partition"] == "" for row in written)
    assert payload["parity_mismatches"] == []
    assert payload["approval_used_for_cluster_selection"] is False
    assert not (tmp_path / "corpus_final.csv").exists()
    assert not (paths["apply_dir"] / "corpus_final.csv").exists()
    assert payload["cap_gate"] == "PASS"


def test_application_does_not_use_approval_for_selection(tmp_path: Path) -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_a") for i in range(6)]
    rows.extend(_fill_singletons(10, 94))
    paths = _write_synthetic_s7a_inputs(tmp_path, rows)
    preview_config = tmp_path / "preview.json"
    preview_config.write_text(
        json.dumps(
            {
                "contract_id": "global_s7a_target_cap",
                "milestone": "S7A_target_cap_preview_dry_run",
                "mode": "preview",
                "curation_config": str(paths["yaml_path"]),
                "authoritative_corpus": str(paths["corpus_path"]),
                "expected_input_sha256": "synthetic",
                "write_authoritative_capped_corpus": False,
                "output_dir": str(paths["preview_dir"]),
                **_shared_s7a_policy(),
            }
        ),
        encoding="utf-8",
    )
    preview_payload = run_s7a_target_cap_preview(
        config_path=preview_config,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=False,
        write_outputs=True,
    )
    derived = select_target_cap(rows, max_target_fraction=FRACTION)
    assert list(derived.removed_cluster_ids) == list(
        preview_payload["result"].removed_cluster_ids
    )
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(
        json.dumps(
            {
                "review_status": "approved_for_application",
                "frozen_input_sha256": preview_payload["input_sha256"],
                "reviewed_preview": {
                    "input_identities": derived.input_n_identities,
                    "proposed_removed_clusters": 1,
                    "proposed_removed_identities": len(derived.removed_identity_ids),
                    "expected_post_cap_identities": derived.output_n_identities,
                    "expected_post_cap_clusters": derived.output_n_clusters,
                    "expected_max_target_share": format_share_value(derived.max_target_share),
                    "selected_cluster_ids": ["not_the_scientifically_selected_cluster"],
                },
                "usage": {
                    "audit_record_only": True,
                    "used_for_cluster_selection": False,
                },
            }
        ),
        encoding="utf-8",
    )
    apply_config = tmp_path / "apply.json"
    apply_config.write_text(
        json.dumps(
            {
                "contract_id": "global_s7a_target_cap",
                "milestone": "S7A_target_cap_application",
                "mode": "apply",
                "curation_config": str(paths["yaml_path"]),
                "authoritative_corpus": str(paths["corpus_path"]),
                "expected_input_sha256": "synthetic",
                "write_authoritative_capped_corpus": True,
                "preview_output_dir": str(paths["preview_dir"]),
                "output_dir": str(paths["apply_dir"]),
                "approval_record": str(approval_path),
                **_shared_s7a_policy(),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(S7TargetCapError, match="approval/application semantic mismatches"):
        run_s7a_target_cap_apply(
            config_path=apply_config,
            repo_root=tmp_path,
            verify_hashes=False,
            enforce_expected_counts=False,
            repeat_for_determinism=False,
            write_outputs=True,
        )
    assert not (paths["apply_dir"] / "corpus_post_cap.csv").exists()
    assert list(derived.removed_cluster_ids) != ["not_the_scientifically_selected_cluster"]


def test_application_refuses_to_overwrite_preview_dir(tmp_path: Path) -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_a") for i in range(6)]
    rows.extend(_fill_singletons(10, 94))
    paths = _write_synthetic_s7a_inputs(tmp_path, rows)
    apply_config = tmp_path / "apply.json"
    apply_config.write_text(
        json.dumps(
            {
                "contract_id": "global_s7a_target_cap",
                "milestone": "S7A_target_cap_application",
                "mode": "apply",
                "curation_config": str(paths["yaml_path"]),
                "authoritative_corpus": str(paths["corpus_path"]),
                "expected_input_sha256": "synthetic",
                "write_authoritative_capped_corpus": True,
                "preview_output_dir": str(paths["preview_dir"]),
                "output_dir": str(paths["preview_dir"]),
                **_shared_s7a_policy(),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(S7TargetCapError, match="must not write to the reviewed preview directory"):
        run_s7a_target_cap_apply(
            config_path=apply_config,
            repo_root=tmp_path,
            verify_hashes=False,
            enforce_expected_counts=False,
            repeat_for_determinism=False,
            write_outputs=False,
            require_preview_parity=False,
            require_approval_parity=False,
        )


def test_application_preserves_original_fields_and_blank_partition(tmp_path: Path) -> None:
    rows = [_row(index=i, target="DOM", cluster_id="c_a") for i in range(6)]
    rows.extend(_fill_singletons(10, 94))
    snapshot = [dict(row) for row in rows]
    paths = _write_synthetic_s7a_inputs(tmp_path, rows)
    preview_config = tmp_path / "preview.json"
    preview_config.write_text(
        json.dumps(
            {
                "contract_id": "global_s7a_target_cap",
                "milestone": "S7A_target_cap_preview_dry_run",
                "mode": "preview",
                "curation_config": str(paths["yaml_path"]),
                "authoritative_corpus": str(paths["corpus_path"]),
                "expected_input_sha256": "synthetic",
                "write_authoritative_capped_corpus": False,
                "output_dir": str(paths["preview_dir"]),
                **_shared_s7a_policy(),
            }
        ),
        encoding="utf-8",
    )
    run_s7a_target_cap_preview(
        config_path=preview_config,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=False,
        write_outputs=True,
    )
    apply_config = tmp_path / "apply.json"
    apply_config.write_text(
        json.dumps(
            {
                "contract_id": "global_s7a_target_cap",
                "milestone": "S7A_target_cap_application",
                "mode": "apply",
                "curation_config": str(paths["yaml_path"]),
                "authoritative_corpus": str(paths["corpus_path"]),
                "expected_input_sha256": "synthetic",
                "write_authoritative_capped_corpus": True,
                "preview_output_dir": str(paths["preview_dir"]),
                "output_dir": str(paths["apply_dir"]),
                **_shared_s7a_policy(),
            }
        ),
        encoding="utf-8",
    )
    payload = run_s7a_target_cap_apply(
        config_path=apply_config,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        repeat_for_determinism=False,
        write_outputs=True,
        require_approval_parity=False,
    )
    written_path = Path(payload["output_paths"]["corpus_post_cap_csv"])
    with written_path.open(newline="", encoding="utf-8") as handle:
        written = list(csv.DictReader(handle))
    by_id = {row["scientific_identity_id"]: row for row in snapshot}
    for row in written:
        original = by_id[row["scientific_identity_id"]]
        for key, value in original.items():
            assert row[key] == value
        assert row["partition"] == ""
    assert input_unmutated(rows, snapshot)

"""Synthetic tests for S6 pre-balancing corpus profile.

Every literal nucleotide string in this file is shorter than 20 nt.
Tests do not read live biological S5 CSVs.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s5_exact_dedup import scientific_identity_id  # noqa: E402
from adapters.s5_sequence_clustering import sequence_core_digest  # noqa: E402
from adapters.s6_profile import (  # noqa: E402
    CANDIDATE_FRACTIONS,
    GMM_POSTERIOR_ASSIGNMENT_METHOD,
    HUMAN_CHECKPOINT_FIELDS,
    S6ProfileError,
    assemble_profile,
    classify_bimodality,
    compare_assemblies,
    enforce_authorised_config,
    fit_univariate_gmm,
    gini_coefficient,
    gmm_posterior_assignment,
    max_allowed_identities,
    sequence_composition,
    shannon_entropy,
)
from adapters.s6_profile_render import (  # noqa: E402
    E5_PARKED_NOTE,
    FIGURE_FILENAMES,
    PREFERRED_SOURCE_FACET_ORDER,
    build_checkpoint3_summary,
    build_corpus_profile_report,
    build_figure_captions,
    build_figure_pack_supervisor,
    donor_facet_sources,
    fig01_spec,
    fig03_spec,
    fig04_spec,
    fig06_spec,
    fig07_spec,
    fig09_spec,
    plot_data_tables,
    write_checkpoint3_package,
    write_figures,
    write_profile_tables,
)
from s6_profile_report import run_s6_profile  # noqa: E402

SEQ_A = "ACGUACGUAA"
SEQ_B = "UGCAUGCAUU"
SEQ_C = "GGAAUCCGAU"
SEQ_D = "CCUUAGGAUC"
SEQ_E = "AUAUCGGAUC"
SEQ_LONG = "ACGUACGUACGUACGUA"  # 17 nt
assert all(len(seq) < 20 for seq in (SEQ_A, SEQ_B, SEQ_C, SEQ_D, SEQ_E, SEQ_LONG))


def _identity(sequence_core: str, target: str) -> str:
    return scientific_identity_id(sequence_core, target)


def _cluster_id(cores: list[str]) -> str:
    payload = "\x1f".join(sorted(sequence_core_digest(core) for core in cores))
    return "S5C_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _row(
    *,
    sequence_core: str,
    target: str,
    cluster_cores: list[str] | None = None,
    source_db: str = "aptamerbase",
    representative: bool = False,
    **fields: str,
) -> dict[str, str]:
    cores = cluster_cores or [sequence_core]
    cluster_id = fields.get("cluster_id") or _cluster_id(cores)
    identity = _identity(sequence_core, target)
    row = {
        "scientific_identity_id": identity,
        "record_id": fields.get("record_id", f"{source_db}:{identity[-8:]}"),
        "sequence_core": sequence_core,
        "sequence_full": fields.get("sequence_full", sequence_core),
        "sequence_length_core": str(len(sequence_core)),
        "sequence_length_full": str(len(fields.get("sequence_full", sequence_core))),
        "canonical_target_name": target,
        "target_family": fields.get("target_family", "enzyme"),
        "target_uniprot": fields.get("target_uniprot", ""),
        "target_pfam": fields.get("target_pfam", ""),
        "target_interpro": fields.get("target_interpro", ""),
        "source_db": source_db,
        "contributing_sources": fields.get("contributing_sources", source_db),
        "corroboration_count": fields.get(
            "corroboration_count",
            str(len([item for item in fields.get("contributing_sources", source_db).split("|") if item])),
        ),
        "cluster_id": cluster_id,
        "is_cluster_representative": "true" if representative else "false",
        "partition": "",
        "evidence_level": fields.get("evidence_level", "E4"),
        "chemistry": fields.get("chemistry", "RNA"),
        "molecule_type": fields.get("molecule_type", "RNA"),
        "construct_scope": fields.get("construct_scope", "unknown"),
        "trim_confidence": fields.get("trim_confidence", "n/a"),
        "trim_status": fields.get("trim_status", "no_constants_detected"),
        "t_to_u_applied": fields.get("t_to_u_applied", "false"),
        "alphabet_as_reported": fields.get("alphabet_as_reported", "RNA"),
        "redistribution_status": fields.get("redistribution_status", "unknown"),
        "independently_attested_by_permissive_source": fields.get(
            "independently_attested_by_permissive_source", "false"
        ),
        "conflict_flags": fields.get("conflict_flags", ""),
        "canonical_affinity_value": fields.get("canonical_affinity_value", ""),
        "canonical_affinity_type": fields.get("canonical_affinity_type", ""),
        "affinity_value_molar": fields.get("affinity_value_molar", ""),
        "sequence_core_sha256": sequence_core_digest(sequence_core),
        "member_count": fields.get("member_count", "1"),
    }
    row.update({key: value for key, value in fields.items() if key not in row})
    return row


def _summary(cluster_id: str, members: list[dict[str, str]], *, merge_basis: str = "mmseqs_only") -> dict[str, str]:
    cores = {row["sequence_core"] for row in members}
    targets = {row["canonical_target_name"] for row in members}
    ena = any("ena" in row["contributing_sources"].split("|") for row in members)
    return {
        "cluster_id": cluster_id,
        "n_distinct_sequences": str(len(cores)),
        "n_scientific_identities": str(len(members)),
        "n_targets": str(len(targets)),
        "merge_basis": merge_basis,
        "ena_provenance_present": "true" if ena else "false",
    }


def _membership(row: dict[str, str], *, source_db: str | None = None) -> dict[str, str]:
    return {
        "scientific_identity_id": row["scientific_identity_id"],
        "source_db": source_db or row["source_db"],
        "sequence_core": row["sequence_core"],
        "canonical_target_name": row["canonical_target_name"],
    }


def _corpus_bundle() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """Five identities, four cores, three clusters, one shared-core pair."""
    c_ab = _cluster_id([SEQ_A, SEQ_B])
    c_c = _cluster_id([SEQ_C])
    c_d = _cluster_id([SEQ_D])
    rows = [
        _row(
            sequence_core=SEQ_A,
            target="NGF",
            cluster_cores=[SEQ_A, SEQ_B],
            cluster_id=c_ab,
            source_db="ena",
            contributing_sources="ena|aptamerbase",
            corroboration_count="2",
            representative=True,
            evidence_level="E2",
            target_uniprot="P01138",
            canonical_affinity_value="1e-9",
            canonical_affinity_type="Kd",
            affinity_value_molar="1e-9",
        ),
        _row(
            sequence_core=SEQ_A,
            target="TrkA",
            cluster_cores=[SEQ_A, SEQ_B],
            cluster_id=c_ab,
            source_db="aptamerbase",
            contributing_sources="aptamerbase",
            corroboration_count="1",
            representative=False,
            evidence_level="E3",
            target_family="receptor",
        ),
        _row(
            sequence_core=SEQ_B,
            target="NGF",
            cluster_cores=[SEQ_A, SEQ_B],
            cluster_id=c_ab,
            source_db="ena",
            contributing_sources="ena",
            corroboration_count="1",
            representative=False,
            evidence_level="E2",
            target_uniprot="P01138",
        ),
        _row(
            sequence_core=SEQ_C,
            target="NDM-1",
            cluster_cores=[SEQ_C],
            cluster_id=c_c,
            source_db="riboaptamer",
            representative=True,
            evidence_level="E4",
            target_family="enzyme",
            redistribution_status="restricted",
        ),
        _row(
            sequence_core=SEQ_D,
            target="VEGF",
            cluster_cores=[SEQ_D],
            cluster_id=c_d,
            source_db="utexas",
            representative=True,
            evidence_level="E4",
            target_family="growth_factor",
        ),
    ]
    by_cluster: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_cluster.setdefault(row["cluster_id"], []).append(row)
    summary = [
        _summary(cid, members, merge_basis="mmseqs_plus_ena_family_must_link" if cid == c_ab else "mmseqs_only")
        for cid, members in by_cluster.items()
    ]
    membership = [_membership(row) for row in rows]
    membership.append(_membership(rows[0], source_db="aptamerbase"))
    overlap = [
        {
            "source_a": "aptamerbase",
            "source_b": "ena",
            "n_shared_scientific_identities": "1",
            "n_shared_duplicate_groups": "1",
        }
    ]
    return rows, summary, membership, overlap


def test_gini_equals_zero_for_uniform_counts() -> None:
    assert gini_coefficient([4, 4, 4, 4]) == pytest.approx(0.0)


def test_gini_increases_with_concentration() -> None:
    assert gini_coefficient([10, 1, 1, 1]) > gini_coefficient([4, 4, 3, 2])


def test_shannon_uniform_is_ln_k() -> None:
    result = shannon_entropy([1, 1, 1, 1])
    assert result["shannon_nats"] == pytest.approx(math.log(4))
    assert result["n_effective"] == pytest.approx(4.0)
    assert result["shannon_normalised"] == pytest.approx(1.0)


def test_max_allowed_identities_is_floor() -> None:
    assert max_allowed_identities(1281, 0.05) == 64
    assert max_allowed_identities(1281, 0.02) == 25
    assert max_allowed_identities(5, 0.40) == 2


def test_gmm_prefers_two_components_on_separated_mixture() -> None:
    values = [20.0] * 30 + [80.0] * 30
    gmm1 = fit_univariate_gmm(values, n_components=1)
    gmm2 = fit_univariate_gmm(values, n_components=2)
    verdict = classify_bimodality(gmm1, gmm2)
    assert gmm2["bic"] < gmm1["bic"]
    assert verdict["conclusion"] == "evidence_of_material_bimodality"
    assert min(gmm2["means"]) == pytest.approx(20.0, abs=1.0)
    assert max(gmm2["means"]) == pytest.approx(80.0, abs=1.0)


def test_gmm_unimodal_has_no_material_bimodality() -> None:
    values = [float(40 + i % 3) for i in range(40)]
    verdict = classify_bimodality(
        fit_univariate_gmm(values, n_components=1),
        fit_univariate_gmm(values, n_components=2),
    )
    assert verdict["conclusion"] in {"no_material_evidence", "weak_evidence"}


def test_composition_counts_distinct_letters() -> None:
    stats = sequence_composition(["ACGU", "ACGU"])
    assert stats["frac_A"] == pytest.approx(0.25)
    assert stats["frac_G"] + stats["frac_C"] == pytest.approx(0.5)


def test_assemble_uses_identity_grain_not_membership_rows() -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    result = assemble_profile(
        rows,
        cluster_summary_rows=summary,
        membership_rows=membership,
        overlap_matrix_rows=overlap,
        clusters_final_rows=[{"sequence_core": row["sequence_core"]} for row in rows[:4]],
    )
    assert result.headline["n_scientific_identities"] == 5
    assert result.headline["n_distinct_sequence_core"] == 4
    assert result.headline["n_final_clusters"] == 3
    assert result.headline["n_scientific_identities"] != len(membership)
    report = build_corpus_profile_report(result)
    assert "one S5 scientific identity" in report
    assert "1,460 pre-dedup" in report or "not 1460" in report


def test_polyspecificity_counts_shared_cores() -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    result = assemble_profile(
        rows,
        cluster_summary_rows=summary,
        membership_rows=membership,
        overlap_matrix_rows=overlap,
    )
    assert result.polyspecificity["n_shared_sequence_cores"] == 1
    assert result.polyspecificity["n_shared_core_identities"] == 2
    assert result.polyspecificity["n_clusters_multi_target"] == 1


def test_cap_analysis_does_not_mutate_or_select() -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    before = [dict(row) for row in rows]
    result = assemble_profile(
        rows,
        cluster_summary_rows=summary,
        membership_rows=membership,
        overlap_matrix_rows=overlap,
        candidate_fractions=(0.20, 0.40),
    )
    assert rows == before
    assert all(row["partition"] == "" for row in rows)
    assert result.headline["s7_cluster_selection_specified"] is False
    assert {row["max_target_fraction"] for row in result.cap_rows} == {"0.20", "0.40"}
    over_40 = next(row for row in result.cap_rows if row["max_target_fraction"] == "0.40")
    # 0.40 * 5 = 2, so counts >2 are overrepresented. NGF has 2, not above.
    assert over_40["n_targets_above_threshold"] == "0"
    over_20 = next(row for row in result.cap_rows if row["max_target_fraction"] == "0.20")
    assert int(over_20["n_targets_above_threshold"]) >= 1
    assert "not executable" in over_20["note"].lower() or "not executable" in over_20["note"]


def test_checkpoint3_includes_c3_05_and_blank_human_fields() -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    result = assemble_profile(
        rows,
        cluster_summary_rows=summary,
        membership_rows=membership,
        overlap_matrix_rows=overlap,
    )
    ids = [row["decision_id"] for row in result.checkpoint3_decisions]
    assert ids == ["C3-01", "C3-02", "C3-03", "C3-04", "C3-05"]
    for row in result.checkpoint3_decisions:
        for field in HUMAN_CHECKPOINT_FIELDS:
            assert row[field] == ""
    report = build_corpus_profile_report(result)
    assert "Decisions requested at CHECKPOINT-3" in report
    assert "does not recommend a final approved option" in report
    summary_text = build_checkpoint3_summary(result)
    assert "Human decision: _(blank)_" in summary_text


def test_emergency_trigger_follows_cluster_count() -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    result = assemble_profile(
        rows,
        cluster_summary_rows=summary,
        membership_rows=membership,
        overlap_matrix_rows=overlap,
    )
    assert result.headline["emergency_trigger_met"] is (
        result.headline["n_final_clusters"] < result.headline["emergency_cluster_trigger"]
    )
    assert (796 < 500) is False


def test_partition_and_representative_assertions() -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    result = assemble_profile(
        rows,
        cluster_summary_rows=summary,
        membership_rows=membership,
        overlap_matrix_rows=overlap,
    )
    assert result.assertions["n_partition_populated"] == 0
    assert result.assertions["n_clusters_without_representative"] == 0
    assert result.assertions["n_clusters_with_gt1_representative"] == 0


def test_missing_cluster_id_fails() -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    rows[0]["cluster_id"] = ""
    with pytest.raises(S6ProfileError, match="missing final cluster_id"):
        assemble_profile(
            rows,
            cluster_summary_rows=summary,
            membership_rows=membership,
            overlap_matrix_rows=overlap,
        )


def test_report_is_sequence_free() -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    result = assemble_profile(
        rows,
        cluster_summary_rows=summary,
        membership_rows=membership,
        overlap_matrix_rows=overlap,
    )
    report = build_corpus_profile_report(result)
    assert SEQ_A not in report
    assert SEQ_B not in report
    assert "ACGUACGUAA" not in report


def test_length_outliers_are_retained() -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    long_core = "A" * 12 + "C" * 5  # 17 nt, below 20-leak and below 100; use length field
    rows[4]["sequence_length_core"] = "123"
    rows[4]["sequence_core"] = long_core
    result = assemble_profile(
        rows,
        cluster_summary_rows=summary,
        membership_rows=membership,
        overlap_matrix_rows=overlap,
    )
    assert result.length_outliers["n_identities_gt_100nt"] == 1
    assert result.headline["n_scientific_identities"] == 5


def test_donor_versus_contributing_source() -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    result = assemble_profile(
        rows,
        cluster_summary_rows=summary,
        membership_rows=membership,
        overlap_matrix_rows=overlap,
    )
    ena = next(row for row in result.source_rows if row["source_db"] == "ena")
    apt = next(row for row in result.source_rows if row["source_db"] == "aptamerbase")
    assert int(ena["n_identities_donor"]) == 2
    assert int(apt["n_identities_contributing"]) >= int(apt["n_identities_donor"])
    assert result.source_stats["definitions"]["donor_source"]
    assert result.source_stats["n_identities_corroborated_gt1"] == 1


def test_enzyme_share_and_uniprot() -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    result = assemble_profile(
        rows,
        cluster_summary_rows=summary,
        membership_rows=membership,
        overlap_matrix_rows=overlap,
    )
    assert result.headline["n_enzyme_identities"] == 3  # NGF x2 + NDM-1
    assert result.uniprot["n_targets_with_uniprot"] == 1
    assert result.uniprot["n_identities_with_uniprot"] == 2


def test_determinism_independent_of_input_order() -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    first = assemble_profile(
        rows,
        cluster_summary_rows=summary,
        membership_rows=membership,
        overlap_matrix_rows=overlap,
    )
    second = assemble_profile(
        list(reversed(rows)),
        cluster_summary_rows=list(reversed(summary)),
        membership_rows=list(reversed(membership)),
        overlap_matrix_rows=list(reversed(overlap)),
    )
    compare_assemblies(first, second)
    assert build_corpus_profile_report(first) == build_corpus_profile_report(second)


def test_config_rejects_balancing_keys() -> None:
    with pytest.raises(S6ProfileError):
        enforce_authorised_config({"balancing": True, "does_not": []})
    with pytest.raises(S6ProfileError):
        enforce_authorised_config({"does_not": ["balancing"]})
    enforce_authorised_config(
        {
            "does_not": [
                "balancing",
                "apply_target_cap",
                "select_final_max_target_fraction",
                "populate_partition",
                "assign_ft_ref_eval",
                "start_s7",
            ]
        }
    )


def test_write_outputs_are_sequence_free_and_human_blank(tmp_path: Path) -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    result = assemble_profile(
        rows,
        cluster_summary_rows=summary,
        membership_rows=membership,
        overlap_matrix_rows=overlap,
    )
    profile_dir = tmp_path / "s6_profile"
    checkpoint_dir = tmp_path / "checkpoint3"
    write_profile_tables(result, profile_dir)
    write_checkpoint3_package(result, checkpoint_dir)
    decisions = (checkpoint_dir / "checkpoint3_decisions.csv").read_text(encoding="utf-8")
    assert SEQ_A not in decisions
    assert ",," in decisions or "awaiting_supervisor_review" in decisions
    payload = json.loads((profile_dir / "headline.json").read_text(encoding="utf-8"))
    assert payload["n_scientific_identities"] == 5
    tables = plot_data_tables(result)
    assert "fig01_top30_targets.csv" in tables
    assert tables["fig09_candidate_target_cap.csv"]


def test_candidate_fractions_match_plan() -> None:
    assert CANDIDATE_FRACTIONS == (0.02, 0.03, 0.05, 0.10)


def test_run_s6_profile_synthetic_tmp(tmp_path: Path) -> None:
    rows, summary, membership, overlap = _corpus_bundle()
    data_dir = tmp_path / "data" / "interim" / "deduplicated"
    data_dir.mkdir(parents=True)
    s4_dir = tmp_path / "data" / "interim" / "global_s4"
    s4_dir.mkdir(parents=True)

    def _write(path: Path, rows_in: list[dict[str, str]]) -> None:
        from common.corpus_schema import write_corpus_csv_atomic

        write_corpus_csv_atomic(path, rows_in, columns=list(rows_in[0].keys()))

    corpus = data_dir / "corpus_clustered_final.csv"
    _write(corpus, rows)
    _write(data_dir / "cluster_summary_final.csv", summary)
    _write(data_dir / "cluster_union_provenance.csv", summary)
    _write(data_dir / "exact_duplicate_membership.csv", membership)
    _write(data_dir / "exact_overlap_matrix.csv", overlap)
    _write(
        data_dir / "clusters_final.tsv",
        [
            {"sequence_core": core}
            for core in dict.fromkeys(row["sequence_core"] for row in rows)
        ],
    )
    # Dummy freeze files for hash skip
    config = {
        "contract_id": "global_s6_profile",
        "milestone": "S6_test",
        "principal_grain": "identity",
        "authoritative_corpus": "data/interim/deduplicated/corpus_clustered_final.csv",
        "cluster_summary_final_csv": "data/interim/deduplicated/cluster_summary_final.csv",
        "cluster_union_provenance_csv": "data/interim/deduplicated/cluster_union_provenance.csv",
        "clusters_final_tsv": "data/interim/deduplicated/clusters_final.tsv",
        "membership_csv": "data/interim/deduplicated/exact_duplicate_membership.csv",
        "overlap_matrix_csv": "data/interim/deduplicated/exact_overlap_matrix.csv",
        "output_report_md": "data/interim/deduplicated/corpus_profile_report.md",
        "profile_dir": "data/interim/deduplicated/s6_profile",
        "figures_dir": "data/interim/deduplicated/figures",
        "checkpoint3_dir": "data/interim/deduplicated/checkpoint3",
        "manifest_json": "data/interim/deduplicated/s6_profile_manifest.json",
        "candidate_max_target_fractions": [0.02, 0.03, 0.05, 0.10],
        "does_not": [
            "balancing",
            "apply_target_cap",
            "select_final_max_target_fraction",
            "populate_partition",
            "assign_ft_ref_eval",
            "start_s7",
        ],
        "expected_s4_hashes": {},
        "expected_s5a_hashes": {},
        "expected_s5_final_hashes": {},
        "sequence_safety_scan_paths": [],
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = run_s6_profile(
        config_path=config_path,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        write_figures_flag=True,
    )
    assert result["ok"] is True
    assert result["headline"]["n_scientific_identities"] == 5
    report = Path(result["output_paths"]["corpus_profile_report.md"]).read_text(encoding="utf-8")
    assert "CHECKPOINT-3" in report
    assert SEQ_A not in report
    second = run_s6_profile(
        config_path=config_path,
        repo_root=tmp_path,
        verify_hashes=False,
        enforce_expected_counts=False,
        write_figures_flag=False,
    )
    assert (
        Path(result["output_paths"]["corpus_profile_report.md"]).read_bytes()
        == Path(second["output_paths"]["corpus_profile_report.md"]).read_bytes()
    )
    assert (
        Path(result["output_paths"]["target_profile.csv"]).read_bytes()
        == Path(second["output_paths"]["target_profile.csv"]).read_bytes()
    )
    figures_dir = tmp_path / "data" / "interim" / "deduplicated" / "figures"
    for name in FIGURE_FILENAMES:
        assert (figures_dir / name).is_file()
    pack = Path(result["output_paths"]["figure_pack_supervisor.md"]).read_text(encoding="utf-8")
    assert SEQ_A not in pack
    assert "Figure 1" in pack
    regime = Path(result["output_paths"]["source_length_regime_summary.csv"]).read_text(
        encoding="utf-8"
    )
    assert GMM_POSTERIOR_ASSIGNMENT_METHOD in regime
    assert (
        Path(result["output_paths"]["source_length_regime_summary.csv"]).read_bytes()
        == Path(second["output_paths"]["source_length_regime_summary.csv"]).read_bytes()
    )
    assert (
        Path(result["output_paths"]["figure_pack_supervisor.md"]).read_bytes()
        == Path(second["output_paths"]["figure_pack_supervisor.md"]).read_bytes()
    )


def _assembled():
    rows, summary, membership, overlap = _corpus_bundle()
    return assemble_profile(
        rows,
        cluster_summary_rows=summary,
        membership_rows=membership,
        overlap_matrix_rows=overlap,
    )


def test_fig03_facets_are_unique_with_common_bins() -> None:
    result = _assembled()
    spec = fig03_spec(result)
    present = [src for src, values in result.core_lengths_by_source.items() if values]
    assert spec["sources"] == donor_facet_sources(result)
    assert len(spec["sources"]) == len(set(spec["sources"]))
    assert set(spec["sources"]) == set(present)
    preferred = [src for src in PREFERRED_SOURCE_FACET_ORDER if src in present]
    assert spec["sources"][: len(preferred)] == preferred
    assert spec["x_range"] == (spec["bins"][0], spec["bins"][-1])
    for src in spec["sources"]:
        assert spec["source_n"][src] == len(spec["source_lengths"][src])
    all_row = next(row for row in result.source_regime_rows if row["source_db"] == "all")
    per_source = [row for row in result.source_regime_rows if row["source_db"] != "all"]
    assert sum(int(row["n_distinct_cores"]) for row in per_source) == int(all_row["n_distinct_cores"])
    assert int(all_row["n_distinct_cores"]) == result.headline["n_distinct_sequence_core"]
    assert sum(int(row["n_shorter_regime"]) for row in per_source) == int(all_row["n_shorter_regime"])
    assert sum(int(row["n_longer_regime"]) for row in per_source) == int(all_row["n_longer_regime"])
    assert all_row["assignment_method"] == GMM_POSTERIOR_ASSIGNMENT_METHOD


def test_gmm_source_assignment_is_deterministic() -> None:
    values = [20.0] * 20 + [80.0] * 20
    gmm2 = fit_univariate_gmm(values, n_components=2)
    first = gmm_posterior_assignment(values, gmm2)
    second = gmm_posterior_assignment(list(reversed(values)), gmm2)
    assert list(gmm_posterior_assignment(values, gmm2)) == list(first)
    assert int(first.sum()) == 20
    assert set(first.tolist()) <= {0, 1}
    # Reversed values change the assignment order but not the component counts.
    assert int(second.sum()) == int(first.sum())


def test_fig04_core_full_binning_and_stats_reconcile() -> None:
    result = _assembled()
    spec = fig04_spec(result)
    assert spec["bins"]
    assert spec["x_range"] == (spec["bins"][0], spec["bins"][-1])
    assert len(spec["core_lengths"]) == len(spec["full_lengths"]) == spec["n_identities"]
    n_same = sum(core == full for core, full in zip(spec["core_lengths"], spec["full_lengths"]))
    assert spec["n_same_length"] == n_same
    assert spec["n_same_length"] == result.core_full_comparison["n_same_length"]
    assert spec["median_full_minus_core_nt"] == pytest.approx(
        result.core_full_comparison["median_full_minus_core_nt"]
    )
    assert spec["median_core_nt"] == pytest.approx(result.core_full_comparison["median_core_nt"])
    assert spec["median_full_nt"] == pytest.approx(result.core_full_comparison["median_full_nt"])


def test_fig06_categorical_log_axis_and_frozen_distribution() -> None:
    result = _assembled()
    frozen = {1: 637, 2: 107, 3: 35, 4: 5, 5: 4, 6: 4, 7: 1, 9: 1, 19: 1, 89: 1}
    result.cluster_stats["core_size_distribution"] = frozen
    result.cluster_rows = [
        {
            "n_distinct_sequence_core": "89",
            "canonical_targets": "NGF",
            "cluster_id": "hidden",
        },
        {
            "n_distinct_sequence_core": "19",
            "canonical_targets": "NGF",
            "cluster_id": "hidden-too",
        },
    ]
    spec = fig06_spec(result)
    assert spec["categories"] == [1, 2, 3, 4, 5, 6, 7, 9, 19, 89]
    assert spec["counts"] == [frozen[size] for size in spec["categories"]]
    assert spec["n_clusters"] == 796
    assert spec["yscale"] == "log"
    labels = {item["size"]: item["label"] for item in spec["annotations"]}
    assert labels[89] == "size 89: NGF"
    assert labels[19] == "size 19: NGF"
    assert "hidden" not in labels[89]


def test_fig07_evidence_labels_and_parked_e5() -> None:
    result = _assembled()
    spec = fig07_spec(result)
    assert spec["n_e2"] == result.evidence["n_e2"]
    assert spec["n_e3"] == result.evidence["n_e3"]
    assert spec["n_e4"] == result.evidence["n_e4"]
    assert spec["levels"] == ["E2", "E3", "E4"]
    assert spec["include_e5_bar"] is False
    assert spec["include_e1_bar"] is False
    assert spec["e5_note"] == E5_PARKED_NOTE
    assert "parked" in spec["e5_note"].lower()
    assert spec["n_e5"] == result.evidence["n_e5"]


def test_fig09_candidate_caps_and_current_corpus_line() -> None:
    result = _assembled()
    spec = fig09_spec(result)
    assert spec["fractions"] == list(CANDIDATE_FRACTIONS)
    assert spec["tick_labels"] == ["2%", "3%", "5%", "10%"]
    assert spec["current_corpus"] == result.headline["n_scientific_identities"]
    tables = plot_data_tables(result)
    impact = tables["fig09_candidate_target_cap.csv"]
    for row, ideal, cons in zip(impact, spec["ideal"], spec["conservative"]):
        assert int(row["idealised_recordwise_capped_corpus_size"]) == ideal
        assert int(row["cluster_union_upper_bound_remaining_identities"]) == cons


def test_fig09_live_like_ngf_only_from_3pct() -> None:
    result = _assembled()
    result.headline["n_scientific_identities"] = 1281
    result.cap_rows = [
        {
            "max_target_fraction": "0.02",
            "idealised_recordwise_capped_corpus_size": "1158",
            "cluster_union_upper_bound_remaining_identities": "1026",
            "n_targets_above_threshold": "5",
            "n_clusters_touching_overrepresented_targets": "20",
        },
        {
            "max_target_fraction": "0.03",
            "idealised_recordwise_capped_corpus_size": "1188",
            "cluster_union_upper_bound_remaining_identities": "1150",
            "n_targets_above_threshold": "1",
            "n_clusters_touching_overrepresented_targets": "14",
        },
        {
            "max_target_fraction": "0.05",
            "idealised_recordwise_capped_corpus_size": "1214",
            "cluster_union_upper_bound_remaining_identities": "1150",
            "n_targets_above_threshold": "1",
            "n_clusters_touching_overrepresented_targets": "14",
        },
        {
            "max_target_fraction": "0.10",
            "idealised_recordwise_capped_corpus_size": "1278",
            "cluster_union_upper_bound_remaining_identities": "1150",
            "n_targets_above_threshold": "1",
            "n_clusters_touching_overrepresented_targets": "14",
        },
    ]
    result.cap_target_rows = [
        {"max_target_fraction": "0.02", "canonical_target_name": "NGF"},
        {"max_target_fraction": "0.02", "canonical_target_name": "HIV-1 Rev protein"},
        {"max_target_fraction": "0.03", "canonical_target_name": "NGF"},
        {"max_target_fraction": "0.05", "canonical_target_name": "NGF"},
        {"max_target_fraction": "0.10", "canonical_target_name": "NGF"},
    ]
    for row in result.target_rows:
        if row["canonical_target_name"] == "NGF":
            row["n_clusters"] = "14"
    spec = fig09_spec(result)
    assert spec["current_corpus"] == 1281
    assert spec["tick_labels"] == ["2%", "3%", "5%", "10%"]
    assert spec["targets_above"][0] == 5
    assert spec["only_ngf_from_3pct"] is True
    assert spec["ngf_clusters"] == 14
    captions = build_figure_captions(result)
    fig09 = next(item for item in captions if item["id"] == "9")
    assert "Neither line is the final predicted corpus size" in fig09["caption"]
    assert "14 NGF clusters" in fig09["caption"]


def test_fig01_plain_english_legend() -> None:
    result = _assembled()
    spec = fig01_spec(result)
    assert spec["bar_label"] == "curated aptamer–target identities"
    assert spec["dot_label"] == "independent sequence clusters"
    assert "scientific identities" not in spec["bar_label"]
    assert spec["annotations"]
    assert "identities /" in spec["annotations"][0]["text"]


def test_captions_and_report_are_sequence_free() -> None:
    result = _assembled()
    captions = build_figure_captions(result)
    pack = build_figure_pack_supervisor(result)
    report = build_corpus_profile_report(result)
    assert [item["filename"] for item in captions] == list(FIGURE_FILENAMES)
    for item in captions:
        assert SEQ_A not in item["caption"]
        assert SEQ_B not in item["title"]
        assert "_" not in item["title"]
    assert SEQ_A not in pack
    assert SEQ_A not in report
    assert "may partly reflect" in report
    assert "C3-06" not in report
    assert all(row["human_decision"] == "" for row in result.checkpoint3_decisions)


def test_write_figures_deterministic_png(tmp_path: Path) -> None:
    result = _assembled()
    first_dir = tmp_path / "a"
    second_dir = tmp_path / "b"
    first = write_figures(result, first_dir)
    second = write_figures(result, second_dir)
    for name in FIGURE_FILENAMES:
        assert Path(first[name]).read_bytes() == Path(second[name]).read_bytes()


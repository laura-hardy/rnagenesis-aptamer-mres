"""Synthetic tests for S7D final corpus assembly and validation.

Every literal nucleotide string in this file is shorter than 20 nt.
Live frozen-hash guards read ignored interim CSVs only to compare hashes
and aggregate counts; they do not embed sequences in tracked files.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s5_exact_dedup import scientific_identity_id  # noqa: E402
from adapters.s7_final_build import (  # noqa: E402
    S7DFinalBuildError,
    build_corpus_final_txt,
    identity_schema_audit,
    run_s7d_final_build,
    split_leakage_audit,
    target_cap_audit,
    training_text_gates,
    verify_frozen_file,
)
from adapters.s7_partition import semantic_cluster_set_hash, semantic_identity_set_hash  # noqa: E402
from s7_finalise import run_with_config  # noqa: E402

BASES = "ACGU"
SYNTHETIC_GMM = {
    "gmm_2": {
        "n_components": 2,
        "means": [8.0, 16.0],
        "variances": [1.0, 1.0],
        "weights": [0.5, 0.5],
        "assignment_method": "gmm_k2_maximum_posterior",
    }
}


def _seq(index: int) -> str:
    chars: list[str] = []
    value = index + 1
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
    source_db: str,
    partition: str,
    evidence_level: str = "E2",
    target_type: str = "protein",
    core: str | None = None,
    record_id: str | None = None,
) -> dict[str, str]:
    sequence_core = core or _seq(index)
    identity = scientific_identity_id(sequence_core, target)
    return {
        "scientific_identity_id": identity,
        "record_id": record_id or f"{source_db}:{index}",
        "cluster_id": cluster_id,
        "canonical_target_name": target,
        "target_name": target,
        "target_name_raw": target,
        "target_type": target_type,
        "target_family": "unknown",
        "sequence_core": sequence_core,
        "sequence_full": sequence_core,
        "sequence_raw": sequence_core,
        "sequence_length_core": str(len(sequence_core)),
        "sequence_length_full": str(len(sequence_core)),
        "sequence_core_sha256": hashlib.sha256(sequence_core.encode("utf-8")).hexdigest(),
        "evidence_level": evidence_level,
        "source_db": source_db,
        "partition": partition,
        "chemistry": "RNA",
        "molecule_type": "RNA",
        "redistribution_status": "restricted",
        "independently_attested_by_permissive_source": "false",
        "corroboration_count": "1",
        "contributing_sources": source_db,
        "near_duplicate_family_id": "",
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["record_id"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _spec(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(path.anchor) if False else path), "sha256": _sha(path)}


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def _build_synthetic_tree(tmp_path: Path) -> dict[str, Path]:
    train = [
        _row(index=1, target="T1", cluster_id="c1", source_db="aptabase", partition="FT", evidence_level="E2"),
        _row(index=2, target="T2", cluster_id="c1", source_db="aptabase", partition="FT", evidence_level="E3"),
    ]
    validation = [
        _row(index=3, target="T3", cluster_id="c2", source_db="ena", partition="FT", evidence_level="E2"),
    ]
    ref = [
        _row(index=4, target="T4", cluster_id="c3", source_db="riboaptamer", partition="REF", evidence_level="E4"),
    ]
    eval_rows = [
        _row(index=5, target="T5", cluster_id="c4", source_db="utexas", partition="EVAL", evidence_level="E2"),
    ]
    ft = train + validation
    partitioned = ft + ref + eval_rows
    removed = [
        _row(index=9, target="T9", cluster_id="c9", source_db="aptabase", partition="", evidence_level="E2"),
    ]
    pre_cap = partitioned + removed
    assignment = [
        {"cluster_id": "c1", "ft_split": "TRAIN"},
        {"cluster_id": "c2", "ft_split": "VALIDATION"},
    ]
    parked_ssdna = [
        {
            "record_id": "aptadiff_a:1",
            "native_id": "1",
            "park_reason": "ssdna_parked",
            "molecule_type": "ssDNA",
        }
    ]
    canonical_a = [
        {
            "record_id": "aptadiff_a:1",
            "sequence_core": _seq(11),
            "sequence_full": _seq(11),
            "molecule_type": "ssDNA",
            "chemistry": "DNA",
        }
    ]
    e5 = [
        {
            "reviewed_relationship_id": "ena:e5|1",
            "record_id": "ena:e5",
            "source_db": "ena",
            "canonical_target_name": "E5T",
            "target_type": "protein",
            "evidence_level": "E5",
            "s4_route": "park_evidence_e5",
            "sequence_core": _seq(12),
            "sequence_full": _seq(12),
            "sequence_length_core": "9",
        }
    ]
    non_protein = [
        {
            "reviewed_relationship_id": "aptabase:np|1",
            "record_id": "aptabase:np",
            "source_db": "aptabase",
            "canonical_target_name": "ATP",
            "target_type": "small_molecule",
            "evidence_level": "E2",
            "s4_route": "park_non_protein",
            "sequence_core": _seq(13),
        }
    ]
    s4_all = e5 + non_protein + [
        {
            "reviewed_relationship_id": "aptabase:1|1",
            "record_id": "aptabase:1",
            "source_db": "aptabase",
            "canonical_target_name": "T1",
            "target_type": "protein",
            "evidence_level": "E2",
            "s4_route": "primary_candidate",
            "sequence_core": train[0]["sequence_core"],
        }
    ]
    audit = [
        {
            "record_id": "aptamerbase:hold",
            "source_db": "aptamerbase",
            "audit_class": "hold_target_unresolved",
            "s4_route": "hold_target_unresolved",
            "canonical_target_name": "",
        }
    ]
    routing = [
        {"grain": "source_record", "source_db": "aptabase", "category": "primary_candidate", "n": "2"},
        {"grain": "reviewed_relationship", "source_db": "ena", "category": "park_evidence_e5", "n": "1"},
    ]
    eval_refs = [
        {
            "reference_id": "ref1",
            "record_type": "sequence",
            "aptamer_name": "XK",
            "target_name_raw": "KPC-2",
            "target_name": "KPC-2",
            "evaluation_role": "positive_kpc2",
            "evaluation_label": "positive",
            "molecule_type": "ssDNA",
            "source_key": "yu_2021",
            "status": "resolved",
        }
    ]
    leakage = [
        {
            "exclusion_id": "lex_x",
            "reference_id": "ref1",
            "target_name": "KPC-2",
            "evaluation_role": "positive",
            "sequence_compare_full": "TTTTTTTT",
            "sequence_compare_core": "TTTTTTTT",
            "status": "resolved",
        }
    ]
    aliases = [
        {
            "canonical_target": "KPC-2",
            "alias": "kpc-2",
            "match_type": "exact_alias",
            "target_family": "beta-lactamase",
            "exclusion_reason": "eval",
            "notes": "",
        }
    ]
    rejection = [
        {
            "record_id": "aptadb:99",
            "source_db": "aptadb",
            "stage": "S3",
            "rejection_reason": "length_out_of_range",
        }
    ]
    combined = [{"record_id": "ena:e5", "near_duplicate_family_id": ""}]
    dictionary = [{"target_dictionary_id": "TD1", "canonical_target_name": "T1"}]
    record_map = [{"record_id": "aptabase:1", "s4_route": "primary_candidate"}]

    paths = {
        "post_cap": tmp_path / "data/interim/s7a_target_cap/corpus_post_cap.csv",
        "partitioned": tmp_path / "data/interim/s7b_partition/corpus_partitioned.csv",
        "ft": tmp_path / "data/interim/s7b_partition/ft.csv",
        "ref": tmp_path / "data/interim/s7b_partition/ref.csv",
        "eval": tmp_path / "data/interim/s7b_partition/eval.csv",
        "train": tmp_path / "data/interim/s7c_ft_split/ft_train.csv",
        "validation": tmp_path / "data/interim/s7c_ft_split/ft_validation.csv",
        "assignment": tmp_path / "data/interim/s7c_ft_split/ft_split_assignment.csv",
        "pre_cap": tmp_path / "data/interim/deduplicated/corpus_clustered_final.csv",
        "removed": tmp_path / "data/interim/s7a_target_cap/s7a_removed_clusters.csv",
        "s4_rel": tmp_path / "data/interim/global_s4/global_s4_reviewed_relationships.csv",
        "s4_dict": tmp_path / "data/interim/global_s4/global_s4_reviewed_target_dictionary.csv",
        "s4_map": tmp_path / "data/interim/global_s4/global_s4_record_relationship_map.csv",
        "s4_audit": tmp_path / "data/interim/global_s4/global_s4_parked_excluded_audit.csv",
        "s4_summary": tmp_path / "data/interim/global_s4/global_s4_routing_summary.csv",
        "s4_combined": tmp_path / "data/interim/global_s4/combined_global_s4_input.csv",
        "parked_ssdna": tmp_path / "data/interim/checkpoints/aptadiff_a_cp1/resolved/a_parked.csv",
        "canonical_a": tmp_path / "data/interim/checkpoints/aptadiff_a_cp1/resolved/a_canonical.csv",
        "eval_refs": tmp_path / "data/interim/evaluation/evaluation_reference_manifest.csv",
        "leakage": tmp_path / "data/interim/leakage_exclusion_set.csv",
        "aliases": tmp_path / "config/leakage_target_aliases.csv",
        "rejection": tmp_path / "data/interim/checkpoints/aptadb_cp1/resolved/rej.csv",
        "bimodality": tmp_path / "data/interim/deduplicated/s6_profile/bimodality.json",
        "output": tmp_path / "data/processed",
        "config": tmp_path / "config/global_s7d_final_build.json",
    }
    _write_csv(paths["post_cap"], partitioned)
    _write_csv(paths["partitioned"], partitioned)
    _write_csv(paths["ft"], ft)
    _write_csv(paths["ref"], ref)
    _write_csv(paths["eval"], eval_rows)
    _write_csv(paths["train"], train)
    _write_csv(paths["validation"], validation)
    _write_csv(paths["assignment"], assignment)
    _write_csv(paths["pre_cap"], pre_cap)
    _write_csv(paths["removed"], [{"cluster_id": "c9", "trigger_target": "T9"}])
    _write_csv(paths["s4_rel"], s4_all)
    _write_csv(paths["s4_dict"], dictionary)
    _write_csv(paths["s4_map"], record_map)
    _write_csv(paths["s4_audit"], audit)
    _write_csv(paths["s4_summary"], routing)
    _write_csv(paths["s4_combined"], combined)
    _write_csv(paths["parked_ssdna"], parked_ssdna)
    _write_csv(paths["canonical_a"], canonical_a)
    _write_csv(paths["eval_refs"], eval_refs)
    _write_csv(paths["leakage"], leakage)
    _write_csv(paths["aliases"], aliases)
    _write_csv(paths["rejection"], rejection)
    paths["bimodality"].parent.mkdir(parents=True, exist_ok=True)
    paths["bimodality"].write_text(json.dumps(SYNTHETIC_GMM), encoding="utf-8")

    def fspec(key: str, extra: dict | None = None) -> dict:
        payload = {"path": _rel(paths[key], tmp_path), "sha256": _sha(paths[key])}
        if extra:
            payload.update(extra)
        return payload

    config = {
        "contract_id": "global_s7d_final_build",
        "build_date": "2026-09-22",
        "governing_plan_version": "1.5",
        "max_target_fraction": 1.0,
        "output_dir": "data/processed",
        "length_regime": {
            "s6_bimodality_json": _rel(paths["bimodality"], tmp_path),
            "assignment_method": "gmm_k2_maximum_posterior",
            "refit": False,
        },
        "leakage_exclusion_set": _rel(paths["leakage"], tmp_path),
        "leakage_target_aliases": _rel(paths["aliases"], tmp_path),
        "source_registry": "missing.csv",
        "frozen_inputs": {
            "s5_pre_cap_corpus": fspec("pre_cap"),
            "s7a_post_cap": fspec("post_cap"),
            "s7a_removed_clusters": fspec("removed"),
            "s7b_partitioned": fspec("partitioned"),
            "s7b_ft": fspec("ft"),
            "s7b_ref": fspec(
                "ref",
                {
                    "identity_set_hash": semantic_identity_set_hash(ref),
                    "cluster_set_hash": semantic_cluster_set_hash(ref),
                },
            ),
            "s7b_eval": fspec(
                "eval",
                {
                    "identity_set_hash": semantic_identity_set_hash(eval_rows),
                    "cluster_set_hash": semantic_cluster_set_hash(eval_rows),
                },
            ),
            "s7c_train": fspec(
                "train",
                {
                    "identity_set_hash": semantic_identity_set_hash(train),
                    "cluster_set_hash": semantic_cluster_set_hash(train),
                },
            ),
            "s7c_validation": fspec(
                "validation",
                {
                    "identity_set_hash": semantic_identity_set_hash(validation),
                    "cluster_set_hash": semantic_cluster_set_hash(validation),
                },
            ),
            "s7c_assignment": fspec("assignment"),
            "s4_reviewed_relationships": fspec("s4_rel"),
            "s4_reviewed_dictionary": fspec("s4_dict"),
            "s4_record_map": fspec("s4_map"),
            "s4_parked_audit": fspec("s4_audit"),
            "s4_routing_summary": fspec("s4_summary"),
            "s4_combined_input": fspec("s4_combined"),
        },
        "parked_ssdna_sources": [
            {
                "source": "aptadiff_a",
                "path": _rel(paths["parked_ssdna"], tmp_path),
                "sha256": _sha(paths["parked_ssdna"]),
                "canonical_path": _rel(paths["canonical_a"], tmp_path),
                "molecule_type_filter": None,
            }
        ],
        "parked_non_protein_sources": [
            {
                "source": "global_s4",
                "lane": "global_s4_park_non_protein",
                "path": _rel(paths["s4_rel"], tmp_path),
                "sha256": _sha(paths["s4_rel"]),
                "filter_field": "s4_route",
                "filter_value": "park_non_protein",
            }
        ],
        "parked_e5_source": {
            "lane": "global_s4_park_evidence_e5",
            "path": _rel(paths["s4_rel"], tmp_path),
            "sha256": _sha(paths["s4_rel"]),
            "filter_field": "s4_route",
            "filter_value": "park_evidence_e5",
        },
        "parked_inventory_lanes": [
            {
                "source": "aptadiff_a",
                "stage": "CHECKPOINT-1",
                "route": "parked_ssdna",
                "grain": "source_record",
                "path": _rel(paths["parked_ssdna"], tmp_path),
                "sha256": _sha(paths["parked_ssdna"]),
                "expected_row_count": 1,
                "sequence_bearing": False,
                "consolidated_output": "parked_ssdna.csv",
                "final_disposition": "consolidated_parked_ssdna",
            },
            {
                "source": "global_s4",
                "stage": "S4",
                "route": "park_non_protein",
                "grain": "reviewed_relationship",
                "path": _rel(paths["s4_rel"], tmp_path),
                "sha256": _sha(paths["s4_rel"]),
                "filters": [{"field": "s4_route", "value": "park_non_protein"}],
                "expected_row_count": 1,
                "sequence_bearing": True,
                "consolidated_output": "parked_non_protein_targets.csv",
                "final_disposition": "consolidated_parked_non_protein",
            },
            {
                "source": "global_s4",
                "stage": "S4",
                "route": "park_evidence_e5",
                "grain": "reviewed_relationship",
                "path": _rel(paths["s4_rel"], tmp_path),
                "sha256": _sha(paths["s4_rel"]),
                "filters": [{"field": "s4_route", "value": "park_evidence_e5"}],
                "expected_row_count": 1,
                "sequence_bearing": True,
                "consolidated_output": "parked_evidence_e5.csv",
                "final_disposition": "consolidated_parked_e5",
            },
            {
                "source": "global_s4",
                "stage": "S4",
                "route": "hold_target_unresolved",
                "grain": "source_record",
                "path": _rel(paths["s4_audit"], tmp_path),
                "sha256": _sha(paths["s4_audit"]),
                "filters": [{"field": "audit_class", "value": "hold_target_unresolved"}],
                "expected_row_count": 1,
                "sequence_bearing": False,
                "consolidated_output": "",
                "final_disposition": "retained_in_source_level_park",
                "not_consolidated_reason": "S4 hold; not ssDNA, non-protein, or E5.",
            },
        ],
        "evaluation_references": {
            "path": _rel(paths["eval_refs"], tmp_path),
            "sha256": _sha(paths["eval_refs"]),
        },
        "replication_dataset_a": {
            "enabled": True,
            "source": "aptadiff_a",
            "parked_path": _rel(paths["parked_ssdna"], tmp_path),
            "canonical_path": _rel(paths["canonical_a"], tmp_path),
            "schema_note": "synthetic",
        },
        "rejection_sources": [
            {
                "source": "aptadb",
                "stage": "CHECKPOINT-1",
                "path": _rel(paths["rejection"], tmp_path),
            }
        ],
        "s4_rejection_routes": ["hold_target_unresolved"],
        "checkpoint_metadata_for_funnel": [],
        "sequence_safety_scan_paths": [],
        "corpus_final_txt_order": "first_occurrence_in_frozen_ft_train_csv",
    }
    paths["config"].parent.mkdir(parents=True, exist_ok=True)
    paths["config"].write_text(json.dumps(config, indent=2), encoding="utf-8")
    return paths


def test_frozen_hash_guard_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "x.csv"
    path.write_text("a\n1\n", encoding="utf-8")
    with pytest.raises(S7DFinalBuildError, match="frozen hash mismatch"):
        verify_frozen_file({"path": "x.csv", "sha256": "0" * 64}, tmp_path, verify_hashes=True)


def test_corpus_final_txt_train_only() -> None:
    train = [
        _row(index=1, target="T1", cluster_id="c1", source_db="a", partition="FT"),
        _row(index=1, target="T2", cluster_id="c1", source_db="a", partition="FT", core=_seq(1)),
        _row(index=2, target="T3", cluster_id="c2", source_db="a", partition="FT"),
    ]
    validation = [_row(index=3, target="T4", cluster_id="c3", source_db="a", partition="FT")]
    ref = [_row(index=4, target="T5", cluster_id="c4", source_db="a", partition="REF")]
    eval_rows = [_row(index=5, target="T6", cluster_id="c5", source_db="a", partition="EVAL")]
    lines = build_corpus_final_txt(train)
    assert lines == [_seq(1), _seq(2)]
    gates = training_text_gates(
        lines,
        train_rows=train,
        validation_rows=validation,
        ref_rows=ref,
        eval_rows=eval_rows,
    )
    assert gates["line_count"] == 2
    assert gates["duplicate_lines"] == 0
    with pytest.raises(S7DFinalBuildError, match="core set is not frozen TRAIN"):
        training_text_gates(
            lines + [_seq(3)],
            train_rows=train,
            validation_rows=validation,
            ref_rows=ref,
            eval_rows=eval_rows,
        )


def test_split_schema_and_cap_gates() -> None:
    train = [_row(index=1, target="T1", cluster_id="c1", source_db="a", partition="FT")]
    validation = [_row(index=2, target="T2", cluster_id="c2", source_db="a", partition="FT")]
    ref = [_row(index=3, target="T3", cluster_id="c3", source_db="a", partition="REF")]
    eval_rows = [_row(index=4, target="T4", cluster_id="c4", source_db="a", partition="EVAL")]
    split = split_leakage_audit(
        {"TRAIN": train, "VALIDATION": validation, "REF": ref, "EVAL": eval_rows}
    )
    assert split["cluster_crossings"] == 0
    leaked = dict(eval_rows[0])
    leaked["cluster_id"] = "c1"
    with pytest.raises(S7DFinalBuildError, match="split leakage"):
        split_leakage_audit(
            {"TRAIN": train, "VALIDATION": validation, "REF": ref, "EVAL": [leaked]}
        )
    corpus = train + validation + ref + eval_rows
    schema = identity_schema_audit(corpus)
    assert schema["n_scientific_identities"] == 4
    cap = target_cap_audit(corpus, max_fraction=0.5)
    assert cap["ok"] is True
    with pytest.raises(S7DFinalBuildError, match="target cap"):
        target_cap_audit(corpus, max_fraction=0.1)


def test_end_to_end_synthetic_assembly(tmp_path: Path) -> None:
    paths = _build_synthetic_tree(tmp_path)
    config = json.loads(paths["config"].read_text(encoding="utf-8"))
    result = run_s7d_final_build(
        config=config,
        repo_root=tmp_path,
        output_dir=paths["output"],
        verify_hashes=True,
        enforce_expected_counts=False,
        write_outputs=True,
        run_sequence_safety=False,
    )
    assert result["ok"] is True
    out = paths["output"]
    assert (out / "corpus_final.csv").read_bytes() == paths["partitioned"].read_bytes()
    assert (out / "ft_train.csv").read_bytes() == paths["train"].read_bytes()
    assert (out / "ft_validation.csv").read_bytes() == paths["validation"].read_bytes()
    assert (out / "ref.csv").read_bytes() == paths["ref"].read_bytes()
    assert (out / "eval.csv").read_bytes() == paths["eval"].read_bytes()
    txt = (out / "corpus_final.txt").read_text(encoding="utf-8").splitlines()
    assert txt == [_seq(1), _seq(2)]
    assert len(set(txt)) == 2
    parked = list(csv.DictReader((out / "parked_ssdna.csv").open(newline="", encoding="utf-8")))
    assert len(parked) == 1
    assert parked[0]["sequence_core"] == _seq(11)
    e5 = list(csv.DictReader((out / "parked_evidence_e5.csv").open(newline="", encoding="utf-8")))
    assert len(e5) == 1
    primary_ids = {row["record_id"] for row in csv.DictReader((out / "corpus_final.csv").open())}
    assert e5[0]["record_id"] not in primary_ids
    nonprot = list(csv.DictReader((out / "parked_non_protein_targets.csv").open()))
    assert len(nonprot) == 1
    eval_refs = list(csv.DictReader((out / "evaluation_references.csv").open()))
    assert eval_refs[0]["target_name"] == "KPC-2"
    rejected = list(csv.DictReader((out / "rejected_all.csv").open()))
    reasons = {row["rejection_reason"] for row in rejected}
    assert "length_out_of_range" in reasons
    assert "hold_target_unresolved" in reasons
    assert "target_cap_subsample" in reasons
    assert result["e5_diagnostic"]["e5_promoted"] is False
    assert result["target_cap"]["ok"] is True
    assert result["leakage"]["exact_evaluation_reference_leakage"] == 0
    assert "corpus_manifest.json" in result["output_hashes"]
    assert (out / "corpus_replication_datasetA.csv").is_file()
    assert result["schema"]["E5"] == 0
    assert result["schema"]["non_protein"] == 0
    inventory = list(csv.DictReader((out / "parked_inventory.csv").open(newline="", encoding="utf-8")))
    assert len(inventory) == 4
    assert {row["final_disposition"] for row in inventory} == {
        "consolidated_parked_ssdna",
        "consolidated_parked_non_protein",
        "consolidated_parked_e5",
        "retained_in_source_level_park",
    }
    assert result["parked_inventory"]["unaccounted_parked_lanes"] == 0
    assert "not the exact number of S5 clusters" in result["report"]
    assert "Parked-data completeness and grain" in result["report"]
    assert "separate replication/comparability artefact" in result["report"]
    assert result["e5_diagnostic"]["cluster_diagnostic"][
        "diagnostic_cluster_units_are_counterfactual"
    ] is True


def test_e5_never_promoted_and_eval_refs_separated(tmp_path: Path) -> None:
    paths = _build_synthetic_tree(tmp_path)
    config = json.loads(paths["config"].read_text(encoding="utf-8"))
    result = run_s7d_final_build(
        config=config,
        repo_root=tmp_path,
        output_dir=paths["output"],
        verify_hashes=True,
        enforce_expected_counts=False,
        run_sequence_safety=False,
    )
    assert result["e5_diagnostic"]["frozen_corpus_changed"] is False
    assert "generic held-out" in result["evaluation_references"]["distinct_from_eval_partition"]


def test_frozen_split_immutability(tmp_path: Path) -> None:
    paths = _build_synthetic_tree(tmp_path)
    config = json.loads(paths["config"].read_text(encoding="utf-8"))
    run_s7d_final_build(
        config=config,
        repo_root=tmp_path,
        output_dir=paths["output"],
        verify_hashes=True,
        enforce_expected_counts=False,
        run_sequence_safety=False,
    )
    assert paths["train"].read_bytes() == (paths["output"] / "ft_train.csv").read_bytes()
    assert _sha(paths["partitioned"]) == _sha(paths["output"] / "corpus_final.csv")


def test_hash_guard_on_mutated_frozen_input(tmp_path: Path) -> None:
    paths = _build_synthetic_tree(tmp_path)
    config = json.loads(paths["config"].read_text(encoding="utf-8"))
    paths["train"].write_text(paths["train"].read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(S7DFinalBuildError, match="frozen hash mismatch"):
        run_s7d_final_build(
            config=config,
            repo_root=tmp_path,
            output_dir=paths["output"],
            verify_hashes=True,
            enforce_expected_counts=False,
            run_sequence_safety=False,
        )


def test_deterministic_rerun(tmp_path: Path) -> None:
    paths = _build_synthetic_tree(tmp_path)
    first = tmp_path / "data/processed/run_a"
    second = tmp_path / "data/processed/run_b"
    config = json.loads(paths["config"].read_text(encoding="utf-8"))
    a = run_s7d_final_build(
        config=config,
        repo_root=tmp_path,
        output_dir=first,
        verify_hashes=True,
        enforce_expected_counts=False,
        run_sequence_safety=False,
    )
    b = run_s7d_final_build(
        config=config,
        repo_root=tmp_path,
        output_dir=second,
        verify_hashes=True,
        enforce_expected_counts=False,
        run_sequence_safety=False,
    )
    for name in (
        "corpus_final.csv",
        "corpus_final.txt",
        "ft_train.csv",
        "ft_validation.csv",
        "ref.csv",
        "eval.csv",
        "parked_ssdna.csv",
        "parked_non_protein_targets.csv",
        "parked_evidence_e5.csv",
        "evaluation_references.csv",
        "rejected_all.csv",
        "parked_inventory.csv",
        "corpus_report.md",
        "corpus_manifest.json",
    ):
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert a["output_hashes"][name] == b["output_hashes"][name]


def test_cli_synthetic(tmp_path: Path) -> None:
    paths = _build_synthetic_tree(tmp_path)
    result = run_with_config(
        config_path=paths["config"].relative_to(tmp_path),
        repo_root=tmp_path,
        verify_hashes=True,
        enforce_expected_counts=False,
        repeat_for_determinism=True,
        run_sequence_safety=False,
    )
    assert result["determinism_ok"] is True
    assert result["ok"] is True


def test_live_frozen_hash_guards() -> None:
    post_cap = REPO_ROOT / "data/interim/s7a_target_cap/corpus_post_cap.csv"
    if not post_cap.is_file():
        pytest.skip("live frozen corpus is not present")
    config = json.loads((REPO_ROOT / "config/global_s7d_final_build.json").read_text(encoding="utf-8"))
    for key, spec in config["frozen_inputs"].items():
        result = verify_frozen_file(spec, REPO_ROOT, verify_hashes=True)
        assert result["matched"] is True, key


def test_live_train_text_semantics() -> None:
    train_path = REPO_ROOT / "data/interim/s7c_ft_split/ft_train.csv"
    validation_path = REPO_ROOT / "data/interim/s7c_ft_split/ft_validation.csv"
    ref_path = REPO_ROOT / "data/interim/s7b_partition/ref.csv"
    eval_path = REPO_ROOT / "data/interim/s7b_partition/eval.csv"
    if not train_path.is_file():
        pytest.skip("live frozen TRAIN is not present")
    train = list(csv.DictReader(train_path.open(newline="", encoding="utf-8")))
    validation = list(csv.DictReader(validation_path.open(newline="", encoding="utf-8")))
    ref = list(csv.DictReader(ref_path.open(newline="", encoding="utf-8")))
    eval_rows = list(csv.DictReader(eval_path.open(newline="", encoding="utf-8")))
    lines = build_corpus_final_txt(train)
    gates = training_text_gates(
        lines,
        train_rows=train,
        validation_rows=validation,
        ref_rows=ref,
        eval_rows=eval_rows,
    )
    assert gates["line_count"] == 669
    assert gates["distinct_sequences"] == 669
    assert gates["duplicate_lines"] == 0
    assert gates["validation_contamination"] == 0
    assert gates["ref_contamination"] == 0
    assert gates["eval_contamination"] == 0


def test_tracked_data_safety() -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "data"], cwd=REPO_ROOT, text=True
    ).strip()
    assert tracked == ""


def test_live_parked_inventory_and_e5_wording() -> None:
    config_path = REPO_ROOT / "config/global_s7d_final_build.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    lanes = config.get("parked_inventory_lanes") or []
    if not lanes:
        pytest.skip("S7D parked inventory lanes are not configured")
    from adapters.s7_final_build import assemble_parked_inventory

    rows, summary = assemble_parked_inventory(lanes, REPO_ROOT, verify_hashes=True)
    assert summary["unaccounted_parked_lanes"] == 0
    assert summary["parked_lanes_inventoried"] == len(rows) == len(lanes)
    assert summary["parked_lanes_retained_source_level_only"] > 0
    assert any(row["final_disposition"] == "retained_in_source_level_park" for row in rows)
    assert "sequence" not in {column.lower() for column in rows[0]}

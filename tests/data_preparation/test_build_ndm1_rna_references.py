"""Tests for the NDM-1 RNA D9 reference layer.

Literal nucleotide strings in this file are shorter than 20 nt.
Live checks compare hashes, lengths, statuses, and source wording.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import adapters.ndm1_rna_references as ndm1_rna  # noqa: E402
from adapters.ndm1_rna_references import (  # noqa: E402
    ABSENT_FILE,
    Ndm1RnaError,
    assert_transcription_agreement,
    canonical_rna_from_cleaned,
    clean_reported_sequence,
    reconcile_existing_s0b,
    run_leakage_diagnostics,
    run_ndm1_rna_build,
    sha256_text,
    snapshot_optional_paths,
    verify_raw_source_hashes,
)
from adapters.s5_validate_exact_dedup import scan_text_for_sequence_leak  # noqa: E402
from s0_build_registry import load_registry_spec, sha256_file  # noqa: E402

CONFIG_PATH = REPO_ROOT / "config/ndm1_rna_reference_build.json"
PROTECTED = (
    "docs/aptarank-two-stage-evaluation-implementation-plan.md",
    "docs/aptarank_full_mres_thesis_evaluation_plan.md",
    "docs/planned_evaluation_report.md",
)
TRACKED_SEQUENCE_FREE = (
    CONFIG_PATH,
    REPO_ROOT / "scripts/data_preparation/adapters/ndm1_rna_references.py",
    REPO_ROOT / "scripts/data_preparation/build_ndm1_rna_references.py",
    Path(__file__),
)


def _config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _sources_ready() -> bool:
    config = _config()
    return all((REPO_ROOT / spec["path"]).is_file() for spec in config["raw_sources"].values())


def test_clean_reported_sequence_keeps_raw_hyphens_out_of_cleaned_form() -> None:
    reported = "ACGT----"
    cleaned = clean_reported_sequence(reported)
    assert "-" in reported
    assert cleaned == "ACGT"
    assert "-" not in cleaned
    assert len(reported) == 8
    assert len(cleaned) == 4


def test_internal_hyphen_is_rejected() -> None:
    with pytest.raises(Ndm1RnaError, match="non-trailing"):
        clean_reported_sequence("ACG-T")


def test_t_to_u_is_deterministic_and_length_preserving() -> None:
    cleaned = "ACGTACGT"
    rna = canonical_rna_from_cleaned(cleaned)
    assert rna == "ACGUACGU"
    assert canonical_rna_from_cleaned(cleaned) == rna
    assert len(rna) == len(cleaned)
    assert "T" not in rna
    with pytest.raises(Ndm1RnaError, match="contains U"):
        canonical_rna_from_cleaned("ACGU")


def test_transcription_disagreement_fails_closed() -> None:
    pdf_rows = [
        {
            "clone_id": "D902",
            "sequence_reported": "ACGT",
            "purine_percent_reported": "50%",
            "gc_percent_reported": "50%",
        }
    ]
    csv_rows = [
        {
            "clone_id": "D902",
            "sequence_reported": "ACGA",
            "sequence_cleaned": "ACGA",
            "purine_percent_reported": "50%",
            "gc_percent_reported": "50%",
        }
    ]
    with pytest.raises(Ndm1RnaError, match="clone order|disagreement"):
        assert_transcription_agreement(pdf_rows, csv_rows)


def test_cleaned_csv_disagreement_fails_closed() -> None:
    pdf_rows = [
        {
            "clone_id": clone,
            "sequence_reported": "ACGT----" if clone == "D907" else "ACGTACGTAC",
            "purine_percent_reported": "50%",
            "gc_percent_reported": "50%",
        }
        for clone in ("D902", "D907", "D909", "D913", "D914", "D918", "D920")
    ]
    csv_rows = []
    for row in pdf_rows:
        cleaned = row["sequence_reported"].rstrip("-")
        if row["clone_id"] == "D907":
            cleaned = "ACGTAC"
        csv_rows.append(
            {
                "clone_id": row["clone_id"],
                "sequence_reported": row["sequence_reported"],
                "sequence_cleaned": cleaned,
                "purine_percent_reported": "50%",
                "gc_percent_reported": "50%",
            }
        )
    with pytest.raises(Ndm1RnaError, match="cleaned sequence disagrees"):
        assert_transcription_agreement(pdf_rows, csv_rows)


def test_source_hash_mismatch_fails_closed() -> None:
    config = _config()
    config["raw_sources"]["table6_csv"]["sha256"] = "0" * 64
    with pytest.raises(Ndm1RnaError, match="SHA-256 mismatch"):
        verify_raw_source_hashes(REPO_ROOT, config)


def test_registry_path_is_repaired_and_csv_hash_is_unchanged() -> None:
    config = _config()
    rows = load_registry_spec(REPO_ROOT / "config/source_registry.csv")
    matches = [row for row in rows if row.source_key == "von_laer_2013_d9_table6"]
    assert len(matches) == 1
    row = matches[0]
    assert row.path == config["registered_csv_path"]
    assert row.path != config["previous_registered_csv_path"]
    assert row.sha256 == config["raw_sources"]["table6_csv"]["sha256"]
    assert row.n_rows_expected == 7
    assert sha256_file(REPO_ROOT / row.path) == row.sha256
    operational = REPO_ROOT / config["operational_registry_path"]
    assert operational.is_file()
    operational_rows = load_registry_spec(operational)
    operational_match = [
        item for item in operational_rows if item.source_key == "von_laer_2013_d9_table6"
    ]
    assert len(operational_match) == 1
    assert operational_match[0].path == row.path
    assert operational_match[0].sha256 == row.sha256


def test_reconciliation_rejects_a_missing_leakage_record() -> None:
    records = [
        {
            "clone_id": "D902",
            "reference_id": "von_laer_2013_ndm1_rna_d902",
            "reported": "ACGT",
            "cleaned": "ACGT",
            "canonical": "ACGU",
            "spec": {
                "legacy_s0b_reference_id": "von_laer_2013_d902",
                "legacy_evaluation_label": "pool_nonbinder",
                "legacy_evaluation_role": "pool_nonbinder_or_control",
                "legacy_exclusion_id": "lex_0001_abcd",
                "legacy_discrepancy_code": "legacy_pool_nonbinder_does_not_distinguish_no_detectable_binding",
                "qualitative_binding_status": "no_detectable_binding",
                "proposed_disposition": "retain_existing_s0b_and_leakage_record_enrich_separately_do_not_duplicate",
            },
        }
    ]
    with pytest.raises(Ndm1RnaError, match="exactly seven"):
        reconcile_existing_s0b(records=records, manifest_rows=[], leakage_rows=[])


def test_leakage_exact_and_near_matches_use_comparison_form() -> None:
    records = [
        {
            "clone_id": "D902",
            "reference_id": "ref_d902",
            "reported": "ACGTACGTAC",
            "cleaned": "ACGTACGTAC",
            "canonical": "ACGUACGUAC",
        },
        {
            "clone_id": "D907",
            "reference_id": "ref_d907",
            "reported": "ACGT----",
            "cleaned": "ACGT",
            "canonical": "ACGU",
        },
    ]
    partitions = {
        "TRAIN": [
            {
                "record_id": "exact",
                "scientific_identity_id": "sci_exact",
                "sequence_full": "ACGUACGUAC",
                "sequence_core": "ACGUACGUAC",
            },
            {
                "record_id": "near",
                "scientific_identity_id": "sci_near",
                "sequence_full": "ACGTACGTAA",
                "sequence_core": "ACGTACGTAA",
            },
        ],
        "VALIDATION": [],
        "REF": [],
        "EVAL": [],
        "CORPUS": [],
    }
    summary = run_leakage_diagnostics(
        records=records,
        partitions=partitions,
        corpus_lines=["GGGGAAAA"],
        threshold=0.90,
    )
    train = summary["by_partition"]["TRAIN"]
    assert train["exact_matches"] > 0
    assert train["identity_ge_threshold"] > train["exact_matches"]
    assert summary["any_exact"] is True
    assert summary["any_identity_ge_threshold"] is True
    assert summary["reverse_complement_matching"] is False


def test_tracked_files_are_sequence_free() -> None:
    for path in TRACKED_SEQUENCE_FREE:
        text = path.read_text(encoding="utf-8")
        assert scan_text_for_sequence_leak(text) is False, path.name


def test_frozen_pins_remain_and_cross_pipeline_files_are_not_hash_pinned() -> None:
    config = _config()
    assert "expected_protected_untracked_sha256" not in config
    assert "immutable_tracked_authorities" not in config
    assert config["protected_untracked_files"] == list(PROTECTED)
    assert config["untouched_during_run"] == [
        "config/global_s7d_final_build.json",
        "config/ndm1_ssdna_reference_build.json",
        "scripts/data_preparation/s0_build_leakage_exclusion.py",
    ]
    frozen = {
        "ft_train.csv": config["frozen_partitions"]["TRAIN"],
        "ft_validation.csv": config["frozen_partitions"]["VALIDATION"],
        "ref.csv": config["frozen_partitions"]["REF"],
        "eval.csv": config["frozen_partitions"]["EVAL"],
        "corpus_final.csv": config["frozen_corpus"]["corpus_final.csv"],
        "corpus_final.txt": config["frozen_corpus"]["corpus_final.txt"],
        "evaluation_references.csv": config["evaluation_references_path"],
        "evaluation_reference_manifest.csv": config["evaluation_reference_manifest_path"],
        "leakage_exclusion_set.csv": config["leakage_exclusion_set_path"],
        "corpus_manifest.json": config["s7d_manifest_path"],
    }
    for name, rel in frozen.items():
        assert sha256_file(REPO_ROOT / rel) == config["expected_frozen_sha256"][name], name
    for rel in config["untouched_during_run"]:
        assert (REPO_ROOT / rel).is_file(), rel
        assert rel not in config["expected_frozen_sha256"]


def _file_identity(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"present": False, "sha256": None, "size": None, "mtime_ns": None}
    stat = path.stat()
    return {
        "present": True,
        "sha256": sha256_file(path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _dry_run_watched_paths(config: dict) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for spec in config["raw_sources"].values():
        paths[f"raw:{spec['path']}"] = REPO_ROOT / spec["path"]
    operational = [
        config["source_registry_path"],
        config["operational_registry_path"],
        *config["frozen_partitions"].values(),
        *config["frozen_corpus"].values(),
        config["evaluation_references_path"],
        config["evaluation_reference_manifest_path"],
        config["leakage_exclusion_set_path"],
        config["s7d_manifest_path"],
        *config["untouched_during_run"],
    ]
    for rel in operational:
        paths[f"input:{rel}"] = REPO_ROOT / rel
    for name in (
        "ndm1_rna_aptamer_references.csv",
        "ndm1_rna_binding_evidence.csv",
        "ndm1_rna_reference_manifest.json",
        "ndm1_rna_reference_verification_report.md",
    ):
        paths[f"output:{name}"] = REPO_ROOT / "data/processed" / name
    return paths


@pytest.mark.skipif(not _sources_ready(), reason="NDM-1 RNA source files are not present")
def test_dry_run_preserves_hash_size_and_mtime() -> None:
    config = _config()
    watched = _dry_run_watched_paths(config)
    before = {label: _file_identity(path) for label, path in watched.items()}
    for label, identity in before.items():
        assert identity["present"] is True, label
    first = run_ndm1_rna_build(
        config=config,
        repo_root=REPO_ROOT,
        write_outputs=False,
        run_leakage=True,
    )
    between = {label: _file_identity(path) for label, path in watched.items()}
    second = run_ndm1_rna_build(
        config=config,
        repo_root=REPO_ROOT,
        write_outputs=False,
        run_leakage=True,
    )
    after = {label: _file_identity(path) for label, path in watched.items()}
    assert first["report"] == second["report"]
    assert first["reconciliation"] == second["reconciliation"]
    assert first["output_hashes"] == {}
    assert second["output_hashes"] == {}
    for label in watched:
        for observed in (between[label], after[label]):
            assert observed["sha256"] == before[label]["sha256"], label
            assert observed["size"] == before[label]["size"], label
            assert observed["mtime_ns"] == before[label]["mtime_ns"], label


@pytest.mark.skipif(not _sources_ready(), reason="NDM-1 RNA source files are not present")
def test_live_build_classifications_provenance_and_leakage() -> None:
    config = _config()
    protected_before = snapshot_optional_paths(REPO_ROOT, PROTECTED)
    untouched_before = {
        rel: sha256_file(REPO_ROOT / rel) for rel in config["untouched_during_run"]
    }
    frozen_before = {
        name: sha256_file(REPO_ROOT / rel)
        for name, rel in {
            **{Path(path).name: path for path in config["frozen_partitions"].values()},
            **config["frozen_corpus"],
            "evaluation_references.csv": config["evaluation_references_path"],
            "evaluation_reference_manifest.csv": config["evaluation_reference_manifest_path"],
            "leakage_exclusion_set.csv": config["leakage_exclusion_set_path"],
            "corpus_manifest.json": config["s7d_manifest_path"],
        }.items()
    }
    result = run_ndm1_rna_build(config=config, repo_root=REPO_ROOT, write_outputs=True)
    references = result["references"]
    evidence = result["evidence"]
    assert [row["clone_id"] for row in references] == config["expected_clone_ids"]
    assert len({row["reference_id"] for row in references}) == 7
    assert len({row["legacy_s0b_reference_id"] for row in references}) == 7
    by_clone = {row["clone_id"]: row for row in references}
    assert by_clone["D902"]["qualitative_binding_status"] == "no_detectable_binding"
    for clone in ("D907", "D913", "D914"):
        assert by_clone[clone]["qualitative_binding_status"] == "weak_binding"
        assert "weak_binding" in by_clone[clone]["legacy_discrepancy_code"]
    assert by_clone["D909"]["qualitative_binding_status"] == "positive_strongest"
    assert by_clone["D918"]["qualitative_binding_status"] == "positive_secondary"
    assert by_clone["D920"]["qualitative_binding_status"] == "positive_secondary"
    for clone, row in by_clone.items():
        assert int(row["cleaned_length"]) == config["expected_cleaned_lengths"][clone]
        assert int(row["canonical_length"]) == int(row["cleaned_length"])
        assert int(row["trailing_gap_count"]) == config["expected_trailing_gap_counts"][clone]
        assert row["t_to_u_applied"] == "true"
        assert row["source_reported_alphabet"] == "DNA_T"
        assert row["molecule_type"] == "RNA"
        assert row["quantitative_affinity_reported"] == "false"
        assert row["affinity_value"] == ""
        assert row["affinity_type"] == ""
        assert row["flanks_inferred"] == "false"
        assert row["reverse_complement_inferred"] == "false"
        assert row["fixed_regions_included"] == "false"
        assert row["motifs_inferred"] == "false"
        assert row["truncations_included"] == "false"
        assert row["doped_selex_included"] == "false"
        assert row["include_in_sequence_comparison"] == "true"
        assert row["similarity_is_not_binding_proof"] == "true"
        assert row["cleaned_source_sha256"] == config["expected_cleaned_source_sha256"][clone]
        assert row["canonical_rna_sha256"] == config["expected_canonical_rna_sha256"][clone]
        assert row["reported_sha256"] == config["expected_reported_sha256"][clone]
        assert row["source_sha256"] == config["raw_sources"]["dissertation_pdf"]["sha256"]
        assert "Table 6" in row["source_table"]
        assert row["pdf_page"] == "42"
        assert row["dissertation_page"] == "36"
        reported = row["sequence_reported_raw"]
        cleaned = row["sequence_cleaned_source"]
        canonical = row["sequence_canonical_rna"]
        assert reported.endswith("-" * int(row["trailing_gap_count"]))
        assert "-" not in cleaned
        assert cleaned == reported.rstrip("-")
        assert canonical == cleaned.replace("T", "U")
        assert "U" not in cleaned
        assert "T" not in canonical
    assert all(row["canonical_equivalent_to_s0b"] == "true" for row in result["reconciliation"])
    assert len(result["reconciliation"]) == 7
    assert {row["proposed_disposition"] for row in references} == {
        "retain_existing_s0b_and_leakage_record_enrich_separately_do_not_duplicate"
    }
    assert len(evidence) == 8
    assert sum(row["evidence_class"] == "binding" for row in evidence) == 7
    inhibition = [row for row in evidence if row["evidence_class"] == "inhibition"]
    assert len(inhibition) == 1
    assert inhibition[0]["clone_id"] == "D909"
    assert inhibition[0]["quantitative_affinity_reported"] == "false"
    assert inhibition[0]["high_affinity_claim"] == "false"
    assert inhibition[0]["clinically_validated"] == "false"
    assert inhibition[0]["affinity_value"] == ""
    leakage = result["leakage"]
    assert leakage["any_exact"] is False
    assert leakage["any_identity_ge_threshold"] is False
    assert leakage["reverse_complement_matching"] is False
    for name in ("TRAIN", "VALIDATION", "REF", "EVAL", "CORPUS", "CORPUS_TXT"):
        assert leakage["by_partition"][name]["exact_matches"] == 0
        assert leakage["by_partition"][name]["identity_ge_threshold"] == 0
    assert "Documentation impact" in result["report"]
    assert "aptarank_full_mres_thesis_evaluation_plan.md" in result["report"]
    assert "aptarank-two-stage-evaluation-implementation-plan.md" in result["report"]
    assert "planned_evaluation_report.md" in result["report"]
    assert scan_text_for_sequence_leak(result["report"]) is False
    report_path = REPO_ROOT / "data/processed/ndm1_rna_reference_verification_report.md"
    manifest_path = REPO_ROOT / "data/processed/ndm1_rna_reference_manifest.json"
    assert scan_text_for_sequence_leak(report_path.read_text(encoding="utf-8")) is False
    assert scan_text_for_sequence_leak(manifest_path.read_text(encoding="utf-8")) is False
    frozen_after = {
        name: sha256_file(REPO_ROOT / rel)
        for name, rel in {
            **{Path(path).name: path for path in config["frozen_partitions"].values()},
            **config["frozen_corpus"],
            "evaluation_references.csv": config["evaluation_references_path"],
            "evaluation_reference_manifest.csv": config["evaluation_reference_manifest_path"],
            "leakage_exclusion_set.csv": config["leakage_exclusion_set_path"],
            "corpus_manifest.json": config["s7d_manifest_path"],
        }.items()
    }
    assert frozen_after == frozen_before
    assert snapshot_optional_paths(REPO_ROOT, PROTECTED) == protected_before
    assert {
        rel: sha256_file(REPO_ROOT / rel) for rel in config["untouched_during_run"]
    } == untouched_before
    assert result["registry"]["operational_status"] == "aligned"
    assert result["git_ls_files_data_empty"] is True
    s7d_manifest = json.loads((REPO_ROOT / config["s7d_manifest_path"]).read_text(encoding="utf-8"))
    assert s7d_manifest["source_registry_sha256"] == config["historical_s7d_source_registry_sha256"]
    assert (
        result["registry"]["operational_registry_sha256"]
        != s7d_manifest["source_registry_sha256"]
    )
    assert result["registry"]["tracked_sha256"] == config["raw_sources"]["table6_csv"]["sha256"]
    report = result["report"]
    assert "The S7D manifest records the source registry used when that frozen corpus was built." in report
    assert "path-only repair" in report
    assert "The D9 CSV content and SHA-256 are unchanged." in report
    assert "expected historical/current provenance distinction" in report
    assert "A future deliberate S7D rebuild would record the registry that is current at that time." in report
    assert "This verification does not rebuild or edit the frozen S7D manifest." in report
    assert "corpus inconsistency" not in report.lower()
    assert "unresolved sequence" not in report.lower()
    assert "Current hashes of those documents are not build inputs." in report
    assert "Its corpus hash is not an RNA contract and can be corrected later." in report
    written_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert written_manifest["protected_document_hashes_are_build_inputs"] is False
    assert written_manifest["untouched_during_run_hashes_are_permanent_pins"] is False


CLONE_SEQUENCES = {
    "D902": "ACGTACGTAC",
    "D907": "AAAA----",
    "D909": "ACGTACGTAA",
    "D913": "ACGTACGTAG",
    "D914": "ACGTACGTTA",
    "D918": "ACGTACGTT-",
    "D920": "ACGTACGTCA",
}
assert all(len(sequence) < 20 for sequence in CLONE_SEQUENCES.values())

REGISTRY_COLUMNS = (
    "source_key",
    "source_dataset",
    "path",
    "sha256",
    "n_rows_expected",
    "snapshot_date",
    "tier",
    "redistribution_status",
    "notes",
)


def _write_dict_csv(path: Path, fieldnames: tuple[str, ...] | list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _real_protected_identities() -> dict[str, dict[str, object]]:
    return {rel: _file_identity(REPO_ROOT / rel) for rel in PROTECTED}


def _synthetic_rows(config: dict) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    pdf_rows: list[dict[str, str]] = []
    csv_rows: list[dict[str, str]] = []
    reported_lengths: dict[str, int] = {}
    cleaned_lengths: dict[str, int] = {}
    gap_counts: dict[str, int] = {}
    reported_hashes: dict[str, str] = {}
    cleaned_hashes: dict[str, str] = {}
    canonical_hashes: dict[str, str] = {}
    for clone in config["expected_clone_ids"]:
        reported = CLONE_SEQUENCES[clone]
        cleaned = reported.rstrip("-")
        canonical = cleaned.replace("T", "U")
        pdf_rows.append(
            {
                "clone_id": clone,
                "sequence_reported": reported,
                "purine_percent_reported": "50%",
                "gc_percent_reported": "50%",
            }
        )
        csv_rows.append(
            {
                "clone_id": clone,
                "sequence_reported": reported,
                "sequence_cleaned": cleaned,
                "purine_percent_reported": "50%",
                "gc_percent_reported": "50%",
            }
        )
        reported_lengths[clone] = len(reported)
        cleaned_lengths[clone] = len(cleaned)
        gap_counts[clone] = len(reported) - len(cleaned)
        reported_hashes[clone] = sha256_text(reported)
        cleaned_hashes[clone] = sha256_text(cleaned)
        canonical_hashes[clone] = sha256_text(canonical)
    config["expected_reported_lengths"] = reported_lengths
    config["expected_cleaned_lengths"] = cleaned_lengths
    config["expected_trailing_gap_counts"] = gap_counts
    config["expected_reported_sha256"] = reported_hashes
    config["expected_cleaned_source_sha256"] = cleaned_hashes
    config["expected_canonical_rna_sha256"] = canonical_hashes
    return pdf_rows, csv_rows


def _isolated_repo(tmp_path: Path) -> tuple[Path, dict, list[dict[str, str]], list[dict[str, str]]]:
    root = tmp_path
    config = _config()
    config.pop("expected_protected_untracked_sha256", None)
    config.pop("immutable_tracked_authorities", None)
    config["untouched_during_run"] = ["config/untouched_marker.txt"]
    config["historical_s7d_source_registry_sha256"] = "0123456789abcdef" * 4
    pdf_rows, csv_rows = _synthetic_rows(config)
    for key, payload in (
        ("dissertation_pdf", b"synthetic-pdf"),
        ("data_xlsx", b"synthetic-xlsx"),
        ("readme_rtf", b"synthetic-rtf"),
    ):
        path = root / config["raw_sources"][key]["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        config["raw_sources"][key]["sha256"] = sha256_file(path)
    table_path = root / config["raw_sources"]["table6_csv"]["path"]
    _write_dict_csv(
        table_path,
        (
            "clone_id",
            "sequence_reported",
            "sequence_cleaned",
            "purine_percent_reported",
            "gc_percent_reported",
        ),
        csv_rows,
    )
    config["raw_sources"]["table6_csv"]["sha256"] = sha256_file(table_path)
    registry_row = {
        "source_key": config["registered_source_key"],
        "source_dataset": "fixture_d9",
        "path": config["registered_csv_path"],
        "sha256": config["raw_sources"]["table6_csv"]["sha256"],
        "n_rows_expected": "7",
        "snapshot_date": "2026-09-27",
        "tier": "eval",
        "redistribution_status": "unknown",
        "notes": "fixture",
    }
    extra_row = {
        "source_key": "fixture_marker",
        "source_dataset": "fixture_marker_dataset",
        "path": config["raw_sources"]["readme_rtf"]["path"],
        "sha256": "b" * 64,
        "n_rows_expected": "1",
        "snapshot_date": "2026-09-27",
        "tier": "eval",
        "redistribution_status": "unknown",
        "notes": "extra row so the operational registry hash differs",
    }
    _write_dict_csv(root / config["source_registry_path"], REGISTRY_COLUMNS, [registry_row])
    _write_dict_csv(
        root / config["operational_registry_path"],
        REGISTRY_COLUMNS,
        [registry_row, extra_row],
    )
    for rel in (
        *config["frozen_partitions"].values(),
        *config["frozen_corpus"].values(),
        config["evaluation_references_path"],
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("record_id,sequence_full\n" if not str(rel).endswith(".txt") else "\n", encoding="utf-8")
    manifest_rows = []
    leakage_rows = []
    for pdf_row in pdf_rows:
        clone = pdf_row["clone_id"]
        spec = config["clones"][clone]
        reported = pdf_row["sequence_reported"]
        cleaned = reported.rstrip("-")
        canonical = cleaned.replace("T", "U")
        manifest_rows.append(
            {
                "reference_id": spec["legacy_s0b_reference_id"],
                "aptamer_name": clone,
                "evaluation_label": spec["legacy_evaluation_label"],
                "exclusion_id": spec["legacy_exclusion_id"],
                "include_in_sequence_leakage": "true",
            }
        )
        leakage_rows.append(
            {
                "reference_id": spec["legacy_s0b_reference_id"],
                "source_key": config["registered_source_key"],
                "aptamer_name": clone,
                "evaluation_label": spec["legacy_evaluation_label"],
                "evaluation_role": spec["legacy_evaluation_role"],
                "exclusion_id": spec["legacy_exclusion_id"],
                "sequence_raw": reported,
                "sequence_full": canonical,
                "sequence_core": canonical,
                "sequence_compare_full": cleaned,
                "t_to_u_applied": "true",
                "molecule_type": "RNA",
                "alphabet_as_reported": "DNA_T",
            }
        )
    _write_dict_csv(
        root / config["evaluation_reference_manifest_path"],
        (
            "reference_id",
            "aptamer_name",
            "evaluation_label",
            "exclusion_id",
            "include_in_sequence_leakage",
        ),
        manifest_rows,
    )
    _write_dict_csv(
        root / config["leakage_exclusion_set_path"],
        (
            "reference_id",
            "source_key",
            "aptamer_name",
            "evaluation_label",
            "evaluation_role",
            "exclusion_id",
            "sequence_raw",
            "sequence_full",
            "sequence_core",
            "sequence_compare_full",
            "t_to_u_applied",
            "molecule_type",
            "alphabet_as_reported",
        ),
        leakage_rows,
    )
    s7d_path = root / config["s7d_manifest_path"]
    s7d_path.parent.mkdir(parents=True, exist_ok=True)
    s7d_path.write_text(
        json.dumps({"source_registry_sha256": config["historical_s7d_source_registry_sha256"]}) + "\n",
        encoding="utf-8",
    )
    marker = root / "config/untouched_marker.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("do-not-edit\n", encoding="utf-8")
    return root, config, pdf_rows, csv_rows


def _run_isolated(root: Path, config: dict, pdf_rows: list[dict[str, str]], csv_rows: list[dict[str, str]], **kwargs):
    return run_ndm1_rna_build(
        config=config,
        repo_root=root,
        write_outputs=kwargs.get("write_outputs", True),
        run_leakage=True,
        enforce_frozen_hashes=False,
        pdf_rows=pdf_rows,
        csv_rows=csv_rows,
        partitions={name: [] for name in ("TRAIN", "VALIDATION", "REF", "EVAL", "CORPUS")},
        corpus_lines=[],
        skip_primary_text_checks=True,
    )


def test_protected_document_hashes_are_not_build_inputs(tmp_path: Path) -> None:
    with pytest.raises(Ndm1RnaError, match="permanent build inputs"):
        run_ndm1_rna_build(
            config={
                "expected_protected_untracked_sha256": {
                    "docs/planned_evaluation_report.md": "ab"
                }
            },
            repo_root=tmp_path,
            write_outputs=False,
        )


def test_cross_pipeline_hash_pins_are_not_accepted(tmp_path: Path) -> None:
    with pytest.raises(Ndm1RnaError, match="untouched_during_run"):
        run_ndm1_rna_build(
            config={
                "immutable_tracked_authorities": {
                    "config/ndm1_ssdna_reference_build.json": "ab"
                }
            },
            repo_root=tmp_path,
            write_outputs=False,
        )


def test_builder_runs_when_protected_documents_are_absent(tmp_path: Path) -> None:
    root, config, pdf_rows, csv_rows = _isolated_repo(tmp_path)
    for rel in config["protected_untracked_files"]:
        assert not (root / rel).exists()
    real_before = _real_protected_identities()
    result = _run_isolated(root, config, pdf_rows, csv_rows, write_outputs=True)
    assert result["ok"] is True
    assert result["counts"]["reference_records"] == 7
    assert result["protected_untracked_snapshot"] == {
        rel: ABSENT_FILE for rel in config["protected_untracked_files"]
    }
    assert result["registry"]["operational_status"] == "aligned"
    assert (
        result["registry"]["operational_registry_sha256"]
        != result["registry"]["s7d_recorded_source_registry_sha256"]
    )
    assert "expected historical/current provenance distinction" in result["report"]
    assert "path-only repair" in result["report"]
    assert (root / "data/processed/ndm1_rna_reference_verification_report.md").is_file()
    assert _real_protected_identities() == real_before


def test_protected_file_change_during_build_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, config, pdf_rows, csv_rows = _isolated_repo(tmp_path)
    rel = config["protected_untracked_files"][0]
    protected = root / rel
    protected.parent.mkdir(parents=True, exist_ok=True)
    protected.write_text("stable\n", encoding="utf-8")
    real_before = _real_protected_identities()
    original = ndm1_rna.render_report

    def _change_during_build(payload: dict) -> str:
        protected.write_text("changed during build\n", encoding="utf-8")
        return original(payload)

    monkeypatch.setattr(ndm1_rna, "render_report", _change_during_build)
    with pytest.raises(Ndm1RnaError, match="protected untracked files changed during the build"):
        _run_isolated(root, config, pdf_rows, csv_rows, write_outputs=False)
    assert _real_protected_identities() == real_before

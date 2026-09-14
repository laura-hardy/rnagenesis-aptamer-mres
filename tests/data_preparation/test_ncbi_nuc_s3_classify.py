"""Tests for the NCBI Nucleotide S3 classification runner (synthetic only).

Does not read real NCBI source sequences except an optional local skipif
production gate that asserts counts without embedding sequences.
"""

from __future__ import annotations

import csv
import io
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.ncbi_nuc import SIDECAR_COLUMNS  # noqa: E402
from adapters.ncbi_nuc_s2 import S2_QC_COLUMNS  # noqa: E402
from adapters.ncbi_nuc_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE,
    PRIMARY_ROUTE_REJECT,
    REJECTION_COLUMNS,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S3_FORBIDDEN_FIELDS,
    empty_corpus_record,
)
from s3_classify import main, run_ncbi_nuc_s3, run_s3_classification  # noqa: E402

POLICY_PATH = REPO_ROOT / "config" / "source_eligibility" / "ncbi_nuc.json"
PRODUCTION_S2 = REPO_ROOT / "data" / "interim" / "normalised" / "ncbi_nuc_normalised.csv"
SYNTHETIC_RNA_36 = "ACGU" * 9
SYNTHETIC_RNA_99 = "ACGU" * 24 + "ACG"
SYNTHETIC_DNA_36 = "ACGT" * 9
SYNTHETIC_N_12 = "ACGT" * 2 + "ACGN"
SYNTHETIC_POLY_A = "A" * 11
SYNTHETIC_DNA_170 = "ACGT" * 42 + "AC"


def _s2_row(
    *,
    native_id: str,
    sequence: str,
    molecule_type: str,
    chemistry: str,
    alphabet: str,
    qc_flags: str = "",
    construct_scope: str = "unknown",
    t_to_u_applied: str = "false",
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"ncbi_nuc:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": construct_scope,
            "trim_status": "no_constants_detected",
            "trim_confidence": "n/a",
            "molecule_type": molecule_type,
            "alphabet_as_reported": alphabet,
            "t_to_u_applied": t_to_u_applied,
            "chemistry": chemistry,
            "target_name_raw": "",
            "source_db": "ncbi_nuc",
            "source_dataset": "ncbi_nuc_genbank_2026-07-27",
            "contributing_sources": "ncbi_nuc",
            "contributing_datasets": "ncbi_nuc_genbank_2026-07-27",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "qc_flags": qc_flags,
        }
    )
    return record


def _qc_row(
    canonical: dict[str, str],
    *,
    primer: bool = False,
    poly_a: bool = False,
    method_object: bool = False,
    cdna: bool = False,
    template: bool = False,
) -> dict[str, str]:
    row = {column: "" for column in S2_QC_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "target_name_raw": canonical["target_name_raw"],
            "alphabet_as_reported": canonical["alphabet_as_reported"],
            "molecule_type": canonical["molecule_type"],
            "chemistry": canonical["chemistry"],
            "t_to_u_applied": canonical["t_to_u_applied"],
            "sequence_length_full": canonical["sequence_length_full"],
            "sequence_length_core": canonical["sequence_length_core"],
            "construct_scope": canonical["construct_scope"],
            "trim_status": canonical["trim_status"],
            "trim_confidence": canonical["trim_confidence"],
            "qc_flags": canonical["qc_flags"],
            "primer_associated": "true" if primer else "false",
            "cdna_template_associated": "true" if cdna else "false",
            "transcription_template": "true" if template else "false",
            "poly_a_fragment": "true" if poly_a else "false",
            "possible_non_aptamer_source_object": "true" if method_object else "false",
            "construct_requires_review": (
                "true" if primer or poly_a or cdna or template else "false"
            ),
            "group_consensus_proposal": "false",
        }
    )
    if primer:
        row["source_object_class"] = "primer_associated"
    elif poly_a:
        row["source_object_class"] = "poly_a_fragment"
    elif method_object:
        row["source_object_class"] = "possible_non_aptamer_method_object"
    elif cdna:
        row["source_object_class"] = "cdna_template_associated"
    elif template:
        row["source_object_class"] = "transcription_template"
    return row


def _meta_row(canonical: dict[str, str]) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "ncbi_nuc_accession": canonical["native_id"],
        }
    )
    return row


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _make_tree(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repo_root = tmp_path / "repo"
    (repo_root / "config" / "source_eligibility").mkdir(parents=True)
    shutil.copy(POLICY_PATH, repo_root / "config" / "source_eligibility" / "ncbi_nuc.json")
    input_dir = repo_root / "data" / "interim" / "normalised"
    metadata_dir = repo_root / "data" / "interim" / "extracted"
    output_dir = repo_root / "data" / "interim" / "checkpoints" / "ncbi_nuc_cp1"
    input_dir.mkdir(parents=True)
    metadata_dir.mkdir(parents=True)
    return repo_root, input_dir, metadata_dir, output_dir


def _write_source(
    input_dir: Path,
    metadata_dir: Path,
    specs: list[dict[str, object]],
) -> None:
    canonical_rows = []
    qc_rows = []
    meta_rows = []
    for spec in specs:
        canonical = _s2_row(
            native_id=str(spec["native_id"]),
            sequence=str(spec["sequence"]),
            molecule_type=str(spec["molecule_type"]),
            chemistry=str(spec["chemistry"]),
            alphabet=str(spec["alphabet"]),
            qc_flags=str(spec.get("qc_flags", "")),
            construct_scope=str(spec.get("construct_scope", "unknown")),
            t_to_u_applied=str(spec.get("t_to_u_applied", "false")),
        )
        canonical_rows.append(canonical)
        qc_rows.append(
            _qc_row(
                canonical,
                primer=bool(spec.get("primer")),
                poly_a=bool(spec.get("poly_a")),
                method_object=bool(spec.get("method_object")),
                cdna=bool(spec.get("cdna")),
                template=bool(spec.get("template")),
            )
        )
        meta_rows.append(_meta_row(canonical))
    _write_csv(input_dir / "ncbi_nuc_normalised.csv", list(CORPUS_COLUMNS), canonical_rows)
    _write_csv(input_dir / "ncbi_nuc_s2_qc.csv", list(S2_QC_COLUMNS), qc_rows)
    _write_csv(
        metadata_dir / "ncbi_nuc_source_metadata.csv",
        list(SIDECAR_COLUMNS),
        meta_rows,
    )


def test_runner_reconciles_one_primary_route_per_row(tmp_path: Path) -> None:
    repo_root, input_dir, metadata_dir, output_dir = _make_tree(tmp_path)
    _write_source(
        input_dir,
        metadata_dir,
        [
            {
                "native_id": "RNA36",
                "sequence": SYNTHETIC_RNA_36,
                "molecule_type": "RNA",
                "chemistry": "RNA",
                "alphabet": "RNA",
                "t_to_u_applied": "true",
            },
            {
                "native_id": "RNA99",
                "sequence": SYNTHETIC_RNA_99,
                "molecule_type": "RNA",
                "chemistry": "RNA",
                "alphabet": "RNA",
                "t_to_u_applied": "true",
            },
            {
                "native_id": "UNK36",
                "sequence": SYNTHETIC_DNA_36,
                "molecule_type": "unknown",
                "chemistry": "unknown",
                "alphabet": "DNA_T",
                "qc_flags": "molecule_type_unknown",
            },
            {
                "native_id": "UNKN",
                "sequence": SYNTHETIC_N_12,
                "molecule_type": "unknown",
                "chemistry": "unknown",
                "alphabet": "ambiguous",
                "qc_flags": "molecule_type_unknown|ambiguous_base",
            },
            {
                "native_id": "PRIMER",
                "sequence": SYNTHETIC_DNA_36,
                "molecule_type": "unknown",
                "chemistry": "unknown",
                "alphabet": "DNA_T",
                "qc_flags": "molecule_type_unknown|primer_associated",
                "construct_scope": "partial_construct",
                "primer": True,
            },
            {
                "native_id": "POLYA",
                "sequence": SYNTHETIC_POLY_A,
                "molecule_type": "unknown",
                "chemistry": "unknown",
                "alphabet": "RNA",
                "qc_flags": "molecule_type_unknown|poly_a_fragment",
                "construct_scope": "partial_construct",
                "poly_a": True,
            },
            {
                "native_id": "METHODDNA",
                "sequence": SYNTHETIC_DNA_170,
                "molecule_type": "DNA",
                "chemistry": "DNA",
                "alphabet": "DNA_T",
                "qc_flags": "possible_non_aptamer_source_object",
                "method_object": True,
            },
            {
                "native_id": "TEMPLATE",
                "sequence": SYNTHETIC_DNA_36,
                "molecule_type": "unknown",
                "chemistry": "unknown",
                "alphabet": "DNA_T",
                "qc_flags": "molecule_type_unknown|transcription_template",
                "construct_scope": "full_construct",
                "template": True,
            },
            {
                "native_id": "CDNA",
                "sequence": SYNTHETIC_DNA_36,
                "molecule_type": "unknown",
                "chemistry": "unknown",
                "alphabet": "DNA_T",
                "qc_flags": "molecule_type_unknown|cdna_template_associated",
                "cdna": True,
            },
        ],
    )
    result = run_ncbi_nuc_s3(
        repo_root=repo_root,
        input_dir=input_dir,
        source_metadata_dir=metadata_dir,
        eligibility_policy=repo_root / "config" / "source_eligibility" / "ncbi_nuc.json",
        output_dir=output_dir,
        expected_rows=9,
        check_deterministic_rerun=True,
    )
    stats = result.stats
    assert stats.s3_rows == 9
    assert stats.decision_counts["proposed_accept"] == 2
    assert stats.decision_counts["proposed_park"] == 4
    assert stats.decision_counts["proposed_reject"] == 3
    assert (
        stats.decision_counts["proposed_accept"]
        + stats.decision_counts["proposed_park"]
        + stats.decision_counts["proposed_reject"]
        == 9
    )
    assert stats.primary_route_counts[PRIMARY_ROUTE_ELIGIBLE] == 2
    assert stats.primary_route_counts[PRIMARY_ROUTE_MOLECULE] == 4
    assert stats.primary_route_counts[PRIMARY_ROUTE_REJECT] == 3
    assert stats.applied_trims == 0
    assert stats.core_equals_full == 9
    assert stats.nonempty_target_name_raw == 0
    assert stats.nonempty_s4_fields == 0
    assert stats.random_accept_audit_pool_size == 2
    assert stats.random_accept_audit_count == 2
    assert stats.random_accept_audit_shortfall == 28
    assert result.deterministic_rerun_ok is True
    assert result.s2_integrity_ok is True

    decisions = list(csv.DictReader(result.output_decisions.open(encoding="utf-8")))
    rejects = list(csv.DictReader(result.output_rejected.open(encoding="utf-8")))
    parks = list(csv.DictReader(result.output_parks.open(encoding="utf-8")))
    assert len(decisions) == 9
    assert len(rejects) == 3
    assert len(parks) == 4
    by_id = {row["record_id"]: row for row in decisions}
    assert by_id["ncbi_nuc:RNA36"]["primary_reason"] == "technically_eligible_rna"
    assert by_id["ncbi_nuc:RNA99"]["review_batch"] == "04_length_boundary"
    assert by_id["ncbi_nuc:UNK36"]["primary_reason"] == "molecule_type_unresolved"
    assert by_id["ncbi_nuc:UNKN"]["primary_reason"] == "molecule_type_unresolved"
    assert "ambiguous_bases" in by_id["ncbi_nuc:UNKN"]["secondary_reasons"]
    assert by_id["ncbi_nuc:PRIMER"]["primary_reason"] == "primer_like"
    assert by_id["ncbi_nuc:POLYA"]["primary_reason"] == "non_aptamer_source_object"
    assert by_id["ncbi_nuc:POLYA"]["molecule_type"] == "unknown"
    assert by_id["ncbi_nuc:METHODDNA"]["primary_reason"] == "non_aptamer_source_object"
    assert by_id["ncbi_nuc:METHODDNA"]["molecule_type"] == "DNA"
    assert by_id["ncbi_nuc:TEMPLATE"]["primary_reason"] == "molecule_type_unresolved"
    assert by_id["ncbi_nuc:CDNA"]["primary_reason"] == "molecule_type_unresolved"
    reject_reasons = {row["rejection_reason"] for row in rejects}
    assert reject_reasons == {"primer_like", "non_aptamer_source_object"}
    local = list(csv.DictReader(result.output_local_detail.open(encoding="utf-8")))
    for row in local:
        assert row["manual_decision"] == ""
        assert row["sequence_core"] == row["sequence_full"]
        for field in S3_FORBIDDEN_FIELDS:
            assert row.get(field, "") == ""
    review = list(csv.DictReader(result.output_review.open(encoding="utf-8")))
    assert list(review[0].keys()) == list(DECISION_COLUMNS)
    assert "sequence_raw" not in DECISION_COLUMNS
    assert "sequence_raw" not in PARK_COLUMNS
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "authorised_for_s4" in summary.lower() or "authorised for S4" in summary
    assert "ACGU" not in summary


def test_cli_dispatch_writes_ncbi_checkpoint(tmp_path: Path) -> None:
    repo_root, input_dir, metadata_dir, output_dir = _make_tree(tmp_path)
    _write_source(
        input_dir,
        metadata_dir,
        [
            {
                "native_id": "RNA36",
                "sequence": SYNTHETIC_RNA_36,
                "molecule_type": "RNA",
                "chemistry": "RNA",
                "alphabet": "RNA",
                "t_to_u_applied": "true",
            }
        ],
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "ncbi_nuc",
                "--repo-root",
                str(repo_root),
                "--input-dir",
                str(input_dir),
                "--source-metadata-dir",
                str(metadata_dir),
                "--eligibility-policy",
                str(repo_root / "config" / "source_eligibility" / "ncbi_nuc.json"),
                "--output-dir",
                str(output_dir),
                "--expected-rows",
                "1",
            ]
        )
    assert code == 0
    assert "source=ncbi_nuc" in stdout.getvalue()
    assert (output_dir / "ncbi_nuc_s3_canonical.csv").is_file()
    assert (output_dir / "rejected_ncbi_nuc.csv").is_file()


def test_run_s3_classification_dispatch(tmp_path: Path) -> None:
    repo_root, input_dir, metadata_dir, output_dir = _make_tree(tmp_path)
    _write_source(
        input_dir,
        metadata_dir,
        [
            {
                "native_id": "UNK36",
                "sequence": SYNTHETIC_DNA_36,
                "molecule_type": "unknown",
                "chemistry": "unknown",
                "alphabet": "DNA_T",
                "qc_flags": "molecule_type_unknown",
            }
        ],
    )
    result = run_s3_classification(
        repo_root=repo_root,
        source_key="ncbi_nuc",
        input_dir=input_dir,
        source_metadata_dir=metadata_dir,
        leakage_set=repo_root / "unused.csv",
        target_aliases=repo_root / "unused.csv",
        eligibility_policy=repo_root / "config" / "source_eligibility" / "ncbi_nuc.json",
        output_dir=output_dir,
        expected_rows=1,
    )
    assert result.source_key == "ncbi_nuc"
    assert result.stats.decision_counts["proposed_park"] == 1


def test_header_only_proposals_file_is_empty_not_fatal(tmp_path: Path) -> None:
    repo_root, input_dir, metadata_dir, output_dir = _make_tree(tmp_path)
    _write_source(
        input_dir,
        metadata_dir,
        [
            {
                "native_id": "RNA36",
                "sequence": SYNTHETIC_RNA_36,
                "molecule_type": "RNA",
                "chemistry": "RNA",
                "alphabet": "RNA",
                "t_to_u_applied": "true",
            }
        ],
    )
    proposals = input_dir / "detected_constants_ncbi_nuc.csv"
    proposals.write_text(
        "proposal_id,experiment_group_id,proposal_source,side,proposed_sequence,"
        "motif_id,motif_length,support,records_considered,records_matching_exactly,"
        "confidence,status,applied,reason_not_applied,reason\n",
        encoding="utf-8",
    )
    result = run_ncbi_nuc_s3(
        repo_root=repo_root,
        input_dir=input_dir,
        source_metadata_dir=metadata_dir,
        eligibility_policy=repo_root / "config" / "source_eligibility" / "ncbi_nuc.json",
        output_dir=output_dir,
        expected_rows=1,
    )
    assert result.stats.s3_rows == 1
    assert result.stats.known_motif_proposal_count == 0
    assert result.stats.applied_trims == 0


@pytest.mark.skipif(
    not PRODUCTION_S2.is_file(),
    reason="Registered NCBI Nucleotide S2 file not present locally",
)
def test_production_s2_row_count_without_embedding_sequences() -> None:
    rows = list(csv.DictReader(PRODUCTION_S2.open(encoding="utf-8")))
    assert len(rows) == 18
    assert all(row["sequence_core"] == row["sequence_full"] for row in rows)
    assert all(row["target_name_raw"] == "" for row in rows)
    assert sum(1 for row in rows if row["molecule_type"] == "RNA") == 5
    assert sum(1 for row in rows if row["molecule_type"] == "DNA") == 1
    assert sum(1 for row in rows if row["molecule_type"] == "unknown") == 12

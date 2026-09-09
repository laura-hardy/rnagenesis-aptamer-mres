"""Tests for the AptamerBase S3 classification runner (synthetic fixtures only).

Literal nucleotides are repeating ACGU/ACGT tiles built at runtime.
Does not embed real AptamerBase sequences. Optional local production
skipif gates assert counts and hashes without writing sequences here.
"""

from __future__ import annotations

import csv
import hashlib
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

from adapters.aptamerbase import (  # noqa: E402
    SIDECAR_COLUMNS,
    TYPE_APTAMER,
    TYPE_PREDICTED_STRUCTURE,
    TYPE_SECONDARY_STRUCTURE,
)
from adapters.aptamerbase_s2 import CONSTANT_PROPOSAL_COLUMNS, S2_QC_COLUMNS  # noqa: E402
from adapters.aptamerbase_s3 import (  # noqa: E402
    PLAN_REJECTION_REASONS,
    PRIMARY_ROUTE_CHEMISTRY_REVIEW,
    PRIMARY_ROUTE_CONSTRUCT,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S3_FORBIDDEN_FIELDS,
    empty_corpus_record,
)
from s3_classify import (  # noqa: E402
    EXPECTED_APTAMERBASE_S2_HASH,
    main,
    run_aptamerbase_s3,
    run_s3_classification,
)

POLICY_PATH = REPO_ROOT / "config" / "source_eligibility" / "aptamerbase.json"
PRODUCTION_S2 = (
    REPO_ROOT / "data" / "interim" / "normalised" / "aptamerbase_normalised.csv"
)
PRODUCTION_QC = REPO_ROOT / "data" / "interim" / "normalised" / "aptamerbase_s2_qc.csv"
PRODUCTION_PROPOSALS = (
    REPO_ROOT / "data" / "interim" / "normalised" / "detected_constants_aptamerbase.csv"
)
PRODUCTION_SIDECAR = (
    REPO_ROOT / "data" / "interim" / "extracted" / "aptamerbase_source_metadata.csv"
)
PRODUCTION_RAW = (
    REPO_ROOT / "data" / "raw" / "aptamerbase" / "aptamerbase_aptamers.csv"
)
PRODUCTION_RDF = (
    REPO_ROOT
    / "data"
    / "raw"
    / "aptamerbase"
    / "aptamerbase.freebase.extract.nt.gz"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _dna(n: int) -> str:
    return ("ACGT" * ((n // 4) + 1))[:n]


def _s2_row(
    native_id: str,
    sequence: str,
    *,
    molecule_type: str = "RNA",
    chemistry: str = "RNA",
    alphabet: str = "RNA",
    qc_flags: str = "",
    trim_status: str = "no_constants_detected",
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"aptamerbase:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "unknown",
            "trim_status": "not_applicable" if sequence == "" else trim_status,
            "trim_confidence": "n/a",
            "molecule_type": molecule_type if sequence else "unknown",
            "alphabet_as_reported": alphabet if sequence else "missing",
            "t_to_u_applied": "false",
            "chemistry": chemistry if sequence else "unknown",
            "target_name_raw": "",
            "source_db": "aptamerbase",
            "source_dataset": "aptamerbase_export_2026-06-24",
            "contributing_sources": "aptamerbase",
            "contributing_datasets": "aptamerbase_export_2026-06-24",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "publication": "Demo",
            "qc_flags": qc_flags,
        }
    )
    return record


def _qc_row(
    canonical: dict[str, str],
    *,
    source_object_type: str = "aptamer",
    chemistry_class: str = "unmodified_backbone",
    rdf_has_rna: str = "true",
    rdf_has_dna: str = "false",
) -> dict[str, str]:
    row = {column: "" for column in S2_QC_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "aptamerbase_id": canonical["native_id"],
            "source_object_type": source_object_type,
            "alphabet_as_reported": canonical["alphabet_as_reported"],
            "molecule_type": canonical["molecule_type"],
            "chemistry": canonical["chemistry"],
            "chemistry_class": chemistry_class,
            "t_to_u_applied": canonical["t_to_u_applied"],
            "sequence_length_full": canonical["sequence_length_full"],
            "sequence_length_core": canonical["sequence_length_core"],
            "construct_scope": canonical["construct_scope"],
            "trim_status": canonical["trim_status"],
            "trim_confidence": canonical["trim_confidence"],
            "qc_flags": canonical["qc_flags"],
            "rdf_has_rna": rdf_has_rna,
            "rdf_has_dna": rdf_has_dna,
        }
    )
    return row


def _meta_row(
    canonical: dict[str, str],
    *,
    aptamerbase_type: str = TYPE_APTAMER,
    aptamerbase_id: str | None = None,
) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "aptamerbase_type": aptamerbase_type,
            "aptamerbase_id": aptamerbase_id or canonical["native_id"],
            "aptamerbase_label": f"label-{canonical['native_id']}",
        }
    )
    return row


def _write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
    *,
    quote_all: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    quoting = csv.QUOTE_ALL if quote_all else csv.QUOTE_MINIMAL
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            lineterminator="\n",
            quoting=quoting,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _make_tree(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    input_dir = repo_root / "data" / "interim" / "normalised"
    meta_dir = repo_root / "data" / "interim" / "extracted"
    output_dir = repo_root / "data" / "interim" / "checkpoints" / "aptamerbase_cp1"
    input_dir.mkdir(parents=True)
    meta_dir.mkdir(parents=True)
    return repo_root, input_dir, meta_dir, output_dir


def _seed(
    input_dir: Path,
    meta_dir: Path,
    items: list[tuple[dict[str, str], dict[str, str], dict[str, str]]],
    *,
    proposals: list[dict[str, str]] | None = None,
) -> None:
    canonical_rows = [item[0] for item in items]
    qc_rows = [item[1] for item in items]
    meta_rows = [item[2] for item in items]
    _write_csv(
        input_dir / "aptamerbase_normalised.csv",
        list(CORPUS_COLUMNS),
        canonical_rows,
    )
    _write_csv(input_dir / "aptamerbase_s2_qc.csv", list(S2_QC_COLUMNS), qc_rows)
    _write_csv(
        meta_dir / "aptamerbase_source_metadata.csv",
        list(SIDECAR_COLUMNS),
        meta_rows,
        quote_all=True,
    )
    _write_csv(
        input_dir / "detected_constants_aptamerbase.csv",
        list(CONSTANT_PROPOSAL_COLUMNS),
        proposals or [],
    )


def _bundle(
    canonical: dict[str, str],
    *,
    source_object_type: str = "aptamer",
    aptamerbase_type: str = TYPE_APTAMER,
    chemistry_class: str = "unmodified_backbone",
    rdf_has_rna: str = "true",
    rdf_has_dna: str = "false",
    aptamerbase_id: str | None = None,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    return (
        canonical,
        _qc_row(
            canonical,
            source_object_type=source_object_type,
            chemistry_class=chemistry_class,
            rdf_has_rna=rdf_has_rna,
            rdf_has_dna=rdf_has_dna,
        ),
        _meta_row(
            canonical,
            aptamerbase_type=aptamerbase_type,
            aptamerbase_id=aptamerbase_id,
        ),
    )


def test_s3_dispatch_recognises_aptamerbase(tmp_path: Path) -> None:
    repo_root, input_dir, meta_dir, output_dir = _make_tree(tmp_path)
    rna = _s2_row("0001", _rna(40))
    _seed(input_dir, meta_dir, [_bundle(rna)])
    result = run_s3_classification(
        repo_root=repo_root,
        source_key="aptamerbase",
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=repo_root / "unused_leakage.csv",
        target_aliases=repo_root / "unused_aliases.csv",
        eligibility_policy=POLICY_PATH,
        output_dir=output_dir,
        expected_rows=1,
    )
    assert result.source_key == "aptamerbase"
    assert result.stats.s3_rows == 1


def test_no_silent_row_disappearance_and_reconciliation(tmp_path: Path) -> None:
    repo_root, input_dir, meta_dir, output_dir = _make_tree(tmp_path)
    shared_id = "m.shared"
    items = [
        _bundle(_s2_row("0001", _rna(40))),
        _bundle(_s2_row("0002", "", qc_flags="missing_sequence")),
        _bundle(
            _s2_row(
                "0003",
                _dna(40),
                molecule_type="ssDNA",
                chemistry="DNA",
                alphabet="DNA_T",
            ),
            rdf_has_rna="false",
            rdf_has_dna="true",
        ),
        _bundle(
            _s2_row("0004", _rna(40), chemistry="2F-RNA"),
            chemistry_class="twof_rna",
        ),
        _bundle(_s2_row("0005", _rna(19))),
        _bundle(
            _s2_row("0006", _rna(40), molecule_type="unknown", chemistry="unknown"),
            rdf_has_rna="false",
            chemistry_class="",
        ),
        _bundle(_s2_row("0007", _rna(101))),
        _bundle(
            _s2_row(
                "0008",
                _rna(20) + "X" + _rna(19),
                alphabet="invalid",
                qc_flags="invalid_character",
            ),
        ),
        _bundle(
            _s2_row(
                "0009",
                _rna(40),
                molecule_type="ssDNA",
                chemistry="DNA",
                alphabet="RNA",
                qc_flags="source_molecule_alphabet_conflict",
            ),
            rdf_has_rna="false",
            rdf_has_dna="true",
        ),
        _bundle(
            _s2_row(
                "0010",
                _rna(40),
                chemistry="unknown",
                qc_flags="spiegelmer_l_rna_review",
            ),
            chemistry_class="spiegelmer_l_rna",
        ),
        _bundle(
            _s2_row(
                "0011",
                _rna(40),
                molecule_type="unknown",
                chemistry="unknown",
                qc_flags="non_aptamer_structure_topic",
            ),
            source_object_type="nucleic_acid_secondary_structure",
            aptamerbase_type=TYPE_SECONDARY_STRUCTURE,
            rdf_has_rna="false",
            chemistry_class="",
        ),
        _bundle(
            _s2_row("0012", _rna(40), molecule_type="RNA"),
            source_object_type="predicted_secondary_structure",
            aptamerbase_type=TYPE_PREDICTED_STRUCTURE,
        ),
        _bundle(_s2_row("0013", _rna(22))),
        _bundle(_s2_row("0014", _rna(95))),
        _bundle(_s2_row("0015", _rna(40)), aptamerbase_id=shared_id),
        _bundle(_s2_row("0016", _rna(41)), aptamerbase_id=shared_id),
        _bundle(_s2_row("0017", _rna(40))),
        _bundle(
            _s2_row(
                "0018",
                _rna(40) + "T",
                alphabet="mixed_T_U",
                qc_flags="mixed_t_u",
            ),
        ),
    ]
    motif_id = "aptamerbase:0017"
    proposals = [
        {
            "proposal_id": f"{motif_id}:known_motif:five_prime:t7_promoter_minimal",
            "experiment_group_id": motif_id,
            "proposal_source": "known_motif",
            "side": "five_prime",
            "proposed_sequence": "",
            "motif_id": "t7_promoter_minimal",
            "motif_length": "18",
            "support": "",
            "records_considered": "1",
            "records_matching_exactly": "1",
            "confidence": "configured_motif_library",
            "status": "proposed_for_review",
            "applied": "false",
            "reason_not_applied": "detection_only_not_an_approved_trim",
            "reason": "known_motif:t7_promoter_minimal",
        }
    ]
    _seed(input_dir, meta_dir, items, proposals=proposals)
    result = run_aptamerbase_s3(
        repo_root=repo_root,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=output_dir,
        expected_rows=18,
        check_deterministic_rerun=True,
    )
    stats = result.stats
    assert stats.s2_rows == stats.s3_rows == 18
    rejected = stats.primary_route_counts.get(PRIMARY_ROUTE_REJECT, 0)
    parked_ssdna = stats.primary_route_counts.get(PRIMARY_ROUTE_SSDNA, 0)
    parked_mol = stats.primary_route_counts.get(PRIMARY_ROUTE_MOLECULE, 0)
    parked_chem = stats.primary_route_counts.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)
    parked_construct = stats.primary_route_counts.get(PRIMARY_ROUTE_CONSTRUCT, 0)
    eligible = stats.primary_route_counts.get(PRIMARY_ROUTE_ELIGIBLE, 0)
    assert (
        rejected
        + parked_ssdna
        + parked_mol
        + parked_chem
        + parked_construct
        + eligible
        == 18
    )
    assert stats.non_aptamer_source_object_count == 2
    assert stats.structure_topic_rows == 2
    assert stats.applied_trim_count == 0
    assert stats.missing_target_rejected_count == 0
    assert stats.core_differs_from_full == 0
    assert result.deterministic_rerun_ok is True
    assert _sha256(result.output_canonical) == _sha256(
        input_dir / "aptamerbase_normalised.csv"
    )
    decisions = list(
        csv.DictReader(result.output_decisions.open(encoding="utf-8", newline=""))
    )
    assert len(decisions) == 18
    assert {row["record_id"] for row in decisions} == {
        f"aptamerbase:{idx:04d}" for idx in range(1, 19)
    }
    assert all(row["target_name_raw"] == "" for row in decisions)
    by_id = {row["record_id"]: row for row in decisions}
    assert by_id["aptamerbase:0011"]["primary_reason"] == "non_aptamer_source_object"
    assert by_id["aptamerbase:0011"]["manual_review_required"] == "false"
    assert by_id["aptamerbase:0002"]["primary_reason"] == "missing_sequence"
    assert by_id["aptamerbase:0002"]["manual_review_required"] == "false"
    assert by_id["aptamerbase:0003"]["primary_reason"] == "ssdna_parked"
    assert by_id["aptamerbase:0003"]["manual_review_required"] == "false"
    assert by_id["aptamerbase:0009"]["primary_reason"] == "ssdna_parked"
    assert by_id["aptamerbase:0009"]["manual_review_required"] == "true"
    assert by_id["aptamerbase:0017"]["primary_reason"] == "trim_construct_unresolved"
    assert by_id["aptamerbase:0015"]["aptamerbase_id"] == shared_id
    assert by_id["aptamerbase:0016"]["aptamerbase_id"] == shared_id
    rejected_rows = list(
        csv.DictReader(result.output_rejected.open(encoding="utf-8", newline=""))
    )
    assert {row["rejection_reason"] for row in rejected_rows} <= set(
        PLAN_REJECTION_REASONS
    )
    canonical = list(
        csv.DictReader(result.output_canonical.open(encoding="utf-8", newline=""))
    )
    for row in canonical:
        for field_name in S3_FORBIDDEN_FIELDS:
            assert row.get(field_name, "") == ""
    summary = result.output_summary.read_text(encoding="utf-8")
    assert _rna(40) not in summary
    assert "No human decisions applied" in summary


def test_cli_and_dispatch(tmp_path: Path) -> None:
    repo_root, input_dir, meta_dir, output_dir = _make_tree(tmp_path)
    rows = [_bundle(_s2_row("0001", _rna(40))), _bundle(_s2_row("0002", _rna(40)))]
    _seed(input_dir, meta_dir, rows)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "aptamerbase",
                "--repo-root",
                str(repo_root),
                "--input-dir",
                str(input_dir),
                "--source-metadata-dir",
                str(meta_dir),
                "--eligibility-policy",
                str(POLICY_PATH),
                "--output-dir",
                str(output_dir),
                "--expected-rows",
                "2",
            ]
        )
    assert code == 0
    assert "source=aptamerbase" in stdout.getvalue()
    assert _rna(40) not in stdout.getvalue()


@pytest.mark.skipif(not PRODUCTION_S2.is_file(), reason="AptamerBase S2 not present")
@pytest.mark.skipif(not PRODUCTION_QC.is_file(), reason="AptamerBase S2 QC missing")
@pytest.mark.skipif(not PRODUCTION_SIDECAR.is_file(), reason="AptamerBase sidecar missing")
@pytest.mark.skipif(not PRODUCTION_RAW.is_file(), reason="AptamerBase raw missing")
@pytest.mark.skipif(
    not PRODUCTION_PROPOSALS.is_file(), reason="AptamerBase S2 proposals missing"
)
def test_production_2128_reconciles_without_embedding_sequences(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    input_dir = repo / "data" / "interim" / "normalised"
    meta_dir = repo / "data" / "interim" / "extracted"
    raw_dir = repo / "data" / "raw" / "aptamerbase"
    output_dir = repo / "data" / "interim" / "checkpoints" / "aptamerbase_cp1"
    input_dir.mkdir(parents=True)
    meta_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    shutil.copy(PRODUCTION_S2, input_dir / "aptamerbase_normalised.csv")
    shutil.copy(PRODUCTION_QC, input_dir / "aptamerbase_s2_qc.csv")
    shutil.copy(PRODUCTION_PROPOSALS, input_dir / "detected_constants_aptamerbase.csv")
    shutil.copy(PRODUCTION_SIDECAR, meta_dir / "aptamerbase_source_metadata.csv")
    shutil.copy(PRODUCTION_RAW, raw_dir / "aptamerbase_aptamers.csv")
    if PRODUCTION_RDF.is_file():
        shutil.copy(PRODUCTION_RDF, raw_dir / "aptamerbase.freebase.extract.nt.gz")
    assert _sha256(input_dir / "aptamerbase_normalised.csv") == EXPECTED_APTAMERBASE_S2_HASH
    result = run_aptamerbase_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=output_dir,
        expected_rows=2128,
        check_deterministic_rerun=True,
    )
    stats = result.stats
    assert stats.s2_rows == stats.s3_rows == 2128
    rejected = stats.primary_route_counts.get(PRIMARY_ROUTE_REJECT, 0)
    parked_ssdna = stats.primary_route_counts.get(PRIMARY_ROUTE_SSDNA, 0)
    parked_mol = stats.primary_route_counts.get(PRIMARY_ROUTE_MOLECULE, 0)
    parked_chem = stats.primary_route_counts.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)
    parked_construct = stats.primary_route_counts.get(PRIMARY_ROUTE_CONSTRUCT, 0)
    eligible = stats.primary_route_counts.get(PRIMARY_ROUTE_ELIGIBLE, 0)
    assert (
        rejected
        + parked_ssdna
        + parked_mol
        + parked_chem
        + parked_construct
        + eligible
        == 2128
    )
    assert stats.structure_topic_rows == 72
    assert stats.non_aptamer_source_object_count == 72
    assert stats.applied_trim_count == 0
    assert stats.core_differs_from_full == 0
    assert stats.missing_target_rejected_count == 0
    assert stats.group_consensus_proposal_record_count == 0
    assert stats.random_accept_audit_count == 30 or stats.random_accept_audit_shortfall > 0
    assert _sha256(result.output_canonical) == EXPECTED_APTAMERBASE_S2_HASH
    assert result.deterministic_rerun_ok is True
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "No human decisions applied" in summary
    assert "Global S4 has not been run" in summary

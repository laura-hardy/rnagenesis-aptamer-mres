"""Tests for the AptaDB S3 classification runner (synthetic fixtures only).

Every literal nucleotide string in this file is shorter than 20 nt except where
length thresholds are tested with strings built at runtime. Does not read real
AptaDB source data.
"""

from __future__ import annotations

import csv
import hashlib
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadb import SIDECAR_COLUMNS, UNLINKED_COLUMNS  # noqa: E402
from adapters.aptadb_s2 import CONSTANT_PROPOSAL_COLUMNS, S2_QC_COLUMNS  # noqa: E402
from adapters.aptadb_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_NON_PROTEIN,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    REJECTION_COLUMNS,
)
from common.corpus_schema import CORPUS_COLUMNS, empty_corpus_record  # noqa: E402
from s3_classify import main, run_aptadb_s3, run_s3_classification  # noqa: E402

POLICY_PATH = REPO_ROOT / "config" / "source_eligibility" / "aptadb.json"


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
    alphabet: str = "RNA",
    chemistry: str = "RNA",
    target: str = "demo_protein",
    qc_flags: str = "",
    trim_status: str = "no_constants_detected",
    trim_confidence: str = "n/a",
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"aptadb:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "unknown",
            "trim_status": "not_applicable" if sequence == "" else trim_status,
            "trim_confidence": trim_confidence,
            "molecule_type": molecule_type if sequence else "unknown",
            "alphabet_as_reported": alphabet if sequence else "missing",
            "t_to_u_applied": "false",
            "chemistry": chemistry if sequence else "unknown",
            "target_name_raw": target,
            "source_db": "aptadb",
            "source_dataset": "aptadb_official_export_2026-08",
            "contributing_sources": "aptadb",
            "contributing_datasets": "aptadb_official_export_2026-08",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "publication": "Demo",
            "pubmed_id": "11111111",
            "qc_flags": qc_flags,
        }
    )
    return record


def _qc_row(canonical: dict[str, str]) -> dict[str, str]:
    row = {column: "" for column in S2_QC_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "target_name_raw": canonical["target_name_raw"],
            "source_aptamer_chemistry": (
                "RNA" if canonical["molecule_type"] == "RNA" else "DNA"
            ),
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
        }
    )
    return row


def _meta_row(canonical: dict[str, str], *, target_chemistry: str) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "aptadb_apta_index": f"Apta_{canonical['native_id']}",
            "aptadb_target_chemistry": target_chemistry,
            "aptadb_aptamer_chemistry": (
                "RNA" if canonical["molecule_type"] == "RNA" else "DNA"
            ),
            "aptadb_aptamer_description": f"name-{canonical['native_id']}",
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
    (repo_root / "config" / "source_normalisation").mkdir(parents=True)
    (repo_root / "config" / "source_normalisation" / "aptadb.json").write_text(
        (REPO_ROOT / "config" / "source_normalisation" / "aptadb.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    input_dir = repo_root / "data" / "interim" / "normalised"
    meta_dir = repo_root / "data" / "interim" / "extracted"
    output_dir = repo_root / "data" / "interim" / "checkpoints" / "aptadb_cp1"

    rows = [
        (_s2_row("1", _rna(40)), "Protein"),
        (_s2_row("2", _rna(40), target=""), "Molecule"),
        (_s2_row("3", _rna(40), target=""), "Cell"),
        (_s2_row("4", _rna(40), target=""), "Other"),
        (
            _s2_row(
                "5",
                _dna(40),
                molecule_type="ssDNA",
                alphabet="DNA_T",
                chemistry="DNA",
            ),
            "Protein",
        ),
        (
            _s2_row(
                "6",
                _dna(40),
                molecule_type="ssDNA",
                alphabet="DNA_T",
                chemistry="DNA",
                target="",
            ),
            "Molecule",
        ),
        (
            _s2_row(
                "7",
                _dna(39) + "-",
                molecule_type="ssDNA",
                alphabet="invalid",
                chemistry="DNA",
                qc_flags="alignment_gaps",
            ),
            "Protein",
        ),
        (
            _s2_row(
                "8",
                _rna(39) + "-",
                qc_flags="alignment_gaps",
                target="",
            ),
            "Cell",
        ),
        (_s2_row("9", _rna(19)), "Protein"),
        (_s2_row("10", _rna(20)), "Protein"),
        (_s2_row("11", _rna(100)), "Protein"),
        (_s2_row("12", _rna(101)), "Protein"),
        (
            _s2_row(
                "13",
                _rna(20) + "T" + _rna(19),
                alphabet="mixed_T_U",
                qc_flags="mixed_t_u",
            ),
            "Protein",
        ),
        (
            _s2_row(
                "14",
                _rna(39) + "X",
                alphabet="invalid",
                qc_flags="invalid_character",
            ),
            "Protein",
        ),
    ]
    canonical_rows = [item[0] for item in rows]
    qc_rows = [_qc_row(item[0]) for item in rows]
    meta_rows = [_meta_row(item[0], target_chemistry=item[1]) for item in rows]
    _write_csv(input_dir / "aptadb_normalised.csv", list(CORPUS_COLUMNS), canonical_rows)
    _write_csv(input_dir / "aptadb_s2_qc.csv", list(S2_QC_COLUMNS), qc_rows)
    _write_csv(meta_dir / "aptadb_source_metadata.csv", list(SIDECAR_COLUMNS), meta_rows)
    _write_csv(
        input_dir / "aptadb_constant_region_proposals.csv",
        list(CONSTANT_PROPOSAL_COLUMNS),
        [],
    )
    _write_csv(
        meta_dir / "aptadb_unlinked_aptamers.csv",
        list(UNLINKED_COLUMNS),
        [
            {
                "apta_index": "Apta_u1",
                "aptamer_chemistry": "DNA",
                "sequence": "ACGTAC",
                "planned_s3_reason": "missing_target",
            },
            {
                "apta_index": "Apta_u2",
                "aptamer_chemistry": "RNA",
                "sequence": "ACGUAC",
                "planned_s3_reason": "missing_target",
            },
        ],
    )
    return repo_root, input_dir, meta_dir, output_dir


def test_no_silent_row_disappearance_and_one_primary_route(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir = _make_tree(tmp_path)
    before = _sha256(input_dir / "aptadb_normalised.csv")
    result = run_aptadb_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=14,
        expected_unlinked_rows=2,
    )
    assert result.stats.s2_rows == 14
    assert result.stats.s3_rows == 14
    rejected = result.stats.primary_route_counts.get(PRIMARY_ROUTE_REJECT, 0)
    parked_ssdna = result.stats.primary_route_counts.get(PRIMARY_ROUTE_SSDNA, 0)
    parked_np = result.stats.primary_route_counts.get(PRIMARY_ROUTE_NON_PROTEIN, 0)
    eligible = result.stats.primary_route_counts.get(PRIMARY_ROUTE_ELIGIBLE, 0)
    assert rejected + parked_ssdna + parked_np + eligible == 14
    assert parked_ssdna == 2
    assert parked_np == 3
    assert eligible == 3
    assert rejected == 6
    assert _sha256(input_dir / "aptadb_normalised.csv") == before
    assert _sha256(result.output_canonical) == before

    decisions = list(
        csv.DictReader(result.output_decisions.open(encoding="utf-8", newline=""))
    )
    routes = [row["primary_route"] for row in decisions]
    assert len(routes) == 14
    assert len(set(row["record_id"] for row in decisions)) == 14

    parked_ssdna_ids = {
        row["record_id"]
        for row in csv.DictReader(
            result.output_parked_ssdna.open(encoding="utf-8", newline="")
        )
    }
    parked_np_ids = {
        row["record_id"]
        for row in csv.DictReader(
            result.output_parked_non_protein.open(encoding="utf-8", newline="")
        )
    }
    assert not (parked_ssdna_ids & parked_np_ids)

    rejected_rows = list(
        csv.DictReader(result.output_rejected.open(encoding="utf-8", newline=""))
    )
    interaction_rejects = [row for row in rejected_rows if row["stage"] == "S3"]
    unlinked_rejects = [
        row for row in rejected_rows if row["stage"] == "S3_source_reconciliation"
    ]
    assert len(interaction_rejects) == 6
    assert len(unlinked_rejects) == 2
    assert all(row["rejection_reason"] == "missing_target" for row in unlinked_rejects)
    assert {row["native_id"] for row in unlinked_rejects} == {"Apta_u1", "Apta_u2"}
    assert result.stats.unlinked_dna == 1
    assert result.stats.unlinked_rna == 1


def test_deterministic_rerun(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir = _make_tree(tmp_path)
    result = run_aptadb_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=14,
        expected_unlinked_rows=2,
        check_deterministic_rerun=True,
    )
    assert result.deterministic_rerun_ok is True


def test_cli_and_dispatch(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir = _make_tree(tmp_path)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "aptadb",
                "--repo-root",
                str(repo),
                "--input-dir",
                str(input_dir),
                "--source-metadata-dir",
                str(meta_dir),
                "--eligibility-policy",
                str(POLICY_PATH),
                "--output-dir",
                str(out_dir),
                "--expected-rows",
                "14",
            ]
        )
    assert code == 0
    assert "source=aptadb" in stdout.getvalue()

    dispatched = run_s3_classification(
        repo_root=repo,
        source_key="aptadb",
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=repo / "missing_leak.csv",
        target_aliases=repo / "missing_alias.csv",
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=14,
    )
    assert dispatched.source_key == "aptadb"


def test_s4_and_schema_sidecars(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir = _make_tree(tmp_path)
    result = run_aptadb_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=14,
        expected_unlinked_rows=2,
    )
    decisions = list(
        csv.DictReader(result.output_decisions.open(encoding="utf-8", newline=""))
    )
    assert list(decisions[0].keys()) == list(DECISION_COLUMNS)
    for row in decisions:
        assert "target_type" not in row
        assert "binding_evidence_score" not in row
        assert row.get("manual_decision", "") == ""
    detail = list(
        csv.DictReader(result.output_local_detail.open(encoding="utf-8", newline=""))
    )
    assert list(detail[0].keys()) == list(LOCAL_DETAIL_COLUMNS)
    assert all(row["manual_decision"] == "" for row in detail)
    parks = list(
        csv.DictReader(result.output_parked_ssdna.open(encoding="utf-8", newline=""))
    )
    assert list(parks[0].keys()) == list(PARK_COLUMNS)
    rejected = list(
        csv.DictReader(result.output_rejected.open(encoding="utf-8", newline=""))
    )
    assert list(rejected[0].keys()) == list(REJECTION_COLUMNS)
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "ACGU" not in summary
    assert "Evidence mapping and thresholding" in summary
    assert "No AptaDB record is authorised for S4 yet" in summary

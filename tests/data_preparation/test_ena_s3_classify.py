"""Tests for the ENA S3 classification runner (synthetic fixtures only).

Every literal nucleotide string is a repeating ACGU tile built at runtime.
Does not read real ENA source data.
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

from adapters.ena import SIDECAR_COLUMNS  # noqa: E402
from adapters.ena_s2 import CONSTANT_PROPOSAL_COLUMNS, MEMBERSHIP_COLUMNS, S2_QC_COLUMNS  # noqa: E402
from adapters.ena_s3 import (  # noqa: E402
    PRIMARY_ROUTE_CONSTRUCT,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
)
from common.corpus_schema import CORPUS_COLUMNS, empty_corpus_record  # noqa: E402
from s3_classify import main, run_ena_s3, run_s3_classification  # noqa: E402

POLICY_PATH = REPO_ROOT / "config" / "source_eligibility" / "ena.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _s2_row(
    native_id: str,
    sequence: str,
    *,
    alphabet: str = "RNA",
    qc_flags: str = "",
    t_to_u_applied: str = "false",
    target: str = "demo_target",
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"ena:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "unknown",
            "trim_status": "no_constants_detected",
            "trim_confidence": "n/a",
            "molecule_type": "RNA",
            "alphabet_as_reported": alphabet,
            "t_to_u_applied": t_to_u_applied,
            "chemistry": "RNA",
            "target_name_raw": target,
            "source_db": "ena",
            "source_dataset": "ena_selected_v2_2026-08",
            "contributing_sources": "ena",
            "contributing_datasets": "ena_selected_v2_2026-08",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "qc_flags": qc_flags,
        }
    )
    return record


def _qc_row(canonical: dict[str, str], **overrides: str) -> dict[str, str]:
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
            "experiment_group_id": "g1",
            "source_promoter_or_template_concern": "false",
            "source_t7_concern": "false",
        }
    )
    row.update(overrides)
    return row


def _meta_row(canonical: dict[str, str], **overrides: str) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "review_unit_id": canonical["native_id"],
            "sequence": canonical["sequence_raw"],
            "target": canonical["target_name_raw"],
            "target_type": "protein",
            "experiment_group_id": "g1",
            "unresolved_target": "0",
            "genuine_target_conflict": "0",
        }
    )
    row.update(overrides)
    return row


def _make_tree(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repo = tmp_path / "repo"
    input_dir = repo / "data" / "interim" / "normalised"
    meta_dir = repo / "data" / "interim" / "extracted"
    output_dir = repo / "data" / "interim" / "checkpoints" / "ena_cp1"
    motif = "AAUUGGCC"
    rows = [
        _s2_row("ok", _rna(40)),
        _s2_row(
            "tu",
            _rna(44),
            alphabet="DNA_T",
            t_to_u_applied="true",
            qc_flags="t_in_reported_rna",
        ),
        _s2_row("short", _rna(17)),
        _s2_row("grp", motif + _rna(30)),
        _s2_row("prom", _rna(48)),
        _s2_row("dup_a", _rna(36)),
        _s2_row("dup_b", _rna(36)),
        _s2_row("bound", _rna(22)),
    ]
    qc_rows = [
        _qc_row(rows[0], experiment_group_id="g_clean"),
        _qc_row(rows[1], experiment_group_id="g_clean"),
        _qc_row(rows[2], experiment_group_id="g_short"),
        _qc_row(rows[3], experiment_group_id="g_trim"),
        _qc_row(
            rows[4],
            experiment_group_id="g_prom",
            source_promoter_or_template_concern="true",
            source_t7_concern="true",
        ),
        _qc_row(rows[5], experiment_group_id="g_dup"),
        _qc_row(rows[6], experiment_group_id="g_dup"),
        _qc_row(rows[7], experiment_group_id="g_bound"),
    ]
    meta_rows = [_meta_row(row) for row in rows]
    proposals = [
        {
            "proposal_id": "g_trim:five_prime:group_consensus",
            "experiment_group_id": "g_trim",
            "proposal_source": "group_consensus",
            "side": "five_prime",
            "proposed_sequence": motif,
            "motif_id": "",
            "motif_length": str(len(motif)),
            "support": "0.8",
            "records_considered": "1",
            "records_matching_exactly": "1",
            "confidence": "medium",
            "status": "candidate",
            "applied": "false",
            "reason_not_applied": "unapplied_pending_checkpoint",
            "reason": "",
        }
    ]
    _write_csv(input_dir / "ena_normalised.csv", list(CORPUS_COLUMNS), rows)
    _write_csv(input_dir / "ena_s2_qc.csv", list(S2_QC_COLUMNS), qc_rows)
    _write_csv(meta_dir / "ena_source_metadata.csv", list(SIDECAR_COLUMNS), meta_rows)
    _write_csv(
        input_dir / "ena_constant_region_proposals.csv",
        list(CONSTANT_PROPOSAL_COLUMNS),
        proposals,
    )
    _write_csv(
        input_dir / "ena_constant_region_membership.csv",
        list(MEMBERSHIP_COLUMNS),
        [
            {
                "proposal_id": "g_trim:five_prime:group_consensus",
                "experiment_group_id": "g_trim",
                "record_id": "ena:grp",
                "proposal_source": "group_consensus",
                "side": "five_prime",
            }
        ],
    )
    return repo, input_dir, meta_dir, output_dir


def test_runner_preserves_all_rows_and_canonical(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir = _make_tree(tmp_path)
    before = _sha256(input_dir / "ena_normalised.csv")
    result = run_ena_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=8,
    )
    assert result.stats.s2_rows == 8
    assert result.stats.s3_rows == 8
    accept = result.stats.decision_counts.get("proposed_accept", 0)
    park = result.stats.decision_counts.get("proposed_park", 0)
    reject = result.stats.decision_counts.get("proposed_reject", 0)
    assert accept + park + reject == 8
    assert reject == 1
    assert park == 2
    assert result.stats.ssdna_parked_count == 0
    assert _sha256(input_dir / "ena_normalised.csv") == before
    assert _sha256(result.output_canonical) == before
    decisions = list(csv.DictReader(result.output_decisions.open(encoding="utf-8")))
    by_id = {row["record_id"]: row for row in decisions}
    assert by_id["ena:ok"]["proposed_decision"] == "proposed_accept"
    assert by_id["ena:tu"]["proposed_decision"] == "proposed_accept"
    assert by_id["ena:short"]["proposed_decision"] == "proposed_reject"
    assert by_id["ena:grp"]["proposed_decision"] == "proposed_park"
    assert by_id["ena:prom"]["proposed_decision"] == "proposed_park"
    assert by_id["ena:dup_a"]["proposed_decision"] == "proposed_accept"
    assert by_id["ena:dup_b"]["proposed_decision"] == "proposed_accept"
    assert by_id["ena:dup_a"]["exact_sequence_full_duplicate_diagnostic"] == "true"
    assert result.stats.duplicate_sequence_full_values == 1
    assert result.stats.duplicate_sequence_full_records == 2
    rejected = list(csv.DictReader(result.output_rejected.open(encoding="utf-8")))
    assert len(rejected) == 1
    assert rejected[0]["rejection_reason"] == "length_out_of_range"
    parks = list(csv.DictReader(result.output_parks.open(encoding="utf-8")))
    assert {row["record_id"] for row in parks} == {"ena:grp", "ena:prom"}
    assert all(row["park_reason"] == "trim_construct_unresolved" for row in parks)
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "diagnostic only — no deduplication performed" in summary
    assert "Evidence was not classified" in summary


def test_deterministic_rerun(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir = _make_tree(tmp_path)
    result = run_ena_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=8,
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
                "ena",
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
                "8",
            ]
        )
    assert code == 0
    assert "source=ena" in stdout.getvalue()
    dispatched = run_s3_classification(
        repo_root=repo,
        source_key="ena",
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=repo / "missing.csv",
        target_aliases=repo / "missing.csv",
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=8,
    )
    assert dispatched.source_key == "ena"
    assert dispatched.stats.primary_route_counts.get(PRIMARY_ROUTE_ELIGIBLE, 0) >= 1
    assert dispatched.stats.primary_route_counts.get(PRIMARY_ROUTE_REJECT, 0) == 1
    assert dispatched.stats.primary_route_counts.get(PRIMARY_ROUTE_CONSTRUCT, 0) == 2

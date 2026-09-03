"""Tests for the AptaIndex S3 classification runner (synthetic fixtures only).

Literal nucleotides are repeating ACGU/ACGT tiles built at runtime.
Does not embed real AptaIndex sequences. Optional local production
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

from adapters.aptaindex import SIDECAR_COLUMNS  # noqa: E402
from adapters.aptaindex_s2 import CONSTANT_PROPOSAL_COLUMNS, S2_QC_COLUMNS  # noqa: E402
from adapters.aptaindex_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS,
    PLAN_REJECTION_REASONS,
    PRIMARY_ROUTE_CHEMISTRY_REVIEW,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    REJECTION_COLUMNS,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S3_FORBIDDEN_FIELDS,
    empty_corpus_record,
)
from s3_classify import (  # noqa: E402
    EXPECTED_APTAINDEX_S2_HASH,
    main,
    run_aptaindex_s3,
    run_s3_classification,
)

POLICY_PATH = REPO_ROOT / "config" / "source_eligibility" / "aptaindex.json"
PRODUCTION_S2 = REPO_ROOT / "data" / "interim" / "normalised" / "aptaindex_normalised.csv"
PRODUCTION_QC = REPO_ROOT / "data" / "interim" / "normalised" / "aptaindex_s2_qc.csv"
PRODUCTION_PROPOSALS = (
    REPO_ROOT / "data" / "interim" / "normalised" / "detected_constants_aptaindex.csv"
)
PRODUCTION_SIDECAR = (
    REPO_ROOT / "data" / "interim" / "extracted" / "aptaindex_source_metadata.csv"
)
PRODUCTION_RAW = (
    REPO_ROOT / "data" / "raw" / "AptaIndex" / "aptamers-export-2026-07-22.csv"
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
    alphabet: str = "chemical_notation",
    target: str = "demo_target",
    qc_flags: str = "",
    trim_status: str = "no_constants_detected",
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"aptaindex:{native_id}",
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
            "target_name_raw": target,
            "source_db": "aptaindex",
            "source_dataset": "aptaindex_export_2026-07-22",
            "contributing_sources": "aptaindex",
            "contributing_datasets": "aptaindex_export_2026-07-22",
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
    mapping_class: str,
    parser_status: str = "ok",
    parser_reason_category: str = "",
    source_type: str = "RNA",
    token_family_summary: str = "r",
    has_l_prefix: str = "false",
) -> dict[str, str]:
    row = {column: "" for column in S2_QC_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "source_type": source_type,
            "parser_status": parser_status,
            "parser_reason_category": parser_reason_category,
            "mapping_class": mapping_class,
            "token_family_summary": token_family_summary,
            "has_l_prefix": has_l_prefix,
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


def _meta_row(
    canonical: dict[str, str],
    *,
    aptaindex_type: str = "RNA",
    aptaindex_target_type: str = "Protein",
) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "aptaindex_native_id": canonical["native_id"],
            "aptaindex_title": f"title-{canonical['native_id']}",
            "aptaindex_type": aptaindex_type,
            "aptaindex_target": canonical["target_name_raw"],
            "aptaindex_target_type": aptaindex_target_type,
            "aptaindex_reference": "Demo",
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
    output_dir = repo_root / "data" / "interim" / "checkpoints" / "aptaindex_cp1"
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
        input_dir / "aptaindex_normalised.csv",
        list(CORPUS_COLUMNS),
        canonical_rows,
        quote_all=True,
    )
    _write_csv(input_dir / "aptaindex_s2_qc.csv", list(S2_QC_COLUMNS), qc_rows)
    _write_csv(
        meta_dir / "aptaindex_source_metadata.csv",
        list(SIDECAR_COLUMNS),
        meta_rows,
        quote_all=True,
    )
    _write_csv(
        input_dir / "detected_constants_aptaindex.csv",
        list(CONSTANT_PROPOSAL_COLUMNS),
        proposals or [],
    )


def _bundle(
    canonical: dict[str, str],
    *,
    mapping_class: str,
    aptaindex_type: str = "RNA",
    parser_status: str = "ok",
    parser_reason_category: str = "",
    token_family_summary: str = "r",
    has_l_prefix: str = "false",
    aptaindex_target_type: str = "Protein",
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    return (
        canonical,
        _qc_row(
            canonical,
            mapping_class=mapping_class,
            parser_status=parser_status,
            parser_reason_category=parser_reason_category,
            source_type=aptaindex_type,
            token_family_summary=token_family_summary,
            has_l_prefix=has_l_prefix,
        ),
        _meta_row(
            canonical,
            aptaindex_type=aptaindex_type,
            aptaindex_target_type=aptaindex_target_type,
        ),
    )


def test_s3_dispatch_recognises_aptaindex(tmp_path: Path) -> None:
    repo_root, input_dir, meta_dir, output_dir = _make_tree(tmp_path)
    rna = _s2_row("0001", _rna(40))
    _seed(input_dir, meta_dir, [_bundle(rna, mapping_class="straightforward_rna")])
    result = run_s3_classification(
        repo_root=repo_root,
        source_key="aptaindex",
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=repo_root / "unused_leakage.csv",
        target_aliases=repo_root / "unused_aliases.csv",
        eligibility_policy=POLICY_PATH,
        output_dir=output_dir,
        expected_rows=1,
    )
    assert result.source_key == "aptaindex"
    assert result.stats.s3_rows == 1


def test_no_silent_row_disappearance_and_reconciliation(tmp_path: Path) -> None:
    repo_root, input_dir, meta_dir, output_dir = _make_tree(tmp_path)
    shared = _rna(40)
    peptide = _s2_row(
        "0006",
        "",
        qc_flags="parser_not_applicable_peptide",
        alphabet="",
    )
    peptide["alphabet_as_reported"] = ""
    unsupported = _s2_row(
        "0008",
        "",
        qc_flags="unsupported_notation",
        alphabet="chemical_notation",
    )
    unsupported["alphabet_as_reported"] = "chemical_notation"
    unsupported["molecule_type"] = "unknown"
    unsupported["chemistry"] = "unknown"
    items = [
        _bundle(_s2_row("0001", _rna(40)), mapping_class="straightforward_rna"),
        _bundle(
            _s2_row("0002", "", qc_flags="missing_sequence"),
            mapping_class="missing_sequence",
            aptaindex_type="DNA",
            parser_status="missing",
            token_family_summary="",
        ),
        _bundle(
            _s2_row("0003", _dna(40), molecule_type="ssDNA", chemistry="DNA"),
            mapping_class="straightforward_dna",
            aptaindex_type="DNA",
            token_family_summary="d",
        ),
        _bundle(
            _s2_row("0004", _rna(40), chemistry="2F-RNA"),
            mapping_class="straightforward_2f_rna",
            aptaindex_type="2'-F-RNA",
            token_family_summary="f+r",
        ),
        _bundle(_s2_row("0005", _rna(19)), mapping_class="straightforward_rna"),
        _bundle(
            peptide,
            mapping_class="peptide",
            aptaindex_type="Peptide",
            parser_status="not_applicable_peptide",
            token_family_summary="",
        ),
        _bundle(_s2_row("0007", _rna(101)), mapping_class="straightforward_rna"),
        _bundle(
            unsupported,
            mapping_class="unsupported_notation",
            aptaindex_type="RNA",
            parser_status="failed",
            parser_reason_category="unsupported_decoration",
            token_family_summary="",
        ),
        _bundle(
            _s2_row("0009", _rna(40), molecule_type="unknown", chemistry="unknown"),
            mapping_class="l_rna",
            aptaindex_type="L-RNA",
            token_family_summary="r",
            has_l_prefix="true",
        ),
        _bundle(
            _s2_row(
                "0010",
                _dna(40),
                molecule_type="unknown",
                chemistry="unknown",
            ),
            mapping_class="l_dna",
            aptaindex_type="L-DNA",
            token_family_summary="d",
            has_l_prefix="true",
        ),
        _bundle(
            _s2_row("0011", _rna(40), molecule_type="unknown", chemistry="unknown"),
            mapping_class="chimeric",
            aptaindex_type="Chimeric",
            token_family_summary="d+r",
        ),
        _bundle(
            _s2_row(
                "0012",
                _dna(40),
                molecule_type="ssDNA",
                chemistry="DNA",
            ),
            mapping_class="type_token_disagreement",
            aptaindex_type="RNA",
            token_family_summary="d",
        ),
        _bundle(_s2_row("0013", _rna(22)), mapping_class="straightforward_rna"),
        _bundle(_s2_row("0014", _rna(95)), mapping_class="straightforward_rna"),
        _bundle(
            _s2_row("0015", shared, target="target_a"),
            mapping_class="straightforward_rna",
        ),
        _bundle(
            _s2_row("0016", shared, target="target_b"),
            mapping_class="straightforward_rna",
        ),
        _bundle(
            _s2_row("0017", _rna(40), target=""),
            mapping_class="straightforward_rna",
        ),
        _bundle(
            _s2_row("0018", _rna(40)),
            mapping_class="straightforward_rna",
            aptaindex_target_type="Peptide",
        ),
    ]
    motif = _s2_row("0019", _rna(40))
    items.append(_bundle(motif, mapping_class="straightforward_rna"))
    proposal = {
        "proposal_id": "aptaindex:0019:known_motif:five_prime:t7_promoter_minimal",
        "experiment_group_id": "aptaindex:0019",
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
    _seed(input_dir, meta_dir, items, proposals=[proposal])

    result = run_aptaindex_s3(
        repo_root=repo_root,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=output_dir,
        expected_rows=len(items),
        check_deterministic_rerun=True,
    )
    stats = result.stats
    assert stats.s2_rows == stats.s3_rows == len(items)
    rejected = stats.primary_route_counts.get(PRIMARY_ROUTE_REJECT, 0)
    parked_ssdna = stats.primary_route_counts.get(PRIMARY_ROUTE_SSDNA, 0)
    parked_chem = stats.primary_route_counts.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)
    eligible = stats.primary_route_counts.get(PRIMARY_ROUTE_ELIGIBLE, 0)
    assert rejected + parked_ssdna + parked_chem + eligible == len(items)
    assert stats.peptide_molecule_count == 1
    assert stats.missing_sequence_count == 1
    assert stats.missing_target_rejected_count == 0
    assert stats.multi_target_sequence_count == 1
    assert stats.multi_target_treated_as_conflict is False
    assert stats.non_protein_parked_count == 0
    assert stats.known_motif_proposal_record_count == 1
    assert stats.ssdna_parked_count == 1
    assert stats.unsupported_notation_count == 1
    assert stats.l_rna_review_count == 1
    assert stats.l_dna_review_count == 1
    assert stats.chimeric_review_count == 1
    assert stats.type_token_disagreement_count == 1
    assert stats.target_canonicalised_count == 0
    assert stats.evidence_scored_count == 0
    assert stats.affinity_normalised_count == 0
    assert result.deterministic_rerun_ok is True
    assert result.s2_integrity_ok is True

    with result.output_rejected.open("r", encoding="utf-8", newline="") as handle:
        rejected_rows = list(csv.DictReader(handle))
    reasons = {row["rejection_reason"] for row in rejected_rows}
    assert reasons <= set(PLAN_REJECTION_REASONS)
    assert "invalid_alphabet" not in reasons
    assert "missing_target" not in reasons
    assert "non_nucleic_acid_molecule" in reasons

    with result.output_review.open("r", encoding="utf-8", newline="") as handle:
        review_ids = [
            row["record_id"]
            for row in csv.DictReader(handle)
            if row["manual_review_required"] == "true"
        ]
    assert "aptaindex:0002" not in review_ids
    assert "aptaindex:0006" not in review_ids
    assert "aptaindex:0008" in review_ids
    assert "aptaindex:0009" in review_ids
    assert "aptaindex:0010" in review_ids
    assert "aptaindex:0011" in review_ids
    assert "aptaindex:0012" in review_ids
    assert "aptaindex:0013" in review_ids
    assert "aptaindex:0014" in review_ids
    assert "aptaindex:0019" in review_ids

    with result.output_local_detail.open("r", encoding="utf-8", newline="") as handle:
        details = {row["record_id"]: row for row in csv.DictReader(handle)}
    assert details["aptaindex:0019"]["manual_decision"] == ""
    assert details["aptaindex:0008"]["sequence_core"] == ""
    assert details["aptaindex:0008"]["parser_reason_category"] == "unsupported_decoration"
    for field_name in S3_FORBIDDEN_FIELDS:
        assert details["aptaindex:0001"].get(field_name, "") == ""

    summary = result.output_summary.read_text(encoding="utf-8")
    assert "No human decisions applied" in summary
    assert "group-wise constant-region inference was disabled" in summary.lower()
    assert "Evidence scored" in summary
    assert str(repo_root.resolve()) not in summary
    assert list(
        csv.DictReader(result.output_decisions.open(encoding="utf-8")).fieldnames
    ) == list(DECISION_COLUMNS)
    assert list(
        csv.DictReader(result.output_parked_ssdna.open(encoding="utf-8")).fieldnames
    ) == list(PARK_COLUMNS)
    assert list(
        csv.DictReader(result.output_parks.open(encoding="utf-8")).fieldnames
    ) == list(PARK_COLUMNS)
    assert list(
        csv.DictReader(result.output_rejected.open(encoding="utf-8")).fieldnames
    ) == list(REJECTION_COLUMNS)
    assert list(
        csv.DictReader(result.output_local_detail.open(encoding="utf-8")).fieldnames
    ) == list(LOCAL_DETAIL_COLUMNS)


def test_carriage_return_in_publication_does_not_split_rows(tmp_path: Path) -> None:
    repo_root, input_dir, meta_dir, output_dir = _make_tree(tmp_path)
    canonical = _s2_row("0001", _rna(40))
    bundle = _bundle(canonical, mapping_class="straightforward_rna")
    bundle[2]["aptaindex_reference"] = "Demo\rRef"
    _seed(input_dir, meta_dir, [bundle])
    result = run_aptaindex_s3(
        repo_root=repo_root,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=output_dir,
        expected_rows=1,
    )
    with result.output_local_detail.open("r", encoding="utf-8", newline="") as handle:
        details = list(csv.DictReader(handle))
    assert len(details) == 1
    assert details[0]["record_id"] == "aptaindex:0001"
    assert "\r" in details[0]["publication"]


def test_cli_and_dispatch(tmp_path: Path) -> None:
    repo_root, input_dir, meta_dir, output_dir = _make_tree(tmp_path)
    rows = [
        _bundle(_s2_row("0001", _rna(40)), mapping_class="straightforward_rna"),
        _bundle(_s2_row("0002", _rna(40)), mapping_class="straightforward_rna"),
    ]
    _seed(input_dir, meta_dir, rows)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "aptaindex",
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
    assert "source=aptaindex" in stdout.getvalue()
    assert _rna(40) not in stdout.getvalue()


@pytest.mark.skipif(not PRODUCTION_S2.is_file(), reason="AptaIndex S2 not present")
@pytest.mark.skipif(not PRODUCTION_QC.is_file(), reason="AptaIndex S2 QC missing")
@pytest.mark.skipif(not PRODUCTION_SIDECAR.is_file(), reason="AptaIndex sidecar missing")
@pytest.mark.skipif(not PRODUCTION_RAW.is_file(), reason="AptaIndex raw missing")
@pytest.mark.skipif(
    not PRODUCTION_PROPOSALS.is_file(), reason="AptaIndex S2 proposals missing"
)
def test_production_1050_reconciles_without_embedding_sequences(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    input_dir = repo / "data" / "interim" / "normalised"
    meta_dir = repo / "data" / "interim" / "extracted"
    raw_dir = repo / "data" / "raw" / "AptaIndex"
    output_dir = repo / "data" / "interim" / "checkpoints" / "aptaindex_cp1"
    input_dir.mkdir(parents=True)
    meta_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    shutil.copy(PRODUCTION_S2, input_dir / "aptaindex_normalised.csv")
    shutil.copy(PRODUCTION_QC, input_dir / "aptaindex_s2_qc.csv")
    shutil.copy(PRODUCTION_PROPOSALS, input_dir / "detected_constants_aptaindex.csv")
    shutil.copy(PRODUCTION_SIDECAR, meta_dir / "aptaindex_source_metadata.csv")
    shutil.copy(PRODUCTION_RAW, raw_dir / "aptamers-export-2026-07-22.csv")
    assert _sha256(input_dir / "aptaindex_normalised.csv") == EXPECTED_APTAINDEX_S2_HASH
    result = run_aptaindex_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=output_dir,
        expected_rows=1050,
        check_deterministic_rerun=True,
    )
    stats = result.stats
    assert stats.s2_rows == stats.s3_rows == 1050
    rejected = stats.primary_route_counts.get(PRIMARY_ROUTE_REJECT, 0)
    parked_ssdna = stats.primary_route_counts.get(PRIMARY_ROUTE_SSDNA, 0)
    parked_chem = stats.primary_route_counts.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)
    eligible = stats.primary_route_counts.get(PRIMARY_ROUTE_ELIGIBLE, 0)
    assert rejected + parked_ssdna + parked_chem + eligible == 1050
    assert stats.peptide_molecule_count == 57
    assert stats.missing_sequence_count == 31
    assert stats.missing_target_rejected_count == 0
    assert stats.multi_target_sequence_count == 38
    assert stats.multi_target_raw_sequence_count == 24
    assert stats.multi_target_treated_as_conflict is False
    assert stats.known_motif_proposal_record_count == 3
    assert stats.random_accept_audit_count == 30
    assert result.deterministic_rerun_ok is True
    assert _sha256(result.output_canonical) == EXPECTED_APTAINDEX_S2_HASH
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "1050" in summary
    assert "No human decisions applied" in summary
    assert "S4 started: `no`" in summary

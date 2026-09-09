"""Tests for AptamerBase CHECKPOINT-1 decision-support audit (synthetic only).

Literal nucleotides are repeating ACGU/ACGT tiles built at runtime.
Does not read real AptamerBase checkpoint data.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadb_checkpoint1_review import (  # noqa: E402
    MANUAL_FIELDS,
    build_bulk_confirmation_row,
    is_audit_only_row,
    materialize_bulk_audit_decisions,
    validate_review_package,
)
from adapters.aptadb_checkpoint1_review import (  # noqa: E402
    AptaDBCheckpoint1ReviewError,
)
from adapters.aptamerbase_checkpoint1_audit import (  # noqa: E402
    AptamerBaseCheckpoint1AuditError,
    RANDOM_SEED,
    build_audit_package,
    classify_chemistry_row,
    classify_motif_row,
    classify_notation_row,
    extract_pmid_hint,
    group_identity_ok,
)
from adapters.aptamerbase_s3 import DECISION_COLUMNS, LOCAL_DETAIL_COLUMNS  # noqa: E402
from checkpoint1_prepare_review import (  # noqa: E402
    prepare_aptamerbase_checkpoint1_review,
)
from checkpoint1_validate_review import main as validate_main  # noqa: E402


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _dna(n: int) -> str:
    return ("ACGT" * ((n // 4) + 1))[:n]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _base_row(
    record_id: str,
    *,
    batch: str,
    reasons: str,
    route: str = "technical_reject",
    decision: str = "proposed_reject",
    primary: str = "invalid_alphabet",
    molecule: str = "RNA",
    chemistry: str = "RNA",
    alphabet: str = "RNA",
    sequence: str | None = None,
    length: int | None = None,
    freebase: str | None = None,
    label: str = "12345678-demo",
    qc: str = "",
    chem_class: str = "unmodified_backbone",
    rdf_rna: str = "true",
    rdf_dna: str = "false",
    modification: str = "",
    t_to_u: str = "false",
    required: str = "true",
    motif_len: str = "",
    motif_side: str = "",
    motif_name: str = "",
) -> dict[str, str]:
    sequence = _rna(24) if sequence is None else sequence
    length_s = str(length if length is not None else len(sequence))
    native = record_id.split(":")[-1]
    row = {column: "" for column in LOCAL_DETAIL_COLUMNS}
    row.update(
        {
            "record_id": record_id,
            "native_id": native,
            "aptamer_name": f"name-{native}",
            "aptamerbase_id": freebase or f"http://rdf.freebase.com/ns/m.{native}",
            "aptamerbase_label": label,
            "aptamerbase_has_modification_details": modification,
            "source_object_type": "aptamer",
            "proposed_decision": decision,
            "primary_reason": primary,
            "primary_route": route,
            "manual_review_required": required,
            "review_batch": batch,
            "checkpoint_review_reasons": reasons,
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length_s,
            "sequence_length_core": length_s,
            "molecule_type": molecule,
            "chemistry": chemistry,
            "chemistry_class": chem_class,
            "alphabet_as_reported": alphabet,
            "t_to_u_applied": t_to_u,
            "qc_flags": qc,
            "rdf_has_rna": rdf_rna,
            "rdf_has_dna": rdf_dna,
            "constant_proposed_trim_length": motif_len,
            "constant_proposal_sides": motif_side,
            "detected_constant_5p": motif_name,
        }
    )
    for name in MANUAL_FIELDS:
        row[name] = ""
    return row


def _queue_pair(detail: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    review = {column: "" for column in DECISION_COLUMNS}
    for column in DECISION_COLUMNS:
        if column in detail:
            review[column] = detail[column]
    return review, detail


def test_blank_bulk_confirmation_keeps_validator_fail_closed() -> None:
    audit = _base_row(
        "aptamerbase:a1",
        batch="05_accept_with_diagnostics",
        reasons="length_boundary",
        route="technically_eligible",
        decision="proposed_accept",
        primary="technically_eligible_rna",
        length=22,
    )
    judge = _base_row(
        "aptamerbase:j1",
        batch="02_molecule_type_unresolved",
        reasons="molecule_type_unresolved",
        route="parked_molecule_unresolved",
        decision="proposed_park",
        primary="molecule_type_unresolved",
        molecule="unknown",
        chemistry="unknown",
    )
    bulk = build_bulk_confirmation_row([audit, judge])
    assert bulk["confirm"] == ""
    assert is_audit_only_row(audit)
    assert not is_audit_only_row(judge)
    report = validate_review_package(
        queue_rows=[audit, judge],
        group_rows=[],
        bulk_confirmation=bulk,
    )
    assert report.ok is False
    assert report.ready_for_application == 0
    assert report.judgement_required_rows == 1
    assert report.unresolved_judgement_required == 1
    assert report.audit_only_rows == 1
    assert report.audit_only_unconfirmed == 1
    assert report.bulk_audit_confirmed is False


def test_bulk_audit_confirms_separately_and_does_not_alter_s3_route() -> None:
    audit = _base_row(
        "aptamerbase:a1",
        batch="06_random_kept_audit",
        reasons="random_kept_audit",
        route="technically_eligible",
        decision="proposed_accept",
        primary="technically_eligible_rna",
        length=40,
    )
    judge = _base_row(
        "aptamerbase:j1",
        batch="01_sequence_or_source_conflict",
        reasons="sequence_notation",
        sequence=_rna(20) + "N",
        alphabet="ambiguous",
        qc="ambiguous_base",
    )
    confirmation = build_bulk_confirmation_row([audit, judge])
    confirmation["confirm"] = "true"
    updated = materialize_bulk_audit_decisions([audit, judge], confirmation)
    by_id = {row["record_id"]: row for row in updated}
    assert by_id["aptamerbase:a1"]["manual_decision"] == "keep"
    assert by_id["aptamerbase:j1"]["manual_decision"] == ""
    assert by_id["aptamerbase:a1"]["primary_route"] == "technically_eligible"
    assert by_id["aptamerbase:j1"]["primary_route"] == "technical_reject"
    report = validate_review_package(
        queue_rows=updated,
        group_rows=[],
        bulk_confirmation=confirmation,
    )
    assert report.unresolved_judgement_required == 1
    assert report.ready_for_application == 0


def test_judgement_rows_still_require_individual_decisions() -> None:
    judge = _base_row(
        "aptamerbase:j1",
        batch="03_chemistry_review",
        reasons="chemistry_requires_review",
        route="parked_chemistry_review",
        decision="proposed_park",
        primary="chemistry_requires_review",
        chemistry="unknown",
        chem_class="amino_2nh2",
        modification="2'-amino-modified pyrimidine nucleotides",
    )
    bulk = build_bulk_confirmation_row([judge])
    bulk["confirm"] = "true"
    report = validate_review_package(
        queue_rows=[judge],
        group_rows=[],
        bulk_confirmation=bulk,
    )
    assert report.judgement_required_rows == 1
    assert report.unresolved_judgement_required == 1
    assert report.audit_only_rows == 0
    assert report.ready_for_application == 0


def test_audit_sample_is_not_resampled() -> None:
    rows = [
        _base_row(
            f"aptamerbase:r{i:02d}",
            batch="06_random_kept_audit",
            reasons="random_kept_audit",
            route="technically_eligible",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            length=40,
        )
        for i in range(3)
    ]
    first = build_audit_package(queue_rows=rows, random_seed=RANDOM_SEED)
    second = build_audit_package(queue_rows=rows, random_seed=RANDOM_SEED)
    ids_a = [row["record_id"] for row in first.audit_only_rows]
    ids_b = [row["record_id"] for row in second.audit_only_rows]
    assert ids_a == ids_b
    with pytest.raises(AptamerBaseCheckpoint1AuditError, match="frozen at 42"):
        build_audit_package(queue_rows=rows, random_seed=7)


def test_one_record_not_duplicated_and_grouping_does_not_collapse() -> None:
    shared = "http://rdf.freebase.com/ns/m.same"
    seq = _rna(24)
    a = _base_row(
        "aptamerbase:001",
        batch="02_molecule_type_unresolved",
        reasons="molecule_type_unresolved",
        route="parked_molecule_unresolved",
        decision="proposed_park",
        primary="molecule_type_unresolved",
        molecule="unknown",
        chemistry="unknown",
        rdf_rna="false",
        rdf_dna="false",
        sequence=seq,
        freebase=shared,
        label="11111111-unit-1",
    )
    b = _base_row(
        "aptamerbase:002",
        batch="02_molecule_type_unresolved",
        reasons="molecule_type_unresolved",
        route="parked_molecule_unresolved",
        decision="proposed_park",
        primary="molecule_type_unresolved",
        molecule="unknown",
        chemistry="unknown",
        rdf_rna="false",
        rdf_dna="false",
        sequence=seq,
        freebase=shared,
        label="11111111-unit-2",
    )
    package = build_audit_package(queue_rows=[a, b])
    assert [row["record_id"] for row in [a, b]] == ["aptamerbase:001", "aptamerbase:002"]
    assert len(package.decision_support_rows) == 1
    assert package.decision_support_rows[0]["n_physical_rows"] == "2"
    assert package.decision_support_rows[0]["member_record_ids"] == (
        "aptamerbase:001|aptamerbase:002"
    )
    assert package.aggregate["judgement_required_source_id_units"] == 1
    assert group_identity_ok([a, b]) is True


def test_unsafe_source_id_group_differences_are_exposed() -> None:
    shared = "http://rdf.freebase.com/ns/m.diff"
    a = _base_row(
        "aptamerbase:001",
        batch="02_molecule_type_unresolved",
        reasons="molecule_type_unresolved",
        route="parked_molecule_unresolved",
        decision="proposed_park",
        primary="molecule_type_unresolved",
        molecule="unknown",
        chemistry="unknown",
        sequence=_rna(24),
        freebase=shared,
    )
    b = _base_row(
        "aptamerbase:002",
        batch="02_molecule_type_unresolved",
        reasons="molecule_type_unresolved",
        route="parked_molecule_unresolved",
        decision="proposed_park",
        primary="molecule_type_unresolved",
        molecule="unknown",
        chemistry="unknown",
        sequence=_rna(30),
        freebase=shared,
    )
    assert group_identity_ok([a, b]) is False
    package = build_audit_package(queue_rows=[a, b])
    assert package.decision_support_rows[0]["safe_for_groupwise_review"] == "false"
    assert package.decision_support_rows[0]["group_scientifically_identical"] == "false"
    assert package.aggregate["unsafe_multi_record_groups"] == 1


def test_compound_secondary_blocker_remains_after_hypothetical_repair() -> None:
    row = _base_row(
        "aptamerbase:gap",
        batch="01_sequence_or_source_conflict",
        reasons="sequence_notation",
        primary="alignment_gaps",
        sequence=_rna(20) + "-" + _rna(10),
        alphabet="RNA",
        qc="alignment_gaps|core_above_max_length",
        length=135,
    )
    classified = classify_notation_row(row)
    assert classified["machine_recommendation"] == (
        "likely_alignment_notation_recoverable_if_source_confirmed"
    )
    assert classified["canonical_sequence_recoverable_without_guessing"] == "false"
    assert "length" in classified["remaining_blocker_if_repaired"]
    assert classified["proposed_corrected_sequence"] == ""
    assert classified["sequence_raw"] == row["sequence_raw"]


def test_chemistry_recommendation_does_not_populate_human_chemistry() -> None:
    row = _base_row(
        "aptamerbase:chem",
        batch="03_chemistry_review",
        reasons="chemistry_requires_review",
        route="parked_chemistry_review",
        decision="proposed_park",
        primary="chemistry_requires_review",
        chemistry="unknown",
        chem_class="amino_2nh2",
        modification="2'-amino-modified pyrimidine nucleotides",
        sequence=_rna(40),
        length=40,
        qc="chemistry_requires_review",
    )
    classified = classify_chemistry_row(row, primary=True)
    assert classified["evidence_class"] == "source_supports_2NH2_RNA"
    assert classified["proposed_chemistry_override"] == "2NH2-RNA"
    assert row["manual_chemistry_override"] == ""
    assert row["chemistry"] == "unknown"


def test_notation_recommendation_does_not_mutate_canonical_sequence() -> None:
    seq = _rna(20) + "N" + _rna(5)
    row = _base_row(
        "aptamerbase:n",
        batch="01_sequence_or_source_conflict",
        reasons="sequence_notation",
        primary="ambiguous_bases",
        sequence=seq,
        alphabet="ambiguous",
        qc="ambiguous_base",
    )
    original = row["sequence_raw"]
    classified = classify_notation_row(row)
    assert classified["machine_recommendation"] == (
        "likely_true_degenerate_or_ambiguous_sequence"
    )
    assert classified["canonical_sequence_recoverable_without_guessing"] == "false"
    assert classified["proposed_corrected_sequence"] == ""
    assert row["sequence_raw"] == original
    assert row["sequence_full"] == original


def test_motif_simulation_does_not_apply_trim() -> None:
    seq = _rna(98)
    row = _base_row(
        "aptamerbase:motif",
        batch="04_known_motif_construct",
        reasons="constant_region_proposal",
        route="parked_construct_review",
        decision="proposed_park",
        primary="trim_construct_unresolved",
        sequence=seq,
        length=98,
        motif_len="17",
        motif_side="five_prime",
        motif_name="t7_promoter_minimal",
        qc="known_promoter_detected|constants_suspected_unresolved",
    )
    classified = classify_motif_row(row)
    assert classified["machine_recommendation"] == "approve_existing_known_motif"
    assert classified["hypothetical_trimmed_core_length"] == "81"
    assert classified["trim_exceeds_40pct_review_trigger"] == "false"
    assert row["manual_trim_action"] == ""
    assert row["sequence_core"] == seq
    assert row["sequence_length_core"] == "98"


def test_publication_evidence_remains_audit_only() -> None:
    assert extract_pmid_hint("21076782-L-Tryptophan-1") == "21076782"
    assert extract_pmid_hint("PMID:1234567 extra") == "1234567"
    row = _base_row(
        "aptamerbase:pub",
        batch="01_sequence_or_source_conflict",
        reasons="source_molecule_alphabet_conflict",
        route="parked_ssdna",
        decision="proposed_park",
        primary="ssdna_parked",
        molecule="ssDNA",
        chemistry="DNA",
        alphabet="RNA",
        sequence=_rna(40),
        rdf_rna="false",
        rdf_dna="true",
        label="12667800-HepatitisCVirusPolymerase-2",
        qc="source_molecule_alphabet_conflict|u_in_reported_dna",
    )
    package = build_audit_package(queue_rows=[row])
    assert package.dna_u_rows[0]["audit_only_bibliographic_hint"] == "12667800"
    assert package.dna_u_rows[0]["machine_recommendation"] == (
        "confirm_rdf_dna_keep_ssdna_park"
    )
    assert row.get("pubmed_id", "") == ""
    assert row.get("target_name_raw", "") == ""


def test_human_fields_remain_blank_and_regeneration_is_deterministic(
    tmp_path: Path,
) -> None:
    rec_path = (
        tmp_path
        / "repo"
        / "config"
        / "checkpoint_reviews"
        / "aptamerbase_checkpoint1_recommendations.json"
    )
    rec_path.parent.mkdir(parents=True)
    rec_path.write_text(
        (
            REPO_ROOT
            / "config"
            / "checkpoint_reviews"
            / "aptamerbase_checkpoint1_recommendations.json"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    checkpoint = repo / "data" / "interim" / "checkpoints" / "aptamerbase_cp1"
    notation = _base_row(
        "aptamerbase:invalid",
        batch="01_sequence_or_source_conflict",
        reasons="sequence_notation",
        sequence=_rna(20) + "N",
        alphabet="ambiguous",
        qc="ambiguous_base",
    )
    boundary = _base_row(
        "aptamerbase:boundary",
        batch="05_accept_with_diagnostics",
        reasons="length_boundary",
        route="technically_eligible",
        decision="proposed_accept",
        primary="technically_eligible_rna",
        length=22,
        sequence=_rna(22),
    )
    reviews = []
    details = []
    for detail in (notation, boundary):
        review, local = _queue_pair(detail)
        reviews.append(review)
        details.append(local)
    _write_csv(
        checkpoint / "aptamerbase_checkpoint1_review.csv",
        list(DECISION_COLUMNS),
        reviews,
    )
    _write_csv(
        checkpoint / "aptamerbase_checkpoint1_local_detail.csv",
        list(LOCAL_DETAIL_COLUMNS),
        details,
    )
    result = prepare_aptamerbase_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "manual_review",
        expected_total_rows=2,
        expected_active_rows=2,
    )
    queue = list(csv.DictReader(result.output_queue.open(encoding="utf-8", newline="")))
    for row in queue:
        for name in MANUAL_FIELDS:
            assert row.get(name, "") == ""
    bulk = list(
        csv.DictReader(result.output_bulk_confirmation.open(encoding="utf-8", newline=""))
    )
    assert bulk[0]["confirm"] == ""
    assert bulk[0]["eligible_record_count"] == "1"
    audit_dir = checkpoint / "manual_review" / "audit"
    first_hash = _sha256(audit_dir / "aptamerbase_checkpoint1_notation_audit.csv")
    result2 = prepare_aptamerbase_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "manual_review",
        expected_total_rows=2,
        expected_active_rows=2,
    )
    assert result2.inputs_unchanged is True
    assert _sha256(audit_dir / "aptamerbase_checkpoint1_notation_audit.csv") == first_hash
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = validate_main(
            [
                "--source",
                "aptamerbase",
                "--repo-root",
                str(repo),
                "--checkpoint-dir",
                str(checkpoint),
            ]
        )
    assert code == 2
    out = stdout.getvalue()
    assert "unresolved_judgement_required=1" in out
    assert "audit_only_unconfirmed=1" in out
    assert "bulk_audit_confirmed=false" in out
    assert "ready_for_application=0" in out
    assert "CHECKPOINT-1 is not closed" in out
    integrity = json.loads(
        (audit_dir / "aptamerbase_checkpoint1_integrity.json").read_text(encoding="utf-8")
    )
    assert integrity["human_decisions_populated"] is False
    assert integrity["checkpoint_closed"] is False
    summary = (audit_dir / "aptamerbase_checkpoint1_audit_summary.md").read_text(
        encoding="utf-8"
    )
    assert "ACGU" not in summary
    assert "ACGT" not in summary


def test_biotin_placeholder_is_recoverable_without_guessing() -> None:
    seq = _dna(20) + "B" + _dna(5)
    row = _base_row(
        "aptamerbase:b",
        batch="01_sequence_or_source_conflict",
        reasons="sequence_notation",
        primary="ambiguous_bases",
        molecule="ssDNA",
        chemistry="DNA",
        alphabet="ambiguous",
        sequence=seq,
        qc="ambiguous_base|terminal_conjugate_present",
        modification="B = biotin-CE",
        rdf_rna="false",
        rdf_dna="true",
    )
    classified = classify_notation_row(row)
    assert classified["machine_recommendation"] == (
        "likely_modification_or_display_notation_recoverable"
    )
    assert classified["canonical_sequence_recoverable_without_guessing"] == "true"
    assert "B" not in classified["proposed_corrected_sequence"]
    assert row["sequence_raw"] == seq
    assert "ssdna_park" in classified["remaining_blocker_if_repaired"]

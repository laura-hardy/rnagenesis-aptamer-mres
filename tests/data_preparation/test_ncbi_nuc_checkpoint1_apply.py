"""NCBI Nucleotide CHECKPOINT-1 apply/dry-run tests (synthetic sequences only).

Does not read real NCBI aptamer sequences or consult ENA.
"""

from __future__ import annotations

import csv
import inspect
import io
import json
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadb_checkpoint1_review import BULK_CONFIRMATION_ID  # noqa: E402
from adapters.ncbi_nuc_checkpoint1_apply import (  # noqa: E402
    NCBI_NUC_APPLY_NOT_AUTHORISED,
    NCBI_NUC_TRACKED_RESOLUTION_COLUMNS,
    NcbiNucCheckpoint1ApplyError,
    refuse_unauthorised_apply,
    tracked_payload_contains_sequence,
)
from adapters.ncbi_nuc_checkpoint1_dry_run import (  # noqa: E402
    serialise_ncbi_nuc_simulation_sequence_free,
    simulate_ncbi_nuc_checkpoint1_application,
)
from adapters.ncbi_nuc_checkpoint1_review import (  # noqa: E402
    NcbiNucCheckpoint1ReviewError,
    apply_reviewed_record,
    apply_ncbi_nuc_checkpoint1_package,
    validate_ncbi_nuc_review_package,
)
from adapters.ncbi_nuc_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE,
    PRIMARY_ROUTE_REJECT,
    REJECTION_COLUMNS,
    REJECTION_STAGE,
)
from checkpoint1_apply_review import (  # noqa: E402
    Checkpoint1ApplyError,
    main,
    run_ncbi_nuc_checkpoint1_apply,
    run_ncbi_nuc_checkpoint1_dry_run,
)
from checkpoint1_prepare_review import (  # noqa: E402
    NCBI_NUC_MANUAL_REVIEW_COLUMNS,
    prepare_ncbi_nuc_checkpoint1_review,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402

SYNTHETIC_RNA_36 = "ACGU" * 9
SYNTHETIC_RNA_99 = "ACGU" * 24 + "ACG"
SYNTHETIC_DNA_36 = "ACGT" * 9
SYNTHETIC_SHORT = "ACGT" * 3
SYNTHETIC_N_12 = "ACGT" * 2 + "ACGN"
SYNTHETIC_PRIMER = "ACGT" * 8
RECOMMENDATIONS = (
    REPO_ROOT
    / "config"
    / "checkpoint_reviews"
    / "ncbi_nuc_checkpoint1_recommendations.json"
)


def _write_csv(path: Path, fieldnames: list[str] | tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _canonical(
    native_id: str,
    sequence: str,
    *,
    molecule: str,
    chemistry: str,
    alphabet: str,
    qc_flags: str = "",
    t_to_u_applied: str = "false",
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence))
    record.update(
        {
            "record_id": f"ncbi_nuc:{native_id}",
            "native_id": native_id,
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "unknown",
            "trim_status": "no_constants_detected",
            "trim_confidence": "n/a",
            "molecule_type": molecule,
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
            "qc_flags": qc_flags,
        }
    )
    return record


def _decision(
    canonical: dict[str, str],
    *,
    proposed: str,
    reason: str,
    route: str,
    secondary: str = "",
    batch: str = "",
    reasons: str = "",
    required: str = "true",
    priority: str = "high",
) -> dict[str, str]:
    row = {column: "" for column in DECISION_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "proposed_decision": proposed,
            "primary_reason": reason,
            "secondary_reasons": secondary,
            "primary_route": route,
            "manual_review_required": required,
            "manual_review_priority": priority,
            "review_batch": batch,
            "checkpoint_review_reasons": reasons,
            "checkpoint_status": "pending_checkpoint_1_review",
            "molecule_type": canonical["molecule_type"],
            "chemistry": canonical["chemistry"],
            "alphabet_as_reported": canonical["alphabet_as_reported"],
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


def _review(
    decision_row: dict[str, str],
    *,
    manual_decision: str,
    audit: bool = False,
    notes: str = "",
    **overrides: str,
) -> dict[str, str]:
    row = {column: "" for column in NCBI_NUC_MANUAL_REVIEW_COLUMNS}
    row.update(decision_row)
    row["audit_only_row"] = "true" if audit else "false"
    row["bulk_audit_eligible"] = "true" if audit else "false"
    row["manual_decision"] = "" if audit else manual_decision
    row["manual_notes"] = notes
    row.update(overrides)
    return row


def _rejection(canonical: dict[str, str], reason: str) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "source_db": canonical["source_db"],
        "source_dataset": canonical["source_dataset"],
        "native_id": canonical["native_id"],
        "sequence_raw": canonical["sequence_raw"],
        "target_name_raw": "",
        "stage": REJECTION_STAGE,
        "rejection_reason": reason,
        "rejection_detail": reason,
    }


def _park(decision_row: dict[str, str]) -> dict[str, str]:
    row = {column: "" for column in PARK_COLUMNS}
    row.update({column: decision_row.get(column, "") for column in PARK_COLUMNS})
    row["park_reason"] = decision_row["primary_reason"]
    return row


def _bulk(*record_ids: str, confirm: str = "true") -> dict[str, str]:
    return {
        "confirmation_id": BULK_CONFIRMATION_ID,
        "scope": "length_boundary_and_or_random_kept_audit_only",
        "eligible_record_count": str(len(record_ids)),
        "eligible_record_ids": "|".join(record_ids),
        "confirm": confirm,
        "reviewer_initials": "",
        "manual_notes": "",
    }


def _package() -> dict[str, object]:
    eligible = _canonical(
        "RNA36",
        SYNTHETIC_RNA_36,
        molecule="RNA",
        chemistry="RNA",
        alphabet="RNA",
        t_to_u_applied="true",
    )
    park = _canonical(
        "UNK36",
        SYNTHETIC_DNA_36,
        molecule="unknown",
        chemistry="unknown",
        alphabet="DNA_T",
    )
    short_park = _canonical(
        "SHORT",
        SYNTHETIC_SHORT,
        molecule="unknown",
        chemistry="unknown",
        alphabet="DNA_T",
        qc_flags="core_below_min_length",
    )
    ambig = _canonical(
        "AMBIG",
        SYNTHETIC_N_12,
        molecule="unknown",
        chemistry="unknown",
        alphabet="ambiguous",
        qc_flags="ambiguous_base|core_below_min_length",
    )
    primer = _canonical(
        "PRIMER",
        SYNTHETIC_PRIMER,
        molecule="unknown",
        chemistry="unknown",
        alphabet="DNA_T",
    )
    method = _canonical(
        "METHOD",
        SYNTHETIC_DNA_36,
        molecule="DNA",
        chemistry="DNA",
        alphabet="DNA_T",
        qc_flags="possible_non_aptamer_source_object",
    )
    decisions = [
        _decision(
            eligible,
            proposed="proposed_accept",
            reason="technically_eligible_rna",
            route=PRIMARY_ROUTE_ELIGIBLE,
            secondary="random_accept_audit",
            batch="05_random_kept_audit",
            reasons="random_kept_audit",
            priority="low",
        ),
        _decision(
            park,
            proposed="proposed_park",
            reason="molecule_type_unresolved",
            route=PRIMARY_ROUTE_MOLECULE,
            batch="02_molecule_type_unresolved",
            reasons="molecule_type_unresolved",
        ),
        _decision(
            short_park,
            proposed="proposed_park",
            reason="molecule_type_unresolved",
            route=PRIMARY_ROUTE_MOLECULE,
            secondary="length_out_of_range",
            batch="02_molecule_type_unresolved",
            reasons="molecule_type_unresolved",
        ),
        _decision(
            ambig,
            proposed="proposed_park",
            reason="molecule_type_unresolved",
            route=PRIMARY_ROUTE_MOLECULE,
            secondary="ambiguous_bases|length_out_of_range",
            batch="02_molecule_type_unresolved",
            reasons="molecule_type_unresolved",
        ),
        _decision(
            primer,
            proposed="proposed_reject",
            reason="primer_like",
            route=PRIMARY_ROUTE_REJECT,
            batch="01_judgement_dependent_technical",
            reasons="judgement_dependent_technical",
        ),
        _decision(
            method,
            proposed="proposed_reject",
            reason="non_aptamer_source_object",
            route=PRIMARY_ROUTE_REJECT,
            secondary="length_out_of_range",
            batch="01_judgement_dependent_technical",
            reasons="judgement_dependent_technical",
        ),
    ]
    canonicals = [eligible, park, short_park, ambig, primer, method]
    queue = [
        _review(decisions[0], manual_decision="", audit=True),
        _review(decisions[1], manual_decision="keep"),
        _review(decisions[2], manual_decision="keep"),
        _review(decisions[3], manual_decision="keep"),
        _review(decisions[4], manual_decision="keep"),
        _review(decisions[5], manual_decision="keep"),
    ]
    return {
        "canonical": canonicals,
        "decisions": decisions,
        "queue": queue,
        "rejections": [
            _rejection(primer, "primer_like"),
            _rejection(method, "non_aptamer_source_object"),
        ],
        "parked": [_park(decisions[1]), _park(decisions[2]), _park(decisions[3])],
        "bulk": _bulk(eligible["record_id"]),
    }


def _simulate(package: dict[str, object], **overrides: object):
    return simulate_ncbi_nuc_checkpoint1_application(
        queue_rows=overrides.get("queue_rows", package["queue"]),
        group_rows=overrides.get("group_rows", []),
        canonical_rows=package["canonical"],
        decision_rows=package["decisions"],
        existing_rejection_rows=package["rejections"],
        existing_parked_rows=package["parked"],
        bulk_confirmation=overrides.get("bulk_confirmation", package["bulk"]),
        expected_source_rows=overrides.get("expected_source_rows", 6),
        expected_reviewed_rows=overrides.get("expected_reviewed_rows", 6),
    )


def test_keep_preserves_accept_park_and_reject_routes() -> None:
    simulation = _simulate(_package())
    by_id = {row["native_id"]: row for row in simulation.change_report}
    assert by_id["RNA36"]["post_review_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert by_id["UNK36"]["post_review_route"] == PRIMARY_ROUTE_MOLECULE
    assert by_id["PRIMER"]["post_review_route"] == PRIMARY_ROUTE_REJECT
    assert by_id["METHOD"]["post_review_route"] == PRIMARY_ROUTE_REJECT
    assert simulation.stats["technically_eligible"] == 1
    assert simulation.stats["parked_molecule_unresolved"] == 3
    assert simulation.stats["technical_rejects_after_review"] == 2
    assert simulation.stats["projected_authorised_for_s4"] == 1
    assert simulation.stats["authorised_for_s4"] == 0
    assert simulation.stats["route_changed"] == 0
    assert simulation.nogo_reasons == ()


def test_bulk_audit_confirmation_preserves_accept() -> None:
    simulation = _simulate(_package())
    eligible_ids = {row["native_id"] for row in simulation.preview_eligible}
    assert eligible_ids == {"RNA36"}
    assert simulation.preview_eligible[0]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE


def test_keep_does_not_mutate_sequence_molecule_chemistry_or_trim() -> None:
    package = _package()
    simulation = _simulate(package)
    original = {row["record_id"]: row for row in package["canonical"]}
    for row in simulation.preview_canonical:
        before = original[row["record_id"]]
        assert row["sequence_raw"] == before["sequence_raw"]
        assert row["sequence_full"] == before["sequence_full"]
        assert row["sequence_core"] == before["sequence_core"]
        assert row["sequence_core"] == row["sequence_full"]
        assert row["molecule_type"] == before["molecule_type"]
        assert row["chemistry"] == before["chemistry"]
        assert row["t_to_u_applied"] == before["t_to_u_applied"]
        assert row["trim_status"] == "no_constants_detected"
    assert simulation.stats["sequence_corrections"] == 0
    assert simulation.stats["molecule_overrides"] == 0
    assert simulation.stats["chemistry_overrides"] == 0
    assert simulation.stats["records_trimmed"] == 0


def test_primer_like_and_non_aptamer_remain_reject() -> None:
    simulation = _simulate(_package())
    rejects = {row["native_id"]: row for row in simulation.preview_rejections}
    assert rejects["PRIMER"]["rejection_reason"] == "primer_like"
    assert rejects["METHOD"]["rejection_reason"] == "non_aptamer_source_object"
    assert rejects["METHOD"]["native_id"] == "METHOD"


def test_unresolved_molecule_park_keeps_secondary_length_and_ambiguity() -> None:
    simulation = _simulate(_package())
    parks = {row["native_id"]: row for row in simulation.preview_parked}
    assert parks["SHORT"]["park_reason"] == "molecule_type_unresolved"
    assert "length_out_of_range" in parks["SHORT"]["secondary_reasons"]
    assert parks["AMBIG"]["park_reason"] == "molecule_type_unresolved"
    assert "ambiguous_bases" in parks["AMBIG"]["secondary_reasons"]
    authorised = {row["native_id"] for row in simulation.preview_eligible}
    assert "SHORT" not in authorised
    assert "AMBIG" not in authorised
    assert "PRIMER" not in authorised


def test_only_reviewed_accepts_are_projected_authorised() -> None:
    simulation = _simulate(_package())
    assert simulation.stats["projected_authorised_for_s4"] == 1
    for item in simulation.applied:
        if item.primary_route_after != PRIMARY_ROUTE_ELIGIBLE:
            assert item.canonical["record_id"] not in {
                row["record_id"] for row in simulation.preview_eligible
            }


def test_unresolved_review_refuses_dry_run() -> None:
    package = _package()
    queue = [dict(row) for row in package["queue"]]
    queue[1]["manual_decision"] = ""
    report = validate_ncbi_nuc_review_package(
        queue_rows=queue,
        group_rows=[],
        bulk_confirmation=package["bulk"],
    )
    assert not report.ok
    with pytest.raises(NcbiNucCheckpoint1ReviewError, match="remain unresolved"):
        apply_ncbi_nuc_checkpoint1_package(
            queue_rows=queue,
            group_rows=[],
            canonical_by_id={row["record_id"]: row for row in package["canonical"]},
            decision_by_id={row["record_id"]: row for row in package["decisions"]},
            rejection_by_id={row["record_id"]: row for row in package["rejections"]},
            park_by_id={row["record_id"]: row for row in package["parked"]},
            bulk_confirmation=package["bulk"],
        )


def test_unconfirmed_audit_refuses_dry_run() -> None:
    package = _package()
    bulk = _bulk("ncbi_nuc:RNA36", confirm="false")
    report = validate_ncbi_nuc_review_package(
        queue_rows=package["queue"],
        group_rows=[],
        bulk_confirmation=bulk,
    )
    assert not report.ok
    assert report.audit_only_unconfirmed == 1
    with pytest.raises(NcbiNucCheckpoint1ReviewError):
        _simulate(package, bulk_confirmation=bulk)


def test_keep_with_override_fields_refuses() -> None:
    package = _package()
    queue = [dict(row) for row in package["queue"]]
    queue[1]["manual_molecule_type_override"] = "RNA"
    report = validate_ncbi_nuc_review_package(
        queue_rows=queue,
        group_rows=[],
        bulk_confirmation=package["bulk"],
    )
    assert not report.ok
    with pytest.raises(NcbiNucCheckpoint1ReviewError, match="must not populate"):
        apply_reviewed_record(
            canonical=package["canonical"][1],
            review_row=queue[1],
            decision_row=package["decisions"][1],
            park_row=package["parked"][0],
        )


def test_malformed_human_action_refuses() -> None:
    package = _package()
    queue = [dict(row) for row in package["queue"]]
    queue[1]["manual_decision"] = "force_accept"
    report = validate_ncbi_nuc_review_package(
        queue_rows=queue,
        group_rows=[],
        bulk_confirmation=package["bulk"],
    )
    assert not report.ok
    with pytest.raises(NcbiNucCheckpoint1ReviewError):
        apply_reviewed_record(
            canonical=package["canonical"][1],
            review_row=queue[1],
            decision_row=package["decisions"][1],
            park_row=package["parked"][0],
        )


def test_edit_is_refused() -> None:
    package = _package()
    queue = [dict(row) for row in package["queue"]]
    queue[1]["manual_decision"] = "edit"
    queue[1]["manual_sequence_corrected"] = SYNTHETIC_RNA_36
    report = validate_ncbi_nuc_review_package(
        queue_rows=queue,
        group_rows=[],
        bulk_confirmation=package["bulk"],
    )
    assert not report.ok
    with pytest.raises(NcbiNucCheckpoint1ReviewError, match="does not consume edit"):
        apply_reviewed_record(
            canonical=package["canonical"][1],
            review_row=queue[1],
            decision_row=package["decisions"][1],
            park_row=package["parked"][0],
        )


def test_s4_fields_stay_empty_and_no_dedup() -> None:
    simulation = _simulate(_package())
    assert len(simulation.preview_canonical) == 6
    for row in simulation.preview_canonical:
        for field_name in S3_FORBIDDEN_FIELDS:
            assert row.get(field_name, "") == ""
        assert row.get("target_name", "") == ""
        assert row.get("accession", "") == ""
        assert row.get("target_name_raw", "") == ""


def test_simulate_does_not_consult_ena() -> None:
    source = inspect.getsource(simulate_ncbi_nuc_checkpoint1_application)
    assert "ena_" not in source
    assert "ENA" not in inspect.signature(simulate_ncbi_nuc_checkpoint1_application).parameters
    simulation = _simulate(_package())
    assert simulation.stats["total_records"] == 6


def test_dry_run_is_deterministic() -> None:
    package = _package()
    first = serialise_ncbi_nuc_simulation_sequence_free(_simulate(package))
    second = serialise_ncbi_nuc_simulation_sequence_free(_simulate(package))
    assert first == second


def test_drop_converts_route_without_being_keep() -> None:
    package = _package()
    review = dict(package["queue"][0])
    review["manual_decision"] = "drop"
    review["audit_only_row"] = "false"
    result = apply_reviewed_record(
        canonical=package["canonical"][0],
        review_row=review,
        decision_row=package["decisions"][0],
    )
    assert result.primary_route_before == PRIMARY_ROUTE_ELIGIBLE
    assert result.primary_route_after == PRIMARY_ROUTE_REJECT
    assert result.primary_reason == "manual_reject"


def _build_dispatcher_fixture(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    rec_dir = repo / "config" / "checkpoint_reviews"
    rec_dir.mkdir(parents=True)
    shutil.copy(RECOMMENDATIONS, rec_dir / "ncbi_nuc_checkpoint1_recommendations.json")
    checkpoint = repo / "data" / "interim" / "checkpoints" / "ncbi_nuc_cp1"
    package = _package()
    reviews = []
    details = []
    for decision, canonical in zip(package["decisions"], package["canonical"], strict=True):
        reviews.append(decision)
        detail = {column: decision.get(column, "") for column in LOCAL_DETAIL_COLUMNS}
        detail.update(
            {
                "sequence_raw": canonical["sequence_raw"],
                "sequence_full": canonical["sequence_full"],
                "sequence_core": canonical["sequence_core"],
            }
        )
        details.append(detail)
    _write_csv(checkpoint / "ncbi_nuc_checkpoint1_review.csv", DECISION_COLUMNS, reviews)
    _write_csv(
        checkpoint / "ncbi_nuc_checkpoint1_local_detail.csv",
        LOCAL_DETAIL_COLUMNS,
        details,
    )
    from common.corpus_schema import CORPUS_COLUMNS

    _write_csv(checkpoint / "ncbi_nuc_s3_canonical.csv", CORPUS_COLUMNS, package["canonical"])
    _write_csv(checkpoint / "ncbi_nuc_s3_decisions.csv", DECISION_COLUMNS, package["decisions"])
    _write_csv(checkpoint / "rejected_ncbi_nuc.csv", REJECTION_COLUMNS, package["rejections"])
    _write_csv(checkpoint / "ncbi_nuc_s3_parked.csv", PARK_COLUMNS, package["parked"])
    prepare_ncbi_nuc_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "manual_review",
        expected_active_rows=6,
        expected_total_rows=6,
    )
    queue_path = checkpoint / "manual_review" / "ncbi_nuc_checkpoint1_manual_review.csv"
    with queue_path.open(encoding="utf-8", newline="") as handle:
        queue = list(csv.DictReader(handle))
    for row in queue:
        if row["audit_only_row"].lower() == "true":
            continue
        row["manual_decision"] = "keep"
        row["manual_notes"] = "keep current route"
    _write_csv(queue_path, NCBI_NUC_MANUAL_REVIEW_COLUMNS, queue)
    bulk_path = (
        checkpoint / "manual_review" / "ncbi_nuc_checkpoint1_bulk_audit_confirmation.csv"
    )
    with bulk_path.open(encoding="utf-8", newline="") as handle:
        bulk_rows = list(csv.DictReader(handle))
    bulk_rows[0]["confirm"] = "true"
    _write_csv(
        bulk_path,
        list(bulk_rows[0].keys()),
        bulk_rows,
    )
    return repo, checkpoint


def test_dispatcher_dry_run_does_not_write_resolved(tmp_path: Path) -> None:
    repo, checkpoint = _build_dispatcher_fixture(tmp_path)
    dry_dir = checkpoint / "dry_run"
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        run_ncbi_nuc_checkpoint1_dry_run(
            repo_root=repo,
            checkpoint_dir=checkpoint,
            output_dir=dry_dir,
            check_deterministic_rerun=True,
            expected_source_rows=6,
            expected_reviewed_rows=6,
            verify_frozen_inputs=False,
            compare_to_pristine=True,
        )
    assert not (checkpoint / "resolved").exists()
    assert "CHECKPOINT-1 is not closed" in buf.getvalue()
    assert (dry_dir / "ncbi_nuc_checkpoint1_dry_run_canonical_preview.csv").is_file()
    assert not (repo / "config" / "global_s4_sources" / "ncbi_nuc.json").exists()


def test_cli_actual_apply_is_refused_without_flag(tmp_path: Path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "ncbi_nuc",
                "--repo-root",
                str(tmp_path),
            ]
        )
    assert code == 1
    assert "not authorised" in stderr.getvalue()
    with pytest.raises(NcbiNucCheckpoint1ApplyError, match="not authorised"):
        refuse_unauthorised_apply()
    with pytest.raises(Checkpoint1ApplyError, match="not authorised"):
        run_ncbi_nuc_checkpoint1_apply()
    assert "--authorise-actual-apply" in NCBI_NUC_APPLY_NOT_AUTHORISED
    assert "--dry-run" in NCBI_NUC_APPLY_NOT_AUTHORISED


def test_cli_dry_run_missing_review_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "data" / "interim" / "checkpoints" / "ncbi_nuc_cp1").mkdir(parents=True)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "ncbi_nuc",
                "--dry-run",
                "--repo-root",
                str(repo),
                "--skip-pipeline-integrity",
                "--expected-total-rows",
                "6",
                "--expected-active-rows",
                "6",
            ]
        )
    assert code == 1
    assert "Missing NCBI Nucleotide manual-review CSV" in stderr.getvalue()


def test_dispatcher_apply_matches_dry_run_and_closes(tmp_path: Path) -> None:
    repo, checkpoint = _build_dispatcher_fixture(tmp_path)
    dry_dir = checkpoint / "dry_run"
    resolved = checkpoint / "resolved"
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        run_ncbi_nuc_checkpoint1_dry_run(
            repo_root=repo,
            checkpoint_dir=checkpoint,
            output_dir=dry_dir,
            check_deterministic_rerun=True,
            expected_source_rows=6,
            expected_reviewed_rows=6,
            verify_frozen_inputs=False,
            compare_to_pristine=True,
        )
        result = run_ncbi_nuc_checkpoint1_apply(
            repo_root=repo,
            checkpoint_dir=checkpoint,
            output_dir=resolved,
            tracked_manifest=repo
            / "config/checkpoint_reviews/ncbi_nuc_checkpoint1_resolutions.csv",
            metadata_out=repo
            / "config/checkpoint_reviews/ncbi_nuc_checkpoint1_metadata.json",
            check_deterministic_rerun=True,
            expected_source_rows=6,
            expected_reviewed_rows=6,
            verify_frozen_inputs=False,
            compare_to_pristine=True,
            compare_to_preview=True,
            authorise_actual_apply=True,
        )
    assert result.checkpoint_closed is True
    assert result.semantic_mismatches == 0
    assert result.byte_mismatches == 0
    assert result.preview_comparison_ok is True
    assert result.stats["technically_eligible"] == 1
    assert result.stats["parked_molecule_unresolved"] == 3
    assert result.stats["technical_rejects_after_review"] == 2
    assert result.stats["authorised_for_s4"] == 1
    canonical = dry_dir / "ncbi_nuc_checkpoint1_dry_run_canonical_preview.csv"
    applied = resolved / "ncbi_nuc_checkpoint1_applied_canonical.csv"
    assert canonical.read_bytes() == applied.read_bytes()
    assert (resolved / "ncbi_nuc_checkpoint1_s4_authorised_ids.csv").is_file()
    assert not (repo / "config/global_s4_sources/ncbi_nuc.json").exists()
    metadata = json.loads(
        (
            repo / "config/checkpoint_reviews/ncbi_nuc_checkpoint1_metadata.json"
        ).read_text(encoding="utf-8")
    )
    assert metadata["checkpoint_closed"] is True
    assert metadata["global_s4_handoff_prepared"] is False
    assert metadata["global_s4_run"] is False
    assert metadata["ncbi_ena_deduplication_performed"] is False
    assert metadata["authorised_for_s4"] == 1
    assert "final corpus" in metadata["authorised_for_s4_meaning"]
    tracked = repo / "config/checkpoint_reviews/ncbi_nuc_checkpoint1_resolutions.csv"
    text = tracked.read_text(encoding="utf-8")
    assert not tracked_payload_contains_sequence(text)
    assert SYNTHETIC_RNA_36 not in text
    rows = list(csv.DictReader(tracked.open(encoding="utf-8")))
    assert list(rows[0].keys()) == list(NCBI_NUC_TRACKED_RESOLUTION_COLUMNS)
    eligible = [row for row in rows if row["authorised_for_s4"] == "true"]
    assert {row["native_id"] for row in eligible} == {"RNA36"}
    parks = [row for row in rows if row["resolved_decision"] == "park"]
    rejects = [row for row in rows if row["resolved_decision"] == "reject"]
    assert len(parks) == 3
    assert len(rejects) == 2
    summary = (resolved / "ncbi_nuc_checkpoint1_resolution_summary.md").read_text(
        encoding="utf-8"
    )
    assert "CHECKPOINT-1 CLOSED" in summary
    assert SYNTHETIC_RNA_36 not in summary


def test_cli_apply_with_authorisation(tmp_path: Path) -> None:
    repo, checkpoint = _build_dispatcher_fixture(tmp_path)
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        dry_code = main(
            [
                "--source",
                "ncbi_nuc",
                "--dry-run",
                "--repo-root",
                str(repo),
                "--checkpoint-dir",
                str(checkpoint),
                "--expected-total-rows",
                "6",
                "--expected-active-rows",
                "6",
                "--skip-pipeline-integrity",
            ]
        )
        apply_code = main(
            [
                "--source",
                "ncbi_nuc",
                "--authorise-actual-apply",
                "--repo-root",
                str(repo),
                "--checkpoint-dir",
                str(checkpoint),
                "--expected-total-rows",
                "6",
                "--expected-active-rows",
                "6",
                "--skip-pipeline-integrity",
            ]
        )
    assert dry_code == 0
    assert apply_code == 0
    assert "checkpoint_closed=true" in buf.getvalue()
    assert (checkpoint / "resolved" / "ncbi_nuc_checkpoint1_applied_canonical.csv").is_file()

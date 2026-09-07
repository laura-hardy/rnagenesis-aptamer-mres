"""Tests for the ENA S2 adapter (synthetic sequences only).

Every literal nucleotide string in this file is shorter than 20 nt, except
programmatically generated homopolymers used to exercise length QC and
group-consensus inference. Does not read real ENA aptamer sequences except
in the optional local-only production skipif gate, which asserts counts
without embedding sequences in this file.
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.ena import SIDECAR_COLUMNS  # noqa: E402
from adapters.ena_s2 import (  # noqa: E402
    GROUP_INFERENCE_KEY,
    EnaS2Error,
    assert_no_legacy_ena_normaliser_import,
    load_ena_policy,
    normalise_ena_record,
    resolve_ena_molecule_and_chemistry,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S2_FORBIDDEN_FIELDS,
    empty_corpus_record,
)
from common.sequence_normalisation import load_normalisation_rules  # noqa: E402
from s2_normalise import (  # noqa: E402
    S2NormaliseError,
    run_ena_s2,
    run_s2_normalisation,
)

POLICY_PATH = REPO_ROOT / "config" / "source_normalisation" / "ena.json"
RULES_PATH = REPO_ROOT / "config" / "sequence_normalisation_rules.json"
PRODUCTION_S1 = REPO_ROOT / "data" / "interim" / "extracted" / "ena_extracted.csv"
PRODUCTION_SIDECAR = (
    REPO_ROOT / "data" / "interim" / "extracted" / "ena_source_metadata.csv"
)
PRODUCTION_RAW = (
    REPO_ROOT
    / "data"
    / "raw"
    / "ENA"
    / "review_v2"
    / "ena_selected_after_manual_review.csv"
)
EXPECTED_SOURCE_DATASET = "ena_selected_v2_2026-08"
SHARED_T7 = "TAATACGACTCACTATA"


def _meta(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row["record_id"] = "ena:ru001"
    row["review_unit_id"] = "ru001"
    row["sequence"] = "ACGUAC"
    row["target"] = "demo_target"
    row["experiment_group_id"] = "g1"
    row["ena_source_family_id_was_blank"] = "true"
    row["ena_effective_near_duplicate_family_id"] = "ena_singleton_ru001"
    row["ena_effective_near_duplicate_family_size"] = "1"
    row["sequence_length"] = "6"
    row.update(overrides)
    return row


def _s1(**overrides: str) -> dict[str, str]:
    record = empty_corpus_record()
    record.update(
        {
            "record_id": "ena:ru001",
            "sequence_raw": "ACGUAC",
            "source_db": "ena",
            "source_dataset": EXPECTED_SOURCE_DATASET,
            "contributing_sources": "ena",
            "contributing_datasets": EXPECTED_SOURCE_DATASET,
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": "ru001",
            "target_name_raw": "demo_target",
            "publication": "",
            "doi": "",
            "pubmed_id": "",
            "notes": "",
        }
    )
    record.update(overrides)
    return record


def _write_inputs(
    input_dir: Path,
    canonical_rows: list[dict[str, str]],
    sidecar_rows: list[dict[str, str]],
) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    with (input_dir / "ena_extracted.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(CORPUS_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        for row in canonical_rows:
            writer.writerow({col: row.get(col, "") for col in CORPUS_COLUMNS})
    with (input_dir / "ena_source_metadata.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(SIDECAR_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        for row in sidecar_rows:
            writer.writerow({col: row.get(col, "") for col in SIDECAR_COLUMNS})


def _runner_pair(
    tmp_path: Path,
    canonical_rows: list[dict[str, str]],
    sidecar_rows: list[dict[str, str]],
) -> tuple[Path, Path, Path]:
    repo_root = tmp_path / "repo"
    input_dir = repo_root / "data" / "interim" / "extracted"
    output_dir = repo_root / "data" / "interim" / "normalised"
    _write_inputs(input_dir, canonical_rows, sidecar_rows)
    return repo_root, input_dir, output_dir


@pytest.fixture(scope="module")
def policy():
    return load_ena_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def rules():
    return load_normalisation_rules()


# --- Policy / molecule contract ---


def test_policy_is_fixed_rna_with_experiment_group_grouping(policy) -> None:
    assert policy.source_key == "ena"
    assert policy.molecule_type == "RNA"
    assert policy.chemistry == "RNA"
    assert policy.group_inference_key == GROUP_INFERENCE_KEY
    assert policy.group_inference_sidecar_field == "experiment_group_id"
    assert policy.apply_approved_trims is False
    assert policy.do_not_use_supporting_group_ids is True
    assert policy.do_not_use_family_id_as_group is True
    assert policy.do_not_infer_molecule_from_alphabet is True


def test_grouping_mode_other_than_experiment_group_id_hard_fails(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad_policy.json"
    path.write_text(
        json.dumps(
            {
                "source_key": "ena",
                "contract_version": "1.0",
                "molecule_type": "RNA",
                "chemistry": "RNA",
                "molecule_evidence_source": "source_contract",
                "reported_length_field": "sequence_length",
                "group_inference_sidecar_field": "experiment_group_id",
                "apply_approved_trims": False,
                "group_inference_key": "target_name_raw_plus_publication",
                "do_not_use_supporting_group_ids": True,
                "do_not_use_family_id_as_group": True,
                "do_not_infer_molecule_from_alphabet": True,
                "do_not_apply_inferred_trims": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EnaS2Error, match="experiment_group_id"):
        load_ena_policy(path)


def test_fixed_rna_molecule_from_contract(policy) -> None:
    result = resolve_ena_molecule_and_chemistry(policy)
    assert result.molecule_type == "RNA"
    assert result.chemistry == "RNA"
    assert result.evidence_source == "source_contract"


def test_molecule_not_inferred_from_alphabet(policy, rules) -> None:
    result = normalise_ena_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(sequence="ACGTAC"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "RNA"
    assert result.canonical["alphabet_as_reported"] == "DNA_T"


# --- Alphabet / T→U ---


def test_rna_u_no_transcription(policy, rules) -> None:
    result = normalise_ena_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["alphabet_as_reported"] == "RNA"
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGUAC"


def test_t_encoded_rna_transcribed_not_ssdna(policy, rules) -> None:
    result = normalise_ena_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(sequence="ACGTAC"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["alphabet_as_reported"] == "DNA_T"
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "RNA"
    assert result.canonical["t_to_u_applied"] == "true"
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert result.canonical["sequence_raw"] == "ACGTAC"
    assert "T" not in result.canonical["sequence_full"]
    assert "U" in result.canonical["sequence_full"]


def test_mixed_t_u_not_silently_transcribed(policy, rules) -> None:
    result = normalise_ena_record(
        _s1(sequence_raw="ACGTU"),
        _meta(sequence="ACGTU"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_full"] == "ACGTU"
    assert result.canonical["t_to_u_applied"] == "false"
    assert "mixed_t_u" in result.canonical["qc_flags"]


# --- Provenance ---


def test_sequence_raw_unchanged_and_reviewed_sequence_used(policy, rules) -> None:
    s1 = _s1(sequence_raw="acguac")
    result = normalise_ena_record(
        s1,
        _meta(
            sequence="acguac",
            sequence_original="ACGTACGT",
            manual_sequence_corrected="1",
            sequence_corrected_applied="1",
        ),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == "acguac"
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert result.qc["sequence_corrected_applied"] == "1"
    assert "ACGTACGT" not in result.canonical["sequence_full"]


def test_correction_metadata_not_overwritten(policy, rules) -> None:
    result = normalise_ena_record(
        _s1(),
        _meta(
            sequence_original="AAAAAA",
            manual_sequence_corrected="1",
            sequence_corrected_applied="1",
            sequence_quality_status="ok",
            automatic_concern_flags="",
        ),
        policy=policy,
        rules=rules,
    )
    assert result.qc["sequence_corrected_applied"] == "1"
    assert result.qc["sequence_quality_status"] == "ok"


def test_s4_fields_remain_empty(policy, rules) -> None:
    result = normalise_ena_record(_s1(), _meta(), policy=policy, rules=rules)
    for field in S2_FORBIDDEN_FIELDS:
        assert result.canonical[field] == ""


def test_no_deduplication_of_identical_sequence_full(tmp_path: Path) -> None:
    rows = [
        _s1(record_id="ena:ru001", native_id="ru001", sequence_raw="ACGTAC"),
        _s1(record_id="ena:ru002", native_id="ru002", sequence_raw="ACGUAC"),
    ]
    sidecar = [
        _meta(record_id="ena:ru001", review_unit_id="ru001", sequence="ACGTAC"),
        _meta(
            record_id="ena:ru002",
            review_unit_id="ru002",
            sequence="ACGUAC",
            experiment_group_id="g2",
        ),
    ]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_ena_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
    )
    assert result.stats.s2_rows == 2
    with result.output_normalised.open(encoding="utf-8", newline="") as handle:
        out_rows = list(csv.DictReader(handle))
    assert len(out_rows) == 2
    assert out_rows[0]["sequence_full"] == out_rows[1]["sequence_full"] == "ACGUAC"
    assert result.stats.exact_duplicate_sequence_full_values == 1
    report = result.output_report.read_text(encoding="utf-8")
    assert "diagnostic only — no deduplication performed" in report


# --- Known motifs ---


def test_known_motif_does_not_trim(policy, rules) -> None:
    result = normalise_ena_record(
        _s1(sequence_raw=SHARED_T7 + "AC"),
        _meta(sequence=SHARED_T7 + "AC"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert result.canonical["trim_status"] == "constants_suspected_unresolved"
    assert result.canonical["trim_confidence"] == "n/a"
    assert "known_promoter_detected" in result.canonical["qc_flags"]


def test_source_promoter_flag_is_not_trim_authorisation(policy, rules) -> None:
    result = normalise_ena_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(
            automatic_concern_flags="t7_promoter",
            sequence_quality_status="promoter_or_template_requires_review",
        ),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert result.qc["source_promoter_or_template_concern"] == "true"
    assert result.qc["source_t7_concern"] == "true"
    assert result.canonical["trim_status"] == "no_constants_detected"


# --- Group inference ---


def _group_rows(
    *,
    group_id: str,
    count: int,
    prefix: str,
    tails: list[str],
    supporting: str = "",
    family_id: str = "",
    start: int = 1,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    canonical = []
    sidecar = []
    for offset, tail in enumerate(tails[:count]):
        index = start + offset
        native = f"ru{index:03d}"
        record_id = f"ena:{native}"
        canonical.append(
            _s1(
                record_id=record_id,
                native_id=native,
                sequence_raw=prefix + tail,
                target_name_raw="demo_target",
            )
        )
        sidecar.append(
            _meta(
                record_id=record_id,
                review_unit_id=native,
                sequence=prefix + tail,
                experiment_group_id=group_id,
                experiment_group_ids=supporting,
                near_duplicate_family_id=family_id,
                ena_effective_near_duplicate_family_id=family_id or f"ena_singleton_{native}",
                sequence_length=str(len(prefix + tail)),
            )
        )
    return canonical, sidecar


def test_qualifying_group_emits_unapplied_medium_proposal(tmp_path: Path) -> None:
    prefix = "AAAAAAAAAAAA"
    tails = ["CCCC", "GGGG", "UUUU", "CCGG", "GGCC"]
    canonical, sidecar = _group_rows(group_id="g_big", count=5, prefix=prefix, tails=tails)
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, canonical, sidecar)
    result = run_ena_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=5,
    )
    assert result.stats.s2_rows == 5
    assert result.stats.core_differs_from_full == 0
    assert result.stats.applied_trims == 0
    assert result.stats.five_prime_proposals >= 1
    assert result.stats.primary_experiment_groups == 1
    with result.output_normalised.open(encoding="utf-8", newline="") as handle:
        out_rows = list(csv.DictReader(handle))
    for row in out_rows:
        assert row["sequence_core"] == row["sequence_full"]
        assert row["experiment_group_id"] == ""
    with result.output_proposals.open(encoding="utf-8", newline="") as handle:
        proposals = list(csv.DictReader(handle))
    group_rows = [p for p in proposals if p["proposal_source"] == "group_consensus"]
    assert group_rows
    assert all(p["applied"] == "false" for p in group_rows)
    assert all(p["confidence"] == "medium" for p in group_rows)
    with result.output_review.open(encoding="utf-8", newline="") as handle:
        review = list(csv.DictReader(handle))
    assert any(row["group_consensus_proposal"] == "true" for row in review)


def test_group_below_minimum_produces_no_motif_proposal(tmp_path: Path) -> None:
    prefix = "AAAAAAAAAAAA"
    tails = ["CCCC", "GGGG", "UUUU", "CCGG"]
    canonical, sidecar = _group_rows(group_id="g_small", count=4, prefix=prefix, tails=tails)
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, canonical, sidecar)
    result = run_ena_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=4,
    )
    assert result.stats.groups_considered == 1
    assert result.stats.groups_meeting_min_size == 0
    assert result.stats.five_prime_proposals == 0
    assert result.stats.three_prime_proposals == 0
    with result.output_proposals.open(encoding="utf-8", newline="") as handle:
        proposals = list(csv.DictReader(handle))
    assert all(p["proposal_source"] != "group_consensus" for p in proposals)


def test_supporting_group_ids_are_not_primary_grouping(tmp_path: Path) -> None:
    prefix = "AAAAAAAAAAAA"
    tails = ["CCCC", "GGGG", "UUUU", "CCGG", "GGCC"]
    canonical = []
    sidecar = []
    for index, tail in enumerate(tails, start=1):
        native = f"ru{index:03d}"
        canonical.append(
            _s1(
                record_id=f"ena:{native}",
                native_id=native,
                sequence_raw=prefix + tail,
            )
        )
        sidecar.append(
            _meta(
                record_id=f"ena:{native}",
                review_unit_id=native,
                sequence=prefix + tail,
                experiment_group_id=f"primary_{index}",
                experiment_group_ids="shared_a|shared_b",
                sequence_length=str(len(prefix + tail)),
            )
        )
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, canonical, sidecar)
    result = run_ena_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=5,
    )
    assert result.stats.primary_experiment_groups == 5
    assert result.stats.supporting_group_ids_expanded == 2
    assert result.stats.groups_considered == 5
    assert result.stats.five_prime_proposals == 0
    assert result.stats.three_prime_proposals == 0


def test_family_id_is_not_grouping_key(tmp_path: Path) -> None:
    prefix = "AAAAAAAAAAAA"
    tails = ["CCCC", "GGGG", "UUUU", "CCGG", "GGCC"]
    canonical = []
    sidecar = []
    for index, tail in enumerate(tails, start=1):
        native = f"ru{index:03d}"
        canonical.append(
            _s1(
                record_id=f"ena:{native}",
                native_id=native,
                sequence_raw=prefix + tail,
            )
        )
        sidecar.append(
            _meta(
                record_id=f"ena:{native}",
                review_unit_id=native,
                sequence=prefix + tail,
                experiment_group_id=f"primary_{index}",
                near_duplicate_family_id="family_shared",
                ena_effective_near_duplicate_family_id="family_shared",
                ena_effective_near_duplicate_family_size="5",
                ena_source_family_id_was_blank="false",
                sequence_length=str(len(prefix + tail)),
            )
        )
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, canonical, sidecar)
    sidecar_before = (input_dir / "ena_source_metadata.csv").read_bytes()
    result = run_ena_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=5,
    )
    assert result.stats.five_prime_proposals == 0
    assert result.stats.primary_experiment_groups == 5
    assert result.stats.nonblank_source_family_ids == 5
    assert (input_dir / "ena_source_metadata.csv").read_bytes() == sidecar_before
    with (input_dir / "ena_source_metadata.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        after = list(csv.DictReader(handle))
    assert all(row["near_duplicate_family_id"] == "family_shared" for row in after)
    assert all(
        row["ena_effective_near_duplicate_family_id"] == "family_shared" for row in after
    )


def test_sidecar_experiment_group_consumed_not_canonical(tmp_path: Path) -> None:
    rows = [_s1()]
    sidecar = [_meta(experiment_group_id="sidecar_only_group")]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_ena_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=1,
    )
    with result.output_normalised.open(encoding="utf-8", newline="") as handle:
        out_rows = list(csv.DictReader(handle))
    assert out_rows[0]["experiment_group_id"] == ""
    with result.output_qc.open(encoding="utf-8", newline="") as handle:
        qc_rows = list(csv.DictReader(handle))
    assert qc_rows[0]["experiment_group_id"] == "sidecar_only_group"
    assert result.stats.primary_experiment_groups == 1


# --- Runner / stage boundary ---


def test_runner_preserves_row_count_no_drop_or_park(tmp_path: Path) -> None:
    rows = [
        _s1(record_id="ena:ru001", native_id="ru001", sequence_raw="ACGUAC"),
        _s1(record_id="ena:ru002", native_id="ru002", sequence_raw="ACGTAC"),
        _s1(record_id="ena:ru003", native_id="ru003", sequence_raw="ACGUAC"),
    ]
    sidecar = [
        _meta(record_id="ena:ru001", review_unit_id="ru001"),
        _meta(
            record_id="ena:ru002",
            review_unit_id="ru002",
            sequence="ACGTAC",
            experiment_group_id="g2",
        ),
        _meta(
            record_id="ena:ru003",
            review_unit_id="ru003",
            experiment_group_id="g3",
            automatic_concern_flags="t7_promoter",
            sequence_quality_status="promoter_or_template_requires_review",
        ),
    ]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_ena_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=3,
    )
    assert result.stats.s1_rows == 3
    assert result.stats.s2_rows == 3
    assert result.stats.records_dropped == 0
    assert result.stats.records_parked == 0
    assert result.stats.sequence_raw_unchanged is True
    assert result.stats.molecule_type_counts == {"RNA": 3}
    assert result.stats.chemistry_counts == {"RNA": 3}
    assert result.stats.t_to_u_count == 1
    assert result.stats.applied_trims == 0
    assert result.stats.core_differs_from_full == 0
    assert result.stats.source_promoter_or_template_count == 1
    assert result.stats.review_candidate_rows >= 1


def test_dispatcher_round_trip(tmp_path: Path) -> None:
    rows = [_s1()]
    sidecar = [_meta()]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_s2_normalisation(
        repo_root=repo_root,
        source_key="ena",
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        source_policy=POLICY_PATH,
        expected_rows=1,
    )
    assert result.source_key == "ena"
    assert result.stats.s2_rows == 1


def test_deterministic_rerun(tmp_path: Path) -> None:
    rows = [
        _s1(record_id="ena:ru001", native_id="ru001", sequence_raw="ACGUAC"),
        _s1(record_id="ena:ru002", native_id="ru002", sequence_raw="acgtac"),
    ]
    sidecar = [
        _meta(record_id="ena:ru001", review_unit_id="ru001"),
        _meta(
            record_id="ena:ru002",
            review_unit_id="ru002",
            sequence="acgtac",
            experiment_group_id="g2",
        ),
    ]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    first = run_ena_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
        check_deterministic_rerun=True,
    )
    assert first.deterministic_rerun_ok is True
    assert first.inputs_unchanged is True


def test_report_has_no_absolute_path_or_sequence(tmp_path: Path) -> None:
    rows = [_s1(sequence_raw="ACGUAC")]
    sidecar = [_meta()]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_ena_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=1,
    )
    report = result.output_report.read_text(encoding="utf-8")
    assert str(repo_root.resolve()) not in report
    assert "ACGUAC" not in report
    assert "S3 has not started" in report
    assert "CHECKPOINT-1 has not been generated" in report
    assert "679-versus-676 deduplication was not performed" in report


def test_legacy_ena_modules_must_not_be_imported() -> None:
    assert_no_legacy_ena_normaliser_import()


def test_canonical_populated_group_id_hard_fails(tmp_path: Path) -> None:
    rows = [_s1(experiment_group_id="should_be_empty")]
    sidecar = [_meta()]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    with pytest.raises(S2NormaliseError, match="experiment_group_id"):
        run_ena_s2(
            repo_root=repo_root,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=RULES_PATH,
            policy_path=POLICY_PATH,
            expected_rows=1,
        )


@pytest.mark.skipif(
    not (
        PRODUCTION_S1.is_file()
        and PRODUCTION_SIDECAR.is_file()
        and PRODUCTION_RAW.is_file()
    ),
    reason="ENA S1 outputs or registered raw file not present locally",
)
def test_production_679_in_equals_679_out_without_embedding_sequences(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    extracted_dir = repo / "data" / "interim" / "extracted"
    raw_dir = repo / "data" / "raw" / "ENA" / "review_v2"
    extracted_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    shutil.copy(PRODUCTION_S1, extracted_dir / "ena_extracted.csv")
    shutil.copy(PRODUCTION_SIDECAR, extracted_dir / "ena_source_metadata.csv")
    shutil.copy(PRODUCTION_RAW, raw_dir / "ena_selected_after_manual_review.csv")
    output_dir = repo / "data" / "interim" / "normalised"
    result = run_ena_s2(
        repo_root=repo,
        input_dir=extracted_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=679,
    )
    assert result.stats.s1_rows == 679
    assert result.stats.s2_rows == 679
    assert result.stats.records_dropped == 0
    assert result.stats.records_parked == 0
    assert result.stats.unique_record_ids == 679
    assert result.stats.molecule_type_counts.get("RNA") == 679
    assert result.stats.chemistry_counts.get("RNA") == 679
    assert result.stats.alphabet_counts.get("RNA") == 674
    assert result.stats.alphabet_counts.get("DNA_T") == 5
    assert result.stats.t_to_u_count == 5
    assert result.stats.applied_trims == 0
    assert result.stats.core_differs_from_full == 0
    assert result.stats.primary_experiment_groups == 25
    assert result.raw_sha256 == (
        "d1069b96c2bcf5eba02d7d7907b3bcc33e041bf80aac6345e7295715e45c5a35"
    )

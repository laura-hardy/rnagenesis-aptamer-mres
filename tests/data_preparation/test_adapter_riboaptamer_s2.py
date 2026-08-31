"""Tests for the RiboAptamer S2 adapter (synthetic sequences only).

Every literal nucleotide string in this file is shorter than 20 nt, except
programmatically generated homopolymers used to exercise length QC.
Does not read real RiboAptamer aptamer sequences except in the optional
local-only production skipif gate, which asserts counts without embedding
sequences in this file.
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

from adapters.riboaptamer import SIDECAR_COLUMNS  # noqa: E402
from adapters.riboaptamer_s2 import (  # noqa: E402
    GROUP_INFERENCE_DISABLED,
    RiboAptamerS2Error,
    diagnose_truncation,
    display_contains_ellipsis,
    display_ends_in_period_or_ellipsis,
    load_riboaptamer_policy,
    normalise_riboaptamer_record,
    resolve_riboaptamer_molecule_and_chemistry,
    truncation_regression_a_pass,
    truncation_regression_b_pass,
    truncation_regression_c_pass,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S2_FORBIDDEN_FIELDS,
    empty_corpus_record,
)
from common.sequence_normalisation import load_normalisation_rules  # noqa: E402
from s2_normalise import (  # noqa: E402
    S2NormaliseError,
    run_riboaptamer_s2,
    run_s2_normalisation,
)

POLICY_PATH = REPO_ROOT / "config" / "source_normalisation" / "riboaptamer.json"
RULES_PATH = REPO_ROOT / "config" / "sequence_normalisation_rules.json"
PRODUCTION_S1 = REPO_ROOT / "data" / "interim" / "extracted" / "riboaptamer_extracted.csv"
PRODUCTION_SIDECAR = (
    REPO_ROOT / "data" / "interim" / "extracted" / "riboaptamer_source_metadata.csv"
)
PRODUCTION_RAW = (
    REPO_ROOT / "data" / "raw" / "riboaptamer" / "all_sequences_509_rows.csv"
)


def _meta(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row["record_id"] = "riboaptamer:001"
    row["riboaptamer_native_id"] = "001"
    row["riboaptamer_csv_data_row"] = "1"
    row["riboaptamer_type"] = "Proteins"
    row.update(overrides)
    return row


def _s1(**overrides: str) -> dict[str, str]:
    record = empty_corpus_record()
    record.update(
        {
            "record_id": "riboaptamer:001",
            "sequence_raw": "ACGUAC",
            "source_db": "riboaptamer",
            "source_dataset": "riboaptamer_full_2026-08",
            "contributing_sources": "riboaptamer",
            "contributing_datasets": "riboaptamer_full_2026-08",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": "001",
            "target_name_raw": "",
            "publication": "",
            "doi": "",
            "pubmed_id": "11111111",
            "notes": json.dumps(
                {"category_prior": "Mammalian"},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
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
    with (input_dir / "riboaptamer_extracted.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(CORPUS_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        for row in canonical_rows:
            writer.writerow({col: row.get(col, "") for col in CORPUS_COLUMNS})
    with (input_dir / "riboaptamer_source_metadata.csv").open(
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
    return load_riboaptamer_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def rules():
    return load_normalisation_rules()


# --- Policy / molecule contract ---


def test_policy_is_fixed_rna_with_grouping_disabled(policy) -> None:
    assert policy.source_key == "riboaptamer"
    assert policy.molecule_type == "RNA"
    assert policy.chemistry == "RNA"
    assert policy.group_inference_key == GROUP_INFERENCE_DISABLED
    assert policy.apply_approved_trims is False
    assert policy.do_not_use_source_type_as_molecule is True


def test_grouping_mode_other_than_disabled_hard_fails(tmp_path: Path) -> None:
    path = tmp_path / "bad_policy.json"
    path.write_text(
        json.dumps(
            {
                "source_key": "riboaptamer",
                "contract_version": "1.0",
                "molecule_type": "RNA",
                "chemistry": "RNA",
                "molecule_evidence_source": "source_contract",
                "apply_approved_trims": False,
                "group_inference_key": "target_name_raw_plus_publication",
                "do_not_use_source_type_as_molecule": True,
                "do_not_infer_molecule_from_alphabet": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RiboAptamerS2Error, match="disabled"):
        load_riboaptamer_policy(path)


def test_fixed_rna_molecule_from_contract(policy) -> None:
    result = resolve_riboaptamer_molecule_and_chemistry(policy)
    assert result.molecule_type == "RNA"
    assert result.chemistry == "RNA"
    assert result.evidence_source == "source_contract"


@pytest.mark.parametrize(
    "source_type",
    ["Proteins", "Small molecules", "Cells", "Nucleic acids"],
)
def test_source_type_does_not_influence_molecule(policy, rules, source_type) -> None:
    result = normalise_riboaptamer_record(
        _s1(),
        _meta(riboaptamer_type=source_type),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "RNA"
    assert result.qc["source_type"] == source_type
    assert result.qc["molecule_evidence_source"] == "source_contract"


# --- Alphabet / T→U ---


def test_rna_u_no_transcription(policy, rules) -> None:
    result = normalise_riboaptamer_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["alphabet_as_reported"] == "RNA"
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGUAC"


def test_t_alphabet_transcribed_as_rna_not_ssdna(policy, rules) -> None:
    result = normalise_riboaptamer_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(riboaptamer_type="Proteins"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["alphabet_as_reported"] == "DNA_T"
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "RNA"
    assert result.canonical["t_to_u_applied"] == "true"
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert result.canonical["sequence_raw"] == "ACGTAC"


def test_mixed_t_u_not_silently_transcribed(policy, rules) -> None:
    result = normalise_riboaptamer_record(
        _s1(sequence_raw="ACGTU"),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_full"] == "ACGTU"
    assert result.canonical["t_to_u_applied"] == "false"
    assert "mixed_t_u" in result.canonical["qc_flags"]


def test_ambiguous_content_flagged_not_repaired(policy, rules) -> None:
    raw = "ACGNR"
    result = normalise_riboaptamer_record(
        _s1(sequence_raw=raw),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == raw
    assert result.canonical["sequence_full"] == "ACGNR"
    assert "ambiguous_base" in result.canonical["qc_flags"]
    assert result.canonical["alphabet_as_reported"] == "ambiguous"


def test_unusual_slash_and_ms_notation_not_interpreted_as_chemistry(
    policy, rules
) -> None:
    raw = "ACGU(ms)/A"
    result = normalise_riboaptamer_record(
        _s1(sequence_raw=raw),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == raw
    assert result.canonical["sequence_full"] == "ACGU(MS)/A"
    assert result.canonical["chemistry"] == "RNA"
    assert "invalid_character" in result.canonical["qc_flags"]


def test_lowercase_and_whitespace_cleaned_without_mutating_raw(policy, rules) -> None:
    raw = " ac guac "
    result = normalise_riboaptamer_record(
        _s1(sequence_raw=raw),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == raw
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert "uppercase" in result.transformations
    assert "remove_whitespace" in result.transformations


# --- Truncation / gaps ---


def test_ellipsis_helpers_distinguish_internal_from_terminal() -> None:
    assert display_contains_ellipsis("AC...GU") is True
    assert display_ends_in_period_or_ellipsis("AC...GU") is False
    assert display_contains_ellipsis("ACGU…") is True
    assert display_ends_in_period_or_ellipsis("ACGU…") is True
    assert display_ends_in_period_or_ellipsis("ACGU.") is True
    assert display_contains_ellipsis("ACGUAC") is False


def test_truncation_regressions_helpers() -> None:
    assert truncation_regression_a_pass(n_records=509, ending_count=0) is True
    assert truncation_regression_a_pass(n_records=509, ending_count=6) is False
    assert truncation_regression_b_pass(75) is True
    assert truncation_regression_b_pass(20) is False
    assert truncation_regression_c_pass(containing_count=1) is True
    assert truncation_regression_c_pass(containing_count=2) is False


def test_ellipsis_record_survives_with_truncated_qc(policy, rules) -> None:
    raw = "ACGU...AC"
    result = normalise_riboaptamer_record(
        _s1(sequence_raw=raw),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == raw
    assert result.canonical["sequence_full"] == "ACGU...AC"
    assert "truncated_sequence" in result.canonical["qc_flags"]
    assert "alignment_gaps" in result.canonical["qc_flags"]
    assert result.qc["ellipsis_anywhere"] == "true"
    assert result.qc["ends_in_period_or_ellipsis"] == "false"
    diag = diagnose_truncation(result.display_clean)
    assert diag.ellipsis_anywhere is True
    assert diag.ends_in_period_or_ellipsis is False


def test_gap_records_survive_with_alignment_qc(policy, rules) -> None:
    raw = "AC-GUA"
    result = normalise_riboaptamer_record(
        _s1(sequence_raw=raw),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == raw
    assert result.canonical["sequence_full"] == "AC-GUA"
    assert "alignment_gaps" in result.canonical["qc_flags"]
    assert "remove_display_separators" not in result.transformations


def test_invalid_character_flagged_not_dropped(policy, rules) -> None:
    raw = "ACGU3"
    result = normalise_riboaptamer_record(
        _s1(sequence_raw=raw),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == raw
    assert "invalid_character" in result.canonical["qc_flags"]
    assert result.canonical["sequence_full"] != ""


# --- Provenance / S4 boundary / trim semantics ---


def test_sequence_raw_and_provenance_unchanged(policy, rules) -> None:
    s1 = _s1(sequence_raw="acguac", pubmed_id="222")
    result = normalise_riboaptamer_record(
        s1,
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == s1["sequence_raw"]
    assert result.canonical["record_id"] == s1["record_id"]
    assert result.canonical["native_id"] == s1["native_id"]
    assert result.canonical["source_db"] == s1["source_db"]
    assert result.canonical["source_dataset"] == s1["source_dataset"]
    assert result.canonical["pubmed_id"] == s1["pubmed_id"]
    assert result.canonical["notes"] == s1["notes"]
    assert result.canonical["target_name_raw"] == ""


def test_s4_fields_remain_empty(policy, rules) -> None:
    result = normalise_riboaptamer_record(
        _s1(),
        _meta(),
        policy=policy,
        rules=rules,
    )
    for field in S2_FORBIDDEN_FIELDS:
        assert result.canonical[field] == ""
    assert result.canonical["target_name_raw"] == ""
    assert result.canonical["pdb_id"] == ""
    assert result.canonical["binding_evidence_type"] == ""
    assert result.canonical["affinity_value"] == ""


def test_known_motif_detected_but_not_trimmed(policy, rules) -> None:
    motif = "TAATACGACTCACTATA"
    result = normalise_riboaptamer_record(
        _s1(sequence_raw=motif + "AC"),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["trim_status"] == "constants_suspected_unresolved"
    assert result.canonical["trim_confidence"] == "n/a"
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert "known_promoter_detected" in result.canonical["qc_flags"]
    assert "t7_promoter_minimal" in result.qc["detected_motifs"]


def test_trim_confidence_na_when_no_trim_applied(policy, rules) -> None:
    result = normalise_riboaptamer_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["trim_status"] == "no_constants_detected"
    assert result.canonical["trim_confidence"] == "n/a"
    assert result.canonical["construct_scope"] == "unknown"


def test_length_outside_policy_survives(policy, rules) -> None:
    short = normalise_riboaptamer_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert "core_below_min_length" in short.canonical["qc_flags"]
    long_seq = "A" * 101
    long = normalise_riboaptamer_record(
        _s1(record_id="riboaptamer:002", native_id="002", sequence_raw=long_seq),
        _meta(record_id="riboaptamer:002", riboaptamer_native_id="002"),
        policy=policy,
        rules=rules,
    )
    assert long.canonical["sequence_raw"] == long_seq
    assert "core_above_max_length" in long.canonical["qc_flags"]


def test_stage_schema_compliance(policy, rules) -> None:
    result = normalise_riboaptamer_record(_s1(), _meta(), policy=policy, rules=rules)
    assert list(result.canonical.keys()) == list(CORPUS_COLUMNS)
    assert result.canonical["t_to_u_applied"] in {"true", "false"}
    assert result.canonical["independently_attested_by_permissive_source"] == "false"


# --- Runner ---


def test_runner_preserves_row_count_no_drop_or_park(tmp_path: Path) -> None:
    rows = [
        _s1(record_id="riboaptamer:001", native_id="001", sequence_raw="ACGUAC"),
        _s1(record_id="riboaptamer:002", native_id="002", sequence_raw="ACGTAC"),
        _s1(record_id="riboaptamer:003", native_id="003", sequence_raw="AC-GUA"),
    ]
    sidecar = [
        _meta(record_id="riboaptamer:001", riboaptamer_type="Proteins"),
        _meta(record_id="riboaptamer:002", riboaptamer_type="Cells"),
        _meta(record_id="riboaptamer:003", riboaptamer_type="Small molecules"),
    ]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_riboaptamer_s2(
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
    assert result.stats.applied_trims == 0
    assert result.stats.core_differs_from_full == 0
    assert result.stats.groups_considered == 0
    assert "group-wise inference disabled" in result.stats.constant_region_reason
    assert result.output_proposals.name == "detected_constants_riboaptamer.csv"


def test_runner_detects_known_motif_without_trimming(tmp_path: Path) -> None:
    motif = "TAATACGACTCACTATA"
    rows = [
        _s1(sequence_raw=motif + "AC"),
        _s1(record_id="riboaptamer:002", native_id="002", sequence_raw="ACGUAC"),
    ]
    sidecar = [
        _meta(),
        _meta(record_id="riboaptamer:002", riboaptamer_native_id="002"),
    ]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_riboaptamer_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
    )
    assert result.stats.known_motif_detection_count == 1
    assert result.stats.applied_trims == 0
    proposals = list(csv.DictReader(result.output_proposals.open(encoding="utf-8")))
    assert len(proposals) == 1
    assert proposals[0]["proposal_source"] == "known_motif"
    assert proposals[0]["applied"] == "false"
    assert proposals[0]["motif_id"] == "t7_promoter_minimal"
    normalised = list(csv.DictReader(result.output_normalised.open(encoding="utf-8")))
    assert normalised[0]["sequence_core"] == normalised[0]["sequence_full"]


def test_group_wise_inference_disabled_in_runner(tmp_path: Path) -> None:
    prefix = "AAAAAAAAAAAA"
    tails = ["CCCC", "GGGG", "UUUU", "CCGG", "GGCC"]
    canonical = []
    sidecar = []
    for index, tail in enumerate(tails, start=1):
        native = f"{index:03d}"
        canonical.append(
            _s1(
                record_id=f"riboaptamer:{native}",
                native_id=native,
                sequence_raw=prefix + tail,
                pubmed_id="44444444",
            )
        )
        sidecar.append(
            _meta(
                record_id=f"riboaptamer:{native}",
                riboaptamer_native_id=native,
            )
        )
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, canonical, sidecar)
    result = run_riboaptamer_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=5,
    )
    assert result.stats.groups_considered == 0
    assert result.stats.records_with_medium_confidence_proposal == 0
    proposals = list(csv.DictReader(result.output_proposals.open(encoding="utf-8")))
    assert all(row["proposal_source"] != "group_consensus" for row in proposals)
    report = result.output_report.read_text(encoding="utf-8")
    assert "group-wise inference disabled for RiboAptamer in this run" in report


def test_ellipsis_survives_runner_and_is_review_candidate(tmp_path: Path) -> None:
    rows = [
        _s1(sequence_raw="ACGU...AC"),
        _s1(record_id="riboaptamer:002", native_id="002", sequence_raw="AC-GUA"),
    ]
    sidecar = [
        _meta(),
        _meta(record_id="riboaptamer:002", riboaptamer_native_id="002"),
    ]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_riboaptamer_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
    )
    assert result.stats.s2_rows == 2
    assert result.stats.containing_ellipsis_count == 1
    assert result.stats.ending_period_or_ellipsis_count == 0
    assert result.stats.alignment_gaps_count == 2
    assert result.stats.truncated_sequence_count == 1
    review = list(csv.DictReader(result.output_review.open(encoding="utf-8")))
    assert {row["record_id"] for row in review} == {
        "riboaptamer:001",
        "riboaptamer:002",
    }


def test_truncation_regression_a_fails_on_terminal_ellipsis(tmp_path: Path) -> None:
    rows = [
        _s1(
            record_id=f"riboaptamer:{i:03d}",
            native_id=f"{i:03d}",
            sequence_raw="ACGUAC...",
        )
        for i in range(1, 6)
    ]
    sidecar = [
        _meta(record_id=f"riboaptamer:{i:03d}", riboaptamer_native_id=f"{i:03d}")
        for i in range(1, 6)
    ]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    # Direct helper: 5/5 ending in ellipsis would fail A at production scale.
    assert truncation_regression_a_pass(n_records=5, ending_count=5) is False
    result = run_riboaptamer_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=5,
    )
    assert result.stats.ending_period_or_ellipsis_count == 5
    assert result.stats.truncation_regression_a_pass is False


def test_dispatcher_routes_riboaptamer(tmp_path: Path) -> None:
    rows = [_s1()]
    sidecar = [_meta()]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_s2_normalisation(
        repo_root=repo_root,
        source_key="riboaptamer",
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        source_policy=POLICY_PATH,
        expected_rows=1,
    )
    assert result.source_key == "riboaptamer"
    assert result.stats.s2_rows == 1


def test_dispatcher_unknown_source_still_fails(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, [_s1()], [_meta()])
    with pytest.raises(S2NormaliseError, match="Unknown S2 source_key"):
        run_s2_normalisation(
            repo_root=repo_root,
            source_key="not_a_source",
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=RULES_PATH,
            source_policy=POLICY_PATH,
            expected_rows=1,
        )


def test_deterministic_rerun(tmp_path: Path) -> None:
    rows = [
        _s1(record_id="riboaptamer:001", native_id="001", sequence_raw="ACGUAC"),
        _s1(record_id="riboaptamer:002", native_id="002", sequence_raw="acgtac"),
    ]
    sidecar = [
        _meta(record_id="riboaptamer:001"),
        _meta(record_id="riboaptamer:002", riboaptamer_native_id="002"),
    ]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    first = run_riboaptamer_s2(
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
    result = run_riboaptamer_s2(
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
    assert "group-wise inference disabled for RiboAptamer in this run" in report


@pytest.mark.skipif(
    not (
        PRODUCTION_S1.is_file()
        and PRODUCTION_SIDECAR.is_file()
        and PRODUCTION_RAW.is_file()
    ),
    reason="RiboAptamer S1 outputs or registered raw file not present locally",
)
def test_production_509_in_equals_509_out_without_embedding_sequences(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    extracted_dir = repo / "data" / "interim" / "extracted"
    raw_dir = repo / "data" / "raw" / "riboaptamer"
    extracted_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    shutil.copy(PRODUCTION_S1, extracted_dir / "riboaptamer_extracted.csv")
    shutil.copy(PRODUCTION_SIDECAR, extracted_dir / "riboaptamer_source_metadata.csv")
    shutil.copy(PRODUCTION_RAW, raw_dir / "all_sequences_509_rows.csv")
    output_dir = repo / "data" / "interim" / "normalised"
    result = run_riboaptamer_s2(
        repo_root=repo,
        input_dir=extracted_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=509,
    )
    assert result.stats.s1_rows == 509
    assert result.stats.s2_rows == 509
    assert result.stats.records_dropped == 0
    assert result.stats.records_parked == 0
    assert result.stats.unique_record_ids == 509
    assert result.stats.molecule_type_counts.get("RNA") == 509
    assert result.stats.applied_trims == 0
    assert result.stats.core_differs_from_full == 0
    assert result.stats.truncation_regression_a_pass is True
    assert result.stats.truncation_regression_b_pass is True
    assert result.stats.truncation_regression_c_pass is True
    assert result.stats.ending_period_or_ellipsis_count == 0
    assert result.stats.containing_ellipsis_count <= 1
    assert result.raw_sha256 == (
        "721d8c5ea81476c1f371ef8bfa814743f364eaf004c0a6eda2aabd6dc5d9a9fd"
    )

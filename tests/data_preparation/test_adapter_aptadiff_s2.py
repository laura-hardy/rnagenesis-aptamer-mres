"""Tests for AptaDiff Dataset A/B S2 adapters (synthetic sequences only).

Tracked tests never embed real AptaDiff sequence values. Optional local-only
production skipif gates assert counts without writing sequences into this file.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadiff import SIDECAR_COLUMNS  # noqa: E402
from adapters.aptadiff_s2 import (  # noqa: E402
    CONSTANT_INFERENCE_DISABLED_REASON,
    CONSTANT_PROPOSAL_COLUMNS,
    CONSTRUCT_SCOPE_RANDOM_REGION_ONLY,
    GROUP_INFERENCE_DISABLED,
    AptaDiffS2Error,
    empty_constant_proposals,
    load_aptadiff_policy,
    normalise_aptadiff_record,
    resolve_aptadiff_molecule_and_chemistry,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S2_FORBIDDEN_FIELDS,
    empty_corpus_record,
)
from common.sequence_normalisation import load_normalisation_rules  # noqa: E402
from s2_normalise import (  # noqa: E402
    S2NormaliseError,
    run_aptadiff_s2,
    run_s2_normalisation,
)

POLICY_A_PATH = REPO_ROOT / "config" / "source_normalisation" / "aptadiff_a.json"
POLICY_B_PATH = REPO_ROOT / "config" / "source_normalisation" / "aptadiff_b.json"
RULES_PATH = REPO_ROOT / "config" / "sequence_normalisation_rules.json"
EXPECTED_A_DATASET = "aptadiff_a_igfbp3_p6_2026-06-22"
EXPECTED_B_DATASET = "aptadiff_b_ptk7_p6_2026-06-22"
EXPECTED_A_RAW = REPO_ROOT / "data/raw/Aptadiff_datasetA/datasetA_IGFBP3_P6.csv"
EXPECTED_B_RAW = REPO_ROOT / "data/raw/Aptadiff_otherdata/datasetB_PTK7_P6.csv"
EXPECTED_A_SHA256 = (
    "ec970c478aaba1aa089ecbaf7f5bc8aa7a11f6eacd0f7b3d3c418de6a27e8c77"
)
EXPECTED_B_SHA256 = (
    "546de810e34035731502caf6476c73cc06feab8156ec8178efaade2d21bf4d72"
)
PRODUCTION_A_S1 = (
    REPO_ROOT / "data" / "interim" / "extracted" / "aptadiff_a_extracted.csv"
)
PRODUCTION_A_SIDECAR = (
    REPO_ROOT / "data" / "interim" / "extracted" / "aptadiff_a_source_metadata.csv"
)
PRODUCTION_B_S1 = (
    REPO_ROOT / "data" / "interim" / "extracted" / "aptadiff_b_extracted.csv"
)
PRODUCTION_B_SIDECAR = (
    REPO_ROOT / "data" / "interim" / "extracted" / "aptadiff_b_source_metadata.csv"
)

# Synthetic 36-mers only. None of these are AptaDiff source values.
SYNTHETIC_DNA_36 = "ACGT" * 9
SYNTHETIC_N_36 = ("ACGT" * 8) + "ACGN"
T7_MINIMAL = "TAATACGACTCACTATA"
SYNTHETIC_T7_LIKE_36 = T7_MINIMAL + "CGTACGTACGTACGTACGT"
SHARED_PREFIX = "GGGGGGGGGGGG"
SHARED_SUFFIX = "CCCCCCCCCCCC"
SHARED_MIDDLES = (
    "ACGTACGTACGT",
    "CGTACGTACGTA",
    "GTACGTACGTAC",
    "TACGTACGTACG",
    "AAAACCCCTTTT",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _meta(
    *,
    source_key: str = "aptadiff_a",
    native_id: str = "00001",
    dataset: str = "A",
    documented_target: str = "IGFBP3",
    p6: str = "5",
    seq: str = SYNTHETIC_DNA_36,
    csv_row: str = "1",
) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row["record_id"] = f"{source_key}:{native_id}"
    row["native_id"] = native_id
    row["aptadiff_csv_data_row"] = csv_row
    row["aptadiff_seq"] = seq
    row["aptadiff_p6"] = p6
    row["aptadiff_dataset"] = dataset
    row["aptadiff_source_key"] = source_key
    row["aptadiff_documented_target"] = documented_target
    row["aptadiff_target_provenance"] = "synthetic fixture"
    return row


def _s1(
    *,
    source_key: str = "aptadiff_a",
    native_id: str = "00001",
    sequence_raw: str = SYNTHETIC_DNA_36,
    source_dataset: str = "demo_a",
) -> dict[str, str]:
    record = empty_corpus_record()
    record.update(
        {
            "record_id": f"{source_key}:{native_id}",
            "sequence_raw": sequence_raw,
            "source_db": source_key,
            "source_dataset": source_dataset,
            "contributing_sources": source_key,
            "contributing_datasets": source_dataset,
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "target_name_raw": "",
            "publication": "",
            "doi": "",
            "pubmed_id": "",
            "notes": "",
        }
    )
    return record


def _write_inputs(
    input_dir: Path,
    source_key: str,
    canonical_rows: list[dict[str, str]],
    sidecar_rows: list[dict[str, str]],
) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    with (input_dir / f"{source_key}_extracted.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(CORPUS_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        for row in canonical_rows:
            writer.writerow({col: row.get(col, "") for col in CORPUS_COLUMNS})
    with (input_dir / f"{source_key}_source_metadata.csv").open(
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
    source_key: str,
    canonical_rows: list[dict[str, str]],
    sidecar_rows: list[dict[str, str]],
) -> tuple[Path, Path, Path]:
    repo_root = tmp_path / "repo"
    input_dir = repo_root / "data" / "interim" / "extracted"
    output_dir = repo_root / "data" / "interim" / "normalised"
    _write_inputs(input_dir, source_key, canonical_rows, sidecar_rows)
    return repo_root, input_dir, output_dir


@pytest.fixture(scope="module")
def policy_a():
    return load_aptadiff_policy(POLICY_A_PATH)


@pytest.fixture(scope="module")
def policy_b():
    return load_aptadiff_policy(POLICY_B_PATH)


@pytest.fixture(scope="module")
def rules():
    return load_normalisation_rules()


def test_source_contracts_are_ssdna_dna(policy_a, policy_b) -> None:
    assert policy_a.source_key == "aptadiff_a"
    assert policy_b.source_key == "aptadiff_b"
    for policy in (policy_a, policy_b):
        assert policy.molecule_type == "ssDNA"
        assert policy.chemistry == "DNA"
        assert policy.do_not_infer_molecule_from_alphabet is True
        assert policy.construct_scope == CONSTRUCT_SCOPE_RANDOM_REGION_ONLY
        assert policy.apply_approved_trims is False
        assert policy.approved_trims == ()
        assert policy.group_inference_key == GROUP_INFERENCE_DISABLED
        assert policy.do_not_apply_inferred_trims is True
    assert policy_a.source_key != policy_b.source_key


def test_a_and_b_remain_independent_policy_files() -> None:
    assert POLICY_A_PATH != POLICY_B_PATH
    a_payload = json.loads(POLICY_A_PATH.read_text(encoding="utf-8"))
    b_payload = json.loads(POLICY_B_PATH.read_text(encoding="utf-8"))
    assert a_payload["source_key"] == "aptadiff_a"
    assert b_payload["source_key"] == "aptadiff_b"


def test_grouping_mode_other_than_disabled_hard_fails(tmp_path: Path) -> None:
    path = tmp_path / "bad_policy.json"
    payload = json.loads(POLICY_A_PATH.read_text(encoding="utf-8"))
    payload["group_inference_key"] = "target_name_raw_plus_publication"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AptaDiffS2Error, match="disabled"):
        load_aptadiff_policy(path)


def test_molecule_from_contract_not_alphabet(policy_a, policy_b) -> None:
    a = resolve_aptadiff_molecule_and_chemistry(policy_a)
    b = resolve_aptadiff_molecule_and_chemistry(policy_b)
    assert a.molecule_type == "ssDNA"
    assert a.chemistry == "DNA"
    assert a.evidence_source == "source_contract"
    assert b.molecule_type == "ssDNA"
    assert b.chemistry == "DNA"


def test_clean_t_alphabet_remains_t_and_reports_dna_t(policy_a, rules) -> None:
    result = normalise_aptadiff_record(
        _s1(),
        _meta(),
        policy=policy_a,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == SYNTHETIC_DNA_36
    assert result.canonical["sequence_full"] == SYNTHETIC_DNA_36
    assert result.canonical["sequence_core"] == SYNTHETIC_DNA_36
    assert result.canonical["alphabet_as_reported"] == "DNA_T"
    assert result.canonical["t_to_u_applied"] == "false"
    assert "U" not in result.canonical["sequence_full"]
    assert result.canonical["molecule_type"] == "ssDNA"
    assert result.canonical["chemistry"] == "DNA"
    assert result.canonical["sequence_length_full"] == "36"
    assert result.canonical["sequence_length_core"] == "36"


def test_no_ordinary_sequence_is_t_to_u_converted(policy_a, policy_b, rules) -> None:
    for policy, source_key, dataset, target in (
        (policy_a, "aptadiff_a", "A", "IGFBP3"),
        (policy_b, "aptadiff_b", "B", "PTK7"),
    ):
        result = normalise_aptadiff_record(
            _s1(source_key=source_key, source_dataset=f"demo_{source_key}"),
            _meta(
                source_key=source_key,
                dataset=dataset,
                documented_target=target,
            ),
            policy=policy,
            rules=rules,
        )
        assert result.canonical["t_to_u_applied"] == "false"
        assert result.canonical["sequence_full"] == SYNTHETIC_DNA_36
        assert "t_to_u" not in result.transformations


def test_n_containing_sequence_survives_and_is_ambiguous(policy_b, rules) -> None:
    result = normalise_aptadiff_record(
        _s1(
            source_key="aptadiff_b",
            sequence_raw=SYNTHETIC_N_36,
            source_dataset="demo_b",
        ),
        _meta(
            source_key="aptadiff_b",
            dataset="B",
            documented_target="PTK7",
            seq=SYNTHETIC_N_36,
        ),
        policy=policy_b,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == SYNTHETIC_N_36
    assert result.canonical["sequence_full"] == SYNTHETIC_N_36
    assert "N" in result.canonical["sequence_full"]
    assert result.canonical["sequence_full"].count("N") == 1
    assert result.canonical["alphabet_as_reported"] == "ambiguous"
    assert "ambiguous_base" in result.canonical["qc_flags"]
    assert result.canonical["molecule_type"] == "ssDNA"
    assert result.canonical["chemistry"] == "DNA"
    assert result.canonical["t_to_u_applied"] == "false"


def test_n_is_not_silently_repaired(policy_a, rules) -> None:
    result = normalise_aptadiff_record(
        _s1(sequence_raw=SYNTHETIC_N_36),
        _meta(seq=SYNTHETIC_N_36),
        policy=policy_a,
        rules=rules,
    )
    assert result.canonical["sequence_full"] == SYNTHETIC_N_36
    assert result.canonical["sequence_core"] == SYNTHETIC_N_36
    assert result.canonical["sequence_full"] != SYNTHETIC_DNA_36


def test_random_region_only_sets_core_equal_full(policy_a, rules) -> None:
    result = normalise_aptadiff_record(
        _s1(),
        _meta(),
        policy=policy_a,
        rules=rules,
    )
    assert result.canonical["construct_scope"] == CONSTRUCT_SCOPE_RANDOM_REGION_ONLY
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert result.canonical["trim_status"] == "no_constants_detected"
    assert result.canonical["trim_confidence"] == "n/a"
    assert result.canonical["detected_constant_5p"] == ""
    assert result.canonical["detected_constant_3p"] == ""


def test_constant_region_inference_is_disabled() -> None:
    assert empty_constant_proposals() == []
    assert list(CONSTANT_PROPOSAL_COLUMNS)


def test_t7_like_prefix_is_not_trimmed(policy_a, rules) -> None:
    assert SYNTHETIC_T7_LIKE_36.startswith(T7_MINIMAL)
    assert len(SYNTHETIC_T7_LIKE_36) == 36
    result = normalise_aptadiff_record(
        _s1(sequence_raw=SYNTHETIC_T7_LIKE_36),
        _meta(seq=SYNTHETIC_T7_LIKE_36),
        policy=policy_a,
        rules=rules,
    )
    assert result.canonical["sequence_full"] == SYNTHETIC_T7_LIKE_36
    assert result.canonical["sequence_core"] == SYNTHETIC_T7_LIKE_36
    assert result.canonical["construct_scope"] == CONSTRUCT_SCOPE_RANDOM_REGION_ONLY
    assert result.canonical["trim_status"] == "no_constants_detected"
    assert result.canonical["detected_constant_5p"] == ""
    assert "known_promoter_detected" not in result.canonical["qc_flags"]
    assert "constants_suspected_unresolved" not in result.canonical["qc_flags"]


def test_group_wise_consensus_trim_does_not_occur(tmp_path: Path) -> None:
    canonical: list[dict[str, str]] = []
    sidecar: list[dict[str, str]] = []
    sequences = [
        SHARED_PREFIX + middle + SHARED_SUFFIX for middle in SHARED_MIDDLES
    ]
    assert all(len(seq) == 36 for seq in sequences)
    assert len(sequences) >= 5
    for index, seq in enumerate(sequences, start=1):
        native = f"{index:05d}"
        canonical.append(
            _s1(native_id=native, sequence_raw=seq, source_dataset="demo_a")
        )
        sidecar.append(
            _meta(native_id=native, seq=seq, csv_row=str(index), p6=str(index))
        )
    repo_root, input_dir, output_dir = _runner_pair(
        tmp_path, "aptadiff_a", canonical, sidecar
    )
    result = run_aptadiff_s2(
        repo_root=repo_root,
        source_key="aptadiff_a",
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_A_PATH,
        expected_rows=len(sequences),
    )
    rows = list(csv.DictReader(result.output_normalised.open(encoding="utf-8")))
    assert len(rows) == len(sequences)
    for row, seq in zip(rows, sequences, strict=True):
        assert row["sequence_raw"] == seq
        assert row["sequence_full"] == seq
        assert row["sequence_core"] == seq
        assert row["construct_scope"] == CONSTRUCT_SCOPE_RANDOM_REGION_ONLY
    proposals = list(csv.DictReader(result.output_proposals.open(encoding="utf-8")))
    assert proposals == []
    assert result.stats.applied_trims == 0
    assert result.stats.core_differs_from_full == 0
    assert result.stats.constant_region_reason == CONSTANT_INFERENCE_DISABLED_REASON


def test_p6_does_not_populate_evidence_or_affinity(policy_a, rules) -> None:
    result = normalise_aptadiff_record(
        _s1(),
        _meta(p6="194981"),
        policy=policy_a,
        rules=rules,
    )
    for field in (
        "affinity_value",
        "affinity_unit",
        "affinity_type",
        "binding_evidence_type",
        "binding_evidence_score",
    ):
        assert result.canonical[field] == ""
    assert result.qc["aptadiff_p6"] == "194981"


def test_target_canonicalisation_remains_absent(policy_a, policy_b, rules) -> None:
    a = normalise_aptadiff_record(_s1(), _meta(), policy=policy_a, rules=rules)
    b = normalise_aptadiff_record(
        _s1(source_key="aptadiff_b", source_dataset="demo_b"),
        _meta(source_key="aptadiff_b", dataset="B", documented_target="PTK7"),
        policy=policy_b,
        rules=rules,
    )
    for result in (a, b):
        for field in S2_FORBIDDEN_FIELDS:
            assert result.canonical[field] == "", field
        assert result.canonical["target_name_raw"] == ""
        assert result.canonical["target_name"] == ""
        assert result.canonical["target_uniprot"] == ""
        assert result.canonical["target_type"] == ""
        assert result.canonical["target_type_source"] == ""
        assert result.canonical["target_family"] == ""
        assert result.canonical["target_pfam"] == ""
    assert a.qc["aptadiff_documented_target"] == "IGFBP3"
    assert b.qc["aptadiff_documented_target"] == "PTK7"


def test_row_order_and_identity_preserved(tmp_path: Path) -> None:
    sequences = [SYNTHETIC_DNA_36, SYNTHETIC_N_36, SYNTHETIC_T7_LIKE_36]
    canonical = [
        _s1(native_id=f"{i:05d}", sequence_raw=seq)
        for index, seq in enumerate(sequences, start=1)
        for i in [index]
    ]
    sidecar = [
        _meta(native_id=f"{i:05d}", seq=seq, csv_row=str(i), p6=str(10 * i))
        for i, seq in enumerate(sequences, start=1)
    ]
    repo_root, input_dir, output_dir = _runner_pair(
        tmp_path, "aptadiff_a", canonical, sidecar
    )
    result = run_aptadiff_s2(
        repo_root=repo_root,
        source_key="aptadiff_a",
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_A_PATH,
        expected_rows=3,
    )
    rows = list(csv.DictReader(result.output_normalised.open(encoding="utf-8")))
    assert [row["record_id"] for row in rows] == [row["record_id"] for row in canonical]
    assert [row["native_id"] for row in rows] == [row["native_id"] for row in canonical]
    assert [row["sequence_raw"] for row in rows] == sequences
    qc = list(csv.DictReader(result.output_qc.open(encoding="utf-8")))
    assert [row["aptadiff_p6"] for row in qc] == ["10", "20", "30"]
    assert result.stats.order_preserved is True


def test_deterministic_rerun_byte_identical(tmp_path: Path) -> None:
    canonical = [
        _s1(native_id="00001", sequence_raw=SYNTHETIC_DNA_36),
        _s1(native_id="00002", sequence_raw=SYNTHETIC_N_36),
    ]
    sidecar = [
        _meta(native_id="00001", seq=SYNTHETIC_DNA_36, csv_row="1"),
        _meta(native_id="00002", seq=SYNTHETIC_N_36, csv_row="2", p6="9"),
    ]
    repo_root, input_dir, output_dir = _runner_pair(
        tmp_path, "aptadiff_a", canonical, sidecar
    )
    first = run_aptadiff_s2(
        repo_root=repo_root,
        source_key="aptadiff_a",
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_A_PATH,
        expected_rows=2,
        check_deterministic_rerun=True,
    )
    assert first.deterministic_rerun_ok is True
    assert first.inputs_unchanged is True


def test_a_and_b_remain_independent_outputs(tmp_path: Path) -> None:
    a_canonical = [_s1(source_key="aptadiff_a", source_dataset="demo_a")]
    a_sidecar = [_meta(source_key="aptadiff_a")]
    b_canonical = [
        _s1(
            source_key="aptadiff_b",
            source_dataset="demo_b",
            sequence_raw=SYNTHETIC_N_36,
        )
    ]
    b_sidecar = [
        _meta(
            source_key="aptadiff_b",
            dataset="B",
            documented_target="PTK7",
            seq=SYNTHETIC_N_36,
        )
    ]
    repo_root, input_dir, output_dir = _runner_pair(
        tmp_path, "aptadiff_a", a_canonical, a_sidecar
    )
    _write_inputs(input_dir, "aptadiff_b", b_canonical, b_sidecar)
    a_result = run_s2_normalisation(
        repo_root=repo_root,
        source_key="aptadiff_a",
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        source_policy=POLICY_A_PATH,
        expected_rows=1,
    )
    b_result = run_s2_normalisation(
        repo_root=repo_root,
        source_key="aptadiff_b",
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        source_policy=POLICY_B_PATH,
        expected_rows=1,
    )
    assert a_result.source_key == "aptadiff_a"
    assert b_result.source_key == "aptadiff_b"
    assert a_result.output_normalised != b_result.output_normalised
    a_rows = list(csv.DictReader(a_result.output_normalised.open(encoding="utf-8")))
    b_rows = list(csv.DictReader(b_result.output_normalised.open(encoding="utf-8")))
    assert a_rows[0]["record_id"].startswith("aptadiff_a:")
    assert b_rows[0]["record_id"].startswith("aptadiff_b:")
    assert a_rows[0]["sequence_full"] == SYNTHETIC_DNA_36
    assert b_rows[0]["sequence_full"] == SYNTHETIC_N_36
    report_a = a_result.output_report.read_text(encoding="utf-8")
    assert "S3 has not started" in report_a
    assert "No record was rejected or parked" in report_a
    assert SYNTHETIC_DNA_36 not in report_a
    assert str(repo_root.resolve()) not in report_a


def test_combined_aptadiff_key_is_rejected(tmp_path: Path) -> None:
    repo_root, input_dir, output_dir = _runner_pair(
        tmp_path, "aptadiff_a", [_s1()], [_meta()]
    )
    with pytest.raises(S2NormaliseError, match="Unknown S2 source_key"):
        run_s2_normalisation(
            repo_root=repo_root,
            source_key="aptadiff",
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=RULES_PATH,
            source_policy=POLICY_A_PATH,
            expected_rows=1,
        )


def test_n_row_is_review_candidate_not_dropped(tmp_path: Path) -> None:
    canonical = [
        _s1(native_id="00001", sequence_raw=SYNTHETIC_DNA_36),
        _s1(native_id="00002", sequence_raw=SYNTHETIC_N_36),
    ]
    sidecar = [
        _meta(native_id="00001", seq=SYNTHETIC_DNA_36, csv_row="1"),
        _meta(native_id="00002", seq=SYNTHETIC_N_36, csv_row="2"),
    ]
    repo_root, input_dir, output_dir = _runner_pair(
        tmp_path, "aptadiff_a", canonical, sidecar
    )
    result = run_aptadiff_s2(
        repo_root=repo_root,
        source_key="aptadiff_a",
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_A_PATH,
        expected_rows=2,
    )
    assert result.stats.s2_rows == 2
    assert result.stats.records_dropped == 0
    assert result.stats.records_parked == 0
    assert result.stats.ambiguous_base_count == 1
    review = list(csv.DictReader(result.output_review.open(encoding="utf-8")))
    assert [row["record_id"] for row in review] == ["aptadiff_a:00002"]
    assert review[0]["alphabet_as_reported"] == "ambiguous"


def _assert_production_counts(
    *,
    source_key: str,
    expected_rows: int,
    dna_t: int,
    ambiguous: int,
    result,
) -> None:
    assert result.source_key == source_key
    assert result.stats.s1_rows == expected_rows
    assert result.stats.s2_rows == expected_rows
    assert result.stats.molecule_type_counts == {"ssDNA": expected_rows}
    assert result.stats.chemistry_counts == {"DNA": expected_rows}
    assert result.stats.alphabet_counts.get("DNA_T", 0) == dna_t
    assert result.stats.alphabet_counts.get("ambiguous", 0) == ambiguous
    assert result.stats.t_to_u_count == 0
    assert result.stats.applied_trims == 0
    assert result.stats.core_differs_from_full == 0
    assert result.stats.length_36_count == expected_rows
    assert result.stats.construct_scope_counts == {
        CONSTRUCT_SCOPE_RANDOM_REGION_ONLY: expected_rows
    }
    assert result.stats.records_dropped == 0
    assert result.stats.records_parked == 0
    assert result.inputs_unchanged is True
    report = result.output_report.read_text(encoding="utf-8")
    assert "S3 has not started" in report
    assert "No record was rejected or parked" in report


@pytest.mark.skipif(
    not PRODUCTION_A_S1.is_file() or not EXPECTED_A_RAW.is_file(),
    reason="Registered AptaDiff Dataset A S1/raw files not present locally",
)
def test_production_dataset_a_s2_reconciliation_without_embedding_sequences(
    tmp_path: Path,
) -> None:
    before_raw = _sha256(EXPECTED_A_RAW)
    before_s1 = _sha256(PRODUCTION_A_S1)
    before_sidecar = _sha256(PRODUCTION_A_SIDECAR)
    assert before_raw == EXPECTED_A_SHA256
    repo = tmp_path / "repo"
    extracted_dir = repo / "data" / "interim" / "extracted"
    raw_dir = repo / "data" / "raw" / "Aptadiff_datasetA"
    extracted_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    shutil.copy(PRODUCTION_A_S1, extracted_dir / "aptadiff_a_extracted.csv")
    shutil.copy(
        PRODUCTION_A_SIDECAR, extracted_dir / "aptadiff_a_source_metadata.csv"
    )
    shutil.copy(EXPECTED_A_RAW, raw_dir / "datasetA_IGFBP3_P6.csv")
    output_dir = repo / "data" / "interim" / "normalised"
    result = run_aptadiff_s2(
        repo_root=repo,
        source_key="aptadiff_a",
        input_dir=extracted_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_A_PATH,
        expected_rows=13803,
        check_deterministic_rerun=True,
    )
    _assert_production_counts(
        source_key="aptadiff_a",
        expected_rows=13803,
        dna_t=13802,
        ambiguous=1,
        result=result,
    )
    assert result.deterministic_rerun_ok is True
    assert _sha256(EXPECTED_A_RAW) == before_raw
    assert _sha256(PRODUCTION_A_S1) == before_s1
    assert _sha256(PRODUCTION_A_SIDECAR) == before_sidecar
    rows = list(csv.DictReader(result.output_normalised.open(encoding="utf-8")))
    assert rows[0]["record_id"] == "aptadiff_a:00001"
    assert rows[-1]["record_id"] == "aptadiff_a:13803"
    assert all(row["target_name_raw"] == "" for row in rows)
    assert all(row["t_to_u_applied"] == "false" for row in rows)
    assert all(row["sequence_core"] == row["sequence_full"] for row in rows)


@pytest.mark.skipif(
    not PRODUCTION_B_S1.is_file() or not EXPECTED_B_RAW.is_file(),
    reason="Registered AptaDiff Dataset B S1/raw files not present locally",
)
def test_production_dataset_b_s2_reconciliation_without_embedding_sequences(
    tmp_path: Path,
) -> None:
    before_raw = _sha256(EXPECTED_B_RAW)
    before_s1 = _sha256(PRODUCTION_B_S1)
    before_sidecar = _sha256(PRODUCTION_B_SIDECAR)
    assert before_raw == EXPECTED_B_SHA256
    repo = tmp_path / "repo"
    extracted_dir = repo / "data" / "interim" / "extracted"
    raw_dir = repo / "data" / "raw" / "Aptadiff_otherdata"
    extracted_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    shutil.copy(PRODUCTION_B_S1, extracted_dir / "aptadiff_b_extracted.csv")
    shutil.copy(
        PRODUCTION_B_SIDECAR, extracted_dir / "aptadiff_b_source_metadata.csv"
    )
    shutil.copy(EXPECTED_B_RAW, raw_dir / "datasetB_PTK7_P6.csv")
    output_dir = repo / "data" / "interim" / "normalised"
    result = run_aptadiff_s2(
        repo_root=repo,
        source_key="aptadiff_b",
        input_dir=extracted_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_B_PATH,
        expected_rows=11547,
        check_deterministic_rerun=True,
    )
    _assert_production_counts(
        source_key="aptadiff_b",
        expected_rows=11547,
        dna_t=11532,
        ambiguous=15,
        result=result,
    )
    assert result.deterministic_rerun_ok is True
    assert _sha256(EXPECTED_B_RAW) == before_raw
    assert _sha256(PRODUCTION_B_S1) == before_s1
    assert _sha256(PRODUCTION_B_SIDECAR) == before_sidecar
    rows = list(csv.DictReader(result.output_normalised.open(encoding="utf-8")))
    assert rows[0]["record_id"] == "aptadiff_b:00001"
    assert rows[-1]["record_id"] == "aptadiff_b:11547"
    assert all(row["molecule_type"] == "ssDNA" for row in rows)
    assert all("U" not in row["sequence_full"] for row in rows)

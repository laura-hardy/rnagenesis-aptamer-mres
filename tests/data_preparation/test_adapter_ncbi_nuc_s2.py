"""Tests for the NCBI Nucleotide S2 adapter (synthetic sequences only).

Every literal nucleotide string in this file is shorter than 20 nt, except
programmatically generated homopolymers used to exercise length QC.
Does not read real NCBI aptamer sequences except in the optional local-only
production skipif gate, which asserts counts without embedding sequences.
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

from adapters.ncbi_nuc import SIDECAR_COLUMNS  # noqa: E402
from adapters.ncbi_nuc_s2 import (  # noqa: E402
    GROUP_INFERENCE_DISABLED,
    NcbiNucS2Error,
    interpret_ncbi_nuc_construct,
    load_ncbi_nuc_policy,
    normalise_ncbi_nuc_record,
    resolve_ncbi_nuc_molecule_and_chemistry,
    s4_fields_are_empty,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S2_FORBIDDEN_FIELDS,
    empty_corpus_record,
)
from common.sequence_normalisation import load_normalisation_rules  # noqa: E402
from s2_normalise import (  # noqa: E402
    run_ncbi_nuc_s2,
    run_s2_normalisation,
)

POLICY_PATH = REPO_ROOT / "config" / "source_normalisation" / "ncbi_nuc.json"
RULES_PATH = REPO_ROOT / "config" / "sequence_normalisation_rules.json"
PRODUCTION_S1 = REPO_ROOT / "data" / "interim" / "extracted" / "ncbi_nuc_extracted.csv"
PRODUCTION_SIDECAR = (
    REPO_ROOT / "data" / "interim" / "extracted" / "ncbi_nuc_source_metadata.csv"
)
PRODUCTION_RAW_DIR = REPO_ROOT / "data" / "raw" / "NCBI_nucleotide"
T7_MOTIF = "TAATACGACTCACTATA"


def _meta(native_id: str, **overrides: str) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row["record_id"] = f"ncbi_nuc:{native_id}"
    row["native_id"] = native_id
    row["ncbi_nuc_accession"] = native_id
    row["ncbi_nuc_origin_length"] = str(len(overrides.get("origin", "acgtac")))
    row.update({k: v for k, v in overrides.items() if k != "origin"})
    return row


def _s1(native_id: str, sequence_raw: str = "acgtac", **overrides: str) -> dict[str, str]:
    record = empty_corpus_record()
    record.update(
        {
            "record_id": f"ncbi_nuc:{native_id}",
            "sequence_raw": sequence_raw,
            "source_db": "ncbi_nuc",
            "source_dataset": "ncbi_nuc_genbank_2026-07-27",
            "contributing_sources": "ncbi_nuc",
            "contributing_datasets": "ncbi_nuc_genbank_2026-07-27",
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
    record.update(overrides)
    return record


def _write_inputs(
    input_dir: Path,
    canonical_rows: list[dict[str, str]],
    sidecar_rows: list[dict[str, str]],
) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    with (input_dir / "ncbi_nuc_extracted.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(CORPUS_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        for row in canonical_rows:
            writer.writerow({col: row.get(col, "") for col in CORPUS_COLUMNS})
    with (input_dir / "ncbi_nuc_source_metadata.csv").open(
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
    return load_ncbi_nuc_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def rules():
    return load_normalisation_rules()


def test_policy_grouping_disabled_and_no_ssdna_coercion(policy) -> None:
    assert policy.source_key == "ncbi_nuc"
    assert policy.group_inference_key == GROUP_INFERENCE_DISABLED
    assert policy.apply_approved_trims is False
    assert policy.do_not_infer_molecule_from_alphabet is True
    assert policy.do_not_coerce_dna_to_ssdna is True
    dna = policy.molecule_identity_by_accession["QT662269"]
    assert dna.molecule_type == "DNA"
    assert dna.chemistry == "DNA"


def test_grouping_mode_other_than_disabled_hard_fails(tmp_path: Path) -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["group_inference_key"] = "target_name_raw"
    path = tmp_path / "bad_policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NcbiNucS2Error, match="disabled"):
        load_ncbi_nuc_policy(path)


def test_ssdna_coercion_in_policy_hard_fails(tmp_path: Path) -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["molecule_identity_by_accession"]["QT662269"] = {
        "molecule_type": "ssDNA",
        "chemistry": "DNA",
    }
    path = tmp_path / "ssdna_policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NcbiNucS2Error, match="ssDNA|unsupported molecule_type"):
        load_ncbi_nuc_policy(path)


def test_approved_rna_t_alphabet_transcribes(policy, rules) -> None:
    result = normalise_ncbi_nuc_record(
        _s1("U34759", "acgtac"),
        _meta("U34759", origin="acgtac"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "RNA"
    assert result.canonical["alphabet_as_reported"] == "DNA_T"
    assert result.canonical["t_to_u_applied"] == "true"
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert result.canonical["sequence_core"] == "ACGUAC"
    assert result.canonical["sequence_raw"] == "acgtac"
    assert "t_in_reported_rna" in result.canonical["qc_flags"]


def test_unresolved_t_alphabet_is_not_transcribed(policy, rules) -> None:
    result = normalise_ncbi_nuc_record(
        _s1("DI115369", "acgtac"),
        _meta("DI115369", origin="acgtac"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "unknown"
    assert result.canonical["chemistry"] == "unknown"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGTAC"
    assert result.canonical["alphabet_as_reported"] == "DNA_T"
    assert "molecule_type_unknown" in result.canonical["qc_flags"]


def test_source_confirmed_dna_is_not_transcribed(policy, rules) -> None:
    result = normalise_ncbi_nuc_record(
        _s1("QT662269", "acgtac"),
        _meta("QT662269", origin="acgtac", ncbi_nuc_locus_molecule="DNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "DNA"
    assert result.canonical["chemistry"] == "DNA"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGTAC"
    assert result.canonical["molecule_type"] != "ssDNA"


def test_alphabet_alone_cannot_resolve_molecule(policy, rules) -> None:
    result = normalise_ncbi_nuc_record(
        _s1("DI115369", "aaaaaa"),
        _meta("DI115369", origin="aaaaaa"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "unknown"
    assert result.canonical["chemistry"] == "unknown"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["alphabet_as_reported"] in {"RNA", "DNA_T"}


def test_explicit_primer_is_partial_construct_not_trimmed(policy, rules) -> None:
    result = normalise_ncbi_nuc_record(
        _s1("FW366678", "acgtac"),
        _meta("FW366678", origin="acgtac"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["construct_scope"] == "partial_construct"
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert result.qc["primer_associated"] == "true"
    assert result.qc["construct_requires_review"] == "true"


def test_explicit_transcription_template_is_full_construct_not_trimmed(
    policy, rules
) -> None:
    result = normalise_ncbi_nuc_record(
        _s1("DD421991", T7_MOTIF + "AC"),
        _meta("DD421991", origin=T7_MOTIF + "AC"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["construct_scope"] == "full_construct"
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert result.qc["transcription_template"] == "true"
    assert "t7_promoter_minimal" in result.qc["detected_motifs"]
    assert result.canonical["trim_status"] == "constants_suspected_unresolved"


def test_cdna_unresolved_boundaries_remain_unknown(policy, rules) -> None:
    result = normalise_ncbi_nuc_record(
        _s1("HV507922", "acgtac"),
        _meta("HV507922", origin="acgtac"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["construct_scope"] == "unknown"
    assert result.qc["cdna_template_associated"] == "true"
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]


def test_no_source_evidence_construct_unknown(policy, rules) -> None:
    result = normalise_ncbi_nuc_record(
        _s1("DI115369", "acgtac"),
        _meta("DI115369", origin="acgtac"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["construct_scope"] == "unknown"
    assert result.qc["unresolved_aptamer_status"] == "true"


def test_poly_a_fragment_is_partial_construct(policy, rules) -> None:
    result = interpret_ncbi_nuc_construct("DJ028182", policy)
    assert result.construct_scope == "partial_construct"
    assert result.source_object_class == "poly_a_fragment"


def test_ambiguity_retained_and_flagged(policy, rules) -> None:
    result = normalise_ncbi_nuc_record(
        _s1("HV200497", "acgtn"),
        _meta("HV200497", origin="acgtn"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_full"] == "ACGTN"
    assert result.canonical["alphabet_as_reported"] == "ambiguous"
    assert "ambiguous_base" in result.canonical["qc_flags"]
    assert result.canonical["sequence_raw"] == "acgtn"


def test_gaps_are_not_removed(policy, rules) -> None:
    result = normalise_ncbi_nuc_record(
        _s1("DI115369", "ac-gta"),
        _meta("DI115369", origin="ac-gta"),
        policy=policy,
        rules=rules,
    )
    assert "-" in result.canonical["sequence_full"]
    assert "alignment_gaps" in result.canonical["qc_flags"]
    assert result.canonical["sequence_raw"] == "ac-gta"


def test_invalid_character_is_not_repaired(policy, rules) -> None:
    result = normalise_ncbi_nuc_record(
        _s1("DI115369", "acgtxa"),
        _meta("DI115369", origin="acgtxa"),
        policy=policy,
        rules=rules,
    )
    assert "X" in result.canonical["sequence_full"]
    assert "invalid_character" in result.canonical["qc_flags"]
    assert result.canonical["sequence_raw"] == "acgtxa"


def test_sequence_raw_unchanged_and_lengths_recomputed(policy, rules) -> None:
    result = normalise_ncbi_nuc_record(
        _s1("U34759", "acgtac"),
        _meta("U34759", origin="acgtac"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == "acgtac"
    assert result.canonical["sequence_length_full"] == str(
        len(result.canonical["sequence_full"])
    )
    assert result.canonical["sequence_length_core"] == str(
        len(result.canonical["sequence_core"])
    )


def test_s4_fields_remain_empty(policy, rules) -> None:
    result = normalise_ncbi_nuc_record(
        _s1("U34759", "acgtac"),
        _meta("U34759", origin="acgtac"),
        policy=policy,
        rules=rules,
    )
    assert s4_fields_are_empty(result.canonical)
    for field in S2_FORBIDDEN_FIELDS:
        assert result.canonical[field] == ""
    assert result.canonical["target_name"] == ""
    assert result.canonical["binding_evidence_type"] == ""
    assert result.canonical["affinity_value"] == ""
    assert result.canonical["cluster_id"] == ""
    assert result.canonical["partition"] == ""


def test_length_outside_policy_survives(policy, rules) -> None:
    short = normalise_ncbi_nuc_record(
        _s1("U34759", "acgtac"),
        _meta("U34759", origin="acgtac"),
        policy=policy,
        rules=rules,
    )
    assert "core_below_min_length" in short.canonical["qc_flags"]
    long_seq = "A" * 101
    long = normalise_ncbi_nuc_record(
        _s1("QT662269", long_seq),
        _meta("QT662269", origin=long_seq),
        policy=policy,
        rules=rules,
    )
    assert long.canonical["sequence_raw"] == long_seq
    assert "core_above_max_length" in long.canonical["qc_flags"]
    assert long.canonical["sequence_core"] == long.canonical["sequence_full"]


def test_molecule_resolution_uses_accession_not_alphabet(policy) -> None:
    rna = resolve_ncbi_nuc_molecule_and_chemistry("U34759", policy)
    dna = resolve_ncbi_nuc_molecule_and_chemistry("QT662269", policy)
    unknown = resolve_ncbi_nuc_molecule_and_chemistry("HV200497", policy)
    assert rna.molecule_type == "RNA"
    assert dna.molecule_type == "DNA"
    assert unknown.molecule_type == "unknown"


def test_runner_preserves_row_count_no_drop_or_park(tmp_path: Path) -> None:
    rows = [
        _s1("U34759", "acgtac"),
        _s1("QT662269", "acgtac"),
        _s1("DI115369", "acgtn"),
        _s1("FW366678", "acgtac"),
        _s1("DD421991", T7_MOTIF + "AC"),
        _s1("HV507922", "acgtac"),
    ]
    sidecar = [
        _meta("U34759", origin="acgtac"),
        _meta("QT662269", origin="acgtac"),
        _meta("DI115369", origin="acgtn"),
        _meta("FW366678", origin="acgtac"),
        _meta("DD421991", origin=T7_MOTIF + "AC"),
        _meta("HV507922", origin="acgtac"),
    ]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_ncbi_nuc_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=6,
    )
    assert result.stats.s1_rows == 6
    assert result.stats.s2_rows == 6
    assert result.stats.records_dropped == 0
    assert result.stats.records_parked == 0
    assert result.stats.applied_trims == 0
    assert result.stats.core_differs_from_full == 0
    assert result.stats.molecule_type_counts.get("RNA") == 1
    assert result.stats.molecule_type_counts.get("DNA") == 1
    assert result.stats.molecule_type_counts.get("unknown") == 4
    assert result.stats.t_to_u_count == 1
    assert result.stats.groups_considered == 0
    proposals = list(csv.DictReader(result.output_proposals.open(encoding="utf-8")))
    assert proposals
    assert all(row["applied"] == "false" for row in proposals)
    assert all(row["proposal_source"] == "known_motif" for row in proposals)
    normalised = list(csv.DictReader(result.output_normalised.open(encoding="utf-8")))
    assert all(row["sequence_core"] == row["sequence_full"] for row in normalised)
    assert all(row["target_name"] == "" for row in normalised)
    review = list(csv.DictReader(result.output_review.open(encoding="utf-8")))
    assert len(review) == result.stats.review_candidate_rows


def test_dispatcher_routes_ncbi_nuc(tmp_path: Path) -> None:
    rows = [_s1("U34759", "acgtac")]
    sidecar = [_meta("U34759", origin="acgtac")]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_s2_normalisation(
        repo_root=repo_root,
        source_key="ncbi_nuc",
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        source_policy=POLICY_PATH,
        expected_rows=1,
    )
    assert result.source_key == "ncbi_nuc"
    assert result.stats.s2_rows == 1


def test_report_has_no_absolute_paths_or_sequences(tmp_path: Path) -> None:
    rows = [_s1("U34759", "acgtac")]
    sidecar = [_meta("U34759", origin="acgtac")]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_ncbi_nuc_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=1,
    )
    report = result.output_report.read_text(encoding="utf-8")
    assert str(repo_root.resolve()) not in report
    assert "acgtac" not in report
    assert "ACGUAC" not in report
    assert "S3 has not started" in report
    assert "group-wise inference disabled for ncbi_nuc in this run" in report


def test_group_consensus_not_emitted(tmp_path: Path) -> None:
    rows = [_s1("U34759", "acgtac"), _s1("U37124", "acgtac")]
    sidecar = [_meta("U34759", origin="acgtac"), _meta("U37124", origin="acgtac")]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_ncbi_nuc_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=2,
    )
    proposals = list(csv.DictReader(result.output_proposals.open(encoding="utf-8")))
    assert all(row["proposal_source"] != "group_consensus" for row in proposals)
    assert result.stats.groups_considered == 0


@pytest.mark.skipif(
    not (
        PRODUCTION_S1.is_file()
        and PRODUCTION_SIDECAR.is_file()
        and PRODUCTION_RAW_DIR.is_dir()
    ),
    reason="NCBI Nucleotide S1 outputs or registered raw files not present locally",
)
def test_production_18_in_equals_18_out_without_embedding_sequences(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    extracted_dir = repo / "data" / "interim" / "extracted"
    raw_dir = repo / "data" / "raw" / "NCBI_nucleotide"
    extracted_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    shutil.copy(PRODUCTION_S1, extracted_dir / "ncbi_nuc_extracted.csv")
    shutil.copy(PRODUCTION_SIDECAR, extracted_dir / "ncbi_nuc_source_metadata.csv")
    for gb in PRODUCTION_RAW_DIR.glob("*.gb"):
        shutil.copy(gb, raw_dir / gb.name)
    output_dir = repo / "data" / "interim" / "normalised"
    result = run_ncbi_nuc_s2(
        repo_root=repo,
        input_dir=extracted_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=18,
    )
    assert result.stats.s1_rows == 18
    assert result.stats.s2_rows == 18
    assert result.stats.records_dropped == 0
    assert result.stats.records_parked == 0
    assert result.stats.unique_record_ids == 18
    assert result.stats.molecule_type_counts.get("RNA") == 5
    assert result.stats.molecule_type_counts.get("DNA") == 1
    assert result.stats.molecule_type_counts.get("unknown") == 12
    assert result.stats.t_to_u_count == 5
    assert result.stats.applied_trims == 0
    assert result.stats.core_differs_from_full == 0
    assert result.stats.groups_considered == 0
    report = result.output_report.read_text(encoding="utf-8")
    with PRODUCTION_S1.open(encoding="utf-8") as handle:
        first = next(csv.DictReader(handle))
    assert first["sequence_raw"] not in report

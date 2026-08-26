"""Tests for the AptaDB S2 adapter (synthetic sequences only).

Every literal nucleotide string in this file is shorter than 20 nt, except
programmatically generated homopolymers used to exercise length QC.
Does not read real AptaDB aptamer sequences.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadb import SIDECAR_COLUMNS  # noqa: E402
from adapters.aptadb_s2 import (  # noqa: E402
    AptaDBS2Error,
    load_aptadb_policy,
    normalise_aptadb_record,
    resolve_aptadb_molecule_and_chemistry,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S2_FORBIDDEN_FIELDS,
    empty_corpus_record,
)
from common.sequence_normalisation import load_normalisation_rules  # noqa: E402
from s2_normalise import run_aptadb_s2  # noqa: E402

POLICY_PATH = REPO_ROOT / "config" / "source_normalisation" / "aptadb.json"
RULES_PATH = REPO_ROOT / "config" / "sequence_normalisation_rules.json"


def _meta(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row["record_id"] = "aptadb:1"
    row["aptadb_aptamer_chemistry"] = "RNA"
    row.update(overrides)
    return row


def _s1(**overrides: str) -> dict[str, str]:
    record = empty_corpus_record()
    record.update(
        {
            "record_id": "aptadb:1",
            "sequence_raw": "ACGUAC",
            "source_db": "aptadb",
            "source_dataset": "aptadb_official_export_2026-08",
            "contributing_sources": "aptadb",
            "contributing_datasets": "aptadb_official_export_2026-08",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": "1",
            "target_name_raw": "demo_protein",
            "publication": "",
            "doi": "",
            "pubmed_id": "11111111",
            "notes": json.dumps({"apta_index": "1"}, separators=(",", ":")),
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
    with (input_dir / "aptadb_extracted.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(CORPUS_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        for row in canonical_rows:
            writer.writerow({col: row.get(col, "") for col in CORPUS_COLUMNS})
    with (input_dir / "aptadb_source_metadata.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(SIDECAR_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        for row in sidecar_rows:
            writer.writerow({col: row.get(col, "") for col in SIDECAR_COLUMNS})


@pytest.fixture(scope="module")
def policy():
    return load_aptadb_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def rules():
    return load_normalisation_rules()


# --- Molecule mapping ---


@pytest.mark.parametrize(
    ("source", "molecule", "chemistry"),
    [
        ("RNA", "RNA", "RNA"),
        ("DNA", "ssDNA", "DNA"),
    ],
)
def test_molecule_chemistry_map(policy, source, molecule, chemistry) -> None:
    result = resolve_aptadb_molecule_and_chemistry(
        {"aptadb_aptamer_chemistry": source},
        policy,
    )
    assert result.molecule_type == molecule
    assert result.chemistry == chemistry
    assert result.evidence_source == "aptamer_chemistry"


def test_unexpected_chemistry_hard_fails(policy) -> None:
    with pytest.raises(AptaDBS2Error, match="Unexpected or blank"):
        resolve_aptadb_molecule_and_chemistry(
            {"aptadb_aptamer_chemistry": "PNA"},
            policy,
        )


def test_blank_chemistry_hard_fails(policy) -> None:
    with pytest.raises(AptaDBS2Error, match="Unexpected or blank"):
        resolve_aptadb_molecule_and_chemistry(
            {"aptadb_aptamer_chemistry": ""},
            policy,
        )


def test_molecule_not_inferred_from_alphabet(policy, rules) -> None:
    result = normalise_aptadb_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(aptadb_aptamer_chemistry="RNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "RNA"


# --- Alphabet / T→U ---


def test_rna_u_no_transcription(policy, rules) -> None:
    result = normalise_aptadb_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(aptadb_aptamer_chemistry="RNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["alphabet_as_reported"] == "RNA"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGUAC"


def test_rna_t_transcribed(policy, rules) -> None:
    result = normalise_aptadb_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(aptadb_aptamer_chemistry="RNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["alphabet_as_reported"] == "DNA_T"
    assert result.canonical["t_to_u_applied"] == "true"
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert result.canonical["sequence_raw"] == "ACGTAC"


def test_ssdna_retains_t(policy, rules) -> None:
    result = normalise_aptadb_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(aptadb_aptamer_chemistry="DNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "ssDNA"
    assert result.canonical["chemistry"] == "DNA"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGTAC"


def test_mixed_t_u_not_silently_transcribed(policy, rules) -> None:
    result = normalise_aptadb_record(
        _s1(sequence_raw="ACGTU"),
        _meta(aptadb_aptamer_chemistry="RNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_full"] == "ACGTU"
    assert result.canonical["t_to_u_applied"] == "false"
    assert "mixed_t_u" in result.canonical["qc_flags"]


# --- QC ---


def test_lowercase_normalised(policy, rules) -> None:
    raw = "acguac"
    result = normalise_aptadb_record(
        _s1(sequence_raw=raw),
        _meta(aptadb_aptamer_chemistry="RNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == raw
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert "uppercase" in result.transformations


def test_gap_retained_as_row_and_flagged_via_shared_cleaning(policy, rules) -> None:
    raw = "AC-GUA"
    result = normalise_aptadb_record(
        _s1(sequence_raw=raw),
        _meta(aptadb_aptamer_chemistry="RNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == raw
    assert result.canonical["record_id"] == "aptadb:1"
    assert result.canonical["sequence_full"] == "AC-GUA"
    assert "alignment_gaps" in result.canonical["qc_flags"]
    assert "remove_display_separators" not in result.transformations
    assert "invalid_character" not in result.canonical["qc_flags"]


def test_internal_dot_flagged_as_alignment_gap_not_invalid(policy, rules) -> None:
    raw = "AC.GUA"
    result = normalise_aptadb_record(
        _s1(sequence_raw=raw),
        _meta(aptadb_aptamer_chemistry="RNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == raw
    assert result.canonical["sequence_full"] == "AC.GUA"
    assert "alignment_gaps" in result.canonical["qc_flags"]
    assert "invalid_character" not in result.canonical["qc_flags"]


def test_ascii_terminal_notation_still_stripped(policy, rules) -> None:
    raw = "5'-ACGUAC-3'"
    result = normalise_aptadb_record(
        _s1(sequence_raw=raw),
        _meta(aptadb_aptamer_chemistry="RNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == raw
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert "alignment_gaps" not in result.canonical["qc_flags"]


def test_ssdna_acg_only_alphabet_is_dna_t(policy, rules) -> None:
    result = normalise_aptadb_record(
        _s1(sequence_raw="ACGACG"),
        _meta(aptadb_aptamer_chemistry="DNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "ssDNA"
    assert result.canonical["alphabet_as_reported"] == "DNA_T"
    assert result.canonical["sequence_full"] == "ACGACG"
    assert result.canonical["t_to_u_applied"] == "false"


def test_rna_acg_only_alphabet_is_rna(policy, rules) -> None:
    result = normalise_aptadb_record(
        _s1(sequence_raw="ACGACG"),
        _meta(aptadb_aptamer_chemistry="RNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["alphabet_as_reported"] == "RNA"
    assert result.canonical["sequence_full"] == "ACGACG"


def test_trim_confidence_na_when_no_trim_applied(policy, rules) -> None:
    result = normalise_aptadb_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(aptadb_aptamer_chemistry="RNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["trim_status"] == "no_constants_detected"
    assert result.canonical["trim_confidence"] == "n/a"


def test_trim_confidence_not_medium_for_unapplied_known_motif(policy, rules) -> None:
    motif = "TAATACGACTCACTATA"
    result = normalise_aptadb_record(
        _s1(sequence_raw=motif + "AC"),
        _meta(aptadb_aptamer_chemistry="DNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["trim_status"] == "constants_suspected_unresolved"
    assert result.canonical["trim_confidence"] == "n/a"
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]


def test_invalid_character_flagged_not_dropped(policy, rules) -> None:
    raw = "ACGT3"
    result = normalise_aptadb_record(
        _s1(sequence_raw=raw),
        _meta(aptadb_aptamer_chemistry="DNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == raw
    assert "invalid_character" in result.canonical["qc_flags"]
    assert result.canonical["sequence_full"] != ""


def test_length_outside_policy_survives(policy, rules) -> None:
    short = normalise_aptadb_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(aptadb_aptamer_chemistry="RNA"),
        policy=policy,
        rules=rules,
    )
    assert "core_below_min_length" in short.canonical["qc_flags"]
    long_seq = "A" * 101
    long = normalise_aptadb_record(
        _s1(record_id="aptadb:2", native_id="2", sequence_raw=long_seq),
        _meta(record_id="aptadb:2", aptadb_aptamer_chemistry="DNA"),
        policy=policy,
        rules=rules,
    )
    assert long.canonical["sequence_raw"] == long_seq
    assert "core_above_max_length" in long.canonical["qc_flags"]


# --- Row / provenance / S4 boundary ---


def test_sequence_raw_and_provenance_unchanged(policy, rules) -> None:
    s1 = _s1(sequence_raw="acgtac", pubmed_id="222")
    result = normalise_aptadb_record(
        s1,
        _meta(aptadb_aptamer_chemistry="RNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == s1["sequence_raw"]
    assert result.canonical["record_id"] == s1["record_id"]
    assert result.canonical["native_id"] == s1["native_id"]
    assert result.canonical["source_db"] == s1["source_db"]
    assert result.canonical["source_dataset"] == s1["source_dataset"]
    assert result.canonical["pubmed_id"] == s1["pubmed_id"]
    assert result.canonical["publication"] == s1["publication"]
    assert result.canonical["contributing_sources"] == s1["contributing_sources"]
    assert result.canonical["contributing_datasets"] == s1["contributing_datasets"]


def test_s4_fields_remain_empty(policy, rules) -> None:
    result = normalise_aptadb_record(
        _s1(),
        _meta(),
        policy=policy,
        rules=rules,
    )
    for field in S2_FORBIDDEN_FIELDS:
        assert result.canonical[field] == ""


def test_pmid_not_copied_into_publication(policy, rules) -> None:
    result = normalise_aptadb_record(
        _s1(publication="", pubmed_id="333"),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["publication"] == ""
    assert result.canonical["pubmed_id"] == "333"


def test_construct_scope_unknown_when_untrimmed(policy, rules) -> None:
    result = normalise_aptadb_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["construct_scope"] == "unknown"
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert result.canonical["trim_status"] == "no_constants_detected"


# --- Runner: row count, grouping, proposals not applied, determinism ---


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


def test_runner_preserves_row_count(tmp_path: Path) -> None:
    rows = [
        _s1(record_id="aptadb:1", native_id="1", sequence_raw="ACGUAC"),
        _s1(record_id="aptadb:2", native_id="2", sequence_raw="ACGTAC"),
        _s1(
            record_id="aptadb:3",
            native_id="3",
            sequence_raw="ACGTAC",
            target_name_raw="",
        ),
    ]
    sidecar = [
        _meta(record_id="aptadb:1", aptadb_aptamer_chemistry="RNA"),
        _meta(record_id="aptadb:2", aptadb_aptamer_chemistry="DNA"),
        _meta(record_id="aptadb:3", aptadb_aptamer_chemistry="DNA"),
    ]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    result = run_aptadb_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=3,
    )
    assert result.stats.s1_rows == 3
    assert result.stats.s2_rows == 3
    assert result.stats.unique_record_ids == 3
    assert result.stats.sequence_raw_unchanged is True


def test_medium_confidence_proposal_does_not_mutate_core(tmp_path: Path) -> None:
    prefix = "AAAAAAAAAAAA"
    tails = ["CCCC", "GGGG", "UUUU", "CCGG", "GGCC"]
    canonical = []
    sidecar = []
    for index, tail in enumerate(tails, start=1):
        canonical.append(
            _s1(
                record_id=f"aptadb:{index}",
                native_id=str(index),
                sequence_raw=prefix + tail,
                target_name_raw="shared_target",
                publication="",
                pubmed_id="44444444",
            )
        )
        sidecar.append(
            _meta(
                record_id=f"aptadb:{index}",
                aptadb_aptamer_chemistry="RNA",
            )
        )
    # Anonymous non-protein rows share the PMID but must not join the group.
    for index in range(6, 9):
        canonical.append(
            _s1(
                record_id=f"aptadb:{index}",
                native_id=str(index),
                sequence_raw=prefix + "AAAA",
                target_name_raw="",
                publication="",
                pubmed_id="44444444",
            )
        )
        sidecar.append(
            _meta(
                record_id=f"aptadb:{index}",
                aptadb_aptamer_chemistry="DNA",
            )
        )
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, canonical, sidecar)
    result = run_aptadb_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=8,
    )
    assert result.stats.s2_rows == 8
    assert result.stats.core_differs_from_full == 0
    assert result.stats.applied_trims == 0
    assert result.stats.five_prime_proposals >= 1
    with result.output_normalised.open("r", encoding="utf-8", newline="") as handle:
        out_rows = list(csv.DictReader(handle))
    for row in out_rows:
        assert row["sequence_core"] == row["sequence_full"]
        assert row["publication"] == ""
        assert row["pubmed_id"] == "44444444"
    with result.output_proposals.open("r", encoding="utf-8", newline="") as handle:
        proposals = list(csv.DictReader(handle))
    group_rows = [p for p in proposals if p["proposal_source"] == "group_consensus"]
    assert group_rows
    assert all(p["applied"] == "false" for p in group_rows)
    assert all(p["confidence"] == "medium" for p in group_rows)


def test_publication_preferred_in_runner_grouping(tmp_path: Path) -> None:
    prefix = "AAAAAAAAAAAA"
    tails = ["CCCC", "GGGG", "UUUU", "CCGG", "GGCC"]
    canonical = []
    sidecar = []
    for index, tail in enumerate(tails, start=1):
        canonical.append(
            _s1(
                record_id=f"aptadb:{index}",
                native_id=str(index),
                sequence_raw=prefix + tail,
                target_name_raw="shared_target",
                publication="Paper A",
                pubmed_id="should_be_ignored",
            )
        )
        sidecar.append(
            _meta(record_id=f"aptadb:{index}", aptadb_aptamer_chemistry="RNA")
        )
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, canonical, sidecar)
    result = run_aptadb_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=5,
    )
    with result.output_normalised.open("r", encoding="utf-8", newline="") as handle:
        out_rows = list(csv.DictReader(handle))
    assert all(row["publication"] == "Paper A" for row in out_rows)
    assert all(row["pubmed_id"] == "should_be_ignored" for row in out_rows)
    assert result.stats.five_prime_proposals >= 1


def test_empty_target_does_not_group_by_pmid_alone(tmp_path: Path) -> None:
    prefix = "AAAAAAAAAAAA"
    tails = ["CCCC", "GGGG", "UUUU", "CCGG", "GGCC"]
    canonical = []
    sidecar = []
    for index, tail in enumerate(tails, start=1):
        canonical.append(
            _s1(
                record_id=f"aptadb:{index}",
                native_id=str(index),
                sequence_raw=prefix + tail,
                target_name_raw="",
                publication="",
                pubmed_id="55555555",
            )
        )
        sidecar.append(
            _meta(record_id=f"aptadb:{index}", aptadb_aptamer_chemistry="RNA")
        )
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, canonical, sidecar)
    result = run_aptadb_s2(
        repo_root=repo_root,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=5,
    )
    assert result.stats.groups_considered == 0
    assert result.stats.five_prime_proposals == 0
    assert result.stats.three_prime_proposals == 0


def test_deterministic_rerun(tmp_path: Path) -> None:
    rows = [
        _s1(record_id="aptadb:1", native_id="1", sequence_raw="ACGUAC"),
        _s1(record_id="aptadb:2", native_id="2", sequence_raw="acgtac"),
    ]
    sidecar = [
        _meta(record_id="aptadb:1", aptadb_aptamer_chemistry="RNA"),
        _meta(record_id="aptadb:2", aptadb_aptamer_chemistry="DNA"),
    ]
    repo_root, input_dir, output_dir = _runner_pair(tmp_path, rows, sidecar)
    first = run_aptadb_s2(
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
    result = run_aptadb_s2(
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

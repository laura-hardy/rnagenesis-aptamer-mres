"""Tests for the AptaIndex S2 adapter (synthetic chemical notation only).

Real AptaIndex sequences are never embedded. Optional local production
skipif gates assert counts and hashes without writing sequences into
this file.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptaindex import SIDECAR_COLUMNS  # noqa: E402
from adapters.aptaindex_s2 import (  # noqa: E402
    GROUP_INFERENCE_DISABLED,
    load_aptaindex_policy,
    normalise_aptaindex_record,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S2_FORBIDDEN_FIELDS,
    empty_corpus_record,
)
from common.sequence_normalisation import load_normalisation_rules  # noqa: E402
from s2_normalise import (  # noqa: E402
    run_aptaindex_s2,
    run_s2_normalisation,
)

POLICY_PATH = REPO_ROOT / "config" / "source_normalisation" / "aptaindex.json"
RULES_PATH = REPO_ROOT / "config" / "sequence_normalisation_rules.json"
PRODUCTION_S1 = REPO_ROOT / "data" / "interim" / "extracted" / "aptaindex_extracted.csv"
PRODUCTION_SIDECAR = (
    REPO_ROOT / "data" / "interim" / "extracted" / "aptaindex_source_metadata.csv"
)
PRODUCTION_RAW = (
    REPO_ROOT / "data" / "raw" / "AptaIndex" / "aptamers-export-2026-07-22.csv"
)
EXPECTED_RAW_SHA = (
    "912b8e554fa2bb2ed3a9e9bdf1cfbe4f757d8c7a00c401629e5bcb5e5c2877a8"
)


def _meta(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row["record_id"] = "aptaindex:0001"
    row["aptaindex_native_id"] = "0001"
    row["aptaindex_csv_data_row"] = "1"
    row["aptaindex_type"] = "DNA"
    row.update(overrides)
    return row


def _s1(**overrides: str) -> dict[str, str]:
    record = empty_corpus_record()
    record.update(
        {
            "record_id": "aptaindex:0001",
            "sequence_raw": "5'-dApdTpdGpdC-3'",
            "source_db": "aptaindex",
            "source_dataset": "aptaindex_export_2026-07-22",
            "contributing_sources": "aptaindex",
            "contributing_datasets": "aptaindex_export_2026-07-22",
            "corroboration_count": "1",
            "redistribution_status": "restricted",
            "independently_attested_by_permissive_source": "false",
            "native_id": "0001",
            "target_name_raw": "demo_target",
            "publication": "Demo Ref",
            "notes": json.dumps({"title": "demo"}, separators=(",", ":")),
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
    with (input_dir / "aptaindex_extracted.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(CORPUS_COLUMNS),
            lineterminator="\n",
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        for row in canonical_rows:
            writer.writerow({col: row.get(col, "") for col in CORPUS_COLUMNS})
    with (input_dir / "aptaindex_source_metadata.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(SIDECAR_COLUMNS),
            lineterminator="\n",
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        for row in sidecar_rows:
            writer.writerow({col: row.get(col, "") for col in SIDECAR_COLUMNS})


def _normalise(*, sequence_raw: str | None = None, aptaindex_type: str = "DNA"):
    s1_row = _s1()
    if sequence_raw is not None:
        s1_row["sequence_raw"] = sequence_raw
    meta = _meta(record_id=s1_row["record_id"], aptaindex_type=aptaindex_type)
    return normalise_aptaindex_record(
        s1_row,
        meta,
        policy=load_aptaindex_policy(POLICY_PATH),
        rules=load_normalisation_rules(RULES_PATH),
    )


def test_policy_disables_group_inference_and_trims() -> None:
    policy = load_aptaindex_policy(POLICY_PATH)
    assert policy.group_inference_key == GROUP_INFERENCE_DISABLED
    assert policy.apply_approved_trims is False
    assert policy.alphabet_as_reported_nucleic_acid == "chemical_notation"


def test_s2_dispatch_recognises_aptaindex(tmp_path: Path) -> None:
    input_dir = tmp_path / "data" / "interim" / "extracted"
    output_dir = tmp_path / "data" / "interim" / "normalised"
    _write_inputs(input_dir, [_s1()], [_meta()])
    result = run_s2_normalisation(
        repo_root=tmp_path,
        source_key="aptaindex",
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        source_policy=POLICY_PATH,
        expected_rows=1,
    )
    assert result.source_key == "aptaindex"
    assert result.stats.s2_rows == 1


def test_synthetic_rows_in_equal_rows_out_no_loss(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "data" / "interim" / "out"
    rows = []
    meta = []
    specs = [
        ("0001", "5'-dApdTpdGpdC-3'", "DNA"),
        ("0002", "5'-rAprUprGprC-3'", "RNA"),
        ("0003", "", "DNA"),
    ]
    for native, seq, typ in specs:
        rows.append(
            _s1(
                record_id=f"aptaindex:{native}",
                native_id=native,
                sequence_raw=seq,
            )
        )
        meta.append(
            _meta(
                record_id=f"aptaindex:{native}",
                aptaindex_native_id=native,
                aptaindex_type=typ,
            )
        )
    _write_inputs(input_dir, rows, meta)
    result = run_aptaindex_s2(
        repo_root=tmp_path,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=3,
    )
    assert result.stats.s1_rows == 3
    assert result.stats.s2_rows == 3
    assert result.stats.records_dropped == 0
    assert result.stats.unique_record_ids == 3


def test_successful_dna_retains_t() -> None:
    result = _normalise(
        sequence_raw="5'-dApdTpdGpdC-3'",
        aptaindex_type="DNA",
    )
    assert result.canonical["sequence_full"] == "ATGC"
    assert result.canonical["sequence_core"] == "ATGC"
    assert result.canonical["molecule_type"] == "ssDNA"
    assert result.canonical["chemistry"] == "DNA"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["alphabet_as_reported"] == "chemical_notation"
    assert "T" in result.canonical["sequence_full"]


def test_successful_rna_produces_rna_nucleotides() -> None:
    result = _normalise(
        sequence_raw="5'-rAprUprGprC-3'",
        aptaindex_type="RNA",
    )
    assert result.canonical["sequence_full"] == "AUGC"
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "RNA"
    assert result.canonical["alphabet_as_reported"] == "chemical_notation"
    assert result.canonical["t_to_u_applied"] == "false"


def test_rna_chemical_t_applies_t_to_u() -> None:
    result = _normalise(
        sequence_raw="5'-rAprTprGprC-3'",
        aptaindex_type="RNA",
    )
    assert result.canonical["sequence_full"] == "AUGC"
    assert result.canonical["t_to_u_applied"] == "true"
    assert result.canonical["sequence_raw"] == "5'-rAprTprGprC-3'"
    assert "T" not in result.canonical["sequence_full"]


def test_2f_rna_keeps_token_family_before_chemistry_mapping() -> None:
    result = _normalise(
        sequence_raw="5'-fAprU pfGprC-3'",
        aptaindex_type="2'-F-RNA",
    )
    assert result.qc["token_family_summary"] == "f+r"
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "2F-RNA"
    assert result.canonical["sequence_full"] == "AUGC"
    assert result.canonical["alphabet_as_reported"] == "chemical_notation"


def test_alphabet_is_chemical_notation_not_dna_t_or_rna() -> None:
    dna = _normalise(sequence_raw="5'-dApdTpdC-3'", aptaindex_type="DNA")
    rna = _normalise(sequence_raw="5'-rAprUprC-3'", aptaindex_type="RNA")
    assert dna.canonical["alphabet_as_reported"] == "chemical_notation"
    assert rna.canonical["alphabet_as_reported"] == "chemical_notation"
    assert dna.canonical["alphabet_as_reported"] != "DNA_T"
    assert rna.canonical["alphabet_as_reported"] != "RNA"


def test_unknown_token_is_full_parse_failure_never_partial() -> None:
    result = _normalise(
        sequence_raw="5'-dApXlkdT-3'",
        aptaindex_type="DNA",
    )
    assert result.qc["parser_status"] == "unsupported"
    assert result.canonical["sequence_full"] == ""
    assert result.canonical["sequence_core"] == ""
    assert result.canonical["sequence_length_full"] == ""
    assert "unsupported_notation" in result.canonical["qc_flags"]
    assert result.canonical["sequence_raw"] == "5'-dApXlkdT-3'"
    assert result.canonical["alphabet_as_reported"] == "chemical_notation"


def test_peptide_row_retained_parser_not_applicable() -> None:
    result = _normalise(
        sequence_raw="ACDEFGHIKLMNPQRSTVWY",
        aptaindex_type="Peptide",
    )
    assert result.qc["parser_status"] == "not_applicable_peptide"
    assert result.canonical["sequence_full"] == ""
    assert result.canonical["sequence_raw"] == "ACDEFGHIKLMNPQRSTVWY"
    assert result.canonical["alphabet_as_reported"] == ""
    assert "parser_not_applicable_peptide" in result.canonical["qc_flags"]
    assert result.canonical["molecule_type"] == "unknown"
    assert result.canonical["record_id"] == "aptaindex:0001"


def test_missing_sequence_retained() -> None:
    result = _normalise(sequence_raw="", aptaindex_type="DNA")
    assert result.qc["parser_status"] == "missing"
    assert result.canonical["sequence_full"] == ""
    assert result.canonical["alphabet_as_reported"] == "missing"
    assert "missing_sequence" in result.canonical["qc_flags"]
    assert result.canonical["t_to_u_applied"] == "false"


def test_unsupported_type_retained_and_flagged() -> None:
    result = _normalise(
        sequence_raw="5'-dApdTpdG-3'",
        aptaindex_type="PNA",
    )
    assert result.canonical["sequence_full"] == "ATG"
    assert result.canonical["molecule_type"] == "unknown"
    assert result.canonical["chemistry"] == "unknown"
    assert "source_type_unsupported" in result.canonical["qc_flags"]
    assert result.qc["mapping_class"] == "source_type_unsupported"


def test_type_token_disagreement_retained_and_flagged() -> None:
    result = _normalise(
        sequence_raw="5'-rAprUprG-3'",
        aptaindex_type="DNA",
    )
    assert result.canonical["sequence_full"] == "AUG"
    assert result.canonical["molecule_type"] == "unknown"
    assert result.canonical["chemistry"] == "unknown"
    assert "source_type_token_disagreement" in result.canonical["qc_flags"]
    assert result.canonical["t_to_u_applied"] == "false"


def test_mixed_t_and_u_retained_not_rejected() -> None:
    result = _normalise(
        sequence_raw="5'-rAprTprUprG-3'",
        aptaindex_type="RNA",
    )
    assert result.canonical["sequence_full"] != ""
    assert "T" in result.canonical["sequence_full"]
    assert "U" in result.canonical["sequence_full"]
    assert result.canonical["t_to_u_applied"] == "false"
    assert "mixed_t_u" in result.canonical["qc_flags"]
    assert result.qc["parser_status"] == "success"


def test_inherited_prefix_syntax_event_in_qc_not_a_chemistry_claim() -> None:
    result = _normalise(
        sequence_raw="5'-rAprUprGpUprC-3'",
        aptaindex_type="RNA",
    )
    assert result.qc["parser_status"] == "success"
    assert result.qc["inherited_token_prefix"] == "r"
    assert "inherited_token_prefix" in result.qc["parser_syntax_events"]
    assert result.canonical["sequence_raw"] == "5'-rAprUprGpUprC-3'"
    assert result.canonical["sequence_full"] == "AUGUC"
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "RNA"
    assert result.qc["mapping_class"] == "straightforward_rna"


def test_terminal_phosphate_syntax_event_in_qc() -> None:
    result = _normalise(
        sequence_raw="5'-{5'/Phosphate}-rAprUprG-3'",
        aptaindex_type="RNA",
    )
    assert result.qc["parser_status"] == "success"
    assert "terminal_phosphate_stripped" in result.qc["parser_syntax_events"]
    assert result.canonical["sequence_raw"] == "5'-{5'/Phosphate}-rAprUprG-3'"
    assert result.canonical["sequence_full"] == "AUG"


def test_thiol_cap_syntax_event_does_not_enter_nucleotide_sequence() -> None:
    result = _normalise(
        sequence_raw="5'-SH-(CH2)6-dApdTpdG-3'",
        aptaindex_type="DNA",
    )
    assert result.qc["parser_status"] == "success"
    assert "terminal_thiol_cap_stripped" in result.qc["parser_syntax_events"]
    assert result.canonical["sequence_full"] == "ATG"
    assert result.canonical["molecule_type"] == "ssDNA"


def test_no_canonical_s4_fields_populated() -> None:
    result = _normalise()
    for field in S2_FORBIDDEN_FIELDS:
        assert result.canonical[field] == ""


def test_length_equals_len_when_present() -> None:
    result = _normalise()
    assert result.canonical["sequence_length_full"] == str(
        len(result.canonical["sequence_full"])
    )
    assert result.canonical["sequence_length_core"] == str(
        len(result.canonical["sequence_core"])
    )


def test_sequence_core_follows_shared_trimming_no_aptaindex_trim() -> None:
    result = _normalise()
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert result.canonical["trim_status"] in {
        "no_constants_detected",
        "constants_suspected_unresolved",
    }


def test_l_rna_not_auto_mapped() -> None:
    result = _normalise(
        sequence_raw="5'-LrALrGLrC-3'",
        aptaindex_type="L-RNA",
    )
    assert result.qc["parser_status"] == "success"
    assert result.canonical["molecule_type"] == "unknown"
    assert result.canonical["chemistry"] == "unknown"
    assert "l_nucleotide_syntax" in result.canonical["qc_flags"]
    assert result.qc["mapping_class"] == "l_rna"


def test_chimeric_not_auto_mapped() -> None:
    result = _normalise(
        sequence_raw="5'-dAprG-3'",
        aptaindex_type="Chimeric",
    )
    assert result.qc["parser_status"] == "success"
    assert result.canonical["molecule_type"] == "unknown"
    assert result.qc["mapping_class"] == "chimeric"


def test_sequence_raw_unchanged_when_parse_succeeds() -> None:
    raw = "5'-dApdTpdGpdC-3'"
    result = _normalise(sequence_raw=raw, aptaindex_type="DNA")
    assert result.canonical["sequence_raw"] == raw
    assert result.canonical["sequence_full"] == "ATGC"


def test_deterministic_rerun(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "data" / "interim" / "out"
    _write_inputs(input_dir, [_s1()], [_meta()])
    result = run_aptaindex_s2(
        repo_root=tmp_path,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=1,
        check_deterministic_rerun=True,
    )
    assert result.deterministic_rerun_ok is True


def test_qc_has_no_sequence_columns(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "data" / "interim" / "out"
    _write_inputs(input_dir, [_s1()], [_meta()])
    result = run_aptaindex_s2(
        repo_root=tmp_path,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=1,
    )
    with result.output_qc.open(encoding="utf-8", newline="") as handle:
        fieldnames = list(csv.DictReader(handle).fieldnames or [])
    for forbidden in (
        "sequence_raw",
        "sequence_full",
        "sequence_core",
        "aptaindex_sequence",
    ):
        assert forbidden not in fieldnames


def test_report_has_no_synthetic_sequence_or_absolute_path(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "data" / "interim" / "out"
    raw = "5'-dApdTpdGpdC-3'"
    _write_inputs(input_dir, [_s1(sequence_raw=raw)], [_meta()])
    result = run_aptaindex_s2(
        repo_root=tmp_path,
        input_dir=input_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=1,
    )
    text = result.output_report.read_text(encoding="utf-8")
    assert raw not in text
    assert str(tmp_path.resolve()) not in text
    assert "chemical_notation" in text


def test_stdout_has_no_sequence(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "data" / "interim" / "out"
    raw = "5'-dApdTpdGpdC-3'"
    _write_inputs(input_dir, [_s1(sequence_raw=raw)], [_meta()])
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        run_aptaindex_s2(
            repo_root=tmp_path,
            input_dir=input_dir,
            output_dir=output_dir,
            rules_path=RULES_PATH,
            policy_path=POLICY_PATH,
            expected_rows=1,
        )
    assert raw not in buffer.getvalue()


@pytest.mark.skipif(not PRODUCTION_S1.is_file(), reason="AptaIndex S1 not present")
@pytest.mark.skipif(not PRODUCTION_SIDECAR.is_file(), reason="AptaIndex sidecar missing")
@pytest.mark.skipif(not PRODUCTION_RAW.is_file(), reason="AptaIndex raw missing")
def test_production_1050_in_1050_out_without_embedding_sequences(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    extracted_dir = repo / "data" / "interim" / "extracted"
    raw_dir = repo / "data" / "raw" / "AptaIndex"
    extracted_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    shutil.copy(PRODUCTION_S1, extracted_dir / "aptaindex_extracted.csv")
    shutil.copy(PRODUCTION_SIDECAR, extracted_dir / "aptaindex_source_metadata.csv")
    shutil.copy(PRODUCTION_RAW, raw_dir / "aptamers-export-2026-07-22.csv")
    output_dir = repo / "data" / "interim" / "normalised"
    result = run_aptaindex_s2(
        repo_root=repo,
        input_dir=extracted_dir,
        output_dir=output_dir,
        rules_path=RULES_PATH,
        policy_path=POLICY_PATH,
        expected_rows=1050,
    )
    assert result.stats.s1_rows == 1050
    assert result.stats.s2_rows == 1050
    assert result.stats.records_dropped == 0
    assert result.stats.unique_record_ids == 1050
    assert result.stats.unique_native_ids == 1050
    assert result.stats.missing_sequence_rows == 31
    assert result.stats.peptide_rows == 57
    assert result.stats.nonempty_nucleic_acid_rows == 962
    assert (
        result.stats.successful_parses + result.stats.unsupported_nucleic_parses
        == 962
    )
    assert result.stats.core_differs_from_full == 0
    digest = hashlib.sha256(PRODUCTION_RAW.read_bytes()).hexdigest()
    assert digest == EXPECTED_RAW_SHA
    report = result.output_report.read_text(encoding="utf-8")
    assert str(REPO_ROOT.resolve()) not in report

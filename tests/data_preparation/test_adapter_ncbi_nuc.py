"""Tests for the NCBI Nucleotide S1 adapter (synthetic fixtures only).

Real aptamer sequences are never embedded. Fixtures use non-biological
placeholder residues only.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters import ADAPTER_KEYS  # noqa: E402
from adapters.ncbi_nuc import (  # noqa: E402
    SIDECAR_COLUMNS,
    SOURCE_DB,
    NcbiNucAdapterError,
    NcbiNucRegisteredInput,
    canonical_pubmed_id,
    extract_ncbi_nuc,
    extract_origin_residues,
    write_sidecar_csv_atomic,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S1_FORBIDDEN_FIELDS,
)
from s0_build_registry import REQUIRED_COLUMNS  # noqa: E402
from s1_extract import run_s1_extraction  # noqa: E402

SYNTHETIC_LOWER = "acgtacgt"
SYNTHETIC_T = "ttttacgt"
SYNTHETIC_N = "acgnacgt"
SYNTHETIC_IUPAC = "acgtryac"


def _hash_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_genbank(
    path: Path,
    *,
    locus: str,
    accession: str,
    sequence: str,
    molecule: str = "DNA",
    pubmed: str | None = None,
    pubmed_values: list[str] | None = None,
    definition: str = "Synthetic fixture record; not a biological aptamer.",
    comment: str = "",
    extra_feature: bool = False,
    version: str | None = None,
) -> None:
    length = len(sequence)
    version_token = version if version is not None else f"{accession}.1"
    pubmed_list = pubmed_values
    if pubmed_list is None:
        pubmed_list = [pubmed] if pubmed else []
    ref_blocks: list[str] = []
    for idx, pmid in enumerate(pubmed_list, start=1):
        pubmed_line = f"\n   PUBMED   {pmid}" if pmid else ""
        ref_blocks.append(
            f"REFERENCE   {idx}  (bases 1 to {length})\n"
            "  AUTHORS   Fixture,A.\n"
            f"  TITLE     Synthetic title {idx}.\n"
            f"  JOURNAL   Synthetic J. {idx}, 1-2 (2026)"
            f"{pubmed_line}\n"
        )
    if not ref_blocks:
        ref_blocks.append(
            f"REFERENCE   1  (bases 1 to {length})\n"
            "  AUTHORS   Fixture,A.\n"
            "  TITLE     Synthetic title.\n"
            "  JOURNAL   Synthetic J. 1, 1-2 (2026)\n"
        )
    comment_block = ""
    if comment:
        comment_block = f"COMMENT     {comment}\n"
    extra = ""
    if extra_feature:
        extra = (
            f"     misc_feature    complement(1..{length})\n"
            '                     /note="synthetic orientation fixture"\n'
        )
    origin_groups = [sequence[i : i + 10] for i in range(0, len(sequence), 10)]
    origin_line = f"{1:>9} " + " ".join(origin_groups)
    text = (
        f"LOCUS       {locus:<16}{length:>12} bp    {molecule:<7} linear   SYN 01-JAN-2026\n"
        f"DEFINITION  {definition}\n"
        f"ACCESSION   {accession}\n"
        f"VERSION     {version_token}\n"
        "KEYWORDS    synthetic_fixture.\n"
        "SOURCE      synthetic construct\n"
        "  ORGANISM  synthetic construct\n"
        "            other sequences; artificial sequences.\n"
        f"{''.join(ref_blocks)}"
        f"{comment_block}"
        "FEATURES             Location/Qualifiers\n"
        f"     source          1..{length}\n"
        '                     /organism="synthetic construct"\n'
        '                     /mol_type="unassigned DNA"\n'
        f"{extra}"
        "ORIGIN\n"
        f"{origin_line}\n"
        "//\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _input(
    path: Path,
    relative_path: str,
    n_rows_expected: int | None = 1,
) -> NcbiNucRegisteredInput:
    return NcbiNucRegisteredInput(
        path=path,
        relative_path=relative_path,
        sha256=_hash_path(path),
        n_rows_expected=n_rows_expected,
    )


def _make_s1_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "docs" / "data_curation").mkdir(parents=True)
    (repo / "scripts" / "data_preparation").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "data" / "raw" / "NCBI_nucleotide").mkdir(parents=True)
    (repo / "data" / "interim" / "extracted").mkdir(parents=True)
    return repo


def test_adapter_key_registered() -> None:
    assert "ncbi_nuc" in ADAPTER_KEYS


def test_homogeneous_multi_file_emits_one_row_per_record(tmp_path: Path) -> None:
    first = tmp_path / "file_b.gb"
    second = tmp_path / "file_a.gb"
    _write_genbank(first, locus="LOCUSB", accession="ACC_B", sequence=SYNTHETIC_LOWER)
    _write_genbank(second, locus="LOCUSA", accession="ACC_A", sequence=SYNTHETIC_T)
    result = extract_ncbi_nuc(
        [
            _input(first, "data/raw/NCBI_nucleotide/file_b.gb"),
            _input(second, "data/raw/NCBI_nucleotide/file_a.gb"),
        ],
        source_dataset="ncbi_nuc_demo",
        redistribution_status="unknown",
        expected_records=2,
    )
    assert result.stats.input_files == 2
    assert result.stats.canonical_rows == 2
    assert result.stats.sidecar_rows == 2
    assert [row["native_id"] for row in result.canonical_rows] == ["ACC_B", "ACC_A"]
    assert [row["record_id"] for row in result.canonical_rows] == [
        "ncbi_nuc:ACC_B",
        "ncbi_nuc:ACC_A",
    ]


def test_registry_order_not_glob_order(tmp_path: Path) -> None:
    """Processing follows the supplied registry order, not glob order."""
    directory = tmp_path / "NCBI_nucleotide"
    z_first = directory / "z_first.gb"
    a_second = directory / "a_second.gb"
    _write_genbank(z_first, locus="LOCZ", accession="ACC_Z", sequence=SYNTHETIC_LOWER)
    _write_genbank(a_second, locus="LOCA", accession="ACC_Y", sequence=SYNTHETIC_T)
    glob_order = [path.name for path in sorted(directory.glob("*.gb"))]
    assert glob_order == ["a_second.gb", "z_first.gb"]
    result = extract_ncbi_nuc(
        [
            _input(z_first, "data/raw/NCBI_nucleotide/z_first.gb"),
            _input(a_second, "data/raw/NCBI_nucleotide/a_second.gb"),
        ],
        source_dataset="ncbi_nuc_demo",
        redistribution_status="unknown",
        expected_records=2,
    )
    assert [row["native_id"] for row in result.canonical_rows] == ["ACC_Z", "ACC_Y"]


def test_accession_is_native_id_not_filename_or_locus(tmp_path: Path) -> None:
    path = tmp_path / "sequence (1).gb"
    _write_genbank(
        path,
        locus="XXU34759",
        accession="U34759X",
        sequence=SYNTHETIC_LOWER,
        version="U34759X.1",
    )
    result = extract_ncbi_nuc(
        [_input(path, "data/raw/NCBI_nucleotide/sequence (1).gb")],
        source_dataset="ncbi_nuc_demo",
        redistribution_status="unknown",
        expected_records=1,
    )
    row = result.canonical_rows[0]
    sidecar = result.sidecar_rows[0]
    assert row["native_id"] == "U34759X"
    assert row["record_id"] == "ncbi_nuc:U34759X"
    assert row["native_id"] != "sequence (1).gb"
    assert row["native_id"] != "sequence (1)"
    assert row["native_id"] != "XXU34759"
    assert row["native_id"] != "U34759X.1"
    assert sidecar["ncbi_nuc_locus"] == "XXU34759"
    assert sidecar["ncbi_nuc_version"] == "U34759X.1"
    assert sidecar["ncbi_nuc_input_basename"] == "sequence (1).gb"
    assert sidecar["ncbi_nuc_accession"] == "U34759X"


def test_missing_accession_fails(tmp_path: Path) -> None:
    path = tmp_path / "missing.gb"
    _write_genbank(path, locus="SYNLOC", accession="SYNACC", sequence=SYNTHETIC_LOWER)
    text = path.read_text(encoding="utf-8").replace(
        "ACCESSION   SYNACC\n", "ACCESSION   \n"
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(NcbiNucAdapterError, match="missing ACCESSION"):
        extract_ncbi_nuc(
            [_input(path, "data/raw/NCBI_nucleotide/missing.gb")],
            source_dataset="ncbi_nuc_demo",
            redistribution_status="unknown",
            expected_records=None,
        )


def test_duplicate_accession_fails(tmp_path: Path) -> None:
    first = tmp_path / "one.gb"
    second = tmp_path / "two.gb"
    _write_genbank(first, locus="LOC1", accession="DUPACC", sequence=SYNTHETIC_LOWER)
    _write_genbank(second, locus="LOC2", accession="DUPACC", sequence=SYNTHETIC_T)
    with pytest.raises(NcbiNucAdapterError, match="Duplicate ACCESSION"):
        extract_ncbi_nuc(
            [
                _input(first, "data/raw/NCBI_nucleotide/one.gb"),
                _input(second, "data/raw/NCBI_nucleotide/two.gb"),
            ],
            source_dataset="ncbi_nuc_demo",
            redistribution_status="unknown",
            expected_records=2,
        )


def test_origin_display_syntax_removed_case_and_iupac_preserved(
    tmp_path: Path,
) -> None:
    path = tmp_path / "origin.gb"
    _write_genbank(path, locus="LOCN", accession="ACCN", sequence=SYNTHETIC_IUPAC)
    result = extract_ncbi_nuc(
        [_input(path, "data/raw/NCBI_nucleotide/origin.gb")],
        source_dataset="ncbi_nuc_demo",
        redistribution_status="unknown",
        expected_records=1,
    )
    raw = result.canonical_rows[0]["sequence_raw"]
    assert raw == SYNTHETIC_IUPAC
    assert raw == raw.lower()
    assert " " not in raw
    assert raw == extract_origin_residues(path.read_text(encoding="utf-8"))
    assert result.sidecar_rows[0]["ncbi_nuc_origin_residues"] == SYNTHETIC_IUPAC


def test_n_residue_preserved_and_no_t_to_u(tmp_path: Path) -> None:
    path = tmp_path / "nt.gb"
    _write_genbank(
        path,
        locus="LOCNT",
        accession="ACCNT",
        sequence=SYNTHETIC_N + SYNTHETIC_T,
    )
    result = extract_ncbi_nuc(
        [_input(path, "data/raw/NCBI_nucleotide/nt.gb")],
        source_dataset="ncbi_nuc_demo",
        redistribution_status="unknown",
        expected_records=1,
    )
    raw = result.canonical_rows[0]["sequence_raw"]
    assert "n" in raw
    assert "t" in raw
    assert "u" not in raw
    assert raw == SYNTHETIC_N + SYNTHETIC_T


def test_no_target_extraction_and_canonical_accession_empty(tmp_path: Path) -> None:
    path = tmp_path / "target.gb"
    _write_genbank(
        path,
        locus="LOCT",
        accession="ACCT",
        sequence=SYNTHETIC_LOWER,
        definition="Synthetic phospholamban cyclin T1 ErbB2 fixture.",
        comment="HCV amino acids are mentioned only as later context.",
    )
    result = extract_ncbi_nuc(
        [_input(path, "data/raw/NCBI_nucleotide/target.gb")],
        source_dataset="ncbi_nuc_demo",
        redistribution_status="unknown",
        expected_records=1,
    )
    row = result.canonical_rows[0]
    sidecar = result.sidecar_rows[0]
    assert row["target_name_raw"] == ""
    assert row["accession"] == ""
    assert "phospholamban" in sidecar["ncbi_nuc_definition"]
    assert "HCV" in sidecar["ncbi_nuc_comment"]
    for field in S1_FORBIDDEN_FIELDS:
        assert row[field] == ""


def test_structured_unique_pmid_mapping(tmp_path: Path) -> None:
    path = tmp_path / "pmid.gb"
    _write_genbank(
        path,
        locus="LOCP",
        accession="ACCP",
        sequence=SYNTHETIC_LOWER,
        pubmed_values=["9222504", ""],
    )
    result = extract_ncbi_nuc(
        [_input(path, "data/raw/NCBI_nucleotide/pmid.gb")],
        source_dataset="ncbi_nuc_demo",
        redistribution_status="unknown",
        expected_records=1,
    )
    assert result.canonical_rows[0]["pubmed_id"] == "9222504"
    assert result.canonical_rows[0]["publication"] == ""
    assert result.canonical_rows[0]["doi"] == ""
    refs = json.loads(result.sidecar_rows[0]["ncbi_nuc_references_json"])
    assert [item["pubmed_id"] for item in refs] == ["9222504", ""]


def test_multiple_or_missing_pmid_remains_conservative() -> None:
    assert canonical_pubmed_id([]) == ""
    assert canonical_pubmed_id([{"pubmed_id": ""}, {"pubmed_id": ""}]) == ""
    assert (
        canonical_pubmed_id([{"pubmed_id": "111"}, {"pubmed_id": "222"}]) == ""
    )
    assert canonical_pubmed_id([{"pubmed_id": "111"}, {"pubmed_id": "111"}]) == "111"


def test_features_comment_references_retained(tmp_path: Path) -> None:
    path = tmp_path / "meta.gb"
    _write_genbank(
        path,
        locus="LOCM",
        accession="ACCM",
        sequence=SYNTHETIC_LOWER,
        comment="Complete comment fixture for later target resolution.",
        extra_feature=True,
        pubmed="9751715",
    )
    result = extract_ncbi_nuc(
        [_input(path, "data/raw/NCBI_nucleotide/meta.gb")],
        source_dataset="ncbi_nuc_demo",
        redistribution_status="unknown",
        expected_records=1,
    )
    sidecar = result.sidecar_rows[0]
    features = json.loads(sidecar["ncbi_nuc_features_json"])
    assert [item["type"] for item in features] == ["source", "misc_feature"]
    assert features[0]["location"] == "1..8"
    assert features[1]["location"] == "complement(1..8)"
    assert features[1]["strand"] == "-"
    assert features[0]["qualifiers"]["mol_type"] == ["unassigned DNA"]
    assert "Complete comment fixture" in sidecar["ncbi_nuc_comment"]
    refs = json.loads(sidecar["ncbi_nuc_references_json"])
    assert refs[0]["pubmed_id"] == "9751715"
    assert refs[0]["title"]


def test_s1_stage_guard_and_provenance_fields(tmp_path: Path) -> None:
    path = tmp_path / "schema.gb"
    _write_genbank(path, locus="LOCS", accession="ACCS", sequence=SYNTHETIC_LOWER)
    result = extract_ncbi_nuc(
        [_input(path, "data/raw/NCBI_nucleotide/schema.gb")],
        source_dataset="ncbi_nuc_genbank_2026-07-27",
        redistribution_status="unknown",
        expected_records=1,
    )
    row = result.canonical_rows[0]
    assert list(row.keys()) == list(CORPUS_COLUMNS)
    assert row["source_db"] == SOURCE_DB
    assert row["source_dataset"] == "ncbi_nuc_genbank_2026-07-27"
    assert row["contributing_sources"] == SOURCE_DB
    assert row["contributing_datasets"] == "ncbi_nuc_genbank_2026-07-27"
    assert row["corroboration_count"] == "1"
    assert row["redistribution_status"] == "unknown"
    assert row["independently_attested_by_permissive_source"] == "false"
    assert row["molecule_type"] == ""
    assert row["chemistry"] == ""
    assert row["sequence_full"] == ""
    assert row["sequence_core"] == ""
    assert row["t_to_u_applied"] == ""
    assert row["alphabet_as_reported"] == ""
    assert row["binding_evidence_score"] == ""
    assert row["partition"] == ""


def test_deterministic_rerun(tmp_path: Path) -> None:
    path = tmp_path / "det.gb"
    _write_genbank(path, locus="LOCD", accession="ACCD", sequence=SYNTHETIC_LOWER)
    args = dict(
        inputs=[_input(path, "data/raw/NCBI_nucleotide/det.gb")],
        source_dataset="ncbi_nuc_demo",
        redistribution_status="unknown",
        expected_records=1,
    )
    first = extract_ncbi_nuc(**args)
    second = extract_ncbi_nuc(**args)
    write_sidecar_csv_atomic(path=tmp_path / "a.csv", rows=first.sidecar_rows)
    write_sidecar_csv_atomic(path=tmp_path / "b.csv", rows=second.sidecar_rows)
    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()
    assert first.canonical_rows == second.canonical_rows
    assert first.sidecar_rows == second.sidecar_rows


def test_s1_runner_multi_file_and_report_is_sequence_safe(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    first = repo / "data" / "raw" / "NCBI_nucleotide" / "z_first.gb"
    second = repo / "data" / "raw" / "NCBI_nucleotide" / "a_second.gb"
    _write_genbank(first, locus="LOCZ", accession="ACCZ", sequence=SYNTHETIC_LOWER)
    _write_genbank(
        second,
        locus="LOCY",
        accession="ACCY",
        sequence=SYNTHETIC_N,
        pubmed="11111111",
    )
    spec_rows = []
    for relative, path in (
        ("data/raw/NCBI_nucleotide/z_first.gb", first),
        ("data/raw/NCBI_nucleotide/a_second.gb", second),
    ):
        spec_rows.append(
            {
                "source_key": "ncbi_nuc",
                "source_dataset": "ncbi_nuc_demo",
                "path": relative,
                "sha256": _hash_path(path),
                "n_rows_expected": "1",
                "snapshot_date": "2026-07-27",
                "tier": "1",
                "redistribution_status": "unknown",
                "notes": (
                    "snapshot_date is a local download-date proxy, not an "
                    "NCBI database release date."
                ),
            }
        )
    spec = repo / "config" / "source_registry.csv"
    _write_csv(spec, list(REQUIRED_COLUMNS), spec_rows)
    result = run_s1_extraction(
        repo_root=repo,
        source_key="ncbi_nuc",
        registry_spec=spec,
        output_dir=repo / "data" / "interim" / "extracted",
        check_deterministic_rerun=True,
    )
    assert result.deterministic_rerun_ok is True
    canonical = list(
        csv.DictReader(result.output_canonical.open(encoding="utf-8", newline=""))
    )
    sidecar = list(
        csv.DictReader(result.output_sidecar.open(encoding="utf-8", newline=""))
    )
    assert list(canonical[0].keys()) == list(CORPUS_COLUMNS)
    assert list(sidecar[0].keys()) == list(SIDECAR_COLUMNS)
    assert [row["native_id"] for row in canonical] == ["ACCZ", "ACCY"]
    report = result.output_report.read_text(encoding="utf-8")
    assert SYNTHETIC_LOWER not in report
    assert SYNTHETIC_N not in report
    assert str(repo.resolve()) not in report
    assert "NO NCBI↔ENA DEDUPLICATION" in report
    assert result.stats.nonempty_pmid == 1

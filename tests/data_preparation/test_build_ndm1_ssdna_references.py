"""Tests for the NDM-1 ssDNA published-reference verification builder.

Every literal nucleotide string in this file is shorter than 20 nt.
Live guards read ignored PDFs/CSVs only to compare hashes, lengths, and flags.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.ndm1_ssdna_references import (  # noqa: E402
    Ndm1SsdnaError,
    canonicalise_ssdna_sequence,
    exact_sequence_duplicates,
    find_tracked_sequence_leaks,
    include_in_final_reference_set,
    join_display_groups,
    nucleotide_sequence_id,
    run_ndm1_ssdna_build,
    sha256_text,
    split_modification_prefix,
)
import adapters.ndm1_ssdna_references as ndm1_mod  # noqa: E402
from adapters.s5_validate_exact_dedup import (  # noqa: E402
    scan_paths_for_sequence_leak,
    scan_text_for_sequence_leak,
)
from adapters.target_extraction_common import SEQ_LEAK_RE  # noqa: E402
from s0_build_registry import sha256_file  # noqa: E402

SEQ_A = "ACGTACGTAA"
SEQ_B = "CGTACGTACG"
SEQ_C = "GTACGTACGA"
SEQ_D = "TACGTACGAC"
SEQ_E = "ACGTACGACT"
SEQ_F = "CGTACGACTG"
SEQ_G = "GTACGACTGA"
assert all(len(seq) < 20 for seq in (SEQ_A, SEQ_B, SEQ_C, SEQ_D, SEQ_E, SEQ_F, SEQ_G))

PROTECTED = [
    "Consent to Act as Corresponding Author.pdf",
    "docs/dataset_search_curation_inventory_log_entry.md",
    "docs/fine-tuning-implementation-plan.md",
]
TRACKED_NEW = [
    REPO_ROOT / "config/ndm1_ssdna_reference_build.json",
    REPO_ROOT / "scripts/data_preparation/adapters/ndm1_ssdna_references.py",
    REPO_ROOT / "scripts/data_preparation/build_ndm1_ssdna_references.py",
    REPO_ROOT / "tests/data_preparation/test_build_ndm1_ssdna_references.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _partition_row(seq: str, record_id: str) -> dict[str, str]:
    return {
        "scientific_identity_id": f"S5I_{record_id}",
        "record_id": record_id,
        "sequence_full": seq,
        "sequence_core": seq,
    }


def _synthetic_extract() -> dict[str, str]:
    return {
        "NDM1-H14.2_43": SEQ_A,
        "NDM1-H14-01": SEQ_B,
        "NDM1-H14-01-FR": SEQ_C,
        "Bio-NDM1-H14.2_43": SEQ_A,
        "Cy5-NDM1-H14.2_43": SEQ_A,
        "Bio-NDM1-H14-01": SEQ_B,
        "Cy5-NDM1-H14-01": SEQ_B,
        "Bio-NDM1-H14-01-FR": SEQ_C,
        "Cy5-Con1": SEQ_F,
        "Bio-ConSc": SEQ_G,
    }


def _write_manual_evidence(
    path: Path, *, apnv: str, cn102: str, flank5: str, flank3: str
) -> str:
    rows = [
        {
            "evidence_id": "ev_cn102_listing",
            "reference_id": "cn102965377b_seq1",
            "evidence_type": "image_only_sequence_listing",
            "primary_source_file": "dummy_cn102.pdf",
            "source_locator": "synthetic sequence listing",
            "transcription_method": "synthetic_fixture",
            "orientation_evidence": "synthetic 5-prime-to-3-prime listing",
            "sequence_length": str(len(cn102)),
            "sequence_sha256": sha256_text(cn102),
            "sequence": cn102,
        },
        {
            "evidence_id": "ev_cn102_5p",
            "reference_id": "cn102965377b_seq1",
            "evidence_type": "library_fixed_5p_flank",
            "primary_source_file": "dummy_cn102.pdf",
            "source_locator": "synthetic 5-prime flank",
            "transcription_method": "synthetic_fixture",
            "orientation_evidence": "synthetic library architecture 5-prime",
            "sequence_length": str(len(flank5)),
            "sequence_sha256": sha256_text(flank5),
            "sequence": flank5,
        },
        {
            "evidence_id": "ev_cn102_3p",
            "reference_id": "cn102965377b_seq1",
            "evidence_type": "library_fixed_3p_flank",
            "primary_source_file": "dummy_cn102.pdf",
            "source_locator": "synthetic 3-prime flank",
            "transcription_method": "synthetic_fixture",
            "orientation_evidence": "synthetic library architecture 3-prime",
            "sequence_length": str(len(flank3)),
            "sequence_sha256": sha256_text(flank3),
            "sequence": flank3,
        },
        {
            "evidence_id": "ev_apnv_fallback",
            "reference_id": "cn108949766b_apnv",
            "evidence_type": "fallback_seq_id_no_1_transcription",
            "primary_source_file": "dummy_cn108.pdf",
            "source_locator": "synthetic paragraph 0040",
            "transcription_method": "synthetic_fixture",
            "orientation_evidence": "synthetic 5-prime-to-3-prime listing",
            "sequence_length": str(len(apnv)),
            "sequence_sha256": sha256_text(apnv),
            "sequence": apnv,
        },
    ]
    _write_csv(
        path,
        [
            "evidence_id",
            "reference_id",
            "evidence_type",
            "primary_source_file",
            "source_locator",
            "transcription_method",
            "orientation_evidence",
            "sequence_length",
            "sequence_sha256",
            "sequence",
        ],
        rows,
    )
    return _sha(path)


def _synthetic_config(tmp_path: Path) -> dict:
    additions = tmp_path / "additions.csv"
    _write_csv(
        additions,
        ["reference_id", "sequence_raw"],
        [
            {"reference_id": "sabrowski2022_ndm1_h14_2_43", "sequence_raw": SEQ_A},
            {"reference_id": "sabrowski2022_ndm1_h14_01", "sequence_raw": SEQ_B},
            {"reference_id": "sabrowski2022_ndm1_h14_01_fr", "sequence_raw": SEQ_C},
            {"reference_id": "cn108949766b_apnv", "sequence_raw": SEQ_D},
            {"reference_id": "cn102965377b_seq1", "sequence_raw": SEQ_E},
        ],
    )
    for name in ("ft_train.csv", "ft_validation.csv", "ref.csv", "eval.csv"):
        _write_csv(
            tmp_path / "data/processed" / name,
            ["scientific_identity_id", "record_id", "sequence_full", "sequence_core"],
            [_partition_row("AUGCAUGC", name)],
        )
    eval_refs = tmp_path / "data/processed/evaluation_references.csv"
    eval_refs.parent.mkdir(parents=True, exist_ok=True)
    eval_refs.write_text("reference_id\nplaceholder\n", encoding="utf-8")
    (tmp_path / "data/processed/corpus_final.csv").write_text("x\n", encoding="utf-8")
    (tmp_path / "data/processed/corpus_final.txt").write_text("y\n", encoding="utf-8")
    dummy_pdfs = {
        "sabrowski_2022_main_article.pdf": tmp_path / "data/raw/evaluation_references/sabrowski_2022_main_article.pdf",
        "sabrowski_2022_supplementary.pdf": tmp_path
        / "data/raw/evaluation_references/source_documents/sabrowski_2022_supplementary.pdf",
        "CN108949766B_patent.pdf": tmp_path / "data/raw/evaluation_references/CN108949766B_patent.pdf",
        "CN102965377B_patent.pdf": tmp_path / "data/raw/evaluation_references/CN102965377B_patent.pdf",
    }
    for path in dummy_pdfs.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-DUMMY")
    evidence_path = (
        tmp_path / "data/interim/evaluation/ndm1_ssdna_manual_primary_source_evidence.csv"
    )
    evidence_sha = _write_manual_evidence(
        evidence_path,
        apnv=SEQ_D,
        cn102=SEQ_E,
        flank5=SEQ_E[:4],
        flank3="TTTT",
    )
    return {
        "contract_id": "synthetic",
        "identity_threshold": 0.9,
        "output_dir": "data/processed",
        "transcription_path": "data/interim/evaluation/ndm1_ssdna_primary_source_transcriptions.csv",
        "manual_primary_source_evidence_path": str(
            evidence_path.relative_to(tmp_path)
        ),
        "expected_manual_primary_source_evidence_sha256": evidence_sha,
        "additions_overrides_path": str(additions.relative_to(tmp_path)),
        "evaluation_references_path": "data/processed/evaluation_references.csv",
        "frozen_partitions": {
            "TRAIN": "data/processed/ft_train.csv",
            "VALIDATION": "data/processed/ft_validation.csv",
            "REF": "data/processed/ref.csv",
            "EVAL": "data/processed/eval.csv",
        },
        "frozen_corpus": {
            "corpus_final.csv": "data/processed/corpus_final.csv",
            "corpus_final.txt": "data/processed/corpus_final.txt",
        },
        "expected_frozen_sha256": {},
        "raw_evidence_immutable_hashes": {},
        "protected_untracked_files": [],
        "raw_sources": {
            "sabrowski_2022_main_article.pdf": {
                "path": "data/raw/evaluation_references/sabrowski_2022_main_article.pdf",
                "sha256": _sha(dummy_pdfs["sabrowski_2022_main_article.pdf"]),
            },
            "sabrowski_2022_supplementary.pdf": {
                "path": "data/raw/evaluation_references/source_documents/sabrowski_2022_supplementary.pdf",
                "sha256": _sha(dummy_pdfs["sabrowski_2022_supplementary.pdf"]),
            },
            "CN108949766B_patent.pdf": {
                "path": "data/raw/evaluation_references/CN108949766B_patent.pdf",
                "sha256": _sha(dummy_pdfs["CN108949766B_patent.pdf"]),
            },
            "CN102965377B_patent.pdf": {
                "path": "data/raw/evaluation_references/CN102965377B_patent.pdf",
                "sha256": _sha(dummy_pdfs["CN102965377B_patent.pdf"]),
            },
        },
        "expected_canonical_sequence_sha256": {
            "sabrowski2022_ndm1_h14_2_43": sha256_text(SEQ_A),
            "sabrowski2022_ndm1_h14_01": sha256_text(SEQ_B),
            "sabrowski2022_ndm1_h14_01_fr": sha256_text(SEQ_C),
            "cn108949766b_apnv": sha256_text(SEQ_D),
            "cn102965377b_seq1": sha256_text(SEQ_E),
            "sabrowski2022_con1": sha256_text(SEQ_F),
            "sabrowski2022_consc": sha256_text(SEQ_G),
        },
        "expected_sequence_lengths": {
            "sabrowski2022_ndm1_h14_2_43": len(SEQ_A),
            "sabrowski2022_ndm1_h14_01": len(SEQ_B),
            "sabrowski2022_ndm1_h14_01_fr": len(SEQ_C),
            "cn108949766b_apnv": len(SEQ_D),
            "cn102965377b_seq1": len(SEQ_E),
            "sabrowski2022_con1": len(SEQ_F),
            "sabrowski2022_consc": len(SEQ_G),
        },
        "cn102_library_architecture": {
            "fixed_5p_length": 4,
            "n_random": 2,
            "fixed_3p_length": 4,
            "stated_total_length": 6,
            "sequence_listing_length": len(SEQ_E),
        },
        "cn102_human_review": {
            "reference_role": "positive_ndm1_binder",
            "verification_status": "verified",
            "include_in_final_reference_set": True,
            "sequence_discrepancy": "source_internal_library_architecture_conflict",
            "human_review_resolution": (
                "explicit_sequence_listing_accepted_over_generic_library_architecture"
            ),
            "human_reviewer": "Laura",
            "human_review_resolution_date": "2026-09-22",
        },
    }


def _run_synthetic(tmp_path: Path, **kwargs):
    config = _synthetic_config(tmp_path)
    return run_ndm1_ssdna_build(
        config=config,
        repo_root=tmp_path,
        sabrowski_extract=_synthetic_extract(),
        **kwargs,
    )


def _apnv_rows(result: dict) -> tuple[dict[str, str], dict[str, str]]:
    reference = next(
        row
        for row in result["references"]
        if row["reference_id"] == "cn108949766b_apnv"
    )
    transcription = next(
        row
        for row in result["transcriptions"]
        if row["transcription_id"] == "tx_cn108949766b_apnv"
    )
    return reference, transcription


def test_dna_alphabet_validation() -> None:
    assert canonicalise_ssdna_sequence("acgt acgt") == "ACGTACGT"
    with pytest.raises(Ndm1SsdnaError):
        canonicalise_ssdna_sequence("ACGX")


def test_uppercase_whitespace_only_normalisation() -> None:
    assert canonicalise_ssdna_sequence("acg\ttac\n gta") == "ACGTACGTA"


def test_t_retained() -> None:
    assert "T" in canonicalise_ssdna_sequence("ACGT")
    assert "U" not in canonicalise_ssdna_sequence("ACGT")


def test_u_rejected_as_canonical_ssdna() -> None:
    with pytest.raises(Ndm1SsdnaError, match="contains U"):
        canonicalise_ssdna_sequence("ACGUAC")


def test_length_recalculated_from_canonical_sequence() -> None:
    seq = canonicalise_ssdna_sequence("ac gt ac")
    assert len(seq) == 6


def test_modification_tokens_never_enter_sequence() -> None:
    token, remainder = split_modification_prefix("/5BiotinTEG/ACGTAC")
    assert token == "/5BiotinTEG/"
    assert canonicalise_ssdna_sequence(remainder) == "ACGTAC"
    assert "BIOTIN" not in canonicalise_ssdna_sequence(remainder)


def test_verified_included_records_require_provenance(tmp_path: Path) -> None:
    result = _run_synthetic(tmp_path)
    included = [
        row
        for row in result["references"]
        if row["include_in_final_reference_set"] == "true"
    ]
    assert included
    for row in included:
        assert row["verification_status"] == "verified"
        assert row["source_file"]
        assert row["source_file_sha256"]
        assert row["source_location"]
        assert row["source_sequence_verification_method"]
        assert row["verified_against_primary_source"] == "true"


def test_apnv_reference_method_matches_manual_evidence_fallback(tmp_path: Path) -> None:
    result = _run_synthetic(tmp_path)
    reference, transcription = _apnv_rows(result)
    assert transcription["extraction_method"] == (
        "fallback_manual_primary_source_evidence_paragraph_0040"
    )
    assert (
        reference["source_sequence_verification_method"]
        == transcription["extraction_method"]
    )
    assert reference["verification_status"] == "verified"
    assert reference["include_in_final_reference_set"] == "true"
    assert reference["sequence_length"] == str(len(SEQ_D))
    assert transcription["sequence_length"] == str(len(SEQ_D))


def test_apnv_reference_method_follows_successful_pdf_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_method = "independent_pdf_text_extraction_paragraph_0040"

    def _fake_extract(path: Path, *, expected_length: int) -> tuple[str, str]:
        assert expected_length == len(SEQ_D)
        return SEQ_D, pdf_method

    monkeypatch.setattr(ndm1_mod, "extract_cn108_apnv_from_pdf", _fake_extract)
    result = _run_synthetic(tmp_path)
    reference, transcription = _apnv_rows(result)
    assert transcription["extraction_method"] == pdf_method
    assert (
        reference["source_sequence_verification_method"]
        == transcription["extraction_method"]
    )
    assert reference["verification_status"] == "verified"
    assert reference["include_in_final_reference_set"] == "true"


def test_needs_human_review_cannot_be_included() -> None:
    assert (
        include_in_final_reference_set(
            verification_status="needs_human_review",
            reference_role="positive_ndm1_binder_candidate",
        )
        is False
    )


def test_controls_cannot_be_included_as_positive_references() -> None:
    assert (
        include_in_final_reference_set(
            verification_status="excluded_control",
            reference_role="his_tag_binding_control",
        )
        is False
    )
    assert (
        include_in_final_reference_set(
            verification_status="verified",
            reference_role="his_tag_binding_control",
        )
        is False
    )


def test_exact_duplicate_detection() -> None:
    rows = [
        {"reference_id": "a", "sequence": SEQ_A},
        {"reference_id": "b", "sequence": SEQ_A},
        {"reference_id": "c", "sequence": SEQ_B},
    ]
    assert exact_sequence_duplicates(rows) == [["a", "b"]]


def test_same_nucleotide_different_chemistry_is_distinct(tmp_path: Path) -> None:
    result = _run_synthetic(tmp_path)
    h14 = [
        row
        for row in result["constructs"]
        if row["reference_id"] == "sabrowski2022_ndm1_h14_2_43"
    ]
    assert len(h14) == 3
    assert len({row["construct_id"] for row in h14}) == 3
    assert len({row["nucleotide_sequence_id"] for row in h14}) == 1
    assert {row["chemistry_label"] for row in h14} == {
        "unmodified",
        "5p_biotinteg",
        "5p_cy5",
    }


def test_h14_01_fr_parent_relationship(tmp_path: Path) -> None:
    result = _run_synthetic(tmp_path)
    child = next(
        row
        for row in result["references"]
        if row["reference_id"] == "sabrowski2022_ndm1_h14_01_fr"
    )
    assert child["parent_reference_id"] == "sabrowski2022_ndm1_h14_01"
    assert child["variant_relationship"] == "experimentally_tested_truncation"
    assert child["include_in_final_reference_set"] == "false"


def test_stable_deterministic_ids(tmp_path: Path) -> None:
    first = _run_synthetic(tmp_path / "a")
    second = _run_synthetic(tmp_path / "b")
    assert [row["reference_id"] for row in first["references"]] == [
        row["reference_id"] for row in second["references"]
    ]
    assert [row["nucleotide_sequence_id"] for row in first["references"]] == [
        row["nucleotide_sequence_id"] for row in second["references"]
    ]
    assert nucleotide_sequence_id(SEQ_A) == nucleotide_sequence_id(SEQ_A)


def test_deterministic_ordering(tmp_path: Path) -> None:
    result = _run_synthetic(tmp_path)
    ref_ids = [row["reference_id"] for row in result["references"]]
    assert ref_ids == sorted(ref_ids)
    construct_ids = [row["construct_id"] for row in result["constructs"]]
    assert construct_ids == sorted(construct_ids)
    measurement_ids = [row["measurement_id"] for row in result["measurements"]]
    assert measurement_ids == sorted(measurement_ids)


def test_required_uniqueness(tmp_path: Path) -> None:
    result = _run_synthetic(tmp_path)
    ref_ids = [row["reference_id"] for row in result["references"]]
    construct_ids = [row["construct_id"] for row in result["constructs"]]
    assert len(ref_ids) == len(set(ref_ids))
    assert len(construct_ids) == len(set(construct_ids))
    by_seq: dict[str, set[str]] = {}
    for row in result["references"]:
        by_seq.setdefault(row["sequence"], set()).add(row["nucleotide_sequence_id"])
    assert all(len(ids) == 1 for ids in by_seq.values())


def test_build_twice_byte_determinism(tmp_path: Path) -> None:
    first_dir = tmp_path / "one"
    second_dir = tmp_path / "two"
    _run_synthetic(first_dir)
    _run_synthetic(second_dir)
    names = [
        "ndm1_ssdna_aptamer_references.csv",
        "ndm1_ssdna_experimental_constructs.csv",
        "ndm1_ssdna_binding_measurements.csv",
        "ndm1_ssdna_reference_manifest.json",
        "ndm1_ssdna_reference_verification_report.md",
        "ndm1_ssdna_primary_source_transcriptions.csv",
    ]
    for name in names[:5]:
        left = first_dir / "data/processed" / name
        right = second_dir / "data/processed" / name
        assert left.read_bytes() == right.read_bytes(), name
    left_tx = first_dir / "data/interim/evaluation/ndm1_ssdna_primary_source_transcriptions.csv"
    right_tx = second_dir / "data/interim/evaluation/ndm1_ssdna_primary_source_transcriptions.csv"
    assert left_tx.read_bytes() == right_tx.read_bytes()


def test_join_display_groups_canonicalises_short_synthetic_tokens() -> None:
    assert join_display_groups([SEQ_A[:5], SEQ_A[5:]], context="synthetic") == SEQ_A


def test_scanner_detects_concatenated_short_nucleotide_arrays() -> None:
    text = json.dumps({"display_groups": [SEQ_A, SEQ_B]})
    leaks = find_tracked_sequence_leaks(
        text, source_kind="json", published_hashes=[], leak_length=20
    )
    assert leaks


def test_scanner_detects_sequence_bearing_keys() -> None:
    text = json.dumps({"fixed_5p": SEQ_A, "fixed_3p": SEQ_B, "flank": SEQ_C})
    leaks = find_tracked_sequence_leaks(
        text, source_kind="json", published_hashes=[], min_json_literal_length=8
    )
    assert leaks


def test_scanner_detects_nested_reconstruction() -> None:
    text = json.dumps({"library": {"fixed_3p_groups": [SEQ_A, SEQ_B]}})
    leaks = find_tracked_sequence_leaks(
        text, source_kind="json", published_hashes=[], leak_length=20
    )
    assert leaks


def test_scanner_detects_known_canonical_hash_if_reconstructed() -> None:
    reconstructed = SEQ_A + SEQ_B
    digest = sha256_text(reconstructed)
    text = json.dumps({"display_groups": [SEQ_A, SEQ_B]})
    leaks = find_tracked_sequence_leaks(
        text, source_kind="json", published_hashes=[digest], leak_length=20
    )
    assert any("published_canonical_hash_reconstructed" in item for item in leaks)


def test_sequence_free_report_and_tracked_files() -> None:
    config = json.loads(
        (REPO_ROOT / "config/ndm1_ssdna_reference_build.json").read_text(encoding="utf-8")
    )
    published = [
        config["expected_canonical_sequence_sha256"]["cn108949766b_apnv"],
        config["expected_canonical_sequence_sha256"]["cn102965377b_seq1"],
    ]
    paths = list(TRACKED_NEW)
    report = REPO_ROOT / "data/processed/ndm1_ssdna_reference_verification_report.md"
    manifest = REPO_ROOT / "data/processed/ndm1_ssdna_reference_manifest.json"
    if report.is_file():
        paths.append(report)
    if manifest.is_file():
        paths.append(manifest)
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert SEQ_LEAK_RE.search(text) is None, path
        assert scan_text_for_sequence_leak(text) is False
        kind = "json" if path.suffix == ".json" else "python"
        if path.suffix == ".md":
            kind = "text"
        leaks = find_tracked_sequence_leaks(
            text,
            source_kind=kind,
            published_hashes=published,
        )
        assert leaks == [], (path, leaks)


def test_cn102_resolution_included_and_manual_evidence_not_overwritten(
    tmp_path: Path,
) -> None:
    config = _synthetic_config(tmp_path)
    evidence = tmp_path / config["manual_primary_source_evidence_path"]
    before = evidence.read_bytes()
    result = run_ndm1_ssdna_build(
        config=config,
        repo_root=tmp_path,
        sabrowski_extract=_synthetic_extract(),
    )
    cn102 = next(
        row
        for row in result["references"]
        if row["reference_id"] == "cn102965377b_seq1"
    )
    assert cn102["verification_status"] == "verified"
    assert cn102["include_in_final_reference_set"] == "true"
    assert cn102["sequence_discrepancy"] == "source_internal_library_architecture_conflict"
    assert result["counts"]["included_verified_references"] == 3
    assert result["counts"]["needs_human_review"] == 0
    assert evidence.read_bytes() == before
    assert result["cn102_conflict"]["conflict"] is True


def test_manual_evidence_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    config = _synthetic_config(tmp_path)
    config["expected_manual_primary_source_evidence_sha256"] = "0" * 64
    with pytest.raises(Ndm1SsdnaError, match="manual-evidence"):
        run_ndm1_ssdna_build(
            config=config,
            repo_root=tmp_path,
            sabrowski_extract=_synthetic_extract(),
            write_outputs=False,
            run_leakage=False,
        )


def test_leakage_diagnostics_complete_for_four_partitions(tmp_path: Path) -> None:
    result = _run_synthetic(tmp_path)
    by_partition = result["leakage"]["by_partition"]
    assert set(by_partition) == {"TRAIN", "VALIDATION", "REF", "EVAL"}
    for part in by_partition.values():
        assert "exact_matches" in part
        assert "identity_ge_threshold" in part
        assert part["n_rows"] == 1


def test_git_ls_files_data_empty() -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "data"], cwd=REPO_ROOT, text=True
    ).strip()
    assert tracked == ""


def test_protected_untracked_files_present() -> None:
    for rel in PROTECTED:
        assert (REPO_ROOT / rel).is_file()


def _live_ready() -> bool:
    return (
        REPO_ROOT
        / "data/raw/evaluation_references/source_documents/sabrowski_2022_supplementary.pdf"
    ).is_file()


@pytest.mark.skipif(not _live_ready(), reason="primary NDM-1 PDFs are not present")
def test_live_source_transcription_matches_verified_records() -> None:
    config = json.loads(
        (REPO_ROOT / "config/ndm1_ssdna_reference_build.json").read_text(encoding="utf-8")
    )
    result = run_ndm1_ssdna_build(
        config=config,
        repo_root=REPO_ROOT,
        write_outputs=False,
        run_leakage=False,
    )
    tx = {
        row["reference_id"]: row
        for row in result["transcriptions"]
        if row["transcription_id"]
        in {
            "tx_sabrowski2022_ndm1_h14_2_43",
            "tx_sabrowski2022_ndm1_h14_01",
            "tx_sabrowski2022_ndm1_h14_01_fr",
            "tx_sabrowski2022_con1",
            "tx_sabrowski2022_consc",
            "tx_cn108949766b_apnv",
            "tx_cn102965377b_seq1",
        }
    }
    for row in result["references"]:
        if row["verification_status"] != "verified":
            continue
        assert tx[row["reference_id"]]["sequence_canonical"] == row["sequence"]
        assert "U" not in row["sequence"]
        assert row["sequence"] == row["sequence"].upper()
        assert int(row["sequence_length"]) == len(row["sequence"])
        assert row["include_in_final_reference_set"] == "true"
    assert result["counts"]["candidate_or_reference_records"] == 7
    assert result["counts"]["included_verified_references"] == 3
    assert result["counts"]["needs_human_review"] == 0
    assert result["counts"]["excluded_control"] == 4
    assert result["counts"]["distinct_canonical_nucleotide_sequences"] == 7
    assert result["counts"]["experimental_constructs"] == 14
    assert result["counts"]["binding_measurements"] == 16
    for row in result["references"]:
        tx_row = tx[row["reference_id"]]
        assert (
            row["source_sequence_verification_method"] == tx_row["extraction_method"]
        )
        assert int(row["sequence_length"]) == int(
            config["expected_sequence_lengths"][row["reference_id"]]
        )
        assert (
            row["sequence_sha256"]
            == config["expected_canonical_sequence_sha256"][row["reference_id"]]
        )
        assert row["source_file"]
        assert row["source_file_sha256"]
        assert row["source_location"]
    ref_ids = {row["reference_id"] for row in result["references"]}
    assert {row["reference_id"] for row in result["constructs"]} <= ref_ids
    construct_ids = {row["construct_id"] for row in result["constructs"]}
    assert {row["construct_id"] for row in result["measurements"]} <= construct_ids
    assert {row["reference_id"] for row in result["measurements"]} <= ref_ids
    cn102 = next(
        row for row in result["references"] if row["reference_id"] == "cn102965377b_seq1"
    )
    assert cn102["verification_status"] == "verified"
    assert cn102["include_in_final_reference_set"] == "true"
    assert cn102["sequence_discrepancy"] == "source_internal_library_architecture_conflict"
    assert (
        cn102["human_review_resolution"]
        == "explicit_sequence_listing_accepted_over_generic_library_architecture"
    )
    assert cn102["human_reviewer"] == "Laura"
    assert cn102["human_review_resolution_date"] == "2026-09-22"
    apnv_ref = next(
        row for row in result["references"] if row["reference_id"] == "cn108949766b_apnv"
    )
    apnv_tx = tx["cn108949766b_apnv"]
    assert apnv_tx["extraction_method"] == (
        "fallback_manual_primary_source_evidence_paragraph_0040"
    )
    assert (
        apnv_ref["source_sequence_verification_method"]
        == apnv_tx["extraction_method"]
    )
    candidate_tx = {
        "tx_sabrowski2022_ndm1_h14_2_43",
        "tx_sabrowski2022_ndm1_h14_01",
        "tx_sabrowski2022_ndm1_h14_01_fr",
        "tx_cn108949766b_apnv",
        "tx_cn102965377b_seq1",
    }
    assert all(
        row["matches_additions_sequence_raw"] == "true"
        for row in result["transcriptions"]
        if row["transcription_id"] in candidate_tx
    )
    assert result["additions_sequence_matches"] is True
    manifest_path = REPO_ROOT / "data/processed/ndm1_ssdna_reference_manifest.json"
    if manifest_path.is_file():
        leakage = json.loads(manifest_path.read_text(encoding="utf-8"))["leakage"]
        assert leakage["any_exact"] is False
        assert leakage["any_identity_ge_threshold"] is False
    leaked = scan_paths_for_sequence_leak(
        [
            REPO_ROOT / "data/processed/ndm1_ssdna_reference_verification_report.md",
            REPO_ROOT / "data/processed/ndm1_ssdna_reference_manifest.json",
        ]
    )
    assert leaked == []


@pytest.mark.skipif(not _live_ready(), reason="primary NDM-1 PDFs are not present")
def test_live_source_and_frozen_hashes_unchanged() -> None:
    config = json.loads(
        (REPO_ROOT / "config/ndm1_ssdna_reference_build.json").read_text(encoding="utf-8")
    )
    protected_before = {rel: _sha(REPO_ROOT / rel) for rel in PROTECTED}
    for rel, digest in config["raw_evidence_immutable_hashes"].items():
        assert sha256_file(REPO_ROOT / rel) == digest
    mapping = {
        "ft_train.csv": config["frozen_partitions"]["TRAIN"],
        "ft_validation.csv": config["frozen_partitions"]["VALIDATION"],
        "ref.csv": config["frozen_partitions"]["REF"],
        "eval.csv": config["frozen_partitions"]["EVAL"],
        "corpus_final.csv": config["frozen_corpus"]["corpus_final.csv"],
        "corpus_final.txt": config["frozen_corpus"]["corpus_final.txt"],
        "evaluation_references.csv": config["evaluation_references_path"],
    }
    for name, rel in mapping.items():
        assert sha256_file(REPO_ROOT / rel) == config["expected_frozen_sha256"][name], name
    for rel in PROTECTED:
        assert _sha(REPO_ROOT / rel) == protected_before[rel]
    assert scan_text_for_sequence_leak(
        (REPO_ROOT / "config/ndm1_ssdna_reference_build.json").read_text(encoding="utf-8")
    ) is False
    config_text = (REPO_ROOT / "config/ndm1_ssdna_reference_build.json").read_text(
        encoding="utf-8"
    )
    published = [
        config["expected_canonical_sequence_sha256"]["cn108949766b_apnv"],
        config["expected_canonical_sequence_sha256"]["cn102965377b_seq1"],
    ]
    assert (
        find_tracked_sequence_leaks(
            config_text, source_kind="json", published_hashes=published
        )
        == []
    )

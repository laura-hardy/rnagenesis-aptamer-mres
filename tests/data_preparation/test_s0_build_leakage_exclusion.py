"""Tests for S0b evaluation-reference / leakage-exclusion build."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from s0_build_leakage_exclusion import (  # noqa: E402
    ADDITIONS_COLUMNS,
    LEAKAGE_COLUMNS,
    LeakageBuildError,
    build_leakage_exclusion,
    main,
    parse_additions_overrides,
    parse_chen_xk10,
    parse_d9,
    parse_precision_selex,
    parse_shi_with_override,
)
from s0_build_registry import REQUIRED_COLUMNS  # noqa: E402

SEQ_LEAK_RE = re.compile(r"[ACGTU]{20,}", re.I)


def _hash_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_utf8_sig_csv(
    path: Path, fieldnames: list[str], rows: list[dict[str, str]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_minimal_xlsx(path: Path, rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    shared: list[str] = []

    def share(text: str) -> int:
        shared.append(text)
        return len(shared) - 1

    sheet = Element(
        "worksheet",
        {"xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"},
    )
    sheet_data = SubElement(sheet, "sheetData")
    for r_idx, row_vals in enumerate(rows, start=1):
        row_el = SubElement(sheet_data, "row", {"r": str(r_idx)})
        for c_idx, value in enumerate(row_vals):
            if value is None or value == "":
                continue
            col = chr(ord("A") + c_idx)
            cell_ref = f"{col}{r_idx}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                c_el = SubElement(row_el, "c", {"r": cell_ref})
                v_el = SubElement(c_el, "v")
                v_el.text = str(value)
            else:
                idx = share(str(value))
                c_el = SubElement(row_el, "c", {"r": cell_ref, "t": "s"})
                v_el = SubElement(c_el, "v")
                v_el.text = str(idx)

    ss_root = Element(
        "sst",
        {
            "xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "count": str(len(shared)),
            "uniqueCount": str(len(shared)),
        },
    )
    for text in shared:
        si = SubElement(ss_root, "si")
        t = SubElement(si, "t")
        t.text = text

    wb = Element(
        "workbook",
        {"xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"},
    )
    wb.set(
        "xmlns:r",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    )
    sheets = SubElement(wb, "sheets")
    SubElement(
        sheets,
        "sheet",
        {
            "name": "Sheet1",
            "sheetId": "1",
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id": "rId1",
        },
    )
    rels = Element(
        "Relationships",
        {"xmlns": "http://schemas.openxmlformats.org/package/2006/relationships"},
    )
    SubElement(
        rels,
        "Relationship",
        {
            "Id": "rId1",
            "Type": (
                "http://schemas.openxmlformats.org/officeDocument/2006/"
                "relationships/officeDocument"
            ),
            "Target": "xl/workbook.xml",
        },
    )
    wb_rels = Element(
        "Relationships",
        {"xmlns": "http://schemas.openxmlformats.org/package/2006/relationships"},
    )
    SubElement(
        wb_rels,
        "Relationship",
        {
            "Id": "rId1",
            "Type": (
                "http://schemas.openxmlformats.org/officeDocument/2006/"
                "relationships/worksheet"
            ),
            "Target": "worksheets/sheet1.xml",
        },
    )
    content_types = Element(
        "Types",
        {"xmlns": "http://schemas.openxmlformats.org/package/2006/content-types"},
    )
    SubElement(
        content_types,
        "Default",
        {
            "Extension": "rels",
            "ContentType": "application/vnd.openxmlformats-package.relationships+xml",
        },
    )
    SubElement(
        content_types,
        "Default",
        {"Extension": "xml", "ContentType": "application/xml"},
    )
    SubElement(
        content_types,
        "Override",
        {
            "PartName": "/xl/workbook.xml",
            "ContentType": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet.main+xml"
            ),
        },
    )
    SubElement(
        content_types,
        "Override",
        {
            "PartName": "/xl/worksheets/sheet1.xml",
            "ContentType": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.worksheet+xml"
            ),
        },
    )
    SubElement(
        content_types,
        "Override",
        {
            "PartName": "/xl/sharedStrings.xml",
            "ContentType": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sharedStrings+xml"
            ),
        },
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", tostring(content_types))
        zf.writestr("_rels/.rels", tostring(rels))
        zf.writestr("xl/workbook.xml", tostring(wb))
        zf.writestr("xl/_rels/workbook.xml.rels", tostring(wb_rels))
        zf.writestr("xl/sharedStrings.xml", tostring(ss_root))
        zf.writestr("xl/worksheets/sheet1.xml", tostring(sheet))


def _aliases_rows() -> list[dict[str, str]]:
    return [
        {
            "canonical_target": "NDM-1",
            "alias": "NDM-1",
            "match_type": "exact_alias",
            "target_family": "carbapenemase",
            "exclusion_reason": "evaluation_reference_target",
            "notes": "test",
        },
        {
            "canonical_target": "KPC-2",
            "alias": "KPC-2",
            "match_type": "exact_alias",
            "target_family": "carbapenemase",
            "exclusion_reason": "evaluation_reference_target",
            "notes": "test",
        },
        {
            "canonical_target": "HSA",
            "alias": "HSA",
            "match_type": "exact_alias",
            "target_family": "serum_protein",
            "exclusion_reason": "evaluation_counterselection_or_control",
            "notes": "test",
        },
        {
            "canonical_target": "carbapenemase",
            "alias": "carbapenemase",
            "match_type": "family_pattern",
            "target_family": "carbapenemase",
            "exclusion_reason": "target_family_exclusion",
            "notes": "test",
        },
    ]


def _d9_rows() -> list[dict[str, str]]:
    # Synthetic short sequences (<20 nt) with documented lengths for unit tests
    # are impractical for the full D9 length gates; dedicated parse_d9 tests use
    # length-accurate short fixtures only when calling lower-level helpers.
    # Full builder fixtures below use short sequences and patch length gates via
    # a reduced synthetic pipeline.
    return [
        {
            "clone_id": "D902",
            "sequence_reported": "ACGTACGTAC",
            "sequence_cleaned": "ACGTACGTAC",
            "purine_percent_reported": "50%",
            "gc_percent_reported": "50%",
        }
    ]


def _make_precision_xlsx(path: Path, n: int = 20) -> None:
    rows: list[list[object]] = [
        ["Aptamer-ID", "Sequences of N40", "dG", "Truncated sequences"],
    ]
    for i in range(1, n + 1):
        core = ("ACGT" * 3)[:12]  # 12 nt synthetic core
        full = (("GCTA" * 4)[:16])  # 16 nt synthetic full
        rows.append([f"XK-{i}", core, -1.0, full])
        rows.append([None, None, None, None])
    _write_minimal_xlsx(path, rows)


def _chen_rows() -> list[dict[str, str]]:
    xk = "ACGTACGTACGT"  # 12 nt
    return [
        {
            "record_id": "chen2020_fam_xk10",
            "aptamer_id": "FAM-XK10",
            "sequence_type": "aptamer",
            "target_name": "KPC-2-expressing Escherichia coli",
            "target_short": "KPC-2",
            "target_type": "protein",
            "selection_or_role": "XK10",
            "reported_sequence_5to3": xk,
            "modification_5prime": "FAM",
            "modification_3prime": "",
            "spacer_5prime": "",
            "spacer_5prime_length_nt": "0",
            "sequence_5to3_mods_removed": xk,
            "core_aptamer_sequence_5to3": xk,
            "core_aptamer_length_nt": "12",
            "construct_length_nt_mods_removed": "12",
            "binding_or_assay_notes": "binder",
            "is_target_binding_aptamer": "yes",
            "is_negative_control": "no",
            "source_paper": "Chen 2020",
            "source_doi": "10.0.0.0",
            "source_location": "Table 1",
            "curation_notes": "positive XK10",
        },
        {
            "record_id": "chen2020_fam_sgc",
            "aptamer_id": "FAM-Sgc",
            "sequence_type": "control",
            "target_name": "negative control",
            "target_short": "Sgc",
            "target_type": "control",
            "selection_or_role": "control",
            "reported_sequence_5to3": "TTTTACGTACGT",
            "modification_5prime": "FAM",
            "modification_3prime": "",
            "spacer_5prime": "",
            "spacer_5prime_length_nt": "0",
            "sequence_5to3_mods_removed": "TTTTACGTACGT",
            "core_aptamer_sequence_5to3": "TTTTACGTACGT",
            "core_aptamer_length_nt": "12",
            "construct_length_nt_mods_removed": "12",
            "binding_or_assay_notes": "neg",
            "is_target_binding_aptamer": "no",
            "is_negative_control": "yes",
            "source_paper": "Chen 2020",
            "source_doi": "10.0.0.0",
            "source_location": "Table 1",
            "curation_notes": "negative control must not be ingested",
        },
    ]


def _shi_rows(*, seq: str = "ACGTACGTACGT") -> list[dict[str, str]]:
    return [
        {
            "record_id": "shi2025_kpc2_kp_aptamer",
            "target_label": "KPC-2 KP",
            "target_description": "KPC-2-expressing Klebsiella pneumoniae",
            "target_type": "bacterium",
            "sequence_5to3_fam_removed": seq,
            "length_nt": str(len(seq)),
            "reported_sequence_context": "synthetic",
            "reported_modification": "5'-FAM",
            "sequence_alphabet": "DNA",
            "source_paper": "Shi 2025",
            "source_doi": "10.0.0.0",
            "source_location": "Supporting Information Table S1",
            "source_ref_number": "1",
            "source_reference_cited_in_si": "Chen et al. 2020",
            "curation_notes": "referenced from Chen",
        }
    ]


def _addition(
    *,
    reference_id: str,
    record_type: str = "sequence",
    action: str = "add",
    sequence_raw: str = "",
    status: str = "resolved",
    include_in_sequence_leakage: str = "true",
    aptamer_name: str = "",
    target_name_raw: str = "NDM-1",
    molecule_type: str = "ssDNA",
    alphabet_as_reported: str = "DNA",
    evaluation_role: str = "positive_control_ndm1_binder",
    reported_length: str = "",
    source_key: str = "test_source",
    supersedes_record_id: str = "",
    notes: str = "",
) -> dict[str, str]:
    return {
        "reference_id": reference_id,
        "record_type": record_type,
        "action": action,
        "source_key": source_key,
        "publication": "Test publication",
        "target_name_raw": target_name_raw,
        "aptamer_name": aptamer_name,
        "sequence_raw": sequence_raw,
        "molecule_type": molecule_type,
        "alphabet_as_reported": alphabet_as_reported,
        "sequence_scope": "full",
        "reported_length": reported_length or str(len(sequence_raw)),
        "binding_metric": "",
        "selection_method": "",
        "selection_rounds": "",
        "source_location": "test table",
        "evaluation_role": evaluation_role,
        "status": status,
        "include_in_sequence_leakage": include_in_sequence_leakage,
        "supersedes_record_id": supersedes_record_id,
        "notes": notes,
    }


def test_parse_additions_duplicate_reference_ids_rejected(tmp_path: Path) -> None:
    path = tmp_path / "additions.csv"
    row = _addition(
        reference_id="dup",
        sequence_raw="ACGTACGTAC",
        aptamer_name="A1",
    )
    _write_utf8_sig_csv(path, list(ADDITIONS_COLUMNS), [row, dict(row)])
    with pytest.raises(LeakageBuildError, match="Duplicate reference_id"):
        parse_additions_overrides(path)


def test_pending_and_dataset_routing(tmp_path: Path) -> None:
    path = tmp_path / "additions.csv"
    rows = [
        _addition(
            reference_id="pending_one",
            sequence_raw="",
            status="pending_sequence_extraction",
            aptamer_name="H14.2_43",
            evaluation_role="positive_control_ndm1_binder",
        ),
        _addition(
            reference_id="prjna_test",
            record_type="dataset",
            sequence_raw="",
            include_in_sequence_leakage="false",
            aptamer_name="",
            evaluation_role="dataset",
        ),
        _addition(
            reference_id="apnv_test",
            sequence_raw="A" * 35,
            aptamer_name="APNV",
            evaluation_role="positive_control_ndm1_vim2_cross_binder",
            target_name_raw="NDM-1 and VIM-2",
            reported_length="35",
        ),
    ]
    _write_utf8_sig_csv(path, list(ADDITIONS_COLUMNS), rows)
    parsed, by_id = parse_additions_overrides(path)
    assert len(parsed) == 3
    assert by_id["pending_one"]["status"] == "pending_sequence_extraction"
    assert by_id["prjna_test"]["record_type"] == "dataset"


def test_shi_override_defeats_unsupported_assignment(tmp_path: Path) -> None:
    shi = tmp_path / "shi.csv"
    _write_utf8_sig_csv(
        shi,
        list(_shi_rows(seq="GGGGCCCCAAAA")[0].keys()),
        _shi_rows(seq="GGGGCCCCAAAA"),
    )
    override = _addition(
        reference_id="shi2025_kpc2kp",
        action="override",
        sequence_raw="",
        status="pending_sequence_extraction",
        aptamer_name="KPC-2 KP aptamer / XK10",
        target_name_raw="KPC-2 KP",
        evaluation_role="duplicate_provenance_xk10_bacterial_detection",
        notes="override pending without SI",
    )
    refs, pending, notes = parse_shi_with_override(
        shi, override, source_key="shi_csv", si_present=False
    )
    assert refs == []
    assert len(pending) == 1
    assert pending[0].reference_id == "shi2025_kpc2kp"
    assert notes


def test_chen_xk10_only_positive_ingested(tmp_path: Path) -> None:
    path = tmp_path / "chen.csv"
    rows = _chen_rows()
    _write_utf8_sig_csv(path, list(rows[0].keys()), rows)
    # Bypass hard 61-nt gate by monkeypatching assert inside parse via short seq:
    # parse_chen_xk10 hard-fails on length 61; use a local monkeypatch.
    import s0_build_leakage_exclusion as mod

    original = mod._assert_length

    def _soft_assert(name: str, sequence: str, expected: int) -> None:
        if name == "Chen XK10":
            return
        original(name, sequence, expected)

    mod._assert_length = _soft_assert  # type: ignore[assignment]
    try:
        refs = parse_chen_xk10(path, source_key="chen_csv")
    finally:
        mod._assert_length = original  # type: ignore[assignment]
    assert len(refs) == 1
    assert refs[0].aptamer_name == "XK10"
    assert refs[0].action == "duplicate_provenance"


def test_precision_produces_20_logical_records(tmp_path: Path) -> None:
    path = tmp_path / "precision.xlsx"
    _make_precision_xlsx(path, n=20)
    refs = parse_precision_selex(path, source_key="precision")
    assert len(refs) == 20
    assert [r.aptamer_name for r in refs] == [f"XK-{i}" for i in range(1, 21)]
    assert all(r.sequence_full != r.sequence_core for r in refs)
    assert all(r.t_to_u_applied is False for r in refs)


def test_d9_seven_clones_and_whitespace_derivation(tmp_path: Path) -> None:
    import s0_build_leakage_exclusion as mod

    path = tmp_path / "d9.csv"
    # Use documented lengths with short synthetic sequences by temporarily
    # patching documented length map for the unit test.
    short = {
        "D902": "ACGTACGTAC",  # 10
        "D907": "ACGTACGT",  # 8 with trailing gaps in reported
        "D909": "ACGTACGTAA",  # 10
        "D913": "ACG TAC GTA C",  # whitespace-normalised → 10
        "D914": "ACGTACGTAG",
        "D918": "ACGTACGTA",  # 9
        "D920": "ACGTACGTAT",
    }
    original_lengths = dict(mod.D9_DOCUMENTED_LENGTHS)
    mod.D9_DOCUMENTED_LENGTHS.update({k: len(v.replace(" ", "")) for k, v in short.items()})
    rows = []
    for clone, seq in short.items():
        reported = seq if clone != "D907" else seq + "----"
        rows.append(
            {
                "clone_id": clone,
                "sequence_reported": reported,
                "sequence_cleaned": "WRONGLENGTH",
                "purine_percent_reported": "50%",
                "gc_percent_reported": "50%",
            }
        )
    _write_utf8_sig_csv(
        path,
        [
            "clone_id",
            "sequence_reported",
            "sequence_cleaned",
            "purine_percent_reported",
            "gc_percent_reported",
        ],
        rows,
    )
    try:
        refs = parse_d9(path, source_key="d9", source_sha="abc")
    finally:
        mod.D9_DOCUMENTED_LENGTHS.clear()
        mod.D9_DOCUMENTED_LENGTHS.update(original_lengths)
    assert len(refs) == 7
    assert [r.aptamer_name for r in refs] == list(mod.EXPECTED_D9_IDS)
    d913 = next(r for r in refs if r.aptamer_name == "D913")
    assert d913.sequence_full == "ACGUACGUAC"
    assert d913.t_to_u_applied is True
    assert d913.molecule_type == "RNA"
    assert d913.alphabet_as_reported == "DNA_T"
    d907 = next(r for r in refs if r.aptamer_name == "D907")
    assert len(d907.sequence_full) == 8


def test_full_builder_provenance_merge_pending_dataset_deterministic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end synthetic build covering merge, pending, dataset, IO safety."""
    import s0_build_leakage_exclusion as mod

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "docs" / "data_curation").mkdir(parents=True)
    (repo / "scripts" / "data_preparation").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    raw = repo / "data" / "raw"
    raw.mkdir(parents=True)
    (raw / "selektion_paper").mkdir()
    (raw / "precision_selex_against_kpc2_paper").mkdir()
    (raw / "chen_et_al_kpc").mkdir()
    (raw / "shi_et_al_paper").mkdir()
    (raw / "evaluation_references" / "source_documents").mkdir(parents=True)

    # Patch D9 lengths for short synthetic sequences.
    short_d9 = {
        "D902": "ACGTACGTAC",
        "D907": "ACGTACGT",
        "D909": "ACGTACGTAA",
        "D913": "TGCATGCATG",
        "D914": "ACGTACGTAG",
        "D918": "ACGTACGTA",
        "D920": "ACGTACGTAT",
    }
    original_lengths = dict(mod.D9_DOCUMENTED_LENGTHS)
    mod.D9_DOCUMENTED_LENGTHS.update({k: len(v) for k, v in short_d9.items()})

    d9_path = raw / "selektion_paper" / "table6_d9_ndm1_sequences.csv"
    _write_utf8_sig_csv(
        d9_path,
        [
            "clone_id",
            "sequence_reported",
            "sequence_cleaned",
            "purine_percent_reported",
            "gc_percent_reported",
        ],
        [
            {
                "clone_id": c,
                "sequence_reported": s,
                "sequence_cleaned": s,
                "purine_percent_reported": "50%",
                "gc_percent_reported": "50%",
            }
            for c, s in short_d9.items()
        ],
    )

    precision_path = raw / "precision_selex_against_kpc2_paper" / "extracted_data.xlsx"
    _make_precision_xlsx(precision_path, n=20)

    chen_path = raw / "chen_et_al_kpc" / "chen2020_kpc2_ecoli_xk10_aptamer_sequences.csv"
    # Match XK-10 full construct from precision fixture for merge.
    xk_full = ("GCTA" * 4)[:16]
    xk_core = ("ACGT" * 3)[:12]
    chen_rows = _chen_rows()
    chen_rows[0]["core_aptamer_sequence_5to3"] = xk_full
    chen_rows[0]["sequence_5to3_mods_removed"] = xk_full
    chen_rows[0]["core_aptamer_length_nt"] = str(len(xk_full))
    _write_utf8_sig_csv(chen_path, list(chen_rows[0].keys()), chen_rows)

    shi_path = raw / "shi_et_al_paper" / "shi2025_kpc2kp_mdrab_aptamer_sequences.csv"
    # Unsupported distinct sequence without SI → pending override path.
    _write_utf8_sig_csv(
        shi_path,
        list(_shi_rows(seq="TTTTTTTTTTTT")[0].keys()),
        _shi_rows(seq="TTTTTTTTTTTT"),
    )

    additions_path = (
        raw
        / "evaluation_references"
        / "carbapenemase_reference_additions_and_overrides.csv"
    )
    apnv = "A" * 35
    h14 = "A" * 80
    h14fr = "C" * 44
    patent = "G" * 88
    additions = [
        _addition(
            reference_id="sabrowski2022_ndm1_h14_2_43",
            sequence_raw="",
            status="pending_sequence_extraction",
            aptamer_name="NDM1-H14.2_43",
            evaluation_role="positive_control_ndm1_binder",
            notes="pending SI",
        ),
        _addition(
            reference_id="sabrowski2022_ndm1_h14_01",
            sequence_raw=h14,
            aptamer_name="NDM1-H14-01",
            evaluation_role="negative_control_his_tag_binder",
            target_name_raw="Polyhistidine tag / HIS-tag",
        ),
        _addition(
            reference_id="sabrowski2022_ndm1_h14_01_fr",
            sequence_raw=h14fr,
            aptamer_name="NDM1-H14-01-FR",
            evaluation_role="methodological_masking_control",
            target_name_raw="Polyhistidine tag",
        ),
        _addition(
            reference_id="cn108949766b_apnv",
            sequence_raw=apnv,
            aptamer_name="APNV",
            evaluation_role="positive_control_ndm1_vim2_cross_binder",
            target_name_raw="NDM-1 and VIM-2",
            reported_length="35",
        ),
        _addition(
            reference_id="cn102965377b_seq1",
            sequence_raw=patent,
            aptamer_name="SEQ ID NO:1",
            evaluation_role="positive_control_ndm1_binder",
            reported_length="88",
        ),
        _addition(
            reference_id="shi2025_kpc2kp",
            action="override",
            sequence_raw="",
            status="pending_sequence_extraction",
            aptamer_name="KPC-2 KP aptamer",
            target_name_raw="KPC-2 KP",
            evaluation_role="duplicate_provenance_xk10_bacterial_detection",
        ),
        _addition(
            reference_id="chen2020_xk10",
            action="duplicate_provenance",
            sequence_raw=xk_full,
            aptamer_name="XK10",
            target_name_raw="KPC-2",
            evaluation_role="duplicate_provenance_xk10",
            supersedes_record_id="yu2021_xk10",
            source_key="chen_2020_table_1",
        ),
        _addition(
            reference_id="prjna830749",
            record_type="dataset",
            sequence_raw="",
            include_in_sequence_leakage="false",
            aptamer_name="",
            evaluation_role="target_specific_round_level_reference_dataset",
        ),
    ]
    _write_utf8_sig_csv(additions_path, list(ADDITIONS_COLUMNS), additions)

    aliases_path = repo / "config" / "leakage_target_aliases.csv"
    _write_csv(
        aliases_path,
        [
            "canonical_target",
            "alias",
            "match_type",
            "target_family",
            "exclusion_reason",
            "notes",
        ],
        _aliases_rows(),
    )

    # Registry with actual hashes; relax Chen 61-nt assert.
    original_assert = mod._assert_length

    def _soft_assert(name: str, sequence: str, expected: int) -> None:
        if name == "Chen XK10":
            return
        original_assert(name, sequence, expected)

    mod._assert_length = _soft_assert  # type: ignore[assignment]

    registry_rows = []
    files = [
        (
            "von_laer_2013_d9_table6",
            "d9",
            "data/raw/selektion_paper/table6_d9_ndm1_sequences.csv",
            d9_path,
            7,
        ),
        (
            "yu_2021_precision_selex_xlsx",
            "precision",
            "data/raw/precision_selex_against_kpc2_paper/extracted_data.xlsx",
            precision_path,
            40,
        ),
        (
            "chen_2020_xk10_csv",
            "chen",
            "data/raw/chen_et_al_kpc/chen2020_kpc2_ecoli_xk10_aptamer_sequences.csv",
            chen_path,
            2,
        ),
        (
            "shi_2025_kpc2kp_csv",
            "shi",
            "data/raw/shi_et_al_paper/shi2025_kpc2kp_mdrab_aptamer_sequences.csv",
            shi_path,
            1,
        ),
        (
            "carbapenemase_additions_overrides",
            "additions",
            "data/raw/evaluation_references/carbapenemase_reference_additions_and_overrides.csv",
            additions_path,
            8,
        ),
    ]
    for key, dataset, rel, path, n_rows in files:
        registry_rows.append(
            {
                "source_key": key,
                "source_dataset": dataset,
                "path": rel,
                "sha256": _hash_path(path),
                "n_rows_expected": str(n_rows),
                "snapshot_date": "2026-08-05",
                "tier": "eval",
                "redistribution_status": "unknown",
                "notes": "synthetic",
            }
        )
    from s0_build_registry import count_xlsx_physical_data_rows

    registry_rows[1]["n_rows_expected"] = str(
        count_xlsx_physical_data_rows(precision_path)
    )
    registry_path = repo / "config" / "source_registry.csv"
    _write_csv(registry_path, list(REQUIRED_COLUMNS), registry_rows)

    output_dir = repo / "data" / "interim" / "evaluation"
    input_hashes = {p: _hash_path(p) for _, _, _, p, _ in files}

    try:
        result = build_leakage_exclusion(
            repo_root=repo,
            registry_spec=registry_path,
            target_aliases_path=aliases_path,
            output_dir=output_dir,
        )
        result2 = build_leakage_exclusion(
            repo_root=repo,
            registry_spec=registry_path,
            target_aliases_path=aliases_path,
            output_dir=output_dir,
        )
    finally:
        mod._assert_length = original_assert  # type: ignore[assignment]
        mod.D9_DOCUMENTED_LENGTHS.clear()
        mod.D9_DOCUMENTED_LENGTHS.update(original_lengths)

    for path, digest in input_hashes.items():
        assert _hash_path(path) == digest

    leakage = repo / "data" / "interim" / "leakage_exclusion_set.csv"
    pending = output_dir / "pending_reference_extractions.csv"
    dataset = output_dir / "reference_dataset_manifest.csv"
    assert leakage.is_file()
    assert pending.is_file()
    assert dataset.is_file()

    with leakage.open(encoding="utf-8", newline="") as handle:
        leak_rows = list(csv.DictReader(handle))
    assert list(leak_rows[0].keys()) == list(LEAKAGE_COLUMNS)
    assert all(r["status"] == "resolved" for r in leak_rows)
    assert len({r["exclusion_id"] for r in leak_rows}) == len(leak_rows)

    xk = [
        r
        for r in leak_rows
        if r["aptamer_name"].upper().replace("-", "") == "XK10"
        or r["reference_id"].startswith("yu2021_xk10")
    ]
    assert len(xk) == 1
    assert "chen_2020_xk10_csv" in xk[0]["contributing_sources"]

    with pending.open(encoding="utf-8", newline="") as handle:
        pending_rows = list(csv.DictReader(handle))
    pending_ids = {r["reference_id"] for r in pending_rows}
    assert "shi2025_kpc2kp" in pending_ids
    assert "sabrowski2022_ndm1_h14_2_43" in pending_ids
    assert not any(r["reference_id"] in pending_ids for r in leak_rows)

    with dataset.open(encoding="utf-8", newline="") as handle:
        dataset_rows = list(csv.DictReader(handle))
    assert len(dataset_rows) == 1
    assert dataset_rows[0]["reference_id"] == "prjna830749"
    assert dataset_rows[0]["include_in_sequence_leakage"] == "false"

    assert result.leakage_rows == result2.leakage_rows
    assert result.incomplete is True

    for tracked in (registry_path, aliases_path):
        text = tracked.read_text(encoding="utf-8")
        assert str(repo) not in text
        assert not SEQ_LEAK_RE.search(text)

    report = (output_dir / "leakage_build_report.md").read_text(encoding="utf-8")
    assert str(repo) not in report
    assert "/Users/" not in report

    # Ensure long nucleotide runs from fixtures do not appear on captured stdout.
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert not SEQ_LEAK_RE.search(combined)


def test_apnv_length_validation() -> None:
    import s0_build_leakage_exclusion as mod

    with pytest.raises(LeakageBuildError, match="APNV"):
        mod._assert_length("APNV", "ACGT", 35)
    mod._assert_length("APNV", "A" * 35, 35)

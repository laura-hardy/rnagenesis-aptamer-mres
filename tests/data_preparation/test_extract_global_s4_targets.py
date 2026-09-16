"""Tests for Milestone-2 raw target extraction (synthetic fixtures only).

Every literal nucleotide string in this file is shorter than 20 nt. Does not
read live combined-input CSVs, source handoffs, or biological RDF extracts.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.target_extraction_aptamerbase import (  # noqa: E402
    CONFIRMED_BY,
    HAS_KD,
    HAS_PARTICIPANT,
    IS_PARTICIPANT_IN,
    RDF_TYPE,
    RDFS_LABEL,
    TYPE_APTAMER,
    TYPE_APTAMER_TARGET,
    TYPE_INTERACTION,
    TYPE_PAIRWISE,
    extract_aptamerbase_record,
    load_aptamerbase_target_graph,
)
from adapters.target_extraction_common import (  # noqa: E402
    RECORD_COLUMNS,
    TargetExtractionError,
    alias_candidate_key,
    primary_match_key,
)
from adapters.target_extraction_dictionary import (  # noqa: E402
    build_target_dictionary,
)
from adapters.target_extraction_ncbi import extract_ncbi_nuc_record  # noqa: E402
from adapters.target_extraction_riboaptamer import (  # noqa: E402
    classify_seq_first_underscore,
    extract_riboaptamer_record,
)
from extract_global_s4_targets import (  # noqa: E402
    extract_global_s4_targets,
    extract_structured_record,
)

URI_APT = "http://rdf.freebase.com/ns/m.syn_apt"
URI_APT_B = "http://rdf.freebase.com/ns/m.syn_apt_b"
URI_INT = "http://rdf.freebase.com/ns/m.syn_int"
URI_INT2 = "http://rdf.freebase.com/ns/m.syn_int2"
URI_TGT = "http://rdf.freebase.com/ns/m.syn_tgt"
URI_TGT2 = "http://rdf.freebase.com/ns/m.syn_tgt2"
URI_KD = "http://rdf.freebase.com/ns/m.syn_kd"
URI_AFF = "http://rdf.freebase.com/ns/m.syn_aff"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _triple(subject: str, predicate: str, obj: str, *, literal: bool = False, lang: str = "") -> str:
    if literal:
        lang_tag = f"@{lang}" if lang else ""
        escaped = obj.replace("\\", "\\\\").replace('"', '\\"')
        return f"<{subject}> <{predicate}> \"{escaped}\"{lang_tag} ."
    return f"<{subject}> <{predicate}> <{obj}> ."


def _write_rdf(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _row(**overrides: str) -> dict[str, str]:
    base = {
        "record_id": "src:1",
        "source_db": "utexas",
        "native_id": "n1",
        "target_name_raw": "",
        "target_name": "",
        "target_uniprot": "",
        "target_type": "",
        "target_type_source": "",
        "target_family": "",
        "target_pfam": "",
        "pdb_id": "",
        "binding_evidence_type": "",
        "binding_evidence_score": "",
        "affinity_value": "",
        "affinity_unit": "",
        "affinity_type": "",
    }
    base.update(overrides)
    return base


def test_one_extraction_row_per_input_record(tmp_path: Path) -> None:
    combined = tmp_path / "data/interim/global_s4/combined_global_s4_input.csv"
    rows = [
        _row(record_id="utexas:1", source_db="utexas", native_id="u1", target_name_raw="VEGF"),
        _row(record_id="utexas:2", source_db="utexas", native_id="u2", target_name_raw="FGF2"),
    ]
    _write_csv(combined, list(rows[0].keys()), rows)
    config = {
        "contract_id": "global_s4_target_extraction",
        "expected_combined_records": 2,
        "expected_combined_sha256": _sha256(combined),
        "combined_input_csv": "data/interim/global_s4/combined_global_s4_input.csv",
        "output_record_csv": "data/interim/global_s4/target_extraction_by_record.csv",
        "output_relationship_csv": "data/interim/global_s4/target_relationship_proposals.csv",
        "output_dictionary_csv": "data/interim/global_s4/target_dictionary_proposed.csv",
        "output_summary": "data/interim/global_s4/target_extraction_summary.md",
        "output_manifest": "data/interim/global_s4/target_extraction_manifest.json",
        "scientific_boundary": {"writes_into_combined_input": False},
    }
    config_path = tmp_path / "config/global_s4_target_extraction.json"
    _write_json(config_path, config)
    before = combined.read_bytes()
    result = extract_global_s4_targets(
        extraction_config=config_path, repo_root=tmp_path
    )
    assert result.n_records == 2
    assert result.n_relationships == 2
    with result.output_record_csv.open(newline="", encoding="utf-8") as handle:
        extracted = list(csv.DictReader(handle))
    assert [row["record_id"] for row in extracted] == ["utexas:1", "utexas:2"]
    assert combined.read_bytes() == before
    assert _sha256(combined) == config["expected_combined_sha256"]
    for row in extracted:
        assert row["existing_target_name_raw"] in {"VEGF", "FGF2"}
        assert row["effective_target_raw"] == row["existing_target_name_raw"]
        assert list(row.keys()) == list(RECORD_COLUMNS)


def test_structured_handoff_target_preserved_exactly() -> None:
    row = _row(
        record_id="aptadb:1",
        source_db="aptadb",
        target_name_raw="Thrombin (EC 3.4.21.5)",
        aptadb_uniprot_id="P00734",
        aptadb_target_id="T1",
        aptadb_target_chemistry="Protein",
        aptadb_protein_names="Thrombin (EC 3.4.21.5)",
    )
    extraction = extract_structured_record(row)
    assert extraction.effective_target_raw == "Thrombin (EC 3.4.21.5)"
    assert extraction.source_uniprot_seed == "P00734"
    assert extraction.source_target_type_prior == "Protein"
    assert extraction.source_target_type_prior_source == "aptadb_target_chemistry"
    assert extraction.relationship_status == "resolved_single"
    assert "source_seed_only" in extraction.notes


def test_structured_target_name_raw_whitespace_preserved_exactly() -> None:
    extraction = extract_structured_record(
        _row(
            record_id="utexas:1",
            source_db="utexas",
            target_name_raw="Tenascin-C (TN-C) ",
        )
    )
    assert extraction.existing_target_name_raw == "Tenascin-C (TN-C) "
    assert extraction.effective_target_raw == "Tenascin-C (TN-C) "
    assert extraction.relationships[0].raw_target == "Tenascin-C (TN-C) "


def test_blank_unresolved_target_is_not_guessed() -> None:
    row = _row(record_id="riboaptamer:1", source_db="riboaptamer")
    extraction = extract_riboaptamer_record(row)
    assert extraction.relationship_status == "unresolved"
    assert extraction.effective_target_raw == ""
    assert extraction.relationships == []


def test_canonical_s4_fields_stay_unpopulated_on_combined(tmp_path: Path) -> None:
    combined = tmp_path / "data/interim/global_s4/combined_global_s4_input.csv"
    row = _row(record_id="utexas:1", source_db="utexas", target_name_raw="VEGF")
    _write_csv(combined, list(row.keys()), [row])
    config = {
        "contract_id": "global_s4_target_extraction",
        "expected_combined_records": 1,
        "expected_combined_sha256": _sha256(combined),
        "combined_input_csv": "data/interim/global_s4/combined_global_s4_input.csv",
        "output_record_csv": "data/interim/global_s4/target_extraction_by_record.csv",
        "output_relationship_csv": "data/interim/global_s4/target_relationship_proposals.csv",
        "output_dictionary_csv": "data/interim/global_s4/target_dictionary_proposed.csv",
        "output_summary": "data/interim/global_s4/target_extraction_summary.md",
        "output_manifest": "data/interim/global_s4/target_extraction_manifest.json",
    }
    _write_json(tmp_path / "config/global_s4_target_extraction.json", config)
    extract_global_s4_targets(
        extraction_config=tmp_path / "config/global_s4_target_extraction.json",
        repo_root=tmp_path,
    )
    with combined.open(newline="", encoding="utf-8") as handle:
        live = next(csv.DictReader(handle))
    for field in (
        "target_name",
        "target_uniprot",
        "target_type",
        "target_family",
        "target_pfam",
        "pdb_id",
        "binding_evidence_type",
        "affinity_value",
    ):
        assert live.get(field, "") == ""


def test_relationship_proposals_may_be_one_to_many_without_expanding_input() -> None:
    rdf_lines = [
        _triple(URI_APT, RDF_TYPE, TYPE_APTAMER),
        _triple(URI_APT, RDFS_LABEL, "aptamer-label", literal=True, lang="en"),
        _triple(URI_INT, RDF_TYPE, TYPE_PAIRWISE),
        _triple(URI_INT2, RDF_TYPE, TYPE_PAIRWISE),
        _triple(URI_APT, IS_PARTICIPANT_IN, URI_INT),
        _triple(URI_APT, IS_PARTICIPANT_IN, URI_INT2),
        _triple(URI_INT, HAS_PARTICIPANT, URI_APT),
        _triple(URI_INT, HAS_PARTICIPANT, URI_TGT),
        _triple(URI_INT2, HAS_PARTICIPANT, URI_APT),
        _triple(URI_INT2, HAS_PARTICIPANT, URI_TGT2),
        _triple(URI_TGT, RDF_TYPE, TYPE_APTAMER_TARGET),
        _triple(URI_TGT2, RDF_TYPE, TYPE_APTAMER_TARGET),
        _triple(URI_TGT, RDFS_LABEL, "NFkappaB p50", literal=True, lang="en"),
        _triple(URI_TGT2, RDFS_LABEL, "NFkappaB p65", literal=True, lang="en"),
    ]
    # load via temp graph
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "graph.nt.gz"
        _write_rdf(path, rdf_lines)
        graph = load_aptamerbase_target_graph(path)
    extraction = extract_aptamerbase_record(
        _row(
            record_id="aptamerbase:1",
            source_db="aptamerbase",
            aptamerbase_id=URI_APT,
            aptamerbase_label="aptamer-label",
        ),
        graph=graph,
    )
    assert extraction.relationship_status == "resolved_multiple"
    assert extraction.record_expansion_proposed is True
    assert len(extraction.relationships) == 2


def test_riboaptamer_explicit_sequence_name_target() -> None:
    extraction = extract_riboaptamer_record(
        _row(
            record_id="riboaptamer:1",
            source_db="riboaptamer",
            riboaptamer_aptamer_name="VEGF aptamer",
            riboaptamer_sequence_name="Vascular Endothelial Growth Factor (VEGF)_24A",
            riboaptamer_description="VEGF is a signalling protein.",
            riboaptamer_category="Mammalian",
            riboaptamer_type="Proteins",
        )
    )
    assert extraction.relationship_status == "resolved_single"
    assert extraction.effective_target_raw == "Vascular Endothelial Growth Factor (VEGF)"
    assert extraction.target_extraction_method == "RA_SEQ_FIRST_UNDERSCORE"
    assert extraction.source_target_type_prior == "Proteins"
    assert "prior_only" in extraction.notes


def test_riboaptamer_generic_clone_name_does_not_generate_target() -> None:
    extraction = extract_riboaptamer_record(
        _row(
            record_id="riboaptamer:2",
            source_db="riboaptamer",
            riboaptamer_aptamer_name="II-mini3-4 aptamer",
            riboaptamer_sequence_name="Hoechst 1captamer II",
            riboaptamer_description="Background about a dye family.",
            riboaptamer_category="Fluorophores",
            riboaptamer_type="Small molecules",
        )
    )
    assert extraction.relationship_status == "unresolved"
    assert extraction.effective_target_raw == ""


def test_riboaptamer_category_alone_never_generates_target() -> None:
    extraction = extract_riboaptamer_record(
        _row(
            record_id="riboaptamer:3",
            source_db="riboaptamer",
            riboaptamer_aptamer_name="cloneQ",
            riboaptamer_sequence_name="cloneQ",
            riboaptamer_description="A mammalian protein involved in signalling.",
            riboaptamer_category="Mammalian",
            riboaptamer_type="Proteins",
        )
    )
    assert extraction.relationship_status == "unresolved"
    assert "VEGF" not in extraction.extracted_target_raw


def test_riboaptamer_ambiguous_multi_entity_prefix() -> None:
    extraction = extract_riboaptamer_record(
        _row(
            record_id="riboaptamer:4",
            source_db="riboaptamer",
            riboaptamer_aptamer_name="MG aptamer",
            riboaptamer_sequence_name="Malachite green (MG),Tetramethylrhodamine (TMR)_MG aptamer",
            riboaptamer_description="Fluorophore background.",
            riboaptamer_type="Small molecules",
        )
    )
    assert extraction.relationship_status == "ambiguous"
    assert extraction.requires_checkpoint2 is True
    assert len(extraction.relationships) == 2
    assert extraction.target_extraction_method.startswith("RA_")


def test_riboaptamer_conflicting_sequence_and_aptamer_names_are_ambiguous() -> None:
    extraction = extract_riboaptamer_record(
        _row(
            record_id="riboaptamer:6",
            source_db="riboaptamer",
            riboaptamer_aptamer_name="polβ aptamer",
            riboaptamer_sequence_name="DNA polymerase kappa (polκ)_32",
            riboaptamer_description="DNA polymerase kappa is a DNA polymerase enzyme.",
            riboaptamer_type="Proteins",
        )
    )
    assert extraction.relationship_status == "ambiguous"
    assert extraction.target_extraction_method == "RA_SEQ_FIRST_UNDERSCORE_CONFLICT"
    assert extraction.requires_checkpoint2 is True
    assert extraction.effective_target_raw == ""
    raws = {rel.raw_target for rel in extraction.relationships}
    assert "DNA polymerase kappa (polκ)" in raws
    assert "polβ" in raws


def test_riboaptamer_clone_aptamer_name_keeps_descriptive_sequence_prefix() -> None:
    extraction = extract_riboaptamer_record(
        _row(
            record_id="riboaptamer:7",
            source_db="riboaptamer",
            riboaptamer_aptamer_name="FB-1 aptamer",
            riboaptamer_sequence_name="Fluorescein_FB-1",
            riboaptamer_description="Fluorescein is a synthetic fluorophore.",
            riboaptamer_type="Small molecules",
        )
    )
    assert extraction.relationship_status == "resolved_single"
    assert extraction.effective_target_raw == "Fluorescein"
    assert extraction.target_extraction_method == "RA_SEQ_FIRST_UNDERSCORE"


def test_riboaptamer_unsupported_sequence_prefix_is_not_deterministic() -> None:
    extraction = extract_riboaptamer_record(
        _row(
            record_id="riboaptamer:8",
            source_db="riboaptamer",
            riboaptamer_aptamer_name="cloneQ aptamer",
            riboaptamer_sequence_name="cloneQ_1",
            riboaptamer_description="A mammalian protein involved in signalling.",
            riboaptamer_category="Mammalian",
            riboaptamer_type="Proteins",
        )
    )
    assert extraction.relationship_status == "unresolved"
    assert extraction.effective_target_raw == ""
    assert extraction.target_extraction_method == "RA_SEQ_FIRST_UNDERSCORE_UNSUPPORTED"


def test_riboaptamer_seq_first_underscore_audit_classes() -> None:
    corroborated = classify_seq_first_underscore(
        prefix="Vascular Endothelial Growth Factor (VEGF)",
        aptamer_name="VEGF aptamer",
        description="VEGF is a signalling protein.",
        article_name="An RNA aptamer of VEGF",
    )
    assert corroborated.classification == "corroborated_target_label"
    assert "aptamer_name" in corroborated.corroboration_sources

    clone = classify_seq_first_underscore(
        prefix="Tobramycin",
        aptamer_name="J6f1 aptamer",
        description="Background text without the ligand string.",
        article_name="J6f1",
    )
    assert clone.classification == "sequence_name_is_explicit_target_label"

    conflict = classify_seq_first_underscore(
        prefix="DNA polymerase kappa (polκ)",
        aptamer_name="polβ aptamer",
        description="DNA polymerase kappa is described here.",
        article_name="Aptamer 32",
    )
    assert conflict.classification == "conflicting_source_metadata"


def test_riboaptamer_rule_provenance_is_recorded() -> None:
    extraction = extract_riboaptamer_record(
        _row(
            record_id="riboaptamer:5",
            source_db="riboaptamer",
            riboaptamer_aptamer_name="ATP aptamer",
            riboaptamer_sequence_name="Adenosine triphosphate (ATP)_rafl7",
            riboaptamer_type="Small molecules",
        )
    )
    assert "rule=RA_SEQ_FIRST_UNDERSCORE" in extraction.relationships[0].target_provenance_locator
    assert extraction.relationships[0].target_provenance_source == "riboaptamer_sequence_name"


def test_aptamerbase_single_target_resolved(tmp_path: Path) -> None:
    lines = [
        _triple(URI_APT, RDF_TYPE, TYPE_APTAMER),
        _triple(URI_APT, RDFS_LABEL, "9685413-Thrombin-1", literal=True, lang="en"),
        _triple(URI_INT, RDF_TYPE, TYPE_INTERACTION),
        _triple(URI_INT, RDF_TYPE, TYPE_PAIRWISE),
        _triple(URI_APT, IS_PARTICIPANT_IN, URI_INT),
        _triple(URI_INT, HAS_PARTICIPANT, URI_APT),
        _triple(URI_INT, HAS_PARTICIPANT, URI_TGT),
        _triple(URI_INT, HAS_KD, URI_KD),
        _triple(URI_INT, CONFIRMED_BY, URI_AFF),
        _triple(URI_TGT, RDF_TYPE, TYPE_APTAMER_TARGET),
        _triple(URI_TGT, RDFS_LABEL, "Thrombin", literal=True, lang="en"),
        _triple(URI_TGT, RDFS_LABEL, "Trombina", literal=True, lang="es"),
        _triple(URI_KD, RDF_TYPE, "http://rdf.freebase.com/ns/base.aptamer.dissociation_constant"),
        _triple(
            URI_KD,
            "http://rdf.freebase.com/ns/base.aptamer.dissociation_constant.has_value",
            "1.2",
            literal=True,
        ),
    ]
    path = tmp_path / "graph.nt.gz"
    _write_rdf(path, lines)
    graph = load_aptamerbase_target_graph(path)
    extraction = extract_aptamerbase_record(
        _row(
            record_id="aptamerbase:1",
            source_db="aptamerbase",
            aptamerbase_id=URI_APT,
            aptamerbase_label="9685413-Thrombin-1",
        ),
        graph=graph,
    )
    assert extraction.relationship_status == "resolved_single"
    assert extraction.effective_target_raw == "Thrombin"
    assert extraction.effective_target_raw != "9685413-Thrombin-1"
    assert extraction.effective_target_raw != "Trombina"
    assert "evidence_not_assigned" in extraction.notes
    assert "affinity_not_canonicalised" in extraction.notes
    assert extraction.source_target_id == URI_TGT


def test_aptamerbase_multiple_indistinguishable_counterparts_ambiguous(tmp_path: Path) -> None:
    lines = [
        _triple(URI_APT, RDF_TYPE, TYPE_APTAMER),
        _triple(URI_APT, RDFS_LABEL, "aptamer-x", literal=True, lang="en"),
        _triple(URI_INT, RDF_TYPE, TYPE_PAIRWISE),
        _triple(URI_APT, IS_PARTICIPANT_IN, URI_INT),
        _triple(URI_INT, HAS_PARTICIPANT, URI_APT),
        _triple(URI_INT, HAS_PARTICIPANT, URI_TGT),
        _triple(URI_INT, HAS_PARTICIPANT, URI_TGT2),
        _triple(URI_TGT, RDF_TYPE, TYPE_APTAMER_TARGET),
        _triple(URI_TGT2, RDF_TYPE, TYPE_APTAMER_TARGET),
        _triple(URI_TGT, RDFS_LABEL, "VEGF165", literal=True, lang="en"),
        _triple(URI_TGT2, RDFS_LABEL, "RVV-X", literal=True, lang="en"),
    ]
    path = tmp_path / "graph.nt.gz"
    _write_rdf(path, lines)
    graph = load_aptamerbase_target_graph(path)
    extraction = extract_aptamerbase_record(
        _row(
            record_id="aptamerbase:2",
            source_db="aptamerbase",
            aptamerbase_id=URI_APT,
            aptamerbase_label="aptamer-x",
        ),
        graph=graph,
    )
    assert extraction.relationship_status == "ambiguous"
    assert extraction.record_expansion_proposed is False
    assert extraction.requires_checkpoint2 is True
    assert {rel.raw_target for rel in extraction.relationships} == {"VEGF165", "RVV-X"}


def test_aptamerbase_no_interaction_unresolved(tmp_path: Path) -> None:
    lines = [
        _triple(URI_APT, RDF_TYPE, TYPE_APTAMER),
        _triple(URI_APT, RDFS_LABEL, "orphan-aptamer", literal=True, lang="en"),
        _triple(URI_TGT, RDF_TYPE, TYPE_APTAMER_TARGET),
        _triple(URI_TGT, RDFS_LABEL, "ShouldNotUse", literal=True, lang="en"),
    ]
    path = tmp_path / "graph.nt.gz"
    _write_rdf(path, lines)
    graph = load_aptamerbase_target_graph(path)
    extraction = extract_aptamerbase_record(
        _row(
            record_id="aptamerbase:3",
            source_db="aptamerbase",
            aptamerbase_id=URI_APT,
            aptamerbase_label="orphan-aptamer",
        ),
        graph=graph,
    )
    assert extraction.relationship_status == "unresolved"
    assert extraction.effective_target_raw == ""


def test_aptamerbase_own_label_never_used_as_target(tmp_path: Path) -> None:
    lines = [
        _triple(URI_APT, RDF_TYPE, TYPE_APTAMER),
        _triple(URI_APT, RDFS_LABEL, "my-aptamer-label", literal=True, lang="en"),
        _triple(URI_INT, RDF_TYPE, TYPE_PAIRWISE),
        _triple(URI_APT, IS_PARTICIPANT_IN, URI_INT),
        _triple(URI_INT, HAS_PARTICIPANT, URI_APT),
        _triple(URI_INT, HAS_PARTICIPANT, URI_TGT),
        _triple(URI_TGT, RDF_TYPE, TYPE_APTAMER_TARGET),
        _triple(URI_TGT, RDFS_LABEL, "Protein X", literal=True, lang="en"),
    ]
    path = tmp_path / "graph.nt.gz"
    _write_rdf(path, lines)
    graph = load_aptamerbase_target_graph(path)
    extraction = extract_aptamerbase_record(
        _row(
            record_id="aptamerbase:4",
            source_db="aptamerbase",
            aptamerbase_id=URI_APT,
            aptamerbase_label="my-aptamer-label",
        ),
        graph=graph,
    )
    assert extraction.effective_target_raw == "Protein X"
    assert extraction.effective_target_raw != "my-aptamer-label"


def test_ncbi_explicit_binds_is_candidate() -> None:
    extraction = extract_ncbi_nuc_record(
        _row(
            record_id="ncbi_nuc:1",
            source_db="ncbi_nuc",
            ncbi_nuc_accession="U34759",
            ncbi_nuc_definition="Synthetic RNA aptamer which binds to a hairpin derived from Bacillus subtilis RNASE P RNA.",
            ncbi_nuc_source_organism="synthetic construct",
        )
    )
    assert extraction.relationship_status == "resolved_single"
    assert "hairpin derived from Bacillus subtilis RNASE P RNA" in extraction.effective_target_raw
    assert extraction.target_provenance_source == "ncbi_nuc_definition"
    assert extraction.effective_target_raw != "synthetic construct"


def test_ncbi_title_only_is_not_sufficient() -> None:
    extraction = extract_ncbi_nuc_record(
        _row(
            record_id="ncbi_nuc:2",
            source_db="ncbi_nuc",
            ncbi_nuc_accession="X1",
            ncbi_nuc_definition="Synthetic RNA molecule, complete sequence.",
            ncbi_nuc_references_json=json.dumps(
                [{"title": "An L-arginine binding RNA motif", "pubmed_id": "1"}]
            ),
        )
    )
    assert extraction.relationship_status == "unresolved"
    assert extraction.effective_target_raw == ""


def test_ncbi_source_organism_is_not_target() -> None:
    extraction = extract_ncbi_nuc_record(
        _row(
            record_id="ncbi_nuc:3",
            source_db="ncbi_nuc",
            ncbi_nuc_accession="X2",
            ncbi_nuc_definition="Random genomic RNA fragment.",
            ncbi_nuc_source_organism="Homo sapiens",
        )
    )
    assert extraction.relationship_status == "unresolved"
    assert "Homo sapiens" not in extraction.effective_target_raw


def test_ncbi_multiple_target_statements_are_checkpoint2() -> None:
    extraction = extract_ncbi_nuc_record(
        _row(
            record_id="ncbi_nuc:4",
            source_db="ncbi_nuc",
            ncbi_nuc_accession="BD161067",
            ncbi_nuc_definition="RNA molecule targeting IRES and NS3 protease of hepatitis C virus.",
        )
    )
    assert extraction.relationship_status == "ambiguous"
    assert extraction.requires_checkpoint2 is True
    assert len(extraction.relationships) >= 2


def test_dictionary_case_whitespace_grouping() -> None:
    a = extract_structured_record(
        _row(record_id="utexas:1", source_db="utexas", target_name_raw="FGF2")
    )
    b = extract_structured_record(
        _row(record_id="utexas:2", source_db="utexas", target_name_raw="  fgf2 ")
    )
    rows, _diag = build_target_dictionary([a, b])
    assert len(rows) == 1
    assert rows[0]["n_records"] == "2"
    assert rows[0]["canonical_target_name_proposal"] in {"FGF2", "fgf2"}
    assert "FGF2" in rows[0]["raw_target"] or "fgf2" in rows[0]["raw_target"]


def test_dictionary_punctuation_alias_candidate_not_auto_merged() -> None:
    a = extract_structured_record(
        _row(record_id="utexas:1", source_db="utexas", target_name_raw="FGF2")
    )
    b = extract_structured_record(
        _row(record_id="utexas:2", source_db="utexas", target_name_raw="FGF-2")
    )
    assert alias_candidate_key("FGF2") == alias_candidate_key("FGF-2")
    assert primary_match_key("FGF2") != primary_match_key("FGF-2")
    rows, diag = build_target_dictionary([a, b])
    assert len(rows) == 2
    assert int(diag["n_alias_candidate_groups"]) >= 1
    assert any("alias_candidate_with_distinct_primary_keys" in row["ambiguity_flags"] for row in rows)


def test_dictionary_conflicting_uniprot_seeds_do_not_merge() -> None:
    a = extract_structured_record(
        _row(
            record_id="aptadb:1",
            source_db="aptadb",
            target_name_raw="Prothrombin",
            aptadb_uniprot_id="P00734",
            aptadb_target_id="T1",
            aptadb_target_chemistry="Protein",
        )
    )
    b = extract_structured_record(
        _row(
            record_id="aptadb:2",
            source_db="aptadb",
            target_name_raw="Prothrombin",
            aptadb_uniprot_id="P00735",
            aptadb_target_id="T2",
            aptadb_target_chemistry="Protein",
        )
    )
    rows, diag = build_target_dictionary([a, b])
    assert len(rows) == 2
    seeds = {row["source_uniprot_seed"] for row in rows}
    assert seeds == {"P00734", "P00735"}
    assert int(diag["n_uniprot_conflict_entries"]) == 2
    assert all(row["requires_checkpoint2"] == "true" for row in rows)


def test_dictionary_does_not_deduplicate_sequences() -> None:
    a = extract_structured_record(
        _row(record_id="ena:1", source_db="ena", target_name_raw="lysozyme")
    )
    b = extract_structured_record(
        _row(record_id="ena:2", source_db="ena", target_name_raw="lysozyme")
    )
    rows, _diag = build_target_dictionary([a, b])
    assert len(rows) == 1
    assert rows[0]["n_records"] == "2"
    assert rows[0]["n_relationships"] == "2"


def test_aptabase_sidecar_join_is_one_to_one() -> None:
    sidecar = {
        "aptabase:1": {
            "record_id": "aptabase:1",
            "aptabase_target_specific": "IgE",
            "aptabase_target_general": "Protein",
        }
    }
    extraction = extract_structured_record(
        _row(
            record_id="aptabase:1",
            source_db="aptabase",
            target_name_raw="IgE",
        ),
        aptabase_sidecar=sidecar,
    )
    assert extraction.effective_target_raw == "IgE"
    assert extraction.source_target_type_prior == "Protein"
    assert extraction.source_target_type_prior_source == "aptabase_target_general"


def test_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    combined = tmp_path / "data/interim/global_s4/combined_global_s4_input.csv"
    row = _row(record_id="utexas:1", source_db="utexas", target_name_raw="VEGF")
    _write_csv(combined, list(row.keys()), [row])
    config = {
        "contract_id": "global_s4_target_extraction",
        "expected_combined_records": 1,
        "expected_combined_sha256": "0" * 64,
        "combined_input_csv": "data/interim/global_s4/combined_global_s4_input.csv",
        "output_record_csv": "data/interim/global_s4/target_extraction_by_record.csv",
        "output_relationship_csv": "data/interim/global_s4/target_relationship_proposals.csv",
        "output_dictionary_csv": "data/interim/global_s4/target_dictionary_proposed.csv",
        "output_summary": "data/interim/global_s4/target_extraction_summary.md",
        "output_manifest": "data/interim/global_s4/target_extraction_manifest.json",
    }
    _write_json(tmp_path / "config/global_s4_target_extraction.json", config)
    with pytest.raises(TargetExtractionError, match="SHA-256"):
        extract_global_s4_targets(
            extraction_config=tmp_path / "config/global_s4_target_extraction.json",
            repo_root=tmp_path,
        )


def test_deterministic_order(tmp_path: Path) -> None:
    combined = tmp_path / "data/interim/global_s4/combined_global_s4_input.csv"
    rows = [
        _row(record_id="utexas:b", source_db="utexas", target_name_raw="B"),
        _row(record_id="utexas:a", source_db="utexas", target_name_raw="A"),
    ]
    _write_csv(combined, list(rows[0].keys()), rows)
    config = {
        "contract_id": "global_s4_target_extraction",
        "expected_combined_records": 2,
        "expected_combined_sha256": _sha256(combined),
        "combined_input_csv": "data/interim/global_s4/combined_global_s4_input.csv",
        "output_record_csv": "data/interim/global_s4/target_extraction_by_record.csv",
        "output_relationship_csv": "data/interim/global_s4/target_relationship_proposals.csv",
        "output_dictionary_csv": "data/interim/global_s4/target_dictionary_proposed.csv",
        "output_summary": "data/interim/global_s4/target_extraction_summary.md",
        "output_manifest": "data/interim/global_s4/target_extraction_manifest.json",
    }
    config_path = tmp_path / "config/global_s4_target_extraction.json"
    _write_json(config_path, config)
    first = extract_global_s4_targets(extraction_config=config_path, repo_root=tmp_path)
    first_bytes = (
        first.output_record_csv.read_bytes(),
        first.output_relationship_csv.read_bytes(),
        first.output_dictionary_csv.read_bytes(),
        first.output_summary.read_bytes(),
        first.output_manifest.read_bytes(),
    )
    second = extract_global_s4_targets(extraction_config=config_path, repo_root=tmp_path)
    assert second.output_record_csv.read_bytes() == first_bytes[0]
    assert second.output_relationship_csv.read_bytes() == first_bytes[1]
    assert second.output_dictionary_csv.read_bytes() == first_bytes[2]
    assert second.output_summary.read_bytes() == first_bytes[3]
    assert second.output_manifest.read_bytes() == first_bytes[4]
    with first.output_record_csv.open(newline="", encoding="utf-8") as handle:
        ids = [row["record_id"] for row in csv.DictReader(handle)]
    assert ids == ["utexas:b", "utexas:a"]

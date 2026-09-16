"""Synthetic tests for evidence-ladder proposals."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s4_evidence import (  # noqa: E402
    propose_aptabase_evidence,
    propose_aptadb_evidence,
    propose_aptamerbase_evidence,
    propose_aptaindex_evidence,
    propose_ena_evidence,
    propose_ncbi_evidence,
    propose_riboaptamer_evidence,
    propose_utexas_evidence,
)


def test_quantitative_affinity_is_e2() -> None:
    result = propose_utexas_evidence({"utexas_kd_nm": "5", "utexas_affinity": "Kd: 5 nM"})
    assert result["evidence_level_proposed"] == "E2"
    assert result["evidence_score_proposed"] == "4"


def test_explicit_qualitative_assay_is_e3() -> None:
    result = propose_aptadb_evidence(
        {
            "aptadb_aptamer_assay": "An ELISA-based assay demonstrating binding",
            "aptadb_binding_conditions_buffer": "PBS pH 7.4",
            "aptadb_reference_pubmed_id": "12345",
        }
    )
    assert result["evidence_level_proposed"] == "E3"


def test_selection_provenance_is_e4() -> None:
    result = propose_ena_evidence(
        {"ena_source_binding_evidence_type": "selection_against_target"}
    )
    assert result["evidence_level_proposed"] == "E4"


def test_database_only_is_e5() -> None:
    result = propose_ena_evidence(
        {"ena_source_binding_evidence_type": "target_specific_aptamer_claim"}
    )
    assert result["evidence_level_proposed"] == "E5"
    assert result["e4_e5_threshold_ambiguous"] == "true"


def test_buffer_alone_is_not_e3() -> None:
    result = propose_aptadb_evidence(
        {
            "aptadb_aptamer_assay": "N/A",
            "aptadb_binding_conditions_buffer": "PBS, 150 mM NaCl",
            "aptadb_reference_pubmed_id": "999",
        }
    )
    assert result["evidence_level_proposed"] != "E3"
    assert "buffer_not_qualitative_assay" in result["notes"]


def test_structure_boolean_alone_is_not_e1() -> None:
    result = propose_aptamerbase_evidence(
        {
            "aptamerbase_id": "http://rdf.freebase.com/ns/m.syn",
            "aptamerbase_has_experimentally_determined_structure": "true",
        },
        graph=None,
    )
    assert result["evidence_level_proposed"] != "E1"
    assert "not_verified" in result["structural_complex_status"] or "not_e1" in result["structural_complex_status"]


def test_e1_requires_verified_complex_not_mmcif_url() -> None:
    result = propose_riboaptamer_evidence(
        {
            "riboaptamer_affinity_kd": "N/A",
            "riboaptamer_mmcif_download_url": "https://example.invalid/6MSF.cif",
            "riboaptamer_pubmed_link": "https://pubmed.ncbi.nlm.nih.gov/1",
        }
    )
    assert result["evidence_level_proposed"] != "E1"
    assert result["structural_complex_status"].startswith("mmcif_url_present")


def test_e4_e5_ambiguous_flagged() -> None:
    result = propose_ena_evidence(
        {"ena_source_binding_evidence_type": "target_specific_aptamer_claim"}
    )
    assert result["e4_e5_threshold_ambiguous"] == "true"
    assert result["evidence_requires_review"] == "true"


def test_aptaindex_lod_is_not_e2() -> None:
    result = propose_aptaindex_evidence(
        {
            "aptaindex_affinity_type": "LOD",
            "aptaindex_affinity": "1",
            "aptaindex_affinity_units": "pM",
        }
    )
    assert result["evidence_level_proposed"] != "E2"


def test_ncbi_publication_alone_not_e4() -> None:
    result = propose_ncbi_evidence(
        {
            "ncbi_nuc_accession": "U99999",
            "ncbi_nuc_definition": "Synthetic RNA fragment.",
            "ncbi_nuc_references_json": '[{"title": "A paper"}]',
        }
    )
    assert result["evidence_level_proposed"] == "E5"
    assert result["e4_e5_threshold_ambiguous"] == "true"


def test_ncbi_explicit_binding_language_is_e4() -> None:
    result = propose_ncbi_evidence(
        {
            "ncbi_nuc_accession": "U37124",
            "ncbi_nuc_definition": "RNA aptamer specific for L-arginine.",
        }
    )
    assert result["evidence_level_proposed"] == "E4"


def test_aptamerbase_kd_join_is_order_independent() -> None:
    from adapters.s4_evidence import AptamerBaseEvidenceGraph

    apt_id = "http://rdf.freebase.com/ns/m.syn"
    interaction = "http://rdf.freebase.com/ns/m.int"
    kd_a = "http://rdf.freebase.com/ns/m.kd_a"
    kd_b = "http://rdf.freebase.com/ns/m.kd_b"
    graph = AptamerBaseEvidenceGraph()
    graph.is_participant_in[apt_id].add(interaction)
    graph.has_kd[interaction].update({kd_b, kd_a})
    graph.kd_values[kd_b].append("20 nM")
    graph.kd_values[kd_a].append("5 nM")
    row = {"aptamerbase_id": apt_id}
    first = propose_aptamerbase_evidence(row, graph)
    second = propose_aptamerbase_evidence(row, graph)
    assert first == second
    assert first["affinity_value_raw"] == "5 nM|20 nM"
    assert first["evidence_level_proposed"] == "E2"

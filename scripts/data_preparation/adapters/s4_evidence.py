"""Source-specific evidence-ladder proposals. Does not exclude or park records."""

from __future__ import annotations

import gzip
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from adapters.aptamerbase_rdf import parse_ntriples_line
from adapters.s4_affinity import parse_affinity_from_text, parse_affinity_value
from adapters.s4_scientific_common import (
    EVIDENCE_SCORE_BY_LEVEL,
    EVIDENCE_TYPE_BY_LEVEL,
    bool_token,
    join_unique,
)
from adapters.target_extraction_aptamerbase import (
    CONFIRMED_BY,
    HAS_KD,
    HAS_PARTICIPANT,
    IS_PARTICIPANT_IN,
)

HAS_VALUE = "http://rdf.freebase.com/ns/base.aptamer.dissociation_constant.has_value"
HAS_TEMP_VALUE = (
    "http://rdf.freebase.com/ns/base.aptamer.dissociation_constant.has_temporary_string_value"
)
AFFINITY_METHOD = "http://rdf.freebase.com/ns/base.aptamer.affinity_experiment.affinity_method"
SELEX_METHOD = "http://rdf.freebase.com/ns/base.aptamer.selex_experiment.has_selex_method"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
TYPE_SELEX = "http://rdf.freebase.com/ns/base.aptamer.selex_experiment"
TYPE_AFFINITY = "http://rdf.freebase.com/ns/base.aptamer.affinity_experiment"
TYPE_STRUCTURE = "http://rdf.freebase.com/ns/base.aptamer.nucleic_acid_secondary_structure"

ASSAY_HINT_RE = re.compile(
    r"(?i)\b(elisa|filter.?bind|spr|blitz|itc|ems(?:a)?|footprint|"
    r"pull.?down|western|binding (?:assay|curve|constant|affin)|"
    r"dissociation|kinetic|nuclease protection)\b"
)
SELECTION_HINT_RE = re.compile(
    r"(?i)\b(selex|selected against|in vitro selection|selection against)\b"
)
PDB_URL_RE = re.compile(r"(?i)(?:pdb|mmcif).*/([0-9][A-Za-z0-9]{3})")


@dataclass
class AptamerBaseEvidenceGraph:
    """Interaction-linked affinity/SELEX provenance for evidence proposals."""

    has_kd: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    kd_values: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    confirmed_by: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    types: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    affinity_methods: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    selex_methods: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    is_participant_in: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))


def load_aptamerbase_evidence_graph(path: Path) -> AptamerBaseEvidenceGraph:
    keep_needles = (
        "interaction.has_dissociation_constant",
        "dissociation_constant.has_value",
        "dissociation_constant.has_temporary_string_value",
        "interaction.is_confirmed_by",
        "affinity_experiment.affinity_method",
        "selex_experiment.has_selex_method",
        "interactor.is_participant_in",
        "base.aptamer.selex_experiment",
        "base.aptamer.affinity_experiment",
    )
    graph = AptamerBaseEvidenceGraph()
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not any(token in line for token in keep_needles):
                continue
            parsed = parse_ntriples_line(line)
            if parsed is None:
                continue
            subject, predicate, kind, obj = parsed
            if predicate == HAS_KD and kind == "uri":
                graph.has_kd[subject].add(obj)
            elif predicate in {HAS_VALUE, HAS_TEMP_VALUE} and kind == "literal":
                graph.kd_values[subject].append(obj)
            elif predicate == CONFIRMED_BY and kind == "uri":
                graph.confirmed_by[subject].add(obj)
            elif predicate == AFFINITY_METHOD:
                graph.affinity_methods[subject].add(obj)
            elif predicate == SELEX_METHOD:
                graph.selex_methods[subject].add(obj)
            elif predicate == RDF_TYPE and kind == "uri":
                graph.types[subject].add(obj)
            elif predicate == IS_PARTICIPANT_IN and kind == "uri":
                graph.is_participant_in[subject].add(obj)
    return graph


def _pack(
    level: str,
    *,
    rule: str,
    provenance: str,
    alternative: str = "",
    review: bool = False,
    e4_e5: bool = False,
    structural: str = "",
    notes: str = "",
    affinity: Mapping[str, str] | None = None,
) -> dict[str, str]:
    aff = dict(affinity or {})
    return {
        "evidence_level_proposed": level,
        "evidence_type_proposed": EVIDENCE_TYPE_BY_LEVEL.get(level, ""),
        "evidence_score_proposed": str(EVIDENCE_SCORE_BY_LEVEL.get(level, "")) if level else "",
        "evidence_rule": rule,
        "evidence_provenance": provenance,
        "alternative_evidence_level": alternative,
        "evidence_requires_review": bool_token(review),
        "e4_e5_threshold_ambiguous": bool_token(e4_e5),
        "structural_complex_status": structural,
        "notes": notes,
        "affinity_type_proposed": aff.get("affinity_type_proposed", ""),
        "affinity_value_raw": aff.get("affinity_value_raw", ""),
        "affinity_unit_raw": aff.get("affinity_unit_raw", ""),
        "affinity_value_molar_proposed": aff.get("affinity_value_molar_proposed", ""),
        "affinity_parse_status": aff.get("affinity_parse_status", ""),
        "affinity_parse_rule": aff.get("affinity_parse_rule", ""),
        "affinity_requires_review": aff.get("affinity_requires_review", "false"),
    }


def propose_aptabase_evidence(sidecar: Mapping[str, str], row: Mapping[str, str]) -> dict[str, str]:
    raw = (sidecar.get("aptabase_affinity_raw") or "").strip()
    measurement = (sidecar.get("aptabase_affinity_measurement_type") or "").strip()
    value = (sidecar.get("aptabase_affinity_value") or "").strip()
    unit = (sidecar.get("aptabase_affinity_unit") or "").strip()
    relation = (sidecar.get("aptabase_affinity_relation") or "").strip()
    parsed = parse_affinity_value(value or raw, unit=unit, affinity_type="Kd")
    if relation == "range":
        parsed["affinity_parse_status"] = "range_or_multiple"
        parsed["affinity_value_molar_proposed"] = ""
        parsed["affinity_requires_review"] = "true"
    provenance = "sidecar:aptabase_affinity_raw|aptabase_affinity_measurement_type"
    if measurement == "concentration" and (value or parsed["affinity_parse_status"] == "normalised"):
        return _pack("E2", rule="APTABASE_QUANTITATIVE_AFFINITY", provenance=provenance, affinity=parsed)
    if measurement in {"unavailable", "missing", "numeric_no_unit", "unparsed", "energy_or_other"}:
        if (row.get("publication") or sidecar.get("aptabase_pmid") or sidecar.get("aptabase_doi") or "").strip():
            return _pack(
                "E4",
                rule="APTABASE_SELECTION_PUBLICATION",
                provenance="sidecar:publication_or_pmid",
                affinity=parsed,
            )
        return _pack("E5", rule="APTABASE_DATABASE_ANNOTATION", provenance=provenance, affinity=parsed)
    if ASSAY_HINT_RE.search(raw):
        return _pack("E3", rule="APTABASE_QUALITATIVE_ASSAY", provenance=provenance, affinity=parsed)
    return _pack("E4", rule="APTABASE_SELECTED_APTAMER", provenance=provenance, affinity=parsed)


def propose_utexas_evidence(row: Mapping[str, str]) -> dict[str, str]:
    kd = (row.get("utexas_kd_nm") or "").strip()
    affinity = (row.get("utexas_affinity") or "").strip()
    parsed = parse_affinity_value(kd, unit="nM", affinity_type="Kd") if kd else parse_affinity_from_text(affinity)
    if kd or (parsed.get("affinity_parse_status") in {"normalised", "inequality", "range_or_multiple", "approximate"}):
        return _pack(
            "E2",
            rule="UTEXAS_QUANTITATIVE_KD",
            provenance="utexas_kd_nm|utexas_affinity",
            affinity=parsed,
        )
    if ASSAY_HINT_RE.search(affinity):
        return _pack("E3", rule="UTEXAS_QUALITATIVE_ASSAY", provenance="utexas_affinity", affinity=parsed)
    if (row.get("publication") or row.get("pubmed_id") or "").strip():
        return _pack("E4", rule="UTEXAS_PUBLICATION_SELECTION", provenance="publication", affinity=parsed)
    return _pack("E5", rule="UTEXAS_DATABASE_ANNOTATION", provenance="utexas_affinity", affinity=parsed)


def propose_aptadb_evidence(row: Mapping[str, str]) -> dict[str, str]:
    assay = (row.get("aptadb_aptamer_assay") or "").strip()
    buffer = (row.get("aptadb_binding_conditions_buffer") or "").strip()
    pmid = (row.get("aptadb_reference_pubmed_id") or "").strip()
    notes = "buffer_is_provenance_only=true"
    parsed = parse_affinity_from_text(assay)
    if assay and assay.casefold() not in {"n/a", "na", ""}:
        if parsed.get("affinity_parse_status") == "normalised" or re.search(
            r"(?i)\b(kd|ic50|ec50|ki|nm|µm|um|pm)\b", assay
        ):
            if parsed.get("affinity_parse_status") in {"normalised", "inequality", "range_or_multiple", "approximate"}:
                return _pack(
                    "E2",
                    rule="APTADB_QUANTITATIVE_AFFINITY",
                    provenance="aptadb_aptamer_assay",
                    affinity=parsed,
                    notes=notes,
                )
        if ASSAY_HINT_RE.search(assay) or re.search(r"(?i)\bbinding\b", assay):
            return _pack(
                "E3",
                rule="APTADB_NAMED_BINDING_ASSAY",
                provenance="aptadb_aptamer_assay",
                affinity=parsed,
                notes=notes,
            )
        if pmid:
            return _pack(
                "E4",
                rule="APTADB_TRACEABLE_PUBLICATION",
                provenance="aptadb_aptamer_assay|aptadb_reference_pubmed_id",
                affinity=parsed,
                notes=notes,
            )
        return _pack(
            "E4",
            rule="APTADB_ASSAY_TEXT_SELECTION",
            provenance="aptadb_aptamer_assay",
            affinity=parsed,
            notes=notes,
        )
    if pmid:
        return _pack(
            "E4",
            rule="APTADB_PMID_WITHOUT_ASSAY",
            provenance="aptadb_reference_pubmed_id",
            alternative="E5",
            review=True,
            e4_e5=True,
            notes=notes + ";buffer_not_qualitative_assay=true",
        )
    return _pack(
        "E5",
        rule="APTADB_DATABASE_ONLY",
        provenance="aptadb_binding_conditions_buffer",
        notes=notes + ";buffer_not_qualitative_assay=true",
        affinity=parsed,
    )


def propose_riboaptamer_evidence(row: Mapping[str, str]) -> dict[str, str]:
    kd = (row.get("riboaptamer_affinity_kd") or "").strip()
    mmcif = (row.get("riboaptamer_mmcif_download_url") or "").strip()
    parsed = parse_affinity_from_text(kd) if kd and kd.casefold() not in {"n/a", "na"} else parse_affinity_value("")
    structural = "not_evaluated"
    if mmcif and mmcif.casefold() not in {"n/a", "na", ""}:
        # URL presence is not E1; do not send deterministic E2/E4 rows to review.
        structural = "mmcif_url_present_complex_not_verified"
    if parsed.get("affinity_parse_status") in {"normalised", "inequality", "range_or_multiple", "approximate"} and kd.casefold() not in {"n/a", "na", ""}:
        return _pack(
            "E2",
            rule="RIBOAPTAMER_QUANTITATIVE_KD",
            provenance="riboaptamer_affinity_kd",
            affinity=parsed,
            structural=structural,
        )
    if (row.get("riboaptamer_pubmed_link") or row.get("pubmed_id") or "").strip():
        return _pack(
            "E4",
            rule="RIBOAPTAMER_PUBLICATION_SELECTION",
            provenance="riboaptamer_pubmed_link",
            affinity=parsed,
            structural=structural,
        )
    return _pack(
        "E4",
        rule="RIBOAPTAMER_DATABASE_SELECTED_APTAMER",
        provenance="riboaptamer_source",
        alternative="E5",
        review=True,
        e4_e5=True,
        structural=structural,
        affinity=parsed,
    )


def propose_aptaindex_evidence(row: Mapping[str, str]) -> dict[str, str]:
    aff_type = (row.get("aptaindex_affinity_type") or "").strip()
    aff = (row.get("aptaindex_affinity") or "").strip()
    unit = (row.get("aptaindex_affinity_units") or "").strip()
    parsed = parse_affinity_value(aff, unit=unit, affinity_type=aff_type)
    if aff_type.casefold() == "lod":
        parsed["affinity_type_proposed"] = "other"
        parsed["affinity_parse_status"] = "lod_not_binding_affinity"
        parsed["affinity_value_molar_proposed"] = ""
        parsed["affinity_requires_review"] = "true"
        if (row.get("publication") or row.get("aptaindex_reference") or "").strip():
            return _pack(
                "E4",
                rule="APTAINDEX_LOD_NOT_E2",
                provenance="aptaindex_affinity_type",
                affinity=parsed,
            )
        return _pack("E5", rule="APTAINDEX_LOD_ANNOTATION", provenance="aptaindex_affinity_type", affinity=parsed)
    if parsed.get("affinity_parse_status") in {"normalised", "inequality", "range_or_multiple", "approximate"}:
        return _pack(
            "E2",
            rule="APTAINDEX_QUANTITATIVE_AFFINITY",
            provenance="aptaindex_affinity_type|aptaindex_affinity",
            affinity=parsed,
        )
    if ASSAY_HINT_RE.search(aff):
        return _pack("E3", rule="APTAINDEX_QUALITATIVE_ASSAY", provenance="aptaindex_affinity", affinity=parsed)
    if (row.get("publication") or row.get("aptaindex_reference") or "").strip():
        return _pack("E4", rule="APTAINDEX_TRACEABLE_SELECTION", provenance="aptaindex_reference", affinity=parsed)
    return _pack("E5", rule="APTAINDEX_ANNOTATION_ONLY", provenance="aptaindex_affinity", affinity=parsed)


def propose_ena_evidence(row: Mapping[str, str]) -> dict[str, str]:
    label = (row.get("ena_source_binding_evidence_type") or "").strip()
    strength = (row.get("binding_evidence_strength") or "").strip()
    if label == "explicit_binding_claim" or label == "functional_or_inhibitory_claim":
        return _pack(
            "E3",
            rule="ENA_EXPLICIT_BINDING_OR_INHIBITION",
            provenance="ena_source_binding_evidence_type",
            notes=f"ena_binding_evidence_strength={strength}",
        )
    if label == "selection_against_target":
        return _pack(
            "E4",
            rule="ENA_SELECTION_AGAINST_TARGET",
            provenance="ena_source_binding_evidence_type",
        )
    if label == "target_specific_aptamer_claim":
        return _pack(
            "E5",
            rule="ENA_TARGET_SPECIFIC_CLAIM",
            provenance="ena_source_binding_evidence_type",
            alternative="E4",
            review=True,
            e4_e5=True,
            notes="ena_target_specific_claim_not_automatic_e4",
        )
    return _pack(
        "E5",
        rule="ENA_UNLABELLED_DATABASE",
        provenance="ena_source_binding_evidence_type",
        alternative="E4",
        review=True,
        e4_e5=True,
    )


def propose_aptamerbase_evidence(
    row: Mapping[str, str],
    graph: AptamerBaseEvidenceGraph | None,
) -> dict[str, str]:
    apt_id = (row.get("aptamerbase_id") or "").strip()
    structure_flag = (row.get("aptamerbase_has_experimentally_determined_structure") or "").strip().casefold()
    structural = "boolean_structure_flag_not_e1"
    if structure_flag in {"true", "1", "yes"}:
        structural = "has_experimentally_determined_structure_true_not_verified_complex"
    interactions = set()
    kd_texts: list[str] = []
    has_selex = False
    has_affinity_exp = False
    if graph is not None and apt_id:
        interactions = set(graph.is_participant_in.get(apt_id, set()))
        for interaction in sorted(interactions):
            for kd_node in sorted(graph.has_kd.get(interaction, set())):
                kd_texts.extend(graph.kd_values.get(kd_node, []))
            for confirm in sorted(graph.confirmed_by.get(interaction, set())):
                types = graph.types.get(confirm, set())
                if TYPE_SELEX in types or graph.selex_methods.get(confirm):
                    has_selex = True
                if TYPE_AFFINITY in types or graph.affinity_methods.get(confirm):
                    has_affinity_exp = True
    kd_texts = [item for item in dict.fromkeys(kd_texts) if item]
    parsed = parse_affinity_from_text(kd_texts[0]) if kd_texts else parse_affinity_value("")
    if kd_texts:
        parsed["affinity_value_raw"] = join_unique(kd_texts)
        if len(kd_texts) > 1:
            parsed["affinity_parse_status"] = "range_or_multiple"
            parsed["affinity_value_molar_proposed"] = ""
            parsed["affinity_requires_review"] = "true"
        return _pack(
            "E2",
            rule="APTAMERBASE_INTERACTION_KD",
            provenance="rdf:interaction.has_dissociation_constant",
            affinity=parsed,
            structural=structural,
        )
    if has_affinity_exp:
        return _pack(
            "E3",
            rule="APTAMERBASE_AFFINITY_EXPERIMENT",
            provenance="rdf:affinity_experiment.confirms",
            structural=structural,
            affinity=parsed,
        )
    if has_selex:
        return _pack(
            "E4",
            rule="APTAMERBASE_SELEX_EXPERIMENT",
            provenance="rdf:selex_experiment",
            structural=structural,
            affinity=parsed,
        )
    if interactions:
        return _pack(
            "E5",
            rule="APTAMERBASE_INTERACTION_ONLY",
            provenance="rdf:interaction.has_participant",
            structural=structural,
            affinity=parsed,
        )
    return _pack(
        "E5",
        rule="APTAMERBASE_DATABASE_ANNOTATION",
        provenance="aptamerbase_label",
        structural=structural,
        affinity=parsed,
    )


def propose_ncbi_evidence(row: Mapping[str, str]) -> dict[str, str]:
    definition = (row.get("ncbi_nuc_definition") or "").strip()
    comment = (row.get("ncbi_nuc_comment") or "").strip()
    features = (row.get("ncbi_nuc_features_json") or "").strip()
    blob = " ".join([definition, comment, features])
    accession = (row.get("ncbi_nuc_accession") or row.get("native_id") or "").strip()
    if ASSAY_HINT_RE.search(blob):
        return _pack(
            "E3",
            rule="NCBI_EXPLICIT_BINDING_ASSAY",
            provenance="ncbi_nuc_definition|ncbi_nuc_features_json",
            notes=f"accession={accession}",
        )
    if SELECTION_HINT_RE.search(blob) or re.search(r"(?i)\b(binds to|specific for|binding RNA aptamer)\b", blob):
        review = accession == "BD161067"
        return _pack(
            "E4",
            rule="NCBI_EXPLICIT_BINDING_OR_SELECTION_LANGUAGE",
            provenance="ncbi_nuc_definition|ncbi_nuc_features_json",
            review=review,
            notes=f"accession={accession}",
        )
    if (row.get("ncbi_nuc_references_json") or row.get("publication") or "").strip():
        return _pack(
            "E5",
            rule="NCBI_PUBLICATION_ONLY",
            provenance="ncbi_nuc_references_json",
            alternative="E4",
            review=True,
            e4_e5=True,
            notes=f"accession={accession};publication_alone_not_e4",
        )
    return _pack(
        "E5",
        rule="NCBI_ANNOTATION_ONLY",
        provenance="ncbi_nuc_definition",
        alternative="E4",
        review=True,
        e4_e5=True,
        notes=f"accession={accession}",
    )


def propose_evidence(
    row: Mapping[str, str],
    *,
    aptabase_sidecar: Mapping[str, str] | None = None,
    aptamerbase_graph: AptamerBaseEvidenceGraph | None = None,
) -> dict[str, str]:
    source = (row.get("source_db") or "").strip()
    if source == "aptabase":
        return propose_aptabase_evidence(sidecar=aptabase_sidecar or {}, row=row)
    if source == "utexas":
        return propose_utexas_evidence(row)
    if source == "aptadb":
        return propose_aptadb_evidence(row)
    if source == "riboaptamer":
        return propose_riboaptamer_evidence(row)
    if source == "aptaindex":
        return propose_aptaindex_evidence(row)
    if source == "ena":
        return propose_ena_evidence(row)
    if source == "aptamerbase":
        return propose_aptamerbase_evidence(row, aptamerbase_graph)
    if source == "ncbi_nuc":
        return propose_ncbi_evidence(row)
    return _pack("E5", rule="UNKNOWN_SOURCE_DATABASE_ONLY", provenance=source)

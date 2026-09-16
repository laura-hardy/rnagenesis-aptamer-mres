#!/usr/bin/env python3
"""Milestone 3: scientific proposals and CHECKPOINT-2 preparation.

Reads the immutable combined pre-S4 input and Milestone-2 target artefacts.
Writes proposal/review tables only. Does not apply canonical S4 fields,
human decisions, leakage exclusions, or S5.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s4_evidence import load_aptamerbase_evidence_graph, propose_evidence  # noqa: E402
from adapters.s4_family_pfam import propose_family, region_or_fragment  # noqa: E402
from adapters.s4_leakage_proposal import load_leakage_resources, propose_leakage  # noqa: E402
from adapters.s4_routing import routing_preview  # noqa: E402
from adapters.s4_scientific_common import (  # noqa: E402
    CANONICAL_FIELDS_MUST_STAY_EMPTY,
    ENRICHED_DICTIONARY_COLUMNS,
    EVIDENCE_AFFINITY_COLUMNS,
    HUMAN_FIELDS,
    LEAKAGE_PROPOSAL_COLUMNS,
    RELATIONSHIP_SCIENTIFIC_COLUMNS,
    ROUTING_PREVIEW_COLUMNS,
    ScientificProposalError,
    assert_combined_canonical_empty,
    assert_no_sequence_leak,
    bool_token,
    fill_row,
    join_unique,
    primary_match_key,
    write_json_atomic,
    write_text_atomic,
)
from adapters.s4_target_type import map_source_type_prior, merge_dictionary_type_priors  # noqa: E402
from adapters.s4_uniprot import (  # noqa: E402
    build_local_uniprot_index,
    load_aptadb_protein_table,
    resolve_uniprot,
)
from adapters.target_extraction_common import DICTIONARY_COLUMNS  # noqa: E402
from checkpoint2_prepare_review import prepare_checkpoint2_package  # noqa: E402
from checkpoint2_validate_review import validate_checkpoint2_package  # noqa: E402
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402
from extract_global_s4_targets import load_aptabase_sidecar  # noqa: E402
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402


@dataclass(frozen=True)
class ScientificProposalResult:
    n_dictionary: int
    n_relationships: int
    n_records: int
    combined_sha256: str
    hashes: Mapping[str, str]
    validator_ready: bool
    output_dir: Path


def _resolve(repo_root: Path, path: Path | str) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        return [{key: row.get(key, "") or "" for key in fields} for row in reader]


def _assert_output(repo_root: Path, output_path: Path | str) -> Path:
    resolved = _resolve(repo_root, output_path)
    interim = (repo_root / "data" / "interim").resolve()
    try:
        resolved.relative_to(interim)
    except ValueError as exc:
        raise ScientificProposalError(
            f"Proposal output must lie beneath data/interim/: {output_path}"
        ) from exc
    if resolved.name == "combined_global_s4_input.csv":
        raise ScientificProposalError("Refusing to write into the combined input CSV")
    return resolved


def _dictionary_lookup_key(raw_target: str, uniprot_seed: str) -> tuple[str, str]:
    return primary_match_key(raw_target), (uniprot_seed or "").strip()


def _machine_recommendation(*, review: bool, reason: str) -> str:
    if not review:
        return "accept_machine_proposal"
    if "uniprot" in reason:
        return "review_uniprot_ambiguity"
    if "type" in reason:
        return "review_target_type"
    if "relationship" in reason or "multi" in reason:
        return "review_relationship"
    return "review_required"


def build_summary(
    *,
    repo_root: Path,
    combined_sha256: str,
    dictionary_rows: Sequence[Mapping[str, str]],
    rel_rows: Sequence[Mapping[str, str]],
    evidence_rows: Sequence[Mapping[str, str]],
    leakage_rows: Sequence[Mapping[str, str]],
    routing_rows: Sequence[Mapping[str, str]],
    checkpoint2: Mapping[str, Any],
    validator: Mapping[str, Any],
    hashes: Mapping[str, str],
    ribo_audit: Mapping[str, Any],
) -> str:
    type_counts = Counter(row.get("target_type_proposed", "") for row in dictionary_rows)
    type_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rel_rows:
        type_by_source[row.get("source_db", "")][row.get("target_type_proposed", "")] += 1
    uniprot_tier = Counter(row.get("uniprot_resolution_tier", "") for row in dictionary_rows)
    family_counts = Counter(row.get("target_family_proposed", "") for row in dictionary_rows)
    pfam_n = sum(1 for row in dictionary_rows if (row.get("target_pfam_proposed") or "").strip())
    evidence_levels = Counter(row.get("evidence_level_proposed", "") for row in evidence_rows)
    evidence_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for row in evidence_rows:
        evidence_by_source[row.get("source_db", "")][row.get("evidence_level_proposed", "")] += 1
    aff_status = Counter(row.get("affinity_parse_status", "") for row in evidence_rows)
    routing_counts = Counter(row.get("routing_preview", "") for row in routing_rows)
    leak_seq = Counter(row.get("sequence_match_kind", "") for row in leakage_rows)
    lines = [
        "# Global-S4 Milestone 3 — scientific proposals and CHECKPOINT-2 preparation",
        "",
        "Machine proposals only. Combined input was not modified. Human",
        "CHECKPOINT-2 fields are blank. Leakage, evidence, and routing were not applied.",
        "",
        "## Integrity",
        "",
        f"- combined SHA-256: `{combined_sha256}`",
        f"- dictionary proposals: `{len(dictionary_rows)}`",
        f"- relationship scientific rows: `{len(rel_rows)}`",
        f"- evidence/affinity rows: `{len(evidence_rows)}`",
        "",
        "## RiboAptamer entry-gate (from regenerated Milestone 2)",
        "",
        f"- single-prefix cohort: `{ribo_audit.get('n_single_prefix_cohort', '')}`",
        f"- corroborated_target_label: `{(ribo_audit.get('classification_counts') or {}).get('corroborated_target_label', 0)}`",
        f"- sequence_name_is_explicit_target_label: `{(ribo_audit.get('classification_counts') or {}).get('sequence_name_is_explicit_target_label', 0)}`",
        f"- conflicting_source_metadata: `{(ribo_audit.get('classification_counts') or {}).get('conflicting_source_metadata', 0)}`",
        f"- insufficient_support: `{(ribo_audit.get('classification_counts') or {}).get('insufficient_support', 0)}`",
        "- Convention: Sequence Name `{target}_{clone}` encodes the ligand in the prefix.",
        "",
        "## Target-type proposals",
        "",
    ]
    for key in ("protein", "peptide", "small_molecule", "ion", "nucleic_acid", "cell", "organism", "other", "unknown"):
        lines.append(f"- `{key}`: `{type_counts.get(key, 0)}`")
    lines.extend(["", "By source (relationship grain):", ""])
    for source, counts in sorted(type_by_source.items()):
        parts = " ".join(f"{key}={counts[key]}" for key in sorted(counts) if counts[key])
        lines.append(f"- `{source}`: {parts}")
    lines.extend(
        [
            "",
            "## UniProt proposals",
            "",
        ]
    )
    for key, value in sorted(uniprot_tier.items()):
        lines.append(f"- `{key or 'blank'}`: `{value}`")
    n_uniprot = sum(1 for row in dictionary_rows if (row.get("uniprot_proposed") or "").strip())
    n_u1 = sum(1 for row in dictionary_rows if row.get("uniprot_resolution_tier") == "U1_source_linked")
    n_u2 = sum(1 for row in dictionary_rows if row.get("uniprot_resolution_tier") == "U2_local_structured")
    n_u3 = sum(1 for row in dictionary_rows if row.get("uniprot_resolution_tier") == "U3_external_lookup" and (row.get("uniprot_proposed") or "").strip())
    n_ambiguous = sum(
        1
        for row in dictionary_rows
        if (row.get("uniprot_ambiguity_reason") or "").strip()
        or (row.get("uniprot_candidates") or "").count("|") >= 1
    )
    lines.extend(
        [
            f"- proposed accessions: `{n_uniprot}`",
            f"- U1 source-seeded: `{n_u1}`",
            f"- U2 local structured: `{n_u2}`",
            f"- U3 external lookup resolved: `{n_u3}`",
            f"- UniProt ambiguities: `{n_ambiguous}`",
            "- AptaDB Prothrombin/Hemagglutinin source-seed collisions remain unmerged.",
            "",
            "## Target family / Pfam",
            "",
        ]
    )
    for key, value in sorted(family_counts.items()):
        lines.append(f"- `{key or 'blank'}`: `{value}`")
    lines.extend(
        [
            f"- Pfam populated: `{pfam_n}` / `{len(dictionary_rows)}`",
            "- Missing Pfam is not an exclusion.",
            "",
            "## Evidence proposals",
            "",
        ]
    )
    for level in ("E1", "E2", "E3", "E4", "E5"):
        lines.append(f"- `{level}`: `{evidence_levels.get(level, 0)}`")
    lines.append(f"- blank/unresolved: `{evidence_levels.get('', 0)}`")
    lines.extend(["", "By source:", ""])
    for source, counts in sorted(evidence_by_source.items()):
        parts = " ".join(f"{key}={counts[key]}" for key in ("E1", "E2", "E3", "E4", "E5") if counts[key])
        lines.append(f"- `{source}`: {parts}")
    n_e4e5 = sum(1 for row in evidence_rows if row.get("e4_e5_threshold_ambiguous") == "true")
    n_e1 = evidence_levels.get("E1", 0)
    lines.extend(
        [
            f"- E4/E5 threshold ambiguities: `{n_e4e5}`",
            f"- automatic E1 assignments: `{n_e1}`",
            "- E1 is assigned only for a verified aptamer–target complex; mmCIF URL or",
            "  structure boolean alone is not E1.",
            "",
            "## Affinity proposals",
            "",
        ]
    )
    for key, value in sorted(aff_status.items()):
        lines.append(f"- `{key or 'blank'}`: `{value}`")
    n_quant = sum(1 for row in evidence_rows if (row.get("affinity_value_raw") or "").strip())
    n_molar = sum(1 for row in evidence_rows if (row.get("affinity_value_molar_proposed") or "").strip())
    n_aff_review = sum(1 for row in evidence_rows if row.get("affinity_requires_review") == "true")
    lines.extend(
        [
            f"- rows with raw affinity text: `{n_quant}`",
            f"- safely normalised molar values: `{n_molar}`",
            f"- affinity review flags: `{n_aff_review}`",
            "",
            "## Leakage proposals",
            "",
            f"- exact sequence: `{leak_seq.get('exact', 0)}`",
            f"- identity ≥0.90: `{leak_seq.get('identity_ge_0.90', 0)}`",
            f"- target alias: `{sum(1 for row in leakage_rows if row.get('target_alias_match') == 'true')}`",
            f"- both sequence and target: `{sum(1 for row in leakage_rows if row.get('both_sequence_and_target') == 'true')}`",
            f"- exclusion proposed: `{sum(1 for row in leakage_rows if row.get('leakage_exclusion_proposed') == 'true')}`",
            f"- review required: `{sum(1 for row in leakage_rows if row.get('requires_review') == 'true')}`",
            "",
            "By source (proposed exclusions):",
            "",
        ]
    )
    leak_source = Counter(
        row.get("source_db", "")
        for row in leakage_rows
        if row.get("leakage_exclusion_proposed") == "true"
    )
    for source, value in sorted(leak_source.items()):
        lines.append(f"- `{source}`: `{value}`")
    lines.extend(["", "## Routing preview (not applied)", ""])
    for key in (
        "primary_candidate",
        "park_non_protein",
        "park_evidence_e5",
        "reject_no_binding_evidence",
        "hold_target_unresolved",
        "hold_evidence_ambiguous",
        "leakage_exclusion_proposed",
    ):
        lines.append(f"- `{key}`: `{routing_counts.get(key, 0)}`")
    cp2_counts = checkpoint2.get("decision_counts") or {}
    lines.extend(
        [
            "",
            "## CHECKPOINT-2 package",
            "",
            f"- target dictionary decisions: `{cp2_counts.get('target', 0)}`",
            f"- relationship decisions: `{cp2_counts.get('relationship', 0)}`",
            f"- evidence decisions: `{cp2_counts.get('evidence', 0)}`",
            f"- affinity decisions: `{cp2_counts.get('affinity', 0)}`",
            f"- leakage decisions: `{cp2_counts.get('leakage', 0)}`",
            f"- affected records (union): `{cp2_counts.get('affected_records', 0)}`",
            f"- validator ready_for_application: `{validator.get('ready_for_application')}`",
            f"- unresolved decisions: `{validator.get('unresolved_decisions')}`",
            "- Human fields are blank. This is not CHECKPOINT-2 completion.",
            "",
            "## Hashes",
            "",
        ]
    )
    for key, digest in hashes.items():
        lines.append(f"- `{key}`: `{digest}`")
    lines.extend(
        [
            "",
            "## Scientific boundary",
            "",
            "- no proposals written into combined input",
            "- no final target/evidence/affinity/leakage application",
            "- no S5 dedup/clustering/balancing/partition",
            "",
        ]
    )
    text = "\n".join(lines) + "\n"
    assert_no_sequence_leak(text, label="scientific proposal summary")
    if str(repo_root.resolve()) in text:
        raise ScientificProposalError("summary must not contain absolute repository paths")
    return text


def propose_global_s4_scientific(
    *,
    proposal_config: Path,
    repo_root: Path | None = None,
    allow_uniprot_network: bool | None = None,
) -> ScientificProposalResult:
    root = repo_root or find_repo_root()
    config = json.loads(_resolve(root, proposal_config).read_text(encoding="utf-8"))
    combined_path = _resolve(root, config["combined_input_csv"])
    before = sha256_file(combined_path)
    if before != config["expected_combined_sha256"]:
        raise ScientificProposalError("Combined input SHA-256 does not match the accepted invariant")

    combined_rows = _read_csv(combined_path)
    if len(combined_rows) != int(config["expected_combined_records"]):
        raise ScientificProposalError("Combined input row count mismatch")
    for row in combined_rows:
        assert_combined_canonical_empty(row)

    extraction_rows = _read_csv(_resolve(root, config["target_extraction_record_csv"]))
    relationship_rows = _read_csv(_resolve(root, config["target_relationship_csv"]))
    dictionary_rows = _read_csv(_resolve(root, config["target_dictionary_csv"]))
    combined_by_id = {row["record_id"]: row for row in combined_rows}
    extraction_by_id = {row["record_id"]: row for row in extraction_rows}
    if [row["record_id"] for row in extraction_rows] != [row["record_id"] for row in combined_rows]:
        raise ScientificProposalError("Extraction table record_id order does not match combined input")

    aptabase_ids = [row["record_id"] for row in combined_rows if row["source_db"] == "aptabase"]
    aptabase_sidecar = load_aptabase_sidecar(
        _resolve(root, config["aptabase_source_metadata"]),
        authorised_ids=aptabase_ids,
    ) if aptabase_ids else {}

    protein_path = _resolve(root, config["aptadb_protein_csv"])
    local_index = build_local_uniprot_index(load_aptadb_protein_table(protein_path))
    rdf_path = _resolve(root, config["aptamerbase_rdf"])
    expected_rdf = str(config.get("expected_aptamerbase_rdf_sha256") or "")
    if expected_rdf and sha256_file(rdf_path) != expected_rdf:
        raise ScientificProposalError("AptamerBase RDF SHA-256 mismatch")
    ab_graph = load_aptamerbase_evidence_graph(rdf_path)
    leak_index, alias_rules = load_leakage_resources(
        exclusion_set=_resolve(root, config["leakage_exclusion_set"]),
        alias_csv=_resolve(root, config["leakage_target_aliases"]),
    )
    cache_dir = _resolve(root, config["uniprot_cache_dir"])
    network = config.get("allow_uniprot_network", False) if allow_uniprot_network is None else allow_uniprot_network

    dict_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in dictionary_rows:
        dict_by_key[_dictionary_lookup_key(row["raw_target"].split("|")[0], row.get("source_uniprot_seed", ""))] = row
        dict_by_key[(row["primary_match_key"], (row.get("source_uniprot_seed") or "").strip())] = row

    extraction_manifest = json.loads(
        _resolve(root, "data/interim/global_s4/target_extraction_manifest.json").read_text(encoding="utf-8")
    )
    ribo_audit = (extraction_manifest.get("riboaptamer_inspection") or {}).get("seq_first_underscore_audit") or {}

    # Evidence per record (source-level; reused across relationships).
    evidence_by_record: dict[str, dict[str, str]] = {}
    for row in combined_rows:
        evidence_by_record[row["record_id"]] = propose_evidence(
            row,
            aptabase_sidecar=aptabase_sidecar.get(row["record_id"]),
            aptamerbase_graph=ab_graph,
        )

    # Enrich dictionary.
    rels_by_dict: dict[str, list[dict[str, str]]] = defaultdict(list)
    for rel in relationship_rows:
        extraction = extraction_by_id[rel["record_id"]]
        key = (primary_match_key(rel["raw_target"]), (rel.get("source_uniprot_seed") or extraction.get("source_uniprot_seed") or "").strip())
        drow = dict_by_key.get(key)
        if drow is None:
            drow = dict_by_key.get((primary_match_key(rel["raw_target"]), ""))
        if drow is not None:
            rels_by_dict[drow["target_dictionary_id"]].append(rel)

    enriched_dictionary: list[dict[str, str]] = []
    dict_enriched_by_id: dict[str, dict[str, str]] = {}
    for row in dictionary_rows:
        source_priors_map: dict[str, str] = {}
        for rel in rels_by_dict.get(row["target_dictionary_id"], []):
            extraction = extraction_by_id[rel["record_id"]]
            source_priors_map[extraction["source_db"]] = extraction.get(
                "source_target_type_prior", ""
            )
        if len(source_priors_map) == 1:
            source_db, prior = next(iter(source_priors_map.items()))
            accession = ""
            if source_db == "ncbi_nuc" and rels_by_dict.get(row["target_dictionary_id"]):
                accession = combined_by_id[
                    rels_by_dict[row["target_dictionary_id"]][0]["record_id"]
                ].get("ncbi_nuc_accession", "")
            type_result = map_source_type_prior(source_db, prior, accession=accession)
        elif source_priors_map:
            type_result = merge_dictionary_type_priors(source_priors_map)
        else:
            type_result = map_source_type_prior(
                (row.get("source_keys") or "").split("|")[0],
                row.get("source_target_type_priors") or "",
            )

        uniprot = resolve_uniprot(
            raw_target=row.get("canonical_target_name_proposal") or row.get("raw_target") or "",
            source_uniprot_seed=row.get("source_uniprot_seed") or "",
            target_type=type_result["target_type_proposed"],
            local_index=local_index,
            cache_dir=cache_dir,
            api_base=str(config.get("uniprot_api_base") or ""),
            api_version=str(config.get("uniprot_api_version") or ""),
            allow_network=bool(network),
        )
        family = propose_family(
            target_type=type_result["target_type_proposed"],
            family_clues=[type_result.get("family_clue", "")],
            uniprot_family_clue=uniprot.get("family_clue_from_uniprot", ""),
        )
        region = region_or_fragment(row.get("canonical_target_name_proposal") or "")
        review_reasons = [
            item
            for item in [
                type_result.get("type_conflict_reason"),
                uniprot.get("uniprot_ambiguity_reason"),
                family.get("family_conflict_reason", ""),
                "target_region_or_fragment"
                if region == "true" and uniprot.get("uniprot_proposed")
                else "",
                row.get("ambiguity_flags")
                if row.get("requires_checkpoint2") == "true"
                else "",
            ]
            if item
        ]
        requires = (
            row.get("requires_checkpoint2") == "true"
            or type_result.get("type_requires_review") == "true"
            or uniprot.get("uniprot_requires_review") == "true"
            or family.get("family_requires_review") == "true"
            or (region == "true" and bool(uniprot.get("uniprot_proposed")))
        )
        enriched = {column: row.get(column, "") for column in DICTIONARY_COLUMNS}
        provenance = join_unique(
            [
                f"type={type_result['target_type_source_proposed']}",
                f"uniprot={uniprot.get('uniprot_resolution_tier')}",
                f"family={family.get('target_family_source')}",
            ]
        )
        enriched.update(
            {
                "target_type_proposed": type_result["target_type_proposed"],
                "target_type_source_proposed": type_result["target_type_source_proposed"],
                "target_type_confidence": type_result["target_type_confidence"],
                "uniprot_proposed": uniprot.get("uniprot_proposed", ""),
                "uniprot_candidates": uniprot.get("uniprot_candidates", ""),
                "uniprot_resolution_tier": uniprot.get("uniprot_resolution_tier", ""),
                "uniprot_query": uniprot.get("uniprot_query", ""),
                "uniprot_organism_context": uniprot.get("uniprot_organism_context", ""),
                "uniprot_ambiguity_reason": uniprot.get("uniprot_ambiguity_reason", ""),
                "target_family_proposed": family.get("target_family_proposed", ""),
                "target_family_source": family.get("target_family_source", ""),
                "target_pfam_proposed": uniprot.get("pfam_from_uniprot", ""),
                "target_interpro_proposed": uniprot.get("interpro_from_uniprot", ""),
                "target_region_or_fragment": region,
                "resolution_provenance": provenance,
                "machine_recommendation": _machine_recommendation(
                    review=requires, reason=";".join(review_reasons)
                ),
                "scientific_ambiguity_reason": join_unique(review_reasons),
                "requires_checkpoint2": bool_token(requires),
                "review_status": "machine_proposed",
            }
        )
        filled = fill_row(ENRICHED_DICTIONARY_COLUMNS, enriched)
        enriched_dictionary.append(filled)
        dict_enriched_by_id[row["target_dictionary_id"]] = filled

    # Relationship scientific rows + evidence table + leakage + routing.
    scientific_rels: list[dict[str, str]] = []
    evidence_rows_out: list[dict[str, str]] = []
    leakage_rows_out: list[dict[str, str]] = []
    routing_rows_out: list[dict[str, str]] = []

    rels_by_record: dict[str, list[dict[str, str]]] = defaultdict(list)
    for rel in relationship_rows:
        rels_by_record[rel["record_id"]].append(rel)

    for combined in combined_rows:
        record_id = combined["record_id"]
        extraction = extraction_by_id[record_id]
        evidence = evidence_by_record[record_id]
        rels = rels_by_record.get(record_id) or []
        target_texts = [extraction.get("effective_target_raw") or "", extraction.get("extracted_target_raw") or ""]
        target_texts.extend(rel.get("raw_target", "") for rel in rels)
        leakage = propose_leakage(
            combined,
            index=leak_index,
            rules=alias_rules,
            target_texts=target_texts,
        )
        leakage_rows_out.append(fill_row(LEAKAGE_PROPOSAL_COLUMNS, leakage))

        if not rels:
            type_result = map_source_type_prior(
                combined["source_db"],
                extraction.get("source_target_type_prior") or "",
                accession=combined.get("ncbi_nuc_accession") or "",
            )
            routing, reason = routing_preview(
                relationship_status=extraction.get("relationship_status") or "unresolved",
                target_type=type_result["target_type_proposed"],
                evidence_level=evidence.get("evidence_level_proposed") or "",
                evidence_ambiguous=evidence.get("e4_e5_threshold_ambiguous") == "true",
                leakage_proposed=leakage.get("leakage_exclusion_proposed") == "true",
                no_binding=not evidence.get("evidence_level_proposed"),
            )
            routing_rows_out.append(
                fill_row(
                    ROUTING_PREVIEW_COLUMNS,
                    {
                        "record_id": record_id,
                        "source_db": combined["source_db"],
                        "relationship_status": extraction.get("relationship_status", ""),
                        "n_target_relationships_proposed": extraction.get("n_target_relationships_proposed", "0"),
                        "record_expansion_proposed": extraction.get("record_expansion_proposed", "false"),
                        "target_type_proposed": type_result["target_type_proposed"],
                        "evidence_level_proposed": evidence.get("evidence_level_proposed", ""),
                        "leakage_exclusion_proposed": leakage.get("leakage_exclusion_proposed", "false"),
                        "routing_preview": routing,
                        "routing_reason": reason,
                        "requires_checkpoint2": extraction.get("requires_checkpoint2", "false"),
                    },
                )
            )
            evidence_rows_out.append(
                fill_row(
                    EVIDENCE_AFFINITY_COLUMNS,
                    {
                        **evidence,
                        "record_id": record_id,
                        "relationship_index": "",
                        "source_db": combined["source_db"],
                    },
                )
            )
            continue

        record_types: list[str] = []
        record_levels: list[str] = []
        record_review = extraction.get("requires_checkpoint2") == "true"
        for rel in rels:
            key = (
                primary_match_key(rel["raw_target"]),
                (rel.get("source_uniprot_seed") or extraction.get("source_uniprot_seed") or "").strip(),
            )
            drow = dict_by_key.get(key) or dict_by_key.get((key[0], ""))
            enriched = dict_enriched_by_id.get(drow["target_dictionary_id"]) if drow else None
            type_result = map_source_type_prior(
                combined["source_db"],
                extraction.get("source_target_type_prior") or "",
                accession=combined.get("ncbi_nuc_accession") or "",
            )
            if enriched and enriched.get("target_type_proposed") not in {"", "unknown"}:
                # Prefer dictionary identity when source prior is empty (UTexas).
                if type_result["target_type_proposed"] == "unknown":
                    type_result["target_type_proposed"] = enriched["target_type_proposed"]
                    type_result["target_type_source_proposed"] = enriched["target_type_source_proposed"]
            uniprot_proposed = (enriched or {}).get("uniprot_proposed", "")
            family_proposed = (enriched or {}).get("target_family_proposed", "")
            if type_result.get("type_conflict_reason") and enriched:
                type_result["type_requires_review"] = "true"
            scientific = fill_row(
                RELATIONSHIP_SCIENTIFIC_COLUMNS,
                {
                    "record_id": record_id,
                    "relationship_index": rel.get("relationship_index", ""),
                    "source_db": combined["source_db"],
                    "target_dictionary_id": (drow or {}).get("target_dictionary_id", ""),
                    "raw_target": rel.get("raw_target", ""),
                    "relationship_status": extraction.get("relationship_status", ""),
                    "record_expansion_proposed": extraction.get("record_expansion_proposed", "false"),
                    "target_type_proposed": type_result["target_type_proposed"],
                    "target_type_source_proposed": type_result["target_type_source_proposed"],
                    "uniprot_proposed": uniprot_proposed,
                    "target_family_proposed": family_proposed,
                    "target_pfam_proposed": (enriched or {}).get("target_pfam_proposed", ""),
                    "target_region_or_fragment": region_or_fragment(rel.get("raw_target") or ""),
                    "evidence_level_proposed": evidence.get("evidence_level_proposed", ""),
                    "evidence_type_proposed": evidence.get("evidence_type_proposed", ""),
                    "evidence_score_proposed": evidence.get("evidence_score_proposed", ""),
                    "evidence_rule": evidence.get("evidence_rule", ""),
                    "evidence_provenance": evidence.get("evidence_provenance", ""),
                    "alternative_evidence_level": evidence.get("alternative_evidence_level", ""),
                    "evidence_requires_review": evidence.get("evidence_requires_review", "false"),
                    "affinity_type_proposed": evidence.get("affinity_type_proposed", ""),
                    "affinity_value_raw": evidence.get("affinity_value_raw", ""),
                    "affinity_unit_raw": evidence.get("affinity_unit_raw", ""),
                    "affinity_value_molar_proposed": evidence.get("affinity_value_molar_proposed", ""),
                    "affinity_parse_status": evidence.get("affinity_parse_status", ""),
                    "affinity_parse_rule": evidence.get("affinity_parse_rule", ""),
                    "affinity_requires_review": evidence.get("affinity_requires_review", "false"),
                    "routing_preview": "",
                    "leakage_match_kind": leakage.get("sequence_match_kind", ""),
                    "requires_checkpoint2": bool_token(
                        record_review
                        or type_result.get("type_requires_review") == "true"
                        or (enriched or {}).get("requires_checkpoint2") == "true"
                    ),
                    "notes": join_unique(
                        [
                            extraction.get("notes", ""),
                            type_result.get("type_conflict_reason", ""),
                        ]
                    ),
                },
            )
            scientific_rels.append(scientific)
            evidence_rows_out.append(
                fill_row(
                    EVIDENCE_AFFINITY_COLUMNS,
                    {
                        **evidence,
                        "record_id": record_id,
                        "relationship_index": rel.get("relationship_index", ""),
                        "source_db": combined["source_db"],
                    },
                )
            )
            record_types.append(type_result["target_type_proposed"])
            record_levels.append(evidence.get("evidence_level_proposed", ""))

        # Record-level routing uses the strongest/most conservative preview.
        leakage_proposed = leakage.get("leakage_exclusion_proposed") == "true"
        status = extraction.get("relationship_status") or "unresolved"
        type_for_route = record_types[0] if len(set(record_types)) == 1 else (
            "unknown" if record_types else "unknown"
        )
        if len(set(record_types)) > 1:
            record_review = True
        evidence_level = record_levels[0] if record_levels else evidence.get("evidence_level_proposed", "")
        routing, reason = routing_preview(
            relationship_status=status,
            target_type=type_for_route,
            evidence_level=evidence_level,
            evidence_ambiguous=evidence.get("e4_e5_threshold_ambiguous") == "true",
            leakage_proposed=leakage_proposed,
            no_binding=not evidence_level,
        )
        if scientific_rels:
            for item in scientific_rels[-len(rels):]:
                if item["record_id"] == record_id:
                    item["routing_preview"] = routing
        routing_rows_out.append(
            fill_row(
                ROUTING_PREVIEW_COLUMNS,
                {
                    "record_id": record_id,
                    "source_db": combined["source_db"],
                    "relationship_status": status,
                    "n_target_relationships_proposed": extraction.get("n_target_relationships_proposed", "0"),
                    "record_expansion_proposed": extraction.get("record_expansion_proposed", "false"),
                    "target_type_proposed": type_for_route,
                    "evidence_level_proposed": evidence_level,
                    "leakage_exclusion_proposed": leakage.get("leakage_exclusion_proposed", "false"),
                    "routing_preview": routing,
                    "routing_reason": reason,
                    "requires_checkpoint2": bool_token(record_review),
                },
            )
        )

    outputs = config["outputs"]
    out_dict = _assert_output(root, outputs["enriched_dictionary_csv"])
    out_rel = _assert_output(root, outputs["relationship_scientific_csv"])
    out_ev = _assert_output(root, outputs["evidence_affinity_csv"])
    out_leak = _assert_output(root, outputs["leakage_proposal_csv"])
    out_route = _assert_output(root, outputs["routing_preview_csv"])
    out_summary = _assert_output(root, outputs["summary"])
    out_manifest = _assert_output(root, outputs["manifest"])
    cp2_dir = _assert_output(root, outputs["checkpoint2_dir"])

    write_corpus_csv_atomic(out_dict, enriched_dictionary, columns=ENRICHED_DICTIONARY_COLUMNS)
    write_corpus_csv_atomic(out_rel, scientific_rels, columns=RELATIONSHIP_SCIENTIFIC_COLUMNS)
    write_corpus_csv_atomic(out_ev, evidence_rows_out, columns=EVIDENCE_AFFINITY_COLUMNS)
    write_corpus_csv_atomic(out_leak, leakage_rows_out, columns=LEAKAGE_PROPOSAL_COLUMNS)
    write_corpus_csv_atomic(out_route, routing_rows_out, columns=ROUTING_PREVIEW_COLUMNS)

    cp2_result = prepare_checkpoint2_package(
        repo_root=root,
        output_dir=cp2_dir,
        dictionary_rows=enriched_dictionary,
        relationship_rows=scientific_rels,
        extraction_rows=extraction_rows,
        evidence_rows=evidence_rows_out,
        leakage_rows=leakage_rows_out,
        routing_rows=routing_rows_out,
    )
    validator = validate_checkpoint2_package(cp2_dir)

    after = sha256_file(combined_path)
    if after != before:
        raise ScientificProposalError("Combined input was modified during scientific proposal generation")
    for field in CANONICAL_FIELDS_MUST_STAY_EMPTY:
        nonempty = sum(1 for row in _read_csv(combined_path) if (row.get(field) or "").strip())
        if nonempty:
            raise ScientificProposalError(f"Combined input canonical {field} became populated")

    hashes = {
        "combined_input": before,
        "enriched_dictionary": sha256_file(out_dict),
        "relationship_scientific": sha256_file(out_rel),
        "evidence_affinity": sha256_file(out_ev),
        "leakage_proposals": sha256_file(out_leak),
        "routing_preview": sha256_file(out_route),
    }
    for name in sorted(p.name for p in cp2_dir.iterdir() if p.is_file()):
        hashes[f"checkpoint2/{name}"] = sha256_file(cp2_dir / name)

    summary = build_summary(
        repo_root=root,
        combined_sha256=before,
        dictionary_rows=enriched_dictionary,
        rel_rows=scientific_rels,
        evidence_rows=evidence_rows_out,
        leakage_rows=leakage_rows_out,
        routing_rows=routing_rows_out,
        checkpoint2=cp2_result,
        validator=validator,
        hashes=hashes,
        ribo_audit=ribo_audit,
    )
    write_text_atomic(out_summary, summary)
    hashes["summary"] = sha256_file(out_summary)
    manifest = {
        "contract_id": config.get("contract_id"),
        "milestone": config.get("milestone"),
        "combined_records": len(combined_rows),
        "dictionary_rows": len(enriched_dictionary),
        "relationship_scientific_rows": len(scientific_rels),
        "evidence_affinity_rows": len(evidence_rows_out),
        "leakage_rows": len(leakage_rows_out),
        "routing_rows": len(routing_rows_out),
        "checkpoint2": cp2_result,
        "validator": validator,
        "hashes": hashes,
        "scientific_boundary": config.get("scientific_boundary") or {},
        "uniprot_network_used": bool(network),
        "human_fields": list(HUMAN_FIELDS),
    }
    manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    assert_no_sequence_leak(manifest_text, label="scientific proposal manifest")
    write_text_atomic(out_manifest, manifest_text)
    hashes["manifest"] = sha256_file(out_manifest)
    write_json_atomic(out_manifest, {**manifest, "hashes": hashes})

    return ScientificProposalResult(
        n_dictionary=len(enriched_dictionary),
        n_relationships=len(scientific_rels),
        n_records=len(combined_rows),
        combined_sha256=before,
        hashes=hashes,
        validator_ready=bool(validator.get("ready_for_application")),
        output_dir=out_dict.parent,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Propose target type/UniProt/family/evidence/affinity/leakage and "
            "prepare a blank CHECKPOINT-2 package. Does not modify combined input."
        )
    )
    parser.add_argument(
        "--proposal-config",
        type=Path,
        required=True,
        help="Repo-relative Milestone-3 scientific-proposal contract JSON",
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument(
        "--allow-uniprot-network",
        action="store_true",
        help="Permit UniProt REST lookups (cached). Default follows config.",
    )
    parser.add_argument(
        "--disable-uniprot-network",
        action="store_true",
        help="Force UniProt lookups to use cache only.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    network = None
    if args.disable_uniprot_network:
        network = False
    elif args.allow_uniprot_network:
        network = True
    result = propose_global_s4_scientific(
        proposal_config=args.proposal_config,
        repo_root=args.repo_root,
        allow_uniprot_network=network,
    )
    print(
        "global-S4 scientific proposals ready: "
        f"dictionary={result.n_dictionary} relationships={result.n_relationships} "
        f"ready_for_application={result.validator_ready}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

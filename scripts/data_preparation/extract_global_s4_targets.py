#!/usr/bin/env python3
"""Milestone 2: raw target extraction and initial target-dictionary proposal.

Reads the immutable combined pre-S4 input and writes separate proposal
artefacts keyed by record_id. Does not populate canonical S4 fields, assign
evidence/affinity, apply leakage, start CHECKPOINT-2, or perform S5.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.target_extraction_aptamerbase import (  # noqa: E402
    aptamerbase_graph_coverage,
    extract_aptamerbase_record,
    load_aptamerbase_target_graph,
)
from adapters.target_extraction_common import (  # noqa: E402
    CANONICAL_FIELDS_MUST_STAY_EMPTY,
    DICTIONARY_COLUMNS,
    RECORD_COLUMNS,
    RELATIONSHIP_COLUMNS,
    RecordExtraction,
    TargetExtractionError,
    TargetRelationship,
    apply_relationships,
    assert_no_sequence_leak,
    base_extraction,
)
from adapters.target_extraction_dictionary import (  # noqa: E402
    build_target_dictionary,
)
from adapters.target_extraction_ncbi import (  # noqa: E402
    extract_ncbi_nuc_record,
)
from adapters.target_extraction_riboaptamer import (  # noqa: E402
    extract_riboaptamer_record,
    inspect_riboaptamer_patterns,
)
from common.corpus_schema import write_corpus_csv_atomic  # noqa: E402
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402

STRUCTURED_SOURCES = (
    "aptabase",
    "utexas",
    "aptadb",
    "aptaindex",
    "ena",
)


@dataclass(frozen=True)
class TargetExtractionResult:
    """Paths and hashes from one Milestone-2 run."""

    n_records: int
    n_relationships: int
    n_dictionary: int
    output_record_csv: Path
    output_relationship_csv: Path
    output_dictionary_csv: Path
    output_summary: Path
    output_manifest: Path
    record_sha256: str
    relationship_sha256: str
    dictionary_sha256: str
    summary_sha256: str
    manifest_sha256: str
    combined_sha256: str
    handoff_sha256: Mapping[str, str]


def _resolve_under_repo(repo_root: Path, path: Path | str) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _relative_display(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _assert_repo_relative(value: str, *, key: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise TargetExtractionError(f"{key} must be a nonempty string path")
    if value.startswith("/") or (len(value) > 2 and value[1] == ":"):
        raise TargetExtractionError(f"{key} must be a repo-relative path")


def _assert_output_allowed(repo_root: Path, output_path: Path | str) -> Path:
    _assert_repo_relative(str(output_path), key="output path")
    resolved = _resolve_under_repo(repo_root, output_path)
    interim_root = (repo_root / "data" / "interim").resolve()
    try:
        resolved.relative_to(interim_root)
    except ValueError as exc:
        raise TargetExtractionError(
            f"Target-extraction output must lie beneath data/interim/: {output_path}"
        ) from exc
    ready_root = (repo_root / "data" / "interim" / "global_s4_ready").resolve()
    try:
        resolved.relative_to(ready_root)
    except ValueError:
        pass
    else:
        raise TargetExtractionError(
            "Refusing to write target proposals under global_s4_ready/"
        )
    combined_name = "combined_global_s4_input.csv"
    if resolved.name == combined_name:
        raise TargetExtractionError(
            "Refusing to write target proposals into the combined input CSV"
        )
    return resolved


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = [{key: row.get(key, "") or "" for key in fields} for row in reader]
    return fields, rows


def load_target_extraction_config(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TargetExtractionError(f"cannot read target-extraction config: {exc}") from exc
    if not isinstance(payload, dict):
        raise TargetExtractionError("target-extraction config must be a JSON object")
    required = (
        "contract_id",
        "expected_combined_records",
        "expected_combined_sha256",
        "combined_input_csv",
        "output_record_csv",
        "output_relationship_csv",
        "output_dictionary_csv",
        "output_summary",
        "output_manifest",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise TargetExtractionError(
            "target-extraction config missing keys: " + ", ".join(missing)
        )
    return payload


def load_aptabase_sidecar(
    path: Path,
    *,
    authorised_ids: Sequence[str],
) -> dict[str, dict[str, str]]:
    """Join frozen AptaBase source metadata 1:1 by record_id."""
    _fields, rows = _read_csv(path)
    by_id: dict[str, dict[str, str]] = {}
    duplicates: list[str] = []
    for row in rows:
        record_id = row.get("record_id", "")
        if not record_id:
            continue
        if record_id in by_id:
            duplicates.append(record_id)
            continue
        by_id[record_id] = row
    if duplicates:
        raise TargetExtractionError(
            "AptaBase source metadata has duplicate record_id values; "
            "refusing heuristic matching"
        )
    missing = [record_id for record_id in authorised_ids if record_id not in by_id]
    if missing:
        raise TargetExtractionError(
            "AptaBase source metadata cannot be joined 1:1 by record_id "
            f"({len(missing)} authorised ids missing)"
        )
    return by_id


def _structured_relationship(
    extraction: RecordExtraction,
    raw: str,
    *,
    locator: str,
    source_target_id: str = "",
    source_uniprot_seed: str = "",
) -> TargetRelationship:
    return TargetRelationship(
        record_id=extraction.record_id,
        source_db=extraction.source_db,
        raw_target=raw,
        target_provenance_source="canonical:target_name_raw",
        target_provenance_locator=locator,
        source_target_id=source_target_id,
        source_uniprot_seed=source_uniprot_seed,
        relationship_confidence="high",
    )


def extract_structured_record(
    row: Mapping[str, str],
    *,
    aptabase_sidecar: Mapping[str, Mapping[str, str]] | None = None,
) -> RecordExtraction:
    """Preserve existing structured target_name_raw without re-extraction."""
    extraction = base_extraction(row)
    raw_exact = row.get("target_name_raw") or ""
    raw = raw_exact.strip()
    source = extraction.source_db
    notes: list[str] = ["structured_existing_target_name_raw=true"]
    source_target_id = ""
    source_uniprot = ""
    locator = f"{source}:canonical:target_name_raw"

    if source == "aptabase":
        sidecar = (aptabase_sidecar or {}).get(extraction.record_id)
        if sidecar is None:
            raise TargetExtractionError(
                f"AptaBase sidecar missing for {extraction.record_id}"
            )
        specific = sidecar.get("aptabase_target_specific") or ""
        general = (sidecar.get("aptabase_target_general") or "").strip()
        extraction.source_target_type_prior = general
        extraction.source_target_type_prior_source = (
            "aptabase_target_general" if general else ""
        )
        notes.append("aptabase_target_general_is_prior_only=true")
        notes.append("affinity_not_interpreted=true")
        if specific.strip() != raw:
            notes.append("aptabase_target_specific_differs_from_target_name_raw")
            extraction.requires_checkpoint2 = True
            extraction.ambiguity_reason = (
                "aptabase_target_specific_differs_from_target_name_raw"
            )
        locator = f"{source}:canonical:target_name_raw|sidecar:aptabase_target_specific"
    elif source == "utexas":
        notes.append("utexas_citation_not_used_as_target=true")
        notes.append("affinity_not_parsed=true")
    elif source == "aptadb":
        source_uniprot = (row.get("aptadb_uniprot_id") or "").strip()
        source_target_id = (row.get("aptadb_target_id") or "").strip()
        chemistry = (row.get("aptadb_target_chemistry") or "").strip()
        extraction.source_target_type_prior = chemistry
        extraction.source_target_type_prior_source = (
            "aptadb_target_chemistry" if chemistry else ""
        )
        extraction.source_uniprot_seed = source_uniprot
        extraction.source_target_id = source_target_id
        notes.append("aptadb_uniprot_is_source_seed_only=true")
        notes.append("aptadb_target_chemistry_is_prior_only=true")
        protein_names = (row.get("aptadb_protein_names") or "").strip()
        if protein_names:
            notes.append("aptadb_protein_names_preserved")
        locator = (
            f"{source}:canonical:target_name_raw"
            f"|aptadb_target_id={source_target_id}"
            f"|aptadb_uniprot_id={source_uniprot}"
        )
    elif source == "aptaindex":
        target_type = (row.get("aptaindex_target_type") or "").strip()
        extraction.source_target_type_prior = target_type
        extraction.source_target_type_prior_source = (
            "aptaindex_target_type" if target_type else ""
        )
        notes.append("aptaindex_target_type_is_prior_only=true")
        notes.append("affinity_not_parsed=true")
        notes.append("redistribution_status_not_altered=true")
        extra_target = row.get("aptaindex_target") or ""
        if extra_target.strip() and extra_target.strip() != raw:
            notes.append("aptaindex_target_differs_from_target_name_raw")
            extraction.requires_checkpoint2 = True
    elif source == "ena":
        source_type = (row.get("ena_source_target_type") or "").strip()
        extraction.source_target_type_prior = source_type
        extraction.source_target_type_prior_source = (
            "ena_source_target_type" if source_type else ""
        )
        notes.append("ena_source_target_type_is_prior_only=true")
        notes.append("title_and_patent_text_not_used=true")
        original = row.get("target_original") or ""
        if original.strip() and original.strip() != raw:
            notes.append("ena_target_original_differs_from_reviewed_target_name_raw")
            locator = f"{source}:canonical:target_name_raw|target_original_preserved"
        if (row.get("genuine_target_conflict") or "").strip() not in {"", "0", "false"}:
            extraction.requires_checkpoint2 = True
            extraction.ambiguity_reason = "ena_genuine_target_conflict"

    if not raw:
        return apply_relationships(
            extraction,
            [],
            status="unresolved",
            method="STRUCTURED_MISSING_TARGET_NAME_RAW",
            confidence="unresolved",
            checkpoint2=True,
            ambiguity_reason="structured_source_missing_target_name_raw",
            notes=";".join(notes),
        )

    rel = _structured_relationship(
        extraction,
        raw_exact,
        locator=locator,
        source_target_id=source_target_id,
        source_uniprot_seed=source_uniprot,
    )
    return apply_relationships(
        extraction,
        [rel],
        status="resolved_single",
        method="STRUCTURED_EXISTING_TARGET_NAME_RAW",
        confidence="high",
        checkpoint2=extraction.requires_checkpoint2,
        ambiguity_reason=extraction.ambiguity_reason,
        notes=";".join(notes),
        effective_override=raw_exact,
    )


def extract_record(
    row: Mapping[str, str],
    *,
    aptabase_sidecar: Mapping[str, Mapping[str, str]] | None = None,
    aptamerbase_graph: Any = None,
) -> RecordExtraction:
    source = (row.get("source_db") or "").strip()
    if source in STRUCTURED_SOURCES:
        return extract_structured_record(row, aptabase_sidecar=aptabase_sidecar)
    if source == "riboaptamer":
        return extract_riboaptamer_record(row)
    if source == "aptamerbase":
        if aptamerbase_graph is None:
            raise TargetExtractionError("AptamerBase RDF graph was not loaded")
        return extract_aptamerbase_record(row, graph=aptamerbase_graph)
    if source == "ncbi_nuc":
        return extract_ncbi_nuc_record(row)
    raise TargetExtractionError(f"unsupported source_db {source!r}")


def _count_by(rows: Sequence[Mapping[str, str]], field: str) -> dict[str, int]:
    return dict(Counter(row.get(field, "") for row in rows))


def _source_status_matrix(
    extractions: Sequence[RecordExtraction],
) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for extraction in extractions:
        matrix[extraction.source_db][extraction.relationship_status] += 1
        matrix[extraction.source_db]["n"] += 1
    return {source: dict(counts) for source, counts in sorted(matrix.items())}


def _top_dictionary_entries(
    dictionary_rows: Sequence[Mapping[str, str]],
    *,
    limit: int = 15,
) -> list[dict[str, str]]:
    ranked = sorted(
        dictionary_rows,
        key=lambda row: (-int(row["n_records"] or 0), row["target_dictionary_id"]),
    )
    return [
        {
            "target_dictionary_id": row["target_dictionary_id"],
            "canonical_target_name_proposal": row["canonical_target_name_proposal"],
            "n_records": row["n_records"],
            "n_relationships": row["n_relationships"],
            "source_keys": row["source_keys"],
            "requires_checkpoint2": row["requires_checkpoint2"],
        }
        for row in ranked[:limit]
    ]


def build_summary(
    *,
    repo_root: Path,
    config: Mapping[str, Any],
    extractions: Sequence[RecordExtraction],
    record_rows: Sequence[Mapping[str, str]],
    relationship_rows: Sequence[Mapping[str, str]],
    dictionary_rows: Sequence[Mapping[str, str]],
    dictionary_diagnostics: Mapping[str, Any],
    ribo_inspect: Mapping[str, Any],
    aptamerbase_coverage: Mapping[str, int],
    hashes: Mapping[str, str],
    handoff_hashes: Mapping[str, str],
    combined_sha256: str,
) -> str:
    status_counts = _count_by(record_rows, "relationship_status")
    conf_counts = _count_by(record_rows, "extraction_confidence")
    dict_conf = _count_by(dictionary_rows, "proposal_confidence")
    by_source = _source_status_matrix(extractions)
    ncbi_lines = []
    for extraction in extractions:
        if extraction.source_db != "ncbi_nuc":
            continue
        accession = ""
        for note in extraction.notes.split(";"):
            if note.startswith("ncbi_nuc_accession="):
                accession = note.split("=", 1)[1]
        ncbi_lines.append(
            f"- `{accession or extraction.record_id}`: "
            f"`{extraction.relationship_status}` "
            f"method=`{extraction.target_extraction_method}` "
            f"field=`{extraction.target_provenance_source}`"
        )
    ribo = by_source.get("riboaptamer", {})
    ab = by_source.get("aptamerbase", {})
    lines = [
        "# Global-S4 Milestone 2 — raw target extraction summary",
        "",
        "Sequence-safe machine proposal. Combined input was not modified.",
        "Canonical target/type/UniProt/family/Pfam/evidence/affinity were not applied.",
        "CHECKPOINT-2 human review was not started.",
        "",
        "## Input",
        "",
        f"- combined records: `{len(extractions)}`",
        f"- combined SHA-256: `{combined_sha256}`",
        f"- record extraction rows: `{len(record_rows)}`",
        f"- relationship proposal rows: `{len(relationship_rows)}`",
        f"- dictionary proposal rows: `{len(dictionary_rows)}`",
        "",
        "## Relationship status",
        "",
        f"- resolved_single: `{status_counts.get('resolved_single', 0)}`",
        f"- resolved_multiple: `{status_counts.get('resolved_multiple', 0)}`",
        f"- ambiguous: `{status_counts.get('ambiguous', 0)}`",
        f"- unresolved: `{status_counts.get('unresolved', 0)}`",
        "",
        "## Extraction confidence",
        "",
    ]
    for key in ("high", "medium", "low", "unresolved"):
        lines.append(f"- {key}: `{conf_counts.get(key, 0)}`")
    lines.extend(["", "## By source", ""])
    for source, counts in by_source.items():
        lines.append(
            f"- `{source}`: n=`{counts.get('n', 0)}` "
            f"resolved_single=`{counts.get('resolved_single', 0)}` "
            f"resolved_multiple=`{counts.get('resolved_multiple', 0)}` "
            f"ambiguous=`{counts.get('ambiguous', 0)}` "
            f"unresolved=`{counts.get('unresolved', 0)}`"
        )
    lines.extend(
        [
            "",
            "## Structured sources",
            "",
            "Existing `target_name_raw` was preserved for aptabase, utexas, aptadb,",
            "aptaindex, and ena. Source category/chemistry values remain priors.",
            "",
            "## RiboAptamer",
            "",
            f"- records: `{ribo.get('n', 0)}`",
            f"- resolved_single: `{ribo.get('resolved_single', 0)}`",
            f"- resolved_multiple: `{ribo.get('resolved_multiple', 0)}`",
            f"- ambiguous: `{ribo.get('ambiguous', 0)}`",
            f"- unresolved: `{ribo.get('unresolved', 0)}`",
            f"- unique aptamer names: `{ribo_inspect.get('unique_aptamer_names')}`",
            f"- names containing aptamer: `{ribo_inspect.get('names_containing_aptamer')}`",
            f"- description explicit aptamer-for hits: "
            f"`{ribo_inspect.get('description_explicit_aptamer_for_hits')}`",
            "- Category and Type were priors only and were not used as target names.",
            "",
            "### RiboAptamer `RA_SEQ_FIRST_UNDERSCORE` audit",
            "",
        ]
    )
    ribo_audit = ribo_inspect.get("seq_first_underscore_audit") or {}
    class_counts = ribo_audit.get("classification_counts") or {}
    corroboration_counts = ribo_audit.get("corroboration_source_counts") or {}
    lines.extend(
        [
            f"- single-prefix cohort: `{ribo_audit.get('n_single_prefix_cohort', 0)}`",
            f"- corroborated_target_label: `{class_counts.get('corroborated_target_label', 0)}`",
            f"- sequence_name_is_explicit_target_label: "
            f"`{class_counts.get('sequence_name_is_explicit_target_label', 0)}`",
            f"- clone_or_construct_label_not_target: "
            f"`{class_counts.get('clone_or_construct_label_not_target', 0)}`",
            f"- conflicting_source_metadata: "
            f"`{class_counts.get('conflicting_source_metadata', 0)}`",
            f"- insufficient_support: `{class_counts.get('insufficient_support', 0)}`",
            "- Convention: Sequence Name `{target}_{clone_or_variant}` encodes the "
            "ligand/target in the prefix. Aptamer Name, Description, or publication "
            "text may corroborate the prefix. Clone-like Aptamer Names do not "
            "override a descriptive prefix. Category and Type are not corroboration.",
            "- Unsupported or clone-like prefixes are not treated as deterministic "
            "targets. Conflicting Aptamer Name vs Sequence Name prefixes are ambiguous.",
            "",
            "Corroboration sources (not Category/Type):",
            "",
        ]
    )
    for key in ("aptamer_name", "description", "article_name", "none"):
        if key in corroboration_counts:
            lines.append(f"- `{key}`: `{corroboration_counts[key]}`")
    lines.extend(
        [
            "",
            "### RiboAptamer Type counts (priors only)",
            "",
        ]
    )
    for key, value in sorted((ribo_inspect.get("type_counts") or {}).items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "### RiboAptamer Category counts (priors only)", ""])
    for key, value in sorted((ribo_inspect.get("category_counts") or {}).items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## AptamerBase RDF",
            "",
            f"- records: `{ab.get('n', 0)}`",
            f"- RDF statements scanned: `{aptamerbase_coverage.get('rdf_statements_scanned', 0)}`",
            f"- nonempty Freebase IDs: `{aptamerbase_coverage.get('nonempty_aptamerbase_id', 0)}`",
            f"- RDF subjects joined: `{aptamerbase_coverage.get('rdf_subject_joined', 0)}`",
            f"- has interaction: `{aptamerbase_coverage.get('has_interaction', 0)}`",
            f"- has aptamer_target counterpart: "
            f"`{aptamerbase_coverage.get('has_aptamer_target_counterpart', 0)}`",
            f"- resolved_single: `{ab.get('resolved_single', 0)}`",
            f"- resolved_multiple: `{ab.get('resolved_multiple', 0)}`",
            f"- ambiguous: `{ab.get('ambiguous', 0)}`",
            f"- unresolved: `{ab.get('unresolved', 0)}`",
            "- Path: `is_participant_in` → `has_participant` → English `rdfs:label`",
            "  on `base.aptamer.aptamer_target` (or secondary protein counterpart).",
            "- `aptamerbase_label` was not treated as a target.",
            "- Affinity/evidence triples were not assigned as E1–E5 or canonical Kd.",
            "",
            "## NCBI Nucleotide",
            "",
        ]
    )
    lines.extend(ncbi_lines or ["- (no NCBI rows)"])
    lines.extend(
        [
            "",
            "## Initial target dictionary (machine proposal)",
            "",
            f"- dictionary entries: `{len(dictionary_rows)}`",
            f"- distinct primary match keys: "
            f"`{dictionary_diagnostics.get('n_primary_match_keys')}`",
            f"- alias-candidate groups: "
            f"`{dictionary_diagnostics.get('n_alias_candidate_groups')}`",
            f"- UniProt-conflict split entries: "
            f"`{dictionary_diagnostics.get('n_uniprot_conflict_entries')}`",
            f"- entries requiring CHECKPOINT-2: "
            f"`{dictionary_diagnostics.get('n_requiring_checkpoint2')}`",
            "",
            "Proposal confidence:",
            "",
        ]
    )
    for key in ("high", "medium", "low", "unresolved"):
        lines.append(f"- {key}: `{dict_conf.get(key, 0)}`")
    lines.extend(["", "### Top entries by affected records", ""])
    for item in _top_dictionary_entries(dictionary_rows):
        lines.append(
            f"- `{item['target_dictionary_id']}` "
            f"n_records=`{item['n_records']}` "
            f"proposal=`{item['canonical_target_name_proposal']}` "
            f"sources=`{item['source_keys']}`"
        )
    n_expansion = sum(
        1 for extraction in extractions if extraction.record_expansion_proposed
    )
    n_distinct_raw = len(
        {
            rel.raw_target
            for extraction in extractions
            for rel in extraction.relationships
            if rel.raw_target
        }
    )
    lines.extend(
        [
            "",
            f"- distinct effective/raw relationship strings: `{n_distinct_raw}`",
            f"- records with expansion proposed: `{n_expansion}`",
            "",
            "## Hashes",
            "",
            f"- record CSV: `{hashes['record']}`",
            f"- relationship CSV: `{hashes['relationship']}`",
            f"- dictionary CSV: `{hashes['dictionary']}`",
            "",
            "Source handoff hashes (unchanged):",
            "",
        ]
    )
    for source, digest in handoff_hashes.items():
        lines.append(f"- `{source}`: `{digest}`")
    lines.extend(
        [
            "",
            "## Scientific boundary",
            "",
            "- no final canonical target_name / target_uniprot / target_type",
            "- no family / Pfam / PDB assignment",
            "- no evidence or affinity canonicalisation",
            "- no leakage application",
            "- no CHECKPOINT-2 human decisions",
            "- no cross-source deduplication, clustering, balancing, or partitioning",
            "",
        ]
    )
    text = "\n".join(lines) + "\n"
    assert_no_sequence_leak(text, label="target extraction summary")
    abs_root = str(repo_root.resolve())
    if abs_root in text:
        raise TargetExtractionError(
            "Target extraction summary must not contain absolute repository paths"
        )
    return text


def extract_global_s4_targets(
    *,
    extraction_config: Path,
    repo_root: Path | None = None,
) -> TargetExtractionResult:
    """Run Milestone-2 target extraction from the immutable combined input."""
    root = repo_root or find_repo_root()
    config_path = _resolve_under_repo(root, extraction_config)
    config = load_target_extraction_config(config_path)
    combined_path = _resolve_under_repo(root, config["combined_input_csv"])
    if not combined_path.is_file():
        raise TargetExtractionError(f"missing combined input: {config['combined_input_csv']}")
    before_combined = sha256_file(combined_path)
    expected_hash = str(config["expected_combined_sha256"])
    if before_combined != expected_hash:
        raise TargetExtractionError(
            "Combined input SHA-256 does not match the accepted Milestone-2 "
            f"invariant ({expected_hash} vs {before_combined})"
        )

    combined_config_rel = config.get("combined_input_config")
    handoff_hashes: dict[str, str] = {}
    if combined_config_rel:
        combined_cfg_path = _resolve_under_repo(root, str(combined_config_rel))
        combined_cfg = json.loads(combined_cfg_path.read_text(encoding="utf-8"))
        for item in combined_cfg.get("contributing_sources") or []:
            source_cfg_path = _resolve_under_repo(root, item["source_config"])
            source_cfg = json.loads(source_cfg_path.read_text(encoding="utf-8"))
            handoff = _resolve_under_repo(root, source_cfg["global_s4_handoff_output"])
            handoff_hashes[item["source_key"]] = sha256_file(handoff)

    _fields, combined_rows = _read_csv(combined_path)
    expected_n = int(config["expected_combined_records"])
    if len(combined_rows) != expected_n:
        raise TargetExtractionError(
            f"Combined input has {len(combined_rows)} rows; expected {expected_n}"
        )
    record_ids = [row["record_id"] for row in combined_rows]
    if len(record_ids) != len(set(record_ids)):
        raise TargetExtractionError("Combined input record_id values are not unique")

    for field in CANONICAL_FIELDS_MUST_STAY_EMPTY:
        nonempty = sum(1 for row in combined_rows if (row.get(field) or "").strip())
        if nonempty:
            raise TargetExtractionError(
                f"Combined input already has canonical {field} populated"
            )

    aptabase_ids = [
        row["record_id"] for row in combined_rows if row.get("source_db") == "aptabase"
    ]
    aptabase_sidecar: dict[str, dict[str, str]] = {}
    if aptabase_ids:
        sidecar_path = _resolve_under_repo(root, config["aptabase_source_metadata"])
        aptabase_sidecar = load_aptabase_sidecar(
            sidecar_path, authorised_ids=aptabase_ids
        )

    aptamerbase_graph = None
    ab_rows = [row for row in combined_rows if row.get("source_db") == "aptamerbase"]
    if ab_rows:
        rdf_path = _resolve_under_repo(root, config["aptamerbase_rdf"])
        expected_rdf = str(config.get("expected_aptamerbase_rdf_sha256") or "")
        if expected_rdf:
            live_rdf = sha256_file(rdf_path)
            if live_rdf != expected_rdf:
                raise TargetExtractionError(
                    "AptamerBase RDF SHA-256 does not match the registered extract"
                )
        aptamerbase_graph = load_aptamerbase_target_graph(rdf_path)

    extractions: list[RecordExtraction] = []
    for row in combined_rows:
        extractions.append(
            extract_record(
                row,
                aptabase_sidecar=aptabase_sidecar,
                aptamerbase_graph=aptamerbase_graph,
            )
        )
    if [item.record_id for item in extractions] != record_ids:
        raise TargetExtractionError("Extraction record_id order does not match input")

    record_rows = [item.as_row() for item in extractions]
    relationship_rows = [
        rel.as_row() for item in extractions for rel in item.relationships
    ]
    dictionary_rows, dictionary_diagnostics = build_target_dictionary(extractions)

    out_record = _assert_output_allowed(root, config["output_record_csv"])
    out_rel = _assert_output_allowed(root, config["output_relationship_csv"])
    out_dict = _assert_output_allowed(root, config["output_dictionary_csv"])
    out_summary = _assert_output_allowed(root, config["output_summary"])
    out_manifest = _assert_output_allowed(root, config["output_manifest"])

    write_corpus_csv_atomic(out_record, record_rows, columns=RECORD_COLUMNS)
    write_corpus_csv_atomic(out_rel, relationship_rows, columns=RELATIONSHIP_COLUMNS)
    write_corpus_csv_atomic(out_dict, dictionary_rows, columns=DICTIONARY_COLUMNS)

    after_combined = sha256_file(combined_path)
    if after_combined != before_combined:
        raise TargetExtractionError("Combined input was modified during target extraction")
    after_handoffs = {}
    if combined_config_rel:
        combined_cfg = json.loads(
            _resolve_under_repo(root, str(combined_config_rel)).read_text(encoding="utf-8")
        )
        for item in combined_cfg.get("contributing_sources") or []:
            source_cfg = json.loads(
                _resolve_under_repo(root, item["source_config"]).read_text(encoding="utf-8")
            )
            handoff = _resolve_under_repo(root, source_cfg["global_s4_handoff_output"])
            after_handoffs[item["source_key"]] = sha256_file(handoff)
        if after_handoffs != handoff_hashes:
            raise TargetExtractionError("Source handoff CSVs were modified during extraction")

    ribo_rows = [row for row in combined_rows if row.get("source_db") == "riboaptamer"]
    ribo_inspect = inspect_riboaptamer_patterns(ribo_rows)
    ab_coverage = (
        aptamerbase_graph_coverage(ab_rows, aptamerbase_graph)
        if aptamerbase_graph is not None
        else {
            "authorised_rows": 0,
            "nonempty_aptamerbase_id": 0,
            "rdf_subject_joined": 0,
            "has_interaction": 0,
            "has_aptamer_target_counterpart": 0,
            "rdf_statements_scanned": 0,
        }
    )

    record_sha = sha256_file(out_record)
    rel_sha = sha256_file(out_rel)
    dict_sha = sha256_file(out_dict)
    hashes = {
        "record": record_sha,
        "relationship": rel_sha,
        "dictionary": dict_sha,
    }
    summary = build_summary(
        repo_root=root,
        config=config,
        extractions=extractions,
        record_rows=record_rows,
        relationship_rows=relationship_rows,
        dictionary_rows=dictionary_rows,
        dictionary_diagnostics=dictionary_diagnostics,
        ribo_inspect=ribo_inspect,
        aptamerbase_coverage=ab_coverage,
        hashes=hashes,
        handoff_hashes=handoff_hashes,
        combined_sha256=before_combined,
    )
    _write_text_atomic(out_summary, summary)
    summary_sha = sha256_file(out_summary)

    status_counts = _count_by(record_rows, "relationship_status")
    manifest = {
        "contract_id": config.get("contract_id"),
        "milestone": config.get("milestone"),
        "combined_records": len(combined_rows),
        "extraction_records": len(record_rows),
        "relationship_rows": len(relationship_rows),
        "dictionary_rows": len(dictionary_rows),
        "relationship_status": status_counts,
        "by_source": _source_status_matrix(extractions),
        "riboaptamer_inspection": {
            key: value
            for key, value in ribo_inspect.items()
            if key != "top_aptamer_names"
        },
        "riboaptamer_top_aptamer_names": ribo_inspect.get("top_aptamer_names"),
        "aptamerbase_rdf_coverage": ab_coverage,
        "dictionary": {
            "n_entries": dictionary_diagnostics.get("n_dictionary_entries"),
            "n_primary_match_keys": dictionary_diagnostics.get("n_primary_match_keys"),
            "n_alias_candidate_groups": dictionary_diagnostics.get(
                "n_alias_candidate_groups"
            ),
            "n_uniprot_conflict_entries": dictionary_diagnostics.get(
                "n_uniprot_conflict_entries"
            ),
            "n_requiring_checkpoint2": dictionary_diagnostics.get(
                "n_requiring_checkpoint2"
            ),
        },
        "paths": {
            "record_csv": _relative_display(out_record, root),
            "relationship_csv": _relative_display(out_rel, root),
            "dictionary_csv": _relative_display(out_dict, root),
            "summary": _relative_display(out_summary, root),
            "manifest": _relative_display(out_manifest, root),
        },
        "hashes": {
            "combined_input": before_combined,
            "record_csv": record_sha,
            "relationship_csv": rel_sha,
            "dictionary_csv": dict_sha,
            "summary": summary_sha,
            "source_handoffs": dict(handoff_hashes),
        },
        "scientific_boundary": config.get("scientific_boundary") or {},
    }
    manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    assert_no_sequence_leak(manifest_text, label="target extraction manifest")
    _write_text_atomic(out_manifest, manifest_text)
    manifest_sha = sha256_file(out_manifest)

    return TargetExtractionResult(
        n_records=len(record_rows),
        n_relationships=len(relationship_rows),
        n_dictionary=len(dictionary_rows),
        output_record_csv=out_record,
        output_relationship_csv=out_rel,
        output_dictionary_csv=out_dict,
        output_summary=out_summary,
        output_manifest=out_manifest,
        record_sha256=record_sha,
        relationship_sha256=rel_sha,
        dictionary_sha256=dict_sha,
        summary_sha256=summary_sha,
        manifest_sha256=manifest_sha,
        combined_sha256=before_combined,
        handoff_sha256=handoff_hashes,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract source-supported raw targets from the combined global-S4 "
            "input and emit an initial machine-proposed target dictionary. "
            "Does not modify the combined input or apply canonical S4 fields."
        )
    )
    parser.add_argument(
        "--extraction-config",
        type=Path,
        required=True,
        help="Repo-relative Milestone-2 target-extraction contract JSON",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detected)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.repo_root or find_repo_root()
    result = extract_global_s4_targets(
        extraction_config=args.extraction_config,
        repo_root=root,
    )
    print(
        "global-S4 target extraction ready: "
        f"records={result.n_records} relationships={result.n_relationships} "
        f"dictionary={result.n_dictionary}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

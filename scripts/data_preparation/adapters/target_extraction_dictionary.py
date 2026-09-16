"""Initial machine-proposed target dictionary from source-supported relationships."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Sequence

from adapters.target_extraction_common import (
    DICTIONARY_COLUMNS,
    RecordExtraction,
    TargetRelationship,
    alias_candidate_key,
    bool_token,
    join_unique,
    primary_match_key,
)

REVIEW_STATUS = "machine_proposed"
CANONICALISATION_METHOD = "most_frequent_whitespace_normalised_raw_string"


def _normalised_display(raw: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", raw or "")).strip()


def _empty_dictionary_row() -> dict[str, str]:
    return {column: "" for column in DICTIONARY_COLUMNS}


def _canonical_raw(rels: Sequence[TargetRelationship]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for rel in rels:
        display = _normalised_display(rel.raw_target)
        if display:
            counts[display] += 1
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[0][0]


def _confidence(rels: Sequence[TargetRelationship], *, flags: list[str]) -> str:
    if any(flag.startswith("aptadb_uniprot") for flag in flags):
        return "low"
    confs = {rel.relationship_confidence for rel in rels}
    if "unresolved" in confs and len(confs) == 1:
        return "unresolved"
    if flags:
        if confs <= {"high"}:
            return "medium"
        return "low"
    if confs == {"high"}:
        return "high"
    if "low" in confs:
        return "low"
    return "medium"


def _split_uniprot_groups(
    rels: Sequence[TargetRelationship],
) -> list[tuple[str, list[TargetRelationship], list[str]]]:
    seeds = sorted(
        {
            (rel.source_uniprot_seed or "").strip()
            for rel in rels
            if (rel.source_uniprot_seed or "").strip()
        }
    )
    if len(seeds) <= 1:
        seed = seeds[0] if seeds else ""
        return [(seed, list(rels), [])]
    groups: list[tuple[str, list[TargetRelationship], list[str]]] = []
    for seed in seeds:
        matched = [rel for rel in rels if (rel.source_uniprot_seed or "").strip() == seed]
        groups.append((seed, matched, ["aptadb_uniprot_seed_conflict"]))
    leftover = [rel for rel in rels if not (rel.source_uniprot_seed or "").strip()]
    if leftover:
        groups.append(("", leftover, ["aptadb_uniprot_seed_conflict"]))
    return groups


def build_target_dictionary(
    extractions: Sequence[RecordExtraction],
) -> tuple[list[dict[str, str]], dict[str, object]]:
    """Aggregate source-supported relationships into dictionary proposals."""
    by_primary: dict[str, list[tuple[RecordExtraction, TargetRelationship]]] = defaultdict(
        list
    )
    for extraction in extractions:
        if extraction.relationship_status == "unresolved":
            continue
        for rel in extraction.relationships:
            if not (rel.raw_target or "").strip():
                continue
            key = primary_match_key(rel.raw_target)
            if not key:
                continue
            by_primary[key].append((extraction, rel))

    alias_to_primaries: dict[str, set[str]] = defaultdict(set)
    for primary, pairs in by_primary.items():
        for _extraction, rel in pairs:
            alias = alias_candidate_key(rel.raw_target)
            if alias:
                alias_to_primaries[alias].add(primary)

    rows: list[dict[str, str]] = []
    for primary in sorted(by_primary):
        pairs = by_primary[primary]
        rels = [rel for _extraction, rel in pairs]
        for seed, seed_rels, split_flags in _split_uniprot_groups(rels):
            seed_pairs = [
                (extraction, rel)
                for extraction, rel in pairs
                if rel in seed_rels
            ]
            record_ids = sorted({extraction.record_id for extraction, _rel in seed_pairs})
            source_keys = sorted({extraction.source_db for extraction, _rel in seed_pairs})
            type_priors = [
                extraction.source_target_type_prior
                for extraction, _rel in seed_pairs
                if extraction.source_target_type_prior
            ]
            target_ids = [rel.source_target_id for _extraction, rel in seed_pairs]
            expansion = any(
                extraction.record_expansion_proposed for extraction, _rel in seed_pairs
            )
            flags = list(split_flags)
            if expansion:
                flags.append("record_expansion_involved")
            if any(extraction.relationship_status == "ambiguous" for extraction, _rel in seed_pairs):
                flags.append("source_relationship_ambiguous")
            if any(
                extraction.relationship_status == "resolved_multiple"
                for extraction, _rel in seed_pairs
            ):
                flags.append("resolved_multiple_source_relationship")
            unique_priors = sorted({item for item in type_priors if item})
            if len(unique_priors) > 1:
                flags.append("mixed_source_target_type_priors")
            alias = alias_candidate_key(seed_rels[0].raw_target)
            sibling_primaries = alias_to_primaries.get(alias, set()) - {primary}
            if sibling_primaries:
                flags.append("alias_candidate_with_distinct_primary_keys")
            canonical = _canonical_raw(seed_rels)
            checkpoint2 = bool(flags) or any(
                rel.requires_checkpoint2 or extraction.requires_checkpoint2
                for extraction, rel in seed_pairs
            )
            row = _empty_dictionary_row()
            row.update(
                {
                    "raw_target": join_unique([rel.raw_target for rel in seed_rels]),
                    "primary_match_key": primary,
                    "alias_candidate_key": alias,
                    "canonical_target_name_proposal": canonical,
                    "canonicalisation_method": CANONICALISATION_METHOD,
                    "proposal_confidence": _confidence(seed_rels, flags=flags),
                    "source_keys": join_unique(source_keys),
                    "n_records": str(len(record_ids)),
                    "n_relationships": str(len(seed_rels)),
                    "source_uniprot_seed": seed if not split_flags else (
                        seed or join_unique(sorted({
                            (rel.source_uniprot_seed or "").strip()
                            for rel in rels
                            if (rel.source_uniprot_seed or "").strip()
                        }))
                    ),
                    "source_target_type_priors": join_unique(type_priors),
                    "source_target_ids": join_unique(target_ids),
                    "record_expansion_involved": bool_token(expansion),
                    "ambiguity_flags": join_unique(flags),
                    "requires_checkpoint2": bool_token(checkpoint2),
                    "review_status": REVIEW_STATUS,
                }
            )
            if split_flags:
                row["source_uniprot_seed"] = seed
            rows.append(row)

    rows.sort(
        key=lambda row: (
            row["primary_match_key"],
            row["source_uniprot_seed"],
            row["canonical_target_name_proposal"],
        )
    )
    for index, row in enumerate(rows, start=1):
        row["target_dictionary_id"] = f"TD{index:04d}"

    alias_groups = [
        {"alias_candidate_key": alias, "primary_match_keys": sorted(primaries)}
        for alias, primaries in sorted(alias_to_primaries.items())
        if len(primaries) > 1
    ]
    diagnostics = {
        "n_dictionary_entries": len(rows),
        "n_primary_match_keys": len(by_primary),
        "n_alias_candidate_groups": len(alias_groups),
        "alias_candidate_groups": alias_groups,
        "n_uniprot_conflict_entries": sum(
            1
            for row in rows
            if "aptadb_uniprot_seed_conflict" in row["ambiguity_flags"]
        ),
        "n_requiring_checkpoint2": sum(
            1 for row in rows if row["requires_checkpoint2"] == "true"
        ),
    }
    return rows, diagnostics

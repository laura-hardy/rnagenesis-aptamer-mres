"""Canonical target-type proposals from source priors and identity conflicts."""

from __future__ import annotations

import re
from typing import Mapping

from adapters.s4_scientific_common import TARGET_TYPE_VOCAB, join_unique

SOURCE_PRIOR_MAP: dict[tuple[str, str], str] = {
    ("aptabase", "protein"): "protein",
    ("aptabase", "peptide"): "peptide",
    ("aptabase", "small organic"): "small_molecule",
    ("aptabase", "cells"): "cell",
    ("aptabase", "antibody"): "protein",
    ("aptadb", "protein"): "protein",
    ("aptaindex", "protein"): "protein",
    ("aptaindex", "small organic"): "small_molecule",
    ("aptaindex", "cells"): "cell",
    ("aptaindex", "peptide"): "peptide",
    ("aptaindex", "other"): "other",
    ("aptaindex", "tissue"): "other",
    ("riboaptamer", "proteins"): "protein",
    ("riboaptamer", "small molecules"): "small_molecule",
    ("riboaptamer", "cells"): "cell",
    ("riboaptamer", "nucleic acids"): "nucleic_acid",
    ("ena", "protein"): "protein",
    ("ena", "enzyme"): "protein",
    ("aptamerbase", "protein"): "protein",
    ("aptamerbase", "peptide"): "peptide",
    ("aptamerbase", "small molecule"): "small_molecule",
    ("aptamerbase", "nucleic acid"): "nucleic_acid",
    ("aptamerbase", "cell"): "cell",
    ("aptamerbase", "nucleotide"): "small_molecule",
    ("aptamerbase", "lipid"): "small_molecule",
    ("aptamerbase", "hormone"): "peptide",
    ("aptamerbase", "enzyme"): "protein",
    ("aptamerbase", "carbohydrate"): "small_molecule",
}

FAMILY_CLUES: dict[tuple[str, str], str] = {
    ("aptabase", "antibody"): "antibody_immunoglobulin",
    ("ena", "enzyme"): "enzyme",
    ("aptamerbase", "enzyme"): "enzyme",
    ("aptamerbase", "hormone"): "other",
}

NCBI_TYPE_BY_ACCESSION: dict[str, str] = {
    "U34759": "nucleic_acid",
    "U37124": "small_molecule",
    "U37123": "small_molecule",
    "AF083271": "small_molecule",
    "BD161067": "unknown",
}


def _norm_prior(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def map_one_prior(source_db: str, prior: str) -> tuple[str, str]:
    """Return (canonical_type, family_clue) for one source prior token."""
    key = (source_db, _norm_prior(prior))
    mapped = SOURCE_PRIOR_MAP.get(key, "")
    family = FAMILY_CLUES.get(key, "")
    return mapped, family


def map_source_type_prior(
    source_db: str,
    prior: str,
    *,
    accession: str = "",
) -> dict[str, str]:
    """Propose a canonical target type from a source prior.

    Source priors are evidence, not unquestioned truth. Mixed RDF classes or
    unmapped priors become unknown and require review when they affect routing.
    """
    source_db = (source_db or "").strip()
    prior = (prior or "").strip()
    if source_db == "ncbi_nuc":
        proposed = NCBI_TYPE_BY_ACCESSION.get(accession, "unknown")
        review = "true" if accession == "BD161067" or proposed == "unknown" else "false"
        return {
            "target_type_proposed": proposed if proposed in TARGET_TYPE_VOCAB else "unknown",
            "target_type_source_proposed": "source_supported_target_interpretation",
            "target_type_confidence": "medium" if proposed != "unknown" else "low",
            "family_clue": "",
            "type_requires_review": review,
            "type_conflict_reason": "ncbi_dual_target_ambiguous"
            if accession == "BD161067"
            else "",
        }

    if not prior:
        return {
            "target_type_proposed": "unknown",
            "target_type_source_proposed": "unresolved",
            "target_type_confidence": "low",
            "family_clue": "",
            "type_requires_review": "false",
            "type_conflict_reason": "",
        }

    tokens = [item.strip() for item in prior.split("|") if item.strip()]
    mapped: list[str] = []
    families: list[str] = []
    unmapped: list[str] = []
    for token in tokens:
        canonical, family = map_one_prior(source_db, token)
        if canonical:
            mapped.append(canonical)
        else:
            unmapped.append(token)
        if family:
            families.append(family)

    unique_types = list(dict.fromkeys(mapped))
    review = "false"
    reason = ""
    confidence = "high"
    source_method = "source_column"
    if source_db in {"aptabase", "riboaptamer", "aptaindex"}:
        source_method = "source_prior"
    if not unique_types:
        proposed = "unknown"
        confidence = "low"
        source_method = "unresolved"
        if unmapped:
            review = "true"
            reason = "unmapped_source_target_type_prior"
    elif len(unique_types) > 1:
        proposed = "unknown"
        confidence = "low"
        review = "true"
        reason = "mixed_source_target_type_prior"
    else:
        proposed = unique_types[0]
        if unmapped:
            review = "true"
            reason = "unmapped_source_target_type_prior"
            confidence = "medium"
        elif source_db in {"aptabase", "riboaptamer", "aptaindex", "aptadb", "ena"}:
            review = "false"
        if source_db == "aptaindex" and _norm_prior(prior) == "tissue":
            review = "true"
            reason = "aptaindex_tissue_mapped_to_other"
        if source_db == "utexas":
            proposed = "unknown"
            source_method = "unresolved"
            confidence = "low"

    if source_db == "aptadb" and proposed != "protein" and prior:
        review = "true"
        reason = "aptadb_chemistry_contradiction"

    return {
        "target_type_proposed": proposed if proposed in TARGET_TYPE_VOCAB else "unknown",
        "target_type_source_proposed": source_method,
        "target_type_confidence": confidence,
        "family_clue": join_unique(families),
        "type_requires_review": review,
        "type_conflict_reason": reason,
    }


def merge_dictionary_type_priors(
    source_priors: Mapping[str, str],
) -> dict[str, str]:
    """Combine per-source mapped priors for one dictionary entry."""
    mapped: list[str] = []
    families: list[str] = []
    reviews: list[str] = []
    sources: list[str] = []
    for source_db, prior in sorted(source_priors.items()):
        result = map_source_type_prior(source_db, prior)
        if result["target_type_proposed"] != "unknown":
            mapped.append(result["target_type_proposed"])
            sources.append(source_db)
        if result["family_clue"]:
            families.append(result["family_clue"])
        if result["type_requires_review"] == "true":
            reviews.append(result["type_conflict_reason"] or "source_prior_review")
    unique = list(dict.fromkeys(mapped))
    if len(unique) == 1:
        proposed = unique[0]
        confidence = "high" if not reviews else "medium"
        review = "true" if reviews else "false"
        reason = join_unique(reviews)
        source = "source_prior" if len(set(sources)) == 1 else "dictionary"
    elif not unique:
        proposed = "unknown"
        confidence = "low"
        review = "false"
        reason = ""
        source = "unresolved"
    else:
        proposed = "unknown"
        confidence = "low"
        review = "true"
        reason = "conflicting_source_target_type_priors"
        source = "dictionary"
    return {
        "target_type_proposed": proposed,
        "target_type_source_proposed": source,
        "target_type_confidence": confidence,
        "family_clue": join_unique(families),
        "type_requires_review": review,
        "type_conflict_reason": reason,
    }

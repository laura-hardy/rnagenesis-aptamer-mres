"""Functional family and Pfam/InterPro proposal helpers."""

from __future__ import annotations

import re
from typing import Mapping

from adapters.s4_scientific_common import TARGET_FAMILY_VOCAB, join_unique

PROTEIN_TYPES = frozenset({"protein", "peptide"})
REGION_RE = re.compile(
    r"(?i)\b(extracellular domain|ectodomain|runt domain|domain of|"
    r"fragment|subunit|complex|truncat(?:ed|ion)|cleaved into)\b"
)


def region_or_fragment(raw_target: str) -> str:
    text = raw_target or ""
    if REGION_RE.search(text):
        return "true"
    return "false"


def propose_family(
    *,
    target_type: str,
    family_clues: list[str],
    uniprot_family_clue: str = "",
    catalytic_activity: str = "",
) -> dict[str, str]:
    """Assign family only after type is sufficiently resolved.

    Non-protein targets receive `other`. Missing family is permitted and is
    not a CHECKPOINT-2 reason by itself.
    """
    if target_type not in PROTEIN_TYPES:
        family = "other" if target_type not in {"unknown", ""} else "unknown"
        return {
            "target_family_proposed": family if family in TARGET_FAMILY_VOCAB else "unknown",
            "target_family_source": "non_protein_handling" if family == "other" else "unresolved",
            "family_requires_review": "false",
        }
    clues = [item for item in family_clues + [uniprot_family_clue] if item]
    unique = list(dict.fromkeys(clues))
    if catalytic_activity and catalytic_activity.strip() not in {"", "N/A"}:
        if "enzyme" not in unique:
            unique.append("enzyme")
    unique = [item for item in unique if item in TARGET_FAMILY_VOCAB]
    if len(unique) == 1:
        return {
            "target_family_proposed": unique[0],
            "target_family_source": "source_metadata_or_uniprot",
            "family_requires_review": "false",
        }
    if len(unique) > 1:
        return {
            "target_family_proposed": "unknown",
            "target_family_source": "unresolved",
            "family_requires_review": "true",
            "family_conflict_reason": "conflicting_family_clues:" + join_unique(unique),
        }
    return {
        "target_family_proposed": "unknown",
        "target_family_source": "unresolved",
        "family_requires_review": "false",
    }


def parse_pfam_interpro(*values: str) -> tuple[str, str]:
    pfams: list[str] = []
    interpros: list[str] = []
    for raw in values:
        for token in re.split(r"[;|,/\s]+", raw or ""):
            token = token.strip()
            if re.fullmatch(r"PF\d{5}", token, re.I):
                pfams.append(token.upper())
            elif re.fullmatch(r"IPR\d{6}", token, re.I):
                interpros.append(token.upper())
    return join_unique(pfams), join_unique(interpros)

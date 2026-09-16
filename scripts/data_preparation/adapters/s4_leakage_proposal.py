"""Diagnostic leakage matching in proposal mode. Does not apply exclusions."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from adapters.s4_scientific_common import bool_token
from common.eligibility import (
    LeakageMatch,
    TargetLeakageMatch,
    load_sequence_leakage_index,
    load_target_alias_rules,
    match_target_leakage,
)
from common.leakage_matching import IDENTITY_THRESHOLD


def load_leakage_resources(
    *,
    exclusion_set: Path,
    alias_csv: Path,
):
    index = load_sequence_leakage_index(exclusion_set)
    rules = load_target_alias_rules(alias_csv)
    return index, rules


def propose_leakage(
    row: Mapping[str, str],
    *,
    index,
    rules: Sequence,
    target_texts: Sequence[str],
) -> dict[str, str]:
    """Match one record against the established leakage exclusion set.

    Uses full/core comparison forms, T/U equivalence, global Levenshtein, and
    the 0.90 identity threshold. Does not print sequences or apply exclusions.
    """
    sequence_full = row.get("sequence_full") or ""
    sequence_core = row.get("sequence_core") or ""
    seq_match: LeakageMatch | None = index.best_match(
        sequence_full=sequence_full,
        sequence_core=sequence_core,
        threshold=IDENTITY_THRESHOLD,
    )
    target_match: TargetLeakageMatch | None = match_target_leakage(list(target_texts), rules)
    sequence_kind = ""
    identity = ""
    if seq_match is not None:
        if seq_match.identity >= 1.0:
            sequence_kind = "exact"
        elif seq_match.identity >= IDENTITY_THRESHOLD:
            sequence_kind = "identity_ge_0.90"
        identity = f"{seq_match.identity:.6f}"
    both = bool(seq_match is not None and target_match is not None)
    proposed = bool(seq_match is not None or target_match is not None)
    review = False
    notes = []
    if seq_match is not None and sequence_kind == "identity_ge_0.90" and seq_match.identity < 1.0:
        if seq_match.identity < 0.95:
            review = True
            notes.append("borderline_sequence_identity")
    if target_match is not None and target_match.match_type == "family_pattern":
        review = True
        notes.append("target_family_pattern_may_need_semantic_review")
    return {
        "record_id": row.get("record_id", ""),
        "source_db": row.get("source_db", ""),
        "sequence_match_kind": sequence_kind,
        "identity": identity,
        "matched_form": seq_match.matched_form if seq_match else "",
        "matched_exclusion_id": seq_match.matched_exclusion_id if seq_match else "",
        "matched_reference_id": seq_match.matched_reference_id if seq_match else "",
        "matched_evaluation_role": seq_match.matched_evaluation_role if seq_match else "",
        "target_alias_match": bool_token(target_match is not None),
        "matched_canonical_target": target_match.matched_canonical_target if target_match else "",
        "target_alias_match_type": target_match.match_type if target_match else "",
        "both_sequence_and_target": bool_token(both),
        "requires_review": bool_token(review),
        "leakage_exclusion_proposed": bool_token(proposed),
        "comparison_representation": "comparison_form_full_and_core_U_to_T",
        "notes": ";".join(notes),
    }

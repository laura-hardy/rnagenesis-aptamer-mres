"""AptaIndex CHECKPOINT-1 structured review: schema and recommendations.

Reuses the AptaDB structured-review field vocabulary and fail-closed
validation. Does not fill ``manual_*`` decisions, apply trims, or start S4.
Recommendations live in separate fields and must never masquerade as human
decisions. This milestone prepares review only; it does not apply it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, Mapping

from adapters.aptadb_checkpoint1_review import (
    AptaDBCheckpoint1ReviewError,
    MANUAL_FIELDS,
    _blank,
    format_validation_markdown,
    parse_review_reasons,
    populate_record_recommendations,
    validate_review_package,
)

DEFAULT_RECOMMENDATIONS_REL: Final[str] = (
    "config/checkpoint_reviews/aptaindex_checkpoint1_recommendations.json"
)
DEFAULT_POLICY_REL: Final[str] = "config/source_eligibility/aptaindex.json"

JUDGEMENT_SUBCATEGORY_KEYS: Final[tuple[str, ...]] = (
    "unsupported_chemical_notation",
    "source_type_token_disagreement",
    "l_rna_stereochemistry",
    "l_dna_stereochemistry",
    "chimeric_molecule",
    "mixed_t_u",
)

REASON_TO_RECOMMENDATION_KEY: Final[Mapping[str, str]] = {
    "unsupported_chemical_notation": "unsupported_chemical_notation",
    "source_type_token_disagreement": "source_type_token_disagreement",
    "l_rna": "l_rna_stereochemistry",
    "l_dna": "l_dna_stereochemistry",
    "chimeric": "chimeric_molecule",
    "mixed_t_u": "mixed_t_u",
    "molecule_type_unresolved": "judgement_dependent",
}


class AptaIndexCheckpoint1ReviewError(ValueError):
    """Invalid AptaIndex CHECKPOINT-1 review schema or prepare input."""


def load_review_recommendations(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("source_key") != "aptaindex":
        raise AptaIndexCheckpoint1ReviewError(
            "recommendation file source_key must be aptaindex"
        )
    return payload


def populate_aptaindex_recommendations(
    row: dict[str, str],
    *,
    recommendations: Mapping[str, Any],
) -> dict[str, str]:
    """Fill recommendation fields only. Never writes ``manual_*`` values."""
    try:
        out = populate_record_recommendations(row, recommendations=recommendations)
    except AptaDBCheckpoint1ReviewError as exc:
        raise AptaIndexCheckpoint1ReviewError(str(exc)) from exc

    reasons = parse_review_reasons(out.get("checkpoint_review_reasons", ""))
    if not out.get("review_recommendation"):
        cfg: Mapping[str, Any] = {}
        for token in (
            "unsupported_chemical_notation",
            "source_type_token_disagreement",
            "l_rna",
            "l_dna",
            "chimeric",
            "mixed_t_u",
        ):
            if token in reasons:
                key = REASON_TO_RECOMMENDATION_KEY[token]
                cfg = recommendations.get(key) or {}
                break
        if not cfg and "judgement_dependent_technical" in reasons:
            cfg = recommendations.get("judgement_dependent") or {}
        elif not cfg and "constant_region_proposal" in reasons:
            cfg = recommendations.get("known_motif") or {}
        if cfg:
            out["review_recommendation"] = _blank(cfg.get("review_recommendation"))
            out["review_rationale"] = _blank(cfg.get("rationale"))
            out["requires_specific_human_decision"] = (
                "true" if cfg.get("requires_specific_human_decision") else "false"
            )
            out["recommended_manual_decision"] = _blank(
                cfg.get("recommended_manual_decision")
            )
            out["recommended_trim_action"] = _blank(
                cfg.get("recommended_trim_action")
            )
            five = cfg.get("recommended_trim_5p_nt", "")
            three = cfg.get("recommended_trim_3p_nt", "")
            if five not in (None, ""):
                out["recommended_trim_5p_nt"] = str(five)
            if three not in (None, ""):
                out["recommended_trim_3p_nt"] = str(three)
            if "recommended_sequence_corrected" in out:
                out["recommended_sequence_corrected"] = ""
            if "recommended_sequence_correction_op" in out:
                if not cfg.get("sequence_correction_op"):
                    out["recommended_sequence_correction_op"] = ""
    for name in MANUAL_FIELDS:
        out[name] = ""
    return out


def build_review_readme() -> str:
    return """# AptaIndex CHECKPOINT-1 human review

This package is a human-review gate. Machine recommendations are guidance
only. Do not treat `review_recommendation` as a completed `manual_decision`.

AptaIndex sequences are restricted. Keep this local package under `data/`.
Do not copy real sequences into tracked docs, commits, or chat.

## What S3 already did automatically

- Missing sequence → `missing_sequence` rejection log (not in this queue).
- Source-declared peptide molecules → `non_nucleic_acid_molecule` rejection
  log. These are peptide aptamers, not peptide targets.
- Straightforward ssDNA (`molecule_type=ssDNA`, `chemistry=DNA`) → parked,
  not rejected, and not T→U converted.
- Length 20–100 nt on successfully parsed nucleotide `sequence_core`.
  Out-of-range records are in the rejection log unless a trim pushed a
  previously in-range full sequence out of range (none expected).
- Straightforward RNA and 2′-F-RNA remain technically eligible at S3.

## What requires human judgement

Fill `manual_decision` for every active review row.

Permitted `manual_decision` values: `keep` / `drop` / `edit`.

### Batch 01 — judgement-dependent technical / chemistry

- Unsupported chemical notation: parser failed closed. Do not auto-edit.
  The `parser_reason_category` column is a redacted syntax class.
- Source Type vs token-family disagreement: do not silently override
  molecule or chemistry.
- L-RNA / L-DNA: preserve stereochemistry; do not flatten to ordinary
  RNA/ssDNA.
- Chimeric: preserve source Type and token-family evidence.
- Mixed T/U after chemical parsing: do not silently convert.

### Batch 02 — constant-region proposals

Known-motif proposals are unapplied. Recommend a trim decision; do not
auto-approve.

### Batch 03 — length-boundary audit

Otherwise-kept 20–25 nt and 90–100 nt records. Audit only unless another
judgement reason is also present.

### Batch 04 — random kept audit

Deterministic sample of technically eligible RNA/2F-RNA records (seed 42,
size 30). Audit only.

## What is deferred

- Blank raw Target is not an S3 `missing_target` reject.
- Sequences associated with more than one distinct target string are not
  S3 conflicts. The corpus grain is one `(sequence, target)` pair.
- Target Type, including Target Type = Peptide, does not decide molecule
  eligibility and is not used for protein/non-protein routing at S3.
- Evidence ladder, affinity, leakage exclusion, global S4, deduplication
  and clustering were not run.

## Recommendations vs decisions

`review_recommendation` / `review_rationale` are machine guidance.
`manual_*` fields must remain blank until Laura records a decision.
Apply will fail closed if any active row is unresolved.
"""

"""AptaIndex CHECKPOINT-1 structured review: schema, recommendations, apply.

Reuses the AptaDB structured-review field vocabulary and fail-closed
validation. Recommendations live in separate fields and must never masquerade
as human decisions.

Apply preserves the S1/S2 contract: AptaIndex ``sequence_raw`` is chemical
notation and is never passed to generic nucleotide normalisation. Human
molecule/chemistry overrides supersede stale S2 ``mapping_class``. Keep
preserves the pre-review S3 route. Drop uses the shared ``manual_reject``
exclusion. Edit reclassifies from the resolved human state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from adapters.aptadb_checkpoint1_review import (
    AptaDBCheckpoint1ReviewError,
    AppliedRecordResult,
    MANUAL_FIELDS,
    _blank,
    _corpus_only,
    _molecule_chemistry_consistent,
    apply_numeric_terminal_trim,
    combined_trim_exceeds_review_threshold,
    combined_trim_fraction,
    default_chemistry_for_molecule,
    format_large_trim_provenance,
    format_validation_markdown,
    is_explicit_human_trim_authorisation,
    parse_review_reasons,
    populate_record_recommendations,
    resolve_effective_trim,
    validate_review_package,
)
from adapters.aptaindex_s3 import (
    DECISION_COLUMNS,
    PRIMARY_ROUTE_CHEMISTRY_REVIEW,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    _build_park_row,
    _build_rejection_row,
    classify_aptaindex_record,
)
from adapters.aptaindex_sequence_parser import STATUS_SUCCESS
from common.corpus_schema import (
    CHEMISTRY_VOCABULARY,
    S3_FORBIDDEN_FIELDS,
    format_qc_flags,
)
from common.eligibility import (
    EligibilityPolicy,
    format_reasons,
    load_eligibility_policy,
    parse_qc_flags,
)
from common.sequence_normalisation import (
    TRIM_CONFIDENCE_HIGH,
    TRIM_CONFIDENCE_MEDIUM,
    TRIM_CONFIDENCE_NA,
    normalise_sequence,
)

DEFAULT_RECOMMENDATIONS_REL: Final[str] = (
    "config/checkpoint_reviews/aptaindex_checkpoint1_recommendations.json"
)
DEFAULT_POLICY_REL: Final[str] = "config/source_eligibility/aptaindex.json"
MANUAL_REJECT_REASON: Final[str] = "manual_reject"
ALPHABET_CHEMICAL_NOTATION: Final[str] = "chemical_notation"
ALLOWED_MOLECULE_OVERRIDES: Final[frozenset[str]] = frozenset(
    {"", "RNA", "ssDNA", "DNA"}
)
SOURCE_TYPE_FALLBACK: Final[Mapping[str, tuple[str, str]]] = {
    "DNA": ("ssDNA", "DNA"),
    "RNA": ("RNA", "RNA"),
    "2'-F-RNA": ("RNA", "2F-RNA"),
}
STALE_MAPPING_QC_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "unsupported_notation",
        "source_type_token_disagreement",
        "mixed_token_chemistry",
        "molecule_type_unknown",
        "source_type_blank",
        "source_type_unsupported",
        "missing_sequence",
        "parser_not_applicable_peptide",
    }
)
ELIGIBLE_RNA_CHEMISTRIES: Final[frozenset[str]] = frozenset({"RNA", "2F-RNA"})
DNA_MOLECULES: Final[frozenset[str]] = frozenset({"ssDNA", "DNA"})

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


def load_default_policy(repo_root: Path) -> EligibilityPolicy:
    return load_eligibility_policy(repo_root / DEFAULT_POLICY_REL)


def mapping_class_for_resolved_state(molecule: str, chemistry: str) -> str | None:
    """Return the S2 mapping_class implied by the resolved human state.

    Unusual RNA chemistries that are not corpus-eligible at S3 keep a
    chemistry-review mapping so they are not promoted to ordinary RNA.
    Unresolved states return ``None`` so the previous mapping is retained.
    """
    mol = (molecule or "").strip()
    chem = (chemistry or "").strip()
    if mol in DNA_MOLECULES and chem in {"DNA", ""}:
        return "straightforward_dna"
    if mol == "RNA" and chem == "RNA":
        return "straightforward_rna"
    if mol == "RNA" and chem == "2F-RNA":
        return "straightforward_2f_rna"
    if mol == "RNA" and chem == "mixed":
        return "mixed_token_chemistry"
    if mol == "RNA" and chem in {"2NH2-RNA", "2OMe-RNA"}:
        return "type_token_disagreement"
    return None


def source_type_for_resolved_state(molecule: str, chemistry: str) -> str:
    """Working source Type used only for post-review S3 reclassification."""
    mol = (molecule or "").strip()
    chem = (chemistry or "").strip()
    if mol in DNA_MOLECULES:
        return "DNA"
    if chem == "2F-RNA":
        return "2'-F-RNA"
    if mol == "RNA":
        return "RNA"
    return ""


def canonicalise_molecule_override(molecule: str) -> str:
    text = (molecule or "").strip()
    if text == "DNA":
        return "ssDNA"
    return text


def resolve_molecule_and_chemistry(
    *,
    review_row: Mapping[str, str],
    canonical: Mapping[str, str],
    source_metadata: Mapping[str, str],
    s2_qc: Mapping[str, str],
) -> tuple[str, str, bool, bool]:
    """Resolve molecule/chemistry from human overrides, then S2, then Type."""
    original_molecule = canonical.get("molecule_type", "")
    original_chemistry = canonical.get("chemistry", "")
    mol_override = _blank(review_row.get("manual_molecule_type_override"))
    chem_override = _blank(review_row.get("manual_chemistry_override"))
    if mol_override and mol_override not in ALLOWED_MOLECULE_OVERRIDES:
        raise AptaIndexCheckpoint1ReviewError(
            f"Unsupported molecule override for {canonical.get('record_id')!r}"
        )
    if chem_override and chem_override not in CHEMISTRY_VOCABULARY:
        raise AptaIndexCheckpoint1ReviewError(
            f"Unsupported chemistry override for {canonical.get('record_id')!r}"
        )

    molecule = canonicalise_molecule_override(mol_override) or original_molecule
    chemistry = chem_override
    if not chemistry:
        if mol_override and canonicalise_molecule_override(mol_override) != (
            original_molecule
        ):
            chemistry = default_chemistry_for_molecule(molecule)
        else:
            chemistry = original_chemistry

    source_type = (
        _blank(source_metadata.get("aptaindex_type"))
        or _blank(review_row.get("aptaindex_type"))
        or _blank(s2_qc.get("source_type"))
    )
    if (molecule in {"", "unknown"} or chemistry in {"", "unknown"}) and (
        source_type in SOURCE_TYPE_FALLBACK
    ):
        fallback_mol, fallback_chem = SOURCE_TYPE_FALLBACK[source_type]
        if molecule in {"", "unknown"}:
            molecule = fallback_mol
        if chemistry in {"", "unknown"}:
            chemistry = fallback_chem

    if not _molecule_chemistry_consistent(molecule, chemistry):
        raise AptaIndexCheckpoint1ReviewError(
            f"Molecule/chemistry override conflict for "
            f"{canonical.get('record_id')!r}"
        )
    mol_overridden = molecule != original_molecule
    chem_overridden = chemistry != original_chemistry
    return molecule, chemistry, mol_overridden, chem_overridden


def _decision_from_mapping(source: Mapping[str, str]) -> dict[str, str]:
    return {column: str(source.get(column, "") or "") for column in DECISION_COLUMNS}


def _strip_stale_mapping_flags(flags: Sequence[str]) -> list[str]:
    return [flag for flag in flags if flag not in STALE_MAPPING_QC_FLAGS]


def _source_override_notes(
    *,
    original_molecule: str,
    reviewed_molecule: str,
    original_chemistry: str,
    reviewed_chemistry: str,
) -> list[str]:
    notes: list[str] = []
    if original_molecule != reviewed_molecule:
        notes.append(
            f"manual_molecule_override original={original_molecule} "
            f"reviewed={reviewed_molecule}"
        )
    if original_chemistry != reviewed_chemistry:
        notes.append(
            f"manual_chemistry_override original={original_chemistry} "
            f"reviewed={reviewed_chemistry}"
        )
    return notes


def apply_reviewed_record(
    *,
    canonical: Mapping[str, str],
    review_row: Mapping[str, str],
    source_metadata: Mapping[str, str],
    s2_qc: Mapping[str, str],
    policy: EligibilityPolicy,
    proposals: Sequence[Mapping[str, str]] = (),
    group_row: Mapping[str, str] | None = None,
    machine_five: int = 0,
    machine_three: int = 0,
) -> AppliedRecordResult:
    """Apply one reviewed AptaIndex record through S3 routing.

    Never passes chemical ``sequence_raw`` to generic ``normalise_sequence``.
    Does not populate S4 fields.
    """
    record_id = canonical["record_id"]
    original_raw = canonical["sequence_raw"]
    original_molecule = canonical.get("molecule_type", "")
    original_chemistry = canonical.get("chemistry", "")
    original_mapping = (s2_qc.get("mapping_class") or "").strip()
    route_before = review_row.get("primary_route", "")
    decision = _blank(review_row.get("manual_decision"))
    if decision not in {"keep", "drop", "edit"}:
        raise AptaIndexCheckpoint1ReviewError(
            f"Cannot apply unresolved manual_decision for {record_id!r}"
        )

    if decision == "keep":
        return _apply_keep(
            canonical=canonical,
            review_row=review_row,
            source_metadata=source_metadata,
            s2_qc=s2_qc,
            route_before=route_before,
        )
    if decision == "drop":
        return _apply_drop(
            canonical=canonical,
            review_row=review_row,
            route_before=route_before,
        )
    return _apply_edit(
        canonical=canonical,
        review_row=review_row,
        source_metadata=source_metadata,
        s2_qc=s2_qc,
        policy=policy,
        proposals=proposals,
        group_row=group_row,
        machine_five=machine_five,
        machine_three=machine_three,
        original_raw=original_raw,
        original_molecule=original_molecule,
        original_chemistry=original_chemistry,
        original_mapping=original_mapping,
        route_before=route_before,
    )


def _apply_keep(
    *,
    canonical: Mapping[str, str],
    review_row: Mapping[str, str],
    source_metadata: Mapping[str, str],
    s2_qc: Mapping[str, str],
    route_before: str,
) -> AppliedRecordResult:
    """Preserve the pre-review S3 route. Do not re-normalise or reclassify."""
    record_id = canonical["record_id"]
    updated = _corpus_only(canonical)
    for field_name in S3_FORBIDDEN_FIELDS:
        updated[field_name] = ""
    note_parts = ["checkpoint1_manual_decision=keep"]
    if _blank(review_row.get("audit_only_row")).lower() == "true":
        note_parts.append("keep_current_route=true")
    if review_row.get("manual_notes"):
        note_parts.append("reviewer_notes_present=true")
    note_parts.append(f"route_before={route_before}")
    note_parts.append(f"route_after={route_before}")
    updated["notes"] = "|".join(part for part in note_parts if part)
    decision_row = _decision_from_mapping(review_row)
    decision_row["notes"] = updated["notes"]
    rejection_row = None
    park_row = None
    if route_before == PRIMARY_ROUTE_REJECT:
        rejection_row = _build_rejection_row(
            canonical=updated, decision=decision_row
        )
    elif route_before in {PRIMARY_ROUTE_SSDNA, PRIMARY_ROUTE_CHEMISTRY_REVIEW}:
        park_row = _build_park_row(
            canonical=updated,
            decision=decision_row,
            source_metadata=source_metadata,
            s2_qc=s2_qc,
        )
    core_len = (
        int(canonical["sequence_length_core"])
        if str(canonical.get("sequence_length_core") or "").isdigit()
        else 0
    )
    full_len = (
        int(canonical["sequence_length_full"])
        if str(canonical.get("sequence_length_full") or "").isdigit()
        else 0
    )
    return AppliedRecordResult(
        record_id=record_id,
        sequence_raw=canonical.get("sequence_raw", ""),
        sequence_full=canonical.get("sequence_full", ""),
        sequence_core=canonical.get("sequence_core", ""),
        sequence_length_full=full_len,
        sequence_length_core=core_len,
        molecule_type=canonical.get("molecule_type", ""),
        chemistry=canonical.get("chemistry", ""),
        alphabet_as_reported=canonical.get("alphabet_as_reported", ""),
        t_to_u_applied=canonical.get("t_to_u_applied", "") == "true",
        trim_status=canonical.get("trim_status", ""),
        trim_confidence=canonical.get("trim_confidence", "") or TRIM_CONFIDENCE_NA,
        primary_route_before=route_before,
        primary_route_after=route_before,
        notes=updated["notes"],
        canonical=updated,
        proposed_decision=decision_row.get("proposed_decision", ""),
        primary_reason=decision_row.get("primary_reason", ""),
        decision=decision_row,
        rejection_row=rejection_row,
        park_row=park_row,
    )


def _apply_drop(
    *,
    canonical: Mapping[str, str],
    review_row: Mapping[str, str],
    route_before: str,
) -> AppliedRecordResult:
    """Exclude the record via the shared ``manual_reject`` reason."""
    record_id = canonical["record_id"]
    original_reason = review_row.get("primary_reason", "")
    updated = _corpus_only(canonical)
    for field_name in S3_FORBIDDEN_FIELDS:
        updated[field_name] = ""
    note_parts = [
        "checkpoint1_manual_decision=drop",
        "human_reviewed_exclusion=true",
    ]
    if original_reason:
        note_parts.append(f"original_primary_reason={original_reason}")
    if route_before:
        note_parts.append(f"original_route={route_before}")
    if review_row.get("manual_notes"):
        note_parts.append("reviewer_notes_present=true")
    note_parts.append(f"route_before={route_before}")
    note_parts.append(f"route_after={PRIMARY_ROUTE_REJECT}")
    updated["notes"] = "|".join(part for part in note_parts if part)
    decision_row = _decision_from_mapping(review_row)
    decision_row["proposed_decision"] = "proposed_reject"
    decision_row["primary_reason"] = MANUAL_REJECT_REASON
    decision_row["secondary_reasons"] = format_reasons(
        part
        for part in (original_reason, review_row.get("secondary_reasons", ""))
        if part
    )
    decision_row["primary_route"] = PRIMARY_ROUTE_REJECT
    decision_row["notes"] = updated["notes"]
    rejection_row = _build_rejection_row(canonical=updated, decision=decision_row)
    extra = "checkpoint1_manual_decision=drop|human_reviewed_exclusion=true"
    detail = rejection_row.get("rejection_detail", "")
    rejection_row["rejection_detail"] = f"{detail}|{extra}" if detail else extra
    core_len = (
        int(canonical["sequence_length_core"])
        if str(canonical.get("sequence_length_core") or "").isdigit()
        else 0
    )
    full_len = (
        int(canonical["sequence_length_full"])
        if str(canonical.get("sequence_length_full") or "").isdigit()
        else 0
    )
    return AppliedRecordResult(
        record_id=record_id,
        sequence_raw=canonical.get("sequence_raw", ""),
        sequence_full=canonical.get("sequence_full", ""),
        sequence_core=canonical.get("sequence_core", ""),
        sequence_length_full=full_len,
        sequence_length_core=core_len,
        molecule_type=canonical.get("molecule_type", ""),
        chemistry=canonical.get("chemistry", ""),
        alphabet_as_reported=canonical.get("alphabet_as_reported", ""),
        t_to_u_applied=canonical.get("t_to_u_applied", "") == "true",
        trim_status=canonical.get("trim_status", ""),
        trim_confidence=canonical.get("trim_confidence", "") or TRIM_CONFIDENCE_NA,
        primary_route_before=route_before,
        primary_route_after=PRIMARY_ROUTE_REJECT,
        notes=updated["notes"],
        canonical=updated,
        proposed_decision="proposed_reject",
        primary_reason=MANUAL_REJECT_REASON,
        decision=decision_row,
        rejection_row=rejection_row,
        park_row=None,
    )


def _apply_edit(
    *,
    canonical: Mapping[str, str],
    review_row: Mapping[str, str],
    source_metadata: Mapping[str, str],
    s2_qc: Mapping[str, str],
    policy: EligibilityPolicy,
    proposals: Sequence[Mapping[str, str]],
    group_row: Mapping[str, str] | None,
    machine_five: int,
    machine_three: int,
    original_raw: str,
    original_molecule: str,
    original_chemistry: str,
    original_mapping: str,
    route_before: str,
) -> AppliedRecordResult:
    record_id = canonical["record_id"]
    molecule, chemistry, mol_overridden, chem_overridden = (
        resolve_molecule_and_chemistry(
            review_row=review_row,
            canonical=canonical,
            source_metadata=source_metadata,
            s2_qc=s2_qc,
        )
    )
    corrected = _blank(review_row.get("manual_sequence_corrected"))
    sequence_corrected = bool(corrected)
    t_to_u_applied = canonical.get("t_to_u_applied", "") == "true"
    alphabet_as_reported = (
        canonical.get("alphabet_as_reported", "") or ALPHABET_CHEMICAL_NOTATION
    )
    norm_flags: list[str] = []

    if sequence_corrected:
        # Human-corrected value is already a nucleotide representation.
        # Never treat it as AptaIndex chemical notation.
        norm = normalise_sequence(corrected, molecule_type=molecule)
        sequence_full = norm.sequence_full or ""
        t_to_u_applied = bool(norm.t_to_u_applied)
        norm_flags = list(norm.qc_flags)
        alphabet_as_reported = ALPHABET_CHEMICAL_NOTATION
    else:
        sequence_full = canonical.get("sequence_full", "")
        if not sequence_full:
            raise AptaIndexCheckpoint1ReviewError(
                f"Edit of {record_id!r} has no nucleotide sequence: "
                "manual_sequence_corrected is empty and S2 sequence_full is empty"
            )

    sequence_core = sequence_full
    trim_status = canonical.get("trim_status") or "no_constants_detected"
    trim_confidence = canonical.get("trim_confidence") or TRIM_CONFIDENCE_NA
    applied_five = 0
    applied_three = 0
    trim_frac = 0.0
    large_trim_human_approved = False
    try:
        effective = resolve_effective_trim(
            review_row,
            group_row,
            machine_five=machine_five,
            machine_three=machine_three,
        )
    except AptaDBCheckpoint1ReviewError as exc:
        raise AptaIndexCheckpoint1ReviewError(str(exc)) from exc
    if effective is not None:
        human_authorised = is_explicit_human_trim_authorisation(effective.action)
        try:
            sequence_core = apply_numeric_terminal_trim(
                sequence_full,
                five_nt=effective.five_nt,
                three_nt=effective.three_nt,
                record_id=record_id,
                human_authorised=human_authorised,
            )
        except AptaDBCheckpoint1ReviewError as exc:
            raise AptaIndexCheckpoint1ReviewError(str(exc)) from exc
        applied_five = effective.five_nt
        applied_three = effective.three_nt
        trim_frac = combined_trim_fraction(
            len(sequence_full), applied_five, applied_three
        )
        large_trim_human_approved = (
            human_authorised
            and combined_trim_exceeds_review_threshold(
                len(sequence_full), applied_five, applied_three
            )
        )
        source = review_row.get("constant_proposal_sources", "")
        if source == "known_motif" or "known_motif" in source:
            trim_confidence = TRIM_CONFIDENCE_HIGH
            trim_status = (
                "t7_removed"
                if applied_five and not applied_three
                else (
                    "t7_and_primers_removed"
                    if applied_five and applied_three
                    else "primers_removed"
                )
            )
        else:
            trim_confidence = TRIM_CONFIDENCE_MEDIUM
            trim_status = "primers_removed"
    if sequence_full and sequence_core and sequence_core not in sequence_full:
        raise AptaIndexCheckpoint1ReviewError(
            f"sequence_core is not a contiguous substring of reviewed "
            f"sequence_full for {record_id!r}"
        )

    resolved_mapping = mapping_class_for_resolved_state(molecule, chemistry)
    mapping_class = resolved_mapping or original_mapping
    working_source_type = source_type_for_resolved_state(molecule, chemistry) or (
        _blank(source_metadata.get("aptaindex_type"))
        or _blank(s2_qc.get("source_type"))
    )

    if sequence_corrected:
        qc_flag_values = _strip_stale_mapping_flags(norm_flags)
        qc_flag_values = [
            flag for flag in qc_flag_values if flag != "mixed_t_u"
        ]
        if effective is None:
            qc_flag_values.extend(
                flag
                for flag in parse_qc_flags(canonical.get("qc_flags", ""))
                if flag
                in {
                    "known_promoter_detected",
                    "constants_suspected_unresolved",
                    "trim_requires_review",
                }
            )
    else:
        qc_flag_values = _strip_stale_mapping_flags(
            list(parse_qc_flags(canonical.get("qc_flags", "")))
        )
    if large_trim_human_approved:
        qc_flag_values.append("large_trim_human_approved")

    updated = _corpus_only(canonical)
    updated["sequence_raw"] = original_raw
    updated["sequence_full"] = sequence_full
    updated["sequence_core"] = sequence_core
    updated["sequence_length_full"] = str(len(sequence_full)) if sequence_full else ""
    updated["sequence_length_core"] = str(len(sequence_core)) if sequence_core else ""
    updated["molecule_type"] = molecule
    updated["chemistry"] = chemistry
    updated["alphabet_as_reported"] = alphabet_as_reported
    updated["t_to_u_applied"] = "true" if t_to_u_applied else "false"
    updated["trim_status"] = trim_status
    updated["trim_confidence"] = trim_confidence
    updated["qc_flags"] = format_qc_flags(qc_flag_values)
    for field_name in S3_FORBIDDEN_FIELDS:
        updated[field_name] = ""

    qc = dict(s2_qc)
    qc["record_id"] = record_id
    qc["molecule_type"] = molecule
    qc["chemistry"] = chemistry
    qc["mapping_class"] = mapping_class
    qc["source_type"] = working_source_type
    qc["parser_status"] = (
        STATUS_SUCCESS if sequence_core else qc.get("parser_status", "")
    )
    qc["alphabet_as_reported"] = alphabet_as_reported
    qc["t_to_u_applied"] = updated["t_to_u_applied"]
    qc["mixed_t_u"] = (
        "true" if "mixed_t_u" in parse_qc_flags(updated["qc_flags"]) else "false"
    )
    qc["sequence_length_full"] = updated["sequence_length_full"]
    qc["sequence_length_core"] = updated["sequence_length_core"]
    qc["trim_status"] = trim_status
    qc["trim_confidence"] = trim_confidence
    qc["qc_flags"] = updated["qc_flags"]

    working_meta = dict(source_metadata)
    working_meta["aptaindex_type"] = working_source_type

    classified = classify_aptaindex_record(
        updated,
        qc,
        working_meta,
        policy=policy,
        proposals=proposals,
    )
    route_after = classified.decision["primary_route"]
    classified.canonical["sequence_raw"] = original_raw
    classified.canonical["alphabet_as_reported"] = alphabet_as_reported
    classified.canonical["t_to_u_applied"] = updated["t_to_u_applied"]
    classified.canonical["qc_flags"] = updated["qc_flags"]

    note_parts = ["checkpoint1_manual_decision=edit"]
    if sequence_corrected:
        note_parts.append("manual_sequence_correction_applied")
    note_parts.extend(
        _source_override_notes(
            original_molecule=original_molecule,
            reviewed_molecule=molecule,
            original_chemistry=original_chemistry,
            reviewed_chemistry=chemistry,
        )
    )
    if mapping_class != original_mapping:
        note_parts.append(
            f"mapping_class_original={original_mapping} "
            f"mapping_class_reviewed={mapping_class}"
        )
    if effective is not None:
        note_parts.append(
            f"manual_trim_action={effective.action};"
            f"applied_5p={applied_five};applied_3p={applied_three};"
            f"trim_source={effective.source};group={effective.group_id}"
        )
    elif _blank(review_row.get("manual_trim_action")) == "reject":
        note_parts.append("manual_trim_action=reject;no_additional_trim")
    if large_trim_human_approved:
        note_parts.append(
            format_large_trim_provenance(
                fraction=trim_frac,
                five_nt=applied_five,
                three_nt=applied_three,
                core_length=len(sequence_core),
                trim_source=effective.source if effective is not None else "",
                human_trim_action=effective.action if effective is not None else "",
                group_id=effective.group_id if effective is not None else "",
            )
        )
    if review_row.get("manual_notes"):
        note_parts.append("reviewer_notes_present=true")
    note_parts.append(f"route_before={route_before}")
    note_parts.append(f"route_after={route_after}")
    notes = "|".join(part for part in note_parts if part)
    classified.canonical["notes"] = notes
    classified.decision["notes"] = notes
    classified.decision["molecule_type"] = molecule
    classified.decision["chemistry"] = chemistry
    classified.decision["mapping_class"] = mapping_class
    classified.decision["alphabet_as_reported"] = alphabet_as_reported
    classified.decision["sequence_length_full"] = updated["sequence_length_full"]
    classified.decision["sequence_length_core"] = updated["sequence_length_core"]
    classified.decision["trim_status"] = trim_status
    classified.decision["trim_confidence"] = trim_confidence
    classified.decision["qc_flags"] = updated["qc_flags"]
    park_row = dict(classified.park_row) if classified.park_row else None
    if park_row is not None:
        park_row["molecule_type"] = molecule
        park_row["chemistry"] = chemistry
        park_row["mapping_class"] = mapping_class
        park_row["sequence_length_core"] = updated["sequence_length_core"]
        park_row["trim_status"] = trim_status
        park_row["trim_confidence"] = trim_confidence
        park_row["qc_flags"] = updated["qc_flags"]

    return AppliedRecordResult(
        record_id=record_id,
        sequence_raw=original_raw,
        sequence_full=sequence_full,
        sequence_core=sequence_core,
        sequence_length_full=len(sequence_full) if sequence_full else 0,
        sequence_length_core=len(sequence_core) if sequence_core else 0,
        molecule_type=molecule,
        chemistry=chemistry,
        alphabet_as_reported=alphabet_as_reported,
        t_to_u_applied=t_to_u_applied,
        trim_status=trim_status,
        trim_confidence=trim_confidence,
        primary_route_before=route_before,
        primary_route_after=route_after,
        notes=notes,
        canonical=classified.canonical,
        proposed_decision=classified.decision.get("proposed_decision", ""),
        primary_reason=classified.decision.get("primary_reason", ""),
        decision=classified.decision,
        rejection_row=(
            dict(classified.rejection_row) if classified.rejection_row else None
        ),
        park_row=park_row,
        applied_trim_5p_nt=applied_five,
        applied_trim_3p_nt=applied_three,
        trim_source=effective.source if effective is not None else "",
        sequence_corrected=sequence_corrected,
        molecule_overridden=mol_overridden or chem_overridden,
        large_trim_human_approved=large_trim_human_approved,
        trim_fraction=trim_frac,
    )


def apply_aptaindex_checkpoint1_package(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    canonical_by_id: Mapping[str, Mapping[str, str]],
    source_metadata_by_id: Mapping[str, Mapping[str, str]],
    s2_qc_by_id: Mapping[str, Mapping[str, str]],
    policy: EligibilityPolicy,
    proposals_by_record: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
    bulk_confirmation: Mapping[str, str] | None = None,
    allow_deferred: bool = False,
) -> tuple[list[AppliedRecordResult], Any]:
    """Apply a fully resolved AptaIndex CHECKPOINT-1 package.

    Fail-closed: unresolved or invalid fields raise.
    """
    report = validate_review_package(
        queue_rows=queue_rows,
        group_rows=group_rows,
        bulk_confirmation=bulk_confirmation,
        allow_deferred=allow_deferred,
    )
    if not report.ok:
        raise AptaIndexCheckpoint1ReviewError(
            "CHECKPOINT-1 cannot be applied while required human decisions "
            f"remain unresolved ({len(report.blocking_issues)} blocking issues)"
        )
    groups_by_id = {row["constant_group_id"]: row for row in group_rows}
    proposals_by_record = proposals_by_record or {}
    applied: list[AppliedRecordResult] = []
    for row in queue_rows:
        record_id = row["record_id"]
        group = groups_by_id.get(row.get("constant_group_id", ""), None)
        machine_five = 0
        machine_three = 0
        if group:
            machine_five = (
                int(group["machine_trim_5p_nt"] or 0)
                if str(group.get("machine_trim_5p_nt") or "").isdigit()
                else 0
            )
            machine_three = (
                int(group["machine_trim_3p_nt"] or 0)
                if str(group.get("machine_trim_3p_nt") or "").isdigit()
                else 0
            )
        if not machine_five and not machine_three:
            proposed = _blank(row.get("constant_proposed_trim_length"))
            side = _blank(row.get("constant_proposal_sides"))
            if proposed.isdigit() and side == "five_prime":
                machine_five = int(proposed)
            elif proposed.isdigit() and side == "three_prime":
                machine_three = int(proposed)
        applied.append(
            apply_reviewed_record(
                canonical=canonical_by_id[record_id],
                review_row=row,
                source_metadata=source_metadata_by_id[record_id],
                s2_qc=s2_qc_by_id[record_id],
                policy=policy,
                proposals=list(proposals_by_record.get(record_id, ())),
                group_row=group,
                machine_five=machine_five,
                machine_three=machine_three,
            )
        )
    return applied, report

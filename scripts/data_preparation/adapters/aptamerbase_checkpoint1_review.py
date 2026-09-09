"""AptamerBase CHECKPOINT-1 structured review, apply transform, and dry-run helpers.

Reuses the AptaDB structured-review field vocabulary and fail-closed
validation. Recommendations live in separate fields and must never masquerade
as human decisions. Real apply without explicit authorisation is refused.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from adapters.aptadb_checkpoint1_review import (
    ALLOWED_MOLECULE_OVERRIDES,
    AppliedRecordResult,
    AptaDBCheckpoint1ReviewError,
    MANUAL_FIELDS,
    _blank,
    _corpus_only,
    _molecule_chemistry_consistent,
    apply_numeric_terminal_trim,
    combined_trim_exceeds_review_threshold,
    combined_trim_fraction,
    format_large_trim_provenance,
    format_validation_markdown,
    is_explicit_human_trim_authorisation,
    materialize_bulk_audit_decisions,
    parse_review_reasons,
    populate_record_recommendations,
    resolve_effective_trim,
    validate_review_package,
)
from adapters.aptamerbase_s3 import (
    DECISION_COLUMNS,
    PRIMARY_ROUTE_CHEMISTRY_REVIEW,
    PRIMARY_ROUTE_CONSTRUCT,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    _build_park_row,
    _build_rejection_row,
    classify_aptamerbase_record,
    source_object_type,
)
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
    TRIM_CONFIDENCE_NA,
    normalise_sequence,
)
DEFAULT_RECOMMENDATIONS_REL: Final[str] = (
    "config/checkpoint_reviews/aptamerbase_checkpoint1_recommendations.json"
)
DEFAULT_POLICY_REL: Final[str] = "config/source_eligibility/aptamerbase.json"

REASON_TO_RECOMMENDATION_KEY: Final[Mapping[str, str]] = {
    "sequence_notation": "sequence_notation",
    "source_molecule_alphabet_conflict": "source_molecule_alphabet_conflict",
    "molecule_type_unresolved": "molecule_type_unresolved",
    "chemistry_requires_review": "chemistry_requires_review",
    "spiegelmer_l_rna": "chemistry_requires_review",
    "constant_region_proposal": "known_motif",
}


class AptamerBaseCheckpoint1ReviewError(ValueError):
    """Invalid AptamerBase CHECKPOINT-1 review schema or prepare input."""


def load_review_recommendations(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("source_key") != "aptamerbase":
        raise AptamerBaseCheckpoint1ReviewError(
            "recommendation file source_key must be aptamerbase"
        )
    return payload


def populate_aptamerbase_recommendations(
    row: dict[str, str],
    *,
    recommendations: Mapping[str, Any],
) -> dict[str, str]:
    """Fill recommendation fields only. Never writes ``manual_*`` values."""
    from adapters.aptadb_checkpoint1_review import AptaDBCheckpoint1ReviewError

    try:
        out = populate_record_recommendations(row, recommendations=recommendations)
    except AptaDBCheckpoint1ReviewError as exc:
        raise AptamerBaseCheckpoint1ReviewError(str(exc)) from exc

    reasons = parse_review_reasons(out.get("checkpoint_review_reasons", ""))
    if not out.get("review_recommendation"):
        cfg: Mapping[str, Any] = {}
        for token in (
            "source_molecule_alphabet_conflict",
            "sequence_notation",
            "molecule_type_unresolved",
            "chemistry_requires_review",
            "spiegelmer_l_rna",
            "constant_region_proposal",
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
    return """# AptamerBase CHECKPOINT-1 human review

This package is a human-review gate. Machine recommendations are guidance
only. Do not treat `review_recommendation` as a completed `manual_decision`.

AptamerBase sequences stay local under `data/`. Do not copy real sequences
into tracked docs, commits, or chat.

## What S3 already did automatically

- RDF-flattened secondary-structure and predicted-secondary-structure objects
  → `non_aptamer_source_object` rejection log (not in this queue).
- Missing aptamer-topic sequence → `missing_sequence` rejection log
  (not in this queue).
- Ordinary clean ssDNA (`molecule_type=ssDNA`) → parked, not rejected, and
  not T→U converted. Ordinary ssDNA is not in this queue.
- Ordinary length 20–100 nt failures with no plausible known-motif trim →
  rejection log, not this queue.
- Straightforward RNA and 2′-F-RNA remain technically eligible at S3.

## What requires human judgement

Fill `manual_decision` for every active review row.

Permitted `manual_decision` values: `keep` / `drop` / `edit`.

Permitted `manual_trim_action` values: `approve` / `override` / `reject` / `defer`.

### Batch 01 — sequence or source conflict

- Mixed T/U, ambiguous bases, alignment gaps, or invalid alphabet: the
  proposed technical rejection is the default, but source notation or
  modification may be recoverable. Do not automatically repair. Do not
  erase explicit RDF molecule identity.
- RDF DNA × U/RNA alphabet conflict: remain parked as ssDNA. Do not
  automatically convert to RNA.

### Batch 02 — molecule type unresolved

Aptamer-topic `molecule_type=unknown`. No U-only fallback to RNA and no
T-only fallback to DNA.

### Batch 03 — chemistry review

RNA with unsupported backbone/sugar chemistry, including Spiegelmer/L-RNA.
Do not flatten L-RNA to ordinary RNA chemistry. Ordinary terminal conjugates
already classified as RNA/2F-RNA at S2 are not chemistry blockers.

### Batch 04 — known-motif / construct

Known shared-motif proposals are unapplied. Record-level trim decisions
only; group-wise inference remains disabled.

### Batch 05 — length-boundary audit

Otherwise-kept 20–25 nt and 90–100 nt records. Audit only unless another
judgement reason is also present. These rows are `bulk_audit_eligible=true`.

### Batch 06 — random kept audit

Deterministic sample of technically eligible RNA/2F-RNA records (seed 42,
size 30). Audit only. Do not resample.

## Bulk audit confirmation (blank)

The 122 audit-only rows (92 length-boundary + 30 random-kept) do **not**
need 122 individual `keep` entries. They are marked `bulk_audit_eligible=true`
with machine recommendation `keep_current_route`.

Confirm them later, after judgement-required rows are settled, by setting
`confirm=true` in `aptamerbase_checkpoint1_bulk_audit_confirmation.csv`.
Do not populate `confirm` now. The validator remains fail-closed until that
explicit confirmation (and until the 169 judgement-required rows have
individual `manual_decision` values).

Decision-support tables (machine recommendations only) live under
`manual_review/audit/`. They do not collapse physical records and do not
populate human fields.

## What is deferred

- `target_name_raw` is empty by design. Do not parse `label`.
- Interactions, experiments, PMID, evidence, affinity, PDB, UniProt/Pfam,
  leakage, deduplication, Freebase-ID collapse, clustering, and global S4
  were not run.

CHECKPOINT-1 authorisation means only technical sequence/molecule/chemistry/
construct eligibility to enter later global S4.

## How to fill the form

1. Inspect the sequence-bearing queue.
2. Enter `manual_decision` (`keep` / `drop` / `edit`).
3. For known-motif rows, enter `manual_trim_action`.
4. For molecule/chemistry conflicts, use `manual_molecule_type_override`
   / `manual_chemistry_override` only when authorising a reviewed change.
5. Leave machine `review_recommendation*` columns unchanged.

Apply will fail closed until every active row is resolved. Human fields
are blank in this prepared package. `ready_for_application = 0` is the
expected state. Judgement-required rows remain unresolved. Bulk audit
confirmation is blank.

CHECKPOINT-1 package generated.
No human decisions applied.
No AptamerBase record is authorised for S4 yet.
The pipeline is stopped awaiting Laura CHECKPOINT-1 review.
Global S4 has not been run.
"""


MANUAL_REJECT_REASON: Final[str] = "manual_reject"
T7_MOTIF_DNA: Final[str] = "TAATACGACTCACTATA"
T7_MOTIF_RNA: Final[str] = "UAAUACGACUCACUAUA"
T7_MOTIFS: Final[frozenset[str]] = frozenset({T7_MOTIF_DNA, T7_MOTIF_RNA})
STALE_SYNTAX_QC_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "mixed_t_u",
        "invalid_character",
        "ambiguous_base",
        "alignment_gaps",
        "source_molecule_alphabet_conflict",
        "t_in_reported_rna",
        "u_in_reported_dna",
    }
)
UNRESOLVED_TRIM_QC_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "known_promoter_detected",
        "constants_suspected_unresolved",
        "trim_requires_review",
    }
)
PARK_ROUTES: Final[frozenset[str]] = frozenset(
    {
        PRIMARY_ROUTE_SSDNA,
        PRIMARY_ROUTE_MOLECULE,
        PRIMARY_ROUTE_CHEMISTRY_REVIEW,
        PRIMARY_ROUTE_CONSTRUCT,
    }
)
PERMITTED_REVIEW_DRIFT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "manual_decision",
        "manual_sequence_corrected",
        "manual_molecule_type_override",
        "manual_chemistry_override",
        "manual_trim_action",
        "manual_trim_5p_nt",
        "manual_trim_3p_nt",
        "manual_notes",
    }
)
_RNA_ALPHABET = re.compile(r"^[ACGU]+$")
_DNA_ALPHABET = re.compile(r"^[ACGT]+$")


def load_default_policy(repo_root: Path) -> EligibilityPolicy:
    return load_eligibility_policy(repo_root / DEFAULT_POLICY_REL)


def resolve_molecule_and_chemistry(
    *,
    review_row: Mapping[str, str],
    canonical: Mapping[str, str],
) -> tuple[str, str, bool, bool]:
    """Human overrides supersede stale S2/RDF typing. Never infer RNA chemistry.

    A human ``unknown`` chemistry override is intentional and must route to
    chemistry park for RNA. Do not default chemistry to RNA from molecule type.
    """
    original_molecule = canonical.get("molecule_type", "")
    original_chemistry = canonical.get("chemistry", "")
    mol_override = _blank(review_row.get("manual_molecule_type_override"))
    chem_override = _blank(review_row.get("manual_chemistry_override"))
    if mol_override and mol_override not in ALLOWED_MOLECULE_OVERRIDES:
        raise AptamerBaseCheckpoint1ReviewError(
            f"Unsupported molecule override for {canonical.get('record_id')!r}"
        )
    if chem_override and chem_override not in CHEMISTRY_VOCABULARY:
        raise AptamerBaseCheckpoint1ReviewError(
            f"Unsupported chemistry override for {canonical.get('record_id')!r}"
        )

    molecule = mol_override or original_molecule
    if chem_override:
        chemistry = chem_override
    elif mol_override == "ssDNA" and original_chemistry in {"", "unknown"}:
        chemistry = "DNA"
    else:
        chemistry = original_chemistry

    if not _molecule_chemistry_consistent(molecule, chemistry):
        raise AptamerBaseCheckpoint1ReviewError(
            f"Molecule/chemistry override conflict for "
            f"{canonical.get('record_id')!r}"
        )
    return (
        molecule,
        chemistry,
        molecule != original_molecule,
        chemistry != original_chemistry,
    )


def _decision_from_mapping(source: Mapping[str, str]) -> dict[str, str]:
    return {column: str(source.get(column, "") or "") for column in DECISION_COLUMNS}


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
        notes.append("reviewed_source_override=true")
    if original_chemistry != reviewed_chemistry:
        notes.append(
            f"manual_chemistry_override original={original_chemistry} "
            f"reviewed={reviewed_chemistry}"
        )
        if not any(part.startswith("reviewed_source_override=") for part in notes):
            notes.append("reviewed_source_override=true")
    return notes


def _assert_known_motif_terminal(sequence_full: str, record_id: str) -> None:
    prefix = sequence_full[:17]
    if prefix not in T7_MOTIFS:
        raise AptamerBaseCheckpoint1ReviewError(
            f"Approved motif trim for {record_id!r} does not exactly match "
            "the frozen 5-prime t7_promoter_minimal terminal"
        )


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
    """Apply one reviewed AptamerBase record through S3 routing.

    ``sequence_raw`` is immutable. Human molecule/chemistry overrides supersede
    stale S2/RDF classification. RDF provenance flags are not rewritten.
    """
    record_id = canonical["record_id"]
    original_raw = canonical["sequence_raw"]
    original_molecule = canonical.get("molecule_type", "")
    original_chemistry = canonical.get("chemistry", "")
    route_before = review_row.get("primary_route", "")
    decision = _blank(review_row.get("manual_decision"))
    if decision not in {"keep", "drop", "edit"}:
        raise AptamerBaseCheckpoint1ReviewError(
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
            source_metadata=source_metadata,
            s2_qc=s2_qc,
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
    object_type = source_object_type(s2_qc, source_metadata) or review_row.get(
        "source_object_type", "aptamer"
    )
    if route_before == PRIMARY_ROUTE_REJECT:
        rejection_row = _build_rejection_row(
            canonical=updated,
            decision=decision_row,
            object_type=object_type,
            source_metadata=source_metadata,
        )
    elif route_before in PARK_ROUTES:
        park_row = _build_park_row(
            canonical=updated,
            decision=decision_row,
            source_metadata=source_metadata,
            s2_qc=s2_qc,
            object_type=object_type,
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
    source_metadata: Mapping[str, str],
    s2_qc: Mapping[str, str],
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
    object_type = source_object_type(s2_qc, source_metadata) or review_row.get(
        "source_object_type", "aptamer"
    )
    rejection_row = _build_rejection_row(
        canonical=updated,
        decision=decision_row,
        object_type=object_type,
        source_metadata=source_metadata,
    )
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
    route_before: str,
) -> AppliedRecordResult:
    record_id = canonical["record_id"]
    molecule, chemistry, mol_overridden, chem_overridden = (
        resolve_molecule_and_chemistry(
            review_row=review_row,
            canonical=canonical,
        )
    )
    corrected = _blank(review_row.get("manual_sequence_corrected"))
    sequence_corrected = bool(corrected)
    original_full = canonical.get("sequence_full", "")
    t_to_u_applied = canonical.get("t_to_u_applied", "") == "true"
    alphabet_as_reported = canonical.get("alphabet_as_reported", "")
    norm_flags: list[str] = []

    if sequence_corrected:
        human_t_to_u = "T" in original_full and corrected == original_full.replace(
            "T", "U"
        )
        if molecule == "RNA" and not _RNA_ALPHABET.fullmatch(corrected):
            raise AptamerBaseCheckpoint1ReviewError(
                f"RNA sequence correction for {record_id!r} is not A/C/G/U"
            )
        if molecule in {"ssDNA", "DNA"} and "U" in corrected:
            raise AptamerBaseCheckpoint1ReviewError(
                f"ssDNA sequence correction for {record_id!r} must not introduce U"
            )
        norm = normalise_sequence(corrected, molecule_type=molecule)
        sequence_full = norm.sequence_full or ""
        t_to_u_applied = bool(norm.t_to_u_applied) or human_t_to_u
        if molecule == "RNA" and human_t_to_u:
            # Reviewed string is already A/C/G/U; do not convert again.
            sequence_full = corrected
            t_to_u_applied = True
        norm_flags = [
            flag for flag in list(norm.qc_flags) if flag not in STALE_SYNTAX_QC_FLAGS
        ]
        alphabet_as_reported = norm.alphabet_as_reported
        if molecule == "RNA" and _RNA_ALPHABET.fullmatch(sequence_full):
            alphabet_as_reported = "RNA"
            norm_flags = [flag for flag in norm_flags if flag != "mixed_t_u"]
        if molecule in {"ssDNA", "DNA"} and _DNA_ALPHABET.fullmatch(sequence_full):
            alphabet_as_reported = "DNA_T"
    else:
        sequence_full = original_full
        if not sequence_full:
            raise AptamerBaseCheckpoint1ReviewError(
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
        raise AptamerBaseCheckpoint1ReviewError(str(exc)) from exc
    if effective is not None:
        if effective.five_nt != 17 or effective.three_nt != 0:
            raise AptamerBaseCheckpoint1ReviewError(
                f"Only the frozen 17/0 known-motif trim is authorised for "
                f"{record_id!r}"
            )
        _assert_known_motif_terminal(sequence_full, record_id)
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
            raise AptamerBaseCheckpoint1ReviewError(str(exc)) from exc
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
        trim_confidence = TRIM_CONFIDENCE_HIGH
        trim_status = "t7_removed"
    if sequence_full and sequence_core and sequence_core not in sequence_full:
        raise AptamerBaseCheckpoint1ReviewError(
            f"sequence_core is not a contiguous substring of reviewed "
            f"sequence_full for {record_id!r}"
        )

    if sequence_corrected:
        qc_flag_values = list(norm_flags)
        if effective is None:
            qc_flag_values.extend(
                flag
                for flag in parse_qc_flags(canonical.get("qc_flags", ""))
                if flag in UNRESOLVED_TRIM_QC_FLAGS
            )
    else:
        qc_flag_values = [
            flag
            for flag in parse_qc_flags(canonical.get("qc_flags", ""))
            if flag not in STALE_SYNTAX_QC_FLAGS
        ]
    if effective is not None:
        qc_flag_values = [
            flag for flag in qc_flag_values if flag not in UNRESOLVED_TRIM_QC_FLAGS
        ]
    if mol_overridden or chem_overridden:
        qc_flag_values = [
            flag
            for flag in qc_flag_values
            if flag != "source_molecule_alphabet_conflict"
        ]
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
    qc["alphabet_as_reported"] = alphabet_as_reported
    qc["t_to_u_applied"] = updated["t_to_u_applied"]
    qc["sequence_length_full"] = updated["sequence_length_full"]
    qc["sequence_length_core"] = updated["sequence_length_core"]
    qc["trim_status"] = trim_status
    qc["trim_confidence"] = trim_confidence
    qc["qc_flags"] = updated["qc_flags"]
    # RDF molecule flags remain source provenance.

    classified = classify_aptamerbase_record(
        updated,
        qc,
        source_metadata,
        policy=policy,
        proposals=list(proposals),
    )
    route_after = classified.decision["primary_route"]
    classified.canonical["sequence_raw"] = original_raw
    classified.canonical["alphabet_as_reported"] = alphabet_as_reported
    classified.canonical["t_to_u_applied"] = updated["t_to_u_applied"]
    classified.canonical["qc_flags"] = updated["qc_flags"]
    classified.canonical["molecule_type"] = molecule
    classified.canonical["chemistry"] = chemistry

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
    classified.decision["alphabet_as_reported"] = alphabet_as_reported
    classified.decision["sequence_length_full"] = updated["sequence_length_full"]
    classified.decision["sequence_length_core"] = updated["sequence_length_core"]
    classified.decision["trim_status"] = trim_status
    classified.decision["trim_confidence"] = trim_confidence
    classified.decision["qc_flags"] = updated["qc_flags"]
    classified.decision["rdf_has_rna"] = s2_qc.get("rdf_has_rna", "")
    classified.decision["rdf_has_dna"] = s2_qc.get("rdf_has_dna", "")
    park_row = dict(classified.park_row) if classified.park_row else None
    if park_row is not None:
        park_row["molecule_type"] = molecule
        park_row["chemistry"] = chemistry
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


def _working_queue_rows(
    queue_rows: Sequence[Mapping[str, str]],
    bulk_confirmation: Mapping[str, str] | None,
) -> list[dict[str, str]]:
    """Materialise bulk-confirmed audit-only keep in memory only."""
    if bulk_confirmation is None:
        return [dict(row) for row in queue_rows]
    if _blank(bulk_confirmation.get("confirm")).lower() != "true":
        return [dict(row) for row in queue_rows]
    try:
        return materialize_bulk_audit_decisions(queue_rows, bulk_confirmation)
    except AptaDBCheckpoint1ReviewError as exc:
        raise AptamerBaseCheckpoint1ReviewError(str(exc)) from exc


def apply_aptamerbase_checkpoint1_package(
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
    """Apply a fully resolved AptamerBase CHECKPOINT-1 package.

    Fail-closed: unresolved or invalid fields raise. Audit-only rows may remain
    blank in the review CSV when bulk confirm=true; keep is materialised only
    in memory.
    """
    report = validate_review_package(
        queue_rows=queue_rows,
        group_rows=group_rows,
        bulk_confirmation=bulk_confirmation,
        allow_deferred=allow_deferred,
    )
    if not report.ok:
        raise AptamerBaseCheckpoint1ReviewError(
            "CHECKPOINT-1 cannot be applied while required human decisions "
            f"remain unresolved ({len(report.blocking_issues)} blocking issues)"
        )
    for row in queue_rows:
        if _blank(row.get("manual_target_corrected")):
            raise AptamerBaseCheckpoint1ReviewError(
                "AptamerBase CHECKPOINT-1 forbids manual_target_corrected "
                f"for {row.get('record_id')!r}"
            )
    working_rows = _working_queue_rows(queue_rows, bulk_confirmation)
    groups_by_id = {row["constant_group_id"]: row for row in group_rows}
    proposals_by_record = proposals_by_record or {}
    applied: list[AppliedRecordResult] = []
    for row in working_rows:
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
            if proposed.isdigit() and side in {"five_prime", "5'"}:
                machine_five = int(proposed)
            elif proposed.isdigit() and side in {"three_prime", "3'"}:
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


def compare_review_to_pristine(
    reviewed_rows: Sequence[Mapping[str, str]],
    pristine_rows: Sequence[Mapping[str, str]],
) -> list[str]:
    """Return immutable-field drift; permitted human decision fields may differ."""
    if len(reviewed_rows) != len(pristine_rows):
        return [
            "Active review row count differs from pristine baseline: "
            f"{len(reviewed_rows)} vs {len(pristine_rows)}"
        ]
    reviewed_ids = [row["record_id"] for row in reviewed_rows]
    pristine_ids = [row["record_id"] for row in pristine_rows]
    if reviewed_ids != pristine_ids:
        return ["Review order or record_id membership differs from pristine baseline"]
    mismatches: list[str] = []
    for reviewed, pristine in zip(reviewed_rows, pristine_rows, strict=True):
        record_id = reviewed["record_id"]
        for field_name, reviewed_value in reviewed.items():
            if field_name in PERMITTED_REVIEW_DRIFT_FIELDS:
                continue
            if reviewed_value != pristine.get(field_name, ""):
                mismatches.append(f"{record_id}:{field_name}")
                if len(mismatches) >= 20:
                    return mismatches
    return mismatches


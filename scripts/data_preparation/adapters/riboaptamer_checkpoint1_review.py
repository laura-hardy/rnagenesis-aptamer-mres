"""RiboAptamer CHECKPOINT-1 structured review: schema, recommendations, apply.

Reuses the AptaDB structured-review field vocabulary and fail-closed
validation. Does not fill ``manual_*`` decisions, apply trims, or start S4.
Recommendations live in separate fields and must never masquerade as human
decisions.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from adapters.aptadb_checkpoint1_review import (
    AppliedRecordResult,
    AptaDBCheckpoint1ReviewError,
    BULK_CONFIRMATION_COLUMNS,
    BULK_CONFIRMATION_ID,
    BULK_SCOPE,
    GROUP_REVIEW_COLUMNS,
    LARGE_TRIM_HUMAN_APPROVED_FLAG,
    MANUAL_FIELDS,
    RECOMMENDATION_FIELDS,
    ValidationReport,
    _blank,
    _corpus_only,
    apply_numeric_terminal_trim,
    combined_trim_exceeds_review_threshold,
    combined_trim_fraction,
    default_chemistry_for_molecule,
    format_large_trim_provenance,
    format_validation_markdown,
    is_audit_only_row,
    is_explicit_human_trim_authorisation,
    parse_review_reasons,
    populate_record_recommendations,
    read_csv_rows,
    resolve_effective_trim,
    validate_review_package,
)
from adapters.riboaptamer_s3 import classify_riboaptamer_record
from common.corpus_schema import S3_FORBIDDEN_FIELDS, format_qc_flags
from common.eligibility import EligibilityPolicy, load_eligibility_policy, parse_qc_flags
from common.sequence_normalisation import (
    TRIM_CONFIDENCE_HIGH,
    TRIM_CONFIDENCE_NA,
    normalise_sequence,
)

DEFAULT_RECOMMENDATIONS_REL: Final[str] = (
    "config/checkpoint_reviews/riboaptamer_checkpoint1_recommendations.json"
)
DEFAULT_POLICY_REL: Final[str] = "config/source_eligibility/riboaptamer.json"

# Human-review notes prefixes. Authoritative signal for unresolved constants.
CP1_FLAG_STRONG: Final[str] = "CP1_FLAG:constants_suspected_unresolved"
CP1_FLAG_WEAK: Final[str] = "CP1_FLAG:possible_constants_unresolved"
QC_FLAG_STRONG: Final[str] = "constants_suspected_unresolved"
QC_FLAG_WEAK: Final[str] = "possible_constants_unresolved"
TRIM_STATUS_STRONG: Final[str] = "constants_suspected_unresolved"
TRIM_STATUS_T7: Final[str] = "t7_removed"

# Laura recorded the T7 approval as informal ``trim``. Schema equivalent is
# ``approve`` of the existing known-motif proposal. Do not invent lengths.
RIBOAPTAMER_TRIM_ACTION_SYNONYMS: Final[Mapping[str, str]] = {"trim": "approve"}

HUMAN_SOURCE_DIRNAME: Final[str] = "human_source"
HUMAN_SOURCE_FILENAME: Final[str] = (
    "riboaptamer_checkpoint1_manual_review.as_saved.csv"
)


class RiboAptamerCheckpoint1ReviewError(ValueError):
    """Invalid RiboAptamer CHECKPOINT-1 review schema, validation, or apply."""


def decode_mixed_utf8_macroman_bytes(raw: bytes) -> str:
    """Decode a review CSV that mixes UTF-8 with MacRoman em-dashes.

    Excel on macOS may leave original UTF-8 sequences intact while storing
    newly typed em-dashes as MacRoman ``0xD1``. Preserve UTF-8 semantics;
    map only lone MacRoman em-dash bytes. Do not invent review decisions.
    """
    out = bytearray()
    index = 0
    length = len(raw)
    while index < length:
        byte = raw[index]
        if byte < 0x80:
            out.append(byte)
            index += 1
            continue
        if (
            0xC2 <= byte <= 0xDF
            and index + 1 < length
            and 0x80 <= raw[index + 1] <= 0xBF
        ):
            out.extend(raw[index : index + 2])
            index += 2
            continue
        if (
            0xE0 <= byte <= 0xEF
            and index + 2 < length
            and 0x80 <= raw[index + 1] <= 0xBF
            and 0x80 <= raw[index + 2] <= 0xBF
        ):
            out.extend(raw[index : index + 3])
            index += 3
            continue
        if (
            0xF0 <= byte <= 0xF4
            and index + 3 < length
            and all(0x80 <= raw[index + offset] <= 0xBF for offset in range(1, 4))
        ):
            out.extend(raw[index : index + 4])
            index += 4
            continue
        if byte == 0xD1:
            out.extend("—".encode("utf-8"))
            index += 1
            continue
        raise RiboAptamerCheckpoint1ReviewError(
            f"Unrecognised non-UTF-8 byte 0x{byte:02x} at position {index} "
            "in RiboAptamer CHECKPOINT-1 review CSV"
        )
    return out.decode("utf-8")


def read_riboaptamer_review_csv(path: Path) -> list[dict[str, str]]:
    """Read a RiboAptamer review CSV, recovering Excel MacRoman if needed."""
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = decode_mixed_utf8_macroman_bytes(raw)
    rows = list(csv.DictReader(text.splitlines()))
    for row in rows:
        for key, value in list(row.items()):
            row[key] = "" if value is None else value
    return rows


def normalise_riboaptamer_trim_action(action: str) -> str:
    """Map informal RiboAptamer trim vocabulary onto the shared schema."""
    blank = _blank(action)
    return RIBOAPTAMER_TRIM_ACTION_SYNONYMS.get(blank, blank)


def normalise_riboaptamer_review_rows(
    rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Copy review rows and map informal trim actions. Never fill blanks."""
    normalised: list[dict[str, str]] = []
    for row in rows:
        out = dict(row)
        out["manual_trim_action"] = normalise_riboaptamer_trim_action(
            out.get("manual_trim_action", "")
        )
        normalised.append(out)
    return normalised


def parse_cp1_constant_flag(manual_notes: str) -> str:
    """Return the unresolved-constant class encoded in human notes, if any."""
    text = manual_notes or ""
    if CP1_FLAG_STRONG in text:
        return QC_FLAG_STRONG
    if CP1_FLAG_WEAK in text:
        return QC_FLAG_WEAK
    return ""


def _append_note_parts(original: str, *parts: str) -> str:
    """Append unique note tokens without replacing source notes."""
    existing = [part for part in (original or "").split("|") if part]
    seen = set(existing)
    for part in parts:
        token = (part or "").strip()
        if not token or token in seen:
            continue
        existing.append(token)
        seen.add(token)
    return "|".join(existing)


def _sanitize_reviewer_note(text: str) -> str:
    return (text or "").replace("|", ";").strip()


def _reviewer_notes_token(manual_notes: str) -> str:
    cleaned = _sanitize_reviewer_note(manual_notes)
    if not cleaned:
        return ""
    return f"checkpoint1_reviewer_notes={cleaned}"


def known_motif_machine_trim(
    review_row: Mapping[str, str],
    proposals: Sequence[Mapping[str, str]] = (),
) -> tuple[int, int]:
    """Return proposed 5'/3' nt from known-motif proposals, else review fields."""
    five = 0
    three = 0
    for proposal in proposals:
        if proposal.get("proposal_source") != "known_motif":
            continue
        length_raw = str(proposal.get("motif_length") or "").strip()
        if not length_raw.isdigit():
            continue
        length = int(length_raw)
        side = _blank(proposal.get("side"))
        if side == "five_prime":
            five = length
        elif side == "three_prime":
            three = length
    if five or three:
        return five, three
    length_raw = _blank(review_row.get("constant_proposed_trim_length", ""))
    if not length_raw.isdigit():
        return 0, 0
    length = int(length_raw)
    sides = _blank(review_row.get("constant_proposal_sides", ""))
    if "five_prime" in sides:
        five = length
    if "three_prime" in sides:
        three = length
    return five, three


def preserve_human_review_source(queue_path: Path) -> Path:
    """Copy Laura's as-saved review bytes before any canonical rewrite."""
    source_dir = queue_path.parent / HUMAN_SOURCE_DIRNAME
    source_dir.mkdir(parents=True, exist_ok=True)
    dest = source_dir / HUMAN_SOURCE_FILENAME
    if not dest.is_file():
        dest.write_bytes(queue_path.read_bytes())
    return dest


def write_canonical_utf8_review_csv(
    path: Path, rows: Sequence[Mapping[str, str]]
) -> None:
    if not rows:
        raise RiboAptamerCheckpoint1ReviewError("Cannot write empty review CSV")
    fieldnames = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, lineterminator="\n", extrasaction="raise"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in fieldnames})


def load_review_recommendations(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("source_key") != "riboaptamer":
        raise RiboAptamerCheckpoint1ReviewError(
            "recommendation file source_key must be riboaptamer"
        )
    return payload


def populate_riboaptamer_recommendations(
    row: dict[str, str],
    *,
    recommendations: Mapping[str, Any],
) -> dict[str, str]:
    """Fill recommendation fields only. Never writes ``manual_*`` values."""
    try:
        out = populate_record_recommendations(row, recommendations=recommendations)
    except AptaDBCheckpoint1ReviewError as exc:
        raise RiboAptamerCheckpoint1ReviewError(str(exc)) from exc

    reasons = parse_review_reasons(out.get("checkpoint_review_reasons", ""))
    if not out.get("review_recommendation"):
        cfg: Mapping[str, Any] = {}
        if "judgement_dependent_technical" in reasons:
            cfg = recommendations.get("judgement_dependent") or {}
        elif "constant_region_proposal" in reasons:
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
    for name in MANUAL_FIELDS:
        out[name] = ""
    return out


def _source_molecule_note(original_molecule: str, reviewed_molecule: str) -> str:
    if original_molecule == reviewed_molecule:
        return ""
    return (
        f"manual_molecule_override original={original_molecule} "
        f"reviewed={reviewed_molecule}"
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
    """Apply one reviewed record through shared normalisation + S3 routing.

    Does not mutate ``sequence_raw``. Does not populate S4 fields.
    """
    record_id = canonical["record_id"]
    original_raw = canonical["sequence_raw"]
    original_notes = canonical.get("notes", "")
    original_molecule = canonical.get("molecule_type", "")
    original_chemistry = canonical.get("chemistry", "")
    route_before = review_row.get("primary_route", "")
    working_review = dict(review_row)
    working_review["manual_trim_action"] = normalise_riboaptamer_trim_action(
        working_review.get("manual_trim_action", "")
    )
    decision = _blank(working_review.get("manual_decision"))
    if decision not in {"keep", "drop", "edit"}:
        raise RiboAptamerCheckpoint1ReviewError(
            f"Cannot apply unresolved manual_decision for {record_id!r}"
        )
    constant_flag = parse_cp1_constant_flag(working_review.get("manual_notes", ""))
    reviewer_note = _reviewer_notes_token(working_review.get("manual_notes", ""))
    if decision == "drop":
        updated = _corpus_only(canonical)
        for field_name in S3_FORBIDDEN_FIELDS:
            updated[field_name] = ""
        updated["notes"] = _append_note_parts(
            original_notes,
            "checkpoint1_manual_decision=drop",
            "human_reviewed_exclusion=true",
            reviewer_note,
        )
        return AppliedRecordResult(
            record_id=record_id,
            sequence_raw=original_raw,
            sequence_full=canonical.get("sequence_full", ""),
            sequence_core=canonical.get("sequence_core", ""),
            sequence_length_full=int(canonical.get("sequence_length_full") or 0),
            sequence_length_core=int(canonical.get("sequence_length_core") or 0),
            molecule_type=original_molecule,
            chemistry=original_chemistry,
            alphabet_as_reported=canonical.get("alphabet_as_reported", ""),
            t_to_u_applied=canonical.get("t_to_u_applied", "") == "true",
            trim_status=canonical.get("trim_status", ""),
            trim_confidence=canonical.get("trim_confidence", "") or TRIM_CONFIDENCE_NA,
            primary_route_before=route_before,
            primary_route_after=route_before,
            notes=updated["notes"],
            canonical=updated,
            proposed_decision=working_review.get("proposed_decision", ""),
            primary_reason=working_review.get("primary_reason", ""),
        )

    working_input = (
        _blank(working_review.get("manual_sequence_corrected")) or original_raw
    )
    molecule = (
        _blank(working_review.get("manual_molecule_type_override"))
        or original_molecule
    )
    chemistry = _blank(working_review.get("manual_chemistry_override"))
    if not chemistry:
        chemistry = (
            default_chemistry_for_molecule(molecule)
            if molecule != original_molecule
            else original_chemistry
        )

    trim_action = _blank(working_review.get("manual_trim_action"))
    if trim_action == "defer":
        raise RiboAptamerCheckpoint1ReviewError(
            f"Deferred trim cannot be applied for {record_id!r}"
        )

    if not machine_five and not machine_three:
        machine_five, machine_three = known_motif_machine_trim(
            working_review, proposals
        )

    norm = normalise_sequence(working_input, molecule_type=molecule)
    sequence_full = norm.sequence_full or ""
    sequence_core = sequence_full
    trim_status = canonical.get("trim_status") or "no_constants_detected"
    trim_confidence = canonical.get("trim_confidence") or TRIM_CONFIDENCE_NA
    applied_five = 0
    applied_three = 0
    trim_frac = 0.0
    large_trim_human_approved = False
    try:
        effective = resolve_effective_trim(
            working_review,
            group_row,
            machine_five=machine_five,
            machine_three=machine_three,
        )
    except AptaDBCheckpoint1ReviewError as exc:
        raise RiboAptamerCheckpoint1ReviewError(str(exc)) from exc
    if effective is not None:
        if effective.five_nt == 0 and effective.three_nt == 0:
            raise RiboAptamerCheckpoint1ReviewError(
                f"Approved trim for {record_id!r} has no 5'/3' nucleotide lengths"
            )
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
            raise RiboAptamerCheckpoint1ReviewError(str(exc)) from exc
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
        source = working_review.get("constant_proposal_sources", "")
        if source == "known_motif" or "known_motif" in source:
            trim_confidence = TRIM_CONFIDENCE_HIGH
            trim_status = (
                TRIM_STATUS_T7
                if applied_five and not applied_three
                else (
                    "t7_and_primers_removed"
                    if applied_five and applied_three
                    else "primers_removed"
                )
            )
        else:
            trim_status = "primers_removed"
    elif constant_flag == QC_FLAG_STRONG:
        trim_status = TRIM_STATUS_STRONG
        trim_confidence = TRIM_CONFIDENCE_NA
    elif constant_flag == QC_FLAG_WEAK:
        if trim_status == TRIM_STATUS_STRONG:
            trim_status = "no_constants_detected"
        trim_confidence = TRIM_CONFIDENCE_NA
    if sequence_full and sequence_core and sequence_core not in sequence_full:
        raise RiboAptamerCheckpoint1ReviewError(
            f"sequence_core is not a contiguous substring of reviewed "
            f"sequence_full for {record_id!r}"
        )

    updated = _corpus_only(canonical)
    updated["sequence_raw"] = original_raw
    updated["sequence_full"] = sequence_full
    updated["sequence_core"] = sequence_core
    updated["sequence_length_full"] = str(len(sequence_full)) if sequence_full else ""
    updated["sequence_length_core"] = str(len(sequence_core)) if sequence_core else ""
    updated["molecule_type"] = molecule
    updated["chemistry"] = chemistry
    updated["alphabet_as_reported"] = norm.alphabet_as_reported
    updated["t_to_u_applied"] = "true" if norm.t_to_u_applied else "false"
    updated["trim_status"] = trim_status
    updated["trim_confidence"] = trim_confidence
    qc_flag_values = list(parse_qc_flags(canonical.get("qc_flags", "")))
    qc_flag_values.extend(list(norm.qc_flags))
    if effective is not None:
        qc_flag_values = [
            flag
            for flag in qc_flag_values
            if flag not in {"trim_requires_review", QC_FLAG_STRONG}
        ]
        if "known_promoter_detected" not in qc_flag_values and (
            "known_motif" in (working_review.get("constant_proposal_sources") or "")
        ):
            qc_flag_values.append("known_promoter_detected")
    if large_trim_human_approved:
        qc_flag_values.append(LARGE_TRIM_HUMAN_APPROVED_FLAG)
    if constant_flag == QC_FLAG_STRONG and effective is None:
        qc_flag_values.append(QC_FLAG_STRONG)
    elif constant_flag == QC_FLAG_WEAK:
        qc_flag_values.append(QC_FLAG_WEAK)
        qc_flag_values = [flag for flag in qc_flag_values if flag != QC_FLAG_STRONG]
    updated["qc_flags"] = format_qc_flags(qc_flag_values)
    for field_name in S3_FORBIDDEN_FIELDS:
        updated[field_name] = ""

    qc = dict(s2_qc)
    qc["record_id"] = record_id
    qc["molecule_type"] = molecule
    qc["chemistry"] = chemistry
    qc["alphabet_as_reported"] = updated["alphabet_as_reported"]
    qc["t_to_u_applied"] = updated["t_to_u_applied"]
    qc["sequence_length_full"] = updated["sequence_length_full"]
    qc["sequence_length_core"] = updated["sequence_length_core"]
    qc["trim_status"] = trim_status
    qc["trim_confidence"] = trim_confidence
    qc["qc_flags"] = updated["qc_flags"]

    classified = classify_riboaptamer_record(
        updated,
        qc,
        source_metadata,
        policy=policy,
        proposals=proposals,
        enforce_rna_contract=False,
    )
    route_after = classified.decision["primary_route"]

    extra_notes = [f"checkpoint1_manual_decision={decision}"]
    if working_input != original_raw:
        extra_notes.append("manual_sequence_correction_applied")
    mol_note = _source_molecule_note(original_molecule, molecule)
    if mol_note:
        extra_notes.append(mol_note)
    if effective is not None:
        extra_notes.append(
            f"manual_trim_action={effective.action};"
            f"applied_5p={applied_five};applied_3p={applied_three};"
            f"trim_source={effective.source};group={effective.group_id}"
        )
    if large_trim_human_approved:
        extra_notes.append(
            format_large_trim_provenance(
                fraction=trim_frac,
                trim_source=effective.source if effective is not None else "",
                human_trim_action=effective.action if effective is not None else "",
                five_nt=applied_five,
                three_nt=applied_three,
                core_length=len(sequence_core),
                group_id=effective.group_id if effective is not None else "",
            )
        )
    if constant_flag:
        extra_notes.append(f"checkpoint1_constant_flag={constant_flag}")
    extra_notes.append(reviewer_note)
    updated["notes"] = _append_note_parts(original_notes, *extra_notes)
    classified.canonical["notes"] = updated["notes"]
    classified.canonical["sequence_raw"] = original_raw
    classified.canonical["qc_flags"] = updated["qc_flags"]
    classified.canonical["trim_status"] = trim_status
    classified.canonical["trim_confidence"] = trim_confidence
    classified.decision["notes"] = updated["notes"]
    classified.decision["qc_flags"] = updated["qc_flags"]
    classified.decision["trim_status"] = trim_status
    classified.decision["trim_confidence"] = trim_confidence

    return AppliedRecordResult(
        record_id=record_id,
        sequence_raw=original_raw,
        sequence_full=sequence_full,
        sequence_core=sequence_core,
        sequence_length_full=len(sequence_full) if sequence_full else 0,
        sequence_length_core=len(sequence_core) if sequence_core else 0,
        molecule_type=molecule,
        chemistry=chemistry,
        alphabet_as_reported=updated["alphabet_as_reported"],
        t_to_u_applied=updated["t_to_u_applied"] == "true",
        trim_status=trim_status,
        trim_confidence=trim_confidence,
        primary_route_before=route_before,
        primary_route_after=route_after,
        notes=updated["notes"],
        canonical=classified.canonical,
        proposed_decision=classified.decision.get("proposed_decision", ""),
        primary_reason=classified.decision.get("primary_reason", ""),
        decision=classified.decision,
        rejection_row=classified.rejection_row,
        park_row=classified.park_row,
        applied_trim_5p_nt=applied_five,
        applied_trim_3p_nt=applied_three,
        trim_source=effective.source if effective is not None else "",
        sequence_corrected=working_input != original_raw,
        molecule_overridden=molecule != original_molecule,
        large_trim_human_approved=large_trim_human_approved,
        trim_fraction=trim_frac,
    )


def apply_riboaptamer_checkpoint1_package(
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
) -> tuple[list[AppliedRecordResult], ValidationReport]:
    """Apply a fully resolved RiboAptamer CHECKPOINT-1 package.

    Fail-closed: unresolved, deferred (unless allowed), or invalid fields raise.
    """
    queue_rows = normalise_riboaptamer_review_rows(queue_rows)
    report = validate_review_package(
        queue_rows=queue_rows,
        group_rows=group_rows,
        bulk_confirmation=bulk_confirmation,
        allow_deferred=allow_deferred,
    )
    if not report.ok:
        raise RiboAptamerCheckpoint1ReviewError(
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
            machine_five, machine_three = known_motif_machine_trim(
                row, list(proposals_by_record.get(record_id, ()))
            )
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


def load_default_policy(repo_root: Path) -> EligibilityPolicy:
    return load_eligibility_policy(repo_root / DEFAULT_POLICY_REL)


def build_review_readme() -> str:
    return """# RiboAptamer CHECKPOINT-1 human review

This package is a human-review gate. Machine recommendations are guidance
only. Do not treat `review_recommendation` as a completed `manual_decision`.

## What S3 already did automatically

Technical sequence eligibility used `sequence_core` length 20–100 nt and the
closed reason vocabulary. Automatic exclusions (missing sequence, ambiguous
bases, invalid alphabet without a judgement-dependent overlap, mixed T/U,
ordinary length-out-of-range) are already in the rejection log and are not
waiting for a keep/drop decision unless they also appear here for overlap
context.

Target classification, evidence/affinity scoring, leakage exclusion, and
source `Type` protein/non-protein routing were not applied. Those remain S4 /
CHECKPOINT-2 work. Empty `target_name_raw` is not a rejection.

## What requires human judgement

Fill `manual_decision` for every active review row.

Permitted `manual_decision` values: `keep` / `drop` / `edit`.

Judgement-dependent technical rows (`truncated_sequence`, `alignment_gaps`,
and any primer/library/trim-induced cases) take review precedence when they
overlap a generic automatic condition such as `invalid_alphabet`. The SelB
ellipsis/gap/invalid overlap is in this batch for that reason.

## Boundary and random audit rows

Length-boundary (20–25 and 90–100 nt) and the random kept sample of 30 are
technically retained. They are for eyeballing, not automatic rejection.
Audit-only rows may be confirmed in bulk via
`riboaptamer_checkpoint1_bulk_audit_confirmation.csv` (`confirm=true`) or
filled individually as `keep`.

## T7 / constant-region proposal

The known 5-prime `t7_promoter_minimal` motif is an unapplied proposal.
Detection confidence is the approved motif library. `sequence_core` has not
been changed. Group-wise constant-region inference was disabled for the
RiboAptamer S2/S3 run, so there are no medium-confidence consensus trims.

Permitted `manual_trim_action` values: `approve` / `override` / `reject` /
`defer`. Trim lengths are nucleotide counts removed from reviewed
`sequence_full`. They are not hand-pasted core coordinates.

If you later approve a trim, apply will preserve `sequence_raw`, rebuild the
normalised/core sequence deterministically, record the motif, recompute core
length, and re-run technical eligibility. Do not apply that now.

## Columns to fill

Record-level human fields:

- `manual_decision`: blank / `keep` / `drop` / `edit`
- `manual_sequence_corrected`: reviewed source sequence, if edited
- `manual_molecule_type_override`: blank / `RNA` / `ssDNA`
- `manual_chemistry_override`: blank or a canonical chemistry vocabulary value
- `manual_trim_action`: blank / `approve` / `override` / `reject` / `defer`
- `manual_trim_5p_nt` / `manual_trim_3p_nt`: non-negative integers or blank
- `manual_trim_group_override`: blank / `true` / `false`
- `manual_notes`

`edit` requires at least one of: corrected sequence, molecule/chemistry
override, or an explicit trim action. `sequence_raw` remains the original
source sequence even if you supply a corrected technical sequence.

Source `Type` (`riboaptamer_type`) is review context only. Do not treat it as
the S3 decision.

## Fail-closed apply

The apply stage will refuse to produce reviewed final S3 output while any
required `manual_decision` is blank, a trim is deferred, or a group/bulk
confirmation remains unresolved. Do not run apply until review is complete.

Do not start S4.
"""


def format_riboaptamer_validation_markdown(report: ValidationReport) -> str:
    text = format_validation_markdown(report)
    return text.replace("AptaDB CHECKPOINT-1", "RiboAptamer CHECKPOINT-1")

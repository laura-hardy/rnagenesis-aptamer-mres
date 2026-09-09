"""AptamerBase CHECKPOINT-1 decision-support audit (no human decisions).

Builds ignored sequence-bearing review units and sequence-free aggregates.
Does not populate ``manual_*`` fields, apply CHECKPOINT-1, alter S2/S3
routes, or start global S4.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Mapping, Sequence

from adapters.aptadb_checkpoint1_review import (
    MANUAL_FIELDS,
    is_audit_only_row,
    parse_review_reasons,
)
from adapters.aptamerbase_s2 import canonicalize_modification_text
from common.sequence_normalisation import ALIGNMENT_GAP_CHARACTERS

IUPAC_AMBIGUITY: Final[frozenset[str]] = frozenset(
    {"N", "R", "Y", "S", "W", "K", "M", "B", "D", "H", "V"}
)
CANONICAL_BASES: Final[frozenset[str]] = frozenset({"A", "C", "G", "T", "U"})
PMID_HINT_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:PMID[:\s_-]*)?(\d{6,8})",
    re.IGNORECASE,
)
NT_RE: Final[re.Pattern[str]] = re.compile(
    r"^<([^>]*)>\s+<([^>]*)>\s+<(.*)>\s+\.\s*$"
)

NOTATION_RECOMMENDATIONS: Final[frozenset[str]] = frozenset(
    {
        "likely_true_degenerate_or_ambiguous_sequence",
        "likely_alignment_notation_recoverable_if_source_confirmed",
        "likely_modification_or_display_notation_recoverable",
        "malformed_or_unrecoverable",
        "chemistry_and_sequence_both_require_review",
        "needs_publication_source_review",
    }
)
DNA_U_RECOMMENDATIONS: Final[frozenset[str]] = frozenset(
    {
        "confirm_rdf_dna_keep_ssdna_park",
        "override_molecule_to_RNA",
        "needs_publication_source_review",
    }
)
MOLECULE_RECOMMENDATIONS: Final[frozenset[str]] = frozenset(
    {
        "recommend_RNA_from_source_evidence",
        "recommend_ssDNA_from_source_evidence",
        "remain_unresolved_park",
        "needs_publication_source_review",
    }
)
CHEMISTRY_EVIDENCE_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "source_supports_2NH2_RNA",
        "source_supports_2OMe_RNA",
        "source_supports_mixed_chemistry",
        "terminal_or_post_selection_modification_only",
        "Spiegelmer_L_RNA",
        "modified_DNA_like",
        "chemistry_unresolved",
        "needs_publication_source_review",
    }
)
MOTIF_RECOMMENDATIONS: Final[frozenset[str]] = frozenset(
    {
        "approve_existing_known_motif",
        "reject_trim_keep_full",
        "needs_source_review",
        "cannot_resolve_due_other_blocker",
    }
)

CORE_LENGTH_MIN: Final[int] = 20
CORE_LENGTH_MAX: Final[int] = 100
MAX_TRIM_FRACTION: Final[float] = 0.40
RANDOM_SEED: Final[int] = 42
RANDOM_SAMPLE_SIZE: Final[int] = 30

RDF_TYPE_PRED: Final[str] = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
FB_TYPE_PRED: Final[str] = "http://rdf.freebase.com/ns/type.object.type"
URI_RNA: Final[str] = "http://rdf.freebase.com/ns/base.aptamer.rna"
URI_DNA: Final[str] = "http://rdf.freebase.com/ns/base.aptamer.dna"
URI_NA: Final[str] = "http://rdf.freebase.com/ns/base.aptamer.nucleic_acid"
URI_APTAMER: Final[str] = "http://rdf.freebase.com/ns/base.aptamer.aptamer"
URI_MOD: Final[str] = "http://rdf.freebase.com/ns/base.aptamer.modified_nucleic_acid"

SCIENTIFIC_IDENTITY_FIELDS: Final[tuple[str, ...]] = (
    "sequence_raw",
    "sequence_full",
    "molecule_type",
    "chemistry",
    "chemistry_class",
    "alphabet_as_reported",
    "t_to_u_applied",
    "aptamerbase_has_modification_details",
)

ISSUE_FLAGS: Final[tuple[str, ...]] = (
    "notation_issue",
    "source_molecule_alphabet_conflict",
    "molecule_unresolved",
    "chemistry_unresolved",
    "spiegelmer_l_rna",
    "length_failure_or_boundary",
    "known_motif",
    "ssdna_route",
    "technical_reject",
)

DECISION_SUPPORT_COLUMNS: Final[tuple[str, ...]] = (
    "freebase_id",
    "member_record_ids",
    "n_physical_rows",
    "review_batches",
    "current_proposed_routes",
    "checkpoint_review_reasons",
    "source_object_type",
    "rdf_has_rna",
    "rdf_has_dna",
    "rdf_has_nucleic_acid",
    "rdf_has_modified_nucleic_acid",
    "molecule_type",
    "alphabet_as_reported",
    "t_to_u_applied",
    "chemistry",
    "chemistry_class",
    "source_modification_present",
    "source_modification_text",
    "sequence_length_full",
    "sequence_length_core",
    "known_motif_status",
    "source_label",
    "audit_only_bibliographic_hint",
    "group_scientifically_identical",
    "safe_for_groupwise_review",
    "judgement_required_member_count",
    "sequence_raw",
    "sequence_full",
    "sequence_core",
)

NOTATION_AUDIT_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "freebase_id",
    "review_batch",
    "current_technical_reason",
    "checkpoint_review_reasons",
    "alphabet_as_reported",
    "qc_flags",
    "rdf_has_rna",
    "rdf_has_dna",
    "source_label",
    "audit_only_bibliographic_hint",
    "source_modification_text",
    "machine_recommendation",
    "canonical_sequence_recoverable_without_guessing",
    "proposed_corrected_sequence",
    "recovery_confidence",
    "evidence_basis",
    "remaining_blocker_if_repaired",
    "would_become_technically_eligible_if_repaired",
    "sequence_raw",
    "sequence_full",
)

DNA_U_AUDIT_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "freebase_id",
    "review_batch",
    "molecule_type",
    "chemistry",
    "chemistry_class",
    "alphabet_as_reported",
    "t_to_u_applied",
    "rdf_has_rna",
    "rdf_has_dna",
    "source_modification_text",
    "source_label",
    "audit_only_bibliographic_hint",
    "machine_recommendation",
    "evidence_basis",
    "remaining_blocker_if_resolved",
    "sequence_raw",
    "sequence_full",
)

MOLECULE_AUDIT_COLUMNS: Final[tuple[str, ...]] = (
    "freebase_id",
    "member_record_ids",
    "n_physical_rows",
    "rdf_has_rna",
    "rdf_has_dna",
    "rdf_has_nucleic_acid",
    "rdf_has_modified_nucleic_acid",
    "alphabet_as_reported",
    "source_modification_text",
    "source_label",
    "audit_only_bibliographic_hint",
    "publication_hint_group",
    "repeated_id_context",
    "sequence_length_core",
    "chemistry",
    "chemistry_class",
    "explicit_local_molecule_evidence",
    "machine_recommendation",
    "evidence_basis",
    "remaining_blocker_if_resolved",
    "sequence_raw",
    "sequence_full",
)

CHEMISTRY_AUDIT_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "freebase_id",
    "review_batch",
    "primary_or_secondary",
    "molecule_type",
    "rdf_has_rna",
    "rdf_has_dna",
    "chemistry_class",
    "current_chemistry",
    "source_modification_text",
    "source_label",
    "audit_only_bibliographic_hint",
    "evidence_class",
    "proposed_chemistry_override",
    "would_become_technically_eligible_after_override",
    "remaining_blocker_if_overridden",
    "machine_recommendation_note",
    "sequence_raw",
    "sequence_full",
)

MOTIF_AUDIT_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "freebase_id",
    "source_molecule_type",
    "chemistry",
    "current_route",
    "primary_reason",
    "motif_type",
    "side",
    "motif_length",
    "match_confidence",
    "full_length",
    "hypothetical_trimmed_core_length",
    "hypothetical_trim_fraction",
    "post_trim_core_satisfies_20_100",
    "trim_exceeds_40pct_review_trigger",
    "other_blocker_remains",
    "machine_recommendation",
    "motif_sequence",
    "sequence_full",
)

MOTIF_SUMMARY_COLUMNS: Final[tuple[str, ...]] = tuple(
    col for col in MOTIF_AUDIT_COLUMNS if col not in {"motif_sequence", "sequence_full"}
)

AUDIT_ONLY_SUPPORT_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "review_batch",
    "length_bucket",
    "chemistry",
    "t_to_u_applied",
    "source_modification_present",
    "qc_flags",
    "accepted_record_invariants_ok",
    "machine_recommendation",
    "sequence_length_core",
    "molecule_type",
    "primary_route",
)

COMPOUND_MATRIX_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "review_batch",
    "freebase_id",
    *ISSUE_FLAGS,
    "human_issue_count",
    "primary_issue",
    "secondary_blockers_if_primary_resolved",
)

INTEGRITY_PATHS: Final[tuple[tuple[str, str], ...]] = (
    ("raw_csv", "data/raw/aptamerbase/aptamerbase_aptamers.csv"),
    ("supporting_rdf", "data/raw/aptamerbase/aptamerbase.freebase.extract.nt.gz"),
    ("s1_canonical", "data/interim/extracted/aptamerbase_extracted.csv"),
    ("s1_sidecar", "data/interim/extracted/aptamerbase_source_metadata.csv"),
    ("s2_canonical", "data/interim/normalised/aptamerbase_normalised.csv"),
    ("s2_qc", "data/interim/normalised/aptamerbase_s2_qc.csv"),
    ("s3_canonical", "data/interim/checkpoints/aptamerbase_cp1/aptamerbase_s3_canonical.csv"),
    ("s3_decisions", "data/interim/checkpoints/aptamerbase_cp1/aptamerbase_s3_decisions.csv"),
    (
        "checkpoint1_review",
        "data/interim/checkpoints/aptamerbase_cp1/aptamerbase_checkpoint1_review.csv",
    ),
    (
        "checkpoint1_local_detail",
        "data/interim/checkpoints/aptamerbase_cp1/aptamerbase_checkpoint1_local_detail.csv",
    ),
)


class AptamerBaseCheckpoint1AuditError(ValueError):
    """Fail-closed audit error. Must not embed source sequences."""


@dataclass
class FrozenIntegrity:
    """SHA-256 freeze of scientific artefacts before review-package refinement."""

    hashes: dict[str, str]
    s3_canonical_equals_s2: bool
    canonical_rows: int
    human_fields_populated: int


@dataclass
class AuditPackage:
    """Deterministic audit tables. Sequence-bearing tables stay under data/."""

    integrity: FrozenIntegrity
    decision_support_rows: list[dict[str, str]]
    decision_support_summary_rows: list[dict[str, str]]
    notation_rows: list[dict[str, str]]
    dna_u_rows: list[dict[str, str]]
    molecule_rows: list[dict[str, str]]
    chemistry_rows: list[dict[str, str]]
    motif_rows: list[dict[str, str]]
    motif_summary_rows: list[dict[str, str]]
    audit_only_rows: list[dict[str, str]]
    compound_rows: list[dict[str, str]]
    aggregate: dict[str, object] = field(default_factory=dict)


def _blank(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _truthy(value: str) -> bool:
    return _blank(value).lower() == "true"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv_atomic(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, str]],
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(fieldnames),
                lineterminator="\n",
                extrasaction="raise",
                quoting=csv.QUOTE_ALL,
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({col: row.get(col, "") for col in fieldnames})
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text if text.endswith("\n") else text + "\n")
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def extract_pmid_hint(label: str) -> str:
    """Audit-only PMID-like prefix. Does not populate canonical pubmed_id."""
    match = PMID_HINT_RE.match(_blank(label))
    return match.group(1) if match else ""


def assert_human_fields_blank(rows: Sequence[Mapping[str, str]], *, label: str) -> None:
    populated = 0
    for row in rows:
        for name in MANUAL_FIELDS:
            if _blank(row.get(name, "")):
                populated += 1
        for name in ("confirm", "reviewer_initials"):
            if name in row and name != "scope" and _blank(row.get(name, "")):
                if name == "confirm":
                    continue
    if populated:
        raise AptamerBaseCheckpoint1AuditError(
            f"Human decision fields unexpectedly populated in {label}: {populated}"
        )


def freeze_scientific_artefacts(repo_root: Path) -> FrozenIntegrity:
    """Record hashes and stop if human decisions are already populated."""
    repo_root = Path(repo_root)
    hashes: dict[str, str] = {}
    for key, rel in INTEGRITY_PATHS:
        path = repo_root / rel
        if not path.is_file():
            raise AptamerBaseCheckpoint1AuditError(f"Missing frozen artefact: {rel}")
        hashes[key] = _sha256_file(path)

    s2 = (repo_root / "data/interim/normalised/aptamerbase_normalised.csv").read_bytes()
    s3 = (
        repo_root
        / "data/interim/checkpoints/aptamerbase_cp1/aptamerbase_s3_canonical.csv"
    ).read_bytes()
    equal = s2 == s3

    review_path = (
        repo_root
        / "data/interim/checkpoints/aptamerbase_cp1/aptamerbase_checkpoint1_review.csv"
    )
    local_path = (
        repo_root
        / "data/interim/checkpoints/aptamerbase_cp1/aptamerbase_checkpoint1_local_detail.csv"
    )
    with review_path.open(encoding="utf-8", newline="") as handle:
        review_rows = list(csv.DictReader(handle))
    with local_path.open(encoding="utf-8", newline="") as handle:
        local_rows = list(csv.DictReader(handle))
    if len(review_rows) != 2128 or len(local_rows) != 2128:
        raise AptamerBaseCheckpoint1AuditError(
            f"CHECKPOINT denominator must be 2128; got {len(review_rows)}"
        )
    assert_human_fields_blank(review_rows, label="checkpoint review")
    assert_human_fields_blank(local_rows, label="local detail")
    populated = 0
    for row in list(review_rows) + list(local_rows):
        for name in MANUAL_FIELDS:
            if _blank(row.get(name, "")):
                populated += 1
    if populated:
        raise AptamerBaseCheckpoint1AuditError(
            "Human decision fields are populated; refusing to continue the audit"
        )
    if not equal:
        raise AptamerBaseCheckpoint1AuditError(
            "S3 canonical is not byte-identical to S2 canonical"
        )
    return FrozenIntegrity(
        hashes=hashes,
        s3_canonical_equals_s2=equal,
        canonical_rows=len(review_rows),
        human_fields_populated=populated,
    )


def load_rdf_type_flags(
    rdf_path: Path | None,
    subject_uris: Sequence[str],
) -> dict[str, dict[str, str]]:
    """Stream supporting RDF type triples for review subjects only."""
    wanted = {uri for uri in subject_uris if uri}
    flags = {
        uri: {
            "rdf_has_rna": "false",
            "rdf_has_dna": "false",
            "rdf_has_nucleic_acid": "false",
            "rdf_has_modified_nucleic_acid": "false",
            "rdf_has_aptamer": "false",
        }
        for uri in wanted
    }
    if rdf_path is None or not Path(rdf_path).is_file() or not wanted:
        return flags
    with gzip.open(rdf_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if (
                RDF_TYPE_PRED not in line
                and FB_TYPE_PRED not in line
            ):
                continue
            parsed = NT_RE.match(line.strip())
            if parsed is None:
                continue
            subject, predicate, obj = parsed.group(1), parsed.group(2), parsed.group(3)
            if subject not in flags:
                continue
            if predicate not in {RDF_TYPE_PRED, FB_TYPE_PRED}:
                continue
            if obj == URI_RNA:
                flags[subject]["rdf_has_rna"] = "true"
            elif obj == URI_DNA:
                flags[subject]["rdf_has_dna"] = "true"
            elif obj == URI_NA:
                flags[subject]["rdf_has_nucleic_acid"] = "true"
            elif obj == URI_MOD:
                flags[subject]["rdf_has_modified_nucleic_acid"] = "true"
            elif obj == URI_APTAMER:
                flags[subject]["rdf_has_aptamer"] = "true"
    return flags


def _int_or_empty(value: str) -> int | None:
    text = _blank(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _qc_set(row: Mapping[str, str]) -> frozenset[str]:
    return frozenset(part for part in _blank(row.get("qc_flags", "")).split("|") if part)


def _mod_text(row: Mapping[str, str]) -> str:
    return row.get("aptamerbase_has_modification_details") or ""


def _mod_canonical(row: Mapping[str, str]) -> str:
    return canonicalize_modification_text(_mod_text(row))


def length_bucket(length: int | None) -> str:
    if length is None:
        return ""
    if 20 <= length <= 25:
        return "20-25"
    if 90 <= length <= 100:
        return "90-100"
    if CORE_LENGTH_MIN <= length <= CORE_LENGTH_MAX:
        return "26-89"
    if length < CORE_LENGTH_MIN:
        return "<20"
    return ">100"


def remaining_blockers(
    row: Mapping[str, str],
    *,
    ignore: frozenset[str] = frozenset(),
) -> list[str]:
    """Blockers that would remain after a hypothetical primary repair."""
    reasons = parse_review_reasons(row.get("checkpoint_review_reasons", ""))
    qc = _qc_set(row)
    length = _int_or_empty(row.get("sequence_length_core", ""))
    blockers: list[str] = []
    if (
        "molecule_unknown" not in ignore
        and (
            "molecule_type_unresolved" in reasons
            or row.get("molecule_type") == "unknown"
        )
    ):
        blockers.append("molecule_unknown")
    if (
        "chemistry_review" not in ignore
        and (
            "chemistry_requires_review" in reasons
            or "spiegelmer_l_rna" in reasons
            or "chemistry_requires_review" in qc
            or "spiegelmer_l_rna_review" in qc
        )
    ):
        blockers.append("chemistry_review")
    if "length" not in ignore and length is not None and not (
        CORE_LENGTH_MIN <= length <= CORE_LENGTH_MAX
    ):
        blockers.append("length")
    if (
        "construct" not in ignore
        and (
            "constant_region_proposal" in reasons
            or "constants_suspected_unresolved" in qc
            or "known_promoter_detected" in qc
        )
    ):
        blockers.append("construct")
    if (
        "ssdna_park" not in ignore
        and (
            row.get("primary_route") == "parked_ssdna"
            or row.get("molecule_type") == "ssDNA"
        )
        and "source_molecule_alphabet_conflict" not in ignore
    ):
        blockers.append("ssdna_park")
    return blockers


def _noncanon_chars(sequence: str) -> str:
    return "".join(
        sorted({ch.upper() for ch in sequence if ch.upper() not in CANONICAL_BASES})
    )


def classify_notation_row(row: Mapping[str, str]) -> dict[str, str]:
    """Machine-only notation recommendation. Never mutates canonical sequence."""
    reasons = parse_review_reasons(row.get("checkpoint_review_reasons", ""))
    raw = row.get("sequence_raw") or ""
    qc = _qc_set(row)
    mod = _mod_canonical(row)
    extra = _noncanon_chars(raw)
    spiegelmer = "spiegelmer_l_rna" in reasons or "spiegelmer_l_rna_review" in qc
    biotin_defined = "b = biotin-ce" in mod or "b = biotin" in mod
    peg_defined = "x = polyethylene glycol" in mod
    chemistry_also = (
        "chemistry_requires_review" in reasons or "chemistry_requires_review" in qc
    )
    remaining = remaining_blockers(row)

    recommendation = "needs_publication_source_review"
    recoverable = False
    proposed = ""
    confidence = "low"
    evidence = "insufficient_local_source_evidence"

    if spiegelmer:
        recommendation = "chemistry_and_sequence_both_require_review"
        confidence = "high"
        evidence = "source_modification_defines_spiegelmer_l_rna_and_x_placeholder"
    elif biotin_defined and "B" in extra:
        recommendation = "likely_modification_or_display_notation_recoverable"
        recovered = "".join(ch for ch in raw if ch.upper() != "B")
        recovered_extra = _noncanon_chars(recovered)
        if recovered and not recovered_extra and set(recovered.upper()) <= CANONICAL_BASES:
            recoverable = True
            proposed = recovered
            confidence = "high"
            evidence = "source_modification_defines_B_as_biotin_CE"
        else:
            confidence = "medium"
            evidence = "source_defines_B_as_biotin_but_remaining_sequence_not_closed_acgtu"
    elif peg_defined and "X" in extra and not spiegelmer:
        recommendation = "likely_modification_or_display_notation_recoverable"
        recovered = "".join(ch for ch in raw if ch.upper() != "X")
        if recovered and not _noncanon_chars(recovered):
            recoverable = True
            proposed = recovered
            confidence = "high"
            evidence = "source_modification_defines_X_as_PEG18"
        else:
            confidence = "medium"
            evidence = "source_defines_X_as_PEG18_but_remaining_sequence_not_closed"
    elif " " in raw or any(ch.isalpha() and ch.upper() not in (CANONICAL_BASES | IUPAC_AMBIGUITY | {"X"}) for ch in raw):
        recommendation = "malformed_or_unrecoverable"
        confidence = "high"
        evidence = "sequence_contains_non_nucleotide_words_or_display_text"
    elif "X" in extra:
        recommendation = "needs_publication_source_review"
        confidence = "low"
        evidence = "X_placeholder_without_source_definition_do_not_guess"
    elif "alignment_gaps" in qc or bool(set(raw) & ALIGNMENT_GAP_CHARACTERS):
        recommendation = "likely_alignment_notation_recoverable_if_source_confirmed"
        confidence = "medium"
        evidence = "gap_characters_present_do_not_delete_without_source_confirmation"
    elif row.get("alphabet_as_reported") == "mixed_T_U" or "mixed_t_u" in qc:
        recommendation = "needs_publication_source_review"
        confidence = "low"
        evidence = "mixed_T_and_U_do_not_guess_which_letter_is_display"
    elif extra and set(extra) <= IUPAC_AMBIGUITY:
        recommendation = "likely_true_degenerate_or_ambiguous_sequence"
        confidence = "high"
        evidence = "IUPAC_ambiguity_codes_present_do_not_substitute_a_canonical_base"
    elif chemistry_also:
        recommendation = "chemistry_and_sequence_both_require_review"
        confidence = "medium"
        evidence = "sequence_and_chemistry_review_both_present"
    else:
        recommendation = "needs_publication_source_review"
        evidence = "notation_not_recoverable_from_local_closed_evidence"

    if recommendation not in NOTATION_RECOMMENDATIONS:
        raise AptamerBaseCheckpoint1AuditError("notation recommendation outside vocabulary")

    eligible_if_repaired = (
        recoverable
        and not remaining
        and row.get("molecule_type") == "RNA"
        and (row.get("chemistry") or "") in {"RNA", "2F-RNA"}
    )
    return {
        "record_id": row["record_id"],
        "freebase_id": row.get("aptamerbase_id", ""),
        "review_batch": row.get("review_batch", ""),
        "current_technical_reason": row.get("primary_reason", ""),
        "checkpoint_review_reasons": row.get("checkpoint_review_reasons", ""),
        "alphabet_as_reported": row.get("alphabet_as_reported", ""),
        "qc_flags": row.get("qc_flags", ""),
        "rdf_has_rna": row.get("rdf_has_rna", ""),
        "rdf_has_dna": row.get("rdf_has_dna", ""),
        "source_label": row.get("aptamerbase_label", ""),
        "audit_only_bibliographic_hint": extract_pmid_hint(row.get("aptamerbase_label", "")),
        "source_modification_text": _mod_text(row),
        "machine_recommendation": recommendation,
        "canonical_sequence_recoverable_without_guessing": (
            "true" if recoverable else "false"
        ),
        "proposed_corrected_sequence": proposed,
        "recovery_confidence": confidence,
        "evidence_basis": evidence,
        "remaining_blocker_if_repaired": "|".join(remaining) if remaining else "none",
        "would_become_technically_eligible_if_repaired": (
            "true" if eligible_if_repaired else "false"
        ),
        "sequence_raw": raw,
        "sequence_full": row.get("sequence_full", ""),
    }


def classify_dna_u_row(row: Mapping[str, str]) -> dict[str, str]:
    """RDF DNA × U conflict. U alphabet is not RNA proof."""
    mod = _mod_text(row)
    chem_class = row.get("chemistry_class") or ""
    rdf_dna = _truthy(row.get("rdf_has_dna", ""))
    rdf_rna = _truthy(row.get("rdf_has_rna", ""))
    remaining = remaining_blockers(row, ignore=frozenset({"ssdna_park"}))
    if rdf_rna and not rdf_dna:
        rec = "override_molecule_to_RNA"
        evidence = "rdf_rna_type_independent_of_alphabet"
    elif chem_class not in {"", "unmodified_backbone", "terminal_conjugate"} or mod.strip():
        rec = "needs_publication_source_review"
        evidence = "rdf_dna_with_conflicting_chemistry_or_modification_do_not_override_from_U"
    elif rdf_dna:
        rec = "confirm_rdf_dna_keep_ssdna_park"
        evidence = "source_native_rdf_dna_type_U_alphabet_is_not_rna_proof"
        remaining = ["ssdna_park"]
    else:
        rec = "needs_publication_source_review"
        evidence = "insufficient_local_molecule_evidence"
    if rec not in DNA_U_RECOMMENDATIONS:
        raise AptamerBaseCheckpoint1AuditError("DNA×U recommendation outside vocabulary")
    return {
        "record_id": row["record_id"],
        "freebase_id": row.get("aptamerbase_id", ""),
        "review_batch": row.get("review_batch", ""),
        "molecule_type": row.get("molecule_type", ""),
        "chemistry": row.get("chemistry", ""),
        "chemistry_class": chem_class,
        "alphabet_as_reported": row.get("alphabet_as_reported", ""),
        "t_to_u_applied": row.get("t_to_u_applied", ""),
        "rdf_has_rna": row.get("rdf_has_rna", ""),
        "rdf_has_dna": row.get("rdf_has_dna", ""),
        "source_modification_text": mod,
        "source_label": row.get("aptamerbase_label", ""),
        "audit_only_bibliographic_hint": extract_pmid_hint(row.get("aptamerbase_label", "")),
        "machine_recommendation": rec,
        "evidence_basis": evidence,
        "remaining_blocker_if_resolved": "|".join(remaining) if remaining else "none",
        "sequence_raw": row.get("sequence_raw", ""),
        "sequence_full": row.get("sequence_full", ""),
    }


def classify_molecule_unit(
    rows: Sequence[Mapping[str, str]],
    rdf_flags: Mapping[str, str],
) -> dict[str, str]:
    """Source-ID molecule audit. U/T alphabet and label targets are not proof."""
    if not rows:
        raise AptamerBaseCheckpoint1AuditError("empty molecule review unit")
    first = rows[0]
    mod = _mod_text(first)
    canon = _mod_canonical(first)
    alphabet = first.get("alphabet_as_reported", "")
    has_na = rdf_flags.get("rdf_has_nucleic_acid", first.get("rdf_has_nucleic_acid", ""))
    explicit = ""
    rec = "needs_publication_source_review"
    if "uridine" in canon or "2'-amino-uridines" in canon:
        rec = "recommend_RNA_from_source_evidence"
        explicit = "modification_text_names_uridines"
    elif "rna" in canon.split() or "containing rna" in canon or "fluoropyrimidine-containing rna" in canon:
        rec = "recommend_RNA_from_source_evidence"
        explicit = "modification_text_explicitly_names_rna"
    elif re.search(r"\bdna\b", canon) and "uridines" not in canon:
        rec = "recommend_ssDNA_from_source_evidence"
        explicit = "modification_text_explicitly_names_dna"
    elif not mod.strip() and not _truthy(first.get("rdf_has_rna", "")) and not _truthy(
        first.get("rdf_has_dna", "")
    ):
        rec = "needs_publication_source_review"
        explicit = "no_rdf_rna_or_dna_type_alphabet_is_not_molecule_proof"
    else:
        rec = "needs_publication_source_review"
        explicit = "local_modification_or_rdf_does_not_independently_resolve_molecule"
    if rec not in MOLECULE_RECOMMENDATIONS:
        raise AptamerBaseCheckpoint1AuditError("molecule recommendation outside vocabulary")
    remaining = remaining_blockers(first, ignore=frozenset({"molecule_unknown"}))
    pmid = extract_pmid_hint(first.get("aptamerbase_label", ""))
    return {
        "freebase_id": first.get("aptamerbase_id", ""),
        "member_record_ids": "|".join(row["record_id"] for row in rows),
        "n_physical_rows": str(len(rows)),
        "rdf_has_rna": rdf_flags.get("rdf_has_rna", first.get("rdf_has_rna", "")),
        "rdf_has_dna": rdf_flags.get("rdf_has_dna", first.get("rdf_has_dna", "")),
        "rdf_has_nucleic_acid": has_na,
        "rdf_has_modified_nucleic_acid": rdf_flags.get(
            "rdf_has_modified_nucleic_acid",
            first.get("rdf_has_modified_nucleic_acid", ""),
        ),
        "alphabet_as_reported": alphabet,
        "source_modification_text": mod,
        "source_label": first.get("aptamerbase_label", ""),
        "audit_only_bibliographic_hint": pmid,
        "publication_hint_group": pmid,
        "repeated_id_context": "true" if len(rows) > 1 else "false",
        "sequence_length_core": "|".join(
            row.get("sequence_length_core", "") for row in rows
        ),
        "chemistry": first.get("chemistry", ""),
        "chemistry_class": first.get("chemistry_class", ""),
        "explicit_local_molecule_evidence": explicit,
        "machine_recommendation": rec,
        "evidence_basis": explicit,
        "remaining_blocker_if_resolved": "|".join(remaining) if remaining else "none",
        "sequence_raw": first.get("sequence_raw", ""),
        "sequence_full": first.get("sequence_full", ""),
    }


def classify_chemistry_row(row: Mapping[str, str], *, primary: bool) -> dict[str, str]:
    """Machine-only chemistry evidence class. Does not fill human chemistry."""
    mod = _mod_text(row)
    canon = _mod_canonical(row)
    chem_class = row.get("chemistry_class") or ""
    molecule = row.get("molecule_type", "")
    rdf_rna = _truthy(row.get("rdf_has_rna", ""))
    evidence = "chemistry_unresolved"
    proposed = ""
    note = "no_chemistry_decision_applied"

    if chem_class == "spiegelmer_l_rna" or "spiegelmer" in canon:
        evidence = "Spiegelmer_L_RNA"
        proposed = ""
        note = "do_not_flatten_L_RNA_to_ordinary_RNA"
    elif chem_class == "pentynyl_du" or "pentynyl" in canon:
        evidence = "modified_DNA_like"
        note = "backbone_or_internal_dU_like_constituent_not_ordinary_RNA"
    elif chem_class == "inverted_dt_construct" or "3'cap" in canon or "[3'-3't]" in canon:
        evidence = "terminal_or_post_selection_modification_only"
        proposed = "RNA"
        note = "inverted_dT_and_PEG_read_as_terminal_cap_not_RNAGenesis_L_RNA;_do_not_force_if_Laura_disagrees"
    elif "2'-deoxy purines and 2'-o-methyl pyrimidines" in canon:
        evidence = "source_supports_mixed_chemistry"
        proposed = "mixed"
        note = "explicit_mixed_sugar_backbone"
    elif chem_class == "ome_or_mixed_sugar" and "2'methoxy pyrimidine" in canon:
        evidence = "source_supports_2OMe_RNA"
        proposed = "2OMe-RNA"
        note = "2OMe_pyrimidine_with_terminal_biotin"
    elif chem_class == "ome_or_mixed_sugar" and "2' o-methyl" in canon and "deoxythymidine" in canon:
        evidence = "source_supports_mixed_chemistry"
        proposed = "mixed"
        note = "2OMe_nucleotides_plus_inverted_dT_and_dT_linkage"
    elif chem_class == "amino_2nh2" or "2'-amino" in canon or "2' nh2" in canon:
        evidence = "source_supports_2NH2_RNA"
        proposed = "2NH2-RNA"
        note = "source_text_2_prime_amino_RNA_backbone"
    elif chem_class == "twof_rna":
        evidence = "needs_publication_source_review"
        proposed = "2F-RNA" if molecule == "RNA" else ""
        note = "2F_pyrimidine_text_present_molecule_must_be_independently_RNA"
    elif chem_class == "terminal_conjugate":
        evidence = "terminal_or_post_selection_modification_only"
        proposed = "RNA" if molecule == "RNA" else ""
        note = "terminal_conjugate_does_not_by_itself_make_backbone_unknown"
    else:
        evidence = "needs_publication_source_review"
        note = "chemistry_not_unambiguously_mapped_from_local_source_text"

    if rdf_rna and evidence == "source_supports_2NH2_RNA":
        pass
    elif evidence in {"source_supports_2NH2_RNA", "source_supports_2OMe_RNA"} and not rdf_rna:
        # Keep the chemistry class but do not pretend molecule is settled.
        note = f"{note}|molecule_not_rdf_rna"

    if evidence not in CHEMISTRY_EVIDENCE_CLASSES:
        raise AptamerBaseCheckpoint1AuditError("chemistry evidence class outside vocabulary")

    remaining = remaining_blockers(row, ignore=frozenset({"chemistry_review"}))
    length = _int_or_empty(row.get("sequence_length_core", ""))
    length_ok = length is not None and CORE_LENGTH_MIN <= length <= CORE_LENGTH_MAX
    become = (
        bool(proposed)
        and proposed in {"RNA", "2F-RNA", "2NH2-RNA", "2OMe-RNA", "mixed"}
        and molecule == "RNA"
        and length_ok
        and not remaining
        and evidence != "Spiegelmer_L_RNA"
        and evidence != "modified_DNA_like"
    )
    return {
        "record_id": row["record_id"],
        "freebase_id": row.get("aptamerbase_id", ""),
        "review_batch": row.get("review_batch", ""),
        "primary_or_secondary": "primary" if primary else "secondary",
        "molecule_type": molecule,
        "rdf_has_rna": row.get("rdf_has_rna", ""),
        "rdf_has_dna": row.get("rdf_has_dna", ""),
        "chemistry_class": chem_class,
        "current_chemistry": row.get("chemistry", ""),
        "source_modification_text": mod,
        "source_label": row.get("aptamerbase_label", ""),
        "audit_only_bibliographic_hint": extract_pmid_hint(row.get("aptamerbase_label", "")),
        "evidence_class": evidence,
        "proposed_chemistry_override": proposed,
        "would_become_technically_eligible_after_override": (
            "true" if become else "false"
        ),
        "remaining_blocker_if_overridden": "|".join(remaining) if remaining else "none",
        "machine_recommendation_note": note,
        "sequence_raw": row.get("sequence_raw", ""),
        "sequence_full": row.get("sequence_full", ""),
    }


def classify_motif_row(row: Mapping[str, str]) -> dict[str, str]:
    """Simulate existing known-motif trim. Does not apply it."""
    full = _int_or_empty(row.get("sequence_length_full", "")) or 0
    motif_len = 0
    for token in _blank(row.get("constant_proposed_trim_length", "")).split("|"):
        parsed = _int_or_empty(token)
        if parsed:
            motif_len = max(motif_len, parsed)
    if motif_len <= 0:
        motif_len = 17
    hyp = full - motif_len if full else 0
    frac = (motif_len / full) if full else 0.0
    in_range = CORE_LENGTH_MIN <= hyp <= CORE_LENGTH_MAX
    over_40 = frac > MAX_TRIM_FRACTION
    remaining = remaining_blockers(row, ignore=frozenset({"construct", "length"}))
    # Length out of range may be resolved by the existing motif trim.
    other = [item for item in remaining if item != "length"]
    if row.get("molecule_type") != "RNA":
        other.append("molecule")
    if (row.get("chemistry") or "") not in {"RNA", "2F-RNA", "2NH2-RNA", "2OMe-RNA"}:
        if row.get("chemistry") not in {"RNA", "2F-RNA"}:
            other.append("chemistry")
    other = list(dict.fromkeys(other))
    if other:
        rec = "cannot_resolve_due_other_blocker"
    elif over_40:
        rec = "needs_source_review"
    elif in_range:
        rec = "approve_existing_known_motif"
    else:
        rec = "reject_trim_keep_full"
    if rec not in MOTIF_RECOMMENDATIONS:
        raise AptamerBaseCheckpoint1AuditError("motif recommendation outside vocabulary")
    sides = row.get("constant_proposal_sides") or row.get("detected_constant_5p", "")
    side = "5'" if "five" in sides or row.get("detected_constant_5p") else ""
    if "three" in (row.get("constant_proposal_sides") or ""):
        side = "3'" if not side else f"{side}/3'"
    motif_name = row.get("detected_constant_5p") or row.get("detected_constant_3p") or ""
    return {
        "record_id": row["record_id"],
        "freebase_id": row.get("aptamerbase_id", ""),
        "source_molecule_type": row.get("molecule_type", ""),
        "chemistry": row.get("chemistry", ""),
        "current_route": row.get("primary_route", ""),
        "primary_reason": row.get("primary_reason", ""),
        "motif_type": motif_name or "t7_promoter_minimal",
        "side": side or "5'",
        "motif_length": str(motif_len),
        "match_confidence": "configured_motif_library",
        "full_length": str(full),
        "hypothetical_trimmed_core_length": str(hyp),
        "hypothetical_trim_fraction": f"{frac:.4f}",
        "post_trim_core_satisfies_20_100": "true" if in_range else "false",
        "trim_exceeds_40pct_review_trigger": "true" if over_40 else "false",
        "other_blocker_remains": "|".join(other) if other else "none",
        "machine_recommendation": rec,
        "motif_sequence": "",
        "sequence_full": row.get("sequence_full", ""),
    }


def accepted_invariants_ok(row: Mapping[str, str]) -> bool:
    length = _int_or_empty(row.get("sequence_length_core", ""))
    return (
        row.get("proposed_decision") == "proposed_accept"
        and row.get("primary_route") == "technically_eligible"
        and row.get("molecule_type") == "RNA"
        and (row.get("chemistry") or "") in {"RNA", "2F-RNA"}
        and length is not None
        and CORE_LENGTH_MIN <= length <= CORE_LENGTH_MAX
        and (row.get("sequence_full") or "") != ""
    )


def issue_flags(row: Mapping[str, str]) -> dict[str, str]:
    reasons = parse_review_reasons(row.get("checkpoint_review_reasons", ""))
    qc = _qc_set(row)
    length = _int_or_empty(row.get("sequence_length_core", ""))
    flags = {
        "notation_issue": "sequence_notation" in reasons,
        "source_molecule_alphabet_conflict": (
            "source_molecule_alphabet_conflict" in reasons
        ),
        "molecule_unresolved": (
            "molecule_type_unresolved" in reasons
            or row.get("molecule_type") == "unknown"
        ),
        "chemistry_unresolved": (
            "chemistry_requires_review" in reasons
            or "chemistry_requires_review" in qc
        ),
        "spiegelmer_l_rna": (
            "spiegelmer_l_rna" in reasons or "spiegelmer_l_rna_review" in qc
        ),
        "length_failure_or_boundary": (
            "length_boundary" in reasons
            or row.get("primary_reason") == "length_out_of_range"
            or (
                length is not None
                and not (CORE_LENGTH_MIN <= length <= CORE_LENGTH_MAX)
            )
        ),
        "known_motif": "constant_region_proposal" in reasons,
        "ssdna_route": row.get("primary_route") == "parked_ssdna",
        "technical_reject": row.get("primary_route") == "technical_reject",
    }
    return {key: "true" if value else "false" for key, value in flags.items()}


def group_identity_ok(rows: Sequence[Mapping[str, str]]) -> bool:
    if len(rows) <= 1:
        return True
    for field_name in SCIENTIFIC_IDENTITY_FIELDS:
        values = {row.get(field_name, "") for row in rows}
        if len(values) > 1:
            return False
    return True


def _apply_rdf_flags(
    row: dict[str, str],
    rdf_by_subject: Mapping[str, Mapping[str, str]],
) -> dict[str, str]:
    out = dict(row)
    flags = rdf_by_subject.get(row.get("aptamerbase_id", ""), {})
    if flags:
        out["rdf_has_nucleic_acid"] = flags.get("rdf_has_nucleic_acid", "")
        if not _blank(out.get("rdf_has_rna", "")):
            out["rdf_has_rna"] = flags.get("rdf_has_rna", out.get("rdf_has_rna", ""))
        if not _blank(out.get("rdf_has_dna", "")):
            out["rdf_has_dna"] = flags.get("rdf_has_dna", out.get("rdf_has_dna", ""))
        if not _blank(out.get("rdf_has_modified_nucleic_acid", "")):
            out["rdf_has_modified_nucleic_acid"] = flags.get(
                "rdf_has_modified_nucleic_acid",
                out.get("rdf_has_modified_nucleic_acid", ""),
            )
    else:
        out.setdefault("rdf_has_nucleic_acid", "")
    return out


def build_decision_support_rows(
    queue_rows: Sequence[Mapping[str, str]],
    rdf_by_subject: Mapping[str, Mapping[str, str]],
) -> tuple[list[dict[str, str]], dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in queue_rows:
        enriched = _apply_rdf_flags(dict(row), rdf_by_subject)
        grouped[enriched.get("aptamerbase_id", "")].append(enriched)

    support: list[dict[str, str]] = []
    judge_units = 0
    safe_groups = 0
    unsafe_groups = 0
    for freebase_id, members in sorted(
        grouped.items(), key=lambda item: item[0] or ""
    ):
        members_sorted = sorted(members, key=lambda row: row["record_id"])
        identical = group_identity_ok(members_sorted)
        judge_members = [row for row in members_sorted if not is_audit_only_row(row)]
        if judge_members:
            judge_units += 1
        if len(members_sorted) > 1:
            if identical:
                safe_groups += 1
            else:
                unsafe_groups += 1
        first = members_sorted[0]
        motif = "none"
        if any(
            "constant_region_proposal"
            in parse_review_reasons(row.get("checkpoint_review_reasons", ""))
            for row in members_sorted
        ):
            motif = "known_motif_proposal_unapplied"
        support.append(
            {
                "freebase_id": freebase_id,
                "member_record_ids": "|".join(row["record_id"] for row in members_sorted),
                "n_physical_rows": str(len(members_sorted)),
                "review_batches": "|".join(
                    sorted({row.get("review_batch", "") for row in members_sorted})
                ),
                "current_proposed_routes": "|".join(
                    sorted({row.get("primary_route", "") for row in members_sorted})
                ),
                "checkpoint_review_reasons": "|".join(
                    sorted(
                        {
                            row.get("checkpoint_review_reasons", "")
                            for row in members_sorted
                        }
                    )
                ),
                "source_object_type": first.get("source_object_type", ""),
                "rdf_has_rna": first.get("rdf_has_rna", ""),
                "rdf_has_dna": first.get("rdf_has_dna", ""),
                "rdf_has_nucleic_acid": first.get("rdf_has_nucleic_acid", ""),
                "rdf_has_modified_nucleic_acid": first.get(
                    "rdf_has_modified_nucleic_acid", ""
                ),
                "molecule_type": "|".join(
                    sorted({row.get("molecule_type", "") for row in members_sorted})
                ),
                "alphabet_as_reported": "|".join(
                    sorted(
                        {row.get("alphabet_as_reported", "") for row in members_sorted}
                    )
                ),
                "t_to_u_applied": "|".join(
                    sorted({row.get("t_to_u_applied", "") for row in members_sorted})
                ),
                "chemistry": "|".join(
                    sorted({row.get("chemistry", "") for row in members_sorted})
                ),
                "chemistry_class": "|".join(
                    sorted({row.get("chemistry_class", "") for row in members_sorted})
                ),
                "source_modification_present": (
                    "true" if _blank(_mod_text(first)) else "false"
                ),
                "source_modification_text": _mod_text(first),
                "sequence_length_full": "|".join(
                    row.get("sequence_length_full", "") for row in members_sorted
                ),
                "sequence_length_core": "|".join(
                    row.get("sequence_length_core", "") for row in members_sorted
                ),
                "known_motif_status": motif,
                "source_label": first.get("aptamerbase_label", ""),
                "audit_only_bibliographic_hint": extract_pmid_hint(
                    first.get("aptamerbase_label", "")
                ),
                "group_scientifically_identical": "true" if identical else "false",
                "safe_for_groupwise_review": (
                    "true" if identical and len(members_sorted) > 1 else "false"
                ),
                "judgement_required_member_count": str(len(judge_members)),
                "sequence_raw": first.get("sequence_raw", ""),
                "sequence_full": first.get("sequence_full", ""),
                "sequence_core": first.get("sequence_core", ""),
            }
        )
    summary = {
        "judgement_required_source_id_units": judge_units,
        "safe_multi_record_groups": safe_groups,
        "unsafe_multi_record_groups": unsafe_groups,
    }
    return support, summary


def _is_chemistry_row(row: Mapping[str, str]) -> bool:
    reasons = parse_review_reasons(row.get("checkpoint_review_reasons", ""))
    qc = _qc_set(row)
    chem_class = row.get("chemistry_class") or ""
    return bool(
        "chemistry_requires_review" in reasons
        or "spiegelmer_l_rna" in reasons
        or "chemistry_requires_review" in qc
        or chem_class
        in {
            "amino_2nh2",
            "ome_or_mixed_sugar",
            "inverted_dt_construct",
            "pentynyl_du",
            "spiegelmer_l_rna",
            "iso_guanosine",
            "unusual_modified_nucleotide",
        }
    )


def build_audit_package(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    rdf_by_subject: Mapping[str, Mapping[str, str]] | None = None,
    integrity: FrozenIntegrity | None = None,
    random_seed: int = RANDOM_SEED,
) -> AuditPackage:
    """Build all decision-support tables from the prepared review queue."""
    rdf_by_subject = rdf_by_subject or {}
    if any(_blank(row.get(name, "")) for row in queue_rows for name in MANUAL_FIELDS):
        raise AptamerBaseCheckpoint1AuditError(
            "Human decision fields must remain blank during the audit"
        )
    ids = [row["record_id"] for row in queue_rows]
    if len(ids) != len(set(ids)):
        raise AptamerBaseCheckpoint1AuditError("duplicate record_id in review queue")

    enriched = [_apply_rdf_flags(dict(row), rdf_by_subject) for row in queue_rows]
    judgement = [row for row in enriched if not is_audit_only_row(row)]
    audit_only = [row for row in enriched if is_audit_only_row(row)]
    support, grouping_summary = build_decision_support_rows(enriched, rdf_by_subject)

    notation_rows = [
        classify_notation_row(row)
        for row in enriched
        if "sequence_notation"
        in parse_review_reasons(row.get("checkpoint_review_reasons", ""))
    ]
    dna_u_rows = [
        classify_dna_u_row(row)
        for row in enriched
        if "source_molecule_alphabet_conflict"
        in parse_review_reasons(row.get("checkpoint_review_reasons", ""))
    ]

    molecule_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in enriched:
        if row.get("review_batch") != "02_molecule_type_unresolved":
            continue
        molecule_groups[row.get("aptamerbase_id", "")].append(row)
    molecule_rows = [
        classify_molecule_unit(
            sorted(members, key=lambda item: item["record_id"]),
            rdf_by_subject.get(freebase_id, {}),
        )
        for freebase_id, members in sorted(molecule_groups.items())
    ]

    chemistry_rows: list[dict[str, str]] = []
    for row in enriched:
        if not _is_chemistry_row(row):
            continue
        primary = row.get("review_batch") == "03_chemistry_review"
        chemistry_rows.append(classify_chemistry_row(row, primary=primary))

    motif_rows = [
        classify_motif_row(row)
        for row in enriched
        if row.get("review_batch") == "04_known_motif_construct"
    ]
    motif_summary_rows = [
        {col: row.get(col, "") for col in MOTIF_SUMMARY_COLUMNS} for row in motif_rows
    ]

    audit_support: list[dict[str, str]] = []
    for row in audit_only:
        length = _int_or_empty(row.get("sequence_length_core", ""))
        rec = row.get("review_recommendation") or "keep_current_route"
        if rec != "keep_current_route":
            rec = "keep_current_route"
        audit_support.append(
            {
                "record_id": row["record_id"],
                "review_batch": row.get("review_batch", ""),
                "length_bucket": length_bucket(length),
                "chemistry": row.get("chemistry", ""),
                "t_to_u_applied": row.get("t_to_u_applied", ""),
                "source_modification_present": (
                    "true" if _blank(_mod_text(row)) else "false"
                ),
                "qc_flags": row.get("qc_flags", ""),
                "accepted_record_invariants_ok": (
                    "true" if accepted_invariants_ok(row) else "false"
                ),
                "machine_recommendation": rec,
                "sequence_length_core": row.get("sequence_length_core", ""),
                "molecule_type": row.get("molecule_type", ""),
                "primary_route": row.get("primary_route", ""),
            }
        )

    compound_rows: list[dict[str, str]] = []
    primary_ignore = {
        "01_sequence_or_source_conflict": frozenset(),
        "02_molecule_type_unresolved": frozenset({"molecule_unknown"}),
        "03_chemistry_review": frozenset({"chemistry_review"}),
        "04_known_motif_construct": frozenset({"construct", "length"}),
        "05_accept_with_diagnostics": frozenset(),
        "06_random_kept_audit": frozenset(),
    }
    for row in judgement:
        flags = issue_flags(row)
        true_flags = [name for name, value in flags.items() if value == "true"]
        primary = row.get("review_batch", "")
        ignore = set(primary_ignore.get(primary, frozenset()))
        reasons = parse_review_reasons(row.get("checkpoint_review_reasons", ""))
        if "sequence_notation" in reasons:
            # Hypothetical notation repair still leaves listed blockers.
            pass
        if "source_molecule_alphabet_conflict" in reasons:
            ignore.add("ssdna_park")
        remaining = remaining_blockers(row, ignore=frozenset(ignore))
        compound_rows.append(
            {
                "record_id": row["record_id"],
                "review_batch": row.get("review_batch", ""),
                "freebase_id": row.get("aptamerbase_id", ""),
                **flags,
                "human_issue_count": str(len(true_flags)),
                "primary_issue": primary,
                "secondary_blockers_if_primary_resolved": (
                    "|".join(remaining) if remaining else "none"
                ),
            }
        )

    random_rows = [
        row for row in audit_only if row.get("review_batch") == "06_random_kept_audit"
    ]
    if random_seed != RANDOM_SEED:
        raise AptamerBaseCheckpoint1AuditError(
            "AptamerBase random-kept audit seed is frozen at 42; refusing resample"
        )
    if len(random_rows) not in {0, RANDOM_SAMPLE_SIZE}:
        # Synthetic packages may have fewer rows; production freeze is 30.
        pass

    counts = Counter(row["human_issue_count"] for row in compound_rows)
    notation_recs = Counter(row["machine_recommendation"] for row in notation_rows)
    dna_recs = Counter(row["machine_recommendation"] for row in dna_u_rows)
    mol_recs = Counter(row["machine_recommendation"] for row in molecule_rows)
    chem_ev = Counter(row["evidence_class"] for row in chemistry_rows)
    motif_recs = Counter(row["machine_recommendation"] for row in motif_rows)
    boundary = [
        row for row in audit_only if row.get("review_batch") == "05_accept_with_diagnostics"
    ]
    aggregate = {
        "active_review_rows": len(enriched),
        "judgement_required_rows": len(judgement),
        "audit_only_rows": len(audit_only),
        "judgement_required_source_id_units": grouping_summary[
            "judgement_required_source_id_units"
        ],
        "safe_multi_record_groups": grouping_summary["safe_multi_record_groups"],
        "unsafe_multi_record_groups": grouping_summary["unsafe_multi_record_groups"],
        "notation_recommendation_counts": dict(notation_recs),
        "dna_u_recommendation_counts": dict(dna_recs),
        "molecule_recommendation_counts": dict(mol_recs),
        "chemistry_evidence_counts": dict(chem_ev),
        "motif_recommendation_counts": dict(motif_recs),
        "compound_exactly_one": counts.get("1", 0),
        "compound_exactly_two": counts.get("2", 0),
        "compound_three_or_more": sum(
            n for key, n in counts.items() if int(key) >= 3
        ),
        "boundary_rows": len(boundary),
        "random_kept_rows": len(random_rows),
        "random_seed": RANDOM_SEED,
        "bulk_confirmation_blank": True,
        "human_fields_blank": True,
        "s2_s3_unchanged": True,
    }
    summary_rows = [
        {
            "freebase_id": row["freebase_id"],
            "member_record_ids": row["member_record_ids"],
            "n_physical_rows": row["n_physical_rows"],
            "review_batches": row["review_batches"],
            "current_proposed_routes": row["current_proposed_routes"],
            "checkpoint_review_reasons": row["checkpoint_review_reasons"],
            "source_object_type": row["source_object_type"],
            "rdf_has_rna": row["rdf_has_rna"],
            "rdf_has_dna": row["rdf_has_dna"],
            "rdf_has_nucleic_acid": row["rdf_has_nucleic_acid"],
            "molecule_type": row["molecule_type"],
            "alphabet_as_reported": row["alphabet_as_reported"],
            "t_to_u_applied": row["t_to_u_applied"],
            "chemistry": row["chemistry"],
            "chemistry_class": row["chemistry_class"],
            "sequence_length_full": row["sequence_length_full"],
            "sequence_length_core": row["sequence_length_core"],
            "known_motif_status": row["known_motif_status"],
            "audit_only_bibliographic_hint": row["audit_only_bibliographic_hint"],
            "group_scientifically_identical": row["group_scientifically_identical"],
            "safe_for_groupwise_review": row["safe_for_groupwise_review"],
            "judgement_required_member_count": row["judgement_required_member_count"],
        }
        for row in support
    ]
    return AuditPackage(
        integrity=integrity
        or FrozenIntegrity(
            hashes={},
            s3_canonical_equals_s2=True,
            canonical_rows=0,
            human_fields_populated=0,
        ),
        decision_support_rows=support,
        decision_support_summary_rows=summary_rows,
        notation_rows=notation_rows,
        dna_u_rows=dna_u_rows,
        molecule_rows=molecule_rows,
        chemistry_rows=chemistry_rows,
        motif_rows=motif_rows,
        motif_summary_rows=motif_summary_rows,
        audit_only_rows=audit_support,
        compound_rows=compound_rows,
        aggregate=aggregate,
    )


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, FrozenIntegrity):
        return {
            "hashes": value.hashes,
            "s3_canonical_equals_s2": value.s3_canonical_equals_s2,
            "canonical_rows": value.canonical_rows,
            "human_fields_populated": value.human_fields_populated,
        }
    return value


def format_audit_summary_markdown(package: AuditPackage) -> str:
    agg = package.aggregate
    lines = [
        "# AptamerBase CHECKPOINT-1 decision-support audit",
        "",
        "Sequence-free aggregate only. Human decision fields remain blank.",
        "CHECKPOINT-1 remains open and unapplied. Global S4 has not been run.",
        "",
        "## Integrity",
        "",
        f"- S3 canonical == S2 canonical: `{package.integrity.s3_canonical_equals_s2}`",
        f"- canonical rows: `{package.integrity.canonical_rows}`",
        f"- human fields populated: `{package.integrity.human_fields_populated}`",
        "",
    ]
    for key, digest in sorted(package.integrity.hashes.items()):
        lines.append(f"- `{key}` SHA-256: `{digest}`")
    lines.extend(
        [
            "",
            "## Workload",
            "",
            f"- judgement-required physical rows: `{agg.get('judgement_required_rows')}`",
            f"- audit-only rows: `{agg.get('audit_only_rows')}`",
            f"- judgement-required source-ID review units: "
            f"`{agg.get('judgement_required_source_id_units')}`",
            f"- safe multi-record Freebase groups: `{agg.get('safe_multi_record_groups')}`",
            f"- unsafe multi-record Freebase groups: `{agg.get('unsafe_multi_record_groups')}`",
            "",
            "## Batch 01 notation recommendations",
            "",
        ]
    )
    for name, count in sorted(
        (agg.get("notation_recommendation_counts") or {}).items()
    ):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "## Batch 01 RDF DNA × U", ""])
    for name, count in sorted((agg.get("dna_u_recommendation_counts") or {}).items()):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "## Batch 02 molecule recommendations", ""])
    for name, count in sorted((agg.get("molecule_recommendation_counts") or {}).items()):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "## Batch 03 chemistry evidence", ""])
    for name, count in sorted((agg.get("chemistry_evidence_counts") or {}).items()):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "## Batch 04 motif recommendations", ""])
    for name, count in sorted((agg.get("motif_recommendation_counts") or {}).items()):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Audit-only",
            "",
            f"- length-boundary: `{agg.get('boundary_rows')}`",
            f"- random-kept (seed {RANDOM_SEED}): `{agg.get('random_kept_rows')}`",
            "- bulk confirmation blank: `true`",
            "- machine recommendation: `keep_current_route`",
            "",
            "## Compound issues (judgement-required)",
            "",
            f"- exactly one human issue: `{agg.get('compound_exactly_one')}`",
            f"- exactly two human issues: `{agg.get('compound_exactly_two')}`",
            f"- three or more human issues: `{agg.get('compound_three_or_more')}`",
            "",
            "No human decision has been recorded.",
            "CHECKPOINT-1 remains open.",
            "No AptamerBase record is authorised for global S4.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def write_audit_package(package: AuditPackage, audit_dir: Path) -> None:
    """Write ignored sequence-bearing tables and a sequence-free summary."""
    audit_dir = Path(audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(
        audit_dir / "aptamerbase_checkpoint1_decision_support.csv",
        DECISION_SUPPORT_COLUMNS,
        package.decision_support_rows,
    )
    write_csv_atomic(
        audit_dir / "aptamerbase_checkpoint1_decision_support_summary.csv",
        tuple(package.decision_support_summary_rows[0].keys())
        if package.decision_support_summary_rows
        else (
            "freebase_id",
            "member_record_ids",
            "n_physical_rows",
            "review_batches",
            "safe_for_groupwise_review",
        ),
        package.decision_support_summary_rows,
    )
    write_csv_atomic(
        audit_dir / "aptamerbase_checkpoint1_notation_audit.csv",
        NOTATION_AUDIT_COLUMNS,
        package.notation_rows,
    )
    write_csv_atomic(
        audit_dir / "aptamerbase_checkpoint1_source_conflict_audit.csv",
        DNA_U_AUDIT_COLUMNS,
        package.dna_u_rows,
    )
    write_csv_atomic(
        audit_dir / "aptamerbase_checkpoint1_molecule_audit.csv",
        MOLECULE_AUDIT_COLUMNS,
        package.molecule_rows,
    )
    write_csv_atomic(
        audit_dir / "aptamerbase_checkpoint1_chemistry_audit.csv",
        CHEMISTRY_AUDIT_COLUMNS,
        package.chemistry_rows,
    )
    write_csv_atomic(
        audit_dir / "aptamerbase_checkpoint1_motif_audit.csv",
        MOTIF_AUDIT_COLUMNS,
        package.motif_rows,
    )
    write_csv_atomic(
        audit_dir / "aptamerbase_checkpoint1_motif_audit_summary.csv",
        MOTIF_SUMMARY_COLUMNS,
        package.motif_summary_rows,
    )
    write_csv_atomic(
        audit_dir / "aptamerbase_checkpoint1_audit_only_support.csv",
        AUDIT_ONLY_SUPPORT_COLUMNS,
        package.audit_only_rows,
    )
    write_csv_atomic(
        audit_dir / "aptamerbase_checkpoint1_compound_issue_matrix.csv",
        COMPOUND_MATRIX_COLUMNS,
        package.compound_rows,
    )
    _write_text_atomic(
        audit_dir / "aptamerbase_checkpoint1_audit_summary.md",
        format_audit_summary_markdown(package),
    )
    integrity_payload = {
        "source_key": "aptamerbase",
        "checkpoint": "CHECKPOINT-1",
        "audit_only": True,
        "human_decisions_populated": False,
        "checkpoint_closed": False,
        "s4_started": False,
        "integrity": _json_safe(package.integrity),
        "aggregate": _json_safe(package.aggregate),
    }
    _write_text_atomic(
        audit_dir / "aptamerbase_checkpoint1_integrity.json",
        json.dumps(integrity_payload, indent=2, sort_keys=True),
    )


def run_aptamerbase_checkpoint1_audit(
    *,
    repo_root: Path,
    queue_rows: Sequence[Mapping[str, str]],
    audit_dir: Path,
    rdf_path: Path | None = None,
    freeze_production_artefacts: bool = False,
) -> AuditPackage:
    """Audit the prepared queue. Optional production freeze when artefacts exist."""
    integrity: FrozenIntegrity | None = None
    if freeze_production_artefacts:
        integrity = freeze_scientific_artefacts(repo_root)
    subjects = [row.get("aptamerbase_id", "") for row in queue_rows]
    rdf_flags = load_rdf_type_flags(rdf_path, subjects)
    package = build_audit_package(
        queue_rows=queue_rows,
        rdf_by_subject=rdf_flags,
        integrity=integrity,
    )
    write_audit_package(package, audit_dir)
    return package

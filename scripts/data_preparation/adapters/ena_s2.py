"""ENA S2 adapter: RNA source contract and shared normalisation.

Consumes S1 canonical rows plus the ENA source-metadata sidecar. Sequence
cleaning uses the shared normaliser only. Group-wise constant-region inference
consumes the sidecar primary ``experiment_group_id``. Does not accept, reject
or park records. Does not apply newly inferred constant-region trims.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from common.corpus_schema import (
    format_qc_flags,
    validate_s2_record,
)
from common.sequence_normalisation import (
    ALPHABET_MISSING,
    TRIM_CONFIDENCE_NA,
    SequenceNormalisationRules,
    load_normalisation_rules,
    normalise_sequence,
)

QC_DELIMITER: Final[str] = "|"

GROUP_INFERENCE_KEY: Final[str] = "experiment_group_id"
SUPPORTING_GROUP_FIELD: Final[str] = "experiment_group_ids"
FAMILY_GROUP_FIELDS: Final[tuple[str, ...]] = (
    "near_duplicate_family_id",
    "ena_effective_near_duplicate_family_id",
)

LEGACY_ENA_MODULES: Final[frozenset[str]] = frozenset(
    {
        "finalize_ena_aptamer_supplement",
        "process_ena_aptamer_candidates",
        "inspect_ena_aptamer_records",
        "ena_candidate_rules",
        "ena_review_rules",
        "ena_review_v2_rules",
        "consolidate_ena_candidate_review",
        "refine_ena_manual_review",
    }
)

S2_QC_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "target_name_raw",
    "alphabet_as_reported",
    "molecule_type",
    "chemistry",
    "molecule_evidence_source",
    "t_to_u_applied",
    "sequence_length_full",
    "sequence_length_core",
    "reported_length_raw",
    "length_matches_source",
    "detected_motifs",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "qc_flags",
    "experiment_group_id",
    "sequence_corrected_applied",
    "sequence_quality_status",
    "automatic_concern_flags",
    "source_promoter_or_template_concern",
    "source_t7_concern",
    "group_consensus_proposal",
    "known_motif_detected",
    "review_reasons",
)

CONSTANT_PROPOSAL_COLUMNS: Final[tuple[str, ...]] = (
    "proposal_id",
    "experiment_group_id",
    "proposal_source",
    "side",
    "proposed_sequence",
    "motif_id",
    "motif_length",
    "support",
    "records_considered",
    "records_matching_exactly",
    "confidence",
    "status",
    "applied",
    "reason_not_applied",
    "reason",
)

MEMBERSHIP_COLUMNS: Final[tuple[str, ...]] = (
    "proposal_id",
    "experiment_group_id",
    "record_id",
    "proposal_source",
    "side",
)

REVIEW_RELEVANT_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "missing_sequence",
        "invalid_character",
        "alignment_gaps",
        "ambiguous_base",
        "mixed_t_u",
        "molecule_type_unknown",
        "t_in_reported_rna",
        "u_in_reported_dna",
        "known_promoter_detected",
        "trim_requires_review",
        "core_below_min_length",
        "core_above_max_length",
        "constants_suspected_unresolved",
    }
)

REVIEW_REASON_SOURCE_PROMOTER: Final[str] = "source_promoter_or_template_concern"
REVIEW_REASON_GROUP_CONSENSUS: Final[str] = "group_consensus_proposal"
REVIEW_REASON_LENGTH_MISMATCH: Final[str] = "source_length_mismatch"
REVIEW_REASON_PROMOTER_DISAGREEMENT: Final[str] = (
    "source_vs_shared_promoter_disagreement"
)


class EnaS2Error(ValueError):
    """Hard failure during ENA S2 normalisation."""


@dataclass(frozen=True)
class EnaNormalisationPolicy:
    """Tracked ENA S2 source-normalisation policy."""

    source_key: str
    contract_version: str
    molecule_type: str
    chemistry: str
    molecule_evidence_source: str
    reported_length_field: str
    group_inference_sidecar_field: str
    apply_approved_trims: bool
    group_inference_key: str
    do_not_use_supporting_group_ids: bool
    do_not_use_family_id_as_group: bool
    do_not_infer_molecule_from_alphabet: bool
    do_not_apply_inferred_trims: bool


@dataclass(frozen=True)
class MoleculeChemistryResult:
    """Resolved molecule type and chemistry from the ENA source contract."""

    source_value: str
    molecule_type: str
    chemistry: str
    evidence_source: str
    qc_flags: tuple[str, ...]


@dataclass
class EnaS2RowResult:
    """Canonical S2 row plus QC sidecar payload for one record."""

    canonical: dict[str, str]
    qc: dict[str, str]
    transformations: tuple[str, ...] = ()
    sidecar_experiment_group_id: str = ""
    sidecar_experiment_group_ids: str = ""
    sidecar_family_id: str = ""


@dataclass
class EnaS2Stats:
    """Aggregate S2 counts (no sequences or row identifiers)."""

    s1_rows: int = 0
    source_metadata_rows: int = 0
    s2_rows: int = 0
    unique_record_ids: int = 0
    unique_native_ids: int = 0
    missing_sequence_rows: int = 0
    nonempty_sequence_rows: int = 0
    records_dropped: int = 0
    records_parked: int = 0
    order_preserved: bool = False
    provenance_preserved: bool = False
    sequence_raw_unchanged: bool = False
    target_name_raw_unchanged: bool = False
    sidecar_unchanged: bool = False
    transformation_counts: dict[str, int] = field(default_factory=dict)
    alphabet_counts: dict[str, int] = field(default_factory=dict)
    molecule_type_counts: dict[str, int] = field(default_factory=dict)
    chemistry_counts: dict[str, int] = field(default_factory=dict)
    t_to_u_count: int = 0
    t_to_u_by_molecule: dict[str, int] = field(default_factory=dict)
    invalid_character_count: int = 0
    alignment_gaps_count: int = 0
    ambiguous_base_count: int = 0
    mixed_t_u_count: int = 0
    known_motif_detection_count: int = 0
    trim_review_count: int = 0
    core_below_min_count: int = 0
    core_above_max_count: int = 0
    rows_with_any_qc_flag: int = 0
    rows_with_multiple_qc_flags: int = 0
    review_candidate_rows: int = 0
    review_reason_counts: dict[str, int] = field(default_factory=dict)
    core_differs_from_full: int = 0
    applied_trims: int = 0
    construct_scope_counts: dict[str, int] = field(default_factory=dict)
    trim_status_counts: dict[str, int] = field(default_factory=dict)
    trim_confidence_counts: dict[str, int] = field(default_factory=dict)
    length_full_buckets: dict[str, int] = field(default_factory=dict)
    length_core_buckets: dict[str, int] = field(default_factory=dict)
    qc_flag_counts: dict[str, int] = field(default_factory=dict)
    length_full_values: list[int] = field(default_factory=list)
    length_core_values: list[int] = field(default_factory=list)
    length_mismatch_count: int = 0
    constant_region_proposals: int = 0
    proposal_source_counts: dict[str, int] = field(default_factory=dict)
    groups_considered: int = 0
    groups_meeting_min_size: int = 0
    groups_below_min_size: int = 0
    records_in_eligible_groups: int = 0
    primary_experiment_groups: int = 0
    populated_primary_experiment_groups: int = 0
    supporting_group_ids_expanded: int = 0
    group_size_histogram: dict[str, int] = field(default_factory=dict)
    five_prime_proposals: int = 0
    three_prime_proposals: int = 0
    records_with_medium_confidence_proposal: int = 0
    high_confidence_trims_applied: int = 0
    source_promoter_or_template_count: int = 0
    source_t7_concern_count: int = 0
    overlap_source_and_shared_motif_count: int = 0
    source_concern_without_shared_motif_count: int = 0
    shared_motif_without_source_concern_count: int = 0
    sequence_corrections_applied: int = 0
    blank_source_family_ids: int = 0
    nonblank_source_family_ids: int = 0
    materialised_singleton_family_ids: int = 0
    exact_duplicate_sequence_full_values: int = 0
    records_in_exact_duplicate_sequence_full: int = 0
    exact_duplicate_sequence_core_values: int = 0
    records_in_exact_duplicate_sequence_core: int = 0
    constant_region_reason: str = "proposals_only_not_applied"
    known_motifs_scanned: tuple[str, ...] = ()


def assert_no_legacy_ena_normaliser_import() -> None:
    """Hard-fail if a pre-unified ENA normalisation/finalisation module is loaded."""
    loaded = set(sys.modules)
    for name in LEGACY_ENA_MODULES:
        if name in loaded or f"scripts.data_preparation.{name}" in loaded:
            raise EnaS2Error(
                "legacy ENA normalisation/finalisation modules must not be "
                "imported by S2"
            )


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EnaS2Error(f"{name} must be a JSON object")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise EnaS2Error(f"{name} must be a boolean")
    return value


def _require_nonempty_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EnaS2Error(f"{name} must be a non-empty string")
    return value.strip()


def load_ena_policy(path: str | Path) -> EnaNormalisationPolicy:
    """Load and validate the ENA source-normalisation policy JSON."""
    policy_path = Path(path)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EnaS2Error(f"cannot read ENA policy: {exc.strerror}") from exc
    except json.JSONDecodeError as exc:
        raise EnaS2Error(f"ENA policy JSON is invalid: {exc.msg}") from exc

    data = _require_mapping(payload, "policy")
    source_key = data.get("source_key")
    if source_key != "ena":
        raise EnaS2Error("policy source_key must be 'ena'")
    grouping = _require_nonempty_str(
        data.get("group_inference_key"), "group_inference_key"
    )
    if grouping != GROUP_INFERENCE_KEY:
        raise EnaS2Error(
            "ENA S2 group_inference_key must be 'experiment_group_id'; "
            "supporting experiment_group_ids must not be the grouping key"
        )
    sidecar_field = _require_nonempty_str(
        data.get("group_inference_sidecar_field"),
        "group_inference_sidecar_field",
    )
    if sidecar_field != GROUP_INFERENCE_KEY:
        raise EnaS2Error(
            "ENA S2 must consume sidecar experiment_group_id as the grouping key"
        )
    if data.get("apply_approved_trims") is True:
        raise EnaS2Error("ENA S2 must not apply approved trims in this milestone")
    molecule_type = _require_nonempty_str(data.get("molecule_type"), "molecule_type")
    chemistry = _require_nonempty_str(data.get("chemistry"), "chemistry")
    if molecule_type != "RNA" or chemistry != "RNA":
        raise EnaS2Error(
            "ENA S2 source contract requires molecule_type=RNA and chemistry=RNA"
        )
    do_not_infer = _require_bool(
        data.get("do_not_infer_molecule_from_alphabet", True),
        "do_not_infer_molecule_from_alphabet",
    )
    if not do_not_infer:
        raise EnaS2Error("ENA molecule type must not be inferred from alphabet")
    do_not_use_supporting = _require_bool(
        data.get("do_not_use_supporting_group_ids", True),
        "do_not_use_supporting_group_ids",
    )
    if not do_not_use_supporting:
        raise EnaS2Error("ENA S2 must not use experiment_group_ids as grouping")
    do_not_use_family = _require_bool(
        data.get("do_not_use_family_id_as_group", True),
        "do_not_use_family_id_as_group",
    )
    if not do_not_use_family:
        raise EnaS2Error("ENA S2 must not use family IDs as grouping")
    do_not_apply = _require_bool(
        data.get("do_not_apply_inferred_trims", True),
        "do_not_apply_inferred_trims",
    )
    if not do_not_apply:
        raise EnaS2Error("ENA S2 must not apply inferred constant-region trims")

    return EnaNormalisationPolicy(
        source_key=source_key,
        contract_version=_require_nonempty_str(
            data.get("contract_version"), "contract_version"
        ),
        molecule_type=molecule_type,
        chemistry=chemistry,
        molecule_evidence_source=_require_nonempty_str(
            data.get("molecule_evidence_source"), "molecule_evidence_source"
        ),
        reported_length_field=str(data.get("reported_length_field", "")),
        group_inference_sidecar_field=sidecar_field,
        apply_approved_trims=_require_bool(
            data.get("apply_approved_trims"), "apply_approved_trims"
        ),
        group_inference_key=grouping,
        do_not_use_supporting_group_ids=do_not_use_supporting,
        do_not_use_family_id_as_group=do_not_use_family,
        do_not_infer_molecule_from_alphabet=do_not_infer,
        do_not_apply_inferred_trims=do_not_apply,
    )


def resolve_ena_molecule_and_chemistry(
    policy: EnaNormalisationPolicy,
) -> MoleculeChemistryResult:
    """Return the fixed experimental RNA contract.

    Alphabet is never consulted. T-encoded reviewed sequences remain RNA.
    """
    return MoleculeChemistryResult(
        source_value="source_contract",
        molecule_type=policy.molecule_type,
        chemistry=policy.chemistry,
        evidence_source=policy.molecule_evidence_source,
        qc_flags=(),
    )


def _motif_names_by_side(motifs: Sequence[Any]) -> tuple[str, str]:
    five: list[str] = []
    three: list[str] = []
    for motif in motifs:
        name = getattr(motif, "name", str(motif))
        position = getattr(motif, "position", "")
        if position == "five_prime":
            five.append(name)
        elif position == "three_prime":
            three.append(name)
    return (
        QC_DELIMITER.join(sorted(set(five))),
        QC_DELIMITER.join(sorted(set(three))),
    )


def length_bucket(length: int | None) -> str:
    """Spec-aligned length buckets for the ENA S2 report."""
    if length is None:
        return "missing"
    if length < 20:
        return "<20"
    if length <= 25:
        return "20-25"
    if length < 90:
        return "26-89"
    if length <= 100:
        return "90-100"
    return ">100"


def summarise_lengths(values: Sequence[int]) -> tuple[str, str, str]:
    """Return min / median / max as strings; empty when no values."""
    if not values:
        return "", "", ""
    ordered = sorted(values)
    med = statistics.median(ordered)
    if isinstance(med, float) and med == int(med):
        med_str = str(int(med))
    else:
        med_str = str(med)
    return str(ordered[0]), med_str, str(ordered[-1])


def source_has_promoter_or_template_concern(source_metadata: Mapping[str, str]) -> bool:
    """True when prior source-review promoter/template provenance is present.

    This inspects sidecar flags only. It does not authorise a trim and does
    not import legacy ENA primer/T7 matching logic.
    """
    quality = (source_metadata.get("sequence_quality_status") or "").lower()
    flags = (source_metadata.get("automatic_concern_flags") or "").lower()
    return (
        "promoter" in quality
        or "template" in quality
        or "promoter" in flags
        or "t7" in flags
    )


def source_has_t7_concern(source_metadata: Mapping[str, str]) -> bool:
    """True when sidecar automatic_concern_flags mention T7."""
    flags = (source_metadata.get("automatic_concern_flags") or "").lower()
    return "t7" in flags


def _parse_reported_length(raw: str) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        try:
            parsed = float(text)
        except ValueError:
            return None
        if parsed != int(parsed):
            return None
        value = int(parsed)
    return value


def split_supporting_group_ids(raw: str) -> tuple[str, ...]:
    """Split sidecar supporting group IDs for diagnostic counting only."""
    if not raw or not raw.strip():
        return ()
    parts: list[str] = []
    for token in raw.replace(";", "|").split("|"):
        item = token.strip()
        if item:
            parts.append(item)
    return tuple(parts)


def group_size_bucket(size: int) -> str:
    """Histogram bucket matching shared inference diagnostics."""
    if size < 5:
        return "1-4"
    if size < 10:
        return "5-9"
    if size < 25:
        return "10-24"
    if size < 50:
        return "25-49"
    return "50+"


def _length_matches_source(s2_length: str, reported_raw: str) -> str:
    if s2_length == "":
        return "n/a" if not reported_raw.strip() else "false"
    reported = _parse_reported_length(reported_raw)
    if reported is None:
        return "n/a"
    try:
        computed = int(s2_length)
    except ValueError:
        return "false"
    return "true" if computed == reported else "false"


def _initial_review_reasons(
    qc_flags: Sequence[str],
    *,
    source_promoter: bool,
    known_motif: bool,
    length_matches: str,
) -> list[str]:
    reasons: list[str] = []
    for flag in qc_flags:
        if flag in REVIEW_RELEVANT_FLAGS:
            reasons.append(flag)
    if source_promoter:
        reasons.append(REVIEW_REASON_SOURCE_PROMOTER)
    if source_promoter != known_motif:
        reasons.append(REVIEW_REASON_PROMOTER_DISAGREEMENT)
    if length_matches == "false":
        reasons.append(REVIEW_REASON_LENGTH_MISMATCH)
    return sorted(set(reasons))


def normalise_ena_record(
    s1_record: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: EnaNormalisationPolicy,
    rules: SequenceNormalisationRules | None = None,
) -> EnaS2RowResult:
    """Normalise one ENA S1 record into S2 canonical + QC rows."""
    active_rules = rules if rules is not None else load_normalisation_rules()
    if s1_record["record_id"] != source_metadata.get("record_id", ""):
        raise EnaS2Error("canonical and sidecar record_id values must match")

    sequence_raw = s1_record["sequence_raw"]
    molchem = resolve_ena_molecule_and_chemistry(policy)
    qc_flags: list[str] = list(molchem.qc_flags)

    # Reviewed S1 sequence_raw is the only normalisation input.
    # sequence_original / deposited sequences are sidecar provenance only.
    _ = source_metadata.get("sequence_original", "")
    _ = source_metadata.get("sequence", "")
    _ = source_metadata.get(SUPPORTING_GROUP_FIELD, "")
    for family_field in FAMILY_GROUP_FIELDS:
        _ = source_metadata.get(family_field, "")

    norm = normalise_sequence(
        sequence_raw,
        molecule_type=molchem.molecule_type,
        trim_plan=None,
        rules=active_rules,
    )
    qc_flags.extend(norm.qc_flags)

    resolved_molecule = molchem.molecule_type
    sequence_full = norm.sequence_full or ""
    sequence_core = sequence_full
    five_motifs, three_motifs = _motif_names_by_side(norm.detected_motifs)

    if norm.sequence_full is None:
        construct_scope = "unknown"
        trim_status = "not_applicable"
        trim_confidence = TRIM_CONFIDENCE_NA
        if "missing_sequence" not in qc_flags:
            qc_flags.append("missing_sequence")
        sequence_full = ""
        sequence_core = ""
        length_full = ""
        length_core = ""
        alphabet = ALPHABET_MISSING
        t_to_u = "false"
    elif norm.detected_motifs:
        construct_scope = "unknown"
        trim_status = "constants_suspected_unresolved"
        trim_confidence = TRIM_CONFIDENCE_NA
        qc_flags.append("constants_suspected_unresolved")
        qc_flags.append("trim_requires_review")
        length_full = str(len(sequence_full))
        length_core = str(len(sequence_core))
        alphabet = norm.alphabet_as_reported
        t_to_u = "true" if norm.t_to_u_applied else "false"
    else:
        construct_scope = "unknown"
        trim_status = "no_constants_detected"
        trim_confidence = TRIM_CONFIDENCE_NA
        length_full = str(len(sequence_full))
        length_core = str(len(sequence_core))
        alphabet = norm.alphabet_as_reported
        t_to_u = "true" if norm.t_to_u_applied else "false"

    if resolved_molecule == "unknown":
        if "molecule_type_unknown" not in qc_flags:
            qc_flags.append("molecule_type_unknown")
    else:
        qc_flags = [flag for flag in qc_flags if flag != "molecule_type_unknown"]

    canonical = dict(s1_record)
    canonical["sequence_raw"] = sequence_raw
    canonical["sequence_full"] = sequence_full
    canonical["sequence_core"] = sequence_core
    canonical["sequence_length_full"] = length_full
    canonical["sequence_length_core"] = length_core
    canonical["construct_scope"] = construct_scope
    canonical["trim_status"] = trim_status
    canonical["trim_confidence"] = trim_confidence
    canonical["detected_constant_5p"] = five_motifs
    canonical["detected_constant_3p"] = three_motifs
    canonical["molecule_type"] = resolved_molecule
    canonical["alphabet_as_reported"] = alphabet
    canonical["t_to_u_applied"] = t_to_u
    canonical["chemistry"] = molchem.chemistry
    canonical["qc_flags"] = format_qc_flags(qc_flags)
    # Live S2 schema forbids canonical experiment_group_id / family IDs.
    canonical["experiment_group_id"] = s1_record.get("experiment_group_id", "")
    canonical["near_duplicate_family_id"] = s1_record.get(
        "near_duplicate_family_id", ""
    )

    validated = validate_s2_record(canonical, s1_record=s1_record)
    detected_motif_names = QC_DELIMITER.join(
        sorted({motif.name for motif in norm.detected_motifs})
    )
    reported_length = source_metadata.get(policy.reported_length_field, "")
    length_matches = _length_matches_source(
        validated["sequence_length_full"], reported_length
    )
    source_promoter = source_has_promoter_or_template_concern(source_metadata)
    source_t7 = source_has_t7_concern(source_metadata)
    known_motif = bool(detected_motif_names)
    review_reasons = _initial_review_reasons(
        [part for part in validated["qc_flags"].split(QC_DELIMITER) if part],
        source_promoter=source_promoter,
        known_motif=known_motif,
        length_matches=length_matches,
    )
    qc = {
        "record_id": validated["record_id"],
        "native_id": validated["native_id"],
        "target_name_raw": validated["target_name_raw"],
        "alphabet_as_reported": validated["alphabet_as_reported"],
        "molecule_type": validated["molecule_type"],
        "chemistry": validated["chemistry"],
        "molecule_evidence_source": molchem.evidence_source,
        "t_to_u_applied": validated["t_to_u_applied"],
        "sequence_length_full": validated["sequence_length_full"],
        "sequence_length_core": validated["sequence_length_core"],
        "reported_length_raw": reported_length,
        "length_matches_source": length_matches,
        "detected_motifs": detected_motif_names,
        "construct_scope": validated["construct_scope"],
        "trim_status": validated["trim_status"],
        "trim_confidence": validated["trim_confidence"],
        "qc_flags": validated["qc_flags"],
        "experiment_group_id": source_metadata.get(
            policy.group_inference_sidecar_field, ""
        ),
        "sequence_corrected_applied": source_metadata.get(
            "sequence_corrected_applied", ""
        ),
        "sequence_quality_status": source_metadata.get("sequence_quality_status", ""),
        "automatic_concern_flags": source_metadata.get("automatic_concern_flags", ""),
        "source_promoter_or_template_concern": (
            "true" if source_promoter else "false"
        ),
        "source_t7_concern": "true" if source_t7 else "false",
        "group_consensus_proposal": "false",
        "known_motif_detected": "true" if known_motif else "false",
        "review_reasons": QC_DELIMITER.join(review_reasons),
    }
    return EnaS2RowResult(
        canonical=validated,
        qc=qc,
        transformations=tuple(norm.transformations),
        sidecar_experiment_group_id=source_metadata.get(
            policy.group_inference_sidecar_field, ""
        ),
        sidecar_experiment_group_ids=source_metadata.get(SUPPORTING_GROUP_FIELD, ""),
        sidecar_family_id=source_metadata.get("near_duplicate_family_id", ""),
    )


def is_review_candidate(qc: Mapping[str, str]) -> bool:
    """Return True when any ENA S2 review-relevant condition is present."""
    reasons = {part for part in (qc.get("review_reasons") or "").split(QC_DELIMITER) if part}
    if reasons:
        return True
    flags = {part for part in (qc.get("qc_flags") or "").split(QC_DELIMITER) if part}
    if flags & REVIEW_RELEVANT_FLAGS:
        return True
    if qc.get("source_promoter_or_template_concern") == "true":
        return True
    if qc.get("group_consensus_proposal") == "true":
        return True
    return False


def annotate_group_consensus_on_qc(
    rows: Sequence[EnaS2RowResult],
    *,
    group_ids_with_proposals: set[str],
    inference_key_by_record: Mapping[str, str | None],
) -> None:
    """Mark QC rows that participate in an unapplied group-consensus proposal."""
    for row in rows:
        record_id = row.canonical["record_id"]
        inference_key = inference_key_by_record.get(record_id)
        if inference_key and inference_key in group_ids_with_proposals:
            row.qc["group_consensus_proposal"] = "true"
            reasons = [
                part
                for part in row.qc.get("review_reasons", "").split(QC_DELIMITER)
                if part
            ]
            if REVIEW_REASON_GROUP_CONSENSUS not in reasons:
                reasons.append(REVIEW_REASON_GROUP_CONSENSUS)
            row.qc["review_reasons"] = QC_DELIMITER.join(sorted(set(reasons)))


def update_stats_from_row(stats: EnaS2Stats, row: EnaS2RowResult) -> None:
    """Accumulate aggregate counters from one normalised row."""
    canonical = row.canonical
    flags = [part for part in canonical["qc_flags"].split(QC_DELIMITER) if part]

    if canonical["sequence_length_full"] == "":
        stats.missing_sequence_rows += 1
    else:
        stats.nonempty_sequence_rows += 1

    for transformation in row.transformations:
        stats.transformation_counts[transformation] = (
            stats.transformation_counts.get(transformation, 0) + 1
        )

    alphabet = canonical["alphabet_as_reported"] or "missing"
    stats.alphabet_counts[alphabet] = stats.alphabet_counts.get(alphabet, 0) + 1

    molecule = canonical["molecule_type"] or "unknown"
    stats.molecule_type_counts[molecule] = (
        stats.molecule_type_counts.get(molecule, 0) + 1
    )
    chemistry = canonical["chemistry"] or "unknown"
    stats.chemistry_counts[chemistry] = stats.chemistry_counts.get(chemistry, 0) + 1

    if canonical["t_to_u_applied"] == "true":
        stats.t_to_u_count += 1
        stats.t_to_u_by_molecule[molecule] = (
            stats.t_to_u_by_molecule.get(molecule, 0) + 1
        )
    if "invalid_character" in flags:
        stats.invalid_character_count += 1
    if "alignment_gaps" in flags:
        stats.alignment_gaps_count += 1
    if "ambiguous_base" in flags:
        stats.ambiguous_base_count += 1
    if "mixed_t_u" in flags:
        stats.mixed_t_u_count += 1
    if row.qc.get("detected_motifs"):
        stats.known_motif_detection_count += 1
    if (
        "trim_requires_review" in flags
        or canonical["trim_status"] == "constants_suspected_unresolved"
    ):
        stats.trim_review_count += 1
    if "core_below_min_length" in flags:
        stats.core_below_min_count += 1
    if "core_above_max_length" in flags:
        stats.core_above_max_count += 1
    if flags:
        stats.rows_with_any_qc_flag += 1
    if len(flags) > 1:
        stats.rows_with_multiple_qc_flags += 1

    for flag in flags:
        stats.qc_flag_counts[flag] = stats.qc_flag_counts.get(flag, 0) + 1

    scope = canonical["construct_scope"] or "(empty)"
    stats.construct_scope_counts[scope] = (
        stats.construct_scope_counts.get(scope, 0) + 1
    )
    trim_status = canonical["trim_status"] or "(empty)"
    stats.trim_status_counts[trim_status] = (
        stats.trim_status_counts.get(trim_status, 0) + 1
    )
    trim_conf = canonical["trim_confidence"] or "(empty)"
    stats.trim_confidence_counts[trim_conf] = (
        stats.trim_confidence_counts.get(trim_conf, 0) + 1
    )

    full_len = (
        int(canonical["sequence_length_full"])
        if canonical["sequence_length_full"]
        else None
    )
    core_len = (
        int(canonical["sequence_length_core"])
        if canonical["sequence_length_core"]
        else None
    )
    full_bucket = length_bucket(full_len)
    core_bucket = length_bucket(core_len)
    stats.length_full_buckets[full_bucket] = (
        stats.length_full_buckets.get(full_bucket, 0) + 1
    )
    stats.length_core_buckets[core_bucket] = (
        stats.length_core_buckets.get(core_bucket, 0) + 1
    )
    if full_len is not None:
        stats.length_full_values.append(full_len)
    if core_len is not None:
        stats.length_core_values.append(core_len)

    if canonical["sequence_full"] != canonical["sequence_core"]:
        stats.core_differs_from_full += 1
    if row.qc.get("length_matches_source") == "false":
        stats.length_mismatch_count += 1
    if row.qc.get("source_promoter_or_template_concern") == "true":
        stats.source_promoter_or_template_count += 1
    if row.qc.get("source_t7_concern") == "true":
        stats.source_t7_concern_count += 1
    known = row.qc.get("known_motif_detected") == "true"
    source_promoter = row.qc.get("source_promoter_or_template_concern") == "true"
    if known and source_promoter:
        stats.overlap_source_and_shared_motif_count += 1
    elif source_promoter and not known:
        stats.source_concern_without_shared_motif_count += 1
    elif known and not source_promoter:
        stats.shared_motif_without_source_concern_count += 1
    if row.qc.get("sequence_corrected_applied") == "1":
        stats.sequence_corrections_applied += 1


def finalise_review_and_duplicate_stats(
    stats: EnaS2Stats,
    rows: Sequence[EnaS2RowResult],
) -> None:
    """Recompute review-candidate and duplicate diagnostics after annotation."""
    stats.review_candidate_rows = 0
    stats.review_reason_counts = {}
    full_values = [row.canonical["sequence_full"] for row in rows]
    core_values = [row.canonical["sequence_core"] for row in rows]
    full_counts = Counter(full_values)
    core_counts = Counter(core_values)
    stats.exact_duplicate_sequence_full_values = sum(
        1 for count in full_counts.values() if count > 1
    )
    stats.records_in_exact_duplicate_sequence_full = sum(
        count for count in full_counts.values() if count > 1
    )
    stats.exact_duplicate_sequence_core_values = sum(
        1 for count in core_counts.values() if count > 1
    )
    stats.records_in_exact_duplicate_sequence_core = sum(
        count for count in core_counts.values() if count > 1
    )
    for row in rows:
        if is_review_candidate(row.qc):
            stats.review_candidate_rows += 1
        for reason in row.qc.get("review_reasons", "").split(QC_DELIMITER):
            if reason:
                stats.review_reason_counts[reason] = (
                    stats.review_reason_counts.get(reason, 0) + 1
                )


def assert_genuine_proposals(proposals: Sequence[Mapping[str, str]]) -> None:
    """Reject motif-length-zero or otherwise non-scientific proposal rows."""
    for row in proposals:
        side = row.get("side", "")
        if side not in {"five_prime", "three_prime"}:
            raise EnaS2Error(f"proposal side must be five_prime/three_prime: {side}")
        if row.get("applied") != "false":
            raise EnaS2Error("ENA proposals must have applied=false")
        motif = (row.get("proposed_sequence") or "").strip()
        motif_id = (row.get("motif_id") or "").strip()
        if not motif and not motif_id:
            raise EnaS2Error("proposal must have motif sequence or motif_id")
        try:
            length = int(row.get("motif_length") or "0")
        except ValueError as exc:
            raise EnaS2Error("motif_length must be an integer") from exc
        if length <= 0:
            raise EnaS2Error("proposal motif_length must be > 0")
        source = row.get("proposal_source", "")
        if source == "group_consensus":
            if row.get("confidence") != "medium":
                raise EnaS2Error("Tier-2 proposals must use confidence=medium")
            if length < 12:
                raise EnaS2Error("Tier-2 motif_length must be >= 12")
            support = float(row.get("support") or 0.0)
            if support < 0.80:
                raise EnaS2Error("Tier-2 support must be >= 0.80")
            considered = int(row.get("records_considered") or 0)
            if considered < 5:
                raise EnaS2Error("Tier-2 group_size must be >= 5")


def build_group_proposal_rows(
    proposals: Sequence[Any],
) -> list[dict[str, str]]:
    """Serialise qualifying group-consensus proposals (never applied)."""
    rows: list[dict[str, str]] = []
    for proposal in proposals:
        if not proposal.proposed_sequence or proposal.length <= 0:
            continue
        rows.append(
            {
                "proposal_id": (
                    f"{proposal.experiment_group_id}:{proposal.side}:group_consensus"
                ),
                "experiment_group_id": proposal.experiment_group_id,
                "proposal_source": "group_consensus",
                "side": proposal.side,
                "proposed_sequence": proposal.proposed_sequence,
                "motif_id": "",
                "motif_length": str(proposal.length),
                "support": f"{proposal.support:.6f}".rstrip("0").rstrip("."),
                "records_considered": str(proposal.records_considered),
                "records_matching_exactly": str(proposal.records_matching_exactly),
                "confidence": proposal.confidence,
                "status": proposal.status,
                "applied": "false",
                "reason_not_applied": "proposal_only_checkpoint1",
                "reason": proposal.reason,
            }
        )
    return rows


def build_known_motif_proposals(
    rows: Sequence[EnaS2RowResult],
) -> list[dict[str, str]]:
    """Build auditable known-motif proposals without applying trims."""
    from common.sequence_normalisation import detect_known_non_core_motifs

    proposals: list[dict[str, str]] = []
    for row in rows:
        sequence_full = row.canonical.get("sequence_full") or ""
        if not sequence_full:
            continue
        detected = detect_known_non_core_motifs(sequence_full)
        for motif in detected:
            side = motif.position
            if side not in {"five_prime", "three_prime"}:
                continue
            proposals.append(
                {
                    "proposal_id": (
                        f"{row.canonical['record_id']}:known_motif:{side}:{motif.name}"
                    ),
                    "experiment_group_id": row.canonical["record_id"],
                    "proposal_source": "known_motif",
                    "side": side,
                    "proposed_sequence": "",
                    "motif_id": motif.name,
                    "motif_length": str(motif.length),
                    "support": "",
                    "records_considered": "1",
                    "records_matching_exactly": "1",
                    "confidence": "configured_motif_library",
                    "status": "proposed_for_review",
                    "applied": "false",
                    "reason_not_applied": "detection_only_not_an_approved_trim",
                    "reason": f"known_motif:{motif.name}",
                }
            )
    proposals.sort(key=lambda item: item["proposal_id"])
    return proposals


def build_membership_rows(
    *,
    group_proposal_rows: Sequence[Mapping[str, str]],
    group_membership: Mapping[str, Sequence[str]],
) -> list[dict[str, str]]:
    """Record participating members of each unapplied group-consensus proposal."""
    rows: list[dict[str, str]] = []
    for proposal in group_proposal_rows:
        group_id = proposal["experiment_group_id"]
        members = sorted(set(group_membership.get(group_id, ())))
        for record_id in members:
            rows.append(
                {
                    "proposal_id": proposal["proposal_id"],
                    "experiment_group_id": group_id,
                    "record_id": record_id,
                    "proposal_source": "group_consensus",
                    "side": proposal["side"],
                }
            )
    rows.sort(key=lambda item: (item["proposal_id"], item["record_id"]))
    return rows

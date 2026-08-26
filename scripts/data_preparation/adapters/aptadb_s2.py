"""AptaDB S2 adapter: explicit chemistry mapping and shared normalisation.

Consumes S1 canonical rows plus the AptaDB source-metadata sidecar. Sequence
cleaning uses the shared normaliser only. Does not accept, reject or park
records. Does not apply newly inferred constant-region trims.
"""

from __future__ import annotations

import json
import statistics
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

S2_QC_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "target_name_raw",
    "source_aptamer_chemistry",
    "alphabet_as_reported",
    "molecule_type",
    "chemistry",
    "molecule_evidence_source",
    "t_to_u_applied",
    "sequence_length_full",
    "sequence_length_core",
    "reported_length_raw",
    "detected_motifs",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "qc_flags",
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

ALLOWED_GROUP_INFERENCE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "target_name_raw_plus_publication",
        "experiment_group_id",
        "experiment_group_then_target_publication",
    }
)


class AptaDBS2Error(ValueError):
    """Hard failure during AptaDB S2 normalisation."""


@dataclass(frozen=True)
class AptadbNormalisationPolicy:
    """Tracked AptaDB S2 source-normalisation policy."""

    source_key: str
    contract_version: str
    molecule_evidence_field: str
    reported_length_field: str
    apply_approved_trims: bool
    group_inference_key: str
    molecule_type_map: Mapping[str, str]
    chemistry_map: Mapping[str, str]
    do_not_infer_molecule_from_alphabet: bool


@dataclass(frozen=True)
class MoleculeChemistryResult:
    """Resolved molecule type and chemistry from AptaDB source metadata."""

    source_value: str
    molecule_type: str
    chemistry: str
    evidence_source: str
    qc_flags: tuple[str, ...]


@dataclass
class AptaDBS2RowResult:
    """Canonical S2 row plus QC sidecar payload for one record."""

    canonical: dict[str, str]
    qc: dict[str, str]
    transformations: tuple[str, ...] = ()


@dataclass
class AptaDBS2Stats:
    """Aggregate S2 counts (no sequences or row identifiers)."""

    s1_rows: int = 0
    source_metadata_rows: int = 0
    s2_rows: int = 0
    unique_record_ids: int = 0
    unique_native_ids: int = 0
    missing_sequence_rows: int = 0
    nonempty_sequence_rows: int = 0
    order_preserved: bool = False
    provenance_preserved: bool = False
    sequence_raw_unchanged: bool = False
    publication_unchanged: bool = False
    transformation_counts: dict[str, int] = field(default_factory=dict)
    alphabet_counts: dict[str, int] = field(default_factory=dict)
    molecule_type_counts: dict[str, int] = field(default_factory=dict)
    chemistry_counts: dict[str, int] = field(default_factory=dict)
    source_chemistry_counts: dict[str, int] = field(default_factory=dict)
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
    constant_region_proposals: int = 0
    proposal_source_counts: dict[str, int] = field(default_factory=dict)
    groups_considered: int = 0
    groups_meeting_min_size: int = 0
    five_prime_proposals: int = 0
    three_prime_proposals: int = 0
    records_with_medium_confidence_proposal: int = 0
    high_confidence_trims_applied: int = 0
    constant_region_reason: str = "proposals_only_not_applied"


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AptaDBS2Error(f"{name} must be a JSON object")
    return value


def _require_str_map(value: Any, name: str) -> dict[str, str]:
    data = _require_mapping(value, name)
    out: dict[str, str] = {}
    for key, mapped in data.items():
        if not isinstance(key, str) or not isinstance(mapped, str):
            raise AptaDBS2Error(f"{name} keys and values must be strings")
        out[key] = mapped
    return out


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise AptaDBS2Error(f"{name} must be a boolean")
    return value


def load_aptadb_policy(path: str | Path) -> AptadbNormalisationPolicy:
    """Load and validate the AptaDB source-normalisation policy JSON."""
    policy_path = Path(path)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AptaDBS2Error(f"cannot read AptaDB policy: {exc.strerror}") from exc
    except json.JSONDecodeError as exc:
        raise AptaDBS2Error(f"AptaDB policy JSON is invalid: {exc.msg}") from exc

    data = _require_mapping(payload, "policy")
    source_key = data.get("source_key")
    if source_key != "aptadb":
        raise AptaDBS2Error("policy source_key must be 'aptadb'")
    contract_version = data.get("contract_version")
    if not isinstance(contract_version, str) or not contract_version.strip():
        raise AptaDBS2Error("contract_version must be a non-empty string")
    grouping = data.get("group_inference_key")
    if not isinstance(grouping, str) or grouping.strip() not in ALLOWED_GROUP_INFERENCE_KEYS:
        raise AptaDBS2Error(
            "group_inference_key must be one of "
            f"{sorted(ALLOWED_GROUP_INFERENCE_KEYS)}"
        )
    if data.get("apply_approved_trims") is True:
        raise AptaDBS2Error(
            "AptaDB S2 must not apply approved trims in this milestone"
        )

    return AptadbNormalisationPolicy(
        source_key=source_key,
        contract_version=contract_version.strip(),
        molecule_evidence_field=str(data.get("molecule_evidence_field", "")),
        reported_length_field=str(data.get("reported_length_field", "")),
        apply_approved_trims=_require_bool(
            data.get("apply_approved_trims"), "apply_approved_trims"
        ),
        group_inference_key=grouping.strip(),
        molecule_type_map=_require_str_map(
            data.get("molecule_type_map"), "molecule_type_map"
        ),
        chemistry_map=_require_str_map(data.get("chemistry_map"), "chemistry_map"),
        do_not_infer_molecule_from_alphabet=_require_bool(
            data.get("do_not_infer_molecule_from_alphabet", True),
            "do_not_infer_molecule_from_alphabet",
        ),
    )


def resolve_aptadb_molecule_and_chemistry(
    source_metadata: Mapping[str, str],
    policy: AptadbNormalisationPolicy,
) -> MoleculeChemistryResult:
    """Map AptaDB ``Aptamer Chemistry`` to molecule_type and chemistry.

    The source field is authoritative. Unexpected or blank values are hard
    failures; molecule type is never inferred from alphabet.
    """
    field_name = policy.molecule_evidence_field
    raw = source_metadata.get(field_name, "")
    source_value = "" if raw is None else str(raw).strip()

    if source_value not in policy.molecule_type_map:
        raise AptaDBS2Error(
            "Unexpected or blank AptaDB Aptamer Chemistry value: "
            f"{source_value!r}"
        )
    if source_value not in policy.chemistry_map:
        raise AptaDBS2Error(
            f"Unexpected AptaDB chemistry source value: {source_value!r}"
        )

    molecule = policy.molecule_type_map[source_value]
    chemistry = policy.chemistry_map[source_value]
    return MoleculeChemistryResult(
        source_value=source_value,
        molecule_type=molecule,
        chemistry=chemistry,
        evidence_source="aptamer_chemistry",
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
    """Spec-aligned length buckets for the AptaDB S2 report."""
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


def normalise_aptadb_record(
    s1_record: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: AptadbNormalisationPolicy,
    rules: SequenceNormalisationRules | None = None,
) -> AptaDBS2RowResult:
    """Normalise one AptaDB S1 record into S2 canonical + QC rows."""
    active_rules = rules if rules is not None else load_normalisation_rules()
    if s1_record["record_id"] != source_metadata.get("record_id", ""):
        raise AptaDBS2Error("canonical and sidecar record_id values must match")

    sequence_raw = s1_record["sequence_raw"]
    molchem = resolve_aptadb_molecule_and_chemistry(source_metadata, policy)
    qc_flags: list[str] = list(molchem.qc_flags)

    norm = normalise_sequence(
        sequence_raw,
        molecule_type=molchem.molecule_type,
        trim_plan=None,
        rules=active_rules,
    )
    qc_flags.extend(norm.qc_flags)

    # Source Aptamer Chemistry is authoritative. Never infer from alphabet.
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

    validated = validate_s2_record(canonical, s1_record=s1_record)
    detected_motif_names = QC_DELIMITER.join(
        sorted({motif.name for motif in norm.detected_motifs})
    )
    qc = {
        "record_id": validated["record_id"],
        "native_id": validated["native_id"],
        "target_name_raw": validated["target_name_raw"],
        "source_aptamer_chemistry": molchem.source_value,
        "alphabet_as_reported": validated["alphabet_as_reported"],
        "molecule_type": validated["molecule_type"],
        "chemistry": validated["chemistry"],
        "molecule_evidence_source": molchem.evidence_source,
        "t_to_u_applied": validated["t_to_u_applied"],
        "sequence_length_full": validated["sequence_length_full"],
        "sequence_length_core": validated["sequence_length_core"],
        "reported_length_raw": source_metadata.get(policy.reported_length_field, ""),
        "detected_motifs": detected_motif_names,
        "construct_scope": validated["construct_scope"],
        "trim_status": validated["trim_status"],
        "trim_confidence": validated["trim_confidence"],
        "qc_flags": validated["qc_flags"],
    }
    return AptaDBS2RowResult(
        canonical=validated,
        qc=qc,
        transformations=tuple(norm.transformations),
    )


def is_review_candidate(qc_flags: str) -> bool:
    """Return True when any manual-review-relevant flag is present."""
    if not qc_flags:
        return False
    flags = {part for part in qc_flags.split(QC_DELIMITER) if part}
    return bool(flags & REVIEW_RELEVANT_FLAGS)


def update_stats_from_row(stats: AptaDBS2Stats, row: AptaDBS2RowResult) -> None:
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

    source_chem = row.qc.get("source_aptamer_chemistry", "") or "(blank)"
    stats.source_chemistry_counts[source_chem] = (
        stats.source_chemistry_counts.get(source_chem, 0) + 1
    )

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
    if is_review_candidate(canonical["qc_flags"]):
        stats.review_candidate_rows += 1

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


def assert_genuine_proposals(proposals: Sequence[Mapping[str, str]]) -> None:
    """Reject motif-length-zero or otherwise non-scientific proposal rows."""
    for row in proposals:
        side = row.get("side", "")
        if side not in {"five_prime", "three_prime"}:
            raise AptaDBS2Error(
                f"proposal side must be five_prime/three_prime: {side}"
            )
        if row.get("applied") != "false":
            raise AptaDBS2Error("AptaDB proposals must have applied=false")
        motif = (row.get("proposed_sequence") or "").strip()
        motif_id = (row.get("motif_id") or "").strip()
        if not motif and not motif_id:
            raise AptaDBS2Error("proposal must have motif sequence or motif_id")
        try:
            length = int(row.get("motif_length") or "0")
        except ValueError as exc:
            raise AptaDBS2Error("motif_length must be an integer") from exc
        if length <= 0:
            raise AptaDBS2Error("proposal motif_length must be > 0")
        source = row.get("proposal_source", "")
        if source == "group_consensus":
            if row.get("confidence") != "medium":
                raise AptaDBS2Error("Tier-2 proposals must use confidence=medium")
            if length < 12:
                raise AptaDBS2Error("Tier-2 motif_length must be >= 12")
            support = float(row.get("support") or 0.0)
            if support < 0.80:
                raise AptaDBS2Error("Tier-2 support must be >= 0.80")
            considered = int(row.get("records_considered") or 0)
            if considered < 5:
                raise AptaDBS2Error("Tier-2 group_size must be >= 5")


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
    rows: Sequence[AptaDBS2RowResult],
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

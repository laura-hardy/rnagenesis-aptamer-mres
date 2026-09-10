"""AptaDiff Dataset A/B S2 adapters: source-contract ssDNA normalisation.

Two distinct source identities share scientifically neutral S2 helpers.
They do not share a combined ``aptadiff`` output. Sequence cleaning uses
the shared normaliser only. Experimental molecule identity comes from the
reviewed source contract (ssDNA / DNA), never from sequence alphabet.
T→U is not applied. Constant-region inference and approved trims are
disabled: P6 sequences are already random-region-only.

Does not accept, reject, or park records. Does not interpret ``p6`` as
affinity or evidence. Does not canonicalise documented targets.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from adapters.aptadiff import APTADIFF_SOURCE_KEYS, SOURCE_PROFILES
from common.corpus_schema import (
    S2_FORBIDDEN_FIELDS,
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
GROUP_INFERENCE_DISABLED: Final[str] = "disabled"
CONSTRUCT_SCOPE_RANDOM_REGION_ONLY: Final[str] = "random_region_only"
TRIM_STATUS_NO_CONSTANTS: Final[str] = "no_constants_detected"
CONSTANT_INFERENCE_DISABLED_REASON: Final[str] = (
    "constant_region_inference_disabled_by_source_contract"
)

# Shared normaliser may flag T7-like prefixes. AptaDiff P6 values are already
# random-region-only; selected-sequence motifs are not residual primers.
MOTIF_INFERENCE_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "known_promoter_detected",
        "constants_suspected_unresolved",
    }
)

S2_QC_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "target_name_raw",
    "aptadiff_dataset",
    "aptadiff_documented_target",
    "aptadiff_p6",
    "alphabet_as_reported",
    "molecule_type",
    "chemistry",
    "molecule_evidence_source",
    "t_to_u_applied",
    "sequence_length_full",
    "sequence_length_core",
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
        "trim_requires_review",
        "core_below_min_length",
        "core_above_max_length",
    }
)


class AptaDiffS2Error(ValueError):
    """Hard failure during AptaDiff S2 normalisation."""


@dataclass(frozen=True)
class AptadiffNormalisationPolicy:
    """Tracked AptaDiff A or B S2 source-normalisation policy."""

    source_key: str
    contract_version: str
    molecule_type: str
    chemistry: str
    molecule_evidence_source: str
    do_not_infer_molecule_from_alphabet: bool
    construct_scope: str
    apply_approved_trims: bool
    approved_trims: tuple[str, ...]
    group_inference_key: str
    do_not_apply_inferred_trims: bool
    p6_field: str
    documented_target_field: str
    dataset_field: str


@dataclass(frozen=True)
class MoleculeChemistryResult:
    """Resolved molecule type and chemistry from the source contract."""

    source_value: str
    molecule_type: str
    chemistry: str
    evidence_source: str
    qc_flags: tuple[str, ...]


@dataclass
class AptaDiffS2RowResult:
    """Canonical S2 row plus QC sidecar payload for one record."""

    canonical: dict[str, str]
    qc: dict[str, str]
    transformations: tuple[str, ...] = ()


@dataclass
class AptaDiffS2Stats:
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
    notes_unchanged: bool = False
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
    core_differs_from_full: int = 0
    applied_trims: int = 0
    length_36_count: int = 0
    other_length_count: int = 0
    nonempty_affinity_fields: int = 0
    nonempty_evidence_fields: int = 0
    nonempty_canonical_target_fields: int = 0
    nonempty_p6_qc_rows: int = 0
    documented_target_counts: dict[str, int] = field(default_factory=dict)
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
    constant_region_reason: str = CONSTANT_INFERENCE_DISABLED_REASON
    known_motifs_scanned: tuple[str, ...] = ()


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AptaDiffS2Error(f"{name} must be a JSON object")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise AptaDiffS2Error(f"{name} must be a boolean")
    return value


def _require_nonempty_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AptaDiffS2Error(f"{name} must be a non-empty string")
    return value.strip()


def load_aptadiff_policy(path: str | Path) -> AptadiffNormalisationPolicy:
    """Load and validate one AptaDiff A or B source-normalisation policy."""
    policy_path = Path(path)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AptaDiffS2Error(
            f"cannot read AptaDiff policy: {exc.strerror}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise AptaDiffS2Error(
            f"AptaDiff policy JSON is invalid: {exc.msg}"
        ) from exc

    data = _require_mapping(payload, "policy")
    source_key = _require_nonempty_str(data.get("source_key"), "source_key")
    if source_key not in APTADIFF_SOURCE_KEYS:
        raise AptaDiffS2Error(
            f"policy source_key must be aptadiff_a or aptadiff_b; got {source_key!r}"
        )
    grouping = _require_nonempty_str(
        data.get("group_inference_key"), "group_inference_key"
    )
    if grouping != GROUP_INFERENCE_DISABLED:
        raise AptaDiffS2Error(
            "AptaDiff S2 group_inference_key must be 'disabled'; "
            "group-wise constant-region inference is not authorised"
        )
    if data.get("apply_approved_trims") is True:
        raise AptaDiffS2Error(
            "AptaDiff S2 must not apply approved trims"
        )
    approved = data.get("approved_trims", [])
    if approved not in ([], ()):
        if not isinstance(approved, list) or any(approved):
            raise AptaDiffS2Error("AptaDiff S2 approved_trims must be empty")
    molecule_type = _require_nonempty_str(data.get("molecule_type"), "molecule_type")
    chemistry = _require_nonempty_str(data.get("chemistry"), "chemistry")
    if molecule_type != "ssDNA" or chemistry != "DNA":
        raise AptaDiffS2Error(
            "AptaDiff S2 source contract requires molecule_type=ssDNA "
            "and chemistry=DNA"
        )
    construct_scope = _require_nonempty_str(
        data.get("construct_scope"), "construct_scope"
    )
    if construct_scope != CONSTRUCT_SCOPE_RANDOM_REGION_ONLY:
        raise AptaDiffS2Error(
            "AptaDiff S2 construct_scope must be random_region_only"
        )
    do_not_infer = _require_bool(
        data.get("do_not_infer_molecule_from_alphabet", True),
        "do_not_infer_molecule_from_alphabet",
    )
    if not do_not_infer:
        raise AptaDiffS2Error(
            "AptaDiff S2 must not infer molecule identity from alphabet"
        )
    do_not_apply_inferred = _require_bool(
        data.get("do_not_apply_inferred_trims", True),
        "do_not_apply_inferred_trims",
    )
    if not do_not_apply_inferred:
        raise AptaDiffS2Error(
            "AptaDiff S2 must not apply inferred constant-region trims"
        )

    return AptadiffNormalisationPolicy(
        source_key=source_key,
        contract_version=_require_nonempty_str(
            data.get("contract_version"), "contract_version"
        ),
        molecule_type=molecule_type,
        chemistry=chemistry,
        molecule_evidence_source=_require_nonempty_str(
            data.get("molecule_evidence_source"), "molecule_evidence_source"
        ),
        do_not_infer_molecule_from_alphabet=do_not_infer,
        construct_scope=construct_scope,
        apply_approved_trims=_require_bool(
            data.get("apply_approved_trims"), "apply_approved_trims"
        ),
        approved_trims=(),
        group_inference_key=grouping,
        do_not_apply_inferred_trims=do_not_apply_inferred,
        p6_field=_require_nonempty_str(data.get("p6_field"), "p6_field"),
        documented_target_field=_require_nonempty_str(
            data.get("documented_target_field"), "documented_target_field"
        ),
        dataset_field=_require_nonempty_str(
            data.get("dataset_field"), "dataset_field"
        ),
    )


def resolve_aptadiff_molecule_and_chemistry(
    policy: AptadiffNormalisationPolicy,
) -> MoleculeChemistryResult:
    """Return the fixed experimental ssDNA contract.

    Molecule identity is not inferred from sequence alphabet.
    """
    return MoleculeChemistryResult(
        source_value="source_contract",
        molecule_type=policy.molecule_type,
        chemistry=policy.chemistry,
        evidence_source=policy.molecule_evidence_source,
        qc_flags=(),
    )


def _strip_motif_inference_flags(flags: Sequence[str]) -> list[str]:
    """Drop motif/primer-inference flags disabled by the source contract."""
    return [flag for flag in flags if flag not in MOTIF_INFERENCE_FLAGS]


def length_bucket(length: int | None) -> str:
    """Spec-aligned length buckets for the AptaDiff S2 report."""
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


def empty_constant_proposals() -> list[dict[str, str]]:
    """Return the header-only constant-region proposal table (no rows)."""
    return []


def s4_fields_are_empty(row: Mapping[str, str]) -> bool:
    """Return True when deferred global-S4 fields remain empty."""
    return all(not row.get(field) for field in S2_FORBIDDEN_FIELDS)


def normalise_aptadiff_record(
    s1_record: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: AptadiffNormalisationPolicy,
    rules: SequenceNormalisationRules | None = None,
) -> AptaDiffS2RowResult:
    """Normalise one AptaDiff S1 record into S2 canonical + QC rows."""
    active_rules = rules if rules is not None else load_normalisation_rules()
    if s1_record["record_id"] != source_metadata.get("record_id", ""):
        raise AptaDiffS2Error("canonical and sidecar record_id values must match")
    expected_source = policy.source_key
    if s1_record["source_db"] != expected_source:
        raise AptaDiffS2Error(
            f"source_db must be {expected_source}; got {s1_record['source_db']!r}"
        )

    sequence_raw = s1_record["sequence_raw"]
    molchem = resolve_aptadiff_molecule_and_chemistry(policy)
    qc_flags: list[str] = list(molchem.qc_flags)

    # p6 and documented targets are sidecar provenance only.
    p6_value = source_metadata.get(policy.p6_field, "")
    documented_target = source_metadata.get(policy.documented_target_field, "")
    dataset_label = source_metadata.get(policy.dataset_field, "")

    norm = normalise_sequence(
        sequence_raw,
        molecule_type=molchem.molecule_type,
        trim_plan=None,
        rules=active_rules,
    )
    qc_flags.extend(norm.qc_flags)
    qc_flags = _strip_motif_inference_flags(qc_flags)

    resolved_molecule = molchem.molecule_type
    sequence_full = norm.sequence_full or ""
    sequence_core = sequence_full

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
    else:
        construct_scope = policy.construct_scope
        trim_status = TRIM_STATUS_NO_CONSTANTS
        trim_confidence = TRIM_CONFIDENCE_NA
        sequence_core = sequence_full
        length_full = str(len(sequence_full))
        length_core = str(len(sequence_core))
        alphabet = norm.alphabet_as_reported
        t_to_u = "true" if norm.t_to_u_applied else "false"

    if resolved_molecule == "unknown":
        if "molecule_type_unknown" not in qc_flags:
            qc_flags.append("molecule_type_unknown")
    else:
        qc_flags = [flag for flag in qc_flags if flag != "molecule_type_unknown"]

    if t_to_u == "true":
        raise AptaDiffS2Error(
            "AptaDiff S2 must not apply T→U; experimental molecule is ssDNA"
        )
    if sequence_core != sequence_full:
        raise AptaDiffS2Error(
            "AptaDiff S2 requires sequence_core == sequence_full "
            "(random_region_only; no trim)"
        )

    canonical = dict(s1_record)
    canonical["sequence_raw"] = sequence_raw
    canonical["sequence_full"] = sequence_full
    canonical["sequence_core"] = sequence_core
    canonical["sequence_length_full"] = length_full
    canonical["sequence_length_core"] = length_core
    canonical["construct_scope"] = construct_scope
    canonical["trim_status"] = trim_status
    canonical["trim_confidence"] = trim_confidence
    canonical["detected_constant_5p"] = ""
    canonical["detected_constant_3p"] = ""
    canonical["molecule_type"] = resolved_molecule
    canonical["alphabet_as_reported"] = alphabet
    canonical["t_to_u_applied"] = t_to_u
    canonical["chemistry"] = molchem.chemistry
    canonical["qc_flags"] = format_qc_flags(qc_flags)

    validated = validate_s2_record(canonical, s1_record=s1_record)
    if not s4_fields_are_empty(validated):
        raise AptaDiffS2Error(
            "AptaDiff S2 must not populate target, evidence, affinity, "
            "or later-stage fields"
        )

    qc = {
        "record_id": validated["record_id"],
        "native_id": validated["native_id"],
        "target_name_raw": validated["target_name_raw"],
        "aptadiff_dataset": dataset_label,
        "aptadiff_documented_target": documented_target,
        "aptadiff_p6": p6_value,
        "alphabet_as_reported": validated["alphabet_as_reported"],
        "molecule_type": validated["molecule_type"],
        "chemistry": validated["chemistry"],
        "molecule_evidence_source": molchem.evidence_source,
        "t_to_u_applied": validated["t_to_u_applied"],
        "sequence_length_full": validated["sequence_length_full"],
        "sequence_length_core": validated["sequence_length_core"],
        "construct_scope": validated["construct_scope"],
        "trim_status": validated["trim_status"],
        "trim_confidence": validated["trim_confidence"],
        "qc_flags": validated["qc_flags"],
    }
    return AptaDiffS2RowResult(
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


def update_stats_from_row(stats: AptaDiffS2Stats, row: AptaDiffS2RowResult) -> None:
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

    documented = row.qc.get("aptadiff_documented_target", "") or "(blank)"
    stats.documented_target_counts[documented] = (
        stats.documented_target_counts.get(documented, 0) + 1
    )
    if row.qc.get("aptadiff_p6", ""):
        stats.nonempty_p6_qc_rows += 1

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
        if full_len == 36:
            stats.length_36_count += 1
        else:
            stats.other_length_count += 1
    if core_len is not None:
        stats.length_core_values.append(core_len)

    if canonical["sequence_full"] != canonical["sequence_core"]:
        stats.core_differs_from_full += 1
    if not s4_fields_are_empty(canonical):
        stats.nonempty_canonical_target_fields += 1
        affinity_fields = (
            "affinity_value",
            "affinity_unit",
            "affinity_type",
            "binding_evidence_type",
            "binding_evidence_score",
        )
        if any(canonical.get(field) for field in affinity_fields):
            stats.nonempty_affinity_fields += 1
            stats.nonempty_evidence_fields += 1


def expected_documented_target(source_key: str) -> str:
    """Return the sidecar-only documented target for one AptaDiff source."""
    try:
        return SOURCE_PROFILES[source_key].documented_target
    except KeyError as exc:
        raise AptaDiffS2Error(
            f"Unknown AptaDiff source_key={source_key!r}"
        ) from exc

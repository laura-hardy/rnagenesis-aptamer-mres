"""RiboAptamer S2 adapter: fixed RNA contract and shared normalisation.

Consumes S1 canonical rows plus the RiboAptamer source-metadata sidecar.
Sequence cleaning uses the shared normaliser only. Does not accept, reject
or park records. Does not apply newly inferred constant-region trims.
Does not run group-wise constant-region inference.
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

ASCII_ELLIPSIS: Final[str] = "..."
UNICODE_ELLIPSIS: Final[str] = "\u2026"

REGRESSION_A_MAX_ENDING_FRACTION: Final[float] = 0.01
REGRESSION_B_MIN_MEDIAN: Final[int] = 20
REGRESSION_C_MAX_CONTAINING_ELLIPSIS: Final[int] = 1

S2_QC_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "target_name_raw",
    "source_type",
    "alphabet_as_reported",
    "molecule_type",
    "chemistry",
    "molecule_evidence_source",
    "t_to_u_applied",
    "sequence_length_full",
    "sequence_length_core",
    "reported_length_raw",
    "ellipsis_anywhere",
    "ends_in_period_or_ellipsis",
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
        "truncated_sequence",
    }
)

GROUP_INFERENCE_DISABLED: Final[str] = "disabled"


class RiboAptamerS2Error(ValueError):
    """Hard failure during RiboAptamer S2 normalisation."""


@dataclass(frozen=True)
class RiboaptamerNormalisationPolicy:
    """Tracked RiboAptamer S2 source-normalisation policy."""

    source_key: str
    contract_version: str
    molecule_type: str
    chemistry: str
    molecule_evidence_source: str
    source_type_field: str
    reported_length_field: str
    apply_approved_trims: bool
    group_inference_key: str
    do_not_use_source_type_as_molecule: bool
    do_not_infer_molecule_from_alphabet: bool


@dataclass(frozen=True)
class MoleculeChemistryResult:
    """Resolved molecule type and chemistry from the source contract."""

    source_value: str
    molecule_type: str
    chemistry: str
    evidence_source: str
    qc_flags: tuple[str, ...]


@dataclass(frozen=True)
class TruncationDiagnostic:
    """Display-normalised ellipsis / period truncation diagnostics."""

    ellipsis_anywhere: bool
    ends_in_period_or_ellipsis: bool
    qc_flags: tuple[str, ...]


@dataclass
class RiboAptamerS2RowResult:
    """Canonical S2 row plus QC sidecar payload for one record."""

    canonical: dict[str, str]
    qc: dict[str, str]
    transformations: tuple[str, ...] = ()
    display_clean: str = ""


@dataclass
class RiboAptamerS2Stats:
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
    source_type_counts: dict[str, int] = field(default_factory=dict)
    t_to_u_count: int = 0
    t_to_u_by_molecule: dict[str, int] = field(default_factory=dict)
    invalid_character_count: int = 0
    alignment_gaps_count: int = 0
    ambiguous_base_count: int = 0
    mixed_t_u_count: int = 0
    truncated_sequence_count: int = 0
    ending_period_or_ellipsis_count: int = 0
    containing_ellipsis_count: int = 0
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
    constant_region_reason: str = (
        "group-wise inference disabled for RiboAptamer in this run"
    )
    truncation_regression_a_pass: bool = False
    truncation_regression_b_pass: bool = False
    truncation_regression_c_pass: bool = False
    known_motifs_scanned: tuple[str, ...] = ()


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RiboAptamerS2Error(f"{name} must be a JSON object")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise RiboAptamerS2Error(f"{name} must be a boolean")
    return value


def _require_nonempty_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RiboAptamerS2Error(f"{name} must be a non-empty string")
    return value.strip()


def load_riboaptamer_policy(path: str | Path) -> RiboaptamerNormalisationPolicy:
    """Load and validate the RiboAptamer source-normalisation policy JSON."""
    policy_path = Path(path)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RiboAptamerS2Error(
            f"cannot read RiboAptamer policy: {exc.strerror}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RiboAptamerS2Error(
            f"RiboAptamer policy JSON is invalid: {exc.msg}"
        ) from exc

    data = _require_mapping(payload, "policy")
    source_key = data.get("source_key")
    if source_key != "riboaptamer":
        raise RiboAptamerS2Error("policy source_key must be 'riboaptamer'")
    grouping = _require_nonempty_str(
        data.get("group_inference_key"), "group_inference_key"
    )
    if grouping != GROUP_INFERENCE_DISABLED:
        raise RiboAptamerS2Error(
            "RiboAptamer S2 group_inference_key must be 'disabled'; "
            "group-wise constant-region inference is not authorised"
        )
    if data.get("apply_approved_trims") is True:
        raise RiboAptamerS2Error(
            "RiboAptamer S2 must not apply approved trims in this milestone"
        )
    molecule_type = _require_nonempty_str(data.get("molecule_type"), "molecule_type")
    chemistry = _require_nonempty_str(data.get("chemistry"), "chemistry")
    if molecule_type != "RNA" or chemistry != "RNA":
        raise RiboAptamerS2Error(
            "RiboAptamer S2 source contract requires molecule_type=RNA "
            "and chemistry=RNA"
        )
    do_not_use_type = _require_bool(
        data.get("do_not_use_source_type_as_molecule", True),
        "do_not_use_source_type_as_molecule",
    )
    if not do_not_use_type:
        raise RiboAptamerS2Error(
            "RiboAptamer source Type must not be used as molecule_type"
        )

    return RiboaptamerNormalisationPolicy(
        source_key=source_key,
        contract_version=_require_nonempty_str(
            data.get("contract_version"), "contract_version"
        ),
        molecule_type=molecule_type,
        chemistry=chemistry,
        molecule_evidence_source=_require_nonempty_str(
            data.get("molecule_evidence_source"), "molecule_evidence_source"
        ),
        source_type_field=str(data.get("source_type_field", "")),
        reported_length_field=str(data.get("reported_length_field", "")),
        apply_approved_trims=_require_bool(
            data.get("apply_approved_trims"), "apply_approved_trims"
        ),
        group_inference_key=grouping,
        do_not_use_source_type_as_molecule=do_not_use_type,
        do_not_infer_molecule_from_alphabet=_require_bool(
            data.get("do_not_infer_molecule_from_alphabet", True),
            "do_not_infer_molecule_from_alphabet",
        ),
    )


def resolve_riboaptamer_molecule_and_chemistry(
    policy: RiboaptamerNormalisationPolicy,
) -> MoleculeChemistryResult:
    """Return the fixed experimental RNA contract.

    Source ``Type`` is a target-class field and is never consulted.
    """
    return MoleculeChemistryResult(
        source_value="source_contract",
        molecule_type=policy.molecule_type,
        chemistry=policy.chemistry,
        evidence_source=policy.molecule_evidence_source,
        qc_flags=(),
    )


def display_contains_ellipsis(display: str) -> bool:
    """Return True when the display-normalised text contains an ellipsis."""
    if not display:
        return False
    return ASCII_ELLIPSIS in display or UNICODE_ELLIPSIS in display


def display_ends_in_period_or_ellipsis(display: str) -> bool:
    """Return True when the display-normalised text ends in ``.`` / ``...`` / ``…``."""
    if not display:
        return False
    return (
        display.endswith(".")
        or display.endswith(ASCII_ELLIPSIS)
        or display.endswith(UNICODE_ELLIPSIS)
    )


def diagnose_truncation(display: str | None) -> TruncationDiagnostic:
    """Flag ellipsis/truncation on the display-normalised sequence only."""
    text = display or ""
    contains = display_contains_ellipsis(text)
    ends = display_ends_in_period_or_ellipsis(text)
    flags: tuple[str, ...] = ("truncated_sequence",) if contains else ()
    return TruncationDiagnostic(
        ellipsis_anywhere=contains,
        ends_in_period_or_ellipsis=ends,
        qc_flags=flags,
    )


def truncation_regression_a_pass(*, n_records: int, ending_count: int) -> bool:
    """Regression A: fewer than 1% end in period or ellipsis."""
    if n_records <= 0:
        return False
    return (ending_count / n_records) < REGRESSION_A_MAX_ENDING_FRACTION


def truncation_regression_b_pass(median_full_length: float | None) -> bool:
    """Regression B: median normalised full length is greater than 20 nt."""
    if median_full_length is None:
        return False
    return median_full_length > REGRESSION_B_MIN_MEDIAN


def truncation_regression_c_pass(*, containing_count: int) -> bool:
    """Regression C: at most one sequence contains an ellipsis anywhere."""
    return containing_count <= REGRESSION_C_MAX_CONTAINING_ELLIPSIS


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
    """Spec-aligned length buckets for the RiboAptamer S2 report."""
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


def median_length(values: Sequence[int]) -> float | None:
    """Return the median of nonempty integer lengths."""
    if not values:
        return None
    return float(statistics.median(sorted(values)))


def normalise_riboaptamer_record(
    s1_record: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: RiboaptamerNormalisationPolicy,
    rules: SequenceNormalisationRules | None = None,
) -> RiboAptamerS2RowResult:
    """Normalise one RiboAptamer S1 record into S2 canonical + QC rows."""
    active_rules = rules if rules is not None else load_normalisation_rules()
    if s1_record["record_id"] != source_metadata.get("record_id", ""):
        raise RiboAptamerS2Error("canonical and sidecar record_id values must match")

    sequence_raw = s1_record["sequence_raw"]
    molchem = resolve_riboaptamer_molecule_and_chemistry(policy)
    qc_flags: list[str] = list(molchem.qc_flags)

    # Source Type is diagnostic metadata only; never molecule evidence.
    _ = source_metadata.get(policy.source_type_field, "")

    norm = normalise_sequence(
        sequence_raw,
        molecule_type=molchem.molecule_type,
        trim_plan=None,
        rules=active_rules,
    )
    qc_flags.extend(norm.qc_flags)

    truncation = diagnose_truncation(norm.sequence_display_clean)
    qc_flags.extend(truncation.qc_flags)

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
    source_type = source_metadata.get(policy.source_type_field, "")
    qc = {
        "record_id": validated["record_id"],
        "native_id": validated["native_id"],
        "target_name_raw": validated["target_name_raw"],
        "source_type": source_type,
        "alphabet_as_reported": validated["alphabet_as_reported"],
        "molecule_type": validated["molecule_type"],
        "chemistry": validated["chemistry"],
        "molecule_evidence_source": molchem.evidence_source,
        "t_to_u_applied": validated["t_to_u_applied"],
        "sequence_length_full": validated["sequence_length_full"],
        "sequence_length_core": validated["sequence_length_core"],
        "reported_length_raw": source_metadata.get(policy.reported_length_field, ""),
        "ellipsis_anywhere": "true" if truncation.ellipsis_anywhere else "false",
        "ends_in_period_or_ellipsis": (
            "true" if truncation.ends_in_period_or_ellipsis else "false"
        ),
        "detected_motifs": detected_motif_names,
        "construct_scope": validated["construct_scope"],
        "trim_status": validated["trim_status"],
        "trim_confidence": validated["trim_confidence"],
        "qc_flags": validated["qc_flags"],
    }
    return RiboAptamerS2RowResult(
        canonical=validated,
        qc=qc,
        transformations=tuple(norm.transformations),
        display_clean=norm.sequence_display_clean or "",
    )


def is_review_candidate(qc_flags: str) -> bool:
    """Return True when any manual-review-relevant flag is present."""
    if not qc_flags:
        return False
    flags = {part for part in qc_flags.split(QC_DELIMITER) if part}
    return bool(flags & REVIEW_RELEVANT_FLAGS)


def update_stats_from_row(stats: RiboAptamerS2Stats, row: RiboAptamerS2RowResult) -> None:
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

    source_type = row.qc.get("source_type", "") or "(blank)"
    stats.source_type_counts[source_type] = (
        stats.source_type_counts.get(source_type, 0) + 1
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
    if "truncated_sequence" in flags:
        stats.truncated_sequence_count += 1
    if row.qc.get("ellipsis_anywhere") == "true":
        stats.containing_ellipsis_count += 1
    if row.qc.get("ends_in_period_or_ellipsis") == "true":
        stats.ending_period_or_ellipsis_count += 1
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


def finalise_truncation_regressions(stats: RiboAptamerS2Stats) -> None:
    """Record PASS/FAIL for the three RiboAptamer truncation regressions."""
    stats.truncation_regression_a_pass = truncation_regression_a_pass(
        n_records=stats.s2_rows,
        ending_count=stats.ending_period_or_ellipsis_count,
    )
    stats.truncation_regression_b_pass = truncation_regression_b_pass(
        median_length(stats.length_full_values)
    )
    stats.truncation_regression_c_pass = truncation_regression_c_pass(
        containing_count=stats.containing_ellipsis_count
    )


def assert_truncation_regressions(stats: RiboAptamerS2Stats) -> None:
    """Hard-fail if a RiboAptamer truncation regression is violated."""
    finalise_truncation_regressions(stats)
    if not stats.truncation_regression_a_pass:
        raise RiboAptamerS2Error(
            "RiboAptamer truncation regression A failed: "
            f"{stats.ending_period_or_ellipsis_count}/{stats.s2_rows} "
            "display-normalised sequences end in '.' / '...' / '…' "
            f"(limit < {REGRESSION_A_MAX_ENDING_FRACTION:.0%})"
        )
    if not stats.truncation_regression_b_pass:
        med = median_length(stats.length_full_values)
        raise RiboAptamerS2Error(
            "RiboAptamer truncation regression B failed: "
            f"median sequence_length_full is {med}; must be > "
            f"{REGRESSION_B_MIN_MEDIAN}"
        )
    if not stats.truncation_regression_c_pass:
        raise RiboAptamerS2Error(
            "RiboAptamer truncation regression C failed: "
            f"{stats.containing_ellipsis_count}/{stats.s2_rows} "
            "display-normalised sequences contain '...' or '…' "
            f"(limit <= {REGRESSION_C_MAX_CONTAINING_ELLIPSIS})"
        )


def assert_genuine_proposals(proposals: Sequence[Mapping[str, str]]) -> None:
    """Reject motif-length-zero or otherwise non-scientific proposal rows."""
    for row in proposals:
        side = row.get("side", "")
        if side not in {"five_prime", "three_prime"}:
            raise RiboAptamerS2Error(
                f"proposal side must be five_prime/three_prime: {side}"
            )
        if row.get("applied") != "false":
            raise RiboAptamerS2Error("RiboAptamer proposals must have applied=false")
        if row.get("proposal_source") == "group_consensus":
            raise RiboAptamerS2Error(
                "RiboAptamer S2 must not emit group-consensus proposals"
            )
        motif = (row.get("proposed_sequence") or "").strip()
        motif_id = (row.get("motif_id") or "").strip()
        if not motif and not motif_id:
            raise RiboAptamerS2Error("proposal must have motif sequence or motif_id")
        try:
            length = int(row.get("motif_length") or "0")
        except ValueError as exc:
            raise RiboAptamerS2Error("motif_length must be an integer") from exc
        if length <= 0:
            raise RiboAptamerS2Error("proposal motif_length must be > 0")


def build_known_motif_proposals(
    rows: Sequence[RiboAptamerS2RowResult],
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

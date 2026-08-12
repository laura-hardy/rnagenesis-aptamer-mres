"""UTexas S2 adapter: molecule/chemistry mapping and shared normalisation.

Consumes S1 canonical rows plus the UTexas source-metadata sidecar. Sequence
cleaning uses the shared normaliser only. Does not accept, reject or park
records. Does not apply newly inferred constant-region trims without an
explicit approved UTexas trim rule.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from common.corpus_schema import (
    format_qc_flags,
    validate_s2_record,
)
from common.sequence_normalisation import (
    ALPHABET_MISSING,
    SequenceNormalisationRules,
    load_normalisation_rules,
    normalise_sequence,
)

QC_DELIMITER: Final[str] = "|"

S2_QC_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "aptamer_name",
    "target_name_raw",
    "source_nucleic_acid_type",
    "alphabet_as_reported",
    "molecule_type",
    "chemistry",
    "molecule_evidence_source",
    "t_to_u_applied",
    "sequence_length_full",
    "sequence_length_core",
    "reported_length_raw",
    "pool_type_present",
    "pool_random_region_raw",
    "post_selex_modifications_present",
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
        "ambiguous_base",
        "mixed_t_u",
        "molecule_type_unknown",
        "molecule_type_requires_review",
        "chemistry_not_in_canonical_vocab",
        "t_in_reported_rna",
        "u_in_reported_dna",
        "known_promoter_detected",
        "trim_requires_review",
        "core_below_min_length",
        "core_above_max_length",
        "constants_suspected_unresolved",
        "pool_type_constants_proposed",
    }
)

# Strict single-random-region pool-type pattern only. Does not guess multi-N
# or free-text library designs.
_POOL_TYPE_SIMPLE_RE: Final[re.Pattern[str]] = re.compile(
    r"""
    ^\s*
    (?:5[\s]*[′'’`´ʹ΄]?\s*[-–—‐−:]?\s*)?
    (?P<five>[ACGTU]+)
    \s*[-–—‐−]\s*
    N\s*(?P<nlen>\d+)
    \s*[-–—‐−]\s*
    (?P<three>[ACGTU]+)
    (?:\s*[-–—‐−:]?\s*3[\s]*[′'’`´ʹ΄]?)?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

_TEXTUAL_NULLS: Final[frozenset[str]] = frozenset(
    {"", "NA", "N/A", "NULL", "NONE", "-", "NOT REPORTED"}
)


class UTexasS2Error(ValueError):
    """Hard failure during UTexas S2 normalisation."""


@dataclass(frozen=True)
class UtexasNormalisationPolicy:
    """Tracked UTexas S2 source-normalisation policy."""

    source_key: str
    contract_version: str
    molecule_evidence_field: str
    chemistry_evidence_field: str
    post_selex_field: str
    pool_type_field: str
    pool_random_region_field: str
    reported_length_field: str
    apply_approved_trims: bool
    approved_trim_rules: tuple[str, ...]
    parse_pool_type_for_proposals: bool
    group_inference_by_pool_type: bool
    molecule_type_map: Mapping[str, str]
    chemistry_map: Mapping[str, str]
    chemistry_not_in_canonical_vocab_sources: frozenset[str]
    molecule_type_requires_review_sources: frozenset[str]
    t_only_without_explicit_molecule_evidence: str
    do_not_infer_molecule_from_t_alphabet: bool
    do_not_infer_fana_from_alphabet: bool


@dataclass(frozen=True)
class MoleculeChemistryResult:
    """Resolved molecule type and chemistry from UTexas source metadata."""

    source_value: str
    molecule_type: str
    chemistry: str
    evidence_source: str
    qc_flags: tuple[str, ...]


@dataclass(frozen=True)
class PoolTypeParseResult:
    """Deterministic parse of a simple Pool Type construct string."""

    group_id: str
    five_prime: str
    three_prime: str
    documented_n_length: int
    parseable: bool


@dataclass
class UTexasS2RowResult:
    """Canonical S2 row plus QC sidecar payload for one record."""

    canonical: dict[str, str]
    qc: dict[str, str]
    transformations: tuple[str, ...] = ()
    pool_parse: PoolTypeParseResult | None = None


@dataclass
class UTexasS2Stats:
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
    transformation_counts: dict[str, int] = field(default_factory=dict)
    alphabet_counts: dict[str, int] = field(default_factory=dict)
    molecule_type_counts: dict[str, int] = field(default_factory=dict)
    chemistry_counts: dict[str, int] = field(default_factory=dict)
    source_nucleic_acid_type_counts: dict[str, int] = field(default_factory=dict)
    t_to_u_count: int = 0
    invalid_character_count: int = 0
    ambiguous_base_count: int = 0
    mixed_t_u_count: int = 0
    known_motif_detection_count: int = 0
    trim_review_count: int = 0
    core_below_min_count: int = 0
    core_above_max_count: int = 0
    rows_with_any_qc_flag: int = 0
    rows_with_multiple_qc_flags: int = 0
    review_candidate_rows: int = 0
    bracketed_three_prime_stripped: int = 0
    bracketed_five_prime_stripped: int = 0
    core_differs_from_full: int = 0
    applied_trims: int = 0
    construct_scope_counts: dict[str, int] = field(default_factory=dict)
    trim_status_counts: dict[str, int] = field(default_factory=dict)
    trim_confidence_counts: dict[str, int] = field(default_factory=dict)
    length_full_buckets: dict[str, int] = field(default_factory=dict)
    length_core_buckets: dict[str, int] = field(default_factory=dict)
    qc_flag_counts: dict[str, int] = field(default_factory=dict)
    constant_region_proposals: int = 0
    proposal_source_counts: dict[str, int] = field(default_factory=dict)
    pool_type_parseable_groups: int = 0
    constant_region_reason: str = (
        "proposals_only_no_approved_utexas_trim_rules"
    )


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise UTexasS2Error(f"{name} must be a JSON object")
    return value


def _require_str_list(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise UTexasS2Error(f"{name} must be a list of strings")
    return tuple(value)


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise UTexasS2Error(f"{name} must be a boolean")
    return value


def _require_str_map(value: Any, name: str) -> dict[str, str]:
    data = _require_mapping(value, name)
    out: dict[str, str] = {}
    for key, mapped in data.items():
        if not isinstance(key, str) or not isinstance(mapped, str):
            raise UTexasS2Error(f"{name} keys and values must be strings")
        out[key] = mapped
    return out


def load_utexas_policy(path: str | Path) -> UtexasNormalisationPolicy:
    """Load and validate the UTexas source-normalisation policy JSON."""
    policy_path = Path(path)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise UTexasS2Error(f"cannot read UTexas policy: {exc.strerror}") from exc
    except json.JSONDecodeError as exc:
        raise UTexasS2Error(f"UTexas policy JSON is invalid: {exc.msg}") from exc

    data = _require_mapping(payload, "policy")
    source_key = data.get("source_key")
    if source_key != "utexas":
        raise UTexasS2Error("policy source_key must be 'utexas'")
    contract_version = data.get("contract_version")
    if not isinstance(contract_version, str) or not contract_version.strip():
        raise UTexasS2Error("contract_version must be a non-empty string")

    return UtexasNormalisationPolicy(
        source_key=source_key,
        contract_version=contract_version.strip(),
        molecule_evidence_field=str(data.get("molecule_evidence_field", "")),
        chemistry_evidence_field=str(data.get("chemistry_evidence_field", "")),
        post_selex_field=str(data.get("post_selex_field", "")),
        pool_type_field=str(data.get("pool_type_field", "")),
        pool_random_region_field=str(data.get("pool_random_region_field", "")),
        reported_length_field=str(data.get("reported_length_field", "")),
        apply_approved_trims=_require_bool(
            data.get("apply_approved_trims"), "apply_approved_trims"
        ),
        approved_trim_rules=_require_str_list(
            data.get("approved_trim_rules", []), "approved_trim_rules"
        ),
        parse_pool_type_for_proposals=_require_bool(
            data.get("parse_pool_type_for_proposals"),
            "parse_pool_type_for_proposals",
        ),
        group_inference_by_pool_type=_require_bool(
            data.get("group_inference_by_pool_type"),
            "group_inference_by_pool_type",
        ),
        molecule_type_map=_require_str_map(
            data.get("molecule_type_map"), "molecule_type_map"
        ),
        chemistry_map=_require_str_map(data.get("chemistry_map"), "chemistry_map"),
        chemistry_not_in_canonical_vocab_sources=frozenset(
            _require_str_list(
                data.get("chemistry_not_in_canonical_vocab_sources", []),
                "chemistry_not_in_canonical_vocab_sources",
            )
        ),
        molecule_type_requires_review_sources=frozenset(
            _require_str_list(
                data.get("molecule_type_requires_review_sources", []),
                "molecule_type_requires_review_sources",
            )
        ),
        t_only_without_explicit_molecule_evidence=str(
            data.get("t_only_without_explicit_molecule_evidence", "unknown")
        ),
        do_not_infer_molecule_from_t_alphabet=_require_bool(
            data.get("do_not_infer_molecule_from_t_alphabet", True),
            "do_not_infer_molecule_from_t_alphabet",
        ),
        do_not_infer_fana_from_alphabet=_require_bool(
            data.get("do_not_infer_fana_from_alphabet", True),
            "do_not_infer_fana_from_alphabet",
        ),
    )


def resolve_utexas_molecule_and_chemistry(
    source_metadata: Mapping[str, str],
    policy: UtexasNormalisationPolicy,
) -> MoleculeChemistryResult:
    """Map UTexas ``Type of Nucleic Acid`` to molecule_type and chemistry."""
    field_name = policy.molecule_evidence_field
    raw = source_metadata.get(field_name, "")
    if raw is None:
        raw = ""
    source_value = str(raw)

    if source_value not in policy.molecule_type_map:
        raise UTexasS2Error(
            f"Unexpected UTexas Type of Nucleic Acid value: {source_value!r}"
        )
    if source_value not in policy.chemistry_map:
        raise UTexasS2Error(
            f"Unexpected UTexas chemistry source value: {source_value!r}"
        )

    molecule = policy.molecule_type_map[source_value]
    chemistry = policy.chemistry_map[source_value]
    flags: list[str] = []
    if molecule == "unknown":
        flags.append("molecule_type_unknown")
    if source_value in policy.molecule_type_requires_review_sources:
        flags.append("molecule_type_requires_review")
    if source_value in policy.chemistry_not_in_canonical_vocab_sources:
        flags.append("chemistry_not_in_canonical_vocab")

    evidence = "type_of_nucleic_acid" if source_value != "" else "blank_type"
    return MoleculeChemistryResult(
        source_value=source_value,
        molecule_type=molecule,
        chemistry=chemistry,
        evidence_source=evidence,
        qc_flags=tuple(sorted(set(flags))),
    )


def _pool_group_id(pool_type: str) -> str:
    digest = hashlib.sha256(pool_type.encode("utf-8")).hexdigest()[:12]
    return f"pool_type:{digest}"


def parse_pool_type_constants(pool_type: str) -> PoolTypeParseResult | None:
    """Parse a simple ``5'-FIXED-N##-FIXED-3'`` Pool Type into flanking motifs.

    Returns ``None`` when the value is blank, marked not reported, or not a
    single-N deterministic construct. Never guesses multi-N layouts.
    """
    text = (pool_type or "").strip()
    if not text or text.upper() in _TEXTUAL_NULLS:
        return None
    normalised = (
        text.replace("\u2010", "-")
        .replace("\u2212", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2032", "'")
    )
    match = _POOL_TYPE_SIMPLE_RE.fullmatch(normalised)
    if match is None:
        return None
    five = match.group("five").upper()
    three = match.group("three").upper()
    nlen = int(match.group("nlen"))
    if len(five) < 4 or len(three) < 4:
        return None
    return PoolTypeParseResult(
        group_id=_pool_group_id(text),
        five_prime=five,
        three_prime=three,
        documented_n_length=nlen,
        parseable=True,
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


def _length_bucket(length: int | None) -> str:
    if length is None:
        return "missing"
    if length < 20:
        return "<20"
    if length <= 100:
        return "20-100"
    if length <= 200:
        return "101-200"
    return ">200"


def normalise_utexas_record(
    s1_record: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: UtexasNormalisationPolicy,
    rules: SequenceNormalisationRules | None = None,
) -> UTexasS2RowResult:
    """Normalise one UTexas S1 record into S2 canonical + QC rows."""
    active_rules = rules if rules is not None else load_normalisation_rules()
    if s1_record["record_id"] != source_metadata.get("record_id", ""):
        raise UTexasS2Error("canonical and sidecar record_id values must match")

    sequence_raw = s1_record["sequence_raw"]
    molchem = resolve_utexas_molecule_and_chemistry(source_metadata, policy)
    qc_flags: list[str] = list(molchem.qc_flags)

    pool_raw = source_metadata.get(policy.pool_type_field, "")
    pool_parse = (
        parse_pool_type_constants(pool_raw)
        if policy.parse_pool_type_for_proposals
        else None
    )

    norm = normalise_sequence(
        sequence_raw,
        molecule_type=molchem.molecule_type,
        trim_plan=None,
        rules=active_rules,
    )
    qc_flags.extend(norm.qc_flags)

    # Source Type of Nucleic Acid is authoritative. Blank and FANA remain
    # unknown even when the shared normaliser would promote U-only alphabet
    # unknowns to RNA; T-only never establishes molecule type.
    resolved_molecule = molchem.molecule_type
    if (
        molchem.source_value == ""
        or molchem.source_value in policy.molecule_type_requires_review_sources
    ):
        resolved_molecule = "unknown"
        if "molecule_type_unknown" not in qc_flags:
            qc_flags.append("molecule_type_unknown")

    sequence_full = norm.sequence_full or ""
    if policy.apply_approved_trims and policy.approved_trim_rules:
        raise UTexasS2Error(
            "UTexas approved trim application is not implemented in this milestone"
        )
    sequence_core = sequence_full

    five_motifs, three_motifs = _motif_names_by_side(norm.detected_motifs)
    if pool_parse is not None:
        qc_flags.append("pool_type_constants_proposed")
        qc_flags.append("trim_requires_review")

    constants_suspected = bool(norm.detected_motifs) or pool_parse is not None
    if norm.sequence_full is None:
        construct_scope = "unknown"
        trim_status = "not_applicable"
        trim_confidence = ""
        if "missing_sequence" not in qc_flags:
            qc_flags.append("missing_sequence")
        sequence_full = ""
        sequence_core = ""
        length_full = ""
        length_core = ""
        alphabet = ALPHABET_MISSING
        t_to_u = "false"
    elif constants_suspected:
        construct_scope = "unknown"
        trim_status = "constants_suspected_unresolved"
        trim_confidence = ""
        qc_flags.append("constants_suspected_unresolved")
        qc_flags.append("trim_requires_review")
        length_full = str(len(sequence_full))
        length_core = str(len(sequence_core))
        alphabet = norm.alphabet_as_reported
        t_to_u = "true" if norm.t_to_u_applied else "false"
    else:
        construct_scope = "unknown"
        trim_status = "no_constants_detected"
        trim_confidence = ""
        length_full = str(len(sequence_full))
        length_core = str(len(sequence_core))
        alphabet = norm.alphabet_as_reported
        t_to_u = "true" if norm.t_to_u_applied else "false"

    if resolved_molecule == "unknown" and "molecule_type_unknown" not in qc_flags:
        qc_flags.append("molecule_type_unknown")

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
    post_selex = source_metadata.get(policy.post_selex_field, "")
    qc = {
        "record_id": validated["record_id"],
        "native_id": validated["native_id"],
        "aptamer_name": source_metadata.get("utexas_name_of_aptamer", ""),
        "target_name_raw": validated["target_name_raw"],
        "source_nucleic_acid_type": molchem.source_value,
        "alphabet_as_reported": validated["alphabet_as_reported"],
        "molecule_type": validated["molecule_type"],
        "chemistry": validated["chemistry"],
        "molecule_evidence_source": molchem.evidence_source,
        "t_to_u_applied": validated["t_to_u_applied"],
        "sequence_length_full": validated["sequence_length_full"],
        "sequence_length_core": validated["sequence_length_core"],
        "reported_length_raw": source_metadata.get(policy.reported_length_field, ""),
        "pool_type_present": "true" if (pool_raw or "").strip() else "false",
        "pool_random_region_raw": source_metadata.get(
            policy.pool_random_region_field, ""
        ),
        "post_selex_modifications_present": (
            "true" if (post_selex or "").strip() else "false"
        ),
        "detected_motifs": detected_motif_names,
        "construct_scope": validated["construct_scope"],
        "trim_status": validated["trim_status"],
        "trim_confidence": validated["trim_confidence"],
        "qc_flags": validated["qc_flags"],
    }
    return UTexasS2RowResult(
        canonical=validated,
        qc=qc,
        transformations=tuple(norm.transformations),
        pool_parse=pool_parse,
    )


def is_review_candidate(qc_flags: str) -> bool:
    """Return True when any manual-review-relevant flag is present."""
    if not qc_flags:
        return False
    flags = {part for part in qc_flags.split(QC_DELIMITER) if part}
    return bool(flags & REVIEW_RELEVANT_FLAGS)


def update_stats_from_row(stats: UTexasS2Stats, row: UTexasS2RowResult) -> None:
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
    if "remove_bracketed_three_prime_label" in row.transformations:
        stats.bracketed_three_prime_stripped += 1
    if "remove_bracketed_five_prime_label" in row.transformations:
        stats.bracketed_five_prime_stripped += 1

    alphabet = canonical["alphabet_as_reported"] or "missing"
    stats.alphabet_counts[alphabet] = stats.alphabet_counts.get(alphabet, 0) + 1

    molecule = canonical["molecule_type"] or "unknown"
    stats.molecule_type_counts[molecule] = (
        stats.molecule_type_counts.get(molecule, 0) + 1
    )
    chemistry = canonical["chemistry"] or "unknown"
    stats.chemistry_counts[chemistry] = stats.chemistry_counts.get(chemistry, 0) + 1

    source_type = row.qc.get("source_nucleic_acid_type", "")
    key = source_type if source_type != "" else "(blank)"
    stats.source_nucleic_acid_type_counts[key] = (
        stats.source_nucleic_acid_type_counts.get(key, 0) + 1
    )

    if canonical["t_to_u_applied"] == "true":
        stats.t_to_u_count += 1
    if "invalid_character" in flags:
        stats.invalid_character_count += 1
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
    full_bucket = _length_bucket(full_len)
    core_bucket = _length_bucket(core_len)
    stats.length_full_buckets[full_bucket] = (
        stats.length_full_buckets.get(full_bucket, 0) + 1
    )
    stats.length_core_buckets[core_bucket] = (
        stats.length_core_buckets.get(core_bucket, 0) + 1
    )

    if canonical["sequence_full"] != canonical["sequence_core"]:
        stats.core_differs_from_full += 1


def build_pool_type_proposals(
    rows: Sequence[UTexasS2RowResult],
) -> list[dict[str, str]]:
    """Build deterministic pool-type constant-region proposals (not applied)."""
    # Group by pool parse group_id; emit one proposal per side per group.
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        parsed = row.pool_parse
        if parsed is None:
            continue
        entry = groups.get(parsed.group_id)
        if entry is None:
            groups[parsed.group_id] = {
                "five": parsed.five_prime,
                "three": parsed.three_prime,
                "nlen": parsed.documented_n_length,
                "count": 1,
            }
        else:
            entry["count"] += 1

    proposals: list[dict[str, str]] = []
    for group_id in sorted(groups):
        entry = groups[group_id]
        count = int(entry["count"])
        for side, motif in (
            ("five_prime", entry["five"]),
            ("three_prime", entry["three"]),
        ):
            proposals.append(
                {
                    "proposal_id": f"{group_id}:{side}",
                    "experiment_group_id": group_id,
                    "proposal_source": "pool_type",
                    "side": side,
                    "proposed_sequence": motif,
                    "motif_length": str(len(motif)),
                    "support": "1.0",
                    "records_considered": str(count),
                    "records_matching_exactly": "",
                    "confidence": "source_documented",
                    "status": "proposed_for_review",
                    "applied": "false",
                    "reason_not_applied": "no_approved_utexas_trim_rule",
                    "reason": (
                        f"deterministic_pool_type_parse;documented_n={entry['nlen']}"
                    ),
                }
            )
    return proposals

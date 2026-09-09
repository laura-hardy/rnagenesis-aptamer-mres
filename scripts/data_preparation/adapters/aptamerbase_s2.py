"""AptamerBase S2 adapter: RDF typing, shared normalisation, known-motif QC.

Consumes frozen S1 canonical rows plus the source-metadata sidecar and a
supporting RDF type index. Sequence cleaning uses the shared normaliser only.
Does not accept, reject, park, deduplicate or trim records. Group-wise
constant-region inference is disabled. Target/evidence/PDB fields stay empty.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from adapters.aptamerbase_rdf import AptamerBaseRdfSubjectFacts
from common.corpus_schema import (
    format_qc_flags,
    validate_s2_record,
)
from common.sequence_normalisation import (
    ALPHABET_DNA_T,
    ALPHABET_MISSING,
    ALPHABET_RNA,
    TRIM_CONFIDENCE_NA,
    SequenceNormalisationRules,
    load_normalisation_rules,
    normalise_sequence,
)

QC_DELIMITER: Final[str] = "|"
GROUP_INFERENCE_DISABLED: Final[str] = "disabled"

APOSTROPHE_VARIANTS: Final[tuple[str, ...]] = ("\u2018", "\u2019", "\u02bc", "\u2032")

S2_QC_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "aptamerbase_id",
    "source_object_type",
    "target_name_raw",
    "alphabet_as_reported",
    "molecule_type",
    "chemistry",
    "chemistry_class",
    "molecule_evidence_source",
    "t_to_u_applied",
    "sequence_length_full",
    "sequence_length_core",
    "reported_length_raw",
    "length_matches_source",
    "observable_length_bucket",
    "rdf_has_rna",
    "rdf_has_dna",
    "rdf_has_modified_nucleic_acid",
    "rdf_has_minimal_aptamer_type",
    "has_minimal_aptamer_sidecar",
    "is_minimal_aptamer_of_sidecar",
    "modification_text_present",
    "detected_motifs",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "qc_flags",
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

REVIEW_RELEVANT_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "missing_sequence",
        "invalid_character",
        "alignment_gaps",
        "ambiguous_base",
        "mixed_t_u",
        "molecule_type_unknown",
        "source_molecule_type_conflict",
        "source_molecule_alphabet_conflict",
        "non_aptamer_structure_topic",
        "chemistry_requires_review",
        "spiegelmer_l_rna_review",
        "dna_twof_like_modification_review",
        "rdf_modified_type_without_modification_text",
        "modification_text_without_rdf_modified_type",
        "known_promoter_detected",
        "trim_requires_review",
        "core_below_min_length",
        "core_above_max_length",
        "constants_suspected_unresolved",
    }
)

REVIEW_REASON_LENGTH_MISMATCH: Final[str] = "source_length_mismatch"

AUTOMATIC_CHEMISTRY_CLASSES: Final[frozenset[str]] = frozenset(
    {"unmodified_backbone", "terminal_conjugate", "twof_rna"}
)


class AptamerBaseS2Error(ValueError):
    """Hard failure during AptamerBase S2 normalisation."""


@dataclass(frozen=True)
class AptamerBaseNormalisationPolicy:
    """Tracked AptamerBase S2 source-normalisation policy."""

    source_key: str
    contract_version: str
    s1_spine_basename: str
    supporting_rdf_basename: str
    molecule_evidence_source: str
    reported_length_field: str
    source_object_type_field: str
    source_id_field: str
    modification_text_field: str
    apply_approved_trims: bool
    group_inference_key: str
    do_not_infer_molecule_from_alphabet: bool
    do_not_apply_inferred_trims: bool
    do_not_create_experiment_group_id: bool
    approved_trims: tuple[str, ...]
    rdf_type_predicate: str
    freebase_type_predicate: str
    modification_details_predicate: str
    rdf_type_uris: dict[str, str]
    source_object_type_map: dict[str, str]
    structure_topic_object_types: frozenset[str]
    rdf_molecule_map: dict[str, str]
    chemistry_literals: dict[str, str]
    chemistry_class_by_canonical: dict[str, str]
    chemistry_automatic_map: dict[str, dict[str, str]]
    qc_tokens: dict[str, str]


@dataclass(frozen=True)
class MoleculeChemistryResult:
    """Resolved object class, molecule type and chemistry for one row."""

    source_object_type: str
    is_structure_topic: bool
    rdf_molecule_type: str
    molecule_type: str
    chemistry: str
    chemistry_class: str
    evidence_source: str
    rdf_has_rna: bool
    rdf_has_dna: bool
    qc_flags: tuple[str, ...]


@dataclass
class AptamerBaseS2RowResult:
    """Canonical S2 row plus QC sidecar payload for one record."""

    canonical: dict[str, str]
    qc: dict[str, str]
    transformations: tuple[str, ...] = ()
    aptamerbase_id: str = ""
    rdf_molecule_type: str = ""
    observable_length: int | None = None
    length_qc_emitted: bool = False


@dataclass
class AptamerBaseS2Stats:
    """Aggregate S2 counts (no sequences or row identifiers)."""

    s1_rows: int = 0
    source_metadata_rows: int = 0
    s2_rows: int = 0
    unique_record_ids: int = 0
    unique_native_ids: int = 0
    unique_freebase_ids: int = 0
    rdf_subjects_joined: int = 0
    rdf_join_coverage_ok: bool = False
    rdf_statement_count: int = 0
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
    molecule_type_unique_id_counts: dict[str, int] = field(default_factory=dict)
    chemistry_counts: dict[str, int] = field(default_factory=dict)
    chemistry_class_counts: dict[str, int] = field(default_factory=dict)
    source_object_type_counts: dict[str, int] = field(default_factory=dict)
    t_to_u_count: int = 0
    rna_t_alphabet_count: int = 0
    dna_u_conflict_count: int = 0
    dna_u_conflict_unique_ids: int = 0
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
    observable_length_without_core_qc: int = 0
    structure_topic_rows: int = 0
    structure_topic_nonempty_sequence: int = 0
    rdf_modified_with_text: int = 0
    rdf_modified_without_text: int = 0
    text_without_rdf_modified: int = 0
    terminal_conjugate_count: int = 0
    twof_rna_automatic_count: int = 0
    spiegelmer_count: int = 0
    chemistry_review_count: int = 0
    sidecar_has_minimal_aptamer_nonempty: int = 0
    sidecar_is_minimal_aptamer_of_nonempty: int = 0
    constant_region_proposals: int = 0
    proposal_source_counts: dict[str, int] = field(default_factory=dict)
    groups_considered: int = 0
    groups_meeting_min_size: int = 0
    five_prime_proposals: int = 0
    three_prime_proposals: int = 0
    records_with_medium_confidence_proposal: int = 0
    high_confidence_trims_applied: int = 0
    constant_region_reason: str = (
        "group-wise inference disabled for AptamerBase in this run; "
        "known_motif_detection_only_not_applied"
    )
    known_motifs_scanned: tuple[str, ...] = ()
    s4_fields_empty: bool = False


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AptamerBaseS2Error(f"{name} must be a JSON object")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise AptamerBaseS2Error(f"{name} must be a boolean")
    return value


def _require_nonempty_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AptamerBaseS2Error(f"{name} must be a non-empty string")
    return value.strip()


def canonicalize_modification_text(text: str) -> str:
    """Collapse whitespace and apostrophe variants for closed-list lookup."""
    if not text:
        return ""
    normalised = text
    for variant in APOSTROPHE_VARIANTS:
        normalised = normalised.replace(variant, "'")
    return " ".join(normalised.split()).casefold()


def load_aptamerbase_policy(path: str | Path) -> AptamerBaseNormalisationPolicy:
    """Load and validate the AptamerBase source-normalisation policy JSON."""
    policy_path = Path(path)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AptamerBaseS2Error(
            f"cannot read AptamerBase policy: {exc.strerror}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise AptamerBaseS2Error(
            f"AptamerBase policy JSON is invalid: {exc.msg}"
        ) from exc

    data = _require_mapping(payload, "policy")
    source_key = data.get("source_key")
    if source_key != "aptamerbase":
        raise AptamerBaseS2Error("policy source_key must be 'aptamerbase'")
    grouping = _require_nonempty_str(
        data.get("group_inference_key"), "group_inference_key"
    )
    if grouping != GROUP_INFERENCE_DISABLED:
        raise AptamerBaseS2Error(
            "AptamerBase S2 group_inference_key must be 'disabled'; "
            "group-wise constant-region inference is not authorised"
        )
    if data.get("apply_approved_trims") is True:
        raise AptamerBaseS2Error(
            "AptamerBase S2 must not apply approved trims in this milestone"
        )
    approved = data.get("approved_trims", [])
    if approved not in ([], None):
        if not isinstance(approved, list) or any(approved):
            raise AptamerBaseS2Error(
                "AptamerBase S2 approved_trims must be empty"
            )
    do_not_infer = _require_bool(
        data.get("do_not_infer_molecule_from_alphabet", True),
        "do_not_infer_molecule_from_alphabet",
    )
    if not do_not_infer:
        raise AptamerBaseS2Error(
            "AptamerBase molecule type must not be inferred from alphabet"
        )
    do_not_apply = _require_bool(
        data.get("do_not_apply_inferred_trims", True),
        "do_not_apply_inferred_trims",
    )
    if not do_not_apply:
        raise AptamerBaseS2Error(
            "AptamerBase S2 must not apply inferred constant-region trims"
        )
    do_not_group = _require_bool(
        data.get("do_not_create_experiment_group_id", True),
        "do_not_create_experiment_group_id",
    )
    if not do_not_group:
        raise AptamerBaseS2Error(
            "AptamerBase S2 must not create experiment_group_id"
        )

    predicates = _require_mapping(data.get("rdf_predicates"), "rdf_predicates")
    type_uris_raw = _require_mapping(data.get("rdf_type_uris"), "rdf_type_uris")
    type_uris = {
        _require_nonempty_str(key, "rdf_type_uris key"): _require_nonempty_str(
            value, f"rdf_type_uris.{key}"
        )
        for key, value in type_uris_raw.items()
    }
    required_type_keys = {
        "aptamer",
        "rna",
        "dna",
        "nucleic_acid",
        "linear_polymer",
        "modified_nucleic_acid",
        "minimal_aptamer",
        "nucleic_acid_secondary_structure",
        "predicted_secondary_structure",
    }
    missing_types = required_type_keys - set(type_uris)
    if missing_types:
        raise AptamerBaseS2Error(
            f"rdf_type_uris missing required keys: {sorted(missing_types)}"
        )

    object_map_raw = _require_mapping(
        data.get("source_object_type_map"), "source_object_type_map"
    )
    object_map = {
        _require_nonempty_str(key, "source_object_type_map key"): (
            _require_nonempty_str(value, f"source_object_type_map.{key}")
        )
        for key, value in object_map_raw.items()
    }
    structure_raw = data.get("structure_topic_object_types")
    if not isinstance(structure_raw, list) or not all(
        isinstance(item, str) and item.strip() for item in structure_raw
    ):
        raise AptamerBaseS2Error(
            "structure_topic_object_types must be a list of non-empty strings"
        )
    molecule_map = dict(
        _require_mapping(data.get("rdf_molecule_map"), "rdf_molecule_map")
    )
    literals_raw = _require_mapping(
        data.get("chemistry_literals"), "chemistry_literals"
    )
    chemistry_literals = {
        str(key): _require_nonempty_str(value, "chemistry_literals value")
        for key, value in literals_raw.items()
    }
    class_by_canonical: dict[str, str] = {}
    for literal, chem_class in chemistry_literals.items():
        canonical = canonicalize_modification_text(literal)
        existing = class_by_canonical.get(canonical)
        if existing is not None and existing != chem_class:
            raise AptamerBaseS2Error(
                "chemistry_literals canonicalise to conflicting classes"
            )
        class_by_canonical[canonical] = chem_class
    automatic_raw = _require_mapping(
        data.get("chemistry_automatic_map"), "chemistry_automatic_map"
    )
    automatic_map: dict[str, dict[str, str]] = {}
    for chem_class, mapping in automatic_raw.items():
        mapped = _require_mapping(mapping, f"chemistry_automatic_map.{chem_class}")
        automatic_map[str(chem_class)] = {
            _require_nonempty_str(key, "automatic map key"): _require_nonempty_str(
                value, "automatic map value"
            )
            for key, value in mapped.items()
        }
    qc_tokens_raw = _require_mapping(data.get("qc_tokens"), "qc_tokens")
    qc_tokens = {
        _require_nonempty_str(key, "qc_tokens key"): _require_nonempty_str(
            value, f"qc_tokens.{key}"
        )
        for key, value in qc_tokens_raw.items()
    }

    return AptamerBaseNormalisationPolicy(
        source_key=source_key,
        contract_version=_require_nonempty_str(
            data.get("contract_version"), "contract_version"
        ),
        s1_spine_basename=_require_nonempty_str(
            data.get("s1_spine_basename"), "s1_spine_basename"
        ),
        supporting_rdf_basename=_require_nonempty_str(
            data.get("supporting_rdf_basename"), "supporting_rdf_basename"
        ),
        molecule_evidence_source=_require_nonempty_str(
            data.get("molecule_evidence_source"), "molecule_evidence_source"
        ),
        reported_length_field=str(data.get("reported_length_field", "")),
        source_object_type_field=_require_nonempty_str(
            data.get("source_object_type_field"), "source_object_type_field"
        ),
        source_id_field=_require_nonempty_str(
            data.get("source_id_field"), "source_id_field"
        ),
        modification_text_field=_require_nonempty_str(
            data.get("modification_text_field"), "modification_text_field"
        ),
        apply_approved_trims=_require_bool(
            data.get("apply_approved_trims"), "apply_approved_trims"
        ),
        group_inference_key=grouping,
        do_not_infer_molecule_from_alphabet=do_not_infer,
        do_not_apply_inferred_trims=do_not_apply,
        do_not_create_experiment_group_id=do_not_group,
        approved_trims=(),
        rdf_type_predicate=_require_nonempty_str(
            predicates.get("rdf_type"), "rdf_predicates.rdf_type"
        ),
        freebase_type_predicate=_require_nonempty_str(
            predicates.get("freebase_object_type"),
            "rdf_predicates.freebase_object_type",
        ),
        modification_details_predicate=_require_nonempty_str(
            predicates.get("modification_details"),
            "rdf_predicates.modification_details",
        ),
        rdf_type_uris=type_uris,
        source_object_type_map=object_map,
        structure_topic_object_types=frozenset(item.strip() for item in structure_raw),
        rdf_molecule_map={str(key): str(value) for key, value in molecule_map.items()},
        chemistry_literals=chemistry_literals,
        chemistry_class_by_canonical=class_by_canonical,
        chemistry_automatic_map=automatic_map,
        qc_tokens=qc_tokens,
    )


def resolve_source_object_type(
    source_type_uri: str,
    policy: AptamerBaseNormalisationPolicy,
) -> str:
    """Map the S1 sidecar object-type URI to a local class name."""
    mapped = policy.source_object_type_map.get(source_type_uri)
    if mapped is None:
        raise AptamerBaseS2Error(
            "unrecognised AptamerBase source object type in S1 sidecar"
        )
    return mapped


def rdf_molecule_key(facts: AptamerBaseRdfSubjectFacts) -> str:
    """Return the RDF RNA/DNA combination key."""
    if facts.has_rna and facts.has_dna:
        return "rna_and_dna"
    if facts.has_rna:
        return "rna_only"
    if facts.has_dna:
        return "dna_only"
    return "neither"


def resolve_rdf_molecule_type(
    facts: AptamerBaseRdfSubjectFacts,
    policy: AptamerBaseNormalisationPolicy,
) -> tuple[str, tuple[str, ...]]:
    """Map RDF RNA/DNA types to canonical molecule_type before object override."""
    key = rdf_molecule_key(facts)
    mapped = policy.rdf_molecule_map.get(key)
    if mapped is None:
        raise AptamerBaseS2Error(f"rdf_molecule_map missing key {key!r}")
    flags: list[str] = []
    if key == "rna_and_dna":
        flags.append(policy.qc_tokens["molecule_type_conflict"])
    return mapped, tuple(flags)


def classify_modification(
    modification_text: str,
    policy: AptamerBaseNormalisationPolicy,
) -> tuple[str, tuple[str, ...]]:
    """Classify exact source modification literals via the closed allowlist."""
    extras: list[str] = []
    canonical = canonicalize_modification_text(modification_text)
    if not canonical:
        return "unmodified_backbone", ()
    lookup = policy.chemistry_class_by_canonical
    direct = lookup.get(canonical)
    if direct is not None:
        if direct == "terminal_conjugate":
            extras.append(policy.qc_tokens["terminal_conjugate"])
        return direct, tuple(extras)

    parts = [
        canonicalize_modification_text(part)
        for part in canonical.split(";")
        if canonicalize_modification_text(part)
    ]
    if len(parts) > 1:
        classes = [lookup.get(part) for part in parts]
        if all(item is not None for item in classes):
            unique = set(classes)
            if unique <= {"twof_rna", "terminal_conjugate"} and "twof_rna" in unique:
                extras.append(policy.qc_tokens["terminal_conjugate"])
                return "twof_rna", tuple(extras)
            if unique == {"terminal_conjugate"}:
                extras.append(policy.qc_tokens["terminal_conjugate"])
                return "terminal_conjugate", tuple(extras)
            if unique == {"unmodified_backbone"}:
                return "unmodified_backbone", ()
    return "unsupported", ()


def resolve_chemistry(
    *,
    source_object_type: str,
    molecule_type: str,
    modification_text: str,
    facts: AptamerBaseRdfSubjectFacts,
    policy: AptamerBaseNormalisationPolicy,
) -> tuple[str, str, tuple[str, ...]]:
    """Return canonical chemistry, class token, and chemistry QC flags."""
    flags: list[str] = []
    text_present = bool(modification_text.strip())
    if facts.has_modified_nucleic_acid and not text_present:
        flags.append(policy.qc_tokens["rdf_mod_without_text"])
    if text_present and not facts.has_modified_nucleic_acid:
        flags.append(policy.qc_tokens["text_without_rdf_mod"])

    chem_class, extras = classify_modification(modification_text, policy)
    flags.extend(extras)

    if source_object_type in policy.structure_topic_object_types:
        return "unknown", chem_class, tuple(dict.fromkeys(flags))

    if chem_class in AUTOMATIC_CHEMISTRY_CLASSES:
        mapped = policy.chemistry_automatic_map.get(chem_class, {})
        chemistry = mapped.get(molecule_type, "")
        if chem_class == "twof_rna" and molecule_type != "RNA":
            flags.append(policy.qc_tokens["chemistry_review"])
            if molecule_type == "ssDNA":
                flags.append(policy.qc_tokens["dna_twof"])
            return "unknown", chem_class, tuple(dict.fromkeys(flags))
        if chemistry:
            if chem_class == "unmodified_backbone" and molecule_type == "ssDNA" and text_present:
                # Native 2'-OH language is RNA sugar; do not auto-map onto DNA.
                flags.append(policy.qc_tokens["chemistry_review"])
                return "unknown", chem_class, tuple(dict.fromkeys(flags))
            return chemistry, chem_class, tuple(dict.fromkeys(flags))
        if molecule_type == "unknown" and chem_class in {
            "unmodified_backbone",
            "terminal_conjugate",
        }:
            # Object override / unresolved RDF already surfaces review via
            # molecule_type_unknown or non_aptamer_structure_topic.
            return "unknown", chem_class, tuple(dict.fromkeys(flags))
        flags.append(policy.qc_tokens["chemistry_review"])
        return "unknown", chem_class, tuple(dict.fromkeys(flags))

    flags.append(policy.qc_tokens["chemistry_review"])
    if chem_class == "spiegelmer_l_rna":
        flags.append(policy.qc_tokens["spiegelmer"])
    return "unknown", chem_class, tuple(dict.fromkeys(flags))


def resolve_aptamerbase_molecule_and_chemistry(
    source_metadata: Mapping[str, str],
    facts: AptamerBaseRdfSubjectFacts,
    policy: AptamerBaseNormalisationPolicy,
) -> MoleculeChemistryResult:
    """Resolve object class, RDF molecule type, override, and chemistry."""
    object_uri = source_metadata.get(policy.source_object_type_field, "")
    source_object_type = resolve_source_object_type(object_uri, policy)
    is_structure = source_object_type in policy.structure_topic_object_types
    rdf_molecule, rdf_flags = resolve_rdf_molecule_type(facts, policy)
    flags = list(rdf_flags)

    if is_structure:
        molecule_type = "unknown"
        flags.append(policy.qc_tokens["structure_topic"])
        evidence_source = "source_object_type"
    else:
        molecule_type = rdf_molecule
        evidence_source = policy.molecule_evidence_source

    chemistry, chem_class, chem_flags = resolve_chemistry(
        source_object_type=source_object_type,
        molecule_type=molecule_type,
        modification_text=source_metadata.get(policy.modification_text_field, ""),
        facts=facts,
        policy=policy,
    )
    flags.extend(chem_flags)
    return MoleculeChemistryResult(
        source_object_type=source_object_type,
        is_structure_topic=is_structure,
        rdf_molecule_type=rdf_molecule,
        molecule_type=molecule_type,
        chemistry=chemistry,
        chemistry_class=chem_class,
        evidence_source=evidence_source,
        rdf_has_rna=facts.has_rna,
        rdf_has_dna=facts.has_dna,
        qc_flags=tuple(dict.fromkeys(flags)),
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
    """Spec-aligned length buckets for the AptamerBase S2 report."""
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


def _length_matches_source(s2_length: str, reported_raw: str) -> str:
    if s2_length == "":
        return "n/a" if not (reported_raw or "").strip() else "false"
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
    length_matches: str,
) -> list[str]:
    reasons = [flag for flag in qc_flags if flag in REVIEW_RELEVANT_FLAGS]
    if length_matches == "false":
        reasons.append(REVIEW_REASON_LENGTH_MISMATCH)
    return sorted(set(reasons))


def normalise_aptamerbase_record(
    s1_record: Mapping[str, str],
    source_metadata: Mapping[str, str],
    facts: AptamerBaseRdfSubjectFacts,
    *,
    policy: AptamerBaseNormalisationPolicy,
    rules: SequenceNormalisationRules | None = None,
) -> AptamerBaseS2RowResult:
    """Normalise one AptamerBase S1 record into S2 canonical + QC rows."""
    active_rules = rules if rules is not None else load_normalisation_rules()
    if s1_record["record_id"] != source_metadata.get("record_id", ""):
        raise AptamerBaseS2Error("canonical and sidecar record_id values must match")

    sequence_raw = s1_record["sequence_raw"]
    molchem = resolve_aptamerbase_molecule_and_chemistry(
        source_metadata, facts, policy
    )
    qc_flags: list[str] = list(molchem.qc_flags)

    # Alphabet never establishes or erases experimental molecule type.
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
    length_qc_emitted = any(
        flag in {"core_below_min_length", "core_above_max_length"}
        for flag in norm.qc_flags
    )

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
        observable_length: int | None = None
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
        observable_length = len(sequence_full)
    else:
        construct_scope = "unknown"
        trim_status = "no_constants_detected"
        trim_confidence = TRIM_CONFIDENCE_NA
        length_full = str(len(sequence_full))
        length_core = str(len(sequence_core))
        alphabet = norm.alphabet_as_reported
        t_to_u = "true" if norm.t_to_u_applied else "false"
        observable_length = len(sequence_full)

    if (
        resolved_molecule == "ssDNA"
        and alphabet == ALPHABET_RNA
        and "U" in sequence_full
    ):
        conflict = policy.qc_tokens["molecule_alphabet_conflict"]
        if conflict not in qc_flags:
            qc_flags.append(conflict)

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
    review_reasons = _initial_review_reasons(
        [part for part in validated["qc_flags"].split(QC_DELIMITER) if part],
        length_matches=length_matches,
    )
    sidecar_minimal = source_metadata.get("aptamerbase_has_minimal_aptamer", "")
    sidecar_is_minimal = source_metadata.get(
        "aptamerbase_is_minimal_aptamer_of", ""
    )
    modification_text = source_metadata.get(policy.modification_text_field, "")
    aptamerbase_id = source_metadata.get(policy.source_id_field, "")
    qc = {
        "record_id": validated["record_id"],
        "native_id": validated["native_id"],
        "aptamerbase_id": aptamerbase_id,
        "source_object_type": molchem.source_object_type,
        "target_name_raw": validated["target_name_raw"],
        "alphabet_as_reported": validated["alphabet_as_reported"],
        "molecule_type": validated["molecule_type"],
        "chemistry": validated["chemistry"],
        "chemistry_class": molchem.chemistry_class,
        "molecule_evidence_source": molchem.evidence_source,
        "t_to_u_applied": validated["t_to_u_applied"],
        "sequence_length_full": validated["sequence_length_full"],
        "sequence_length_core": validated["sequence_length_core"],
        "reported_length_raw": reported_length,
        "length_matches_source": length_matches,
        "observable_length_bucket": length_bucket(observable_length),
        "rdf_has_rna": "true" if facts.has_rna else "false",
        "rdf_has_dna": "true" if facts.has_dna else "false",
        "rdf_has_modified_nucleic_acid": (
            "true" if facts.has_modified_nucleic_acid else "false"
        ),
        "rdf_has_minimal_aptamer_type": (
            "true" if facts.has_minimal_aptamer else "false"
        ),
        "has_minimal_aptamer_sidecar": "true" if sidecar_minimal.strip() else "false",
        "is_minimal_aptamer_of_sidecar": (
            "true" if sidecar_is_minimal.strip() else "false"
        ),
        "modification_text_present": "true" if modification_text.strip() else "false",
        "detected_motifs": detected_motif_names,
        "construct_scope": validated["construct_scope"],
        "trim_status": validated["trim_status"],
        "trim_confidence": validated["trim_confidence"],
        "qc_flags": validated["qc_flags"],
        "review_reasons": QC_DELIMITER.join(review_reasons),
    }
    return AptamerBaseS2RowResult(
        canonical=validated,
        qc=qc,
        transformations=tuple(norm.transformations),
        aptamerbase_id=aptamerbase_id,
        rdf_molecule_type=molchem.rdf_molecule_type,
        observable_length=observable_length,
        length_qc_emitted=length_qc_emitted,
    )


def is_review_candidate(qc: Mapping[str, str]) -> bool:
    """Return True when any AptamerBase S2 review-relevant condition is present."""
    reasons = {
        part for part in (qc.get("review_reasons") or "").split(QC_DELIMITER) if part
    }
    if reasons:
        return True
    flags = {part for part in (qc.get("qc_flags") or "").split(QC_DELIMITER) if part}
    return bool(flags & REVIEW_RELEVANT_FLAGS)


def update_stats_from_row(stats: AptamerBaseS2Stats, row: AptamerBaseS2RowResult) -> None:
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
    chem_class = row.qc.get("chemistry_class", "") or "(empty)"
    stats.chemistry_class_counts[chem_class] = (
        stats.chemistry_class_counts.get(chem_class, 0) + 1
    )

    object_type = row.qc.get("source_object_type", "") or "(blank)"
    stats.source_object_type_counts[object_type] = (
        stats.source_object_type_counts.get(object_type, 0) + 1
    )

    if canonical["t_to_u_applied"] == "true":
        stats.t_to_u_count += 1
    if molecule == "RNA" and alphabet == ALPHABET_DNA_T:
        stats.rna_t_alphabet_count += 1
    if policy_flag_present(flags, "source_molecule_alphabet_conflict"):
        stats.dna_u_conflict_count += 1
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
    # Observable buckets use the normalised string length even when shared
    # length QC flags were not emitted (invalid early-return path).
    observable = row.observable_length
    full_bucket = length_bucket(observable if observable is not None else full_len)
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
    if (
        observable is not None
        and not row.length_qc_emitted
        and (observable < 20 or observable > 100)
    ):
        stats.observable_length_without_core_qc += 1

    if canonical["sequence_full"] != canonical["sequence_core"]:
        stats.core_differs_from_full += 1
    if row.qc.get("length_matches_source") == "false":
        stats.length_mismatch_count += 1
    if row.qc.get("source_object_type") in {
        "nucleic_acid_secondary_structure",
        "predicted_secondary_structure",
    }:
        stats.structure_topic_rows += 1
        if canonical["sequence_length_full"]:
            stats.structure_topic_nonempty_sequence += 1
    rdf_mod = row.qc.get("rdf_has_modified_nucleic_acid") == "true"
    text_present = row.qc.get("modification_text_present") == "true"
    if rdf_mod and text_present:
        stats.rdf_modified_with_text += 1
    elif rdf_mod and not text_present:
        stats.rdf_modified_without_text += 1
    elif text_present and not rdf_mod:
        stats.text_without_rdf_modified += 1
    if "terminal_conjugate_present" in flags:
        stats.terminal_conjugate_count += 1
    if chemistry == "2F-RNA":
        stats.twof_rna_automatic_count += 1
    if "spiegelmer_l_rna_review" in flags:
        stats.spiegelmer_count += 1
    if "chemistry_requires_review" in flags:
        stats.chemistry_review_count += 1
    if row.qc.get("has_minimal_aptamer_sidecar") == "true":
        stats.sidecar_has_minimal_aptamer_nonempty += 1
    if row.qc.get("is_minimal_aptamer_of_sidecar") == "true":
        stats.sidecar_is_minimal_aptamer_of_nonempty += 1


def policy_flag_present(flags: Sequence[str], token: str) -> bool:
    return token in flags


def finalise_review_and_id_stats(
    stats: AptamerBaseS2Stats,
    rows: Sequence[AptamerBaseS2RowResult],
) -> None:
    """Recompute review-candidate and unique-ID diagnostics."""
    stats.review_candidate_rows = 0
    stats.review_reason_counts = {}
    molecule_by_id: dict[str, str] = {}
    conflict_ids: set[str] = set()
    rdf_molecule_by_id: dict[str, str] = {}
    for row in rows:
        source_id = row.aptamerbase_id
        rdf_molecule = row.rdf_molecule_type
        previous = rdf_molecule_by_id.get(source_id)
        if previous is None:
            rdf_molecule_by_id[source_id] = rdf_molecule
        elif previous != rdf_molecule:
            raise AptamerBaseS2Error(
                "repeated Freebase ID received inconsistent RDF-derived typing"
            )
        molecule_by_id.setdefault(source_id, row.canonical["molecule_type"])
        if "source_molecule_alphabet_conflict" in row.canonical["qc_flags"]:
            conflict_ids.add(source_id)
        if is_review_candidate(row.qc):
            stats.review_candidate_rows += 1
        for reason in row.qc.get("review_reasons", "").split(QC_DELIMITER):
            if reason:
                stats.review_reason_counts[reason] = (
                    stats.review_reason_counts.get(reason, 0) + 1
                )
    unique_molecule: dict[str, int] = {}
    for molecule in molecule_by_id.values():
        unique_molecule[molecule] = unique_molecule.get(molecule, 0) + 1
    stats.molecule_type_unique_id_counts = unique_molecule
    stats.unique_freebase_ids = len(molecule_by_id)
    stats.dna_u_conflict_unique_ids = len(conflict_ids)
    stats.rdf_subjects_joined = len(rdf_molecule_by_id)
    stats.rdf_join_coverage_ok = stats.unique_freebase_ids == stats.rdf_subjects_joined


def assert_genuine_proposals(proposals: Sequence[Mapping[str, str]]) -> None:
    """Reject motif-length-zero or otherwise non-scientific proposal rows."""
    for row in proposals:
        side = row.get("side", "")
        if side not in {"five_prime", "three_prime"}:
            raise AptamerBaseS2Error(
                f"proposal side must be five_prime/three_prime: {side}"
            )
        if row.get("applied") != "false":
            raise AptamerBaseS2Error("AptamerBase proposals must have applied=false")
        if row.get("proposal_source") == "group_consensus":
            raise AptamerBaseS2Error(
                "AptamerBase S2 must not emit group-consensus proposals"
            )
        motif = (row.get("proposed_sequence") or "").strip()
        motif_id = (row.get("motif_id") or "").strip()
        if not motif and not motif_id:
            raise AptamerBaseS2Error("proposal must have motif sequence or motif_id")
        try:
            length = int(row.get("motif_length") or "0")
        except ValueError as exc:
            raise AptamerBaseS2Error("motif_length must be an integer") from exc
        if length <= 0:
            raise AptamerBaseS2Error("proposal motif_length must be > 0")


def build_known_motif_proposals(
    rows: Sequence[AptamerBaseS2RowResult],
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


def s4_fields_are_empty(row: Mapping[str, str]) -> bool:
    """Return True when deferred global-S4 fields remain empty."""
    from common.corpus_schema import S2_FORBIDDEN_FIELDS

    return all(not row.get(field) for field in S2_FORBIDDEN_FIELDS)

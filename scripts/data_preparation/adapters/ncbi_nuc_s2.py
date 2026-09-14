"""NCBI Nucleotide S2 adapter: accession-approved molecule/construct policy.

Consumes S1 canonical rows plus the NCBI GenBank source-metadata sidecar.
Sequence cleaning uses the shared normaliser only. Group-wise
constant-region inference is disabled. Does not accept, reject or park
records. Does not apply trims. Does not infer molecule identity from
alphabet, ENA, patent titles, or sequence length.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

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

ALLOWED_CONSTRUCT_SCOPES: Final[frozenset[str]] = frozenset(
    {
        "unknown",
        "partial_construct",
        "full_construct",
    }
)

ALLOWED_MOLECULE_TYPES: Final[frozenset[str]] = frozenset({"RNA", "DNA", "unknown"})
ALLOWED_CHEMISTRY: Final[frozenset[str]] = frozenset({"RNA", "DNA", "unknown"})

ALLOWED_SOURCE_OBJECT_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "primer_associated",
        "cdna_template_associated",
        "transcription_template",
        "poly_a_fragment",
        "possible_non_aptamer_method_object",
        "unresolved_aptamer_status",
    }
)

APPROVED_RNA_ACCESSIONS: Final[frozenset[str]] = frozenset(
    {"U34759", "U37124", "U37123", "AF083271", "BD161067"}
)
APPROVED_DNA_ACCESSIONS: Final[frozenset[str]] = frozenset({"QT662269"})

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
    "source_object_class",
    "construct_requires_review",
    "primer_associated",
    "cdna_template_associated",
    "transcription_template",
    "poly_a_fragment",
    "possible_non_aptamer_source_object",
    "unresolved_aptamer_status",
    "known_motif_detected",
    "group_consensus_proposal",
    "ncbi_nuc_locus_molecule",
    "ncbi_nuc_source_mol_type",
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
        "t_in_reported_rna",
        "u_in_reported_dna",
        "known_promoter_detected",
        "trim_requires_review",
        "core_below_min_length",
        "core_above_max_length",
        "constants_suspected_unresolved",
        "construct_requires_review",
        "primer_associated",
        "cdna_template_associated",
        "transcription_template",
        "poly_a_fragment",
        "possible_non_aptamer_source_object",
        "unresolved_aptamer_status",
    }
)

REVIEW_REASON_KNOWN_MOTIF: Final[str] = "known_motif_proposal"
REVIEW_REASON_LENGTH_MISMATCH: Final[str] = "source_length_mismatch"
REVIEW_REASON_UNRESOLVED_MOLECULE: Final[str] = "unresolved_molecule_identity"


class NcbiNucS2Error(ValueError):
    """Hard failure during NCBI Nucleotide S2 normalisation."""


@dataclass(frozen=True)
class AccessionIdentity:
    """Approved molecule/chemistry assignment for one ACCESSION."""

    molecule_type: str
    chemistry: str


@dataclass(frozen=True)
class NcbiNucNormalisationPolicy:
    """Tracked NCBI Nucleotide S2 source-normalisation policy."""

    source_key: str
    contract_version: str
    molecule_evidence_source: str
    reported_length_field: str
    apply_approved_trims: bool
    group_inference_key: str
    do_not_infer_molecule_from_alphabet: bool
    do_not_apply_inferred_trims: bool
    do_not_create_experiment_group_id: bool
    do_not_coerce_dna_to_ssdna: bool
    default_molecule_type: str
    default_chemistry: str
    default_construct_scope: str
    molecule_identity_by_accession: Mapping[str, AccessionIdentity]
    construct_scope_by_accession: Mapping[str, str]
    source_object_class_by_accession: Mapping[str, str]


@dataclass(frozen=True)
class MoleculeChemistryResult:
    """Resolved molecule type and chemistry from the accession policy."""

    accession: str
    molecule_type: str
    chemistry: str
    evidence_source: str
    qc_flags: tuple[str, ...]


@dataclass(frozen=True)
class ConstructInterpretation:
    """Source-supported construct/object interpretation for one record."""

    construct_scope: str
    source_object_class: str
    qc_flags: tuple[str, ...]
    review_reasons: tuple[str, ...]


@dataclass
class NcbiNucS2RowResult:
    """Canonical S2 row plus QC sidecar payload for one record."""

    canonical: dict[str, str]
    qc: dict[str, str]
    transformations: tuple[str, ...] = ()


@dataclass
class NcbiNucS2Stats:
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
    pubmed_id_unchanged: bool = False
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
    source_object_class_counts: dict[str, int] = field(default_factory=dict)
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
    five_prime_proposals: int = 0
    three_prime_proposals: int = 0
    records_with_medium_confidence_proposal: int = 0
    high_confidence_trims_applied: int = 0
    constant_region_reason: str = (
        "group-wise inference disabled for ncbi_nuc in this run"
    )
    known_motifs_scanned: tuple[str, ...] = ()


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NcbiNucS2Error(f"{name} must be a JSON object")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise NcbiNucS2Error(f"{name} must be a boolean")
    return value


def _require_nonempty_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NcbiNucS2Error(f"{name} must be a non-empty string")
    return value.strip()


def _require_str_map(value: Any, name: str) -> dict[str, str]:
    data = _require_mapping(value, name)
    out: dict[str, str] = {}
    for key, mapped in data.items():
        if not isinstance(key, str) or not isinstance(mapped, str):
            raise NcbiNucS2Error(f"{name} keys and values must be strings")
        accession = key.strip()
        mapped_value = mapped.strip()
        if not accession or not mapped_value:
            raise NcbiNucS2Error(f"{name} keys and values must be non-empty")
        out[accession] = mapped_value
    return out


def _load_molecule_identity_map(
    value: Any,
    *,
    do_not_coerce_dna_to_ssdna: bool,
) -> dict[str, AccessionIdentity]:
    data = _require_mapping(value, "molecule_identity_by_accession")
    out: dict[str, AccessionIdentity] = {}
    for key, payload in data.items():
        if not isinstance(key, str) or not key.strip():
            raise NcbiNucS2Error(
                "molecule_identity_by_accession keys must be ACCESSION strings"
            )
        mapping = _require_mapping(payload, f"molecule_identity_by_accession.{key}")
        molecule = _require_nonempty_str(
            mapping.get("molecule_type"),
            f"molecule_identity_by_accession.{key}.molecule_type",
        )
        chemistry = _require_nonempty_str(
            mapping.get("chemistry"),
            f"molecule_identity_by_accession.{key}.chemistry",
        )
        if molecule not in ALLOWED_MOLECULE_TYPES:
            raise NcbiNucS2Error(
                f"unsupported molecule_type for {key}: {molecule!r}"
            )
        if chemistry not in ALLOWED_CHEMISTRY:
            raise NcbiNucS2Error(
                f"unsupported chemistry for {key}: {chemistry!r}"
            )
        if do_not_coerce_dna_to_ssdna and molecule == "ssDNA":
            raise NcbiNucS2Error(
                "ncbi_nuc must not coerce deposited DNA to ssDNA"
            )
        if molecule == "DNA" and chemistry != "DNA":
            raise NcbiNucS2Error(
                f"ncbi_nuc DNA accession {key} must use chemistry=DNA"
            )
        if molecule == "RNA" and chemistry != "RNA":
            raise NcbiNucS2Error(
                f"ncbi_nuc RNA accession {key} must use chemistry=RNA"
            )
        out[key.strip()] = AccessionIdentity(
            molecule_type=molecule, chemistry=chemistry
        )
    rna = {acc for acc, ident in out.items() if ident.molecule_type == "RNA"}
    dna = {acc for acc, ident in out.items() if ident.molecule_type == "DNA"}
    if rna != APPROVED_RNA_ACCESSIONS:
        raise NcbiNucS2Error(
            "ncbi_nuc RNA ACCESSION set must be exactly the approved five"
        )
    if dna != APPROVED_DNA_ACCESSIONS:
        raise NcbiNucS2Error(
            "ncbi_nuc DNA ACCESSION set must be exactly QT662269"
        )
    return out


def load_ncbi_nuc_policy(path: str | Path) -> NcbiNucNormalisationPolicy:
    """Load and validate the NCBI Nucleotide source-normalisation policy JSON."""
    policy_path = Path(path)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise NcbiNucS2Error(f"cannot read NCBI Nucleotide policy: {exc.strerror}") from exc
    except json.JSONDecodeError as exc:
        raise NcbiNucS2Error(f"NCBI Nucleotide policy JSON is invalid: {exc.msg}") from exc

    data = _require_mapping(payload, "policy")
    source_key = data.get("source_key")
    if source_key != "ncbi_nuc":
        raise NcbiNucS2Error("policy source_key must be 'ncbi_nuc'")
    grouping = _require_nonempty_str(
        data.get("group_inference_key"), "group_inference_key"
    )
    if grouping != GROUP_INFERENCE_DISABLED:
        raise NcbiNucS2Error(
            "ncbi_nuc S2 group_inference_key must be 'disabled'; "
            "group-wise constant-region inference is not authorised"
        )
    if data.get("apply_approved_trims") is True:
        raise NcbiNucS2Error("ncbi_nuc S2 must not apply approved trims")
    do_not_infer = _require_bool(
        data.get("do_not_infer_molecule_from_alphabet", True),
        "do_not_infer_molecule_from_alphabet",
    )
    if not do_not_infer:
        raise NcbiNucS2Error("ncbi_nuc molecule type must not be inferred from alphabet")
    do_not_apply = _require_bool(
        data.get("do_not_apply_inferred_trims", True),
        "do_not_apply_inferred_trims",
    )
    if not do_not_apply:
        raise NcbiNucS2Error("ncbi_nuc S2 must not apply inferred constant-region trims")
    do_not_create_group = _require_bool(
        data.get("do_not_create_experiment_group_id", True),
        "do_not_create_experiment_group_id",
    )
    if not do_not_create_group:
        raise NcbiNucS2Error("ncbi_nuc S2 must not create experiment_group_id")
    do_not_coerce = _require_bool(
        data.get("do_not_coerce_dna_to_ssdna", True),
        "do_not_coerce_dna_to_ssdna",
    )
    if not do_not_coerce:
        raise NcbiNucS2Error("ncbi_nuc must not coerce DNA to ssDNA")

    default_molecule = _require_nonempty_str(
        data.get("default_molecule_type"), "default_molecule_type"
    )
    default_chemistry = _require_nonempty_str(
        data.get("default_chemistry"), "default_chemistry"
    )
    if default_molecule != "unknown" or default_chemistry != "unknown":
        raise NcbiNucS2Error(
            "ncbi_nuc default molecule/chemistry must remain unknown"
        )
    default_scope = _require_nonempty_str(
        data.get("default_construct_scope"), "default_construct_scope"
    )
    if default_scope != "unknown":
        raise NcbiNucS2Error("ncbi_nuc default construct_scope must be unknown")

    construct_map = _require_str_map(
        data.get("construct_scope_by_accession"), "construct_scope_by_accession"
    )
    for accession, scope in construct_map.items():
        if scope not in ALLOWED_CONSTRUCT_SCOPES:
            raise NcbiNucS2Error(
                f"unsupported construct_scope for {accession}: {scope!r}"
            )
        if scope == "random_region_only":
            raise NcbiNucS2Error(
                "ncbi_nuc must not assign random_region_only from sequence appearance"
            )
    object_map = _require_str_map(
        data.get("source_object_class_by_accession"),
        "source_object_class_by_accession",
    )
    for accession, object_class in object_map.items():
        if object_class not in ALLOWED_SOURCE_OBJECT_CLASSES:
            raise NcbiNucS2Error(
                f"unsupported source_object_class for {accession}: {object_class!r}"
            )

    return NcbiNucNormalisationPolicy(
        source_key=source_key,
        contract_version=_require_nonempty_str(
            data.get("contract_version"), "contract_version"
        ),
        molecule_evidence_source=_require_nonempty_str(
            data.get("molecule_evidence_source"), "molecule_evidence_source"
        ),
        reported_length_field=str(data.get("reported_length_field", "")),
        apply_approved_trims=_require_bool(
            data.get("apply_approved_trims"), "apply_approved_trims"
        ),
        group_inference_key=grouping,
        do_not_infer_molecule_from_alphabet=do_not_infer,
        do_not_apply_inferred_trims=do_not_apply,
        do_not_create_experiment_group_id=do_not_create_group,
        do_not_coerce_dna_to_ssdna=do_not_coerce,
        default_molecule_type=default_molecule,
        default_chemistry=default_chemistry,
        default_construct_scope=default_scope,
        molecule_identity_by_accession=_load_molecule_identity_map(
            data.get("molecule_identity_by_accession"),
            do_not_coerce_dna_to_ssdna=do_not_coerce,
        ),
        construct_scope_by_accession=construct_map,
        source_object_class_by_accession=object_map,
    )


def resolve_ncbi_nuc_molecule_and_chemistry(
    native_id: str,
    policy: NcbiNucNormalisationPolicy,
) -> MoleculeChemistryResult:
    """Return the accession-approved molecule identity.

    Alphabet is never consulted. Unlisted ACCESSION values remain unknown.
    """
    accession = (native_id or "").strip()
    identity = policy.molecule_identity_by_accession.get(accession)
    if identity is None:
        flags: tuple[str, ...] = ("molecule_type_unknown",)
        return MoleculeChemistryResult(
            accession=accession,
            molecule_type=policy.default_molecule_type,
            chemistry=policy.default_chemistry,
            evidence_source="unresolved_genbank_identity",
            qc_flags=flags,
        )
    return MoleculeChemistryResult(
        accession=accession,
        molecule_type=identity.molecule_type,
        chemistry=identity.chemistry,
        evidence_source=policy.molecule_evidence_source,
        qc_flags=(),
    )


def interpret_ncbi_nuc_construct(
    native_id: str,
    policy: NcbiNucNormalisationPolicy,
) -> ConstructInterpretation:
    """Return source-supported construct/object flags without guessing a core."""
    accession = (native_id or "").strip()
    construct_scope = policy.construct_scope_by_accession.get(
        accession, policy.default_construct_scope
    )
    object_class = policy.source_object_class_by_accession.get(accession, "")
    if not object_class and accession not in policy.molecule_identity_by_accession:
        object_class = "unresolved_aptamer_status"

    qc_flags: list[str] = []
    review_reasons: list[str] = []
    if object_class == "possible_non_aptamer_method_object":
        qc_flags.append("possible_non_aptamer_source_object")
        review_reasons.append("possible_non_aptamer_source_object")
    elif object_class:
        qc_flags.append(object_class)
        review_reasons.append(object_class)
    if object_class in {
        "primer_associated",
        "cdna_template_associated",
        "transcription_template",
        "poly_a_fragment",
    }:
        qc_flags.append("construct_requires_review")
        review_reasons.append("construct_requires_review")
    return ConstructInterpretation(
        construct_scope=construct_scope,
        source_object_class=object_class,
        qc_flags=tuple(dict.fromkeys(qc_flags)),
        review_reasons=tuple(dict.fromkeys(review_reasons)),
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
    """Spec-aligned length buckets for the NCBI Nucleotide S2 report."""
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
        return None
    return value


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


def s4_fields_are_empty(row: Mapping[str, str]) -> bool:
    """Return True when deferred global-S4 fields remain empty."""
    return all(not row.get(field) for field in S2_FORBIDDEN_FIELDS)


def _boolean_token(value: bool) -> str:
    return "true" if value else "false"


def normalise_ncbi_nuc_record(
    s1_record: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: NcbiNucNormalisationPolicy,
    rules: SequenceNormalisationRules | None = None,
) -> NcbiNucS2RowResult:
    """Normalise one NCBI Nucleotide S1 record into S2 canonical + QC rows."""
    active_rules = rules if rules is not None else load_normalisation_rules()
    if s1_record["record_id"] != source_metadata.get("record_id", ""):
        raise NcbiNucS2Error("canonical and sidecar record_id values must match")
    native_id = s1_record["native_id"]
    if native_id != source_metadata.get("native_id", ""):
        raise NcbiNucS2Error("canonical and sidecar native_id values must match")

    sequence_raw = s1_record["sequence_raw"]
    molchem = resolve_ncbi_nuc_molecule_and_chemistry(native_id, policy)
    construct = interpret_ncbi_nuc_construct(native_id, policy)
    qc_flags: list[str] = list(molchem.qc_flags)
    qc_flags.extend(construct.qc_flags)

    # Sidecar GenBank text is provenance only; never molecule evidence here.
    _ = source_metadata.get("ncbi_nuc_definition", "")
    _ = source_metadata.get("ncbi_nuc_comment", "")
    _ = source_metadata.get("ncbi_nuc_locus_molecule", "")
    _ = source_metadata.get("ncbi_nuc_source_mol_type", "")

    norm = normalise_sequence(
        sequence_raw,
        molecule_type=molchem.molecule_type,
        trim_plan=None,
        rules=active_rules,
    )
    qc_flags.extend(norm.qc_flags)

    # Policy molecule identity is authoritative; alphabet must not override it.
    resolved_molecule = molchem.molecule_type
    sequence_full = norm.sequence_full or ""
    sequence_core = sequence_full
    five_motifs, three_motifs = _motif_names_by_side(norm.detected_motifs)

    if norm.sequence_full is None:
        construct_scope = construct.construct_scope
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
        construct_scope = construct.construct_scope
        trim_status = "constants_suspected_unresolved"
        trim_confidence = TRIM_CONFIDENCE_NA
        qc_flags.append("constants_suspected_unresolved")
        qc_flags.append("trim_requires_review")
        length_full = str(len(sequence_full))
        length_core = str(len(sequence_core))
        alphabet = norm.alphabet_as_reported
        t_to_u = "true" if norm.t_to_u_applied else "false"
    else:
        construct_scope = construct.construct_scope
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

    if t_to_u == "true" and resolved_molecule != "RNA":
        raise NcbiNucS2Error(
            "T→U may be applied only to source-approved RNA ACCESSION values"
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

    if not s4_fields_are_empty(canonical):
        raise NcbiNucS2Error("ncbi_nuc S2 must not populate deferred S4 fields")

    validated = validate_s2_record(canonical, s1_record=s1_record)
    detected_motif_names = QC_DELIMITER.join(
        sorted({motif.name for motif in norm.detected_motifs})
    )
    reported_length = source_metadata.get(policy.reported_length_field, "")
    length_matches = _length_matches_source(
        validated["sequence_length_full"], reported_length
    )
    known_motif = bool(detected_motif_names)
    review_reasons = list(construct.review_reasons)
    for flag in [part for part in validated["qc_flags"].split(QC_DELIMITER) if part]:
        if flag in REVIEW_RELEVANT_FLAGS:
            review_reasons.append(flag)
    if resolved_molecule == "unknown":
        review_reasons.append(REVIEW_REASON_UNRESOLVED_MOLECULE)
    if known_motif:
        review_reasons.append(REVIEW_REASON_KNOWN_MOTIF)
    if length_matches == "false":
        review_reasons.append(REVIEW_REASON_LENGTH_MISMATCH)
    review_reasons = sorted(set(review_reasons))

    primer = construct.source_object_class == "primer_associated"
    cdna = construct.source_object_class == "cdna_template_associated"
    template = construct.source_object_class == "transcription_template"
    poly_a = construct.source_object_class == "poly_a_fragment"
    non_aptamer = construct.source_object_class == "possible_non_aptamer_method_object"
    unresolved_status = construct.source_object_class == "unresolved_aptamer_status"
    construct_review = "construct_requires_review" in construct.qc_flags

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
        "source_object_class": construct.source_object_class,
        "construct_requires_review": _boolean_token(construct_review),
        "primer_associated": _boolean_token(primer),
        "cdna_template_associated": _boolean_token(cdna),
        "transcription_template": _boolean_token(template),
        "poly_a_fragment": _boolean_token(poly_a),
        "possible_non_aptamer_source_object": _boolean_token(non_aptamer),
        "unresolved_aptamer_status": _boolean_token(unresolved_status),
        "known_motif_detected": _boolean_token(known_motif),
        "group_consensus_proposal": "false",
        "ncbi_nuc_locus_molecule": source_metadata.get("ncbi_nuc_locus_molecule", ""),
        "ncbi_nuc_source_mol_type": source_metadata.get("ncbi_nuc_source_mol_type", ""),
        "qc_flags": validated["qc_flags"],
        "review_reasons": QC_DELIMITER.join(review_reasons),
    }
    return NcbiNucS2RowResult(
        canonical=validated,
        qc=qc,
        transformations=tuple(norm.transformations),
    )


def is_review_candidate(qc: Mapping[str, str]) -> bool:
    """Return True when any NCBI S2 review-relevant condition is present."""
    reasons = {
        part for part in (qc.get("review_reasons") or "").split(QC_DELIMITER) if part
    }
    if reasons:
        return True
    flags = {part for part in (qc.get("qc_flags") or "").split(QC_DELIMITER) if part}
    if flags & REVIEW_RELEVANT_FLAGS:
        return True
    if qc.get("known_motif_detected") == "true":
        return True
    if qc.get("construct_requires_review") == "true":
        return True
    return False


def update_stats_from_row(stats: NcbiNucS2Stats, row: NcbiNucS2RowResult) -> None:
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
    object_class = row.qc.get("source_object_class", "") or "(none)"
    stats.source_object_class_counts[object_class] = (
        stats.source_object_class_counts.get(object_class, 0) + 1
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


def finalise_review_stats(
    stats: NcbiNucS2Stats,
    rows: Sequence[NcbiNucS2RowResult],
) -> None:
    """Recompute review-candidate counts after row normalisation."""
    stats.review_candidate_rows = 0
    stats.review_reason_counts = {}
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
            raise NcbiNucS2Error(
                f"proposal side must be five_prime/three_prime: {side}"
            )
        if row.get("applied") != "false":
            raise NcbiNucS2Error("ncbi_nuc proposals must have applied=false")
        if row.get("proposal_source") == "group_consensus":
            raise NcbiNucS2Error(
                "ncbi_nuc S2 must not emit group-consensus proposals"
            )
        motif = (row.get("proposed_sequence") or "").strip()
        motif_id = (row.get("motif_id") or "").strip()
        if not motif and not motif_id:
            raise NcbiNucS2Error("proposal must have motif sequence or motif_id")
        try:
            length = int(row.get("motif_length") or "0")
        except ValueError as exc:
            raise NcbiNucS2Error("motif_length must be an integer") from exc
        if length <= 0:
            raise NcbiNucS2Error("proposal motif_length must be > 0")


def build_known_motif_proposals(
    rows: Sequence[NcbiNucS2RowResult],
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

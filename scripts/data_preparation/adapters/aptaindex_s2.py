"""AptaIndex S2 adapter: chemical-notation parse then shared normalisation.

Consumes S1 canonical rows plus the AptaIndex source-metadata sidecar.
Chemical notation is parsed in a source-specific full-consumption parser
before shared nucleotide normalisation. Does not accept, reject or park
records. Does not apply newly inferred constant-region trims. Does not
run group-wise constant-region inference.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from adapters.aptaindex_sequence_parser import (
    PEPTIDE_SOURCE_TYPE,
    STATUS_MISSING,
    STATUS_NOT_APPLICABLE_PEPTIDE,
    STATUS_SUCCESS,
    STATUS_UNSUPPORTED,
    AptaIndexParseResult,
    parse_aptaindex_source_sequence,
)
from common.corpus_schema import (
    format_qc_flags,
    validate_s2_record,
)
from common.sequence_normalisation import (
    ALPHABET_CHEMICAL_NOTATION,
    ALPHABET_MISSING,
    TRIM_CONFIDENCE_NA,
    SequenceNormalisationResult,
    SequenceNormalisationRules,
    detect_known_non_core_motifs,
    load_normalisation_rules,
    normalise_sequence,
    validate_core_length,
)

QC_DELIMITER: Final[str] = "|"
GROUP_INFERENCE_DISABLED: Final[str] = "disabled"

S2_QC_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "source_type",
    "parser_status",
    "parser_reason_category",
    "mapping_class",
    "token_family_summary",
    "has_l_prefix",
    "linkage_summary",
    "has_terminal_phosphate",
    "alphabet_as_reported",
    "molecule_type",
    "chemistry",
    "molecule_evidence_source",
    "t_to_u_applied",
    "has_t",
    "has_u",
    "mixed_t_u",
    "sequence_length_full",
    "sequence_length_core",
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
        "parser_not_applicable_peptide",
        "unsupported_notation",
        "source_type_unsupported",
        "source_type_token_disagreement",
        "mixed_token_chemistry",
        "l_nucleotide_syntax",
        "mixed_t_u",
        "inosine_base",
        "molecule_type_unknown",
        "known_promoter_detected",
        "trim_requires_review",
        "constants_suspected_unresolved",
        "core_below_min_length",
        "core_above_max_length",
        "linkage_phosphorothioate",
        "linkage_mixed",
    }
)


class AptaIndexS2Error(ValueError):
    """Hard failure during AptaIndex S2 normalisation."""


@dataclass(frozen=True)
class StraightforwardMapping:
    """One Type × token-family mapping authorised at S2."""

    source_type: str
    token_families: tuple[str, ...]
    allow_l_prefix: bool
    molecule_type: str
    chemistry: str
    mapping_class: str
    notes: str


@dataclass(frozen=True)
class AptaindexNormalisationPolicy:
    """Tracked AptaIndex S2 source-normalisation policy."""

    source_key: str
    contract_version: str
    source_type_field: str
    alphabet_as_reported_nucleic_acid: str
    peptide_source_type: str
    apply_approved_trims: bool
    group_inference_key: str
    do_not_infer_molecule_from_alphabet: bool
    unmapped_molecule_type: str
    unmapped_chemistry: str
    known_source_types: tuple[str, ...]
    do_not_auto_resolve_source_types: tuple[str, ...]
    straightforward_mappings: tuple[StraightforwardMapping, ...]


@dataclass(frozen=True)
class MoleculeChemistryResult:
    """Resolved molecule/chemistry proposal for one AptaIndex record."""

    source_value: str
    molecule_type: str
    chemistry: str
    evidence_source: str
    mapping_class: str
    qc_flags: tuple[str, ...]


@dataclass
class AptaIndexS2RowResult:
    """Canonical S2 row plus QC sidecar payload for one record."""

    canonical: dict[str, str]
    qc: dict[str, str]
    transformations: tuple[str, ...] = ()
    parse: AptaIndexParseResult | None = None


@dataclass
class AptaIndexS2Stats:
    """Aggregate S2 counts (no sequences). Native IDs are not stored here."""

    s1_rows: int = 0
    source_metadata_rows: int = 0
    s2_rows: int = 0
    unique_record_ids: int = 0
    unique_native_ids: int = 0
    missing_sequence_rows: int = 0
    peptide_rows: int = 0
    nonempty_nucleic_acid_rows: int = 0
    successful_parses: int = 0
    unsupported_nucleic_parses: int = 0
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
    parser_status_counts: dict[str, int] = field(default_factory=dict)
    parser_reason_counts: dict[str, int] = field(default_factory=dict)
    mapping_class_counts: dict[str, int] = field(default_factory=dict)
    token_family_counts: dict[str, int] = field(default_factory=dict)
    type_token_family_counts: dict[str, int] = field(default_factory=dict)
    t_to_u_count: int = 0
    parsed_t_only: int = 0
    parsed_u_only: int = 0
    parsed_neither_t_u: int = 0
    mixed_t_u_count: int = 0
    l_nucleotide_count: int = 0
    inosine_count: int = 0
    linkage_phosphorothioate_count: int = 0
    linkage_mixed_count: int = 0
    source_type_disagreement_count: int = 0
    source_type_unsupported_count: int = 0
    known_motif_detection_count: int = 0
    trim_review_count: int = 0
    core_below_min_count: int = 0
    core_above_max_count: int = 0
    no_constants_detected_count: int = 0
    medium_confidence_inference_count: int = 0
    trim_to_short_count: int = 0
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
        "group-wise inference disabled for AptaIndex in this run"
    )
    known_motifs_scanned: tuple[str, ...] = ()


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AptaIndexS2Error(f"{name} must be a JSON object")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise AptaIndexS2Error(f"{name} must be a boolean")
    return value


def _require_nonempty_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AptaIndexS2Error(f"{name} must be a non-empty string")
    return value.strip()


def _require_str_list(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AptaIndexS2Error(f"{name} must be a list of strings")
    return tuple(value)


def load_aptaindex_policy(path: str | Path) -> AptaindexNormalisationPolicy:
    """Load and validate the AptaIndex source-normalisation policy JSON."""
    policy_path = Path(path)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AptaIndexS2Error(
            f"cannot read AptaIndex policy: {exc.strerror}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise AptaIndexS2Error(
            f"AptaIndex policy JSON is invalid: {exc.msg}"
        ) from exc

    data = _require_mapping(payload, "policy")
    source_key = data.get("source_key")
    if source_key != "aptaindex":
        raise AptaIndexS2Error("policy source_key must be 'aptaindex'")
    grouping = _require_nonempty_str(
        data.get("group_inference_key"), "group_inference_key"
    )
    if grouping != GROUP_INFERENCE_DISABLED:
        raise AptaIndexS2Error(
            "AptaIndex S2 group_inference_key must be 'disabled'; "
            "group-wise constant-region inference is not authorised"
        )
    if data.get("apply_approved_trims") is True:
        raise AptaIndexS2Error(
            "AptaIndex S2 must not apply approved trims in this milestone"
        )
    alphabet = _require_nonempty_str(
        data.get("alphabet_as_reported_nucleic_acid"),
        "alphabet_as_reported_nucleic_acid",
    )
    if alphabet != ALPHABET_CHEMICAL_NOTATION:
        raise AptaIndexS2Error(
            "AptaIndex nucleic-acid alphabet_as_reported must be "
            "chemical_notation"
        )

    raw_mappings = data.get("straightforward_mappings")
    if not isinstance(raw_mappings, list):
        raise AptaIndexS2Error("straightforward_mappings must be a list")
    mappings: list[StraightforwardMapping] = []
    for index, item in enumerate(raw_mappings):
        row = _require_mapping(item, f"straightforward_mappings[{index}]")
        mappings.append(
            StraightforwardMapping(
                source_type=_require_nonempty_str(
                    row.get("source_type"),
                    f"straightforward_mappings[{index}].source_type",
                ),
                token_families=tuple(
                    sorted(
                        _require_str_list(
                            row.get("token_families"),
                            f"straightforward_mappings[{index}].token_families",
                        )
                    )
                ),
                allow_l_prefix=_require_bool(
                    row.get("allow_l_prefix"),
                    f"straightforward_mappings[{index}].allow_l_prefix",
                ),
                molecule_type=_require_nonempty_str(
                    row.get("molecule_type"),
                    f"straightforward_mappings[{index}].molecule_type",
                ),
                chemistry=_require_nonempty_str(
                    row.get("chemistry"),
                    f"straightforward_mappings[{index}].chemistry",
                ),
                mapping_class=_require_nonempty_str(
                    row.get("mapping_class"),
                    f"straightforward_mappings[{index}].mapping_class",
                ),
                notes=str(row.get("notes", "")),
            )
        )

    return AptaindexNormalisationPolicy(
        source_key=source_key,
        contract_version=_require_nonempty_str(
            data.get("contract_version"), "contract_version"
        ),
        source_type_field=_require_nonempty_str(
            data.get("source_type_field"), "source_type_field"
        ),
        alphabet_as_reported_nucleic_acid=alphabet,
        peptide_source_type=str(
            data.get("peptide_source_type", PEPTIDE_SOURCE_TYPE)
        ),
        apply_approved_trims=_require_bool(
            data.get("apply_approved_trims"), "apply_approved_trims"
        ),
        group_inference_key=grouping,
        do_not_infer_molecule_from_alphabet=_require_bool(
            data.get("do_not_infer_molecule_from_alphabet", True),
            "do_not_infer_molecule_from_alphabet",
        ),
        unmapped_molecule_type=str(data.get("unmapped_molecule_type", "unknown")),
        unmapped_chemistry=str(data.get("unmapped_chemistry", "unknown")),
        known_source_types=_require_str_list(
            data.get("known_source_types"), "known_source_types"
        ),
        do_not_auto_resolve_source_types=_require_str_list(
            data.get("do_not_auto_resolve_source_types"),
            "do_not_auto_resolve_source_types",
        ),
        straightforward_mappings=tuple(mappings),
    )


def resolve_aptaindex_molecule_and_chemistry(
    source_type: str,
    parse: AptaIndexParseResult,
    policy: AptaindexNormalisationPolicy,
) -> MoleculeChemistryResult:
    """Map molecule/chemistry only where Type and token syntax agree.

    L-RNA, L-DNA, Chimeric, Type/token disagreements and mixed families
    remain unknown proposals for S3/CHECKPOINT-1.
    """
    flags: list[str] = []
    unmapped_mol = policy.unmapped_molecule_type
    unmapped_chem = policy.unmapped_chemistry

    if parse.status == STATUS_MISSING:
        return MoleculeChemistryResult(
            source_value=source_type,
            molecule_type=unmapped_mol,
            chemistry=unmapped_chem,
            evidence_source="",
            mapping_class="missing_sequence",
            qc_flags=("missing_sequence", "molecule_type_unknown"),
        )
    if parse.status == STATUS_NOT_APPLICABLE_PEPTIDE:
        return MoleculeChemistryResult(
            source_value=source_type,
            molecule_type=unmapped_mol,
            chemistry=unmapped_chem,
            evidence_source="source_type_peptide",
            mapping_class="peptide",
            qc_flags=("parser_not_applicable_peptide",),
        )
    if parse.status == STATUS_UNSUPPORTED:
        extra: list[str] = ["unsupported_notation", "molecule_type_unknown"]
        if source_type == "":
            extra.append("source_type_blank")
        elif source_type not in set(policy.known_source_types):
            extra.append("source_type_unsupported")
        return MoleculeChemistryResult(
            source_value=source_type,
            molecule_type=unmapped_mol,
            chemistry=unmapped_chem,
            evidence_source="",
            mapping_class="unsupported_notation",
            qc_flags=tuple(extra),
        )

    if parse.has_l_prefix:
        flags.append("l_nucleotide_syntax")
    if len(parse.token_prefixes) > 1:
        authorised_mixed = False
        for mapping in policy.straightforward_mappings:
            if (
                source_type == mapping.source_type
                and parse.token_prefixes == mapping.token_families
                and (mapping.allow_l_prefix or not parse.has_l_prefix)
                and len(mapping.token_families) > 1
            ):
                authorised_mixed = True
                break
        if not authorised_mixed:
            flags.append("mixed_token_chemistry")

    if source_type == "":
        flags.append("source_type_blank")
        flags.append("molecule_type_unknown")
        return MoleculeChemistryResult(
            source_value=source_type,
            molecule_type=unmapped_mol,
            chemistry=unmapped_chem,
            evidence_source="",
            mapping_class="source_type_blank",
            qc_flags=tuple(sorted(set(flags))),
        )
    if source_type not in set(policy.known_source_types):
        flags.append("source_type_unsupported")
        flags.append("molecule_type_unknown")
        return MoleculeChemistryResult(
            source_value=source_type,
            molecule_type=unmapped_mol,
            chemistry=unmapped_chem,
            evidence_source="",
            mapping_class="source_type_unsupported",
            qc_flags=tuple(sorted(set(flags))),
        )
    if source_type in set(policy.do_not_auto_resolve_source_types):
        flags.append("molecule_type_unknown")
        mapping_class = {
            "L-RNA": "l_rna",
            "L-DNA": "l_dna",
            "Chimeric": "chimeric",
        }.get(source_type, "unmapped_other")
        return MoleculeChemistryResult(
            source_value=source_type,
            molecule_type=unmapped_mol,
            chemistry=unmapped_chem,
            evidence_source="source_type_deferred",
            mapping_class=mapping_class,
            qc_flags=tuple(sorted(set(flags))),
        )

    for mapping in policy.straightforward_mappings:
        if source_type != mapping.source_type:
            continue
        if parse.token_prefixes != mapping.token_families:
            continue
        if parse.has_l_prefix and not mapping.allow_l_prefix:
            continue
        return MoleculeChemistryResult(
            source_value=source_type,
            molecule_type=mapping.molecule_type,
            chemistry=mapping.chemistry,
            evidence_source="source_type_and_token_family",
            mapping_class=mapping.mapping_class,
            qc_flags=tuple(sorted(set(flags))),
        )

    flags.append("source_type_token_disagreement")
    flags.append("molecule_type_unknown")
    mapping_class = (
        "mixed_token_chemistry"
        if "mixed_token_chemistry" in flags
        else "type_token_disagreement"
    )
    return MoleculeChemistryResult(
        source_value=source_type,
        molecule_type=unmapped_mol,
        chemistry=unmapped_chem,
        evidence_source="",
        mapping_class=mapping_class,
        qc_flags=tuple(sorted(set(flags))),
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
    """Spec-aligned length buckets for the AptaIndex S2 report."""
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


def _normalise_inosine_bases(
    bases: str,
    *,
    molecule_type: str,
    rules: SequenceNormalisationRules,
) -> SequenceNormalisationResult:
    """Normalise parsed bases that include inosine without dropping I.

    The shared alphabet classifier treats ``I`` as invalid and would skip
    T→U. Inosine is a parsed AptaIndex base letter, not unknown syntax.
    """
    qc_flags: list[str] = ["inosine_base"]
    transformations: list[str] = []
    sequence_full = bases
    t_to_u_applied = False
    has_t = "T" in bases
    has_u = "U" in bases
    if has_t and has_u:
        qc_flags.append("mixed_t_u")
        if molecule_type == "RNA":
            qc_flags.append("t_in_reported_rna")
        if molecule_type in {"DNA", "ssDNA"}:
            qc_flags.append("u_in_reported_dna")
    elif molecule_type == "RNA" and has_t:
        sequence_full = bases.replace("T", "U")
        t_to_u_applied = True
        transformations.append("t_to_u")
        qc_flags.append("t_in_reported_rna")
    elif molecule_type in {"DNA", "ssDNA"} and has_u:
        qc_flags.append("u_in_reported_dna")

    detected = detect_known_non_core_motifs(sequence_full, rules)
    if any(motif.name == "t7_promoter_minimal" for motif in detected):
        qc_flags.append("known_promoter_detected")
    for motif in detected:
        if motif.action != "flag_only":
            qc_flags.append("trim_requires_review")
    length_check = validate_core_length(sequence_full, rules)
    qc_flags.extend(length_check.flags)
    if molecule_type == "unknown":
        qc_flags.append("molecule_type_unknown")
    return SequenceNormalisationResult(
        sequence_raw=bases,
        sequence_display_clean=bases,
        sequence_full=sequence_full,
        sequence_core=sequence_full,
        alphabet_as_reported=ALPHABET_CHEMICAL_NOTATION,
        alphabet_after_normalisation=ALPHABET_CHEMICAL_NOTATION,
        molecule_type=molecule_type,
        t_to_u_applied=t_to_u_applied,
        sequence_length_full=len(sequence_full),
        sequence_length_core=len(sequence_full),
        detected_motifs=detected,
        applied_trims=(),
        qc_flags=tuple(sorted(set(qc_flags))),
        transformations=tuple(transformations),
    )


def _linkage_flags(parse: AptaIndexParseResult) -> tuple[str, ...]:
    flags: list[str] = []
    markers = set(parse.internucleotide_linkages)
    if "s" in markers:
        flags.append("linkage_phosphorothioate")
    if markers == {"p", "s"}:
        flags.append("linkage_mixed")
    if parse.terminal_phosphate_marker == "s":
        flags.append("linkage_phosphorothioate")
    return tuple(flags)


def normalise_aptaindex_record(
    s1_record: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: AptaindexNormalisationPolicy,
    rules: SequenceNormalisationRules | None = None,
) -> AptaIndexS2RowResult:
    """Normalise one AptaIndex S1 record into S2 canonical + QC rows."""
    active_rules = rules if rules is not None else load_normalisation_rules()
    if s1_record["record_id"] != source_metadata.get("record_id", ""):
        raise AptaIndexS2Error("canonical and sidecar record_id values must match")

    sequence_raw = s1_record["sequence_raw"]
    source_type = source_metadata.get(policy.source_type_field, "")
    parse = parse_aptaindex_source_sequence(
        sequence_raw, source_type=source_type
    )
    molchem = resolve_aptaindex_molecule_and_chemistry(
        source_type, parse, policy
    )
    qc_flags: list[str] = list(molchem.qc_flags)
    transformations: list[str] = []

    alphabet = ""
    sequence_full = ""
    sequence_core = ""
    length_full = ""
    length_core = ""
    t_to_u = "false"
    five_motifs = ""
    three_motifs = ""
    detected_motif_names = ""
    construct_scope = "unknown"
    trim_status = "not_applicable"
    trim_confidence = TRIM_CONFIDENCE_NA
    detected_motifs: tuple[Any, ...] = ()

    if parse.status == STATUS_MISSING:
        alphabet = ALPHABET_MISSING
        construct_scope = "missing"
        trim_status = "not_applicable"
    elif parse.status == STATUS_NOT_APPLICABLE_PEPTIDE:
        alphabet = ""
        construct_scope = "not_applicable"
        trim_status = "not_applicable"
    elif parse.status == STATUS_UNSUPPORTED:
        alphabet = policy.alphabet_as_reported_nucleic_acid
        construct_scope = "unknown"
        trim_status = "not_applicable"
    else:
        alphabet = policy.alphabet_as_reported_nucleic_acid
        qc_flags.extend(_linkage_flags(parse))
        if parse.mixed_t_u and "mixed_t_u" not in qc_flags:
            qc_flags.append("mixed_t_u")
        if parse.has_i:
            norm = _normalise_inosine_bases(
                parse.base_string,
                molecule_type=molchem.molecule_type,
                rules=active_rules,
            )
        else:
            norm = normalise_sequence(
                parse.base_string,
                molecule_type=molchem.molecule_type,
                trim_plan=None,
                rules=active_rules,
            )
        transformations.extend(norm.transformations)
        # Shared classifier labels parsed bases RNA/DNA_T; AptaIndex raw
        # representation remains chemical notation (plan §7).
        shared_flags = [
            flag
            for flag in norm.qc_flags
            if flag not in {"molecule_type_unknown", "missing_sequence"}
        ]
        qc_flags.extend(shared_flags)
        if molchem.molecule_type == "unknown":
            qc_flags.append("molecule_type_unknown")
        else:
            qc_flags = [flag for flag in qc_flags if flag != "molecule_type_unknown"]

        sequence_full = norm.sequence_full or ""
        sequence_core = sequence_full
        detected_motifs = norm.detected_motifs
        five_motifs, three_motifs = _motif_names_by_side(detected_motifs)
        detected_motif_names = QC_DELIMITER.join(
            sorted({motif.name for motif in detected_motifs})
        )
        t_to_u = "true" if norm.t_to_u_applied else "false"
        length_full = str(len(sequence_full)) if sequence_full else ""
        length_core = str(len(sequence_core)) if sequence_core else ""
        if detected_motifs:
            construct_scope = "unknown"
            trim_status = "constants_suspected_unresolved"
            qc_flags.append("constants_suspected_unresolved")
            qc_flags.append("trim_requires_review")
        else:
            construct_scope = "unknown"
            trim_status = "no_constants_detected"

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
    canonical["molecule_type"] = molchem.molecule_type
    canonical["alphabet_as_reported"] = alphabet
    canonical["t_to_u_applied"] = t_to_u
    canonical["chemistry"] = molchem.chemistry
    canonical["qc_flags"] = format_qc_flags(qc_flags)

    validated = validate_s2_record(canonical, s1_record=s1_record)
    qc = {
        "record_id": validated["record_id"],
        "native_id": validated["native_id"],
        "source_type": source_type,
        "parser_status": parse.status,
        "parser_reason_category": parse.reason_category,
        "mapping_class": molchem.mapping_class,
        "token_family_summary": parse.token_family_summary,
        "has_l_prefix": "true" if parse.has_l_prefix else "false",
        "linkage_summary": parse.linkage_summary,
        "has_terminal_phosphate": (
            "true" if parse.has_terminal_phosphate else "false"
        ),
        "alphabet_as_reported": validated["alphabet_as_reported"],
        "molecule_type": validated["molecule_type"],
        "chemistry": validated["chemistry"],
        "molecule_evidence_source": molchem.evidence_source,
        "t_to_u_applied": validated["t_to_u_applied"],
        "has_t": "true" if parse.has_t else "false",
        "has_u": "true" if parse.has_u else "false",
        "mixed_t_u": "true" if parse.mixed_t_u else "false",
        "sequence_length_full": validated["sequence_length_full"],
        "sequence_length_core": validated["sequence_length_core"],
        "detected_motifs": detected_motif_names,
        "construct_scope": validated["construct_scope"],
        "trim_status": validated["trim_status"],
        "trim_confidence": validated["trim_confidence"],
        "qc_flags": validated["qc_flags"],
    }
    return AptaIndexS2RowResult(
        canonical=validated,
        qc=qc,
        transformations=tuple(transformations),
        parse=parse,
    )


def is_review_candidate(qc_flags: str) -> bool:
    """Return True when any manual-review-relevant flag is present."""
    if not qc_flags:
        return False
    flags = {part for part in qc_flags.split(QC_DELIMITER) if part}
    return bool(flags & REVIEW_RELEVANT_FLAGS)


def update_stats_from_row(stats: AptaIndexS2Stats, row: AptaIndexS2RowResult) -> None:
    """Accumulate aggregate counters from one normalised row."""
    canonical = row.canonical
    qc = row.qc
    flags = [part for part in canonical["qc_flags"].split(QC_DELIMITER) if part]
    parse = row.parse

    parser_status = qc.get("parser_status", "")
    stats.parser_status_counts[parser_status or "(empty)"] = (
        stats.parser_status_counts.get(parser_status or "(empty)", 0) + 1
    )
    reason = qc.get("parser_reason_category", "") or "(empty)"
    stats.parser_reason_counts[reason] = stats.parser_reason_counts.get(reason, 0) + 1
    mapping = qc.get("mapping_class", "") or "(empty)"
    stats.mapping_class_counts[mapping] = (
        stats.mapping_class_counts.get(mapping, 0) + 1
    )

    if parser_status == STATUS_MISSING:
        stats.missing_sequence_rows += 1
    elif parser_status == STATUS_NOT_APPLICABLE_PEPTIDE:
        stats.peptide_rows += 1
    else:
        stats.nonempty_nucleic_acid_rows += 1
        if parser_status == STATUS_SUCCESS:
            stats.successful_parses += 1
        elif parser_status == STATUS_UNSUPPORTED:
            stats.unsupported_nucleic_parses += 1

    if canonical["sequence_length_full"] == "":
        stats.nonempty_sequence_rows += 0
    else:
        stats.nonempty_sequence_rows += 1

    for transformation in row.transformations:
        stats.transformation_counts[transformation] = (
            stats.transformation_counts.get(transformation, 0) + 1
        )

    alphabet = canonical["alphabet_as_reported"] or "(empty)"
    stats.alphabet_counts[alphabet] = stats.alphabet_counts.get(alphabet, 0) + 1

    molecule = canonical["molecule_type"] or "unknown"
    stats.molecule_type_counts[molecule] = (
        stats.molecule_type_counts.get(molecule, 0) + 1
    )
    chemistry = canonical["chemistry"] or "unknown"
    stats.chemistry_counts[chemistry] = stats.chemistry_counts.get(chemistry, 0) + 1

    source_type = qc.get("source_type", "") or "(blank)"
    stats.source_type_counts[source_type] = (
        stats.source_type_counts.get(source_type, 0) + 1
    )

    family = qc.get("token_family_summary", "")
    if parser_status == STATUS_SUCCESS:
        fam_key = family or "(empty)"
        stats.token_family_counts[fam_key] = (
            stats.token_family_counts.get(fam_key, 0) + 1
        )
        cross = f"{source_type} × {fam_key}"
        if qc.get("has_l_prefix") == "true":
            cross = f"{cross} (L)"
        stats.type_token_family_counts[cross] = (
            stats.type_token_family_counts.get(cross, 0) + 1
        )
        if parse is not None:
            if parse.has_t and not parse.has_u:
                stats.parsed_t_only += 1
            elif parse.has_u and not parse.has_t:
                stats.parsed_u_only += 1
            elif parse.has_t and parse.has_u:
                stats.mixed_t_u_count += 1
            else:
                stats.parsed_neither_t_u += 1

    if canonical["t_to_u_applied"] == "true":
        stats.t_to_u_count += 1
    if "l_nucleotide_syntax" in flags:
        stats.l_nucleotide_count += 1
    if "inosine_base" in flags:
        stats.inosine_count += 1
    if "linkage_phosphorothioate" in flags:
        stats.linkage_phosphorothioate_count += 1
    if "linkage_mixed" in flags:
        stats.linkage_mixed_count += 1
    if "source_type_token_disagreement" in flags:
        stats.source_type_disagreement_count += 1
    if "source_type_unsupported" in flags:
        stats.source_type_unsupported_count += 1
    if qc.get("detected_motifs"):
        stats.known_motif_detection_count += 1
    if (
        "trim_requires_review" in flags
        or canonical["trim_status"] == "constants_suspected_unresolved"
    ):
        stats.trim_review_count += 1
    if canonical["trim_status"] == "no_constants_detected":
        stats.no_constants_detected_count += 1
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
            raise AptaIndexS2Error(
                f"proposal side must be five_prime/three_prime: {side}"
            )
        if row.get("applied") != "false":
            raise AptaIndexS2Error("AptaIndex proposals must have applied=false")
        if row.get("proposal_source") == "group_consensus":
            raise AptaIndexS2Error(
                "AptaIndex S2 must not emit group-consensus proposals"
            )
        motif_id = (row.get("motif_id") or "").strip()
        if not motif_id:
            raise AptaIndexS2Error("proposal must have motif_id")
        try:
            length = int(row.get("motif_length") or "0")
        except ValueError as exc:
            raise AptaIndexS2Error("motif_length must be an integer") from exc
        if length <= 0:
            raise AptaIndexS2Error("proposal motif_length must be > 0")


def build_known_motif_proposals(
    rows: Sequence[AptaIndexS2RowResult],
) -> list[dict[str, str]]:
    """Build auditable known-motif proposals without applying trims."""
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

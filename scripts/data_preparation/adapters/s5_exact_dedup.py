"""S5A exact scientific ``(sequence_core, canonical_target_name)`` deduplication.

This milestone collapses exact scientific identities and merges provenance.
It does not cluster sequences, merge S4 target dictionary IDs globally,
resolve NCBI/ENA duplicates, balance targets, or assign partitions.

Scientific identity
-------------------
The governing key is ``(sequence_core, canonical_target_name)``.
``target_dictionary_id`` is retained in provenance and flagged when a group
contains more than one ID; it is not part of the scientific key.

``scientific_identity_id`` is ``S5I_`` plus the SHA-256 hex digest of
``sequence_core + "\\x1f" + canonical_target_name`` encoded as UTF-8. The
digest is order-independent and does not depend on donor selection.

Metadata completeness
---------------------
Completeness is a count of named structured fields that are present and
non-placeholder. It is not row order, column order, text length, or a
count of every populated cell.

Donor hierarchy
---------------
1. highest ``evidence_score`` (S4 ``binding_evidence_score``);
2. highest pre-S5 ``corroboration_count`` (never inferred from duplicate
   row count);
3. highest metadata completeness;
4. alphabetical ``source_db``;
5. alphabetical ``reviewed_relationship_id``.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Collection, Iterable, Mapping, Sequence

from adapters.s4_scientific_common import (
    EVIDENCE_SCORE_BY_LEVEL,
    ScientificProposalError,
    bool_token,
    fill_row,
    split_pipe,
)
from common.corpus_schema import normalise_csv_value

S5ExactDedupError = ScientificProposalError

PRIMARY_ROUTE = "primary_candidate"
SCIENTIFIC_IDENTITY_PREFIX = "S5I_"
SCIENTIFIC_KEY_SEPARATOR = "\x1f"
SEQUENCE_HASH_PREFIX = "S5S_"

PLACEHOLDER_TOKENS: frozenset[str] = frozenset(
    {
        "",
        "unknown",
        "n/a",
        "na",
        "none",
        "null",
        "n.a.",
        "<na>",
        ".",
        "-",
    }
)
UNRESOLVED_TOKENS: frozenset[str] = PLACEHOLDER_TOKENS | frozenset({"unknown"})

# Named completeness bits. Order is the documented definition, not a ranking
# of scientific importance. Presence is a boolean; string length is ignored.
METADATA_COMPLETENESS_FIELDS: tuple[str, ...] = (
    "canonical_affinity",
    "affinity_type",
    "doi",
    "pubmed_id",
    "accession",
    "target_uniprot",
    "target_pfam",
    "target_family",
    "pdb_id",
    "chemistry",
    "molecule_type",
    "construct_scope",
    "trim_status",
    "publication",
)

REDISTRIBUTION_RANK: dict[str, int] = {
    "permissive": 0,
    "unknown": 1,
    "restricted": 2,
    "prohibited": 3,
}

COMBINED_EXTRA_FIELDS: tuple[str, ...] = (
    "source_dataset",
    "redistribution_status",
    "independently_attested_by_permissive_source",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "detected_constant_5p",
    "detected_constant_3p",
    "sequence_raw",
    "sequence_length_full",
    "sequence_length_core",
    "alphabet_as_reported",
    "t_to_u_applied",
    "pdb_id",
    "experiment_group_id",
    "near_duplicate_family_id",
    "qc_flags",
    "notes",
    "accessions",
    "ena_effective_near_duplicate_family_id",
    "ena_effective_near_duplicate_family_size",
    "utexas_post_selex_modifications",
    "aptamerbase_has_modification_details",
    "rdf_has_modified_nucleic_acid",
    "aptadb_pdb_cross_reference",
    "aptadb_uniprot_id",
    "contributing_sources",
    "contributing_datasets",
    "corroboration_count",
)

CONFLICT_FLAG_VOCAB: tuple[str, ...] = (
    "multiple_target_dictionary_ids",
    "multiple_affinity_measurements",
    "conflicting_affinity_values",
    "multiple_chemistries",
    "multiple_evidence_levels",
    "multiple_sequence_full",
    "multiple_construct_scopes",
    "multiple_trim_statuses",
)

DEFAULT_OVERLAP_SOURCES: tuple[str, ...] = (
    "aptabase",
    "aptadb",
    "aptaindex",
    "aptamerbase",
    "ena",
    "ncbi_nuc",
    "riboaptamer",
    "utexas",
)

CORPUS_DEDUP_COLUMNS: tuple[str, ...] = (
    "scientific_identity_id",
    "record_id",
    "donor_reviewed_relationship_id",
    "donor_rationale",
    "member_count",
    "metadata_completeness_score",
    "conflict_flags",
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "sequence_length_full",
    "sequence_length_core",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "detected_constant_5p",
    "detected_constant_3p",
    "molecule_type",
    "alphabet_as_reported",
    "t_to_u_applied",
    "chemistry",
    "contributing_chemistries",
    "target_name_raw",
    "target_name",
    "canonical_target_name",
    "target_dictionary_id",
    "contributing_target_dictionary_ids",
    "target_uniprot",
    "target_type",
    "target_type_source",
    "target_family",
    "target_pfam",
    "target_interpro",
    "target_region_or_fragment",
    "pdb_id",
    "binding_evidence_type",
    "binding_evidence_score",
    "evidence_level",
    "evidence_score",
    "evidence_type",
    "affinity_value",
    "affinity_unit",
    "affinity_type",
    "canonical_affinity_value",
    "canonical_affinity_unit",
    "canonical_affinity_type",
    "affinity_value_molar",
    "affinity_unit_normalized",
    "affinity_qualifier",
    "affinity_value_raw",
    "source_db",
    "source_dataset",
    "contributing_sources",
    "contributing_datasets",
    "corroboration_count",
    "contributing_record_ids",
    "contributing_reviewed_relationship_ids",
    "contributing_native_ids",
    "contributing_publications",
    "contributing_dois",
    "contributing_pubmed_ids",
    "contributing_accessions",
    "redistribution_status",
    "independently_attested_by_permissive_source",
    "native_id",
    "publication",
    "doi",
    "pubmed_id",
    "accession",
    "experiment_group_id",
    "near_duplicate_family_id",
    "cluster_id",
    "is_cluster_representative",
    "partition",
    "qc_flags",
    "notes",
)

MEMBERSHIP_COLUMNS: tuple[str, ...] = (
    "scientific_identity_id",
    "is_donor",
    "donor_reviewed_relationship_id",
    "donor_rationale",
    "metadata_completeness_score",
    "reviewed_relationship_id",
    "record_id",
    "source_db",
    "source_dataset",
    "native_id",
    "relationship_index",
    "target_dictionary_id",
    "canonical_target_name",
    "raw_target",
    "target_type",
    "target_family",
    "target_uniprot",
    "target_pfam",
    "target_interpro",
    "target_region_or_fragment",
    "evidence_level",
    "evidence_score",
    "evidence_type",
    "affinity_value_raw",
    "affinity_unit_raw",
    "affinity_type",
    "affinity_value_molar",
    "affinity_unit_normalized",
    "affinity_qualifier",
    "canonical_affinity_value",
    "canonical_affinity_unit",
    "canonical_affinity_type",
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "sequence_length_full",
    "sequence_length_core",
    "molecule_type",
    "chemistry",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "detected_constant_5p",
    "detected_constant_3p",
    "alphabet_as_reported",
    "t_to_u_applied",
    "publication",
    "doi",
    "pubmed_id",
    "accession",
    "accessions",
    "pdb_id",
    "redistribution_status",
    "pre_s5_corroboration_count",
    "experiment_group_id",
    "near_duplicate_family_id",
    "ena_effective_near_duplicate_family_id",
    "ena_effective_near_duplicate_family_size",
    "utexas_post_selex_modifications",
    "aptamerbase_has_modification_details",
    "rdf_has_modified_nucleic_acid",
    "aptadb_pdb_cross_reference",
    "aptadb_uniprot_id",
    "qc_flags",
    "notes",
    "s4_route",
    "s4_route_reason",
)

GROUP_COLUMNS: tuple[str, ...] = (
    "scientific_identity_id",
    "member_count",
    "distinct_source_count",
    "contributing_sources",
    "donor_source_db",
    "donor_reviewed_relationship_id",
    "evidence_score_min",
    "evidence_score_max",
    "distinct_target_dictionary_id_count",
    "contributing_target_dictionary_ids",
    "distinct_chemistry_count",
    "contributing_chemistries",
    "affinity_observation_count",
    "distinct_canonical_affinity_count",
    "distinct_sequence_full_count",
    "distinct_construct_scope_count",
    "distinct_trim_status_count",
    "conflict_flags",
)

DICTIONARY_CONFLICT_COLUMNS: tuple[str, ...] = (
    "scientific_identity_id",
    "canonical_target_name",
    "contributing_target_dictionary_ids",
    "contributing_sources",
    "member_count",
    "donor_target_dictionary_id",
    "donor_reviewed_relationship_id",
)

MULTI_TARGET_COLUMNS: tuple[str, ...] = (
    "sequence_core_sha256",
    "sequence_length_core",
    "n_canonical_targets",
    "canonical_target_names",
    "n_target_dictionary_ids",
    "target_dictionary_ids",
    "n_scientific_identities",
    "n_relationship_rows",
    "contributing_sources",
)

OVERLAP_MATRIX_COLUMNS: tuple[str, ...] = (
    "source_a",
    "source_b",
    "n_shared_scientific_identities",
    "n_shared_duplicate_groups",
)


def _blank(value: Any) -> str:
    return normalise_csv_value(value).strip()


def _token(value: Any) -> str:
    return " ".join(_blank(value).casefold().split())


def _is_placeholder(value: Any) -> bool:
    return _token(value) in PLACEHOLDER_TOKENS


def _is_unresolved(value: Any) -> bool:
    return _token(value) in UNRESOLVED_TOKENS


def _present(value: Any) -> bool:
    return not _is_placeholder(value)


def _present_resolved(value: Any) -> bool:
    return not _is_unresolved(value)


def join_sorted_unique(values: Iterable[Any], *, sep: str = "|") -> str:
    unique = {_blank(value) for value in values if _blank(value)}
    return sep.join(sorted(unique))


def scientific_key(sequence_core: str, canonical_target_name: str) -> tuple[str, str]:
    core = _blank(sequence_core)
    name = _blank(canonical_target_name)
    if not core:
        raise S5ExactDedupError("sequence_core is required for S5A scientific identity")
    if not name:
        raise S5ExactDedupError(
            "canonical_target_name is required for S5A scientific identity"
        )
    return core, name


def scientific_identity_id(sequence_core: str, canonical_target_name: str) -> str:
    """Return a stable, order-independent scientific identity ID."""
    core, name = scientific_key(sequence_core, canonical_target_name)
    payload = f"{core}{SCIENTIFIC_KEY_SEPARATOR}{name}".encode("utf-8")
    return SCIENTIFIC_IDENTITY_PREFIX + hashlib.sha256(payload).hexdigest()


def sequence_core_sha256(sequence_core: str) -> str:
    core = _blank(sequence_core)
    return SEQUENCE_HASH_PREFIX + hashlib.sha256(core.encode("utf-8")).hexdigest()


def _evidence_score(row: Mapping[str, str]) -> int:
    raw = _blank(row.get("evidence_score") or row.get("binding_evidence_score"))
    if raw:
        try:
            return int(raw)
        except ValueError as exc:
            raise S5ExactDedupError(
                f"non-integer evidence_score {raw!r} on "
                f"{row.get('reviewed_relationship_id')}"
            ) from exc
    level = _blank(row.get("evidence_level"))
    if level in EVIDENCE_SCORE_BY_LEVEL:
        return EVIDENCE_SCORE_BY_LEVEL[level]
    return 0


def _pre_s5_corroboration_count(row: Mapping[str, str]) -> int:
    raw = _blank(
        row.get("pre_s5_corroboration_count") or row.get("corroboration_count") or "1"
    )
    try:
        value = int(raw)
    except ValueError as exc:
        raise S5ExactDedupError(
            f"non-integer pre-S5 corroboration_count {raw!r} on "
            f"{row.get('reviewed_relationship_id')}"
        ) from exc
    if value < 1:
        raise S5ExactDedupError(
            f"pre-S5 corroboration_count must be >= 1; got {value}"
        )
    return value


def _canonical_molar(row: Mapping[str, str]) -> str:
    """Scalar canonical molar used for donor completeness and conflict flags.

    Member ``affinity_value_molar`` observations remain in the membership
    table even when this canonical field is blank.
    """
    return _blank(row.get("canonical_affinity_value"))


def _affinity_type_value(row: Mapping[str, str]) -> str:
    return _blank(row.get("canonical_affinity_type") or row.get("affinity_type"))


def _accession_value(row: Mapping[str, str]) -> str:
    return _blank(row.get("accession") or row.get("accessions"))


def metadata_completeness_bits(row: Mapping[str, str]) -> dict[str, bool]:
    """Return the frozen named completeness bits for one relationship."""
    return {
        "canonical_affinity": _present(_canonical_molar(row)),
        "affinity_type": _present(_affinity_type_value(row)),
        "doi": _present(row.get("doi")),
        "pubmed_id": _present(row.get("pubmed_id")),
        "accession": _present(_accession_value(row)),
        "target_uniprot": _present(row.get("target_uniprot")),
        "target_pfam": _present(row.get("target_pfam")),
        "target_family": _present_resolved(row.get("target_family")),
        "pdb_id": _present(row.get("pdb_id")),
        "chemistry": _present_resolved(row.get("chemistry")),
        "molecule_type": _present_resolved(row.get("molecule_type")),
        "construct_scope": _present_resolved(row.get("construct_scope")),
        "trim_status": _present(row.get("trim_status")),
        "publication": _present(row.get("publication")),
    }


def metadata_completeness_score(row: Mapping[str, str]) -> int:
    bits = metadata_completeness_bits(row)
    missing = [name for name in METADATA_COMPLETENESS_FIELDS if name not in bits]
    extra = [name for name in bits if name not in METADATA_COMPLETENESS_FIELDS]
    if missing or extra:
        raise S5ExactDedupError(
            "completeness bit names drifted from METADATA_COMPLETENESS_FIELDS"
        )
    return sum(1 for name in METADATA_COMPLETENESS_FIELDS if bits[name])


def donor_sort_key(row: Mapping[str, str]) -> tuple[int, int, int, str, str]:
    """Ascending sort key; the last tuple is the donor.

    Evidence, pre-S5 corroboration, and completeness are negated so a normal
    ascending sort prefers higher values. The final ``reviewed_relationship_id``
    tie-break is alphabetical and therefore independent of input row order.
    """
    return (
        -_evidence_score(row),
        -_pre_s5_corroboration_count(row),
        -metadata_completeness_score(row),
        _blank(row.get("source_db")),
        _blank(row.get("reviewed_relationship_id")),
    )


def select_donor(members: Sequence[Mapping[str, str]]) -> dict[str, str]:
    if not members:
        raise S5ExactDedupError("cannot select a donor from an empty group")
    ordered = sorted((dict(row) for row in members), key=donor_sort_key)
    return ordered[0]


def donor_rationale(row: Mapping[str, str]) -> str:
    return (
        f"evidence_score={_evidence_score(row)}; "
        f"pre_s5_corroboration_count={_pre_s5_corroboration_count(row)}; "
        f"metadata_completeness={metadata_completeness_score(row)}; "
        f"source_db={_blank(row.get('source_db'))}; "
        f"reviewed_relationship_id={_blank(row.get('reviewed_relationship_id'))}"
    )


def _distinct_nonempty(members: Sequence[Mapping[str, str]], field: str) -> list[str]:
    return sorted({_blank(row.get(field)) for row in members if _blank(row.get(field))})


def _molar_identity(value: str) -> str | Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return value


def derive_conflict_flags(members: Sequence[Mapping[str, str]]) -> list[str]:
    flags: list[str] = []
    dictionary_ids = _distinct_nonempty(members, "target_dictionary_id")
    if len(dictionary_ids) > 1:
        flags.append("multiple_target_dictionary_ids")
    molars = [_canonical_molar(row) for row in members if _canonical_molar(row)]
    if len(molars) > 1:
        flags.append("multiple_affinity_measurements")
    molar_identities = {_molar_identity(value) for value in molars}
    if len(molar_identities) > 1:
        flags.append("conflicting_affinity_values")
    chemistries = [
        _blank(row.get("chemistry"))
        for row in members
        if _present_resolved(row.get("chemistry"))
    ]
    if len(set(chemistries)) > 1:
        flags.append("multiple_chemistries")
    levels = _distinct_nonempty(members, "evidence_level")
    if len(levels) > 1:
        flags.append("multiple_evidence_levels")
    if len(_distinct_nonempty(members, "sequence_full")) > 1:
        flags.append("multiple_sequence_full")
    if len(_distinct_nonempty(members, "construct_scope")) > 1:
        flags.append("multiple_construct_scopes")
    if len(_distinct_nonempty(members, "trim_status")) > 1:
        flags.append("multiple_trim_statuses")
    return [flag for flag in CONFLICT_FLAG_VOCAB if flag in flags]


def merged_redistribution_status(members: Sequence[Mapping[str, str]]) -> str:
    statuses = []
    for row in members:
        status = _token(row.get("redistribution_status")) or "unknown"
        if status not in REDISTRIBUTION_RANK:
            status = "unknown"
        statuses.append(status)
    if not statuses:
        return "unknown"
    return min(statuses, key=lambda item: REDISTRIBUTION_RANK[item])


def independently_attested_by_permissive_source(
    members: Sequence[Mapping[str, str]],
) -> bool:
    return any(_token(row.get("redistribution_status")) == "permissive" for row in members)


def merge_provenance(members: Sequence[Mapping[str, str]]) -> dict[str, str]:
    """Merge provenance from remaining members. Does not select a donor."""
    sources = join_sorted_unique(row.get("source_db") for row in members)
    datasets = join_sorted_unique(row.get("source_dataset") for row in members)
    source_list = split_pipe(sources)
    return {
        "contributing_sources": sources,
        "contributing_datasets": datasets,
        "corroboration_count": str(len(source_list)),
        "contributing_target_dictionary_ids": join_sorted_unique(
            row.get("target_dictionary_id") for row in members
        ),
        "contributing_chemistries": join_sorted_unique(
            row.get("chemistry")
            for row in members
            if _present_resolved(row.get("chemistry"))
        ),
        "contributing_record_ids": join_sorted_unique(
            row.get("record_id") for row in members
        ),
        "contributing_reviewed_relationship_ids": join_sorted_unique(
            row.get("reviewed_relationship_id") for row in members
        ),
        "contributing_native_ids": join_sorted_unique(
            row.get("native_id") for row in members
        ),
        "contributing_publications": join_sorted_unique(
            row.get("publication") for row in members if _present(row.get("publication"))
        ),
        "contributing_dois": join_sorted_unique(row.get("doi") for row in members),
        "contributing_pubmed_ids": join_sorted_unique(
            row.get("pubmed_id") for row in members
        ),
        "contributing_accessions": join_sorted_unique(
            [_accession_value(row) for row in members]
        ),
        "redistribution_status": merged_redistribution_status(members),
        "independently_attested_by_permissive_source": bool_token(
            independently_attested_by_permissive_source(members)
        ),
        "member_count": str(len(members)),
    }


def membership_after_excluding_sources(
    membership_rows: Sequence[Mapping[str, str]],
    excluded_sources: Collection[str],
) -> list[dict[str, str]]:
    """Keep membership rows whose source independently attests the identity."""
    excluded = { _blank(source) for source in excluded_sources }
    return [
        dict(row)
        for row in membership_rows
        if _blank(row.get("source_db")) not in excluded
    ]


def identities_remaining_after_excluding_sources(
    membership_rows: Sequence[Mapping[str, str]],
    excluded_sources: Collection[str],
) -> dict[str, dict[str, str]]:
    """Re-merge provenance for identities that still have an attestor."""
    remaining = membership_after_excluding_sources(membership_rows, excluded_sources)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in remaining:
        identity = _blank(row.get("scientific_identity_id"))
        if not identity:
            raise S5ExactDedupError("membership row missing scientific_identity_id")
        grouped[identity].append(row)
    return {
        identity: merge_provenance(members)
        for identity, members in sorted(grouped.items())
    }


def filter_s5a_input(
    relationship_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Return primary-candidate relationships only.

    Record-level ``s4_record_outcome`` is ignored on purpose. A source record
    may contribute a parked relationship and a valid primary relationship;
    only the primary relationship enters S5A.
    """
    selected: list[dict[str, str]] = []
    seen_rel: set[str] = set()
    for row in relationship_rows:
        if _blank(row.get("s4_route")) != PRIMARY_ROUTE:
            continue
        rel_id = _blank(row.get("reviewed_relationship_id"))
        if not rel_id:
            raise S5ExactDedupError("primary relationship missing reviewed_relationship_id")
        if rel_id in seen_rel:
            raise S5ExactDedupError(
                f"duplicate reviewed_relationship_id in S5A input: {rel_id}"
            )
        seen_rel.add(rel_id)
        selected.append(dict(row))
    return selected


def enrich_with_combined_extras(
    relationship_rows: Sequence[Mapping[str, str]],
    combined_by_record_id: Mapping[str, Mapping[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Join construct/trim/redistribution extras without altering S4 science."""
    extras_index = combined_by_record_id or {}
    enriched: list[dict[str, str]] = []
    for row in relationship_rows:
        out = dict(row)
        record_id = _blank(row.get("record_id"))
        extras = extras_index.get(record_id, {})
        for field_name in COMBINED_EXTRA_FIELDS:
            if field_name in {"contributing_sources", "contributing_datasets", "corroboration_count"}:
                continue
            if not _blank(out.get(field_name)):
                out[field_name] = _blank(extras.get(field_name))
        if not _blank(out.get("source_dataset")):
            out["source_dataset"] = _blank(extras.get("source_dataset"))
        if not _blank(out.get("redistribution_status")):
            out["redistribution_status"] = _blank(extras.get("redistribution_status"))
        out["pre_s5_corroboration_count"] = _blank(
            extras.get("corroboration_count")
            or out.get("pre_s5_corroboration_count")
            or out.get("corroboration_count")
            or "1"
        )
        out["pre_s5_contributing_sources"] = _blank(
            extras.get("contributing_sources") or out.get("source_db")
        )
        if not _blank(out.get("accessions")):
            out["accessions"] = _blank(extras.get("accessions"))
        for extra_name in (
            "ena_effective_near_duplicate_family_id",
            "ena_effective_near_duplicate_family_size",
            "utexas_post_selex_modifications",
            "aptamerbase_has_modification_details",
            "rdf_has_modified_nucleic_acid",
            "aptadb_pdb_cross_reference",
            "aptadb_uniprot_id",
            "experiment_group_id",
            "near_duplicate_family_id",
            "sequence_raw",
            "sequence_length_full",
            "sequence_length_core",
            "construct_scope",
            "trim_status",
            "trim_confidence",
            "detected_constant_5p",
            "detected_constant_3p",
            "alphabet_as_reported",
            "t_to_u_applied",
            "pdb_id",
            "qc_flags",
            "notes",
        ):
            if not _blank(out.get(extra_name)):
                out[extra_name] = _blank(extras.get(extra_name))
        if not _blank(out.get("target_name_raw")):
            out["target_name_raw"] = _blank(
                extras.get("target_name_raw") or out.get("raw_target")
            )
        enriched.append(out)
    return enriched


def _assert_no_identity_collisions(groups: Mapping[str, tuple[str, str]]) -> None:
    inverse: dict[tuple[str, str], str] = {}
    for identity, key in groups.items():
        if key in inverse and inverse[key] != identity:
            raise S5ExactDedupError(
                "scientific_identity_id collision between distinct keys"
            )
        inverse[key] = identity
    if len(groups) != len(set(groups)):
        raise S5ExactDedupError("duplicate scientific_identity_id values")


def _donor_corpus_row(
    donor: Mapping[str, str],
    members: Sequence[Mapping[str, str]],
    *,
    identity: str,
    provenance: Mapping[str, str],
    flags: Sequence[str],
) -> dict[str, str]:
    molar = _canonical_molar(donor)
    affinity_type = _affinity_type_value(donor)
    evidence_type = _blank(donor.get("evidence_type") or donor.get("binding_evidence_type"))
    evidence_score = str(_evidence_score(donor))
    values = {
        "scientific_identity_id": identity,
        "record_id": _blank(donor.get("record_id")),
        "donor_reviewed_relationship_id": _blank(donor.get("reviewed_relationship_id")),
        "donor_rationale": donor_rationale(donor),
        "metadata_completeness_score": str(metadata_completeness_score(donor)),
        "conflict_flags": join_sorted_unique(flags),
        "sequence_raw": _blank(donor.get("sequence_raw")),
        "sequence_full": _blank(donor.get("sequence_full")),
        "sequence_core": _blank(donor.get("sequence_core")),
        "sequence_length_full": _blank(donor.get("sequence_length_full")),
        "sequence_length_core": _blank(donor.get("sequence_length_core")),
        "construct_scope": _blank(donor.get("construct_scope")),
        "trim_status": _blank(donor.get("trim_status")),
        "trim_confidence": _blank(donor.get("trim_confidence")),
        "detected_constant_5p": _blank(donor.get("detected_constant_5p")),
        "detected_constant_3p": _blank(donor.get("detected_constant_3p")),
        "molecule_type": _blank(donor.get("molecule_type")),
        "alphabet_as_reported": _blank(donor.get("alphabet_as_reported")),
        "t_to_u_applied": _blank(donor.get("t_to_u_applied")),
        "chemistry": _blank(donor.get("chemistry")),
        "target_name_raw": _blank(donor.get("target_name_raw") or donor.get("raw_target")),
        "target_name": _blank(donor.get("canonical_target_name")),
        "canonical_target_name": _blank(donor.get("canonical_target_name")),
        "target_dictionary_id": _blank(donor.get("target_dictionary_id")),
        "target_uniprot": _blank(donor.get("target_uniprot")),
        "target_type": _blank(donor.get("target_type")),
        "target_type_source": _blank(donor.get("target_type_source")),
        "target_family": _blank(donor.get("target_family")),
        "target_pfam": _blank(donor.get("target_pfam")),
        "target_interpro": _blank(donor.get("target_interpro")),
        "target_region_or_fragment": _blank(donor.get("target_region_or_fragment")),
        "pdb_id": _blank(donor.get("pdb_id")),
        "binding_evidence_type": evidence_type,
        "binding_evidence_score": evidence_score,
        "evidence_level": _blank(donor.get("evidence_level")),
        "evidence_score": evidence_score,
        "evidence_type": evidence_type,
        "affinity_value": molar,
        "affinity_unit": _blank(
            donor.get("canonical_affinity_unit") or donor.get("affinity_unit_normalized")
        ),
        "affinity_type": affinity_type,
        "canonical_affinity_value": _blank(donor.get("canonical_affinity_value")),
        "canonical_affinity_unit": _blank(donor.get("canonical_affinity_unit")),
        "canonical_affinity_type": _blank(donor.get("canonical_affinity_type")),
        "affinity_value_molar": _blank(donor.get("affinity_value_molar")),
        "affinity_unit_normalized": _blank(donor.get("affinity_unit_normalized")),
        "affinity_qualifier": _blank(donor.get("affinity_qualifier")),
        "affinity_value_raw": _blank(donor.get("affinity_value_raw")),
        "source_db": _blank(donor.get("source_db")),
        "source_dataset": _blank(donor.get("source_dataset")),
        "native_id": _blank(donor.get("native_id")),
        "publication": _blank(donor.get("publication")),
        "doi": _blank(donor.get("doi")),
        "pubmed_id": _blank(donor.get("pubmed_id")),
        "accession": _blank(donor.get("accession")),
        "experiment_group_id": _blank(donor.get("experiment_group_id")),
        "near_duplicate_family_id": _blank(donor.get("near_duplicate_family_id")),
        "cluster_id": "",
        "is_cluster_representative": "",
        "partition": "",
        "qc_flags": _blank(donor.get("qc_flags")),
        "notes": _blank(donor.get("notes")),
        **provenance,
    }
    return fill_row(CORPUS_DEDUP_COLUMNS, values)


def _membership_row(
    member: Mapping[str, str],
    *,
    identity: str,
    donor: Mapping[str, str],
    flags: Sequence[str],
) -> dict[str, str]:
    del flags
    values = {
        "scientific_identity_id": identity,
        "is_donor": bool_token(
            _blank(member.get("reviewed_relationship_id"))
            == _blank(donor.get("reviewed_relationship_id"))
        ),
        "donor_reviewed_relationship_id": _blank(donor.get("reviewed_relationship_id")),
        "donor_rationale": donor_rationale(donor),
        "metadata_completeness_score": str(metadata_completeness_score(member)),
        "pre_s5_corroboration_count": str(_pre_s5_corroboration_count(member)),
    }
    for column in MEMBERSHIP_COLUMNS:
        if column in values:
            continue
        values[column] = _blank(member.get(column))
    return fill_row(MEMBERSHIP_COLUMNS, values)


def _group_row(
    members: Sequence[Mapping[str, str]],
    *,
    identity: str,
    donor: Mapping[str, str],
    provenance: Mapping[str, str],
    flags: Sequence[str],
) -> dict[str, str]:
    scores = [_evidence_score(row) for row in members]
    molars = [_canonical_molar(row) for row in members if _canonical_molar(row)]
    values = {
        "scientific_identity_id": identity,
        "member_count": str(len(members)),
        "distinct_source_count": provenance["corroboration_count"],
        "contributing_sources": provenance["contributing_sources"],
        "donor_source_db": _blank(donor.get("source_db")),
        "donor_reviewed_relationship_id": _blank(donor.get("reviewed_relationship_id")),
        "evidence_score_min": str(min(scores)),
        "evidence_score_max": str(max(scores)),
        "distinct_target_dictionary_id_count": str(
            len(split_pipe(provenance["contributing_target_dictionary_ids"]))
        ),
        "contributing_target_dictionary_ids": provenance[
            "contributing_target_dictionary_ids"
        ],
        "distinct_chemistry_count": str(
            len(split_pipe(provenance["contributing_chemistries"]))
        ),
        "contributing_chemistries": provenance["contributing_chemistries"],
        "affinity_observation_count": str(len(molars)),
        "distinct_canonical_affinity_count": str(len({_molar_identity(v) for v in molars})),
        "distinct_sequence_full_count": str(len(_distinct_nonempty(members, "sequence_full"))),
        "distinct_construct_scope_count": str(
            len(_distinct_nonempty(members, "construct_scope"))
        ),
        "distinct_trim_status_count": str(
            len(_distinct_nonempty(members, "trim_status"))
        ),
        "conflict_flags": join_sorted_unique(flags),
    }
    return fill_row(GROUP_COLUMNS, values)


def _multi_target_rows(input_rows: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    by_core: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in input_rows:
        by_core[_blank(row.get("sequence_core"))].append(row)
    reports: list[dict[str, str]] = []
    for core, rows in by_core.items():
        names = join_sorted_unique(row.get("canonical_target_name") for row in rows)
        ids = join_sorted_unique(row.get("target_dictionary_id") for row in rows)
        name_list = split_pipe(names)
        id_list = split_pipe(ids)
        if len(name_list) <= 1:
            continue
        identities = {
            scientific_identity_id(
                _blank(row.get("sequence_core")),
                _blank(row.get("canonical_target_name")),
            )
            for row in rows
        }
        reports.append(
            fill_row(
                MULTI_TARGET_COLUMNS,
                {
                    "sequence_core_sha256": sequence_core_sha256(core),
                    "sequence_length_core": str(len(core)),
                    "n_canonical_targets": str(len(name_list)),
                    "canonical_target_names": names,
                    "n_target_dictionary_ids": str(len(id_list)),
                    "target_dictionary_ids": ids,
                    "n_scientific_identities": str(len(identities)),
                    "n_relationship_rows": str(len(rows)),
                    "contributing_sources": join_sorted_unique(
                        row.get("source_db") for row in rows
                    ),
                },
            )
        )
    reports.sort(key=lambda row: (row["sequence_core_sha256"], row["canonical_target_names"]))
    return reports


def _overlap_matrix(
    corpus_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    *,
    source_keys: Sequence[str],
) -> list[dict[str, str]]:
    identity_sources: dict[str, set[str]] = {}
    for row in corpus_rows:
        identity_sources[_blank(row.get("scientific_identity_id"))] = set(
            split_pipe(row.get("contributing_sources") or "")
        )
    duplicate_sources: dict[str, set[str]] = {}
    for row in group_rows:
        duplicate_sources[_blank(row.get("scientific_identity_id"))] = set(
            split_pipe(row.get("contributing_sources") or "")
        )
    sources = list(source_keys)
    matrix: list[dict[str, str]] = []
    for source_a in sources:
        for source_b in sources:
            shared_identities = sum(
                1
                for members in identity_sources.values()
                if source_a in members and source_b in members
            )
            shared_groups = sum(
                1
                for members in duplicate_sources.values()
                if source_a in members and source_b in members
            )
            matrix.append(
                fill_row(
                    OVERLAP_MATRIX_COLUMNS,
                    {
                        "source_a": source_a,
                        "source_b": source_b,
                        "n_shared_scientific_identities": str(shared_identities),
                        "n_shared_duplicate_groups": str(shared_groups),
                    },
                )
            )
    return matrix


def _count_distribution(values: Iterable[str]) -> dict[str, int]:
    return dict(Counter(value for value in values if value))


@dataclass
class ExactDedupResult:
    input_rows: list[dict[str, str]]
    corpus_dedup: list[dict[str, str]]
    membership: list[dict[str, str]]
    duplicate_groups: list[dict[str, str]]
    dictionary_id_conflicts: list[dict[str, str]]
    multi_target_sequences: list[dict[str, str]]
    overlap_matrix: list[dict[str, str]]
    diagnostics: dict[str, Any] = field(default_factory=dict)


def exact_deduplicate(
    relationship_rows: Sequence[Mapping[str, str]],
    *,
    combined_by_record_id: Mapping[str, Mapping[str, str]] | None = None,
    overlap_source_keys: Sequence[str] | None = None,
) -> ExactDedupResult:
    """Collapse exact scientific identities and merge provenance."""
    primary = filter_s5a_input(relationship_rows)
    enriched = enrich_with_combined_extras(primary, combined_by_record_id)
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    identity_for_key: dict[str, tuple[str, str]] = {}
    for row in enriched:
        key = scientific_key(
            row.get("sequence_core", ""),
            row.get("canonical_target_name", ""),
        )
        identity = scientific_identity_id(*key)
        previous = identity_for_key.get(identity)
        if previous is not None and previous != key:
            raise S5ExactDedupError(
                "SHA-256 collision in scientific_identity_id generation"
            )
        identity_for_key[identity] = key
        grouped[key].append(row)
    _assert_no_identity_collisions(identity_for_key)

    corpus: list[dict[str, str]] = []
    membership: list[dict[str, str]] = []
    groups_out: list[dict[str, str]] = []
    dict_conflicts: list[dict[str, str]] = []

    for key in sorted(grouped):
        members = sorted(
            grouped[key],
            key=lambda row: _blank(row.get("reviewed_relationship_id")),
        )
        identity = scientific_identity_id(*key)
        donor = select_donor(members)
        provenance = merge_provenance(members)
        flags = derive_conflict_flags(members)
        corpus.append(
            _donor_corpus_row(
                donor,
                members,
                identity=identity,
                provenance=provenance,
                flags=flags,
            )
        )
        for member in members:
            membership.append(
                _membership_row(
                    member,
                    identity=identity,
                    donor=donor,
                    flags=flags,
                )
            )
        if len(members) > 1:
            groups_out.append(
                _group_row(
                    members,
                    identity=identity,
                    donor=donor,
                    provenance=provenance,
                    flags=flags,
                )
            )
        if "multiple_target_dictionary_ids" in flags:
            dict_conflicts.append(
                fill_row(
                    DICTIONARY_CONFLICT_COLUMNS,
                    {
                        "scientific_identity_id": identity,
                        "canonical_target_name": key[1],
                        "contributing_target_dictionary_ids": provenance[
                            "contributing_target_dictionary_ids"
                        ],
                        "contributing_sources": provenance["contributing_sources"],
                        "member_count": str(len(members)),
                        "donor_target_dictionary_id": _blank(
                            donor.get("target_dictionary_id")
                        ),
                        "donor_reviewed_relationship_id": _blank(
                            donor.get("reviewed_relationship_id")
                        ),
                    },
                )
            )

    corpus.sort(key=lambda row: row["scientific_identity_id"])
    membership.sort(
        key=lambda row: (
            row["scientific_identity_id"],
            row["reviewed_relationship_id"],
        )
    )
    groups_out.sort(key=lambda row: row["scientific_identity_id"])
    dict_conflicts.sort(key=lambda row: row["scientific_identity_id"])

    duplicate_member_rows = sum(int(row["member_count"]) for row in groups_out)
    duplicate_excess = duplicate_member_rows - len(groups_out)
    source_keys = tuple(overlap_source_keys) if overlap_source_keys else DEFAULT_OVERLAP_SOURCES
    observed_sources = sorted({_blank(row.get("source_db")) for row in enriched if _blank(row.get("source_db"))})
    overlap_sources = list(source_keys)
    for source in observed_sources:
        if source not in overlap_sources:
            overlap_sources.append(source)

    cores_by_name: dict[str, set[str]] = defaultdict(set)
    cores_by_id: dict[str, set[str]] = defaultdict(set)
    for row in enriched:
        core = _blank(row.get("sequence_core"))
        cores_by_name[core].add(_blank(row.get("canonical_target_name")))
        cores_by_id[core].add(_blank(row.get("target_dictionary_id")))
    multi_name_cores = {core for core, names in cores_by_name.items() if len(names) > 1}
    multi_name_or_id_cores = {
        core
        for core in cores_by_name
        if len(cores_by_name[core]) > 1 or len(cores_by_id[core]) > 1
    }
    record_counts = Counter(_blank(row.get("record_id")) for row in enriched)
    multi_record_ids = {record_id: n for record_id, n in record_counts.items() if n > 1}

    diagnostics = {
        "n_input_relationships": len(enriched),
        "n_distinct_source_record_ids": len(record_counts),
        "n_distinct_sequence_core": len(cores_by_name),
        "n_scientific_identities": len(corpus),
        "n_exact_duplicate_groups": len(groups_out),
        "n_rows_in_duplicate_groups": duplicate_member_rows,
        "n_duplicate_excess": duplicate_excess,
        "n_membership_rows": len(membership),
        "n_target_dictionary_id_conflict_groups": len(dict_conflicts),
        "n_groups_multiple_chemistries": sum(
            1
            for row in groups_out
            if "multiple_chemistries" in split_pipe(row["conflict_flags"])
        ),
        "n_groups_conflicting_affinity_values": sum(
            1
            for row in groups_out
            if "conflicting_affinity_values" in split_pipe(row["conflict_flags"])
        ),
        "n_groups_multiple_affinity_measurements": sum(
            1
            for row in groups_out
            if "multiple_affinity_measurements" in split_pipe(row["conflict_flags"])
        ),
        "n_groups_multiple_evidence_levels": sum(
            1
            for row in groups_out
            if "multiple_evidence_levels" in split_pipe(row["conflict_flags"])
        ),
        "n_groups_multiple_sequence_full": sum(
            1
            for row in groups_out
            if "multiple_sequence_full" in split_pipe(row["conflict_flags"])
        ),
        "n_groups_multiple_construct_scopes": sum(
            1
            for row in groups_out
            if "multiple_construct_scopes" in split_pipe(row["conflict_flags"])
        ),
        "n_groups_multiple_trim_statuses": sum(
            1
            for row in groups_out
            if "multiple_trim_statuses" in split_pipe(row["conflict_flags"])
        ),
        "n_multi_target_sequence_cores": len(multi_name_cores),
        "n_multi_target_sequence_rows": sum(
            1 for row in enriched if _blank(row.get("sequence_core")) in multi_name_cores
        ),
        "n_multi_name_or_id_sequence_cores": len(multi_name_or_id_cores),
        "n_multi_name_or_id_sequence_rows": sum(
            1
            for row in enriched
            if _blank(row.get("sequence_core")) in multi_name_or_id_cores
        ),
        "n_source_record_ids_with_multiple_primary_relationships": len(multi_record_ids),
        "n_rows_from_multi_relationship_source_records": sum(multi_record_ids.values()),
        "max_primary_relationships_for_one_source_record": max(
            record_counts.values(), default=0
        ),
        "source_input_distribution": _count_distribution(
            _blank(row.get("source_db")) for row in enriched
        ),
        "evidence_input_distribution": _count_distribution(
            _blank(row.get("evidence_level")) for row in enriched
        ),
        "donor_source_distribution": _count_distribution(
            _blank(row.get("source_db")) for row in corpus
        ),
        "donor_evidence_distribution": _count_distribution(
            _blank(row.get("evidence_level")) for row in corpus
        ),
        "corroboration_count_distribution": _count_distribution(
            _blank(row.get("corroboration_count")) for row in corpus
        ),
        "contributing_source_count_distribution": _count_distribution(
            str(len(split_pipe(row.get("contributing_sources") or "")))
            for row in corpus
        ),
        "independently_attested_by_permissive_source_distribution": _count_distribution(
            _blank(row.get("independently_attested_by_permissive_source"))
            for row in corpus
        ),
        "ncbi_nuc_input_rows": sum(
            1 for row in enriched if _blank(row.get("source_db")) == "ncbi_nuc"
        ),
        "ena_input_rows": sum(
            1 for row in enriched if _blank(row.get("source_db")) == "ena"
        ),
        "cluster_id_assigned": any(_blank(row.get("cluster_id")) for row in corpus),
        "is_cluster_representative_assigned": any(
            _blank(row.get("is_cluster_representative")) for row in corpus
        ),
        "metadata_completeness_fields": list(METADATA_COMPLETENESS_FIELDS),
        "scientific_identity_id_format": (
            'S5I_<sha256(sequence_core + "\\x1f" + canonical_target_name)>'
        ),
    }
    return ExactDedupResult(
        input_rows=enriched,
        corpus_dedup=corpus,
        membership=membership,
        duplicate_groups=groups_out,
        dictionary_id_conflicts=dict_conflicts,
        multi_target_sequences=_multi_target_rows(enriched),
        overlap_matrix=_overlap_matrix(
            corpus,
            groups_out,
            source_keys=overlap_sources,
        ),
        diagnostics=diagnostics,
    )


def expected_count_errors(
    diagnostics: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    checks = (
        ("n_input_relationships", "n_input_relationships"),
        ("n_distinct_source_record_ids", "n_distinct_source_record_ids"),
        ("n_distinct_sequence_core", "n_distinct_sequence_core"),
        ("n_scientific_identities", "n_scientific_identities"),
        ("n_exact_duplicate_groups", "n_exact_duplicate_groups"),
        ("n_rows_in_duplicate_groups", "n_rows_in_duplicate_groups"),
        ("n_duplicate_excess", "n_duplicate_excess"),
        ("n_membership_rows", "n_membership_rows"),
        ("n_target_dictionary_id_conflict_groups", "n_target_dictionary_id_conflict_groups"),
    )
    for diag_key, expected_key in checks:
        if expected_key not in expected:
            continue
        if diagnostics.get(diag_key) != expected[expected_key]:
            errors.append(
                f"{diag_key}: expected {expected[expected_key]}, got {diagnostics.get(diag_key)}"
            )
    for name, expected_dist in (
        ("source_input_distribution", expected.get("source_input_distribution")),
        ("evidence_input_distribution", expected.get("evidence_input_distribution")),
    ):
        if not expected_dist:
            continue
        observed = diagnostics.get(name) or {}
        for key, value in expected_dist.items():
            if observed.get(key, 0) != value:
                errors.append(f"{name}.{key}: expected {value}, got {observed.get(key, 0)}")
        extra = set(observed) - set(expected_dist)
        if extra:
            errors.append(f"{name} extra keys: {sorted(extra)}")
    if diagnostics.get("cluster_id_assigned"):
        errors.append("cluster_id was assigned; S5A must leave it empty")
    if diagnostics.get("is_cluster_representative_assigned"):
        errors.append("is_cluster_representative was assigned; S5A must leave it empty")
    return errors


def serialise_payload(rows: Sequence[Mapping[str, str]], columns: Sequence[str]) -> str:
    """Deterministic CSV payload for byte-identity comparison."""
    lines = [",".join(columns)]
    for row in rows:
        encoded = []
        for column in columns:
            value = normalise_csv_value(row.get(column, ""))
            if any(char in value for char in [",", '"', "\n", "\r"]):
                value = '"' + value.replace('"', '""') + '"'
            encoded.append(value)
        lines.append(",".join(encoded))
    return "\n".join(lines) + "\n"


def build_s5a_report(result: ExactDedupResult) -> str:
    diag = result.diagnostics
    conflict_lines = [
        f"- {row['scientific_identity_id']}: {row['canonical_target_name']} "
        f"IDs={row['contributing_target_dictionary_ids']} "
        f"sources={row['contributing_sources']} n={row['member_count']}"
        for row in result.dictionary_id_conflicts
    ]
    if not conflict_lines:
        conflict_lines = ["- none"]
    source_lines = [
        f"- {source} = {count}"
        for source, count in sorted(
            (diag.get("source_input_distribution") or {}).items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    donor_lines = [
        f"- {source} = {count}"
        for source, count in sorted(
            (diag.get("donor_source_distribution") or {}).items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    evidence_lines = [
        f"- {level} = {count}"
        for level, count in sorted((diag.get("evidence_input_distribution") or {}).items())
    ]
    corroboration_lines = [
        f"- {key} = {count}"
        for key, count in sorted(
            (diag.get("corroboration_count_distribution") or {}).items(),
            key=lambda item: int(item[0]) if str(item[0]).isdigit() else item[0],
        )
    ]
    attested = diag.get("independently_attested_by_permissive_source_distribution") or {}
    attested_lines = [
        f"- {key} = {count}"
        for key, count in sorted(attested.items())
    ]
    completeness = ", ".join(METADATA_COMPLETENESS_FIELDS)
    text = "\n".join(
        [
            "# S5A exact scientific deduplication",
            "",
            "Exact deduplication on `(sequence_core, canonical_target_name)`.",
            "No clustering, no MMseqs2/CD-HIT, no balancing, no partitions.",
            "S4 target dictionary IDs were not globally merged.",
            "NCBI/ENA duplicate resolution was not implemented; none was required.",
            "",
            "## Identity",
            "",
            f"- scientific_identity_id format: `{diag['scientific_identity_id_format']}`",
            "- donor `record_id` is provenance, not uniqueness",
            "",
            "## Input",
            "",
            f"- primary relationships: {diag['n_input_relationships']}",
            f"- distinct source record_id: {diag['n_distinct_source_record_ids']}",
            f"- distinct sequence_core: {diag['n_distinct_sequence_core']}",
            f"- NCBI rows: {diag['ncbi_nuc_input_rows']}",
            f"- ENA rows: {diag['ena_input_rows']}",
            "",
            "### Source distribution (input relationships)",
            "",
            *source_lines,
            "",
            "### Evidence distribution (input relationships)",
            "",
            *evidence_lines,
            "",
            "## Exact dedup reconciliation",
            "",
            f"- scientific identities: {diag['n_scientific_identities']}",
            f"- exact duplicate groups (>1 member): {diag['n_exact_duplicate_groups']}",
            f"- rows in those groups: {diag['n_rows_in_duplicate_groups']}",
            f"- excess duplicate observations: {diag['n_duplicate_excess']}",
            f"- membership rows: {diag['n_membership_rows']}",
            "",
            "## Donor hierarchy",
            "",
            "1. highest evidence_score",
            "2. highest pre-S5 corroboration_count (not duplicate-row count)",
            "3. highest metadata completeness",
            "4. alphabetical source_db",
            "5. alphabetical reviewed_relationship_id",
            "",
            f"Completeness fields: {completeness}.",
            "Presence is a boolean. Publication is a presence bit only.",
            "Unresolved `unknown` does not count for family, chemistry,",
            "molecule type, or construct scope.",
            "",
            "### Donor source distribution (scientific identities)",
            "",
            *donor_lines,
            "",
            "## Provenance",
            "",
            "corroboration_count = number of distinct source_db values.",
            "",
            *corroboration_lines,
            "",
            "independently_attested_by_permissive_source:",
            *attested_lines,
            "",
            "## Dictionary-ID conflicts",
            "",
            f"- groups with >1 target_dictionary_id: "
            f"{diag['n_target_dictionary_id_conflict_groups']}",
            *conflict_lines,
            "",
            "## Evidence / affinity / chemistry",
            "",
            f"- duplicate groups with differing evidence levels: "
            f"{diag['n_groups_multiple_evidence_levels']}",
            f"- duplicate groups with multiple affinity measurements: "
            f"{diag['n_groups_multiple_affinity_measurements']}",
            f"- duplicate groups with conflicting canonical affinity values: "
            f"{diag['n_groups_conflicting_affinity_values']}",
            f"- duplicate groups with multiple chemistries: "
            f"{diag['n_groups_multiple_chemistries']}",
            f"- duplicate groups with >1 sequence_full: "
            f"{diag['n_groups_multiple_sequence_full']}",
            f"- duplicate groups with >1 construct_scope: "
            f"{diag['n_groups_multiple_construct_scopes']}",
            f"- duplicate groups with >1 trim_status: "
            f"{diag['n_groups_multiple_trim_statuses']}",
            "",
            "Scalar evidence, affinity, and chemistry come from the donor.",
            "Every member observation remains in exact_duplicate_membership.csv.",
            "Affinities were not averaged, minimised, or otherwise combined.",
            "",
            "## Multi-target sequences",
            "",
            f"- sequence_core values with >1 canonical target name: "
            f"{diag['n_multi_target_sequence_cores']} "
            f"({diag['n_multi_target_sequence_rows']} rows)",
            f"- sequence_core values with >1 canonical name or dictionary ID: "
            f"{diag['n_multi_name_or_id_sequence_cores']} "
            f"({diag['n_multi_name_or_id_sequence_rows']} rows)",
            "",
            "These remain distinct scientific identities. Sequence-only collapse",
            "was not performed. Clustering is out of scope for S5A.",
            "",
            "## Source-record grain",
            "",
            f"- source record_id values with >1 primary relationship: "
            f"{diag['n_source_record_ids_with_multiple_primary_relationships']}",
            f"- rows involved: {diag['n_rows_from_multi_relationship_source_records']}",
            f"- maximum primary relationships for one source record: "
            f"{diag['max_primary_relationships_for_one_source_record']}",
            "",
            "## Boundary",
            "",
            "- cluster_id empty",
            "- is_cluster_representative empty",
            "- partition empty",
            "- S4 files not rewritten",
            "",
        ]
    )
    return text if text.endswith("\n") else text + "\n"

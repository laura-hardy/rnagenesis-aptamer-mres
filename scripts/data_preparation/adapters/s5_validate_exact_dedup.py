"""S5B validation of frozen S5A exact scientific deduplication.

This milestone checks S5A outputs against the original primary S4
relationships. It does not invent a second dedup algorithm, cluster
sequences, rewrite S4/S5A scientific files, or migrate the final schema.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any, Mapping, Sequence

from adapters.s4_scientific_common import ScientificProposalError, split_pipe
from adapters.s5_exact_dedup import (
    derive_conflict_flags,
    donor_rationale,
    donor_sort_key,
    filter_s5a_input,
    identities_remaining_after_excluding_sources,
    join_sorted_unique,
    merge_provenance,
    metadata_completeness_score,
    scientific_identity_id,
    scientific_key,
    select_donor,
    sequence_core_sha256,
    _blank,
    _canonical_molar,
    _distinct_nonempty,
    _evidence_score,
    _molar_identity,
    _present_resolved,
)
from adapters.target_extraction_common import SEQ_LEAK_RE
from common.sequence_normalisation import (
    ALPHABET_INVALID,
    ALPHABET_MISSING,
    classify_alphabet,
    load_normalisation_rules,
    validate_core_length,
)

S5ValidateError = ScientificProposalError

S5_ROW_IDENTITY_FIELD = "scientific_identity_id"
EXCLUDED_RELATIONSHIP_ROUTES: frozenset[str] = frozenset(
    {
        "park_non_protein",
        "park_evidence_e5",
        "hold_target_unresolved",
        "reject_no_binding_evidence",
        "leakage_exclusion_proposed",
        "hold_evidence_ambiguous",
    }
)
EXCLUDED_RECORD_OUTCOMES: frozenset[str] = frozenset(
    {
        "park_non_protein",
        "park_evidence_e5",
        "hold_target_unresolved",
        "reject_no_binding_evidence",
        "target_parked",
        "relationship_parked",
        "unresolved_no_relationship",
        "leakage_excluded",
    }
)
DONOR_SCALAR_FIELDS: tuple[str, ...] = (
    "record_id",
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
    "canonical_target_name",
    "target_dictionary_id",
    "target_uniprot",
    "target_type",
    "target_family",
    "target_pfam",
    "target_interpro",
    "target_region_or_fragment",
    "pdb_id",
    "evidence_level",
    "evidence_score",
    "evidence_type",
    "canonical_affinity_value",
    "canonical_affinity_unit",
    "canonical_affinity_type",
    "affinity_value_molar",
    "affinity_unit_normalized",
    "affinity_qualifier",
    "affinity_value_raw",
    "source_db",
    "source_dataset",
    "native_id",
    "publication",
    "doi",
    "pubmed_id",
    "accession",
    "experiment_group_id",
    "near_duplicate_family_id",
    "qc_flags",
    "notes",
)
MERGED_PROVENANCE_FIELDS: tuple[str, ...] = (
    "member_count",
    "contributing_sources",
    "contributing_datasets",
    "corroboration_count",
    "contributing_target_dictionary_ids",
    "contributing_chemistries",
    "contributing_record_ids",
    "contributing_reviewed_relationship_ids",
    "contributing_native_ids",
    "contributing_publications",
    "contributing_dois",
    "contributing_pubmed_ids",
    "contributing_accessions",
    "redistribution_status",
    "independently_attested_by_permissive_source",
)
CLUSTERING_INPUT_COLUMNS: tuple[str, ...] = (
    "sequence_core",
    "sequence_core_sha256",
    "sequence_length_core",
    "n_scientific_identities",
    "scientific_identity_ids",
    "canonical_target_names",
)
DONOR_DECISION_SOLE = "sole_member"
DONOR_DECISION_EVIDENCE = "evidence_score"
DONOR_DECISION_CORROBORATION = "pre_s5_corroboration_count"
DONOR_DECISION_COMPLETENESS = "metadata_completeness"
DONOR_DECISION_SOURCE = "alphabetical_source_db"
DONOR_DECISION_REL_ID = "alphabetical_reviewed_relationship_id"


@dataclass
class S5BValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _index_by(rows: Sequence[Mapping[str, str]], field: str) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        key = _blank(row.get(field))
        if not key:
            raise S5ValidateError(f"missing {field} while indexing rows")
        if key in index:
            raise S5ValidateError(f"duplicate {field} while indexing rows: {key}")
        index[key] = dict(row)
    return index


def _group_by(rows: Sequence[Mapping[str, str]], field: str) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[_blank(row.get(field))].append(dict(row))
    return grouped


def _sorted_pipe(value: str) -> bool:
    items = split_pipe(value)
    return items == sorted(items) and len(items) == len(set(items))


def _count_or_zero(counter: Mapping[str, int], key: str) -> int:
    return int(counter.get(key, 0))


def s5_row_identity(row: Mapping[str, str]) -> str:
    """Return the authoritative unique S5 scientific-row identifier."""
    identity = _blank(row.get(S5_ROW_IDENTITY_FIELD))
    if not identity:
        raise S5ValidateError(
            "scientific_identity_id is required as the S5 unique row identity"
        )
    return identity


def require_unique_s5_row_identity(
    rows: Sequence[Mapping[str, str]],
) -> list[str]:
    identities = [s5_row_identity(row) for row in rows]
    if len(identities) != len(set(identities)):
        raise S5ValidateError("scientific_identity_id is not unique")
    if any(not item.startswith("S5I_") or len(item) != 68 for item in identities):
        raise S5ValidateError("scientific_identity_id format is invalid")
    return identities


def forbid_donor_record_id_as_s5_unique_identity(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, dict[str, str]]:
    """Fail if donor ``record_id`` is treated as the unique S5 identity.

    Duplicate donor ``record_id`` values are valid provenance when one source
    record contributes more than one scientific identity.
    """
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        record_id = _blank(row.get("record_id"))
        if not record_id:
            continue
        if record_id in index:
            raise S5ValidateError(
                "donor record_id is not a unique S5 row identity; "
                "use scientific_identity_id"
            )
        index[record_id] = dict(row)
    return index


def classify_donor_decision(members: Sequence[Mapping[str, str]]) -> str:
    """Return which accepted hierarchy step selected the donor."""
    if not members:
        raise S5ValidateError("cannot classify donor decision for an empty group")
    if len(members) == 1:
        return DONOR_DECISION_SOLE
    ordered = sorted(members, key=donor_sort_key)
    winner_key = donor_sort_key(ordered[0])
    runner_key = donor_sort_key(ordered[1])
    if winner_key[0] != runner_key[0]:
        return DONOR_DECISION_EVIDENCE
    if winner_key[1] != runner_key[1]:
        return DONOR_DECISION_CORROBORATION
    if winner_key[2] != runner_key[2]:
        return DONOR_DECISION_COMPLETENESS
    if winner_key[3] != runner_key[3]:
        return DONOR_DECISION_SOURCE
    return DONOR_DECISION_REL_ID


def clustering_sequence_projection(
    corpus_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """One sequence-level clustering input row per distinct ``sequence_core``.

    Does not cluster, assign ``cluster_id``, or invoke MMseqs2/CD-HIT.
    Cluster assignment later broadcasts back to every scientific identity
    that shares the core.
    """
    grouped: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in corpus_rows:
        core = _blank(row.get("sequence_core"))
        if not core:
            raise S5ValidateError("clustering projection requires sequence_core")
        grouped[core].append(row)
    projection: list[dict[str, str]] = []
    for core, rows in grouped.items():
        projection.append(
            {
                "sequence_core": core,
                "sequence_core_sha256": sequence_core_sha256(core),
                "sequence_length_core": str(len(core)),
                "n_scientific_identities": str(len(rows)),
                "scientific_identity_ids": join_sorted_unique(
                    s5_row_identity(row) for row in rows
                ),
                "canonical_target_names": join_sorted_unique(
                    row.get("canonical_target_name") for row in rows
                ),
            }
        )
    projection.sort(key=lambda row: row["sequence_core_sha256"])
    return projection


def scan_text_for_sequence_leak(text: str) -> bool:
    return SEQ_LEAK_RE.search(text or "") is not None


def scan_paths_for_sequence_leak(paths: Sequence[Any]) -> list[str]:
    leaked: list[str] = []
    for path in paths:
        payload = path.read_text(encoding="utf-8") if hasattr(path, "read_text") else ""
        if scan_text_for_sequence_leak(payload):
            leaked.append(str(path))
    return leaked


def _expected_mismatch(
    diagnostics: Mapping[str, Any],
    expected: Mapping[str, Any],
    key: str,
) -> str | None:
    if key not in expected:
        return None
    observed = diagnostics.get(key)
    wanted = expected[key]
    if observed != wanted:
        return f"{key}: expected {wanted}, got {observed}"
    return None


def _affinity_mean(members: Sequence[Mapping[str, str]]) -> Decimal | None:
    values: list[Decimal] = []
    for row in members:
        raw = _canonical_molar(row)
        if not raw:
            continue
        try:
            values.append(Decimal(raw))
        except (InvalidOperation, ValueError):
            return None
    if len(values) < 2:
        return None
    return sum(values) / len(values)


def _record_identity_audit(corpus_rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    identities = [s5_row_identity(row) for row in corpus_rows]
    record_ids = [_blank(row.get("record_id")) for row in corpus_rows]
    record_counts = Counter(record_id for record_id in record_ids if record_id)
    duplicated = {
        record_id: count for record_id, count in record_counts.items() if count > 1
    }
    regenerated = []
    collisions = 0
    for row in corpus_rows:
        expected = scientific_identity_id(
            row.get("sequence_core", ""),
            row.get("canonical_target_name", ""),
        )
        regenerated.append(expected)
        if expected != s5_row_identity(row):
            collisions += 1
    return {
        "n_corpus_rows": len(corpus_rows),
        "n_scientific_identity_id_populated": sum(1 for item in identities if item),
        "n_scientific_identity_id_unique": len(set(identities)),
        "n_scientific_identity_id_regeneration_mismatches": collisions,
        "record_id_is_unique": len(record_counts) == len(record_ids) and len(record_ids) == len(
            set(record_ids)
        ),
        "n_distinct_donor_record_id": len(record_counts),
        "n_duplicated_donor_record_id_values": len(duplicated),
        "n_rows_with_duplicated_donor_record_id": sum(duplicated.values()),
        "authoritative_s5_row_identity": S5_ROW_IDENTITY_FIELD,
        "final_schema_recommendation": "option_b_extend_schema_keep_source_record_id",
    }


def _clustering_readiness(
    corpus_rows: Sequence[Mapping[str, str]],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    cores = [_blank(row.get("sequence_core")) for row in corpus_rows]
    missing = sum(1 for core in cores if not core)
    if missing:
        errors.append(f"missing sequence_core on {missing} corpus rows")
    lengths = [len(core) for core in cores if core]
    rules = load_normalisation_rules()
    alphabet_counts: Counter[str] = Counter()
    invalid = 0
    outside_window = 0
    for row in corpus_rows:
        core = _blank(row.get("sequence_core"))
        if not core:
            continue
        classified = classify_alphabet(core, rules=rules, molecule_type=row.get("molecule_type"))
        alphabet_counts[classified.alphabet] += 1
        if classified.alphabet in {ALPHABET_INVALID, ALPHABET_MISSING}:
            invalid += 1
        length_check = validate_core_length(core, rules)
        if not length_check.within_policy:
            outside_window += 1
    core_counts = Counter(cores)
    repeated_cores = {
        sequence_core_sha256(core): count
        for core, count in core_counts.items()
        if core and count > 1
    }
    projection = clustering_sequence_projection(corpus_rows) if missing == 0 else []
    if any(_blank(row.get("cluster_id")) for row in corpus_rows):
        errors.append("cluster_id is populated; S5B must not assign clusters")
    if any(_blank(row.get("is_cluster_representative")) for row in corpus_rows):
        errors.append("is_cluster_representative is populated; S5B must not cluster")
    if invalid:
        errors.append(f"invalid or missing sequence alphabet on {invalid} identities")
    diagnostics = {
        "n_clustering_input_rows": len(projection),
        "n_distinct_sequence_core": len({core for core in cores if core}),
        "n_missing_sequence_core": missing,
        "sequence_length_min": min(lengths) if lengths else None,
        "sequence_length_median": float(median(lengths)) if lengths else None,
        "sequence_length_max": max(lengths) if lengths else None,
        "n_rows_outside_20_100": outside_window,
        "alphabet_distribution": dict(sorted(alphabet_counts.items())),
        "n_sequence_cores_shared_by_multiple_identities": len(repeated_cores),
        "n_extra_identities_from_shared_cores": max(len(cores) - len(set(cores)), 0),
        "shared_core_identity_count_distribution": dict(
            sorted(Counter(repeated_cores.values()).items())
        ),
        "clustering_input_representation": (
            "one row per distinct sequence_core, then broadcast cluster_id "
            "back onto every scientific_identity_id sharing that core"
        ),
    }
    return diagnostics, errors


def _ena_readiness(membership_rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    ena_rows = [
        row for row in membership_rows if _blank(row.get("source_db")) == "ena"
    ]
    identities = {s5_row_identity(row) for row in ena_rows}
    cores = {_blank(row.get("sequence_core")) for row in ena_rows if _blank(row.get("sequence_core"))}
    family_rows: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    declared_multi: set[str] = set()
    reconstructable = True
    for row in ena_rows:
        family_id = _blank(row.get("ena_effective_near_duplicate_family_id"))
        size_raw = _blank(row.get("ena_effective_near_duplicate_family_size"))
        if family_id:
            family_rows[family_id].append(row)
        else:
            reconstructable = reconstructable and True
        if size_raw:
            try:
                if int(size_raw) > 1 and family_id:
                    declared_multi.add(family_id)
            except ValueError:
                reconstructable = False
    collapsed_families = []
    for family_id, rows in family_rows.items():
        family_identities = {s5_row_identity(row) for row in rows}
        if len(rows) > len(family_identities):
            collapsed_families.append(family_id)
    represented_multi_in_s5 = {
        family_id for family_id, rows in family_rows.items() if len(rows) > 1
    }
    return {
        "n_ena_membership_rows": len(ena_rows),
        "n_identities_with_ena_provenance": len(identities),
        "n_distinct_ena_sequence_core": len(cores),
        "n_ena_family_ids_represented": len(family_rows),
        "n_declared_multi_member_families_represented": len(declared_multi),
        "n_multi_member_families_with_at_least_two_s5_members": len(
            represented_multi_in_s5
        ),
        "n_families_with_exact_dedup_collapse_among_ena_members": len(collapsed_families),
        "family_membership_reconstructable_from_sidecar": reconstructable
        and "ena_effective_near_duplicate_family_id" in (ena_rows[0] if ena_rows else {"ena_effective_near_duplicate_family_id": ""}),
        "e5_only_families_excluded_from_s5_ground_truth": True,
    }


def validate_exact_dedup(
    *,
    relationship_rows: Sequence[Mapping[str, str]],
    corpus_rows: Sequence[Mapping[str, str]],
    membership_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    dictionary_conflict_rows: Sequence[Mapping[str, str]],
    record_map_rows: Sequence[Mapping[str, str]] | None = None,
    parked_audit_rows: Sequence[Mapping[str, str]] | None = None,
    expected: Mapping[str, Any] | None = None,
    enforce_live_counts: bool = False,
    regression_relationship_id: str = "aptamerbase:1110|2",
) -> S5BValidationResult:
    """Validate S5A outputs against primary S4 relationships.

    Does not call ``exact_deduplicate``. Donor, key, and provenance checks
    reuse the frozen S5A helpers.
    """
    errors: list[str] = []
    primary = filter_s5a_input(relationship_rows)
    primary_by_rel = _index_by(primary, "reviewed_relationship_id")
    membership_by_rel = {}
    try:
        membership_by_rel = _index_by(membership_rows, "reviewed_relationship_id")
    except S5ValidateError as exc:
        errors.append(str(exc))
        membership_by_rel = {
            _blank(row.get("reviewed_relationship_id")): dict(row)
            for row in membership_rows
        }

    n_primary = len(primary)
    n_membership = len(membership_rows)
    n_identities = len(corpus_rows)
    n_groups = len(group_rows)
    n_dup_rows = sum(int(_blank(row.get("member_count")) or "0") for row in group_rows)
    n_excess = n_dup_rows - n_groups
    if n_primary != n_membership:
        errors.append(
            f"membership coverage: primary {n_primary} != membership {n_membership}"
        )
    if n_primary - n_excess != n_identities:
        errors.append(
            f"reconciliation {n_primary} - {n_excess} != {n_identities}"
        )

    for rel_id, source_row in primary_by_rel.items():
        member = membership_by_rel.get(rel_id)
        if member is None:
            errors.append(f"primary relationship missing from membership: {rel_id}")
            continue
        if _blank(member.get("record_id")) != _blank(source_row.get("record_id")):
            errors.append(f"membership record_id drifted for {rel_id}")
        try:
            expected_key = scientific_key(
                source_row.get("sequence_core", ""),
                source_row.get("canonical_target_name", ""),
            )
            member_key = scientific_key(
                member.get("sequence_core", ""),
                member.get("canonical_target_name", ""),
            )
        except S5ValidateError as exc:
            errors.append(f"{rel_id}: {exc}")
            continue
        if expected_key != member_key:
            errors.append(f"scientific key drifted for {rel_id}")
        expected_identity = scientific_identity_id(*expected_key)
        if _blank(member.get("scientific_identity_id")) != expected_identity:
            errors.append(f"scientific_identity_id mismatch for {rel_id}")
        if _blank(member.get("s4_route")) != "primary_candidate":
            errors.append(f"non-primary route in membership: {rel_id}")

    excluded_rel_ids = {
        _blank(row.get("reviewed_relationship_id"))
        for row in relationship_rows
        if _blank(row.get("s4_route")) in EXCLUDED_RELATIONSHIP_ROUTES
        and _blank(row.get("reviewed_relationship_id"))
    }
    leaked_excluded = excluded_rel_ids.intersection(membership_by_rel)
    if leaked_excluded:
        errors.append(
            "excluded S4 relationships present in membership: "
            + ",".join(sorted(leaked_excluded)[:8])
        )
    membership_routes = Counter(
        _blank(row.get("s4_route")) for row in membership_rows
    )
    for route in EXCLUDED_RELATIONSHIP_ROUTES:
        if membership_routes.get(route):
            errors.append(f"membership contains {route} rows")

    if record_map_rows is not None:
        parked_records = {
            _blank(row.get("record_id"))
            for row in record_map_rows
            if _blank(row.get("s4_record_outcome")) in EXCLUDED_RECORD_OUTCOMES
            and int(_blank(row.get("n_effective_relationships")) or "0") == 0
        }
        leaked_records = parked_records.intersection(
            _blank(row.get("record_id")) for row in membership_rows
        )
        if leaked_records:
            errors.append(
                "parked/unresolved records leaked into membership: "
                + ",".join(sorted(leaked_records)[:8])
            )

    if parked_audit_rows is not None:
        audit_rel_ids = {
            _blank(row.get("reviewed_relationship_id"))
            for row in parked_audit_rows
            if _blank(row.get("reviewed_relationship_id"))
            and _blank(row.get("s4_route")) in EXCLUDED_RELATIONSHIP_ROUTES
        }
        leaked_audit = audit_rel_ids.intersection(membership_by_rel)
        if leaked_audit:
            errors.append(
                "park/exclusion audit relationships leaked into membership: "
                + ",".join(sorted(leaked_audit)[:8])
            )

    if regression_relationship_id:
        in_input = any(
            _blank(row.get("reviewed_relationship_id")) == regression_relationship_id
            for row in relationship_rows
        )
        if in_input or enforce_live_counts:
            member = membership_by_rel.get(regression_relationship_id)
            source = primary_by_rel.get(regression_relationship_id)
            if source is None:
                errors.append(
                    f"regression relationship {regression_relationship_id} is not an S4 primary"
                )
            elif member is None:
                errors.append(
                    f"regression relationship {regression_relationship_id} missing from membership"
                )
            else:
                if _blank(member.get("canonical_target_name")) != _blank(
                    source.get("canonical_target_name")
                ):
                    errors.append(
                        f"{regression_relationship_id} canonical target drifted from S4"
                    )
                if _blank(member.get("canonical_target_name")).casefold() == "a549 cells":
                    errors.append(
                        f"{regression_relationship_id} used the parked non-protein target"
                    )

    members_by_identity = _group_by(membership_rows, "scientific_identity_id")
    try:
        corpus_by_identity = _index_by(corpus_rows, "scientific_identity_id")
    except S5ValidateError as exc:
        errors.append(str(exc))
        corpus_by_identity = {
            _blank(row.get("scientific_identity_id")): dict(row) for row in corpus_rows
        }
    try:
        groups_by_identity = _index_by(group_rows, "scientific_identity_id")
    except S5ValidateError as exc:
        errors.append(str(exc))
        groups_by_identity = {
            _blank(row.get("scientific_identity_id")): dict(row) for row in group_rows
        }
    try:
        conflicts_by_identity = _index_by(
            dictionary_conflict_rows, "scientific_identity_id"
        )
    except S5ValidateError as exc:
        errors.append(str(exc))
        conflicts_by_identity = {
            _blank(row.get("scientific_identity_id")): dict(row)
            for row in dictionary_conflict_rows
        }

    membership_identities = set(members_by_identity)
    corpus_identities = set(corpus_by_identity)
    if membership_identities != corpus_identities:
        errors.append("master/membership identity sets differ")
    orphan_groups = set(groups_by_identity) - corpus_identities
    if orphan_groups:
        errors.append(f"orphan duplicate groups: {len(orphan_groups)}")
    orphan_conflicts = set(conflicts_by_identity) - corpus_identities
    if orphan_conflicts:
        errors.append(f"orphan dictionary-ID conflict rows: {len(orphan_conflicts)}")
    for identity, members in members_by_identity.items():
        if identity not in corpus_by_identity:
            errors.append(f"membership identity missing from corpus: {identity}")
        if len(members) < 1:
            errors.append(f"identity has no membership rows: {identity}")

    key_to_identity: dict[tuple[str, str], str] = {}
    identity_keys: dict[str, set[tuple[str, str]]] = defaultdict(set)
    identity_names: dict[str, set[str]] = defaultdict(set)
    donor_decisions: Counter[str] = Counter()
    corroboration_counts: Counter[str] = Counter()
    permissive_true = 0
    evidence_levels = Counter()
    n_sequence_full_inconsistent = 0
    n_missing_core = 0
    n_core_differs = 0
    n_donor_mismatch = 0
    n_utexas_mod_notes = 0
    n_restricted_aptaindex = 0

    for identity, members in members_by_identity.items():
        keys = set()
        cores = set()
        names = set()
        for member in members:
            try:
                key = scientific_key(
                    member.get("sequence_core", ""),
                    member.get("canonical_target_name", ""),
                )
            except S5ValidateError as exc:
                errors.append(f"{identity}: {exc}")
                continue
            keys.add(key)
            cores.add(key[0])
            names.add(key[1])
            expected_identity = scientific_identity_id(*key)
            if expected_identity != identity:
                errors.append(
                    f"{identity} does not regenerate from member scientific key"
                )
            stored_score = _blank(member.get("metadata_completeness_score"))
            recomputed_score = str(metadata_completeness_score(member))
            if stored_score and stored_score != recomputed_score:
                errors.append(f"completeness score drifted on {member.get('reviewed_relationship_id')}")
            if _blank(member.get("source_db")) == "aptaindex" and _blank(
                member.get("redistribution_status")
            ) == "restricted":
                n_restricted_aptaindex += 1
            if _blank(member.get("utexas_post_selex_modifications")):
                n_utexas_mod_notes += 1
        identity_keys[identity] = keys
        identity_names[identity] = names
        if len(keys) != 1:
            errors.append(f"{identity} has {len(keys)} distinct scientific keys")
        if len(names) != 1:
            errors.append(f"{identity} has {len(names)} canonical target names")
        if len(cores) != 1:
            n_core_differs += 1
            errors.append(f"{identity} has differing sequence_core across members")
        if any(not _blank(member.get("sequence_core")) for member in members):
            n_missing_core += 1
        for key in keys:
            previous = key_to_identity.get(key)
            if previous is None:
                key_to_identity[key] = identity
            elif previous != identity:
                errors.append("two scientific_identity_id values share one scientific key")

        donor = select_donor(members)
        donor_id = _blank(donor.get("reviewed_relationship_id"))
        master = corpus_by_identity.get(identity, {})
        if _blank(master.get("donor_reviewed_relationship_id")) != donor_id:
            n_donor_mismatch += 1
            errors.append(f"donor mismatch for {identity}")
        donor_members = [
            row
            for row in members
            if _blank(row.get("reviewed_relationship_id")) == donor_id
        ]
        if len(donor_members) != 1:
            errors.append(f"{identity} does not have exactly one donor membership row")
        elif _blank(donor_members[0].get("is_donor")) != "true":
            errors.append(f"{identity} donor membership is_donor is not true")
        if sum(1 for row in members if _blank(row.get("is_donor")) == "true") != 1:
            errors.append(f"{identity} does not have exactly one is_donor=true row")
        if _blank(master.get("donor_rationale")) != donor_rationale(donor):
            errors.append(f"donor rationale drifted for {identity}")
        donor_decisions[classify_donor_decision(members)] += 1

        provenance = merge_provenance(members)
        flags = derive_conflict_flags(members)
        flag_token = join_sorted_unique(flags)
        if _blank(master.get("conflict_flags")) != flag_token:
            errors.append(f"conflict_flags drifted for {identity}")
        for field_name in MERGED_PROVENANCE_FIELDS:
            if _blank(master.get(field_name)) != _blank(provenance.get(field_name)):
                errors.append(f"{field_name} drifted for {identity}")
        for field_name in DONOR_SCALAR_FIELDS:
            if _blank(master.get(field_name)) != _blank(donor.get(field_name)):
                errors.append(f"donor scalar {field_name} drifted for {identity}")
        if _blank(master.get("target_name")) != _blank(donor.get("canonical_target_name")):
            errors.append(f"target_name drifted for {identity}")
        if _blank(master.get("binding_evidence_type")) != _blank(
            donor.get("evidence_type") or donor.get("binding_evidence_type")
        ):
            errors.append(f"binding_evidence_type drifted for {identity}")
        if _blank(master.get("binding_evidence_score")) != str(_evidence_score(donor)):
            errors.append(f"binding_evidence_score drifted for {identity}")
        if _blank(master.get("affinity_value")) != _canonical_molar(donor):
            errors.append(f"scalar affinity is not donor-derived for {identity}")
        if _blank(master.get("sequence_full")) != _blank(donor.get("sequence_full")):
            n_sequence_full_inconsistent += 1
        mean_affinity = _affinity_mean(members)
        if mean_affinity is not None:
            donor_molar = _canonical_molar(donor)
            master_molar = _blank(master.get("canonical_affinity_value"))
            try:
                if (
                    donor_molar
                    and master_molar
                    and Decimal(master_molar) == mean_affinity
                    and Decimal(donor_molar) != mean_affinity
                ):
                    errors.append(f"affinity appears averaged for {identity}")
            except (InvalidOperation, ValueError):
                pass

        distinct_sources = {
            _blank(row.get("source_db")) for row in members if _blank(row.get("source_db"))
        }
        if int(provenance["corroboration_count"] or "0") != len(distinct_sources):
            errors.append(f"corroboration is not distinct-source count for {identity}")
        corroboration_counts[provenance["corroboration_count"]] += 1
        if not _sorted_pipe(provenance["contributing_sources"]):
            errors.append(f"contributing_sources not sorted unique for {identity}")
        if not _sorted_pipe(provenance["contributing_datasets"]):
            errors.append(f"contributing_datasets not sorted unique for {identity}")

        if _blank(master.get("independently_attested_by_permissive_source")) == "true":
            permissive_true += 1
        evidence_levels[_blank(master.get("evidence_level"))] += 1
        if _blank(master.get("evidence_level")) == "E5":
            errors.append(f"E5 entered S5 for {identity}")
        if _blank(master.get("evidence_level")) != _blank(donor.get("evidence_level")):
            errors.append(f"corroboration appears to have raised evidence for {identity}")

        if len(members) > 1:
            group = groups_by_identity.get(identity)
            if group is None:
                errors.append(f"duplicate identity missing group row: {identity}")
            else:
                if _blank(group.get("member_count")) != str(len(members)):
                    errors.append(f"group member_count drifted for {identity}")
                if _blank(group.get("distinct_source_count")) != provenance["corroboration_count"]:
                    errors.append(f"group distinct_source_count drifted for {identity}")
                if _blank(group.get("donor_reviewed_relationship_id")) != donor_id:
                    errors.append(f"group donor drifted for {identity}")
                if _blank(group.get("conflict_flags")) != flag_token:
                    errors.append(f"group conflict_flags drifted for {identity}")
        elif identity in groups_by_identity:
            errors.append(f"singleton identity has a duplicate-group row: {identity}")

        dict_ids = _distinct_nonempty(members, "target_dictionary_id")
        if len(dict_ids) > 1:
            conflict = conflicts_by_identity.get(identity)
            if conflict is None:
                errors.append(f"missing dictionary-ID conflict row for {identity}")
            else:
                if _blank(conflict.get("donor_target_dictionary_id")) != _blank(
                    donor.get("target_dictionary_id")
                ):
                    errors.append(f"conflict scalar ID is not donor ID for {identity}")
                if _blank(conflict.get("contributing_target_dictionary_ids")) != provenance[
                    "contributing_target_dictionary_ids"
                ]:
                    errors.append(f"conflict membership IDs incomplete for {identity}")
                if "multiple_target_dictionary_ids" not in split_pipe(flag_token):
                    errors.append(f"missing multiple_target_dictionary_ids flag for {identity}")
        elif identity in conflicts_by_identity:
            errors.append(f"spurious dictionary-ID conflict row for {identity}")

    primary_keys = set()
    for row in primary:
        primary_keys.add(
            scientific_key(
                row.get("sequence_core", ""),
                row.get("canonical_target_name", ""),
            )
        )
    if len(primary_keys) != n_identities:
        errors.append(
            f"distinct primary scientific keys {len(primary_keys)} != identities {n_identities}"
        )
    if set(key_to_identity) != primary_keys:
        errors.append("scientific-key bijection between primary input and identities failed")

    cores_by_name: dict[str, set[str]] = defaultdict(set)
    identities_by_core: dict[str, set[str]] = defaultdict(set)
    for row in primary:
        core = _blank(row.get("sequence_core"))
        cores_by_name[core].add(_blank(row.get("canonical_target_name")))
    for identity, members in members_by_identity.items():
        for member in members:
            identities_by_core[_blank(member.get("sequence_core"))].add(identity)
    multi_name_cores = {
        core for core, names in cores_by_name.items() if core and len(names) > 1
    }
    multi_name_rows = sum(
        1 for row in primary if _blank(row.get("sequence_core")) in multi_name_cores
    )
    for core in multi_name_cores:
        n_names = len(cores_by_name[core])
        n_ids = len(identities_by_core.get(core, set()))
        if n_ids < n_names:
            errors.append(
                "multi-target sequence collapsed below its canonical-name count"
            )
        if n_ids < 2:
            errors.append("multi-target sequence reduced to a single scientific identity")

    def _group_flag_count(flag: str) -> int:
        return sum(
            1
            for row in group_rows
            if flag in split_pipe(row.get("conflict_flags") or "")
        )

    n_chem_groups = sum(
        1
        for identity, members in members_by_identity.items()
        if len(members) > 1
        and len(
            {
                _blank(row.get("chemistry"))
                for row in members
                if _present_resolved(row.get("chemistry"))
            }
        )
        > 1
    )
    n_evidence_groups = sum(
        1
        for identity, members in members_by_identity.items()
        if len(members) > 1 and len(_distinct_nonempty(members, "evidence_level")) > 1
    )
    n_affinity_conflict = sum(
        1
        for identity, members in members_by_identity.items()
        if len(members) > 1
        and len(
            {
                _molar_identity(_canonical_molar(row))
                for row in members
                if _canonical_molar(row)
            }
        )
        > 1
    )
    n_affinity_obs = sum(
        1
        for identity, members in members_by_identity.items()
        if len(members) > 1
        and len([row for row in members if _canonical_molar(row)]) > 1
    )
    n_construct = sum(
        1
        for identity, members in members_by_identity.items()
        if len(members) > 1 and len(_distinct_nonempty(members, "construct_scope")) > 1
    )
    n_trim = sum(
        1
        for identity, members in members_by_identity.items()
        if len(members) > 1 and len(_distinct_nonempty(members, "trim_status")) > 1
    )
    n_seq_full = sum(
        1
        for identity, members in members_by_identity.items()
        if len(members) > 1 and len(_distinct_nonempty(members, "sequence_full")) > 1
    )

    if n_chem_groups != _group_flag_count("multiple_chemistries"):
        errors.append("multiple_chemistries flag disagrees with membership")
    if n_affinity_conflict != _group_flag_count("conflicting_affinity_values"):
        errors.append("conflicting_affinity_values flag disagrees with membership")
    if n_seq_full:
        errors.append(f"duplicate groups with >1 sequence_full: {n_seq_full}")

    conflict_names = Counter(
        _blank(row.get("canonical_target_name")) for row in dictionary_conflict_rows
    )

    try:
        require_unique_s5_row_identity(corpus_rows)
        identity_unique = True
    except S5ValidateError as exc:
        identity_unique = False
        errors.append(str(exc))
    record_audit = _record_identity_audit(corpus_rows)
    clustering_diag, clustering_errors = _clustering_readiness(corpus_rows)
    errors.extend(clustering_errors)
    ena_diag = _ena_readiness(membership_rows)

    diagnostics: dict[str, Any] = {
        "n_input_relationships": n_primary,
        "n_membership_rows": n_membership,
        "n_scientific_identities": n_identities,
        "n_exact_duplicate_groups": n_groups,
        "n_rows_in_duplicate_groups": n_dup_rows,
        "n_duplicate_excess": n_excess,
        "n_distinct_primary_scientific_keys": len(primary_keys),
        "n_distinct_sequence_core": len(cores_by_name),
        "n_multi_target_sequence_cores": len(multi_name_cores),
        "n_multi_target_sequence_rows": multi_name_rows,
        "n_target_dictionary_id_conflict_groups": len(dictionary_conflict_rows),
        "dictionary_conflict_name_counts": dict(sorted(conflict_names.items())),
        "n_groups_multiple_evidence_levels": n_evidence_groups,
        "n_groups_conflicting_affinity_values": n_affinity_conflict,
        "n_groups_multiple_affinity_measurements": n_affinity_obs,
        "n_groups_multiple_chemistries": n_chem_groups,
        "n_groups_multiple_sequence_full": n_seq_full,
        "n_groups_multiple_construct_scopes": n_construct,
        "n_groups_multiple_trim_statuses": n_trim,
        "n_donor_mismatches": n_donor_mismatch,
        "donor_decision_distribution": dict(sorted(donor_decisions.items())),
        "n_identities_evidence_determined_winner": _count_or_zero(
            donor_decisions, DONOR_DECISION_EVIDENCE
        ),
        "n_identities_completeness_determined_winner": _count_or_zero(
            donor_decisions, DONOR_DECISION_COMPLETENESS
        ),
        "n_identities_source_alphabetical_determined_winner": _count_or_zero(
            donor_decisions, DONOR_DECISION_SOURCE
        ),
        "n_identities_relationship_id_tiebreak_determined_winner": _count_or_zero(
            donor_decisions, DONOR_DECISION_REL_ID
        ),
        "n_identities_corroboration_determined_winner": _count_or_zero(
            donor_decisions, DONOR_DECISION_CORROBORATION
        ),
        "n_identities_sole_member": _count_or_zero(donor_decisions, DONOR_DECISION_SOLE),
        "corroboration_count_distribution": {
            key: corroboration_counts[key] for key in sorted(corroboration_counts, key=lambda item: int(item) if str(item).isdigit() else item)
        },
        "n_independently_attested_by_permissive_source_true": permissive_true,
        "donor_evidence_distribution": dict(sorted(evidence_levels.items())),
        "n_donor_sequence_full_inconsistent": n_sequence_full_inconsistent,
        "n_missing_sequence_core": n_missing_core,
        "n_identities_with_differing_member_sequence_core": n_core_differs,
        "n_utexas_post_selex_modification_notes": n_utexas_mod_notes,
        "n_restricted_aptaindex_membership_rows": n_restricted_aptaindex,
        "scientific_identity_id_unique": identity_unique,
        "row_identity": record_audit,
        "clustering_readiness": clustering_diag,
        "ena_readiness": ena_diag,
        "regression_relationship_present": regression_relationship_id in membership_by_rel
        if regression_relationship_id
        else None,
        "source_exclusion_helper_available": identities_remaining_after_excluding_sources
        is not None,
    }

    expected_counts = expected or {}
    if enforce_live_counts:
        for key in (
            "n_input_relationships",
            "n_membership_rows",
            "n_scientific_identities",
            "n_distinct_sequence_core",
            "n_exact_duplicate_groups",
            "n_duplicate_excess",
            "n_multi_target_sequence_cores",
            "n_multi_target_sequence_rows",
            "n_target_dictionary_id_conflict_groups",
            "n_groups_multiple_evidence_levels",
            "n_groups_conflicting_affinity_values",
            "n_groups_multiple_affinity_measurements",
            "n_groups_multiple_chemistries",
            "n_groups_multiple_sequence_full",
            "n_groups_multiple_construct_scopes",
            "n_groups_multiple_trim_statuses",
            "n_independently_attested_by_permissive_source_true",
        ):
            mismatch = _expected_mismatch(diagnostics, expected_counts, key)
            if mismatch:
                errors.append(mismatch)
        expected_corr = expected_counts.get("corroboration_count_distribution") or {}
        observed_corr = diagnostics.get("corroboration_count_distribution") or {}
        for key, value in expected_corr.items():
            if observed_corr.get(str(key), 0) != value:
                errors.append(
                    f"corroboration_count_distribution.{key}: expected {value}, "
                    f"got {observed_corr.get(str(key), 0)}"
                )
        expected_names = expected_counts.get("dictionary_conflict_name_counts") or {}
        for name, value in expected_names.items():
            if conflict_names.get(name, 0) != value:
                errors.append(
                    f"dictionary_conflict_name_counts.{name}: expected {value}, "
                    f"got {conflict_names.get(name, 0)}"
                )
        if diagnostics["clustering_readiness"]["n_distinct_sequence_core"] != expected_counts.get(
            "n_distinct_sequence_core",
            diagnostics["clustering_readiness"]["n_distinct_sequence_core"],
        ):
            errors.append("clustering distinct sequence_core drifted from scientific identities")

    if n_donor_mismatch:
        errors.append("donor recomputation mismatches are a NO-GO")
    if n_sequence_full_inconsistent:
        errors.append("donor sequence_full inconsistent with donor membership")
    if n_missing_core:
        errors.append("missing sequence_core on an identity")
    if permissive_true and enforce_live_counts:
        errors.append("independently_attested_by_permissive_source is not false for all identities")

    # Deduplicate while preserving order.
    unique_errors: list[str] = []
    seen_errors: set[str] = set()
    for item in errors:
        if item in seen_errors:
            continue
        seen_errors.add(item)
        unique_errors.append(item)

    return S5BValidationResult(
        ok=not unique_errors,
        errors=unique_errors,
        diagnostics=diagnostics,
    )


def build_s5b_report(
    result: S5BValidationResult,
    *,
    s4_hashes: Mapping[str, str] | None = None,
    s5a_hashes: Mapping[str, str] | None = None,
    sequence_safety: Mapping[str, Any] | None = None,
) -> str:
    diag = result.diagnostics
    row_identity = diag.get("row_identity") or {}
    clustering = diag.get("clustering_readiness") or {}
    ena = diag.get("ena_readiness") or {}
    donor_lines = [
        f"- {key} = {count}"
        for key, count in (diag.get("donor_decision_distribution") or {}).items()
    ]
    corr_lines = [
        f"- {key} = {count}"
        for key, count in (diag.get("corroboration_count_distribution") or {}).items()
    ]
    conflict_name_lines = [
        f"- {name} = {count}"
        for name, count in (diag.get("dictionary_conflict_name_counts") or {}).items()
    ]
    alphabet_lines = [
        f"- {name} = {count}"
        for name, count in (clustering.get("alphabet_distribution") or {}).items()
    ]
    hash_lines = []
    for label, payload in (("S4", s4_hashes), ("S5A", s5a_hashes)):
        if not payload:
            continue
        hash_lines.append(f"### {label} freeze hashes")
        hash_lines.append("")
        for name, digest in payload.items():
            hash_lines.append(f"- `{name}`: `{digest}`")
        hash_lines.append("")
    safety_lines = []
    if sequence_safety:
        safety_lines = [
            f"- tracked S5 files scanned: {sequence_safety.get('n_paths_scanned', 0)}",
            f"- sequence-leak matches in scanned S5 files: {sequence_safety.get('n_leaks', 0)}",
            f"- historical docs/log matches excluded from this scan: "
            f"{sequence_safety.get('historical_log_sequences_present', False)}",
        ]
    status = "GO" if result.ok else "NO-GO"
    error_lines = [f"- {item}" for item in result.errors] or ["- none"]
    lines = [
        "# S5B exact-dedup validation and scientific freeze",
        "",
        "Validation of frozen S5A exact scientific identities.",
        "No clustering, no MMseqs2/CD-HIT, no S4 rewrite, no S5A scientific rewrite.",
        "",
        f"## Status: {status}",
        "",
        "## Errors",
        "",
        *error_lines,
        "",
        "## Population",
        "",
        f"- primary relationships: {diag.get('n_input_relationships')}",
        f"- membership rows: {diag.get('n_membership_rows')}",
        f"- scientific identities: {diag.get('n_scientific_identities')}",
        f"- duplicate groups: {diag.get('n_exact_duplicate_groups')}",
        f"- duplicate excess: {diag.get('n_duplicate_excess')}",
        f"- distinct scientific keys: {diag.get('n_distinct_primary_scientific_keys')}",
        f"- distinct sequence_core: {diag.get('n_distinct_sequence_core')}",
        f"- multi-target sequence_core: {diag.get('n_multi_target_sequence_cores')} "
        f"({diag.get('n_multi_target_sequence_rows')} rows)",
        f"- EGFR regression present: {diag.get('regression_relationship_present')}",
        "",
        "## Donor decision paths",
        "",
        f"- evidence determined winner: {diag.get('n_identities_evidence_determined_winner')}",
        f"- completeness determined winner: {diag.get('n_identities_completeness_determined_winner')}",
        f"- source alphabetical determined winner: {diag.get('n_identities_source_alphabetical_determined_winner')}",
        f"- relationship-ID tie-break determined winner: {diag.get('n_identities_relationship_id_tiebreak_determined_winner')}",
        f"- pre-S5 corroboration determined winner: {diag.get('n_identities_corroboration_determined_winner')}",
        f"- sole member: {diag.get('n_identities_sole_member')}",
        f"- donor mismatches: {diag.get('n_donor_mismatches')}",
        "",
        *donor_lines,
        "",
        "## Corroboration",
        "",
        *corr_lines,
        "",
        f"- independently_attested_by_permissive_source true: "
        f"{diag.get('n_independently_attested_by_permissive_source_true')}",
        f"- restricted AptaIndex membership rows: "
        f"{diag.get('n_restricted_aptaindex_membership_rows')}",
        "",
        "## Conflicts",
        "",
        f"- target-dictionary ID conflict groups: {diag.get('n_target_dictionary_id_conflict_groups')}",
        *conflict_name_lines,
        f"- differing evidence groups: {diag.get('n_groups_multiple_evidence_levels')}",
        f"- conflicting canonical affinity groups: {diag.get('n_groups_conflicting_affinity_values')}",
        f"- multiple affinity observations: {diag.get('n_groups_multiple_affinity_measurements')}",
        f"- multiple chemistry groups: {diag.get('n_groups_multiple_chemistries')}",
        f"- >1 sequence_full: {diag.get('n_groups_multiple_sequence_full')}",
        f"- >1 construct_scope: {diag.get('n_groups_multiple_construct_scopes')}",
        f"- >1 trim_status: {diag.get('n_groups_multiple_trim_statuses')}",
        f"- UTexas post-SELEX modification notes: {diag.get('n_utexas_post_selex_modification_notes')}",
        "",
        "## Row identity",
        "",
        f"- donor record_id unique: {row_identity.get('record_id_is_unique')}",
        f"- duplicated donor record_id values: {row_identity.get('n_duplicated_donor_record_id_values')}",
        f"- rows with duplicated donor record_id: {row_identity.get('n_rows_with_duplicated_donor_record_id')}",
        f"- scientific_identity_id populated: {row_identity.get('n_scientific_identity_id_populated')}/"
        f"{row_identity.get('n_corpus_rows')}",
        f"- scientific_identity_id unique: {row_identity.get('n_scientific_identity_id_unique')}",
        f"- regeneration mismatches / collisions: "
        f"{row_identity.get('n_scientific_identity_id_regeneration_mismatches')}",
        f"- authoritative S5 row identity: `{row_identity.get('authoritative_s5_row_identity')}`",
        f"- later final-schema recommendation: `{row_identity.get('final_schema_recommendation')}`",
        "",
        "Donor `record_id` remains provenance. S5C must key on `scientific_identity_id`.",
        "S5B does not implement Option A or Option B final-schema migration.",
        "",
        "## Clustering readiness",
        "",
        f"- identities: {diag.get('n_scientific_identities')}",
        f"- clustering input rows (one per sequence_core): {clustering.get('n_clustering_input_rows')}",
        f"- missing sequence_core: {clustering.get('n_missing_sequence_core')}",
        f"- length min/median/max: {clustering.get('sequence_length_min')} / "
        f"{clustering.get('sequence_length_median')} / {clustering.get('sequence_length_max')}",
        f"- outside 20-100: {clustering.get('n_rows_outside_20_100')}",
        f"- shared cores: {clustering.get('n_sequence_cores_shared_by_multiple_identities')}",
        f"- extra identities from shared cores: {clustering.get('n_extra_identities_from_shared_cores')}",
        f"- proposed input: {clustering.get('clustering_input_representation')}",
        "",
        "### Alphabet",
        "",
        *alphabet_lines,
        "",
        "## ENA family provenance",
        "",
        f"- ENA membership rows: {ena.get('n_ena_membership_rows')}",
        f"- identities with ENA provenance: {ena.get('n_identities_with_ena_provenance')}",
        f"- distinct ENA sequence_core: {ena.get('n_distinct_ena_sequence_core')}",
        f"- family IDs represented: {ena.get('n_ena_family_ids_represented')}",
        f"- declared multi-member families represented: "
        f"{ena.get('n_declared_multi_member_families_represented')}",
        f"- families with >=2 S5 ENA members: "
        f"{ena.get('n_multi_member_families_with_at_least_two_s5_members')}",
        f"- within-family exact-dedup collapses: "
        f"{ena.get('n_families_with_exact_dedup_collapse_among_ena_members')}",
        f"- family membership reconstructable from sidecar: "
        f"{ena.get('family_membership_reconstructable_from_sidecar')}",
        "",
        "Cluster recall is not evaluated. E5-only families outside S5 are not failures.",
        "",
        "## Sequence safety",
        "",
        *(safety_lines or ["- not reported"]),
        "",
        "## Freeze hashes",
        "",
        *hash_lines,
        "## Boundary",
        "",
        "- S4 science unchanged",
        "- S5A scientific policy unchanged",
        "- no clustering / MMseqs2 / CD-HIT",
        "- no cluster IDs assigned",
        "- no S6 / S7 / balancing / splits",
        "",
    ]
    text = "\n".join(lines)
    return text if text.endswith("\n") else text + "\n"


__all__ = [
    "CLUSTERING_INPUT_COLUMNS",
    "DONOR_DECISION_COMPLETENESS",
    "DONOR_DECISION_CORROBORATION",
    "DONOR_DECISION_EVIDENCE",
    "DONOR_DECISION_REL_ID",
    "DONOR_DECISION_SOLE",
    "DONOR_DECISION_SOURCE",
    "S5BValidationResult",
    "S5ValidateError",
    "S5_ROW_IDENTITY_FIELD",
    "build_s5b_report",
    "classify_donor_decision",
    "clustering_sequence_projection",
    "forbid_donor_record_id_as_s5_unique_identity",
    "require_unique_s5_row_identity",
    "s5_row_identity",
    "scan_paths_for_sequence_leak",
    "scan_text_for_sequence_leak",
    "validate_exact_dedup",
]

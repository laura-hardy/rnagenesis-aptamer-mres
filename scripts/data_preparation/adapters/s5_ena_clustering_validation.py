"""S5D ENA-family validation, pairwise diagnostics, and method adjudication.

ENA ``near_duplicate_family_id`` values are used as the plan's clustering
reference. This module does not retune identity thresholds, merge or split
families by hand, or replace clustering with the diagnostic graph.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Callable, Iterable, Mapping, Sequence

from adapters.s4_scientific_common import (
    ScientificProposalError,
    bool_token,
    fill_row,
    split_pipe,
)
from adapters.s5_exact_dedup import _blank, join_sorted_unique
from adapters.s5_sequence_clustering import make_sequence_id, sequence_core_digest
from common.leakage_matching import global_edit_identity

S5EnaValidationError = ScientificProposalError

IDENTITY_THRESHOLD = 0.90
MATERIALISED_SINGLETON_PREFIX = "ena_singleton_"
DECISION_ACCEPT_CDHIT = "ACCEPT CD-HIT"
DECISION_BOTH_FAIL = "NO-GO — BOTH METHODS FAIL VALIDATION"
DECISION_GROUND_TRUTH_CONTRADICTION = (
    "NO-GO — GROUND-TRUTH / 90%-RULE CONTRADICTION"
)

FAMILY_REPORT_COLUMNS: tuple[str, ...] = (
    "ena_family_id",
    "declared_multi_member",
    "n_s5_ena_membership_rows",
    "n_s5_ena_sequence_cores",
    "n_clusters",
    "contained_in_one_cluster",
    "cluster_size_partition",
    "min_core_length",
    "median_core_length",
    "max_core_length",
    "lengths_differ",
    "experiment_group_ids",
    "canonical_targets",
    "levenshtein_graph_status",
    "mmseqs_pairwise_graph_status",
    "source_definition_graph_status",
    "source_definition_edge_labels",
    "split_reason_summary",
    "cluster_ids",
)

SINGLETON_AUDIT_COLUMNS: tuple[str, ...] = (
    "ena_family_id",
    "sequence_id",
    "cluster_id",
    "n_ena_cores_in_cluster",
    "n_materialised_singletons_in_cluster",
    "n_real_multi_member_families_in_cluster",
    "n_non_ena_sequences_in_cluster",
    "ena_internal_status",
    "conflict_reason",
)

CROSS_FAMILY_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "n_ena_families",
    "n_real_multi_member_families",
    "n_materialised_singleton_families",
    "mix_kind",
    "ena_family_ids",
)

METHOD_COMPARISON_COLUMNS: tuple[str, ...] = (
    "metric",
    "mmseqs",
    "cdhit",
)


@dataclass
class EnaValidationResult:
    family_rows: list[dict[str, str]]
    singleton_rows: list[dict[str, str]]
    cross_family_rows: list[dict[str, str]]
    metrics: dict[str, Any] = field(default_factory=dict)


def _median_token(values: Sequence[int]) -> str:
    if not values:
        return ""
    value = median(values)
    if float(value) == int(value):
        return str(int(value))
    return str(value)


def _union_find_components(nodes: Sequence[str], edges: Sequence[tuple[str, str]]) -> list[list[str]]:
    parent = {node: node for node in nodes}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        root_l, root_r = find(left), find(right)
        if root_l != root_r:
            parent[root_r] = root_l

    for left, right in edges:
        if left in parent and right in parent:
            union(left, right)
    grouped: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        grouped[find(node)].append(node)
    return [sorted(members) for members in grouped.values()]


def pairwise_graph_status(
    sequence_ids: Sequence[str],
    identity_lookup: Callable[[str, str], float | None],
    *,
    threshold: float = IDENTITY_THRESHOLD,
) -> dict[str, Any]:
    """Classify a family graph. Diagnostic only; not a clustering algorithm."""
    nodes = list(dict.fromkeys(sequence_ids))
    if len(nodes) <= 1:
        return {
            "status": "singleton",
            "n_nodes": len(nodes),
            "n_edges_ge_threshold": 0,
            "n_pairs": 0,
            "n_pairs_below_threshold": 0,
            "n_pairs_missing": 0,
            "min_pairwise_identity": None,
            "n_components": len(nodes),
        }
    edges: list[tuple[str, str]] = []
    n_pairs = 0
    n_below = 0
    n_missing = 0
    identities: list[float] = []
    for i, left in enumerate(nodes):
        for right in nodes[i + 1 :]:
            n_pairs += 1
            identity = identity_lookup(left, right)
            if identity is None:
                n_missing += 1
                continue
            identities.append(identity)
            if identity >= threshold:
                edges.append((left, right))
            else:
                n_below += 1
    components = _union_find_components(nodes, edges)
    if n_pairs > 0 and n_below == 0 and n_missing == 0:
        status = "all_pairs_ge_0.90"
    elif len(components) == 1 and edges:
        status = "connected_not_all_pairs"
    else:
        status = "disconnected_at_0.90"
    return {
        "status": status,
        "n_nodes": len(nodes),
        "n_edges_ge_threshold": len(edges),
        "n_pairs": n_pairs,
        "n_pairs_below_threshold": n_below,
        "n_pairs_missing": n_missing,
        "min_pairwise_identity": min(identities) if identities else None,
        "n_components": len(components),
    }


def levenshtein_identity_lookup(
    cores_by_id: Mapping[str, str],
) -> Callable[[str, str], float | None]:
    def lookup(left: str, right: str) -> float | None:
        core_a = cores_by_id.get(left, "")
        core_b = cores_by_id.get(right, "")
        if not core_a or not core_b:
            return None
        return global_edit_identity(core_a, core_b)

    return lookup


def mmseqs_alignment_lookup(
    alignments: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    identity_key: str = "identity",
) -> Callable[[str, str], float | None]:
    def lookup(left: str, right: str) -> float | None:
        if left == right:
            return 1.0
        row = alignments.get((left, right)) or alignments.get((right, left))
        if row is None:
            return None
        value = row.get(identity_key)
        if value is None or value == "":
            return None
        return float(value)

    return lookup


def source_definition_edge(
    core_a: str, core_b: str
) -> str:
    """Recompute the documented ENA near-duplicate classifier on S5 cores.

    Read-only diagnostic. Does not regenerate source families.
    """
    from ena_review_rules import classify_sequence_relationship

    if not core_a or not core_b:
        return "unrelated"
    return classify_sequence_relationship(core_a, core_b)


def source_definition_lookup(
    cores_by_id: Mapping[str, str],
) -> Callable[[str, str], float | None]:
    def lookup(left: str, right: str) -> float | None:
        rel = source_definition_edge(cores_by_id.get(left, ""), cores_by_id.get(right, ""))
        return 1.0 if rel != "unrelated" else 0.0

    return lookup


def cluster_size_partition(cluster_sizes: Sequence[int]) -> str:
    sizes = sorted((int(size) for size in cluster_sizes), reverse=True)
    total = sum(sizes)
    if not sizes:
        return "0 ->"
    return f"{total} -> " + "+".join(str(size) for size in sizes)


def is_materialised_singleton(family_id: str) -> bool:
    return _blank(family_id).startswith(MATERIALISED_SINGLETON_PREFIX)


def _ena_membership_families(
    membership_rows: Sequence[Mapping[str, str]],
) -> dict[str, list[Mapping[str, str]]]:
    families: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in membership_rows:
        if _blank(row.get("source_db")) != "ena":
            continue
        family_id = _blank(row.get("ena_effective_near_duplicate_family_id"))
        if not family_id:
            continue
        families[family_id].append(row)
    return families


def _declared_multi_member(rows: Sequence[Mapping[str, str]]) -> bool:
    for row in rows:
        size_raw = _blank(row.get("ena_effective_near_duplicate_family_size"))
        try:
            if size_raw and int(size_raw) > 1:
                return True
        except ValueError:
            continue
    return False


def _core_cluster_maps(
    clustered_corpus: Sequence[Mapping[str, str]],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    identity_cluster = {
        _blank(row.get("scientific_identity_id")): _blank(row.get("cluster_id"))
        for row in clustered_corpus
    }
    identity_core = {
        _blank(row.get("scientific_identity_id")): _blank(row.get("sequence_core"))
        for row in clustered_corpus
    }
    core_cluster: dict[str, str] = {}
    for row in clustered_corpus:
        core = _blank(row.get("sequence_core"))
        cluster_id = _blank(row.get("cluster_id"))
        if core:
            core_cluster[core] = cluster_id
    return identity_cluster, identity_core, core_cluster


def family_core_records(
    family_rows: Sequence[Mapping[str, str]],
    *,
    identity_core: Mapping[str, str],
    identity_cluster: Mapping[str, str],
) -> list[dict[str, str]]:
    cores: dict[str, dict[str, str]] = {}
    for row in family_rows:
        identity = _blank(row.get("scientific_identity_id"))
        core = identity_core.get(identity) or _blank(row.get("sequence_core"))
        if not core:
            continue
        cluster_id = identity_cluster.get(identity, "")
        seq_id = make_sequence_id(core)
        current = cores.setdefault(
            core,
            {
                "sequence_core": core,
                "sequence_id": seq_id,
                "sequence_core_sha256": sequence_core_digest(core),
                "cluster_id": cluster_id,
                "length": str(len(core)),
                "experiment_group_ids": set(),  # type: ignore[dict-item]
                "canonical_targets": set(),  # type: ignore[dict-item]
            },
        )
        current["experiment_group_ids"].add(_blank(row.get("experiment_group_id")))  # type: ignore[attr-defined]
        current["canonical_targets"].add(_blank(row.get("canonical_target_name")))  # type: ignore[attr-defined]
        if cluster_id:
            current["cluster_id"] = cluster_id
    records: list[dict[str, str]] = []
    for core, item in cores.items():
        records.append(
            {
                "sequence_core": core,
                "sequence_id": item["sequence_id"],
                "sequence_core_sha256": item["sequence_core_sha256"],
                "cluster_id": item["cluster_id"],
                "length": item["length"],
                "experiment_group_ids": join_sorted_unique(item["experiment_group_ids"]),
                "canonical_targets": join_sorted_unique(item["canonical_targets"]),
            }
        )
    records.sort(key=lambda row: row["sequence_id"])
    return records


def _split_reason_summary(
    *,
    contained: bool,
    lev_status: str,
    mmseqs_status: str,
    source_status: str,
    source_labels: Sequence[str],
    alignments: Mapping[tuple[str, str], Mapping[str, Any]] | None,
    cores_by_id: Mapping[str, str],
    sequence_ids: Sequence[str],
    cluster_by_id: Mapping[str, str],
    representative_by_cluster: Mapping[str, str] | None,
) -> str:
    if contained:
        return "contained"
    reasons: list[str] = []
    truncationish = {
        "prefix/suffix truncation",
        "internal substring/core relationship",
        "extension with flanking bases",
    }
    if any(label in truncationish for label in source_labels):
        reasons.append("source_definition_allows_truncation_or_substring")
    if lev_status == "disconnected_at_0.90":
        reasons.append("global_levenshtein_disconnected_at_0.90")
    elif lev_status == "connected_not_all_pairs":
        reasons.append("global_levenshtein_connected_not_all_pairs")
    if mmseqs_status == "disconnected_at_0.90":
        reasons.append("mmseqs_pairwise_disconnected_at_0.90")
    elif mmseqs_status == "connected_not_all_pairs":
        reasons.append("mmseqs_pairwise_connected_not_all_pairs")
    elif mmseqs_status == "missing":
        reasons.append("mmseqs_pairwise_alignments_unavailable")
    if alignments and representative_by_cluster:
        coverage_fail = 0
        identity_fail = 0
        greedy_fail = 0
        missing_vs_other_rep = 0
        ids = list(sequence_ids)
        for member in ids:
            member_cluster = cluster_by_id.get(member, "")
            other_reps = [
                representative_by_cluster[cluster_id]
                for cluster_id in sorted(set(cluster_by_id.values()))
                if cluster_id and cluster_id != member_cluster and cluster_id in representative_by_cluster
            ]
            if not other_reps:
                continue
            best_id = -1.0
            best_cov_target = -1.0
            found = False
            for rep in other_reps:
                row = alignments.get((member, rep)) or alignments.get((rep, member))
                if row is None:
                    continue
                found = True
                identity = float(row.get("identity") or -1.0)
                tcov = float(row.get("target_coverage") or row.get("tcov") or -1.0)
                if identity > best_id:
                    best_id = identity
                    best_cov_target = tcov
            if not found:
                missing_vs_other_rep += 1
                lev = global_edit_identity(cores_by_id[member], cores_by_id[other_reps[0]]) if other_reps and other_reps[0] in cores_by_id else None
                if lev is not None and lev >= IDENTITY_THRESHOLD:
                    reasons.append("mmseqs_prefilter_or_search_miss_despite_levenshtein_ge_0.90")
            elif best_id < IDENTITY_THRESHOLD:
                identity_fail += 1
            elif best_cov_target >= 0 and best_cov_target < 0.8:
                coverage_fail += 1
            else:
                greedy_fail += 1
        if identity_fail:
            reasons.append("member_vs_other_family_rep_identity_below_0.90")
        if coverage_fail:
            reasons.append("cov_mode_1_or_coverage_0.8")
        if greedy_fail:
            reasons.append("greedy_representative_choice_or_transitivity")
        if missing_vs_other_rep:
            reasons.append("alignment_to_other_family_rep_missing")
    if source_status != "disconnected_at_0.90" and lev_status == "disconnected_at_0.90":
        reasons.append("source_family_broader_than_s5_90_percent_rule")
    if not reasons:
        reasons.append("undetermined_from_available_alignments")
    return join_sorted_unique(reasons)


def validate_ena_families(
    *,
    membership_rows: Sequence[Mapping[str, str]],
    clustered_corpus: Sequence[Mapping[str, str]],
    cluster_rows: Sequence[Mapping[str, str]] | None = None,
    mmseqs_alignments: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
    representative_by_cluster: Mapping[str, str] | None = None,
    method_label: str = "cluster",
) -> EnaValidationResult:
    identity_cluster, identity_core, _core_cluster = _core_cluster_maps(clustered_corpus)
    families = _ena_membership_families(membership_rows)
    cluster_to_ena_families: dict[str, set[str]] = defaultdict(set)
    family_rows: list[dict[str, str]] = []
    core_to_family: dict[str, str] = {}

    for family_id, rows in families.items():
        cores = family_core_records(
            rows,
            identity_core=identity_core,
            identity_cluster=identity_cluster,
        )
        clusters = [row["cluster_id"] for row in cores if row["cluster_id"]]
        cluster_counts = Counter(clusters)
        for cluster_id in cluster_counts:
            cluster_to_ena_families[cluster_id].add(family_id)
        for row in cores:
            core_to_family[row["sequence_core"]] = family_id
        lengths = [int(row["length"]) for row in cores]
        seq_ids = [row["sequence_id"] for row in cores]
        cores_by_id = {row["sequence_id"]: row["sequence_core"] for row in cores}
        cluster_by_id = {row["sequence_id"]: row["cluster_id"] for row in cores}
        lev = pairwise_graph_status(seq_ids, levenshtein_identity_lookup(cores_by_id))
        if mmseqs_alignments is None:
            mmseqs_graph = {"status": "missing"}
        else:
            mmseqs_graph = pairwise_graph_status(
                seq_ids, mmseqs_alignment_lookup(mmseqs_alignments)
            )
        source_edges: list[str] = []
        for i, left in enumerate(seq_ids):
            for right in seq_ids[i + 1 :]:
                label = source_definition_edge(cores_by_id[left], cores_by_id[right])
                if label != "unrelated":
                    source_edges.append(label)
        source_graph = pairwise_graph_status(
            seq_ids, source_definition_lookup(cores_by_id), threshold=0.5
        )
        if source_graph["status"] == "all_pairs_ge_0.90":
            source_status = "all_pairs_related_under_source_definition"
        elif source_graph["status"] == "connected_not_all_pairs":
            source_status = "connected_under_source_definition"
        elif len(seq_ids) <= 1:
            source_status = "singleton"
        else:
            source_status = "disconnected_under_source_definition"
        contained = len(cluster_counts) == 1
        family_rows.append(
            fill_row(
                FAMILY_REPORT_COLUMNS,
                {
                    "ena_family_id": family_id,
                    "declared_multi_member": bool_token(_declared_multi_member(rows)),
                    "n_s5_ena_membership_rows": str(len(rows)),
                    "n_s5_ena_sequence_cores": str(len(cores)),
                    "n_clusters": str(len(cluster_counts)),
                    "contained_in_one_cluster": bool_token(contained),
                    "cluster_size_partition": cluster_size_partition(cluster_counts.values()),
                    "min_core_length": str(min(lengths)) if lengths else "",
                    "median_core_length": _median_token(lengths),
                    "max_core_length": str(max(lengths)) if lengths else "",
                    "lengths_differ": bool_token(len(set(lengths)) > 1),
                    "experiment_group_ids": join_sorted_unique(
                        row.get("experiment_group_id") for row in rows
                    ),
                    "canonical_targets": join_sorted_unique(
                        row.get("canonical_target_name") for row in rows
                    ),
                    "levenshtein_graph_status": lev["status"],
                    "mmseqs_pairwise_graph_status": mmseqs_graph["status"],
                    "source_definition_graph_status": source_status,
                    "source_definition_edge_labels": join_sorted_unique(source_edges),
                    "split_reason_summary": _split_reason_summary(
                        contained=contained,
                        lev_status=lev["status"],
                        mmseqs_status=str(mmseqs_graph["status"]),
                        source_status=source_status,
                        source_labels=source_edges,
                        alignments=mmseqs_alignments,
                        cores_by_id=cores_by_id,
                        sequence_ids=seq_ids,
                        cluster_by_id=cluster_by_id,
                        representative_by_cluster=representative_by_cluster,
                    ),
                    "cluster_ids": "|".join(sorted(cluster_counts)),
                },
            )
        )
    family_rows.sort(key=lambda row: row["ena_family_id"])

    # Same 16-family cohort as S5C: >=2 ENA membership rows in S5.
    multi_member = [
        row for row in family_rows if int(row["n_s5_ena_membership_rows"]) >= 2
    ]
    singleton_source = [
        row for row in family_rows if int(row["n_s5_ena_membership_rows"]) == 1
    ]

    cluster_members: dict[str, set[str]] = defaultdict(set)
    cluster_cores: dict[str, set[str]] = defaultdict(set)
    cluster_sources: dict[str, set[str]] = defaultdict(set)
    sequence_cluster: dict[str, str] = {}
    for row in clustered_corpus:
        cluster_id = _blank(row.get("cluster_id"))
        core = _blank(row.get("sequence_core"))
        seq_id = _blank(row.get("sequence_id")) or make_sequence_id(core)
        cluster_cores[cluster_id].add(core)
        sequence_cluster[seq_id] = cluster_id
        sources = set(split_pipe(row.get("contributing_sources") or ""))
        if _blank(row.get("source_db")):
            sources.add(_blank(row.get("source_db")))
        cluster_sources[cluster_id].update(sources)
        cluster_members[cluster_id].add(seq_id)

    if cluster_rows:
        for row in cluster_rows:
            sequence_cluster[row["member_sequence_id"]] = row["cluster_id"]

    real_family_ids = {
        row["ena_family_id"]
        for row in family_rows
        if row["declared_multi_member"] == "true" or int(row["n_s5_ena_membership_rows"]) >= 2
    }
    real_family_ids = {
        row["ena_family_id"]
        for row in multi_member
        if not is_materialised_singleton(row["ena_family_id"])
    }
    singleton_ids = {row["ena_family_id"] for row in singleton_source}

    singleton_rows: list[dict[str, str]] = []
    for row in singleton_source:
        family_id = row["ena_family_id"]
        cluster_ids = split_pipe(row["cluster_ids"])
        cluster_id = cluster_ids[0] if cluster_ids else ""
        ena_families_here = cluster_to_ena_families.get(cluster_id, set())
        other_ena = ena_families_here - {family_id}
        real_here = sorted(fam for fam in other_ena if fam in real_family_ids)
        singleton_here = sorted(fam for fam in other_ena if fam in singleton_ids)
        ena_cores = 0
        non_ena = 0
        for core in cluster_cores.get(cluster_id, set()):
            if core in core_to_family:
                ena_cores += 1
            else:
                non_ena += 1
        if other_ena and real_here:
            status = "cluster_with_real_multi_member_ena_family"
        elif other_ena and singleton_here:
            status = "cluster_with_another_materialised_singleton"
        elif other_ena:
            status = "cluster_with_another_ena_family"
        elif ena_cores > 1:
            status = "cluster_with_another_ena_core"
        elif non_ena:
            status = "cluster_only_with_non_ena_sequences"
        else:
            status = "isolated_from_every_other_ena_core"
        conflict = ""
        if status not in {
            "isolated_from_every_other_ena_core",
            "cluster_only_with_non_ena_sequences",
        }:
            other_groups = set()
            other_targets = set()
            this_groups = set(split_pipe(row["experiment_group_ids"]))
            this_targets = set(split_pipe(row["canonical_targets"]))
            for other_id in sorted(other_ena):
                other_row = next(item for item in family_rows if item["ena_family_id"] == other_id)
                other_groups.update(split_pipe(other_row["experiment_group_ids"]))
                other_targets.update(split_pipe(other_row["canonical_targets"]))
            if this_groups and other_groups and this_groups.isdisjoint(other_groups):
                conflict = "source_definition_scoped_by_experiment_group"
            elif this_targets and other_targets and this_targets.isdisjoint(other_targets):
                conflict = "source_definition_scoped_by_target"
            else:
                conflict = "possible_source_grouping_miss_or_core_trim_change"
        seq_id = ""
        for member_row in families[family_id]:
            identity = _blank(member_row.get("scientific_identity_id"))
            core = identity_core.get(identity) or _blank(member_row.get("sequence_core"))
            if core:
                seq_id = make_sequence_id(core)
                break
        singleton_rows.append(
            fill_row(
                SINGLETON_AUDIT_COLUMNS,
                {
                    "ena_family_id": family_id,
                    "sequence_id": seq_id,
                    "cluster_id": cluster_id,
                    "n_ena_cores_in_cluster": str(ena_cores),
                    "n_materialised_singletons_in_cluster": str(len(singleton_here) + (1 if family_id in singleton_ids else 0)),
                    "n_real_multi_member_families_in_cluster": str(len(real_here) + (1 if family_id in real_family_ids else 0)),
                    "n_non_ena_sequences_in_cluster": str(non_ena),
                    "ena_internal_status": status,
                    "conflict_reason": conflict,
                },
            )
        )
    singleton_rows.sort(key=lambda row: row["ena_family_id"])

    cross_family_rows: list[dict[str, str]] = []
    for cluster_id, fams in sorted(cluster_to_ena_families.items()):
        if len(fams) <= 1:
            continue
        real_here = sorted(fam for fam in fams if fam in real_family_ids)
        singleton_here = sorted(fam for fam in fams if fam in singleton_ids)
        if len(real_here) > 1 and singleton_here:
            mix = "real_families_plus_materialised_singletons"
        elif len(real_here) > 1:
            mix = "multiple_real_ena_families"
        elif len(singleton_here) > 1 and real_here:
            mix = "real_family_plus_materialised_singletons"
        elif len(singleton_here) > 1:
            mix = "multiple_materialised_singletons"
        else:
            mix = "multiple_ena_families"
        cross_family_rows.append(
            fill_row(
                CROSS_FAMILY_COLUMNS,
                {
                    "cluster_id": cluster_id,
                    "n_ena_families": str(len(fams)),
                    "n_real_multi_member_families": str(len(real_here)),
                    "n_materialised_singleton_families": str(len(singleton_here)),
                    "mix_kind": mix,
                    "ena_family_ids": "|".join(sorted(fams)),
                },
            )
        )

    contained = [row for row in multi_member if row["contained_in_one_cluster"] == "true"]
    split = [row for row in multi_member if row["contained_in_one_cluster"] == "false"]
    contained_cores = sum(int(row["n_s5_ena_sequence_cores"]) for row in contained)
    split_cores = sum(int(row["n_s5_ena_sequence_cores"]) for row in split)
    total_multi_cores = contained_cores + split_cores
    n_multi = len(multi_member)
    containment_rate = (len(contained) / n_multi) if n_multi else None

    isolated = [
        row
        for row in singleton_rows
        if row["ena_internal_status"] == "isolated_from_every_other_ena_core"
    ]
    with_singleton = [
        row
        for row in singleton_rows
        if row["ena_internal_status"] == "cluster_with_another_materialised_singleton"
    ]
    with_real = [
        row
        for row in singleton_rows
        if row["ena_internal_status"] == "cluster_with_real_multi_member_ena_family"
    ]
    with_non_ena = [
        row
        for row in singleton_rows
        if row["ena_internal_status"] == "cluster_only_with_non_ena_sequences"
    ]
    ena_internal_fail = [
        row
        for row in singleton_rows
        if row["ena_internal_status"]
        not in {
            "isolated_from_every_other_ena_core",
            "cluster_only_with_non_ena_sequences",
        }
    ]
    documented_scope = [
        row
        for row in ena_internal_fail
        if row["conflict_reason"]
        in {
            "source_definition_scoped_by_experiment_group",
            "source_definition_scoped_by_target",
        }
    ]
    n_singleton = len(singleton_rows)
    singleton_separation_rate = (
        (n_singleton - len(ena_internal_fail)) / n_singleton if n_singleton else None
    )

    incompatible_families = [
        row
        for row in multi_member
        if row["levenshtein_graph_status"] == "disconnected_at_0.90"
    ]

    metrics = {
        "method_label": method_label,
        "n_ena_family_ids_represented": len(family_rows),
        "n_declared_multi_member_families_represented": sum(
            1 for row in family_rows if row["declared_multi_member"] == "true"
        ),
        "n_multi_member_families_with_at_least_two_s5_members": n_multi,
        "n_multi_member_families_contained_in_one_cluster": len(contained),
        "n_multi_member_families_split_across_gt1_cluster": len(split),
        "family_containment_rate": containment_rate,
        "n_multi_member_family_cores": total_multi_cores,
        "n_contained_family_cores": contained_cores,
        "n_split_family_cores": split_cores,
        "multi_member_family_ids": [row["ena_family_id"] for row in multi_member],
        "contained_family_ids": [row["ena_family_id"] for row in contained],
        "split_family_ids": [row["ena_family_id"] for row in split],
        "n_singleton_source_families": n_singleton,
        "n_singletons_isolated_from_every_other_ena_core": len(isolated),
        "n_singletons_clustered_with_another_materialised_singleton": len(with_singleton),
        "n_singletons_clustered_with_real_multi_member_family": len(with_real),
        "n_singletons_clustered_only_with_non_ena_sequences": len(with_non_ena),
        "n_ena_internal_singleton_conflicts": len(ena_internal_fail),
        "n_singleton_conflicts_documented_experiment_or_target_scope": len(documented_scope),
        "singleton_ena_internal_separation_rate": singleton_separation_rate,
        "n_clusters_containing_multiple_ena_families": len(cross_family_rows),
        "n_clusters_combining_distinct_real_ena_families": sum(
            1
            for row in cross_family_rows
            if int(row["n_real_multi_member_families"]) > 1
        ),
        "n_clusters_mixing_real_families_and_singletons": sum(
            1
            for row in cross_family_rows
            if int(row["n_real_multi_member_families"]) >= 1
            and int(row["n_materialised_singleton_families"]) >= 1
        ),
        "n_clusters_mixing_multiple_materialised_singletons": sum(
            1
            for row in cross_family_rows
            if int(row["n_materialised_singleton_families"]) > 1
        ),
        "n_families_incompatible_with_90_percent_global_identity": len(incompatible_families),
        "incompatible_family_ids": [row["ena_family_id"] for row in incompatible_families],
        "e5_or_out_of_s5_members_not_counted_as_s5_failure": True,
    }
    return EnaValidationResult(
        family_rows=family_rows,
        singleton_rows=singleton_rows,
        cross_family_rows=cross_family_rows,
        metrics=metrics,
    )


def family_containment_pass(metrics: Mapping[str, Any], *, expected_families: int = 16) -> bool:
    return (
        int(metrics.get("n_multi_member_families_with_at_least_two_s5_members") or 0)
        == expected_families
        and int(metrics.get("n_multi_member_families_contained_in_one_cluster") or 0)
        == expected_families
        and int(metrics.get("n_multi_member_families_split_across_gt1_cluster") or 0) == 0
    )


def singleton_separation_acceptable(metrics: Mapping[str, Any]) -> bool:
    """Non-ENA neighbours are allowed. Remaining ENA-internal conflicts must be scoped."""
    conflicts = int(metrics.get("n_ena_internal_singleton_conflicts") or 0)
    documented = int(
        metrics.get("n_singleton_conflicts_documented_experiment_or_target_scope") or 0
    )
    return conflicts == documented


def ground_truth_incompatible_with_90(metrics: Mapping[str, Any]) -> bool:
    return int(metrics.get("n_families_incompatible_with_90_percent_global_identity") or 0) > 0


def compare_methods(
    mmseqs_metrics: Mapping[str, Any],
    cdhit_metrics: Mapping[str, Any],
    *,
    mmseqs_structural: Mapping[str, Any] | None = None,
    cdhit_structural: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    mmseqs_structural = mmseqs_structural or {}
    cdhit_structural = cdhit_structural or {}

    def _fmt(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:.4f}"
        if isinstance(value, bool):
            return "yes" if value else "no"
        return str(value)

    rows = [
        ("total_clusters", mmseqs_structural.get("n_clusters"), cdhit_structural.get("n_clusters")),
        (
            "singleton_clusters",
            mmseqs_structural.get("n_singleton_clusters"),
            cdhit_structural.get("n_singleton_clusters"),
        ),
        (
            "multi_sequence_clusters",
            mmseqs_structural.get("n_multi_sequence_clusters"),
            cdhit_structural.get("n_multi_sequence_clusters"),
        ),
        (
            "largest_cluster",
            mmseqs_structural.get("largest_cluster_size"),
            cdhit_structural.get("largest_cluster_size"),
        ),
        (
            "ena_families_wholly_contained",
            mmseqs_metrics.get("n_multi_member_families_contained_in_one_cluster"),
            cdhit_metrics.get("n_multi_member_families_contained_in_one_cluster"),
        ),
        (
            "ena_family_containment_rate",
            mmseqs_metrics.get("family_containment_rate"),
            cdhit_metrics.get("family_containment_rate"),
        ),
        (
            "member_weighted_contained_family_cores",
            f"{mmseqs_metrics.get('n_contained_family_cores')}/{mmseqs_metrics.get('n_multi_member_family_cores')}",
            f"{cdhit_metrics.get('n_contained_family_cores')}/{cdhit_metrics.get('n_multi_member_family_cores')}",
        ),
        (
            "materialised_ena_singleton_ena_internal_separation",
            mmseqs_metrics.get("singleton_ena_internal_separation_rate"),
            cdhit_metrics.get("singleton_ena_internal_separation_rate"),
        ),
        (
            "clusters_combining_distinct_ena_families",
            mmseqs_metrics.get("n_clusters_containing_multiple_ena_families"),
            cdhit_metrics.get("n_clusters_containing_multiple_ena_families"),
        ),
        (
            "all_1144_cores_assigned",
            mmseqs_structural.get("all_cores_assigned", True),
            cdhit_structural.get("all_cores_assigned", True),
        ),
        (
            "deterministic_rerun",
            mmseqs_structural.get("determinism_ok", True),
            cdhit_structural.get("determinism_ok"),
        ),
    ]
    return [
        fill_row(
            METHOD_COMPARISON_COLUMNS,
            {"metric": metric, "mmseqs": _fmt(mmseqs), "cdhit": _fmt(cdhit)},
        )
        for metric, mmseqs, cdhit in rows
    ]


def adjudicate_clustering_methods(
    *,
    mmseqs_metrics: Mapping[str, Any],
    cdhit_metrics: Mapping[str, Any],
    cdhit_mechanical_ok: bool,
    expected_families: int = 16,
) -> dict[str, Any]:
    """Apply the S5D acceptance hierarchy. No parameter-tuning path exists."""
    gt_conflict = ground_truth_incompatible_with_90(cdhit_metrics) or ground_truth_incompatible_with_90(
        mmseqs_metrics
    )
    cdhit_contains = family_containment_pass(
        cdhit_metrics, expected_families=expected_families
    )
    cdhit_singletons = singleton_separation_acceptable(cdhit_metrics)
    mmseqs_contains = family_containment_pass(
        mmseqs_metrics, expected_families=expected_families
    )
    cdhit_split = int(
        cdhit_metrics.get("n_multi_member_families_split_across_gt1_cluster") or 0
    )
    mmseqs_split = int(
        mmseqs_metrics.get("n_multi_member_families_split_across_gt1_cluster") or 0
    )
    cdhit_contained_n = int(
        cdhit_metrics.get("n_multi_member_families_contained_in_one_cluster") or 0
    )
    mmseqs_contained_n = int(
        mmseqs_metrics.get("n_multi_member_families_contained_in_one_cluster") or 0
    )

    if gt_conflict:
        decision = DECISION_GROUND_TRUTH_CONTRADICTION
        case = "D"
        accept_cdhit = False
        create_final_artefacts = False
    elif cdhit_contains and cdhit_singletons and cdhit_mechanical_ok:
        decision = DECISION_ACCEPT_CDHIT
        case = "A"
        accept_cdhit = True
        create_final_artefacts = True
    else:
        decision = DECISION_BOTH_FAIL
        accept_cdhit = False
        create_final_artefacts = False
        if cdhit_contained_n > mmseqs_contained_n and cdhit_split >= 1:
            case = "B"
        else:
            case = "C"

    return {
        "decision": decision,
        "case": case,
        "accept_cdhit": accept_cdhit,
        "create_final_artefacts": create_final_artefacts,
        "final_clustering_method": "cd-hit-est" if accept_cdhit else "",
        "reason": (
            "mmseqs_poor_ena_family_recall"
            if accept_cdhit
            else (
                "ena_families_incompatible_with_90_percent_rule"
                if decision == DECISION_GROUND_TRUTH_CONTRADICTION
                else "both_prespecified_methods_fail_ena_validation"
            )
        ),
        "mmseqs_contained": mmseqs_contained_n,
        "cdhit_contained": cdhit_contained_n,
        "mmseqs_split": mmseqs_split,
        "cdhit_split": cdhit_split,
        "cdhit_mechanical_ok": cdhit_mechanical_ok,
        "parameter_tuning_path_exists": False,
        "third_algorithm_invented": False,
        "mmseqs_selected_because_it_ran_first": False,
    }


def ena_validation_pass_from_clusters(
    *,
    family_to_clusters: Mapping[str, Sequence[str]],
    singleton_to_cluster_ena_cores: Mapping[str, int],
    singleton_non_ena_only: Mapping[str, bool] | None = None,
    out_of_s5_family_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Synthetic helper used by tests. Does not count E5/out-of-S5 members."""
    ignored = set(out_of_s5_family_ids or ())
    relevant = {
        family_id: clusters
        for family_id, clusters in family_to_clusters.items()
        if family_id not in ignored
    }
    multi = {
        family_id: clusters
        for family_id, clusters in relevant.items()
        if not is_materialised_singleton(family_id)
    }
    contained = [family_id for family_id, clusters in multi.items() if len(set(clusters)) == 1]
    split = [family_id for family_id, clusters in multi.items() if len(set(clusters)) > 1]
    singleton_failures = []
    singleton_non_ena = []
    for family_id, n_ena_cores in singleton_to_cluster_ena_cores.items():
        if family_id in ignored:
            continue
        if n_ena_cores > 1:
            singleton_failures.append(family_id)
        elif singleton_non_ena_only and singleton_non_ena_only.get(family_id):
            singleton_non_ena.append(family_id)
    return {
        "contained_family_ids": sorted(contained),
        "split_family_ids": sorted(split),
        "family_containment_pass": not split and bool(multi),
        "singleton_ena_internal_failures": sorted(singleton_failures),
        "singleton_non_ena_neighbours_not_failures": sorted(singleton_non_ena),
        "out_of_s5_ignored": sorted(ignored),
    }

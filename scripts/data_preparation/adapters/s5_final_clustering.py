"""S5E leakage-safe final cluster construction.

Final ``cluster_id`` is the connected component of:

* frozen S5C MMseqs sequence-similarity clusters, and
* positive must-link constraints from retained real multi-member ENA
  ``near_duplicate_family_id`` values.

This module does not rerun MMseqs, does not select CD-HIT, does not
treat materialised ENA singleton IDs as cannot-links, and does not
begin S6/S7. Frozen S5A/S5C artefacts are read-only.
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Mapping, Sequence

from adapters.s4_scientific_common import (
    ScientificProposalError,
    bool_token,
    fill_row,
    split_pipe,
)
from adapters.s5_ena_clustering_validation import (
    is_materialised_singleton,
    validate_ena_families,
)
from adapters.s5_exact_dedup import (
    CORPUS_DEDUP_COLUMNS,
    DEFAULT_OVERLAP_SOURCES,
    join_sorted_unique,
    _blank,
)
from adapters.s5_sequence_clustering import (
    CLUSTER_ID_PREFIX,
    FROZEN_CORPUS_DEDUP_NAME,
    expected_count_errors,
    make_sequence_id,
    multi_target_preservation,
    sequence_core_digest,
    stable_cluster_id,
)
from adapters.target_extraction_common import SEQ_LEAK_RE

S5FinalClusteringError = ScientificProposalError

MERGE_MMSEQS_ONLY = "mmseqs_only"
MERGE_MMSEQS_PLUS_ENA = "mmseqs_plus_ena_family_must_link"

AUTHORISED_PARAMETERS: dict[str, Any] = {
    "base_sequence_clustering_method": "mmseqs",
    "min_seq_id": 0.90,
    "coverage": 0.80,
    "cov_mode": 1,
    "sensitivity": 7.5,
    "family_constraint_source": "ena.near_duplicate_family_id",
    "family_constraint_semantics": "positive_must_link_only",
    "materialised_singletons_as_cannot_link": False,
    "cd_hit_selected": False,
}

FORBIDDEN_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "balancing",
        "cdhit_selected_true",
        "ft_ref_eval",
        "ft_ref_eval_assignment",
        "max_target_fraction",
        "overwrite_s5c",
        "parameter_tuning",
        "partition",
        "target_cap",
        "train_validation_split",
        "train_validation_test_split",
        "u_to_t_derived_corpus",
    }
)

FROZEN_S5C_NAMES: frozenset[str] = frozenset(
    {
        "clusters.tsv",
        "corpus_clustered.csv",
        "cluster_summary.csv",
        "s5c_clustering_manifest.json",
        "s5c_sequence_clustering_report.md",
        "s5c_rna_u_preflight.json",
        "sequence_clustering_input.csv",
        "sequence_clustering_input.fasta",
        "sequence_scientific_identity_map.csv",
        "cluster_identity_audit.csv",
        "ena_family_clustering_diagnostics.csv",
        FROZEN_CORPUS_DEDUP_NAME,
        "exact_duplicate_membership.csv",
        "exact_duplicate_groups.csv",
        "s5a_exact_dedup_report.md",
        "s5b_validation_report.md",
        "s5b_validation_summary.json",
    }
)

CLUSTERS_FINAL_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "sequence_id",
    "sequence_core_sha256",
    "sequence_length",
    "sequence_cluster_id_mmseqs",
    "mmseqs_representative_sequence_id",
    "is_mmseqs_sequence_representative",
    "final_representative_sequence_id",
    "final_representative_sequence_core_sha256",
    "member_is_final_sequence_representative",
    "merge_basis",
    "ena_family_must_link_ids",
)

CORPUS_CLUSTERED_FINAL_COLUMNS: tuple[str, ...] = (
    *CORPUS_DEDUP_COLUMNS,
    "sequence_id",
    "sequence_core_sha256",
    "sequence_cluster_id_mmseqs",
    "mmseqs_representative_sequence_id",
    "mmseqs_representative_sequence_core_sha256",
    "is_mmseqs_sequence_representative",
    "is_mmseqs_scientific_representative",
    "final_representative_sequence_id",
    "final_representative_sequence_core_sha256",
)

CLUSTER_SUMMARY_FINAL_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "n_distinct_sequences",
    "n_scientific_identities",
    "representative_sequence_id",
    "representative_sequence_core_sha256",
    "representative_scientific_identity_id",
    "min_sequence_length",
    "median_sequence_length",
    "max_sequence_length",
    "n_targets",
    "n_sources",
    "contains_multi_target_identical_core",
    "ena_provenance_present",
    "n_mmseqs_components",
    "mmseqs_cluster_ids",
    "n_ena_family_must_links",
    "ena_family_must_link_ids",
    "differs_from_single_mmseqs_component",
    "merge_basis",
)

CLUSTER_UNION_PROVENANCE_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "n_sequence_cores",
    "n_scientific_identities",
    "n_mmseqs_components",
    "mmseqs_cluster_ids",
    "n_ena_family_must_links",
    "ena_family_must_link_ids",
    "n_ena_families_that_bridged_mmseqs_components",
    "ena_family_ids_that_bridged_mmseqs_components",
    "differs_from_single_mmseqs_component",
    "merge_basis",
    "n_canonical_targets",
    "contributing_sources",
)

FAMILY_CONTAINMENT_COLUMNS: tuple[str, ...] = (
    "ena_family_id",
    "declared_multi_member",
    "n_s5_ena_sequence_cores",
    "n_mmseqs_clusters_before_union",
    "n_final_clusters",
    "contained_in_one_final_cluster",
    "created_union_edge",
    "final_cluster_ids",
)

MUST_LINK_COHORT_COLUMNS: tuple[str, ...] = (
    "ena_family_id",
    "declared_multi_member",
    "n_s5_ena_membership_rows",
    "n_s5_ena_sequence_cores",
    "must_link_applied",
    "sequence_ids",
    "mmseqs_cluster_ids",
)


@dataclass
class UnionFind:
    """Deterministic union-find. Final IDs never depend on parent labels."""

    parent: dict[str, str] = field(default_factory=dict)

    def add(self, node: str) -> None:
        node = _blank(node)
        if node and node not in self.parent:
            self.parent[node] = node

    def find(self, node: str) -> str:
        node = _blank(node)
        if node not in self.parent:
            self.add(node)
        root = node
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[node] != root:
            nxt = self.parent[node]
            self.parent[node] = root
            node = nxt
        return root

    def union(self, left: str, right: str) -> None:
        root_l, root_r = self.find(left), self.find(right)
        if root_l == root_r:
            return
        if root_l > root_r:
            root_l, root_r = root_r, root_l
        self.parent[root_r] = root_l

    def components(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for node in self.parent:
            grouped[self.find(node)].append(node)
        return {root: sorted(members) for root, members in grouped.items()}


@dataclass
class FinalClusteringResult:
    clusters_final: list[dict[str, str]]
    clustered_corpus: list[dict[str, str]]
    cluster_summary: list[dict[str, str]]
    union_provenance: list[dict[str, str]]
    family_containment: list[dict[str, str]]
    must_link_cohort: list[dict[str, str]]
    diagnostics: dict[str, Any] = field(default_factory=dict)


def enforce_authorised_parameters(config: Mapping[str, Any]) -> None:
    forbidden = sorted(set(config) & FORBIDDEN_CONFIG_KEYS)
    if forbidden:
        raise S5FinalClusteringError(
            "S5E config contains forbidden S6/S7 keys: " + ", ".join(forbidden)
        )
    if config.get("cd_hit_selected") is True:
        raise S5FinalClusteringError("S5E must not select CD-HIT as the clustering method")
    for key, expected in AUTHORISED_PARAMETERS.items():
        if key not in config:
            raise S5FinalClusteringError(f"S5E config missing required parameter {key}")
        observed = config[key]
        if isinstance(expected, float):
            try:
                value = float(observed)
            except (TypeError, ValueError) as exc:
                raise S5FinalClusteringError(
                    f"S5E parameter {key} must be numeric; got {observed!r}"
                ) from exc
            if not math.isclose(value, expected, rel_tol=0.0, abs_tol=1e-12):
                raise S5FinalClusteringError(
                    f"S5E parameter {key}={observed!r} is not authorised; required {expected}"
                )
        elif observed != expected:
            raise S5FinalClusteringError(
                f"S5E parameter {key}={observed!r} is not authorised; required {expected!r}"
            )


def assert_not_frozen_s5_path(path: Any) -> None:
    name = getattr(path, "name", str(path))
    if name in FROZEN_S5C_NAMES:
        raise S5FinalClusteringError(f"refusing to overwrite frozen S5 artefact {name}")
    if name == FROZEN_CORPUS_DEDUP_NAME:
        raise S5FinalClusteringError("refusing to write onto frozen corpus_dedup.csv")


def _declared_multi_member(rows: Sequence[Mapping[str, str]]) -> bool:
    for row in rows:
        size_raw = _blank(row.get("ena_effective_near_duplicate_family_size"))
        try:
            if size_raw and int(size_raw) > 1:
                return True
        except ValueError:
            continue
    return False


def _format_median(values: Sequence[int]) -> str:
    if not values:
        return ""
    value = median(values)
    if float(value) == int(value):
        return str(int(value))
    return str(value)


def _sequence_id_for(row: Mapping[str, str]) -> str:
    seq_id = _blank(row.get("sequence_id"))
    if seq_id:
        return seq_id
    core = _blank(row.get("sequence_core"))
    if not core:
        member = _blank(row.get("member_sequence_id"))
        if member:
            return member
        raise S5FinalClusteringError("sequence_id / sequence_core required")
    return make_sequence_id(core)


def index_mmseqs_clusters(
    cluster_rows: Sequence[Mapping[str, str]],
) -> dict[str, dict[str, Any]]:
    by_cluster: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    by_member: dict[str, Mapping[str, str]] = {}
    for row in cluster_rows:
        cluster_id = _blank(row.get("cluster_id") or row.get("sequence_cluster_id_mmseqs"))
        member = _blank(row.get("member_sequence_id") or row.get("sequence_id"))
        if not cluster_id or not member:
            raise S5FinalClusteringError("MMseqs cluster row missing cluster_id or member")
        by_cluster[cluster_id].append(row)
        if member in by_member:
            raise S5FinalClusteringError(f"sequence {member} assigned to multiple MMseqs clusters")
        by_member[member] = row
    indexed: dict[str, dict[str, Any]] = {}
    for cluster_id, members in by_cluster.items():
        reps = [
            _blank(row.get("member_sequence_id") or row.get("sequence_id"))
            for row in members
            if row.get("member_is_mmseqs_representative") == "true"
            or row.get("is_mmseqs_sequence_representative") == "true"
        ]
        if len(reps) != 1:
            raise S5FinalClusteringError(
                f"MMseqs cluster {cluster_id} has {len(reps)} sequence representatives"
            )
        member_ids = sorted(
            {
                _blank(row.get("member_sequence_id") or row.get("sequence_id"))
                for row in members
            }
        )
        digests = [
            _blank(row.get("member_sequence_core_sha256") or row.get("sequence_core_sha256"))
            for row in members
        ]
        indexed[cluster_id] = {
            "cluster_id": cluster_id,
            "members": member_ids,
            "representative_sequence_id": reps[0],
            "n_sequences": len(member_ids),
            "member_rows": members,
            "digests": sorted(digests),
        }
    if len(by_member) != len(cluster_rows):
        raise S5FinalClusteringError("MMseqs cluster membership is not unique")
    return indexed


def derive_ena_must_link_cohort(
    membership_rows: Sequence[Mapping[str, str]],
    *,
    sequence_id_by_core: Mapping[str, str] | None = None,
    mmseqs_cluster_by_seq: Mapping[str, str] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], dict[str, Any]]:
    """Real source-assigned multi-member ENA families only.

    Materialised ``ena_singleton_*`` IDs create no must-link edges.
    A declared multi-member family with only one surviving S5 core
    creates no union edge.
    """
    families: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in membership_rows:
        if _blank(row.get("source_db")) != "ena":
            continue
        family_id = _blank(row.get("ena_effective_near_duplicate_family_id"))
        if not family_id or is_materialised_singleton(family_id):
            continue
        families[family_id].append(row)

    cohort_rows: list[dict[str, str]] = []
    must_links: list[dict[str, Any]] = []
    for family_id, rows in sorted(families.items()):
        cores = sorted(
            {
                _blank(row.get("sequence_core"))
                for row in rows
                if _blank(row.get("sequence_core"))
            }
        )
        seq_ids = []
        for core in cores:
            seq_ids.append(
                (sequence_id_by_core or {}).get(core) or make_sequence_id(core)
            )
        mmseqs_ids = sorted(
            {
                (mmseqs_cluster_by_seq or {}).get(seq_id, "")
                for seq_id in seq_ids
                if (mmseqs_cluster_by_seq or {}).get(seq_id)
            }
        )
        declared = _declared_multi_member(rows)
        apply_link = declared and len(cores) >= 2
        cohort_rows.append(
            fill_row(
                MUST_LINK_COHORT_COLUMNS,
                {
                    "ena_family_id": family_id,
                    "declared_multi_member": bool_token(declared),
                    "n_s5_ena_membership_rows": str(len(rows)),
                    "n_s5_ena_sequence_cores": str(len(cores)),
                    "must_link_applied": bool_token(apply_link),
                    "sequence_ids": "|".join(seq_ids),
                    "mmseqs_cluster_ids": "|".join(mmseqs_ids),
                },
            )
        )
        if apply_link:
            must_links.append(
                {
                    "ena_family_id": family_id,
                    "sequence_cores": cores,
                    "sequence_ids": seq_ids,
                    "mmseqs_cluster_ids": mmseqs_ids,
                }
            )
    represented = [row["ena_family_id"] for row in cohort_rows if row["declared_multi_member"] == "true"]
    diagnostics = {
        "n_real_multi_member_family_ids_represented": len(represented),
        "n_families_with_ge2_retained_s5_ena_cores": len(must_links),
        "real_multi_member_family_ids": represented,
        "must_link_family_ids": [item["ena_family_id"] for item in must_links],
        "materialised_singletons_as_must_link": False,
    }
    return cohort_rows, must_links, diagnostics


def union_mmseqs_and_family_must_links(
    mmseqs_index: Mapping[str, Mapping[str, Any]],
    must_links: Sequence[Mapping[str, Any]],
    *,
    shuffle_seed: int | None = None,
) -> dict[str, str]:
    """Return ``sequence_id -> final component root`` after global union.

    ``shuffle_seed`` only permutes processing order. Component membership
    must be independent of that order; stable cluster IDs are derived
    later from sorted member hashes, not from union-find roots.
    """
    uf = UnionFind()
    mmseqs_items = list(mmseqs_index.items())
    family_items = list(must_links)
    if shuffle_seed is not None:
        rng = random.Random(shuffle_seed)
        rng.shuffle(mmseqs_items)
        rng.shuffle(family_items)

    for _cluster_id, payload in mmseqs_items:
        members = list(payload["members"])
        if shuffle_seed is not None:
            random.Random(shuffle_seed).shuffle(members)
        for member in members:
            uf.add(member)
        for left, right in zip(members, members[1:]):
            uf.union(left, right)

    for family in family_items:
        seq_ids = list(family["sequence_ids"])
        if shuffle_seed is not None:
            random.Random(shuffle_seed).shuffle(seq_ids)
        for seq_id in seq_ids:
            uf.add(seq_id)
        for left, right in zip(seq_ids, seq_ids[1:]):
            uf.union(left, right)

    return {seq_id: uf.find(seq_id) for seq_id in uf.parent}


def _final_membership_from_roots(
    seq_to_root: Mapping[str, str],
    seq_digest: Mapping[str, str],
) -> dict[str, str]:
    members_by_root: dict[str, list[str]] = defaultdict(list)
    for seq_id, root in seq_to_root.items():
        members_by_root[root].append(seq_id)
    seq_to_final: dict[str, str] = {}
    for members in members_by_root.values():
        digests = [seq_digest[seq_id] for seq_id in members]
        final_id = stable_cluster_id(digests)
        for seq_id in members:
            seq_to_final[seq_id] = final_id
    return seq_to_final


def _assert_mmseqs_not_split(
    mmseqs_index: Mapping[str, Mapping[str, Any]],
    seq_to_final: Mapping[str, str],
) -> None:
    for cluster_id, payload in mmseqs_index.items():
        finals = {seq_to_final.get(member, "") for member in payload["members"]}
        if "" in finals or len(finals) != 1:
            raise S5FinalClusteringError(
                "NO-GO: S5E split a frozen MMseqs cluster "
                f"{cluster_id} into {sorted(finals)}"
            )


def _family_ids_by_core(
    membership_rows: Sequence[Mapping[str, str]],
) -> dict[str, set[str]]:
    by_core: dict[str, set[str]] = defaultdict(set)
    for row in membership_rows:
        if _blank(row.get("source_db")) != "ena":
            continue
        family_id = _blank(row.get("ena_effective_near_duplicate_family_id"))
        core = _blank(row.get("sequence_core"))
        if not family_id or not core or is_materialised_singleton(family_id):
            continue
        if _declared_multi_member([row]) or family_id.startswith("ndfam_"):
            by_core[core].add(family_id)
    return by_core


def select_final_representatives(
    *,
    final_members: Mapping[str, Sequence[str]],
    mmseqs_index: Mapping[str, Mapping[str, Any]],
    mmseqs_cluster_by_seq: Mapping[str, str],
    identities_by_seq: Mapping[str, Sequence[Mapping[str, str]]],
    digest_by_seq: Mapping[str, str],
) -> dict[str, dict[str, str]]:
    """Technical representative only. No biological superiority is implied."""
    chosen: dict[str, dict[str, str]] = {}
    for cluster_id, members in final_members.items():
        candidates: list[tuple[int, str, str]] = []
        for seq_id in members:
            mmseqs_id = mmseqs_cluster_by_seq[seq_id]
            payload = mmseqs_index[mmseqs_id]
            if payload["representative_sequence_id"] != seq_id:
                continue
            candidates.append(
                (
                    -int(payload["n_sequences"]),
                    digest_by_seq[seq_id],
                    seq_id,
                )
            )
        if not candidates:
            raise S5FinalClusteringError(
                f"final cluster {cluster_id} has no frozen MMseqs representative"
            )
        _neg_size, _digest, seq_id = min(candidates)
        identity_ids = [
            _blank(row.get("scientific_identity_id"))
            for row in identities_by_seq.get(seq_id, ())
            if _blank(row.get("scientific_identity_id"))
        ]
        if not identity_ids:
            raise S5FinalClusteringError(
                f"final representative core {seq_id} has no scientific identities"
            )
        chosen[cluster_id] = {
            "sequence_id": seq_id,
            "sequence_core_sha256": digest_by_seq[seq_id],
            "scientific_identity_id": min(identity_ids),
        }
    return chosen


def _group_final_members(seq_to_final: Mapping[str, str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for seq_id, cluster_id in seq_to_final.items():
        grouped[cluster_id].append(seq_id)
    return {cluster_id: sorted(members) for cluster_id, members in grouped.items()}


def _sources_of(row: Mapping[str, str]) -> set[str]:
    sources = set(split_pipe(row.get("contributing_sources") or ""))
    if _blank(row.get("source_db")):
        sources.add(_blank(row.get("source_db")))
    return {item for item in sources if item}


def _assert_one_scientific_representative(
    clustered_corpus: Sequence[Mapping[str, str]],
) -> None:
    by_cluster: dict[str, list[str]] = defaultdict(list)
    for row in clustered_corpus:
        if row.get("is_cluster_representative") == "true":
            by_cluster[row["cluster_id"]].append(row["scientific_identity_id"])
    clusters = {row["cluster_id"] for row in clustered_corpus}
    missing = sorted(clusters - set(by_cluster))
    if missing:
        raise S5FinalClusteringError(
            f"{len(missing)} final clusters lack a scientific representative"
        )
    extra = {
        cluster_id: identities
        for cluster_id, identities in by_cluster.items()
        if len(identities) != 1
    }
    if extra:
        raise S5FinalClusteringError(
            "final clusters with !=1 scientific representative: " + ", ".join(sorted(extra))
        )


def _assert_shared_cores_share_cluster(
    clustered_corpus: Sequence[Mapping[str, str]],
) -> None:
    by_core: dict[str, set[str]] = defaultdict(set)
    for row in clustered_corpus:
        by_core[_blank(row.get("sequence_core"))].add(_blank(row.get("cluster_id")))
    inconsistent = {
        sequence_core_digest(core): sorted(cluster_ids)
        for core, cluster_ids in by_core.items()
        if len(cluster_ids) != 1
    }
    if inconsistent:
        raise S5FinalClusteringError(
            "identical sequence_core values received different final cluster IDs"
        )


def build_family_containment(
    must_link_cohort: Sequence[Mapping[str, str]],
    seq_to_final: Mapping[str, str],
    mmseqs_cluster_by_seq: Mapping[str, str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows: list[dict[str, str]] = []
    relevant = [
        row for row in must_link_cohort if row.get("must_link_applied") == "true"
    ]
    for row in relevant:
        seq_ids = split_pipe(row["sequence_ids"])
        finals = sorted({seq_to_final.get(seq_id, "") for seq_id in seq_ids})
        finals = [item for item in finals if item]
        mmseqs_ids = sorted(
            {mmseqs_cluster_by_seq.get(seq_id, "") for seq_id in seq_ids if mmseqs_cluster_by_seq.get(seq_id)}
        )
        contained = len(finals) == 1
        created_union = len(mmseqs_ids) > 1
        rows.append(
            fill_row(
                FAMILY_CONTAINMENT_COLUMNS,
                {
                    "ena_family_id": row["ena_family_id"],
                    "declared_multi_member": row["declared_multi_member"],
                    "n_s5_ena_sequence_cores": row["n_s5_ena_sequence_cores"],
                    "n_mmseqs_clusters_before_union": str(len(mmseqs_ids)),
                    "n_final_clusters": str(len(finals)),
                    "contained_in_one_final_cluster": bool_token(contained),
                    "created_union_edge": bool_token(created_union),
                    "final_cluster_ids": "|".join(finals),
                },
            )
        )
    rows.sort(key=lambda item: item["ena_family_id"])
    split = [row["ena_family_id"] for row in rows if row["contained_in_one_final_cluster"] != "true"]
    diagnostics = {
        "n_must_link_families": len(rows),
        "n_must_link_families_contained": sum(
            1 for row in rows if row["contained_in_one_final_cluster"] == "true"
        ),
        "n_must_link_families_split": len(split),
        "split_family_ids": split,
        "must_link_containment_pass": not split and bool(rows),
    }
    if split:
        raise S5FinalClusteringError(
            "NO-GO: retained multi-member ENA families not contained after union: "
            + ", ".join(split)
        )
    return rows, diagnostics


def _overlap_unique_counts(
    corpus_rows: Sequence[Mapping[str, str]],
    *,
    source_keys: Sequence[str] = DEFAULT_OVERLAP_SOURCES,
) -> dict[str, Any]:
    unique_to: Counter[str] = Counter()
    present_in: Counter[str] = Counter()
    corroboration = Counter()
    for row in corpus_rows:
        sources = sorted(_sources_of(row))
        corroboration[len(sources)] += 1
        for source in sources:
            present_in[source] += 1
        if len(sources) == 1:
            unique_to[sources[0]] += 1
    return {
        "identities_unique_to_source": {key: unique_to.get(key, 0) for key in source_keys},
        "identities_containing_source": {key: present_in.get(key, 0) for key in source_keys},
        "corroboration_count_distribution": {
            str(key): count for key, count in sorted(corroboration.items())
        },
    }


def assemble_final_clustering(
    *,
    corpus_rows: Sequence[Mapping[str, str]],
    mmseqs_cluster_rows: Sequence[Mapping[str, str]],
    membership_rows: Sequence[Mapping[str, str]],
    mmseqs_clustered_corpus: Sequence[Mapping[str, str]] | None = None,
    expected_counts: Mapping[str, Any] | None = None,
    shuffle_seed: int | None = None,
) -> FinalClusteringResult:
    mmseqs_index = index_mmseqs_clusters(mmseqs_cluster_rows)
    digest_by_seq: dict[str, str] = {}
    length_by_seq: dict[str, str] = {}
    mmseqs_cluster_by_seq: dict[str, str] = {}
    mmseqs_rep_by_seq: dict[str, str] = {}
    for cluster_id, payload in mmseqs_index.items():
        for row in payload["member_rows"]:
            seq_id = _blank(row.get("member_sequence_id") or row.get("sequence_id"))
            digest = _blank(row.get("member_sequence_core_sha256") or row.get("sequence_core_sha256"))
            digest_by_seq[seq_id] = digest
            length_by_seq[seq_id] = _blank(row.get("sequence_length"))
            mmseqs_cluster_by_seq[seq_id] = cluster_id
            mmseqs_rep_by_seq[seq_id] = payload["representative_sequence_id"]

    identities_by_seq: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    sequence_id_by_core: dict[str, str] = {}
    identity_source = mmseqs_clustered_corpus if mmseqs_clustered_corpus is not None else corpus_rows
    for row in identity_source:
        core = _blank(row.get("sequence_core"))
        seq_id = _sequence_id_for(row) if _blank(row.get("sequence_id")) else make_sequence_id(core)
        if core:
            sequence_id_by_core[core] = seq_id
            if seq_id not in digest_by_seq:
                digest_by_seq[seq_id] = sequence_core_digest(core)
            if seq_id not in length_by_seq:
                length_by_seq[seq_id] = str(len(core))
        identities_by_seq[seq_id].append(row)

    if len(digest_by_seq) != len(mmseqs_cluster_rows):
        raise S5FinalClusteringError(
            "MMseqs cluster row count does not match unique sequence cores"
        )

    cohort_rows, must_links, cohort_diag = derive_ena_must_link_cohort(
        membership_rows,
        sequence_id_by_core=sequence_id_by_core,
        mmseqs_cluster_by_seq=mmseqs_cluster_by_seq,
    )
    seq_to_root = union_mmseqs_and_family_must_links(
        mmseqs_index, must_links, shuffle_seed=shuffle_seed
    )
    expected_seq_ids = set(mmseqs_cluster_by_seq)
    if set(seq_to_root) != expected_seq_ids:
        missing = sorted(expected_seq_ids - set(seq_to_root))
        extra = sorted(set(seq_to_root) - expected_seq_ids)
        raise S5FinalClusteringError(
            f"union-find sequence coverage mismatch; missing={missing[:5]} extra={extra[:5]}"
        )
    seq_to_final = _final_membership_from_roots(seq_to_root, digest_by_seq)
    _assert_mmseqs_not_split(mmseqs_index, seq_to_final)

    final_members = _group_final_members(seq_to_final)
    n_mmseqs = len(mmseqs_index)
    n_final = len(final_members)
    if n_final > n_mmseqs:
        raise S5FinalClusteringError(
            f"NO-GO: S5E created {n_final} clusters from {n_mmseqs} MMseqs clusters"
        )

    family_core_ids = _family_ids_by_core(membership_rows)
    must_link_ids = {item["ena_family_id"] for item in must_links}

    cluster_mmseqs: dict[str, set[str]] = defaultdict(set)
    cluster_families: dict[str, set[str]] = defaultdict(set)
    cluster_bridging: dict[str, set[str]] = defaultdict(set)
    for seq_id, final_id in seq_to_final.items():
        mmseqs_id = mmseqs_cluster_by_seq[seq_id]
        cluster_mmseqs[final_id].add(mmseqs_id)
        core = next(
            (
                _blank(row.get("sequence_core"))
                for row in identities_by_seq.get(seq_id, ())
                if _blank(row.get("sequence_core"))
            ),
            "",
        )
        if not core:
            continue
        for family_id in family_core_ids.get(core, set()):
            if family_id in must_link_ids:
                cluster_families[final_id].add(family_id)

    for family in must_links:
        mmseqs_ids = {
            mmseqs_cluster_by_seq[seq_id]
            for seq_id in family["sequence_ids"]
            if seq_id in mmseqs_cluster_by_seq
        }
        if len(mmseqs_ids) <= 1:
            continue
        finals = {seq_to_final[seq_id] for seq_id in family["sequence_ids"]}
        for final_id in finals:
            cluster_bridging[final_id].add(family["ena_family_id"])

    merge_basis: dict[str, str] = {}
    for cluster_id, mmseqs_ids in cluster_mmseqs.items():
        if len(mmseqs_ids) == 1:
            merge_basis[cluster_id] = MERGE_MMSEQS_ONLY
            only = next(iter(mmseqs_ids))
            if cluster_id != only:
                raise S5FinalClusteringError(
                    "un-unioned final cluster_id must equal the frozen MMseqs cluster_id"
                )
        else:
            merge_basis[cluster_id] = MERGE_MMSEQS_PLUS_ENA

    chosen = select_final_representatives(
        final_members=final_members,
        mmseqs_index=mmseqs_index,
        mmseqs_cluster_by_seq=mmseqs_cluster_by_seq,
        identities_by_seq=identities_by_seq,
        digest_by_seq=digest_by_seq,
    )

    clusters_final: list[dict[str, str]] = []
    for seq_id in sorted(seq_to_final, key=lambda item: (seq_to_final[item], item)):
        final_id = seq_to_final[seq_id]
        mmseqs_id = mmseqs_cluster_by_seq[seq_id]
        rep = chosen[final_id]
        clusters_final.append(
            fill_row(
                CLUSTERS_FINAL_COLUMNS,
                {
                    "cluster_id": final_id,
                    "sequence_id": seq_id,
                    "sequence_core_sha256": digest_by_seq[seq_id],
                    "sequence_length": length_by_seq.get(seq_id, ""),
                    "sequence_cluster_id_mmseqs": mmseqs_id,
                    "mmseqs_representative_sequence_id": mmseqs_rep_by_seq[seq_id],
                    "is_mmseqs_sequence_representative": bool_token(
                        mmseqs_index[mmseqs_id]["representative_sequence_id"] == seq_id
                    ),
                    "final_representative_sequence_id": rep["sequence_id"],
                    "final_representative_sequence_core_sha256": rep["sequence_core_sha256"],
                    "member_is_final_sequence_representative": bool_token(
                        seq_id == rep["sequence_id"]
                    ),
                    "merge_basis": merge_basis[final_id],
                    "ena_family_must_link_ids": join_sorted_unique(cluster_families.get(final_id, ())),
                },
            )
        )

    identity_rows = list(identity_source)
    clustered_corpus: list[dict[str, str]] = []
    for row in identity_rows:
        core = _blank(row.get("sequence_core"))
        seq_id = _blank(row.get("sequence_id")) or make_sequence_id(core)
        final_id = seq_to_final[seq_id]
        mmseqs_id = _blank(row.get("cluster_id")) or mmseqs_cluster_by_seq[seq_id]
        if mmseqs_clustered_corpus is not None:
            mmseqs_id = mmseqs_cluster_by_seq[seq_id]
        values = {column: _blank(row.get(column)) for column in CORPUS_DEDUP_COLUMNS}
        values["cluster_id"] = final_id
        values["is_cluster_representative"] = "false"
        mmseqs_rep_id = mmseqs_index[mmseqs_id]["representative_sequence_id"]
        clustered_corpus.append(
            fill_row(
                CORPUS_CLUSTERED_FINAL_COLUMNS,
                {
                    **values,
                    "sequence_id": seq_id,
                    "sequence_core_sha256": digest_by_seq[seq_id],
                    "sequence_cluster_id_mmseqs": mmseqs_id,
                    "mmseqs_representative_sequence_id": mmseqs_rep_id,
                    "mmseqs_representative_sequence_core_sha256": digest_by_seq[mmseqs_rep_id],
                    "is_mmseqs_sequence_representative": bool_token(
                        mmseqs_index[mmseqs_id]["representative_sequence_id"] == seq_id
                    ),
                    "is_mmseqs_scientific_representative": bool_token(
                        row.get("is_cluster_representative") == "true"
                    )
                    if mmseqs_clustered_corpus is not None
                    else "false",
                    "final_representative_sequence_id": chosen[final_id]["sequence_id"],
                    "final_representative_sequence_core_sha256": chosen[final_id][
                        "sequence_core_sha256"
                    ],
                },
            )
        )

    for row in clustered_corpus:
        row["is_cluster_representative"] = bool_token(
            row["scientific_identity_id"] == chosen[row["cluster_id"]]["scientific_identity_id"]
        )
    if mmseqs_clustered_corpus is None:
        for row in clustered_corpus:
            if (
                row["is_mmseqs_sequence_representative"] == "true"
                and row["scientific_identity_id"]
                == min(
                    _blank(item.get("scientific_identity_id"))
                    for item in identities_by_seq[row["sequence_id"]]
                )
            ):
                row["is_mmseqs_scientific_representative"] = "true"
            else:
                row["is_mmseqs_scientific_representative"] = "false"

    clustered_corpus.sort(key=lambda row: row["scientific_identity_id"])
    _assert_one_scientific_representative(clustered_corpus)
    _assert_shared_cores_share_cluster(clustered_corpus)

    identities_by_cluster: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in clustered_corpus:
        identities_by_cluster[row["cluster_id"]].append(row)

    family_containment_rows, family_containment_diag = build_family_containment(
        cohort_rows, seq_to_final, mmseqs_cluster_by_seq
    )

    summary: list[dict[str, str]] = []
    provenance: list[dict[str, str]] = []
    for cluster_id, members in sorted(final_members.items()):
        identities = identities_by_cluster[cluster_id]
        lengths = [int(length_by_seq[seq_id]) for seq_id in members if length_by_seq.get(seq_id)]
        targets = {
            _blank(row.get("canonical_target_name"))
            for row in identities
            if _blank(row.get("canonical_target_name"))
        }
        sources: set[str] = set()
        for row in identities:
            sources.update(_sources_of(row))
        cores = Counter(_blank(row.get("sequence_core")) for row in identities)
        ena_present = any("ena" in _sources_of(row) for row in identities)
        mmseqs_ids = sorted(cluster_mmseqs[cluster_id])
        family_ids = sorted(cluster_families.get(cluster_id, ()))
        bridging = sorted(cluster_bridging.get(cluster_id, ()))
        differs = len(mmseqs_ids) > 1
        rep = chosen[cluster_id]
        summary.append(
            fill_row(
                CLUSTER_SUMMARY_FINAL_COLUMNS,
                {
                    "cluster_id": cluster_id,
                    "n_distinct_sequences": str(len(members)),
                    "n_scientific_identities": str(len(identities)),
                    "representative_sequence_id": rep["sequence_id"],
                    "representative_sequence_core_sha256": rep["sequence_core_sha256"],
                    "representative_scientific_identity_id": rep["scientific_identity_id"],
                    "min_sequence_length": str(min(lengths)) if lengths else "",
                    "median_sequence_length": _format_median(lengths),
                    "max_sequence_length": str(max(lengths)) if lengths else "",
                    "n_targets": str(len(targets)),
                    "n_sources": str(len(sources)),
                    "contains_multi_target_identical_core": bool_token(
                        any(count > 1 for count in cores.values())
                    ),
                    "ena_provenance_present": bool_token(ena_present),
                    "n_mmseqs_components": str(len(mmseqs_ids)),
                    "mmseqs_cluster_ids": "|".join(mmseqs_ids),
                    "n_ena_family_must_links": str(len(family_ids)),
                    "ena_family_must_link_ids": "|".join(family_ids),
                    "differs_from_single_mmseqs_component": bool_token(differs),
                    "merge_basis": merge_basis[cluster_id],
                },
            )
        )
        provenance.append(
            fill_row(
                CLUSTER_UNION_PROVENANCE_COLUMNS,
                {
                    "cluster_id": cluster_id,
                    "n_sequence_cores": str(len(members)),
                    "n_scientific_identities": str(len(identities)),
                    "n_mmseqs_components": str(len(mmseqs_ids)),
                    "mmseqs_cluster_ids": "|".join(mmseqs_ids),
                    "n_ena_family_must_links": str(len(family_ids)),
                    "ena_family_must_link_ids": "|".join(family_ids),
                    "n_ena_families_that_bridged_mmseqs_components": str(len(bridging)),
                    "ena_family_ids_that_bridged_mmseqs_components": "|".join(bridging),
                    "differs_from_single_mmseqs_component": bool_token(differs),
                    "merge_basis": merge_basis[cluster_id],
                    "n_canonical_targets": str(len(targets)),
                    "contributing_sources": join_sorted_unique(sources),
                },
            )
        )
    summary.sort(key=lambda row: row["cluster_id"])
    provenance.sort(key=lambda row: row["cluster_id"])

    n_unioned_final = sum(1 for row in summary if row["merge_basis"] == MERGE_MMSEQS_PLUS_ENA)
    n_mmseqs_merged = sum(int(row["n_mmseqs_components"]) for row in summary if row["merge_basis"] == MERGE_MMSEQS_PLUS_ENA)
    size_counts = Counter(int(row["n_distinct_sequences"]) for row in summary)
    identity_counts = Counter(int(row["n_scientific_identities"]) for row in summary)
    singletons = sum(1 for row in summary if int(row["n_distinct_sequences"]) == 1)
    multi_seq = n_final - singletons
    largest = max(size_counts) if size_counts else 0
    n_rep = sum(1 for row in clustered_corpus if row["is_cluster_representative"] == "true")
    n_seq_rep = sum(
        1 for row in clusters_final if row["member_is_final_sequence_representative"] == "true"
    )
    if n_rep != n_final or n_seq_rep != n_final:
        raise S5FinalClusteringError(
            "NO-GO: representative count does not match final cluster count"
        )

    ena_validation = validate_ena_families(
        membership_rows=membership_rows,
        clustered_corpus=clustered_corpus,
        cluster_rows=[
            {
                "cluster_id": row["cluster_id"],
                "member_sequence_id": row["sequence_id"],
            }
            for row in clusters_final
        ],
    )
    # Positive recall only: do not treat singleton/cross-family merges as failures.
    singleton_metrics = {
        "n_materialised_singleton_families": ena_validation.metrics.get(
            "n_singleton_source_families", 0
        ),
        "n_singletons_isolated_from_every_other_ena_core": ena_validation.metrics.get(
            "n_singletons_isolated_from_every_other_ena_core"
        ),
        "n_singletons_clustered_with_another_materialised_singleton": ena_validation.metrics.get(
            "n_singletons_clustered_with_another_materialised_singleton"
        ),
        "n_singletons_clustered_with_real_multi_member_family": ena_validation.metrics.get(
            "n_singletons_clustered_with_real_multi_member_family"
        ),
        "n_singletons_clustered_only_with_non_ena_sequences": ena_validation.metrics.get(
            "n_singletons_clustered_only_with_non_ena_sequences"
        ),
        "n_clusters_containing_multiple_ena_families": ena_validation.metrics.get(
            "n_clusters_containing_multiple_ena_families", 0
        ),
        "n_clusters_combining_distinct_real_ena_families": ena_validation.metrics.get(
            "n_clusters_combining_distinct_real_ena_families"
        ),
        "n_clusters_mixing_real_families_and_singletons": ena_validation.metrics.get(
            "n_clusters_mixing_real_families_and_singletons"
        ),
        "treated_as_cannot_link": False,
        "treated_as_validation_failure": False,
    }

    multi = multi_target_preservation(
        clustered_corpus,
        membership_rows=membership_rows,
        expected_shared_cores=(expected_counts or {}).get("n_shared_sequence_cores"),
        expected_shared_identities=(expected_counts or {}).get("n_shared_core_identities"),
        expected_shared_membership_rows=(expected_counts or {}).get(
            "n_shared_core_membership_rows"
        ),
    )
    overlap = _overlap_unique_counts(clustered_corpus)
    largest_clusters = [
        {
            "cluster_id": row["cluster_id"],
            "n_distinct_sequences": int(row["n_distinct_sequences"]),
            "n_scientific_identities": int(row["n_scientific_identities"]),
            "n_targets": int(row["n_targets"]),
            "merge_basis": row["merge_basis"],
        }
        for row in sorted(
            summary,
            key=lambda item: (-int(item["n_distinct_sequences"]), item["cluster_id"]),
        )[:10]
    ]
    diagnostics: dict[str, Any] = {
        "n_scientific_identities": len(clustered_corpus),
        "n_distinct_sequence_core": len(clusters_final),
        "n_mmseqs_clusters": n_mmseqs,
        "n_final_clusters": n_final,
        "n_singleton_clusters": singletons,
        "n_multi_sequence_clusters": multi_seq,
        "singleton_fraction": (singletons / n_final) if n_final else None,
        "largest_cluster_size": largest,
        "cluster_size_distribution": dict(sorted(size_counts.items())),
        "identities_per_cluster_distribution": dict(sorted(identity_counts.items())),
        "n_clusters_gt1_canonical_target": sum(
            1 for row in summary if int(row["n_targets"]) > 1
        ),
        "n_clusters_gt1_source": sum(1 for row in summary if int(row["n_sources"]) > 1),
        "n_clusters_with_ena_provenance": sum(
            1 for row in summary if row["ena_provenance_present"] == "true"
        ),
        "n_clusters_with_multi_target_identical_core": sum(
            1
            for row in summary
            if row["contains_multi_target_identical_core"] == "true"
        ),
        "n_scientific_representatives": n_rep,
        "n_sequence_representatives": n_seq_rep,
        "n_missing_cluster_id": sum(
            1 for row in clustered_corpus if not _blank(row.get("cluster_id"))
        ),
        "n_mmseqs_clusters_in_unioned_final_clusters": n_mmseqs_merged,
        "n_final_clusters_affected_by_ena_must_links": n_unioned_final,
        "n_reduction_due_to_family_constraints": n_mmseqs - n_final,
        "n_reduction_due_to_near_sequence_clustering": (
            len(clusters_final) - n_mmseqs
        ),
        "mmseqs_clusters_preserved_as_subsets": True,
        "cd_hit_selected": False,
        "cd_hit_fallback_tested": True,
        "family_constraint_semantics": "positive_must_link_only",
        "materialised_singletons_as_cannot_link": False,
        "cluster_id_convention": (
            "S5C_ + sha256 of sorted final-member sequence_core_sha256 values "
            "joined by U+001F"
        ),
        "representative_convention": (
            "largest frozen MMseqs component's MMseqs representative core, "
            "then lexicographically smallest sequence_core_sha256 on size tie, "
            "then lexicographically smallest scientific_identity_id"
        ),
        "multi_target": multi,
        "ena_must_link": {**cohort_diag, **family_containment_diag},
        "ena_descriptive": singleton_metrics,
        "ena_family_metrics": {
            key: ena_validation.metrics.get(key)
            for key in (
                "n_ena_family_ids_represented",
                "n_declared_multi_member_families_represented",
                "n_multi_member_families_with_at_least_two_s5_members",
                "n_multi_member_families_contained_in_one_cluster",
                "n_multi_member_families_split_across_gt1_cluster",
                "n_singleton_source_families",
                "n_singletons_isolated_from_every_other_ena_core",
                "n_singletons_clustered_with_another_materialised_singleton",
                "n_singletons_clustered_with_real_multi_member_family",
                "n_singletons_clustered_only_with_non_ena_sequences",
                "n_clusters_containing_multiple_ena_families",
                "n_clusters_combining_distinct_real_ena_families",
                "n_clusters_mixing_real_families_and_singletons",
            )
        },
        "overlap": overlap,
        "largest_clusters": largest_clusters,
        "no_row_removal": len(clustered_corpus),
        "scientific_identities_before": len(corpus_rows),
        "scientific_identities_after": len(clustered_corpus),
        "n_shared_sequence_cores": multi["n_shared_sequence_cores"],
        "n_shared_core_identities": multi["n_shared_core_identities"],
        "n_shared_core_membership_rows": multi["n_shared_core_membership_rows"],
        "n_missing_sequence_core": sum(
            1 for row in clustered_corpus if not _blank(row.get("sequence_core"))
        ),
        "n_real_multi_member_family_ids_represented": cohort_diag[
            "n_real_multi_member_family_ids_represented"
        ],
        "n_families_with_ge2_retained_s5_ena_cores": cohort_diag[
            "n_families_with_ge2_retained_s5_ena_cores"
        ],
    }
    if expected_counts:
        errors = expected_count_errors(diagnostics, expected_counts)
        extra_expected = {
            "n_mmseqs_clusters": n_mmseqs,
            "n_real_multi_member_family_ids_represented": cohort_diag[
                "n_real_multi_member_family_ids_represented"
            ],
            "n_families_with_ge2_retained_s5_ena_cores": cohort_diag[
                "n_families_with_ge2_retained_s5_ena_cores"
            ],
        }
        for key, observed in extra_expected.items():
            wanted = expected_counts.get(key)
            if wanted is not None and observed != wanted:
                errors.append(f"{key}: expected {wanted}, got {observed}")
        if errors:
            raise S5FinalClusteringError(
                "S5E expected-count regression:\n" + "\n".join(errors)
            )
    if diagnostics["n_scientific_identities"] != diagnostics["scientific_identities_before"]:
        raise S5FinalClusteringError("NO-GO: S5E removed or added scientific identities")
    if diagnostics["n_distinct_sequence_core"] != len(mmseqs_cluster_rows):
        raise S5FinalClusteringError("NO-GO: S5E did not retain every clustered sequence core")
    return FinalClusteringResult(
        clusters_final=clusters_final,
        clustered_corpus=clustered_corpus,
        cluster_summary=summary,
        union_provenance=provenance,
        family_containment=family_containment_rows,
        must_link_cohort=cohort_rows,
        diagnostics=diagnostics,
    )


def compare_final_runs(
    first: FinalClusteringResult,
    second: FinalClusteringResult,
) -> None:
    if first.clusters_final != second.clusters_final:
        raise S5FinalClusteringError(
            "NO-GO: clusters_final.tsv membership/IDs differed across identical runs"
        )
    if first.clustered_corpus != second.clustered_corpus:
        raise S5FinalClusteringError(
            "NO-GO: corpus_clustered_final.csv differed across identical runs"
        )
    if first.cluster_summary != second.cluster_summary:
        raise S5FinalClusteringError(
            "NO-GO: cluster_summary_final.csv differed across identical runs"
        )
    if first.union_provenance != second.union_provenance:
        raise S5FinalClusteringError(
            "NO-GO: cluster_union_provenance.csv differed across identical runs"
        )


def membership_signature(clusters_final: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    members: dict[str, set[str]] = defaultdict(set)
    for row in clusters_final:
        members[row["cluster_id"]].add(row["sequence_id"])
    return {
        cluster_id: tuple(sorted(seq_ids))
        for cluster_id, seq_ids in sorted(members.items())
    }


def build_overlap_report(
    diagnostics: Mapping[str, Any],
    *,
    overlap_matrix: Sequence[Mapping[str, str]] | None = None,
    s4_hashes: Mapping[str, str] | None = None,
    s5a_hashes: Mapping[str, str] | None = None,
    s5c_hashes: Mapping[str, str] | None = None,
    output_hashes: Mapping[str, str] | None = None,
) -> str:
    ena = diagnostics.get("ena_must_link") or {}
    descriptive = diagnostics.get("ena_descriptive") or {}
    family_metrics = diagnostics.get("ena_family_metrics") or {}
    multi = diagnostics.get("multi_target") or {}
    overlap = diagnostics.get("overlap") or {}
    size_lines = [
        f"- size {size}: {count}"
        for size, count in (diagnostics.get("cluster_size_distribution") or {}).items()
    ]
    identity_lines = [
        f"- {count} identities: {n_clusters}"
        for count, n_clusters in (
            diagnostics.get("identities_per_cluster_distribution") or {}
        ).items()
    ]
    unique_lines = [
        f"- {source}: {count}"
        for source, count in (overlap.get("identities_unique_to_source") or {}).items()
    ]
    present_lines = [
        f"- {source}: {count}"
        for source, count in (overlap.get("identities_containing_source") or {}).items()
    ]
    corr = overlap.get("corroboration_count_distribution") or {}
    corr_lines = [f"- {key} source(s): {count}" for key, count in corr.items()]
    matrix_lines = []
    if overlap_matrix:
        matrix_lines.append(
            "| source_a | source_b | shared identities | shared duplicate groups |"
        )
        matrix_lines.append("|---|---|---:|---:|")
        for row in overlap_matrix:
            matrix_lines.append(
                f"| {row['source_a']} | {row['source_b']} | "
                f"{row['n_shared_scientific_identities']} | "
                f"{row['n_shared_duplicate_groups']} |"
            )
    largest_lines = []
    for item in diagnostics.get("largest_clusters") or []:
        largest_lines.append(
            f"- {item['cluster_id']}: {item['n_distinct_sequences']} sequences, "
            f"{item['n_scientific_identities']} identities, "
            f"{item['n_targets']} targets, merge={item['merge_basis']}"
        )
    contained_ids = ena.get("must_link_family_ids") or []
    family_lines = [f"- {family_id}: contained_in_one_final_cluster=true" for family_id in contained_ids]
    hash_lines = []
    for label, payload in (
        ("S4", s4_hashes),
        ("S5A", s5a_hashes),
        ("S5C", s5c_hashes),
        ("S5E final", output_hashes),
    ):
        if not payload:
            continue
        hash_lines.append(f"### {label}")
        hash_lines.append("")
        for name, digest in payload.items():
            hash_lines.append(f"- {name}: `{digest}`")
        hash_lines.append("")
    text = "\n".join(
        [
            "# Global S5 — overlap and leakage-safe clustering",
            "",
            "Governing S5 aggregate report after exact scientific deduplication",
            "and leakage-safe final clustering. No biological sequences.",
            "",
            "Final `cluster_id` is the connected component of frozen MMseqs",
            "90%-identity clusters **union** trusted real multi-member ENA",
            "family must-links. ENA family IDs are not negative/cannot-link",
            "constraints and are not global 90%-identity ground truth.",
            "",
            "## Exact scientific overlap (S5A freeze)",
            "",
            f"- scientific identities: {diagnostics.get('n_scientific_identities')}",
            f"- distinct sequence_core: {diagnostics.get('n_distinct_sequence_core')}",
            "",
            "Identities unique to one contributing source:",
            *unique_lines,
            "",
            "Identities containing each source (including multi-source rows):",
            *present_lines,
            "",
            "corroboration_count distribution:",
            *corr_lines,
            "",
            "Exact-identity n×n overlap matrix (frozen S5A):",
            *matrix_lines,
            "",
            "## Sequence-similarity clustering (frozen S5C MMseqs)",
            "",
            "Authorised command:",
            "",
            "```text",
            "mmseqs easy-cluster --min-seq-id 0.9 -c 0.8 --cov-mode 1 -s 7.5",
            "```",
            "",
            f"- MMseqs clusters: {diagnostics.get('n_mmseqs_clusters')}",
            f"- unique cores clustered: {diagnostics.get('n_distinct_sequence_core')}",
            f"- reduction due to near-sequence clustering: "
            f"{diagnostics.get('n_reduction_due_to_near_sequence_clustering')}",
            "",
            "CD-HIT-est `-c 0.9 -n 8` was tested in S5D after apparent poor",
            "ENA-family recall. It is **not** the v1 final clustering method.",
            "",
            "## Final leakage-safe clusters (S5E)",
            "",
            f"- final clusters: {diagnostics.get('n_final_clusters')}",
            f"- singleton clusters: {diagnostics.get('n_singleton_clusters')}",
            f"- multi-sequence clusters: {diagnostics.get('n_multi_sequence_clusters')}",
            f"- singleton fraction: {diagnostics.get('singleton_fraction')}",
            f"- largest cluster size: {diagnostics.get('largest_cluster_size')}",
            f"- MMseqs clusters absorbed into unioned finals: "
            f"{diagnostics.get('n_mmseqs_clusters_in_unioned_final_clusters')}",
            f"- final clusters affected by ENA must-links: "
            f"{diagnostics.get('n_final_clusters_affected_by_ena_must_links')}",
            f"- reduction attributable to family constraints: "
            f"{diagnostics.get('n_reduction_due_to_family_constraints')}",
            f"- MMseqs clusters preserved as subsets: "
            f"{diagnostics.get('mmseqs_clusters_preserved_as_subsets')}",
            "",
            "Cluster-size distribution:",
            *size_lines,
            "",
            "Identities per cluster:",
            *identity_lines,
            "",
            "Largest clusters:",
            *largest_lines,
            "",
            f"- clusters with >1 canonical target: {diagnostics.get('n_clusters_gt1_canonical_target')}",
            f"- clusters with >1 source: {diagnostics.get('n_clusters_gt1_source')}",
            f"- clusters with ENA provenance: {diagnostics.get('n_clusters_with_ena_provenance')}",
            f"- clusters containing a multi-target identical core: "
            f"{diagnostics.get('n_clusters_with_multi_target_identical_core')}",
            f"- scientific representatives: {diagnostics.get('n_scientific_representatives')}",
            "",
            "## ENA positive must-link validation",
            "",
            "Required: every retained real multi-member ENA family is wholly",
            "contained in one final cluster. Materialised singleton IDs and",
            "cross-family MMseqs merges are reported descriptively and are",
            "**not** validation failures.",
            "",
            f"- real/multi-member family IDs represented: "
            f"{ena.get('n_real_multi_member_family_ids_represented')}",
            f"- families with ≥2 retained S5 ENA cores: "
            f"{ena.get('n_families_with_ge2_retained_s5_ena_cores')}",
            f"- of those, contained in one final cluster: "
            f"{ena.get('n_must_link_families_contained')}",
            f"- of those, split: {ena.get('n_must_link_families_split')}",
            f"- containment pass: {ena.get('must_link_containment_pass')}",
            "",
            "16-family containment:",
            *family_lines,
            "",
            "Descriptive (not fail conditions):",
            f"- singleton-source family IDs (1 S5 membership row): "
            f"{descriptive.get('n_materialised_singleton_families')}",
            f"- isolated from every other ENA core: "
            f"{descriptive.get('n_singletons_isolated_from_every_other_ena_core')}",
            f"- clustered with another materialised singleton: "
            f"{descriptive.get('n_singletons_clustered_with_another_materialised_singleton')}",
            f"- clustered with a real multi-member ENA family: "
            f"{descriptive.get('n_singletons_clustered_with_real_multi_member_family')}",
            f"- clustered only with non-ENA sequences: "
            f"{descriptive.get('n_singletons_clustered_only_with_non_ena_sequences')}",
            f"- clusters containing multiple ENA family IDs: "
            f"{descriptive.get('n_clusters_containing_multiple_ena_families')}",
            f"- clusters combining distinct real ENA families: "
            f"{descriptive.get('n_clusters_combining_distinct_real_ena_families')}",
            f"- clusters mixing real families and singletons: "
            f"{descriptive.get('n_clusters_mixing_real_families_and_singletons')}",
            f"- ENA family IDs represented (including singletons): "
            f"{family_metrics.get('n_ena_family_ids_represented')}",
            "",
            "## Multi-target preservation",
            "",
            f"- shared sequence cores: {multi.get('n_shared_sequence_cores')}",
            f"- scientific identities on those cores: {multi.get('n_shared_core_identities')}",
            f"- shared cores consistent cluster ID: {multi.get('shared_cores_consistent_cluster_id')}",
            f"- scientific identities before/after: "
            f"{diagnostics.get('scientific_identities_before')} / "
            f"{diagnostics.get('scientific_identities_after')}",
            "",
            "Scientific identities were not merged. Multi-target sequences",
            "remain multiple identities and share one leakage-safe cluster.",
            "",
            "## Schema (S5B retained; S7 not migrated here)",
            "",
            "- `scientific_identity_id` is the unique S5 scientific-row identifier.",
            "- donor/source `record_id` is provenance and is not unique.",
            "- final `cluster_id` is the leakage-safe grouping identifier.",
            "- frozen `sequence_cluster_id_mmseqs` remains the MMseqs identity.",
            "- S7/final-schema work must formally retain `scientific_identity_id`.",
            "",
            "## Integrity hashes",
            "",
            *hash_lines,
            "## Boundary",
            "",
            "- S4 unchanged",
            "- S5A exact-dedup freeze unchanged",
            "- S5C MMseqs candidate unchanged",
            "- CD-HIT not selected",
            "- no scientific identities removed",
            "- no balancing, target cap, FT/REF/EVAL, or train/validation split",
            "- S6 not started",
            "",
        ]
    )
    if SEQ_LEAK_RE.search(text or ""):
        raise S5FinalClusteringError(
            "overlap_report.md must not contain biological sequences"
        )
    return text if text.endswith("\n") else text + "\n"


def build_s5e_report(diagnostics: Mapping[str, Any]) -> str:
    ena = diagnostics.get("ena_must_link") or {}
    text = "\n".join(
        [
            "# Global S5E — leakage-safe final clustering",
            "",
            "S5E unions frozen MMseqs 90% clusters with trusted real",
            "multi-member ENA family must-links. It does not rerun MMseqs,",
            "select CD-HIT, or begin S6/S7.",
            "",
            f"- MMseqs clusters: {diagnostics.get('n_mmseqs_clusters')}",
            f"- final clusters: {diagnostics.get('n_final_clusters')}",
            f"- reduction due to family constraints: "
            f"{diagnostics.get('n_reduction_due_to_family_constraints')}",
            f"- must-link families contained: "
            f"{ena.get('n_must_link_families_contained')} / "
            f"{ena.get('n_must_link_families')}",
            f"- scientific identities: {diagnostics.get('n_scientific_identities')}",
            f"- unique sequence cores: {diagnostics.get('n_distinct_sequence_core')}",
            "",
        ]
    )
    if SEQ_LEAK_RE.search(text or ""):
        raise S5FinalClusteringError("S5E report must not contain biological sequences")
    return text if text.endswith("\n") else text + "\n"

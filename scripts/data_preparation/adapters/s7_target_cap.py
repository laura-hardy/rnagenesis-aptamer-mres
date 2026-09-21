"""GLOBAL S7A — deterministic whole-cluster 3% target-cap selection.

Pure selection function shared by preview and scientific application.
This module does not populate ``partition``, promote E5, or promote
non-protein records. Cluster selection never reads the human approval
record; that artefact is an audit / post-derivation parity check only.

Authority: CHECKPOINT-3 C3-01 / C3-05.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Mapping, Sequence

from adapters.s4_scientific_common import ScientificProposalError
from adapters.target_extraction_common import SEQ_LEAK_RE

S7TargetCapError = ScientificProposalError

CLUSTER_TYPE_PURE = "target_pure"
CLUSTER_TYPE_MIXED = "mixed"
ACTIVE_MAX_TARGET_FRACTION = Decimal("0.03")
SHARE_QUANTUM = Decimal("0.0000000001")
IDENTITY_COLUMNS: tuple[str, ...] = (
    "scientific_identity_id",
    "cluster_id",
    "canonical_target_name",
    "sequence_core",
    "evidence_level",
    "target_type",
    "partition",
)
SEQUENCE_BEARING_COLUMNS: frozenset[str] = frozenset(
    {
        "sequence_raw",
        "sequence_full",
        "sequence_core",
        "detected_constant_5p",
        "detected_constant_3p",
    }
)
FORBIDDEN_OUTPUT_NAMES: frozenset[str] = frozenset(
    {
        "clusters.tsv",
        "clusters_final.tsv",
        "corpus_clustered.csv",
        "corpus_clustered_final.csv",
        "corpus_dedup.csv",
        "cluster_summary.csv",
        "cluster_summary_final.csv",
        "cluster_union_provenance.csv",
        "exact_duplicate_membership.csv",
        "exact_duplicate_groups.csv",
        "exact_overlap_matrix.csv",
        "overlap_report.md",
        "s5_final_clustering_manifest.json",
        "s5a_exact_dedup_report.md",
        "s5b_validation_report.md",
        "s5b_validation_summary.json",
        "s5c_clustering_manifest.json",
        "s5c_sequence_clustering_report.md",
        "s5c_rna_u_preflight.json",
        "sequence_clustering_input.csv",
        "sequence_clustering_input.fasta",
        "sequence_scientific_identity_map.csv",
        "cluster_identity_audit.csv",
        "ena_family_clustering_diagnostics.csv",
        "s5e_ena_must_link_containment.csv",
        "s5e_ena_must_link_cohort.csv",
        "target_dictionary_id_conflicts.csv",
        "multi_target_sequence_report.csv",
        "corpus_final.csv",
        "corpus_final.txt",
        "corpus_profile_report.md",
        "s6_profile_manifest.json",
    }
)
AUTHORISED_MODES: frozenset[str] = frozenset({"preview", "apply"})
PREVIEW_MODE = "preview"
APPLY_MODE = "apply"
TRACE_COLUMNS: tuple[str, ...] = (
    "step_number",
    "cluster_id",
    "trigger_target",
    "cluster_type",
    "cluster_total_identities",
    "trigger_target_identities_removed",
    "collateral_identities_removed",
    "collateral_target_counts_json",
    "denominator_before",
    "trigger_target_count_before",
    "trigger_target_share_before",
    "denominator_after",
    "trigger_target_count_after",
    "trigger_target_share_after",
    "max_target_share_after",
    "selection_rationale",
)
REMOVED_CLUSTER_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "first_step_number",
    "trigger_target",
    "cluster_type",
    "cluster_total_identities",
    "trigger_target_identities_removed",
    "collateral_identities_removed",
    "n_distinct_sequence_core",
)
TARGET_DISTRIBUTION_COLUMNS: tuple[str, ...] = (
    "canonical_target_name",
    "n_scientific_identities",
    "n_distinct_sequence_core",
    "n_clusters",
    "share",
    "exceeds_cap",
)
COLLATERAL_SIDECAR_COLUMNS: tuple[str, ...] = (
    "step_number",
    "cluster_id",
    "trigger_target",
    "non_trigger_target",
    "n_identities",
)


@dataclass(frozen=True)
class RemovalStep:
    step_number: int
    cluster_id: str
    trigger_target: str
    cluster_type: str
    cluster_total_identities: int
    trigger_target_identities_removed: int
    collateral_identities_removed: int
    collateral_target_counts: dict[str, int]
    denominator_before: int
    trigger_target_count_before: int
    trigger_target_share_before: Decimal
    denominator_after: int
    trigger_target_count_after: int
    trigger_target_share_after: Decimal
    max_target_share_after: Decimal
    selection_rationale: str

    def as_row(self) -> dict[str, str]:
        return {
            "step_number": str(self.step_number),
            "cluster_id": self.cluster_id,
            "trigger_target": self.trigger_target,
            "cluster_type": self.cluster_type,
            "cluster_total_identities": str(self.cluster_total_identities),
            "trigger_target_identities_removed": str(
                self.trigger_target_identities_removed
            ),
            "collateral_identities_removed": str(self.collateral_identities_removed),
            "collateral_target_counts_json": json.dumps(
                self.collateral_target_counts, sort_keys=True, ensure_ascii=False
            ),
            "denominator_before": str(self.denominator_before),
            "trigger_target_count_before": str(self.trigger_target_count_before),
            "trigger_target_share_before": format_share_value(
                self.trigger_target_share_before
            ),
            "denominator_after": str(self.denominator_after),
            "trigger_target_count_after": str(self.trigger_target_count_after),
            "trigger_target_share_after": format_share_value(
                self.trigger_target_share_after
            ),
            "max_target_share_after": format_share_value(self.max_target_share_after),
            "selection_rationale": self.selection_rationale,
        }


@dataclass
class TargetCapResult:
    steps: list[RemovalStep] = field(default_factory=list)
    retained_identity_ids: tuple[str, ...] = ()
    removed_identity_ids: tuple[str, ...] = ()
    removed_cluster_ids: tuple[str, ...] = ()
    input_n_identities: int = 0
    input_n_cores: int = 0
    input_n_clusters: int = 0
    input_n_targets: int = 0
    output_n_identities: int = 0
    output_n_cores: int = 0
    output_n_clusters: int = 0
    output_n_targets: int = 0
    max_target_share: Decimal = Decimal("0")
    max_target_name: str = ""
    n_pure_clusters_removed: int = 0
    n_mixed_clusters_removed: int = 0
    n_collateral_identities_removed: int = 0
    cap_gate_pass: bool = False
    independent_target_counts: dict[str, int] = field(default_factory=dict)
    assertions: dict[str, Any] = field(default_factory=dict)


def _blank(value: Any) -> str:
    return "" if value is None else str(value).strip()


def parse_fraction(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def format_share_value(share: Decimal) -> str:
    quantized = share.quantize(SHARE_QUANTUM, rounding=ROUND_HALF_EVEN)
    return format(quantized, "f")


def identity_share(count: int, denominator: int) -> Decimal:
    if denominator <= 0:
        raise S7TargetCapError("identity denominator must be positive")
    return Decimal(count) / Decimal(denominator)


def exceeds_cap(count: int, denominator: int, fraction: Decimal) -> bool:
    if denominator <= 0:
        raise S7TargetCapError("identity denominator must be positive")
    return identity_share(count, denominator) > fraction


def assert_no_sequence_leak(text: str, *, label: str) -> None:
    if SEQ_LEAK_RE.search(text or ""):
        raise S7TargetCapError(f"{label} must not contain biological sequence strings")


def assert_not_forbidden_output_path(path: Any) -> None:
    name = getattr(path, "name", str(path).rsplit("/", 1)[-1])
    if name in FORBIDDEN_OUTPUT_NAMES:
        raise S7TargetCapError(f"S7A must not write forbidden artefact {name}")


def enforce_shared_cap_policy(config: Mapping[str, Any]) -> None:
    fraction = parse_fraction(config.get("max_target_fraction"))
    if fraction != ACTIVE_MAX_TARGET_FRACTION:
        raise S7TargetCapError(
            f"active max_target_fraction must be 0.03, got {fraction}"
        )
    if _blank(config.get("training_sequence_column")) != "sequence_core":
        raise S7TargetCapError("training_sequence_column must be sequence_core")
    if _blank(config.get("cap_unit")) != "final_cluster":
        raise S7TargetCapError("cap_unit must be final_cluster")
    if _blank(config.get("denominator_semantics")) != "current_post_removal_identity_count":
        raise S7TargetCapError(
            "denominator_semantics must be current_post_removal_identity_count"
        )
    if _blank(config.get("cluster_integrity")) != "never_split_cluster":
        raise S7TargetCapError("cluster_integrity must be never_split_cluster")
    if config.get("target_pure_first") is not True:
        raise S7TargetCapError("target_pure_first must be true")
    if config.get("recompute_after_every_removal") is not True:
        raise S7TargetCapError("recompute_after_every_removal must be true")
    ordering = _blank(config.get("simultaneous_overrepresented_target_ordering"))
    if ordering != "fail_closed_unspecified":
        raise S7TargetCapError(
            "simultaneous overrepresented-target ordering must fail closed"
        )
    if config.get("no_partitioning") is False:
        raise S7TargetCapError("S7A must not populate partitions")
    if config.get("no_e5_promotion") is False:
        raise S7TargetCapError("S7A must not promote E5")
    if config.get("no_non_protein_promotion") is False:
        raise S7TargetCapError("S7A must not promote non-protein records")


def enforce_preview_config(config: Mapping[str, Any]) -> None:
    mode = _blank(config.get("mode"))
    if mode != PREVIEW_MODE:
        raise S7TargetCapError(f"S7A preview mode must be preview, got {mode!r}")
    if config.get("write_authoritative_capped_corpus") is True:
        raise S7TargetCapError("S7A preview must not write an authoritative capped corpus")
    enforce_shared_cap_policy(config)


def enforce_application_config(config: Mapping[str, Any]) -> None:
    mode = _blank(config.get("mode"))
    if mode != APPLY_MODE:
        raise S7TargetCapError(f"S7A application mode must be apply, got {mode!r}")
    if config.get("write_authoritative_capped_corpus") is not True:
        raise S7TargetCapError("S7A application must write the authoritative capped corpus")
    if config.get("no_partitioning") is False:
        raise S7TargetCapError("S7A application must not populate partitions")
    output_dir = _blank(config.get("output_dir"))
    preview_dir = _blank(config.get("preview_output_dir"))
    if not output_dir:
        raise S7TargetCapError("S7A application output_dir is required")
    if not preview_dir:
        raise S7TargetCapError("S7A application preview_output_dir is required")
    if output_dir == preview_dir:
        raise S7TargetCapError(
            "S7A application must not write to the reviewed preview directory"
        )
    enforce_shared_cap_policy(config)


def project_identity_rows(
    corpus_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    projected: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in corpus_rows:
        identity = _blank(row.get("scientific_identity_id"))
        cluster_id = _blank(row.get("cluster_id"))
        target = _blank(row.get("canonical_target_name"))
        core = _blank(row.get("sequence_core"))
        if not identity:
            raise S7TargetCapError("scientific_identity_id is required")
        if identity in seen:
            raise S7TargetCapError(f"duplicate scientific_identity_id {identity}")
        if not cluster_id:
            raise S7TargetCapError(f"{identity} is missing cluster_id")
        if not target:
            raise S7TargetCapError(f"{identity} is missing canonical_target_name")
        if not core:
            raise S7TargetCapError(f"{identity} is missing sequence_core")
        seen.add(identity)
        projected.append(
            {
                "scientific_identity_id": identity,
                "cluster_id": cluster_id,
                "canonical_target_name": target,
                "sequence_core": core,
                "evidence_level": _blank(row.get("evidence_level")),
                "target_type": _blank(row.get("target_type")),
                "partition": _blank(row.get("partition")),
            }
        )
    return projected


def _counts_from_ids(
    retained_ids: set[str],
    by_id: Mapping[str, Mapping[str, str]],
) -> tuple[int, Counter[str]]:
    counts: Counter[str] = Counter()
    for identity in retained_ids:
        counts[by_id[identity]["canonical_target_name"]] += 1
    return len(retained_ids), counts


def _overrepresented_targets(
    counts: Mapping[str, int],
    denominator: int,
    fraction: Decimal,
) -> list[tuple[str, int, Decimal]]:
    over: list[tuple[str, int, Decimal]] = []
    for target, count in counts.items():
        if exceeds_cap(count, denominator, fraction):
            over.append((target, count, identity_share(count, denominator)))
    over.sort(key=lambda item: item[0])
    return over


def _cluster_members(
    cluster_id: str,
    retained_ids: set[str],
    members_by_cluster: Mapping[str, Sequence[str]],
) -> list[str]:
    return [
        identity
        for identity in members_by_cluster[cluster_id]
        if identity in retained_ids
    ]


def _select_cluster(
    *,
    trigger_target: str,
    retained_ids: set[str],
    by_id: Mapping[str, Mapping[str, str]],
    members_by_cluster: Mapping[str, Sequence[str]],
) -> tuple[str, str, str]:
    pure_candidates: list[tuple[int, str]] = []
    mixed_candidates: list[tuple[int, int, str]] = []
    for cluster_id, members in members_by_cluster.items():
        retained_members = [
            identity for identity in members if identity in retained_ids
        ]
        if not retained_members:
            continue
        targets = {
            by_id[identity]["canonical_target_name"] for identity in retained_members
        }
        trigger_n = sum(
            1
            for identity in retained_members
            if by_id[identity]["canonical_target_name"] == trigger_target
        )
        if trigger_n == 0:
            continue
        if targets == {trigger_target}:
            pure_candidates.append((trigger_n, cluster_id))
        else:
            collateral = len(retained_members) - trigger_n
            mixed_candidates.append((collateral, trigger_n, cluster_id))
    if pure_candidates:
        # Largest trigger-target identity count, then stable cluster_id.
        pure_candidates.sort(key=lambda item: (-item[0], item[1]))
        cluster_id = pure_candidates[0][1]
        rationale = (
            f"Overrepresented target {trigger_target}. Selected target-pure cluster "
            f"{cluster_id} with {pure_candidates[0][0]} trigger-target identities "
            "(largest remaining target-pure cluster; stable cluster_id tie-break)."
        )
        return cluster_id, CLUSTER_TYPE_PURE, rationale
    if mixed_candidates:
        mixed_candidates.sort(key=lambda item: (item[0], item[2]))
        cluster_id = mixed_candidates[0][2]
        rationale = (
            f"Overrepresented target {trigger_target}. No remaining target-pure "
            f"cluster. Selected mixed cluster {cluster_id} with "
            f"{mixed_candidates[0][0]} collateral identities "
            "(least collateral; stable cluster_id tie-break)."
        )
        return cluster_id, CLUSTER_TYPE_MIXED, rationale
    raise S7TargetCapError(
        f"no remaining cluster touches overrepresented target {trigger_target}"
    )


def _max_share(counts: Mapping[str, int], denominator: int) -> tuple[str, Decimal]:
    best_target = ""
    best_share = Decimal("-1")
    for target, count in sorted(counts.items()):
        share = identity_share(count, denominator)
        if share > best_share:
            best_target = target
            best_share = share
    return best_target, max(best_share, Decimal("0"))


def select_target_cap(
    corpus_rows: Sequence[Mapping[str, str]],
    *,
    max_target_fraction: Decimal | float | str = ACTIVE_MAX_TARGET_FRACTION,
) -> TargetCapResult:
    """Deterministic whole-cluster target-cap selection.

    Does not mutate ``corpus_rows``. Does not assign partitions.
    """
    fraction = parse_fraction(max_target_fraction)
    identities = project_identity_rows(corpus_rows)
    by_id = {row["scientific_identity_id"]: row for row in identities}
    members_by_cluster: dict[str, list[str]] = defaultdict(list)
    for row in identities:
        members_by_cluster[row["cluster_id"]].append(row["scientific_identity_id"])
    for cluster_id in members_by_cluster:
        members_by_cluster[cluster_id].sort()

    retained_ids = set(by_id)
    removed_ids: set[str] = set()
    removed_clusters: list[str] = []
    steps: list[RemovalStep] = []
    input_n = len(identities)
    input_cores = len({row["sequence_core"] for row in identities})
    input_clusters = len(members_by_cluster)
    input_targets = len({row["canonical_target_name"] for row in identities})

    while True:
        denominator, counts = _counts_from_ids(retained_ids, by_id)
        if denominator == 0:
            raise S7TargetCapError("target cap removed every scientific identity")
        over = _overrepresented_targets(counts, denominator, fraction)
        if not over:
            break
        if len(over) > 1:
            detail = ", ".join(
                f"{target}={count}/{denominator} ({format_share_value(share)})"
                for target, count, share in over
            )
            raise S7TargetCapError(
                "CHECKPOINT-3 does not authorise an ordering rule among multiple "
                "simultaneously overrepresented targets; fail closed. "
                f"step={len(steps) + 1}; targets: {detail}"
            )
        trigger_target, trigger_count, trigger_share = over[0]
        cluster_id, cluster_type, rationale = _select_cluster(
            trigger_target=trigger_target,
            retained_ids=retained_ids,
            by_id=by_id,
            members_by_cluster=members_by_cluster,
        )
        members = _cluster_members(cluster_id, retained_ids, members_by_cluster)
        if not members:
            raise S7TargetCapError(f"selected empty cluster {cluster_id}")
        collateral_counts: Counter[str] = Counter()
        trigger_removed = 0
        for identity in members:
            target = by_id[identity]["canonical_target_name"]
            if target == trigger_target:
                trigger_removed += 1
            else:
                collateral_counts[target] += 1
        denominator_after = denominator - len(members)
        trigger_after = trigger_count - trigger_removed
        retained_ids.difference_update(members)
        removed_ids.update(members)
        removed_clusters.append(cluster_id)
        _, counts_after = _counts_from_ids(retained_ids, by_id)
        max_target_name, max_share_after = _max_share(counts_after, denominator_after)
        steps.append(
            RemovalStep(
                step_number=len(steps) + 1,
                cluster_id=cluster_id,
                trigger_target=trigger_target,
                cluster_type=cluster_type,
                cluster_total_identities=len(members),
                trigger_target_identities_removed=trigger_removed,
                collateral_identities_removed=sum(collateral_counts.values()),
                collateral_target_counts={
                    target: collateral_counts[target]
                    for target in sorted(collateral_counts)
                },
                denominator_before=denominator,
                trigger_target_count_before=trigger_count,
                trigger_target_share_before=trigger_share,
                denominator_after=denominator_after,
                trigger_target_count_after=trigger_after,
                trigger_target_share_after=(
                    identity_share(trigger_after, denominator_after)
                    if denominator_after
                    else Decimal("0")
                ),
                max_target_share_after=max_share_after,
                selection_rationale=rationale,
            )
        )
        del max_target_name

    retained_sorted = tuple(sorted(retained_ids))
    removed_sorted = tuple(sorted(removed_ids))
    result = TargetCapResult(
        steps=steps,
        retained_identity_ids=retained_sorted,
        removed_identity_ids=removed_sorted,
        removed_cluster_ids=tuple(removed_clusters),
        input_n_identities=input_n,
        input_n_cores=input_cores,
        input_n_clusters=input_clusters,
        input_n_targets=input_targets,
        n_pure_clusters_removed=sum(
            1 for step in steps if step.cluster_type == CLUSTER_TYPE_PURE
        ),
        n_mixed_clusters_removed=sum(
            1 for step in steps if step.cluster_type == CLUSTER_TYPE_MIXED
        ),
        n_collateral_identities_removed=sum(
            step.collateral_identities_removed for step in steps
        ),
    )
    return validate_target_cap_result(
        corpus_rows,
        result,
        max_target_fraction=fraction,
        identities=identities,
    )


def independent_target_distribution(
    rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    grouped: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[_blank(row.get("canonical_target_name"))].append(row)
    denominator = len(rows)
    out: list[dict[str, str]] = []
    for target in sorted(grouped, key=lambda name: (-len(grouped[name]), name)):
        members = grouped[target]
        count = len(members)
        share = identity_share(count, denominator) if denominator else Decimal("0")
        cores = { _blank(row.get("sequence_core")) for row in members }
        clusters = { _blank(row.get("cluster_id")) for row in members }
        out.append(
            {
                "canonical_target_name": target,
                "n_scientific_identities": str(count),
                "n_distinct_sequence_core": str(len(cores)),
                "n_clusters": str(len(clusters)),
                "share": format_share_value(share),
                "exceeds_cap": "true" if exceeds_cap(count, denominator, ACTIVE_MAX_TARGET_FRACTION) else "false",
            }
        )
    return out


def validate_target_cap_result(
    corpus_rows: Sequence[Mapping[str, str]],
    result: TargetCapResult,
    *,
    max_target_fraction: Decimal | float | str = ACTIVE_MAX_TARGET_FRACTION,
    identities: Sequence[Mapping[str, str]] | None = None,
) -> TargetCapResult:
    fraction = parse_fraction(max_target_fraction)
    projected = list(identities) if identities is not None else project_identity_rows(corpus_rows)
    by_id = {row["scientific_identity_id"]: row for row in projected}
    all_ids = set(by_id)
    retained = set(result.retained_identity_ids)
    removed = set(result.removed_identity_ids)
    if retained | removed != all_ids:
        raise S7TargetCapError("every input identity must be retained or removed")
    if retained & removed:
        raise S7TargetCapError("an identity cannot be both retained and removed")

    members_by_cluster: dict[str, list[str]] = defaultdict(list)
    for row in projected:
        members_by_cluster[row["cluster_id"]].append(row["scientific_identity_id"])
    for cluster_id, members in members_by_cluster.items():
        member_set = set(members)
        n_retained = len(member_set & retained)
        n_removed = len(member_set & removed)
        if n_retained and n_removed:
            raise S7TargetCapError(
                f"cluster {cluster_id} is partly retained and partly removed"
            )

    cores_retained = {
        by_id[identity]["sequence_core"] for identity in retained
    }
    cores_removed = {
        by_id[identity]["sequence_core"] for identity in removed
    }
    spanning = cores_retained & cores_removed
    if spanning:
        raise S7TargetCapError(
            "sequence_core spans retained and removed sides through cluster inconsistency"
        )

    retained_rows = [by_id[identity] for identity in retained]
    if any(_blank(row.get("partition")) != "" for row in retained_rows):
        raise S7TargetCapError("S7A retained identities must keep blank partition")
    if any(_blank(row.get("evidence_level")) == "E5" for row in retained_rows):
        raise S7TargetCapError("S7A must not introduce E5 identities")
    if any(
        _blank(row.get("target_type")) not in {"", "protein"}
        for row in retained_rows
    ):
        raise S7TargetCapError("S7A must not introduce non-protein identities")

    independent_counts: Counter[str] = Counter(
        row["canonical_target_name"] for row in retained_rows
    )
    denominator = len(retained_rows)
    max_target = ""
    max_share = Decimal("0")
    for target, count in sorted(independent_counts.items()):
        share = identity_share(count, denominator)
        if exceeds_cap(count, denominator, fraction):
            raise S7TargetCapError(
                f"independent final share for {target} is {format_share_value(share)} > {fraction}"
            )
        if share > max_share:
            max_target = target
            max_share = share
    result.output_n_identities = denominator
    result.output_n_cores = len({row["sequence_core"] for row in retained_rows})
    result.output_n_clusters = len({row["cluster_id"] for row in retained_rows})
    result.output_n_targets = len(independent_counts)
    result.max_target_share = max_share
    result.max_target_name = max_target
    result.cap_gate_pass = max_share <= fraction
    result.independent_target_counts = dict(independent_counts)
    result.assertions = {
        "every_identity_accounted": True,
        "no_partial_clusters": True,
        "no_sequence_core_span": True,
        "no_partition_assigned": True,
        "no_e5_introduced": True,
        "no_non_protein_introduced": True,
        "independent_max_share_le_cap": True,
        "input_unmutated_required": True,
    }
    if not result.cap_gate_pass:
        raise S7TargetCapError("final max target share exceeds the 0.03 cap")
    return result


def removed_cluster_rows(
    corpus_rows: Sequence[Mapping[str, str]],
    result: TargetCapResult,
) -> list[dict[str, str]]:
    by_id = {
        row["scientific_identity_id"]: row
        for row in project_identity_rows(corpus_rows)
    }
    first_step = {step.cluster_id: step for step in result.steps}
    out: list[dict[str, str]] = []
    for cluster_id in result.removed_cluster_ids:
        step = first_step[cluster_id]
        members = [
            by_id[identity]
            for identity in result.removed_identity_ids
            if by_id[identity]["cluster_id"] == cluster_id
        ]
        cores = {row["sequence_core"] for row in members}
        out.append(
            {
                "cluster_id": cluster_id,
                "first_step_number": str(step.step_number),
                "trigger_target": step.trigger_target,
                "cluster_type": step.cluster_type,
                "cluster_total_identities": str(step.cluster_total_identities),
                "trigger_target_identities_removed": str(
                    step.trigger_target_identities_removed
                ),
                "collateral_identities_removed": str(
                    step.collateral_identities_removed
                ),
                "n_distinct_sequence_core": str(len(cores)),
            }
        )
    return out


def collateral_sidecar_rows(result: TargetCapResult) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for step in result.steps:
        if step.cluster_type != CLUSTER_TYPE_MIXED:
            continue
        for target, count in step.collateral_target_counts.items():
            rows.append(
                {
                    "step_number": str(step.step_number),
                    "cluster_id": step.cluster_id,
                    "trigger_target": step.trigger_target,
                    "non_trigger_target": target,
                    "n_identities": str(count),
                }
            )
    return rows


def compare_target_cap_results(first: TargetCapResult, second: TargetCapResult) -> None:
    if [step.as_row() for step in first.steps] != [step.as_row() for step in second.steps]:
        raise S7TargetCapError("target-cap selection is not deterministic")
    if first.retained_identity_ids != second.retained_identity_ids:
        raise S7TargetCapError("retained identity set is not deterministic")
    if first.removed_cluster_ids != second.removed_cluster_ids:
        raise S7TargetCapError("removed cluster order is not deterministic")


def build_preview_report(
    *,
    input_sha256: str,
    result: TargetCapResult,
    pre_cap_max_target: str,
    pre_cap_max_share: Decimal,
    distribution_rows: Sequence[Mapping[str, str]],
    other_target_exceeded_after_reduction: bool,
) -> str:
    lines = [
        "# S7A target-cap preview (dry-run)",
        "",
        "This report is a **validated preview**. It does not apply the scientific",
        "target cap to an authoritative corpus. Human review is required before",
        "cap application. No FT/REF/EVAL values were assigned.",
        "",
        "## Frozen input",
        "",
        f"- SHA-256: `{input_sha256}`",
        f"- identities: {result.input_n_identities}",
        f"- distinct sequence_core: {result.input_n_cores}",
        f"- clusters: {result.input_n_clusters}",
        f"- canonical targets: {result.input_n_targets}",
        f"- pre-cap max target: {pre_cap_max_target}",
        f"- pre-cap max share: {format_share_value(pre_cap_max_share)}",
        "",
        "## Aggregate preview result",
        "",
        f"- removal steps: {len(result.steps)}",
        f"- clusters proposed removed: {len(result.removed_cluster_ids)}",
        f"- identities proposed removed: {len(result.removed_identity_ids)}",
        f"- sequence cores proposed removed: {result.input_n_cores - result.output_n_cores}",
        f"- initial identity denominator: {result.input_n_identities}",
        f"- final preview identity denominator: {result.output_n_identities}",
        f"- initial cluster count: {result.input_n_clusters}",
        f"- final preview cluster count: {result.output_n_clusters}",
        f"- initial target count: {result.input_n_targets}",
        f"- final preview target count: {result.output_n_targets}",
        f"- maximum final target share: {format_share_value(result.max_target_share)} ({result.max_target_name})",
        f"- all-target <= 3% gate: {'PASS' if result.cap_gate_pass else 'FAIL'}",
        f"- pure clusters removed: {result.n_pure_clusters_removed}",
        f"- mixed clusters removed: {result.n_mixed_clusters_removed}",
        f"- collateral identities removed: {result.n_collateral_identities_removed}",
        f"- any non-initial-dominant target exceeded 3% after denominator reduction: "
        f"{'yes' if other_target_exceeded_after_reduction else 'no'}",
        "",
        "## Removal trace",
        "",
        "| step | cluster_id | trigger target | pure/mixed | target identities | collateral | denominator before | share before | denominator after | share after |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for step in result.steps:
        lines.append(
            f"| {step.step_number} | `{step.cluster_id}` | {step.trigger_target} | "
            f"{step.cluster_type} | {step.trigger_target_identities_removed} | "
            f"{step.collateral_identities_removed} | {step.denominator_before} | "
            f"{format_share_value(step.trigger_target_share_before)} | "
            f"{step.denominator_after} | {format_share_value(step.trigger_target_share_after)} |"
        )
    if not result.steps:
        lines.append("| — | — | — | — | 0 | 0 | — | — | — | — |")
    lines.extend(
        [
            "",
            "## Independent top retained targets",
            "",
            "| target | retained identities | final share |",
            "| --- | ---: | ---: |",
        ]
    )
    for row in list(distribution_rows)[:10]:
        lines.append(
            f"| {row['canonical_target_name']} | {row['n_scientific_identities']} | {row['share']} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- authoritative capped corpus written = no",
            "- scientific target cap applied = no",
            "- FT/REF/EVAL assigned = no",
            "- S5 input mutated = no",
            "",
        ]
    )
    report = "\n".join(lines)
    assert_no_sequence_leak(report, label="s7a_target_cap_preview_report.md")
    return report


def input_unmutated(original: Sequence[Mapping[str, str]], snapshot: Sequence[Mapping[str, Any]]) -> bool:
    if len(original) != len(snapshot):
        return False
    for left, right in zip(original, snapshot, strict=True):
        if dict(left) != dict(right):
            return False
    return True


def retained_corpus_rows(
    corpus_rows: Sequence[Mapping[str, str]],
    retained_identity_ids: Sequence[str],
) -> list[dict[str, str]]:
    retained = set(retained_identity_ids)
    return [
        dict(row)
        for row in corpus_rows
        if row["scientific_identity_id"] in retained
    ]


def _count_mismatch(label: str, expected: Any, observed: Any) -> str | None:
    if expected != observed:
        return f"{label}: expected {expected}, got {observed}"
    return None


def preview_application_parity_mismatches(
    *,
    preview_step_rows: Sequence[Mapping[str, str]],
    application: TargetCapResult,
    preview_summary: Mapping[str, Any] | None = None,
) -> list[str]:
    """Post-derivation comparison. Does not select clusters."""
    mismatches: list[str] = []
    apply_rows = [step.as_row() for step in application.steps]
    mismatches.append(
        _count_mismatch("n_removal_steps", len(preview_step_rows), len(apply_rows))
    )
    preview_ids = [row.get("cluster_id", "") for row in preview_step_rows]
    apply_ids = [row.get("cluster_id", "") for row in apply_rows]
    mismatches.append(
        _count_mismatch("removal_order_cluster_ids", preview_ids, apply_ids)
    )
    mismatches.append(
        _count_mismatch(
            "trigger_targets",
            [row.get("trigger_target", "") for row in preview_step_rows],
            [row.get("trigger_target", "") for row in apply_rows],
        )
    )
    mismatches.append(
        _count_mismatch(
            "cluster_types",
            [row.get("cluster_type", "") for row in preview_step_rows],
            [row.get("cluster_type", "") for row in apply_rows],
        )
    )
    mismatches.append(
        _count_mismatch(
            "trigger_target_identities_removed",
            [row.get("trigger_target_identities_removed", "") for row in preview_step_rows],
            [row.get("trigger_target_identities_removed", "") for row in apply_rows],
        )
    )
    mismatches.append(
        _count_mismatch(
            "collateral_identities",
            [row.get("collateral_identities_removed", "") for row in preview_step_rows],
            [row.get("collateral_identities_removed", "") for row in apply_rows],
        )
    )
    for field in (
        "denominator_before",
        "denominator_after",
        "trigger_target_count_before",
        "trigger_target_count_after",
        "trigger_target_share_before",
        "trigger_target_share_after",
        "max_target_share_after",
    ):
        mismatches.append(
            _count_mismatch(
                field,
                [row.get(field, "") for row in preview_step_rows],
                [row.get(field, "") for row in apply_rows],
            )
        )
    if preview_summary:
        mismatches.append(
            _count_mismatch(
                "final_retained_identities",
                int(preview_summary.get("n_scientific_identities", -1)),
                application.output_n_identities,
            )
        )
        mismatches.append(
            _count_mismatch(
                "final_retained_clusters",
                int(preview_summary.get("n_final_clusters", -1)),
                application.output_n_clusters,
            )
        )
        mismatches.append(
            _count_mismatch(
                "final_retained_cores",
                int(preview_summary.get("n_distinct_sequence_core", -1)),
                application.output_n_cores,
            )
        )
        mismatches.append(
            _count_mismatch(
                "final_retained_targets",
                int(preview_summary.get("n_canonical_targets", -1)),
                application.output_n_targets,
            )
        )
        mismatches.append(
            _count_mismatch(
                "final_max_target_share",
                str(preview_summary.get("max_target_share", "")),
                format_share_value(application.max_target_share),
            )
        )
    return [item for item in mismatches if item]


def approval_parity_mismatches(
    application: TargetCapResult,
    approval: Mapping[str, Any],
) -> list[str]:
    """Post-derivation audit check. Never used to select clusters."""
    mismatches: list[str] = []
    reviewed = approval.get("reviewed_preview") or {}
    mismatches.append(
        _count_mismatch(
            "approval.input_identities",
            int(reviewed.get("input_identities", -1)),
            application.input_n_identities,
        )
    )
    mismatches.append(
        _count_mismatch(
            "approval.proposed_removed_clusters",
            int(reviewed.get("proposed_removed_clusters", -1)),
            len(application.removed_cluster_ids),
        )
    )
    mismatches.append(
        _count_mismatch(
            "approval.proposed_removed_identities",
            int(reviewed.get("proposed_removed_identities", -1)),
            len(application.removed_identity_ids),
        )
    )
    mismatches.append(
        _count_mismatch(
            "approval.expected_post_cap_identities",
            int(reviewed.get("expected_post_cap_identities", -1)),
            application.output_n_identities,
        )
    )
    mismatches.append(
        _count_mismatch(
            "approval.expected_post_cap_clusters",
            int(reviewed.get("expected_post_cap_clusters", -1)),
            application.output_n_clusters,
        )
    )
    mismatches.append(
        _count_mismatch(
            "approval.expected_max_target_share",
            str(reviewed.get("expected_max_target_share", "")),
            format_share_value(application.max_target_share),
        )
    )
    expected_ids = [str(item) for item in reviewed.get("selected_cluster_ids", [])]
    mismatches.append(
        _count_mismatch(
            "approval.selected_cluster_ids",
            expected_ids,
            list(application.removed_cluster_ids),
        )
    )
    return [item for item in mismatches if item]


def independent_post_cap_invariants(
    *,
    input_rows: Sequence[Mapping[str, str]],
    retained_rows: Sequence[Mapping[str, str]],
    result: TargetCapResult,
    max_target_fraction: Decimal | float | str = ACTIVE_MAX_TARGET_FRACTION,
) -> dict[str, Any]:
    """Recompute post-cap invariants from retained rows, not loop counters."""
    fraction = parse_fraction(max_target_fraction)
    retained_ids = [row["scientific_identity_id"] for row in retained_rows]
    if len(retained_ids) != len(set(retained_ids)):
        raise S7TargetCapError("duplicate scientific_identity_id in retained corpus")
    if any(not _blank(row.get("cluster_id")) for row in retained_rows):
        raise S7TargetCapError("missing cluster_id in retained corpus")
    if any(_blank(row.get("partition")) != "" for row in retained_rows):
        raise S7TargetCapError("partition values must remain blank after S7A")
    evidence = Counter(_blank(row.get("evidence_level")) for row in retained_rows)
    if evidence.get("E5", 0) != 0:
        raise S7TargetCapError("S7A post-cap corpus contains E5 identities")
    non_protein = sum(
        1 for row in retained_rows if _blank(row.get("target_type")) != "protein"
    )
    if non_protein:
        raise S7TargetCapError("S7A post-cap corpus contains non-protein identities")

    input_by_id = {row["scientific_identity_id"]: dict(row) for row in input_rows}
    retained_set = set(retained_ids)
    removed_set = set(result.removed_identity_ids)
    all_input = {row["scientific_identity_id"] for row in input_rows}
    if retained_set | removed_set != all_input:
        raise S7TargetCapError("retained+removed identities do not equal frozen S5 identities")
    if retained_set & removed_set:
        raise S7TargetCapError("retained and removed identity sets overlap")
    if set(result.retained_identity_ids) != retained_set:
        raise S7TargetCapError("written retained identities disagree with selection result")

    members_by_cluster: dict[str, list[str]] = defaultdict(list)
    for row in input_rows:
        members_by_cluster[row["cluster_id"]].append(row["scientific_identity_id"])
    for cluster_id, members in members_by_cluster.items():
        member_set = set(members)
        n_retained = len(member_set & retained_set)
        n_removed = len(member_set & removed_set)
        if n_retained and n_removed:
            raise S7TargetCapError(
                f"cluster {cluster_id} is partly retained and partly removed"
            )
        core_disposition: dict[str, set[str]] = defaultdict(set)
        for identity in members:
            side = "retained" if identity in retained_set else "removed"
            core_disposition[input_by_id[identity]["sequence_core"]].add(side)
        if any(len(sides) != 1 for sides in core_disposition.values()):
            raise S7TargetCapError(
                f"sequence_core in cluster {cluster_id} spans retained and removed"
            )

    unexpected_removed = removed_set - {
        row["scientific_identity_id"]
        for row in input_rows
        if row["cluster_id"] in set(result.removed_cluster_ids)
    }
    if unexpected_removed:
        raise S7TargetCapError("identities removed outside the selected clusters")

    by_id = {row["scientific_identity_id"]: row for row in retained_rows}
    for identity in retained_ids:
        original = input_by_id[identity]
        written = by_id[identity]
        for key in original:
            if original.get(key, "") != written.get(key, ""):
                raise S7TargetCapError(
                    f"retained field {key} changed for {identity}"
                )

    counts = Counter(row["canonical_target_name"] for row in retained_rows)
    denominator = len(retained_rows)
    over = [
        target
        for target, count in counts.items()
        if exceeds_cap(count, denominator, fraction)
    ]
    max_target, max_share = (
        _max_share(counts, denominator) if counts else ("", Decimal("0"))
    )
    distribution = independent_target_distribution(retained_rows)
    if any(row["exceeds_cap"] != "false" for row in distribution):
        raise S7TargetCapError("independent distribution reports a target over the 3% cap")
    if max_share > fraction:
        raise S7TargetCapError("independent max target share exceeds the 0.03 cap")

    return {
        "n_scientific_identities": denominator,
        "n_distinct_sequence_core": len({row["sequence_core"] for row in retained_rows}),
        "n_final_clusters": len({row["cluster_id"] for row in retained_rows}),
        "n_canonical_targets": len(counts),
        "n_identities_removed": len(removed_set),
        "n_cores_removed": len({input_by_id[i]["sequence_core"] for i in removed_set}),
        "n_clusters_removed": len(result.removed_cluster_ids),
        "n_targets_lost_entirely": result.input_n_targets - len(counts),
        "duplicate_scientific_identity_id": 0,
        "missing_cluster_id": 0,
        "partition_nonblank": 0,
        "partial_clusters": 0,
        "identity_sets_disjoint": True,
        "identity_union_complete": True,
        "unexpected_removals": 0,
        "fields_unchanged": True,
        "evidence_counts": dict(evidence),
        "source_counts": dict(
            Counter(_blank(row.get("source_db")) for row in retained_rows)
        ),
        "chemistry_counts": dict(
            Counter(_blank(row.get("chemistry")) for row in retained_rows)
        ),
        "target_type_counts": dict(
            Counter(_blank(row.get("target_type")) for row in retained_rows)
        ),
        "max_target_name": max_target,
        "max_target_share": format_share_value(max_share),
        "targets_over_cap": over,
        "cap_gate": "PASS" if not over and max_share <= fraction else "FAIL",
        "distribution_top10": distribution[:10],
        "ngf_count": counts.get("NGF", 0),
    }


def build_application_report(
    *,
    input_sha256: str,
    result: TargetCapResult,
    pre_cap_max_target: str,
    pre_cap_max_share: Decimal,
    distribution_rows: Sequence[Mapping[str, str]],
    other_target_exceeded_after_reduction: bool,
    preview_hashes: Mapping[str, str],
    output_hashes: Mapping[str, str],
    parity_mismatches: Sequence[str],
    independent: Mapping[str, Any],
    determinism_ok: bool,
) -> str:
    lines = [
        "# S7A target-cap application",
        "",
        "This report records the **authoritative S7A whole-cluster 3% cap**",
        "applied to the frozen final S5 corpus. The post-cap corpus is",
        "pre-partition. No FT/REF/EVAL values were assigned. S7B has not",
        "started.",
        "",
        "## Frozen input",
        "",
        f"- SHA-256: `{input_sha256}`",
        f"- identities: {result.input_n_identities}",
        f"- distinct sequence_core: {result.input_n_cores}",
        f"- clusters: {result.input_n_clusters}",
        f"- canonical targets: {result.input_n_targets}",
        f"- pre-cap max target: {pre_cap_max_target}",
        f"- pre-cap max share: {format_share_value(pre_cap_max_share)}",
        "",
        "## Human-approved preview",
        "",
        "- review_status: approved_for_application",
        "- decision_date: 2026-09-21",
        "- approval metadata was not used to select clusters",
        f"- preview/application semantic mismatches: {len(parity_mismatches)}",
        "",
        "## Reviewed preview artefact hashes",
        "",
    ]
    for name in sorted(preview_hashes):
        lines.append(f"- `{name}`: `{preview_hashes[name]}`")
    lines.extend(
        [
            "",
            "## Authoritative application result",
            "",
            f"- identities retained: {result.output_n_identities}",
            f"- distinct sequence_core retained: {result.output_n_cores}",
            f"- clusters retained: {result.output_n_clusters}",
            f"- canonical targets retained: {result.output_n_targets}",
            f"- identities removed: {len(result.removed_identity_ids)}",
            f"- sequence cores removed: {result.input_n_cores - result.output_n_cores}",
            f"- clusters removed: {len(result.removed_cluster_ids)}",
            f"- targets lost entirely: {independent.get('n_targets_lost_entirely', 0)}",
            f"- pure clusters removed: {result.n_pure_clusters_removed}",
            f"- mixed clusters removed: {result.n_mixed_clusters_removed}",
            f"- collateral identities removed: {result.n_collateral_identities_removed}",
            f"- maximum final target share: {format_share_value(result.max_target_share)} ({result.max_target_name})",
            f"- all-target <= 3% gate: {'PASS' if result.cap_gate_pass else 'FAIL'}",
            "- any non-initial-dominant target exceeded 3% after denominator reduction: "
            f"{'yes' if other_target_exceeded_after_reduction else 'no'}",
            "",
            "## Removal trace",
            "",
            "| step | cluster_id | trigger target | pure/mixed | target identities | collateral | denominator before | share before | denominator after | share after |",
            "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for step in result.steps:
        lines.append(
            f"| {step.step_number} | `{step.cluster_id}` | {step.trigger_target} | "
            f"{step.cluster_type} | {step.trigger_target_identities_removed} | "
            f"{step.collateral_identities_removed} | {step.denominator_before} | "
            f"{format_share_value(step.trigger_target_share_before)} | "
            f"{step.denominator_after} | {format_share_value(step.trigger_target_share_after)} |"
        )
    if not result.steps:
        lines.append("| — | — | — | — | 0 | 0 | — | — | — | — |")
    lines.extend(
        [
            "",
            "## Independent top retained targets",
            "",
            "| target | retained identities | final share | exceeds 3% |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in list(distribution_rows)[:10]:
        lines.append(
            f"| {row['canonical_target_name']} | {row['n_scientific_identities']} | "
            f"{row['share']} | {row['exceeds_cap']} |"
        )
    evidence = independent.get("evidence_counts") or {}
    lines.extend(
        [
            "",
            "## Post-cap biological-scope aggregates",
            "",
            f"- E2: {evidence.get('E2', 0)}",
            f"- E3: {evidence.get('E3', 0)}",
            f"- E4: {evidence.get('E4', 0)}",
            f"- E5: {evidence.get('E5', 0)}",
            f"- target_type: {json.dumps(independent.get('target_type_counts') or {}, sort_keys=True)}",
            f"- chemistry: {json.dumps(independent.get('chemistry_counts') or {}, sort_keys=True)}",
            f"- source_db: {json.dumps(independent.get('source_counts') or {}, sort_keys=True)}",
            "",
            "## Authoritative output hashes",
            "",
        ]
    )
    for name in sorted(output_hashes):
        lines.append(f"- `{name}`: `{output_hashes[name]}`")
    lines.extend(
        [
            "",
            "## Determinism and boundary",
            "",
            f"- deterministic rerun: {'PASS' if determinism_ok else 'FAIL'}",
            "- authoritative post-cap corpus written = yes",
            "- scientific target cap applied = yes",
            "- FT/REF/EVAL assigned = no",
            "- S7B started = no",
            "- S5 input mutated = no",
            "",
        ]
    )
    report = "\n".join(lines)
    assert_no_sequence_leak(report, label="s7a_target_cap_report.md")
    return report

"""GLOBAL S7B — deterministic whole-cluster FT/REF/EVAL assignment.

Preview mode writes sequence-free dry-run artefacts. Apply mode rederives
the same assignment from frozen S7A input, writes the authoritative
partitioned corpus under ignored ``data/``, and freezes REF/EVAL.

This module does not create an FT train/validation split, write
``corpus_final``, promote E5, promote non-protein records, rewrite
S5/S6/S7A, or begin S7C.

Authority: CHECKPOINT-3 C3-02 and governing plan §1.1.

Length-regime labels reuse the frozen S6 two-component GMM
(``gmm_k2_maximum_posterior``). The GMM is not refit on the post-cap
corpus.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Mapping, Sequence

from adapters.s4_scientific_common import ScientificProposalError
from adapters.s6_profile import (
    GMM_POSTERIOR_ASSIGNMENT_METHOD,
    gmm_posterior_assignment,
    length_of,
)
from adapters.target_extraction_common import SEQ_LEAK_RE

import numpy as np

S7PartitionError = ScientificProposalError

PARTITION_LABELS: tuple[str, ...] = ("EVAL", "FT", "REF")
REPORT_PARTITION_ORDER: tuple[str, ...] = ("FT", "REF", "EVAL")
DEFAULT_FRACTIONS: dict[str, Fraction] = {
    "FT": Fraction(4, 5),
    "REF": Fraction(1, 10),
    "EVAL": Fraction(1, 10),
}
PRIMARY_CRITERIA: tuple[str, ...] = (
    "target",
    "evidence",
    "length_regime",
    "source",
)
LENGTH_REGIME_LABELS: tuple[str, ...] = ("short", "long")
EVIDENCE_LEVELS: tuple[str, ...] = ("E2", "E3", "E4")
JSD_LOG_BASE: float = 2.0
JSD_EMPTY = math.log(2.0) / math.log(JSD_LOG_BASE)  # 1.0 bit
UNKNOWN_FAMILY = "unknown"
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
        "corpus_final.csv",
        "corpus_final.txt",
        "FT.csv",
        "REF.csv",
        "EVAL.csv",
        "corpus_clustered_final.csv",
        "clusters_final.tsv",
        "corpus_post_cap.csv",
        "s7a_target_cap_removal_trace.csv",
        "s7a_removed_clusters.csv",
        "s7a_post_cap_target_distribution.csv",
        "s7a_target_cap_report.md",
        "s7a_target_cap_manifest.json",
        "corpus_profile_report.md",
        "s6_profile_manifest.json",
    }
)
PREVIEW_MODE = "preview"
APPLY_MODE = "apply"
AUTHORISED_MODES: frozenset[str] = frozenset({PREVIEW_MODE, APPLY_MODE})
FREEZE_DATE = "2026-09-21"
FREEZE_REASON = (
    "top-level FT/REF/EVAL assignment approved before any model-selection, "
    "fine-tuning, hyperparameter or REF-calibration use"
)
VALID_PARTITION_LABELS: frozenset[str] = frozenset(REPORT_PARTITION_ORDER)
OBJECTIVE_PROFILE_JSD = "jsd_minimax"
OBJECTIVE_PROFILE_ABSDEV = "max_abs_proportion_deviation"
DEFAULT_OBJECTIVE_PROFILE = OBJECTIVE_PROFILE_JSD
COMPARISON_TUPLE_FIELDS: tuple[str, ...] = (
    "O1_max_primary_D",
    "lexicographic_descending_D_vector",
    "O3_sum_primary_D",
    "assignment_signature",
)
ABSDEV_COMPARISON_TUPLE_FIELDS: tuple[str, ...] = (
    "R1_max_primary_M",
    "lexicographic_descending_M_vector",
    "R3_sum_primary_M",
    "lexicographic_descending_D_vector",
    "sum_primary_D",
    "assignment_signature",
)
# Screened candidate rejection only. An exact js_from_vec rescore still
# decides every swap that this margin cannot prove is strictly worse.
_JSD_SCREEN_EPS = 1e-8
_SEARCH_BATCH_CHUNK = 64
CLUSTER_ORDERING: tuple[str, ...] = (
    "n_identities_descending",
    "n_distinct_canonical_targets_descending",
    "n_distinct_sequence_core_descending",
    "cluster_id_ascending",
)
CLUSTER_PREVIEW_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "proposed_partition",
    "cluster_identity_count",
    "cluster_core_count",
    "n_distinct_canonical_targets",
    "n_distinct_primary_sources",
    "n_short_cores",
    "n_long_cores",
    "n_e2",
    "n_e3",
    "n_e4",
    "multi_target_cluster",
    "multi_source_cluster",
)
CLUSTER_ASSIGNMENT_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "partition",
    "cluster_identity_count",
    "cluster_core_count",
    "n_distinct_canonical_targets",
    "n_distinct_primary_sources",
    "n_short_cores",
    "n_long_cores",
    "n_e2",
    "n_e3",
    "n_e4",
    "multi_target_cluster",
    "multi_source_cluster",
)
IDENTITY_SUMMARY_COLUMNS: tuple[str, ...] = (
    "partition",
    "n_clusters",
    "cluster_fraction",
    "n_identities",
    "identity_fraction",
    "n_canonical_targets_represented",
    "n_e2",
    "n_e3",
    "n_e4",
    "prop_e2",
    "prop_e3",
    "prop_e4",
    "n_multi_target_clusters",
    "n_multi_source_clusters",
)
CORE_SUMMARY_COLUMNS: tuple[str, ...] = (
    "partition",
    "n_distinct_cores",
    "core_fraction",
    "n_short_cores",
    "n_long_cores",
    "prop_short",
    "prop_long",
)
TARGET_DISTRIBUTION_COLUMNS: tuple[str, ...] = (
    "canonical_target_name",
    "n_global",
    "share_global",
    "n_FT",
    "share_FT",
    "n_REF",
    "share_REF",
    "n_EVAL",
    "share_EVAL",
    "n_partitions_represented",
)
EVIDENCE_DISTRIBUTION_COLUMNS: tuple[str, ...] = (
    "evidence_level",
    "n_global",
    "share_global",
    "n_FT",
    "share_FT",
    "n_REF",
    "share_REF",
    "n_EVAL",
    "share_EVAL",
)
LENGTH_DISTRIBUTION_COLUMNS: tuple[str, ...] = (
    "length_regime",
    "n_global_cores",
    "share_global",
    "n_FT_cores",
    "share_FT",
    "n_REF_cores",
    "share_REF",
    "n_EVAL_cores",
    "share_EVAL",
)
SOURCE_DISTRIBUTION_COLUMNS: tuple[str, ...] = (
    "source_db",
    "n_global",
    "share_global",
    "n_FT",
    "share_FT",
    "n_REF",
    "share_REF",
    "n_EVAL",
    "share_EVAL",
)
FAMILY_DIAGNOSTIC_COLUMNS: tuple[str, ...] = (
    "target_family",
    "role",
    "n_global",
    "share_global",
    "n_FT",
    "share_FT",
    "n_REF",
    "share_REF",
    "n_EVAL",
    "share_EVAL",
)
DIVERGENCE_COLUMNS: tuple[str, ...] = (
    "criterion",
    "role",
    "J_FT",
    "J_REF",
    "J_EVAL",
    "D_worst_partition",
    "log_base",
)


def _blank(value: Any) -> str:
    return "" if value is None else str(value).strip()


def format_fraction(numerator: int, denominator: int, digits: int = 12) -> str:
    if denominator <= 0:
        return ""
    return f"{(numerator / denominator):.{digits}f}"


def format_float(value: float, digits: int = 12) -> str:
    if math.isnan(value) or math.isinf(value):
        return str(value)
    return f"{value:.{digits}f}"


def parse_fraction(value: Any) -> Fraction:
    if isinstance(value, Fraction):
        return value
    return Fraction(str(value)).limit_denominator(10_000)


def assert_no_sequence_leak(text: str, *, label: str) -> None:
    if SEQ_LEAK_RE.search(text or ""):
        raise S7PartitionError(f"{label} must not contain biological sequence strings")


def assert_not_forbidden_output_path(path: Any) -> None:
    name = getattr(path, "name", str(path).rsplit("/", 1)[-1])
    if name in FORBIDDEN_OUTPUT_NAMES:
        raise S7PartitionError(f"S7B must not write forbidden artefact {name}")


def input_unmutated(
    rows: Sequence[Mapping[str, str]],
    snapshot: Sequence[Mapping[str, str]],
) -> bool:
    if len(rows) != len(snapshot):
        return False
    for current, original in zip(rows, snapshot):
        if dict(current) != dict(original):
            return False
    return True


def assignment_signature(assignment: Mapping[str, str]) -> str:
    """Stable signature of a complete or partial cluster assignment."""
    return "|".join(
        f"{cluster_id}:{assignment[cluster_id]}"
        for cluster_id in sorted(assignment)
    )


def resolve_partition_labels(partition_labels: Sequence[str] | None) -> tuple[str, ...]:
    """Report-order labels. Default is the frozen S7B FT/REF/EVAL order."""
    if partition_labels is None:
        return REPORT_PARTITION_ORDER
    if not partition_labels:
        raise S7PartitionError("partition_labels must be non-empty")
    return tuple(partition_labels)


def resolve_placement_labels(placement_labels: Sequence[str] | None) -> tuple[str, ...]:
    """Greedy/local-search label order. Default is alphabetical S7B labels."""
    if placement_labels is None:
        return PARTITION_LABELS
    if not placement_labels:
        raise S7PartitionError("placement_labels must be non-empty")
    return tuple(placement_labels)


def _log(value: float, base: float) -> float:
    if value <= 0.0:
        raise S7PartitionError("logarithm requires a positive argument")
    if base == 2.0:
        return math.log2(value)
    return math.log(value) / math.log(base)


def kl_divergence(
    p: Sequence[float],
    q: Sequence[float],
    *,
    log_base: float = JSD_LOG_BASE,
) -> float:
    if len(p) != len(q):
        raise S7PartitionError("KL support length mismatch")
    total = 0.0
    for p_i, q_i in zip(p, q):
        if p_i < 0.0 or q_i < 0.0:
            raise S7PartitionError("KL probabilities must be non-negative")
        if p_i == 0.0:
            continue
        if q_i == 0.0:
            return math.inf
        total += p_i * _log(p_i / q_i, log_base)
    return total


def js_divergence(
    p: Sequence[float],
    q: Sequence[float],
    *,
    log_base: float = JSD_LOG_BASE,
) -> float:
    """Jensen-Shannon divergence on a shared finite support.

    ``p`` and ``q`` are probability vectors over the same category order,
    including categories with probability 0. Logarithm base is ``log_base``
    (default 2, so JSD is in bits and bounded by 1). The mixture
    ``m = 0.5 (p + q)`` keeps JSD defined when a category is absent from
    exactly one of the two distributions.
    """
    if len(p) != len(q):
        raise S7PartitionError("JSD support length mismatch")
    mixture = [0.5 * (p_i + q_i) for p_i, q_i in zip(p, q)]
    return 0.5 * kl_divergence(p, mixture, log_base=log_base) + 0.5 * kl_divergence(
        q, mixture, log_base=log_base
    )


def empty_jsd(*, log_base: float = JSD_LOG_BASE) -> float:
    """Supremum of two-distribution JSD at the chosen log base."""
    return math.log(2.0) / math.log(log_base)


def counts_to_probs(
    counts: Mapping[str, int],
    support: Sequence[str],
) -> list[float] | None:
    total = sum(int(counts.get(category, 0)) for category in support)
    if total <= 0:
        return None
    return [int(counts.get(category, 0)) / total for category in support]


def resolve_objective_profile(profile: str | None) -> str:
    if profile is None:
        return DEFAULT_OBJECTIVE_PROFILE
    if profile not in {OBJECTIVE_PROFILE_JSD, OBJECTIVE_PROFILE_ABSDEV}:
        raise S7PartitionError(f"unknown objective profile {profile!r}")
    return profile


def max_abs_proportion_deviation(
    counts: Mapping[str, int],
    support: Sequence[str],
    global_probs: Sequence[float],
) -> float:
    """Maximum absolute category-proportion deviation on complete support.

    An absent category contributes its full global proportion. Relative
    percentage error is not used. Empty mass yields ``max(global_probs)``.
    """
    if len(global_probs) != len(support):
        raise S7PartitionError("absolute-deviation support length mismatch")
    probs = counts_to_probs(counts, support)
    if probs is None:
        return max(global_probs) if global_probs else 0.0
    return max(abs(p_i - q_i) for p_i, q_i in zip(probs, global_probs))


def max_abs_dev_from_vec(counts_vec: Any, global_p: Any) -> float:
    total = float(np.sum(counts_vec))
    if total <= 0.0:
        return float(np.max(global_p)) if getattr(global_p, "size", 0) else 0.0
    return float(np.max(np.abs(counts_vec / total - global_p)))


def worst_abs_deviation_category(
    counts: Mapping[str, int],
    support: Sequence[str],
    global_probs: Sequence[float],
) -> tuple[str, float]:
    """Return the first support category attaining the maximum |P-P_FT|."""
    if not support:
        return "", 0.0
    if len(global_probs) != len(support):
        raise S7PartitionError("absolute-deviation support length mismatch")
    probs = counts_to_probs(counts, support)
    if probs is None:
        idx = max(range(len(support)), key=lambda i: global_probs[i])
        return support[idx], float(global_probs[idx])
    idx = max(range(len(support)), key=lambda i: abs(probs[i] - global_probs[i]))
    return support[idx], abs(probs[idx] - global_probs[idx])


def scientific_prefix_from_components(
    *,
    d_target: float,
    d_evidence: float,
    d_length: float,
    d_source: float,
    m_target: float = 0.0,
    m_evidence: float = 0.0,
    m_length: float = 0.0,
    m_source: float = 0.0,
    profile: str | None = None,
) -> tuple[Any, ...]:
    """Build the scientific comparison prefix for the selected profile."""
    resolved = resolve_objective_profile(profile)
    d_values = (d_target, d_evidence, d_length, d_source)
    d_lex = tuple(sorted(d_values, reverse=True))
    o3 = d_target + d_evidence + d_length + d_source
    if resolved == OBJECTIVE_PROFILE_ABSDEV:
        m_values = (m_target, m_evidence, m_length, m_source)
        m_lex = tuple(sorted(m_values, reverse=True))
        r3 = m_target + m_evidence + m_length + m_source
        return (max(m_lex), m_lex, r3, d_lex, o3)
    return (max(d_lex), d_lex, o3)


def js_against_global(
    counts: Mapping[str, int],
    global_probs: Sequence[float],
    support: Sequence[str],
    *,
    log_base: float = JSD_LOG_BASE,
) -> float:
    probs = counts_to_probs(counts, support)
    if probs is None:
        return empty_jsd(log_base=log_base)
    return js_divergence(probs, global_probs, log_base=log_base)


@dataclass(frozen=True)
class QuotaTriple:
    n_FT: int
    n_REF: int
    n_EVAL: int
    sse: Fraction

    @property
    def as_tuple(self) -> tuple[int, int, int]:
        return (self.n_FT, self.n_REF, self.n_EVAL)

    def remaining(self) -> dict[str, int]:
        return {"FT": self.n_FT, "REF": self.n_REF, "EVAL": self.n_EVAL}

    def as_dict(self) -> dict[str, int]:
        return dict(self.remaining())


def derive_integer_quotas(
    n_clusters: int,
    fractions: Mapping[str, Any] | None = None,
) -> list[QuotaTriple]:
    """Return all tied-optimal integer (FT, REF, EVAL) quotas.

    Minimises ``sum_p (n_p / N - desired_p)^2`` over non-negative integers
    with ``n_FT + n_REF + n_EVAL = N``. Does not break REF/EVAL ties by
    label order.
    """
    if n_clusters < 0:
        raise S7PartitionError("n_clusters must be non-negative")
    desired = dict(DEFAULT_FRACTIONS)
    if fractions:
        for label in REPORT_PARTITION_ORDER:
            if label not in fractions:
                raise S7PartitionError(f"missing desired fraction for {label}")
            desired[label] = parse_fraction(fractions[label])
    if sum(desired.values()) != 1:
        raise S7PartitionError("desired partition fractions must sum to 1")
    best_sse: Fraction | None = None
    winners: list[QuotaTriple] = []
    for n_ft in range(n_clusters + 1):
        for n_ref in range(n_clusters - n_ft + 1):
            n_eval = n_clusters - n_ft - n_ref
            sse = (
                (Fraction(n_ft, n_clusters) - desired["FT"]) ** 2
                + (Fraction(n_ref, n_clusters) - desired["REF"]) ** 2
                + (Fraction(n_eval, n_clusters) - desired["EVAL"]) ** 2
            )
            candidate = QuotaTriple(n_ft, n_ref, n_eval, sse)
            if best_sse is None or sse < best_sse:
                best_sse = sse
                winners = [candidate]
            elif sse == best_sse:
                winners.append(candidate)
    winners.sort(key=lambda item: item.as_tuple)
    return winners


@dataclass
class ClusterFeature:
    cluster_id: str
    n_identities: int
    n_cores: int
    n_distinct_targets: int
    n_distinct_sources: int
    target_counts: dict[str, int]
    evidence_counts: dict[str, int]
    source_counts: dict[str, int]
    length_counts: dict[str, int]
    family_counts: dict[str, int]
    multi_target: bool
    multi_source: bool
    target_vec: Any = None
    evidence_vec: Any = None
    source_vec: Any = None
    length_vec: Any = None
    family_vec: Any = None

    def preview_row(self, partition: str) -> dict[str, str]:
        return {
            "cluster_id": self.cluster_id,
            "proposed_partition": partition,
            "cluster_identity_count": str(self.n_identities),
            "cluster_core_count": str(self.n_cores),
            "n_distinct_canonical_targets": str(self.n_distinct_targets),
            "n_distinct_primary_sources": str(self.n_distinct_sources),
            "n_short_cores": str(int(self.length_counts.get("short", 0))),
            "n_long_cores": str(int(self.length_counts.get("long", 0))),
            "n_e2": str(int(self.evidence_counts.get("E2", 0))),
            "n_e3": str(int(self.evidence_counts.get("E3", 0))),
            "n_e4": str(int(self.evidence_counts.get("E4", 0))),
            "multi_target_cluster": "true" if self.multi_target else "false",
            "multi_source_cluster": "true" if self.multi_source else "false",
        }

    def assignment_row(self, partition: str) -> dict[str, str]:
        row = self.preview_row(partition)
        row["partition"] = row.pop("proposed_partition")
        return row


@dataclass
class FeatureSpace:
    targets: tuple[str, ...]
    evidence: tuple[str, ...]
    sources: tuple[str, ...]
    length_regimes: tuple[str, ...]
    families: tuple[str, ...]
    global_target: dict[str, int]
    global_evidence: dict[str, int]
    global_source: dict[str, int]
    global_length: dict[str, int]
    global_family: dict[str, int]
    n_identities: int
    n_cores: int
    n_clusters: int
    log_base: float = JSD_LOG_BASE
    target_probs: list[float] = field(init=False)
    evidence_probs: list[float] = field(init=False)
    source_probs: list[float] = field(init=False)
    length_probs: list[float] = field(init=False)
    family_probs: list[float] = field(init=False)

    def __post_init__(self) -> None:
        target_probs = counts_to_probs(self.global_target, self.targets)
        evidence_probs = counts_to_probs(self.global_evidence, self.evidence)
        source_probs = counts_to_probs(self.global_source, self.sources)
        length_probs = counts_to_probs(self.global_length, self.length_regimes)
        family_probs = counts_to_probs(self.global_family, self.families)
        if (
            target_probs is None
            or evidence_probs is None
            or source_probs is None
            or length_probs is None
            or family_probs is None
        ):
            raise S7PartitionError("global feature distributions must have positive mass")
        self.target_probs = target_probs
        self.evidence_probs = evidence_probs
        self.source_probs = source_probs
        self.length_probs = length_probs
        self.family_probs = family_probs
        self.target_p = np.asarray(target_probs, dtype=float)
        self.evidence_p = np.asarray(evidence_probs, dtype=float)
        self.source_p = np.asarray(source_probs, dtype=float)
        self.length_p = np.asarray(length_probs, dtype=float)
        self.family_p = np.asarray(family_probs, dtype=float)


@dataclass
class PartitionCounts:
    clusters: set[str] = field(default_factory=set)
    n_identities: int = 0
    n_cores: int = 0
    target: Counter[str] = field(default_factory=Counter)
    evidence: Counter[str] = field(default_factory=Counter)
    source: Counter[str] = field(default_factory=Counter)
    length: Counter[str] = field(default_factory=Counter)
    family: Counter[str] = field(default_factory=Counter)
    n_multi_target_clusters: int = 0
    n_multi_source_clusters: int = 0
    target_vec: Any = None
    evidence_vec: Any = None
    source_vec: Any = None
    length_vec: Any = None
    family_vec: Any = None

    def add(self, feature: ClusterFeature) -> None:
        if feature.cluster_id in self.clusters:
            raise S7PartitionError(f"cluster {feature.cluster_id} already assigned")
        self.clusters.add(feature.cluster_id)
        self.n_identities += feature.n_identities
        self.n_cores += feature.n_cores
        self.target.update(feature.target_counts)
        self.evidence.update(feature.evidence_counts)
        self.source.update(feature.source_counts)
        self.length.update(feature.length_counts)
        self.family.update(feature.family_counts)
        self.n_multi_target_clusters += int(feature.multi_target)
        self.n_multi_source_clusters += int(feature.multi_source)
        if feature.target_vec is not None and self.target_vec is not None:
            self.target_vec += feature.target_vec
            self.evidence_vec += feature.evidence_vec
            self.source_vec += feature.source_vec
            self.length_vec += feature.length_vec
            self.family_vec += feature.family_vec

    def remove(self, feature: ClusterFeature) -> None:
        if feature.cluster_id not in self.clusters:
            raise S7PartitionError(f"cluster {feature.cluster_id} is not in this partition")
        self.clusters.remove(feature.cluster_id)
        self.n_identities -= feature.n_identities
        self.n_cores -= feature.n_cores
        self.target.subtract(feature.target_counts)
        self.evidence.subtract(feature.evidence_counts)
        self.source.subtract(feature.source_counts)
        self.length.subtract(feature.length_counts)
        self.family.subtract(feature.family_counts)
        self.n_multi_target_clusters -= int(feature.multi_target)
        self.n_multi_source_clusters -= int(feature.multi_source)
        if feature.target_vec is not None and self.target_vec is not None:
            self.target_vec -= feature.target_vec
            self.evidence_vec -= feature.evidence_vec
            self.source_vec -= feature.source_vec
            self.length_vec -= feature.length_vec
            self.family_vec -= feature.family_vec

    def n_clusters(self) -> int:
        return len(self.clusters)


@dataclass(frozen=True)
class ObjectiveScore:
    d_target: float
    d_evidence: float
    d_length: float
    d_source: float
    j_target: dict[str, float]
    j_evidence: dict[str, float]
    j_length: dict[str, float]
    j_source: dict[str, float]
    log_base: float = JSD_LOG_BASE
    a_target: dict[str, float] = field(default_factory=dict)
    a_evidence: dict[str, float] = field(default_factory=dict)
    a_length: dict[str, float] = field(default_factory=dict)
    a_source: dict[str, float] = field(default_factory=dict)
    m_target: float = 0.0
    m_evidence: float = 0.0
    m_length: float = 0.0
    m_source: float = 0.0
    profile: str = DEFAULT_OBJECTIVE_PROFILE

    @property
    def o1(self) -> float:
        return max(self.d_target, self.d_evidence, self.d_length, self.d_source)

    @property
    def lex_vector(self) -> tuple[float, float, float, float]:
        return tuple(
            sorted(
                (self.d_target, self.d_evidence, self.d_length, self.d_source),
                reverse=True,
            )
        )

    @property
    def o3(self) -> float:
        return self.d_target + self.d_evidence + self.d_length + self.d_source

    @property
    def r1(self) -> float:
        return max(self.m_target, self.m_evidence, self.m_length, self.m_source)

    @property
    def m_lex_vector(self) -> tuple[float, float, float, float]:
        return tuple(
            sorted(
                (self.m_target, self.m_evidence, self.m_length, self.m_source),
                reverse=True,
            )
        )

    @property
    def r3(self) -> float:
        return self.m_target + self.m_evidence + self.m_length + self.m_source

    @property
    def comparison_tuple_fields(self) -> tuple[str, ...]:
        if self.profile == OBJECTIVE_PROFILE_ABSDEV:
            return ABSDEV_COMPARISON_TUPLE_FIELDS
        return COMPARISON_TUPLE_FIELDS

    def scientific_prefix(self) -> tuple[Any, ...]:
        """Scientific comparison prefix for the selected profile.

        Frozen S7B default (``jsd_minimax``): O1, descending D vector, O3.
        S7C absolute-deviation profile: R1, descending M vector, R3,
        then JSD descending D vector and D-sum as later tie-breaks.
        """
        return scientific_prefix_from_components(
            d_target=self.d_target,
            d_evidence=self.d_evidence,
            d_length=self.d_length,
            d_source=self.d_source,
            m_target=self.m_target,
            m_evidence=self.m_evidence,
            m_length=self.m_length,
            m_source=self.m_source,
            profile=self.profile,
        )

    def comparison_tuple(self, assignment: Mapping[str, str]) -> tuple[Any, ...]:
        """Exact optimisation key, in documented order.

        Frozen S7B ``jsd_minimax``:

        1. O1 = max of the four worst-partition primary divergences.
        2. The four D values sorted descending (lexicographic).
        3. O3 = sum of the four D values.
        4. Stable assignment signature of sorted ``cluster_id:label``.

        S7C ``max_abs_proportion_deviation``:

        1. R1 = max of the four worst-subset maximum absolute proportion
           deviations M_c.
        2. The four M values sorted descending (lexicographic).
        3. R3 = sum of the four M values.
        4. The four D (JSD) values sorted descending.
        5. Sum of the four D values.
        6. Stable assignment signature.
        """
        return (*self.scientific_prefix(), assignment_signature(assignment))

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "log_base": self.log_base,
            "J_target": dict(self.j_target),
            "J_evidence": dict(self.j_evidence),
            "J_length": dict(self.j_length),
            "J_source": dict(self.j_source),
            "D_target": self.d_target,
            "D_evidence": self.d_evidence,
            "D_length": self.d_length,
            "D_source": self.d_source,
            "O1": self.o1,
            "lexicographic_descending_D_vector": list(self.lex_vector),
            "O3": self.o3,
            "A_target": dict(self.a_target),
            "A_evidence": dict(self.a_evidence),
            "A_length": dict(self.a_length),
            "A_source": dict(self.a_source),
            "M_target": self.m_target,
            "M_evidence": self.m_evidence,
            "M_length": self.m_length,
            "M_source": self.m_source,
            "R1": self.r1,
            "lexicographic_descending_M_vector": list(self.m_lex_vector),
            "R3": self.r3,
            "arbitrary_manually_chosen_criterion_weights": None,
            "target_family_in_primary_objective": False,
            "comparison_tuple_fields": list(self.comparison_tuple_fields),
        }


def _counts_to_vec(counts: Mapping[str, int], support: Sequence[str]) -> Any:
    vec = np.zeros(len(support), dtype=float)
    index = {category: i for i, category in enumerate(support)}
    for category, value in counts.items():
        vec[index[category]] = float(value)
    return vec


def _kl_vec(p: Any, q: Any, log_base: float) -> float:
    mask = p > 0.0
    if not np.any(mask):
        return 0.0
    ratio = p[mask] / q[mask]
    if log_base == 2.0:
        return float(np.sum(p[mask] * np.log2(ratio)))
    return float(np.sum(p[mask] * (np.log(ratio) / math.log(log_base))))


def js_from_vec(counts_vec: Any, global_p: Any, *, log_base: float = JSD_LOG_BASE) -> float:
    total = float(np.sum(counts_vec))
    if total <= 0.0:
        return empty_jsd(log_base=log_base)
    n = int(counts_vec.shape[0])
    if n <= 32:
        acc = 0.0
        inv_total = 1.0 / total
        for i in range(n):
            p_i = float(counts_vec[i]) * inv_total
            q_i = float(global_p[i])
            mixture = 0.5 * (p_i + q_i)
            if p_i > 0.0:
                acc += p_i * _log(p_i / mixture, log_base)
            if q_i > 0.0:
                acc += q_i * _log(q_i / mixture, log_base)
        return 0.5 * acc
    probs = counts_vec / total
    mixture = 0.5 * (probs + global_p)
    return 0.5 * _kl_vec(probs, mixture, log_base) + 0.5 * _kl_vec(global_p, mixture, log_base)


def js_divergence_rows(
    counts: Any,
    global_p: Any,
    *,
    log_base: float = JSD_LOG_BASE,
) -> Any:
    """Row-wise JSD used only to reject clearly worse swaps.

    Each row is a category-count vector on ``global_p``'s support. The
    values match ``js_from_vec`` up to summation order (well inside
    ``_JSD_SCREEN_EPS``). Accept/reject decisions do not use this value
    unless it proves the swap is strictly worse than the current exact
    objective by more than that margin.
    """
    matrix = np.asarray(counts, dtype=float)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    totals = matrix.sum(axis=1)
    out = np.empty(matrix.shape[0], dtype=float)
    empty = empty_jsd(log_base=log_base)
    dead = totals <= 0.0
    out[dead] = empty
    live = ~dead
    if not np.any(live):
        return out
    probs = np.zeros_like(matrix)
    probs[live] = matrix[live] / totals[live, None]
    mixture = 0.5 * (probs + np.asarray(global_p, dtype=float))

    def _kl_rows(p: Any, q: Any) -> Any:
        mask = p > 0.0
        contrib = np.zeros_like(p)
        if log_base == 2.0:
            contrib[mask] = p[mask] * np.log2(p[mask] / q[mask])
        else:
            contrib[mask] = p[mask] * (np.log(p[mask] / q[mask]) / math.log(log_base))
        return contrib.sum(axis=1)

    out[live] = 0.5 * _kl_rows(probs, mixture)[live] + 0.5 * _kl_rows(
        np.broadcast_to(np.asarray(global_p, dtype=float), probs.shape), mixture
    )[live]
    return out


def _screen_rejects_swap(
    batch_prefix: tuple[Any, ...],
    current_prefix: tuple[Any, ...],
    *,
    eps: float = _JSD_SCREEN_EPS,
) -> bool:
    """True only when batch O1 is strictly worse than the exact O1 by ``eps``.

    The comparison tuple is ordered by O1 first. A one-ulp decrease in O1
    is an improvement even when the later lexicographic terms get worse, so
    a within-margin O1 tie is never rejected here. Lexicographic terms,
    the divergence sum, and the assignment signature stay on the exact path.
    """
    return float(batch_prefix[0]) > float(current_prefix[0]) + eps


def format_search_prefix(prefix: tuple[Any, ...]) -> str:
    """Compact O1 / descending-D / O3 text for progress logs."""
    lex = ",".join(f"{float(value):.6f}" for value in prefix[1])
    return f"({float(prefix[0]):.6f},[{lex}],{float(prefix[2]):.6f})"


def score_partition_states(
    states: Mapping[str, PartitionCounts],
    space: FeatureSpace,
    *,
    include_family: bool = False,
    partition_labels: Sequence[str] | None = None,
    objective_profile: str | None = None,
) -> ObjectiveScore:
    """Score a partial or complete assignment against the global corpus.

    Each partition is compared to the **full stored global** distribution
    for that criterion, not to the mixture of currently assigned clusters.
    A partition with zero mass on the criterion grain receives JSD equal
    to the supremum at the configured log base (1 bit when log2), and
    maximum absolute proportion deviation equal to the largest global
    category share. The four primary criteria are target, evidence, length
    regime, and source. ``target_family`` is ignored unless
    ``include_family`` is requested for a secondary diagnostic, and even
    then it is not folded into O1/O2/O3 or R1/R3.

    Default ``partition_labels`` is the frozen S7B FT/REF/EVAL report
    order. Default ``objective_profile`` is frozen S7B ``jsd_minimax``.
    Absolute-deviation diagnostics are always computed; they enter the
    comparison tuple only under ``max_abs_proportion_deviation``.
    """
    del include_family  # family is never part of the primary score object
    labels = resolve_partition_labels(partition_labels)
    profile = resolve_objective_profile(objective_profile)
    j_target = {}
    j_evidence = {}
    j_length = {}
    j_source = {}
    a_target = {}
    a_evidence = {}
    a_length = {}
    a_source = {}
    for label in labels:
        state = states[label]
        if state.target_vec is not None:
            j_target[label] = js_from_vec(state.target_vec, space.target_p, log_base=space.log_base)
            j_evidence[label] = js_from_vec(
                state.evidence_vec, space.evidence_p, log_base=space.log_base
            )
            j_length[label] = js_from_vec(state.length_vec, space.length_p, log_base=space.log_base)
            j_source[label] = js_from_vec(state.source_vec, space.source_p, log_base=space.log_base)
            a_target[label] = max_abs_dev_from_vec(state.target_vec, space.target_p)
            a_evidence[label] = max_abs_dev_from_vec(state.evidence_vec, space.evidence_p)
            a_length[label] = max_abs_dev_from_vec(state.length_vec, space.length_p)
            a_source[label] = max_abs_dev_from_vec(state.source_vec, space.source_p)
        else:
            j_target[label] = js_against_global(
                state.target, space.target_probs, space.targets, log_base=space.log_base
            )
            j_evidence[label] = js_against_global(
                state.evidence, space.evidence_probs, space.evidence, log_base=space.log_base
            )
            j_length[label] = js_against_global(
                state.length, space.length_probs, space.length_regimes, log_base=space.log_base
            )
            j_source[label] = js_against_global(
                state.source, space.source_probs, space.sources, log_base=space.log_base
            )
            a_target[label] = max_abs_proportion_deviation(
                state.target, space.targets, space.target_probs
            )
            a_evidence[label] = max_abs_proportion_deviation(
                state.evidence, space.evidence, space.evidence_probs
            )
            a_length[label] = max_abs_proportion_deviation(
                state.length, space.length_regimes, space.length_probs
            )
            a_source[label] = max_abs_proportion_deviation(
                state.source, space.sources, space.source_probs
            )
    return ObjectiveScore(
        d_target=max(j_target.values()),
        d_evidence=max(j_evidence.values()),
        d_length=max(j_length.values()),
        d_source=max(j_source.values()),
        j_target=j_target,
        j_evidence=j_evidence,
        j_length=j_length,
        j_source=j_source,
        log_base=space.log_base,
        a_target=a_target,
        a_evidence=a_evidence,
        a_length=a_length,
        a_source=a_source,
        m_target=max(a_target.values()),
        m_evidence=max(a_evidence.values()),
        m_length=max(a_length.values()),
        m_source=max(a_source.values()),
        profile=profile,
    )


def family_jsd_by_partition(
    states: Mapping[str, PartitionCounts],
    space: FeatureSpace,
    *,
    partition_labels: Sequence[str] | None = None,
) -> dict[str, float]:
    """Secondary diagnostic only — not used by the optimiser."""
    labels = resolve_partition_labels(partition_labels)
    return {
        label: js_against_global(
            states[label].family, space.family_probs, space.families, log_base=space.log_base
        )
        for label in labels
    }


def load_frozen_s6_gmm(payload: Mapping[str, Any]) -> dict[str, Any]:
    gmm = payload.get("gmm_2")
    if not isinstance(gmm, Mapping):
        raise S7PartitionError("frozen S6 bimodality.json is missing gmm_2")
    means = [float(v) for v in gmm["means"]]
    variances = [float(v) for v in gmm["variances"]]
    weights = [float(v) for v in gmm["weights"]]
    if len(means) != 2 or len(variances) != 2 or len(weights) != 2:
        raise S7PartitionError("frozen S6 GMM must have exactly two components")
    if means[0] > means[1]:
        raise S7PartitionError("frozen S6 GMM means must be stored in ascending order")
    return {
        "n_components": 2,
        "means": means,
        "variances": variances,
        "weights": weights,
        "assignment_method": GMM_POSTERIOR_ASSIGNMENT_METHOD,
        "source_regime_method": str(payload.get("source_regime_method") or ""),
    }


def assign_length_regimes(
    corpus_rows: Sequence[Mapping[str, str]],
    gmm2: Mapping[str, Any],
) -> dict[str, str]:
    """Assign each distinct sequence_core to frozen S6 short/long regimes.

    Uses stored ``sequence_length_core`` where present (S6 ``length_of``),
    then ``gmm_posterior_assignment``. Component 0 is short; ties go short.
    Sequence strings are not stored in the returned map values.
    """
    unique: dict[str, Mapping[str, str]] = {}
    for row in corpus_rows:
        core = _blank(row.get("sequence_core"))
        if not core:
            raise S7PartitionError("sequence_core is required for length-regime assignment")
        unique.setdefault(core, row)
    ordered_cores = sorted(unique)
    lengths = [length_of(unique[core], "sequence_core") for core in ordered_cores]
    assignments = gmm_posterior_assignment(lengths, gmm2)
    regimes: dict[str, str] = {}
    for core, assign in zip(ordered_cores, assignments):
        regimes[core] = LENGTH_REGIME_LABELS[int(assign)]
    return regimes


def verify_frozen_identities(
    corpus_rows: Sequence[Mapping[str, str]],
    expected: Mapping[str, int] | None = None,
) -> dict[str, int]:
    identities = [_blank(row.get("scientific_identity_id")) for row in corpus_rows]
    if any(not item for item in identities):
        raise S7PartitionError("every identity must have scientific_identity_id")
    if len(identities) != len(set(identities)):
        raise S7PartitionError("scientific_identity_id values are not unique")
    if any(not _blank(row.get("cluster_id")) for row in corpus_rows):
        raise S7PartitionError("every identity must have a retained S5 cluster_id")
    core_clusters: dict[str, set[str]] = defaultdict(set)
    for row in corpus_rows:
        core_clusters[_blank(row.get("sequence_core"))].add(_blank(row.get("cluster_id")))
    if any(not core for core in core_clusters):
        raise S7PartitionError("sequence_core is required")
    multi = {core: sorted(clusters) for core, clusters in core_clusters.items() if len(clusters) > 1}
    if multi:
        raise S7PartitionError("a sequence_core maps to more than one cluster")
    if any((row.get("partition") or "").strip() for row in corpus_rows):
        raise S7PartitionError("input partition values must all be blank")
    evidence = Counter(_blank(row.get("evidence_level")) for row in corpus_rows)
    if evidence.get("E5", 0) != 0:
        raise S7PartitionError("S7B input must not contain E5 identities")
    unexpected_evidence = sorted(level for level in evidence if level not in EVIDENCE_LEVELS)
    if unexpected_evidence:
        raise S7PartitionError(f"unexpected evidence levels: {unexpected_evidence}")
    types = {_blank(row.get("target_type")) for row in corpus_rows}
    if types != {"protein"}:
        raise S7PartitionError(f"input target types must all be protein, got {sorted(types)}")
    observed = {
        "n_scientific_identities": len(corpus_rows),
        "n_distinct_sequence_core": len(core_clusters),
        "n_final_clusters": len({_blank(row.get("cluster_id")) for row in corpus_rows}),
        "n_canonical_targets": len(
            {_blank(row.get("canonical_target_name")) for row in corpus_rows}
        ),
    }
    if expected:
        for key, wanted in expected.items():
            if observed.get(key) != wanted:
                raise S7PartitionError(f"{key}: expected {wanted}, got {observed.get(key)}")
    return observed


def build_cluster_features(
    corpus_rows: Sequence[Mapping[str, str]],
    core_regimes: Mapping[str, str],
) -> tuple[dict[str, ClusterFeature], FeatureSpace]:
    """Build sequence-free cluster feature vectors.

    Grains:
    - canonical target: identity
    - evidence: identity
    - source: identity-grain ``source_db`` (not expanded contributing_sources)
    - length regime: distinct sequence_core
    - target_family: identity, diagnostic only
    """
    verify_frozen_identities(corpus_rows)
    grouped: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in corpus_rows:
        grouped[_blank(row.get("cluster_id"))].append(row)

    features: dict[str, ClusterFeature] = {}
    global_target: Counter[str] = Counter()
    global_evidence: Counter[str] = Counter()
    global_source: Counter[str] = Counter()
    global_length: Counter[str] = Counter()
    global_family: Counter[str] = Counter()

    for cluster_id, members in grouped.items():
        target_counts: Counter[str] = Counter()
        evidence_counts: Counter[str] = Counter()
        source_counts: Counter[str] = Counter()
        family_counts: Counter[str] = Counter()
        cores: dict[str, str] = {}
        for row in members:
            target = _blank(row.get("canonical_target_name"))
            evidence = _blank(row.get("evidence_level"))
            source = _blank(row.get("source_db")) or "(blank)"
            family = _blank(row.get("target_family")) or UNKNOWN_FAMILY
            core = _blank(row.get("sequence_core"))
            if not target:
                raise S7PartitionError(f"{cluster_id} is missing canonical_target_name")
            if evidence not in EVIDENCE_LEVELS:
                raise S7PartitionError(f"{cluster_id} has invalid evidence_level {evidence!r}")
            if core not in core_regimes:
                raise S7PartitionError("length regime missing for a retained sequence_core")
            target_counts[target] += 1
            evidence_counts[evidence] += 1
            source_counts[source] += 1
            family_counts[family] += 1
            cores[core] = core_regimes[core]
        length_counts: Counter[str] = Counter(cores.values())
        unexpected_regimes = sorted(set(length_counts) - set(LENGTH_REGIME_LABELS))
        if unexpected_regimes:
            raise S7PartitionError(f"unexpected length regimes: {unexpected_regimes}")
        feature = ClusterFeature(
            cluster_id=cluster_id,
            n_identities=len(members),
            n_cores=len(cores),
            n_distinct_targets=len(target_counts),
            n_distinct_sources=len(source_counts),
            target_counts=dict(target_counts),
            evidence_counts=dict(evidence_counts),
            source_counts=dict(source_counts),
            length_counts=dict(length_counts),
            family_counts=dict(family_counts),
            multi_target=len(target_counts) > 1,
            multi_source=len(source_counts) > 1,
        )
        features[cluster_id] = feature
        global_target.update(target_counts)
        global_evidence.update(evidence_counts)
        global_source.update(source_counts)
        global_length.update(length_counts)
        global_family.update(family_counts)

    space = FeatureSpace(
        targets=tuple(sorted(global_target)),
        evidence=tuple(level for level in EVIDENCE_LEVELS if global_evidence.get(level, 0)),
        sources=tuple(sorted(global_source)),
        length_regimes=LENGTH_REGIME_LABELS,
        families=tuple(sorted(global_family)),
        global_target=dict(global_target),
        global_evidence=dict(global_evidence),
        global_source=dict(global_source),
        global_length=dict(global_length),
        global_family=dict(global_family),
        n_identities=len(corpus_rows),
        n_cores=sum(global_length.values()),
        n_clusters=len(features),
    )
    for feature in features.values():
        feature.target_vec = _counts_to_vec(feature.target_counts, space.targets)
        feature.evidence_vec = _counts_to_vec(feature.evidence_counts, space.evidence)
        feature.source_vec = _counts_to_vec(feature.source_counts, space.sources)
        feature.length_vec = _counts_to_vec(feature.length_counts, space.length_regimes)
        feature.family_vec = _counts_to_vec(feature.family_counts, space.families)
        feature.target_nz = tuple(int(i) for i in np.nonzero(feature.target_vec)[0])
        feature.evidence_nz = tuple(int(i) for i in np.nonzero(feature.evidence_vec)[0])
        feature.source_nz = tuple(int(i) for i in np.nonzero(feature.source_vec)[0])
        feature.length_nz = tuple(int(i) for i in np.nonzero(feature.length_vec)[0])
    return features, space


def cluster_processing_order(features: Mapping[str, ClusterFeature]) -> list[str]:
    """Harder/larger clusters first, then stable cluster_id."""
    return sorted(
        features,
        key=lambda cluster_id: (
            -features[cluster_id].n_identities,
            -features[cluster_id].n_distinct_targets,
            -features[cluster_id].n_cores,
            cluster_id,
        ),
    )


def _empty_states(
    space: FeatureSpace | None = None,
    labels: Sequence[str] | None = None,
) -> dict[str, PartitionCounts]:
    order = resolve_partition_labels(labels)
    states = {label: PartitionCounts() for label in order}
    if space is not None:
        for state in states.values():
            state.target_vec = np.zeros(len(space.targets), dtype=float)
            state.evidence_vec = np.zeros(len(space.evidence), dtype=float)
            state.source_vec = np.zeros(len(space.sources), dtype=float)
            state.length_vec = np.zeros(len(space.length_regimes), dtype=float)
            state.family_vec = np.zeros(len(space.families), dtype=float)
    return states


def states_from_assignment(
    assignment: Mapping[str, str],
    features: Mapping[str, ClusterFeature],
    space: FeatureSpace | None = None,
    *,
    partition_labels: Sequence[str] | None = None,
) -> dict[str, PartitionCounts]:
    states = _empty_states(space, labels=partition_labels)
    for cluster_id, label in assignment.items():
        if label not in states:
            raise S7PartitionError(f"unknown partition label {label!r}")
        states[label].add(features[cluster_id])
    return states


def greedy_assign(
    features: Mapping[str, ClusterFeature],
    space: FeatureSpace,
    quotas: Any,
    *,
    partition_labels: Sequence[str] | None = None,
    placement_labels: Sequence[str] | None = None,
    objective_profile: str | None = None,
) -> dict[str, str]:
    """Deterministic greedy placement with the same primary objective.

    Partial-state scoring uses currently assigned clusters only (including
    the tentative placement) compared with the fixed global corpus
    distributions. Empty partitions receive supremum JSD (and maximum
    global category share under the absolute-deviation profile). Final
    exact scientific ties use alphabetical partition-label order
    (EVAL < FT < REF for the default S7B labels). Default
    ``objective_profile`` is frozen S7B ``jsd_minimax``.
    """
    remaining = quotas.remaining()
    report_labels = resolve_partition_labels(partition_labels)
    place_labels = resolve_placement_labels(placement_labels)
    profile = resolve_objective_profile(objective_profile)
    states = _empty_states(space, labels=report_labels)
    assignment: dict[str, str] = {}
    for cluster_id in cluster_processing_order(features):
        feature = features[cluster_id]
        feasible = [label for label in place_labels if remaining.get(label, 0) > 0]
        if not feasible:
            raise S7PartitionError("greedy placement exhausted partition capacity early")
        best_label: str | None = None
        best_key: tuple[Any, ...] | None = None
        for label in feasible:
            states[label].add(feature)
            score = score_partition_states(
                states,
                space,
                partition_labels=report_labels,
                objective_profile=profile,
            )
            key = (*score.scientific_prefix(), label)
            states[label].remove(feature)
            if best_key is None or key < best_key:
                best_key = key
                best_label = label
        if best_label is None:
            raise S7PartitionError("greedy placement failed to select a partition")
        states[best_label].add(feature)
        assignment[cluster_id] = best_label
        remaining[best_label] -= 1
    if any(value != 0 for value in remaining.values()):
        raise S7PartitionError("greedy placement did not exhaust exact cluster quotas")
    return assignment


def _swap_clusters(
    states: Mapping[str, PartitionCounts],
    features: Mapping[str, ClusterFeature],
    cluster_a: str,
    label_a: str,
    cluster_b: str,
    label_b: str,
) -> None:
    states[label_a].remove(features[cluster_a])
    states[label_b].remove(features[cluster_b])
    states[label_a].add(features[cluster_b])
    states[label_b].add(features[cluster_a])


def pairwise_local_search(
    assignment: Mapping[str, str],
    features: Mapping[str, ClusterFeature],
    space: FeatureSpace,
    *,
    max_accepted_swaps: int = 1_000_000,
    max_evals: int | None = None,
    max_passes: int = 10_000,
    max_seconds: float | None = None,
    progress: bool = False,
    progress_every: int = 5_000,
    evaluator: str = "screened",
    partition_labels: Sequence[str] | None = None,
    placement_labels: Sequence[str] | None = None,
    log_prefix: str = "S7B",
    objective_profile: str | None = None,
    search_stats: dict[str, Any] | None = None,
) -> tuple[dict[str, str], int, int, bool]:
    """Deterministic first-improvement pairwise swap search.

    Candidate order is alphabetical partition-pair, then sorted cluster_id
    pairs. A swap is accepted only when the comparison tuple strictly
    improves. After an accepted swap the scan continues through the
    remaining stable candidates, skipping cluster IDs that have left the
    snapshotted partition membership. Cluster counts per partition are
    preserved. Search stops after one complete pass with no improving swap.
    ``max_passes`` is a safety cap only; hitting it is reported and is not
    the intended scientific termination.

    The hot path keeps per-partition category-count vectors and only
    updates membership after an accepted swap. For the frozen
    ``jsd_minimax`` profile, candidate swaps are scored in deterministic
    chunks. A chunked Jensen-Shannon screen may skip a swap only when it
    is strictly worse than the current exact objective by more than
    ``_JSD_SCREEN_EPS``. Every other candidate, and every accepted swap,
    is confirmed with the original ``js_from_vec`` prefix. The
    absolute-deviation profile always uses that exact scalar path.
    ``evaluator="scalar"`` forces the original per-swap path.

    ``max_evals`` and ``max_seconds`` are fail-closed diagnostic bounds:
    exceeding either raises ``S7PartitionError`` and must not be treated
    as an accepted partition. ``max_passes`` remains a soft safety cap.
    Default labels are the frozen S7B FT/REF/EVAL set; ``log_prefix``
    defaults to ``S7B``.
    """
    report_labels = resolve_partition_labels(partition_labels)
    place_labels = resolve_placement_labels(placement_labels)
    profile = resolve_objective_profile(objective_profile)
    current = dict(assignment)
    members: dict[str, set[str]] = {label: set() for label in report_labels}
    target = {label: np.zeros(len(space.targets), dtype=float) for label in report_labels}
    evidence = {label: np.zeros(len(space.evidence), dtype=float) for label in report_labels}
    source = {label: np.zeros(len(space.sources), dtype=float) for label in report_labels}
    length = {label: np.zeros(len(space.length_regimes), dtype=float) for label in report_labels}
    n_id = {label: 0 for label in report_labels}
    n_core = {label: 0 for label in report_labels}
    for cluster_id, label in current.items():
        feature = features[cluster_id]
        members[label].add(cluster_id)
        n_id[label] += feature.n_identities
        n_core[label] += feature.n_cores
        for index in feature.target_nz:
            target[label][index] += feature.target_vec[index]
        for index in feature.evidence_nz:
            evidence[label][index] += feature.evidence_vec[index]
        for index in feature.source_nz:
            source[label][index] += feature.source_vec[index]
        for index in feature.length_nz:
            length[label][index] += feature.length_vec[index]

    global_target = space.target_p
    global_evidence = space.evidence_p
    global_source = space.source_p
    global_length = space.length_p
    log_base = space.log_base

    def _js(counts: Any, global_p: Any, total: int) -> float:
        del total
        return js_from_vec(counts, global_p, log_base=log_base)

    def _move(feature: ClusterFeature, src: str, dst: str) -> None:
        n_id[src] -= feature.n_identities
        n_id[dst] += feature.n_identities
        n_core[src] -= feature.n_cores
        n_core[dst] += feature.n_cores
        t_src = target[src]
        t_dst = target[dst]
        for index in feature.target_nz:
            value = feature.target_vec[index]
            t_src[index] -= value
            t_dst[index] += value
        e_src = evidence[src]
        e_dst = evidence[dst]
        for index in feature.evidence_nz:
            value = feature.evidence_vec[index]
            e_src[index] -= value
            e_dst[index] += value
        s_src = source[src]
        s_dst = source[dst]
        for index in feature.source_nz:
            value = feature.source_vec[index]
            s_src[index] -= value
            s_dst[index] += value
        l_src = length[src]
        l_dst = length[dst]
        for index in feature.length_nz:
            value = feature.length_vec[index]
            l_src[index] -= value
            l_dst[index] += value

    j_target = {label: _js(target[label], global_target, n_id[label]) for label in report_labels}
    j_evidence = {label: _js(evidence[label], global_evidence, n_id[label]) for label in report_labels}
    j_length = {label: _js(length[label], global_length, n_core[label]) for label in report_labels}
    j_source = {label: _js(source[label], global_source, n_id[label]) for label in report_labels}

    def _rescore(label: str) -> None:
        j_target[label] = _js(target[label], global_target, n_id[label])
        j_evidence[label] = _js(evidence[label], global_evidence, n_id[label])
        j_length[label] = _js(length[label], global_length, n_core[label])
        j_source[label] = _js(source[label], global_source, n_id[label])

    def _prefix() -> tuple[Any, ...]:
        d_target = max(j_target.values())
        d_evidence = max(j_evidence.values())
        d_length = max(j_length.values())
        d_source = max(j_source.values())
        if profile == OBJECTIVE_PROFILE_ABSDEV:
            m_target = max(
                max_abs_dev_from_vec(target[label], global_target) for label in report_labels
            )
            m_evidence = max(
                max_abs_dev_from_vec(evidence[label], global_evidence)
                for label in report_labels
            )
            m_length = max(
                max_abs_dev_from_vec(length[label], global_length) for label in report_labels
            )
            m_source = max(
                max_abs_dev_from_vec(source[label], global_source) for label in report_labels
            )
            return scientific_prefix_from_components(
                d_target=d_target,
                d_evidence=d_evidence,
                d_length=d_length,
                d_source=d_source,
                m_target=m_target,
                m_evidence=m_evidence,
                m_length=m_length,
                m_source=m_source,
                profile=profile,
            )
        lex = tuple(sorted((d_target, d_evidence, d_length, d_source), reverse=True))
        return (max(lex), lex, d_target + d_evidence + d_length + d_source)

    accepted = 0
    n_passes = 0
    n_evals = 0
    n_exact = 0
    started = time.perf_counter()
    use_screen = evaluator != "scalar" and profile != OBJECTIVE_PROFILE_ABSDEV
    if evaluator not in {"screened", "scalar"}:
        raise S7PartitionError(f"unknown local-search evaluator {evaluator!r}")
    pair_candidates = 0
    label_list = list(place_labels)
    for i, label_a in enumerate(label_list):
        n_a = sum(1 for label in current.values() if label == label_a)
        for label_b in label_list[i + 1 :]:
            n_b = sum(1 for label in current.values() if label == label_b)
            pair_candidates += n_a * n_b

    def _publish() -> None:
        if search_stats is None:
            return
        search_stats["n_evals"] = n_evals
        search_stats["n_exact_evals"] = n_exact
        search_stats["n_accepted_swaps"] = accepted
        search_stats["n_passes"] = n_passes
        search_stats["elapsed_seconds"] = time.perf_counter() - started
        search_stats["pair_candidates_per_pass"] = pair_candidates
        search_stats["evaluator"] = "scalar" if not use_screen else "screened"

    def _enforce_bounds() -> None:
        elapsed = time.perf_counter() - started
        if max_evals is not None and n_evals > max_evals:
            _publish()
            raise S7PartitionError(
                "S7B local-search bound exceeded "
                f"(considered={n_evals}, max_evals={max_evals}, elapsed={elapsed:.1f}s); "
                "no partition output accepted"
            )
        if max_seconds is not None and elapsed > max_seconds:
            _publish()
            raise S7PartitionError(
                "S7B local-search bound exceeded "
                f"(elapsed={elapsed:.1f}s, max_seconds={max_seconds}, considered={n_evals}); "
                "no partition output accepted"
            )

    def _maybe_progress(*, force: bool = False) -> None:
        if not progress:
            return
        if not force and (progress_every <= 0 or n_evals == 0 or n_evals % progress_every != 0):
            return
        elapsed = time.perf_counter() - started
        rate = n_evals / elapsed if elapsed > 0 else 0.0
        done = ""
        if pair_candidates:
            frac = min(1.0, n_evals / pair_candidates)
            done = f" pass_progress~{frac:.1%}"
        sys.stderr.write(
            f"{log_prefix} local-search clusters={len(current)} "
            f"pass={n_passes} considered={n_evals} exact={n_exact} "
            f"accepted={accepted} elapsed={elapsed:.1f}s "
            f"swaps_per_s={rate:.0f} "
            f"objective={format_search_prefix(current_prefix)}{done}\n"
        )
        sys.stderr.flush()

    def _consider_exact(cluster_a: str, label_a: str, cluster_b: str, label_b: str) -> bool:
        nonlocal accepted, improved, current_prefix, current_sig, n_exact
        feat_a = features[cluster_a]
        feat_b = features[cluster_b]
        n_exact += 1
        cached = (
            j_target[label_a],
            j_evidence[label_a],
            j_length[label_a],
            j_source[label_a],
            j_target[label_b],
            j_evidence[label_b],
            j_length[label_b],
            j_source[label_b],
        )
        _move(feat_a, label_a, label_b)
        _move(feat_b, label_b, label_a)
        _rescore(label_a)
        _rescore(label_b)
        new_prefix = _prefix()
        better = new_prefix < current_prefix
        if new_prefix == current_prefix:
            if current_sig is None:
                current_sig = assignment_signature(current)
            trial = dict(current)
            trial[cluster_a] = label_b
            trial[cluster_b] = label_a
            better = assignment_signature(trial) < current_sig
        if better:
            members[label_a].remove(cluster_a)
            members[label_b].remove(cluster_b)
            members[label_a].add(cluster_b)
            members[label_b].add(cluster_a)
            current[cluster_a] = label_b
            current[cluster_b] = label_a
            accepted += 1
            improved = True
            current_prefix = new_prefix
            current_sig = None
            if accepted > max_accepted_swaps:
                raise S7PartitionError("pairwise local search exceeded max accepted swaps")
            return True
        _move(feat_a, label_b, label_a)
        _move(feat_b, label_a, label_b)
        (
            j_target[label_a],
            j_evidence[label_a],
            j_length[label_a],
            j_source[label_a],
            j_target[label_b],
            j_evidence[label_b],
            j_length[label_b],
            j_source[label_b],
        ) = cached
        return False

    def _screened_prefixes(
        label_a: str,
        label_b: str,
        feat_a: ClusterFeature,
        chunk: Sequence[ClusterFeature],
    ) -> list[tuple[Any, ...]]:
        third = [label for label in report_labels if label not in {label_a, label_b}]
        bundles = (
            (target, global_target, j_target, feat_a.target_vec, [item.target_vec for item in chunk]),
            (
                evidence,
                global_evidence,
                j_evidence,
                feat_a.evidence_vec,
                [item.evidence_vec for item in chunk],
            ),
            (length, global_length, j_length, feat_a.length_vec, [item.length_vec for item in chunk]),
            (source, global_source, j_source, feat_a.source_vec, [item.source_vec for item in chunk]),
        )
        worst: list[Any] = []
        for store, global_p, cached_j, vec_a, rows in bundles:
            mat_b = np.vstack(rows)
            new_a = store[label_a][None, :] - vec_a[None, :] + mat_b
            new_b = store[label_b][None, :] - mat_b + vec_a[None, :]
            ja = js_divergence_rows(new_a, global_p, log_base=log_base)
            jb = js_divergence_rows(new_b, global_p, log_base=log_base)
            other = max((cached_j[label] for label in third), default=0.0)
            worst.append(np.maximum(np.maximum(ja, jb), other))
        prefixes: list[tuple[Any, ...]] = []
        for index in range(len(chunk)):
            values = tuple(float(column[index]) for column in worst)
            lex = tuple(sorted(values, reverse=True))
            prefixes.append((max(lex), lex, values[0] + values[1] + values[2] + values[3]))
        return prefixes

    if progress:
        sys.stderr.write(
            f"{log_prefix} local-search start clusters={len(current)} "
            f"pair_candidates_per_pass={pair_candidates} "
            f"evaluator={'screened' if use_screen else 'scalar'}\n"
        )
        sys.stderr.flush()

    while True:
        n_passes += 1
        improved = False
        current_prefix = _prefix()
        current_sig: str | None = None
        labels = list(place_labels)
        for i, label_a in enumerate(labels):
            for label_b in labels[i + 1 :]:
                clusters_a = sorted(members[label_a])
                clusters_b = sorted(members[label_b])
                for cluster_a in clusters_a:
                    if cluster_a not in members[label_a]:
                        continue
                    feat_a = features[cluster_a]
                    if not use_screen:
                        for cluster_b in clusters_b:
                            if cluster_a not in members[label_a]:
                                break
                            if cluster_b not in members[label_b]:
                                continue
                            n_evals += 1
                            _enforce_bounds()
                            _maybe_progress()
                            if _consider_exact(cluster_a, label_a, cluster_b, label_b):
                                break
                        continue
                    pending = [cluster_b for cluster_b in clusters_b if cluster_b in members[label_b]]
                    cursor = 0
                    accepted_here = False
                    while cursor < len(pending):
                        if cluster_a not in members[label_a]:
                            break
                        window = pending[cursor : cursor + _SEARCH_BATCH_CHUNK]
                        cursor += len(window)
                        active = [cluster_b for cluster_b in window if cluster_b in members[label_b]]
                        if not active:
                            continue
                        screened = _screened_prefixes(
                            label_a,
                            label_b,
                            feat_a,
                            [features[cluster_b] for cluster_b in active],
                        )
                        for cluster_b, batch_prefix in zip(active, screened):
                            if cluster_a not in members[label_a]:
                                accepted_here = True
                                break
                            if cluster_b not in members[label_b]:
                                continue
                            n_evals += 1
                            _enforce_bounds()
                            _maybe_progress()
                            if _screen_rejects_swap(batch_prefix, current_prefix):
                                continue
                            if _consider_exact(cluster_a, label_a, cluster_b, label_b):
                                accepted_here = True
                                break
                        if accepted_here:
                            break
        if progress or len(current) >= 50:
            metric_name = "R1" if profile == OBJECTIVE_PROFILE_ABSDEV else "O1"
            elapsed = time.perf_counter() - started
            sys.stderr.write(
                f"{log_prefix} local-search pass="
                f"{n_passes} considered={n_evals} exact={n_exact} "
                f"accepted={accepted} "
                f"elapsed={elapsed:.1f}s "
                f"{metric_name}={current_prefix[0]:.9f} "
                f"objective={format_search_prefix(current_prefix)} improved={improved}\n"
            )
            sys.stderr.flush()
        if not improved:
            _publish()
            return current, accepted, n_passes, True
        if n_passes >= max_passes:
            _publish()
            return current, accepted, n_passes, False
    _publish()
    return current, accepted, n_passes, False


def random_whole_cluster_assignment(
    cluster_ids: Sequence[str],
    quotas: Any,
    seed: int,
    *,
    partition_labels: Sequence[str] | None = None,
) -> dict[str, str]:
    """Diagnostic only. Not eligible as the scientific assignment."""
    rng = random.Random(seed)
    ordered = sorted(cluster_ids)
    rng.shuffle(ordered)
    assignment: dict[str, str] = {}
    start = 0
    labels = resolve_partition_labels(partition_labels)
    counts = quotas.as_dict()
    for label in labels:
        n = counts[label]
        for cluster_id in ordered[start : start + n]:
            assignment[cluster_id] = label
        start += n
    if len(assignment) != len(cluster_ids):
        raise S7PartitionError("random assignment did not cover every cluster")
    return assignment


def score_assignment(
    assignment: Mapping[str, str],
    features: Mapping[str, ClusterFeature],
    space: FeatureSpace,
    *,
    partition_labels: Sequence[str] | None = None,
    objective_profile: str | None = None,
) -> ObjectiveScore:
    return score_partition_states(
        states_from_assignment(
            assignment, features, space, partition_labels=partition_labels
        ),
        space,
        partition_labels=partition_labels,
        objective_profile=objective_profile,
    )


def optimise_partition(
    features: Mapping[str, ClusterFeature],
    space: FeatureSpace,
    quotas: Any,
    *,
    max_passes: int = 10_000,
    max_evals: int | None = None,
    max_seconds: float | None = None,
    progress: bool = False,
    progress_every: int = 5_000,
    evaluator: str = "screened",
    partition_labels: Sequence[str] | None = None,
    placement_labels: Sequence[str] | None = None,
    log_prefix: str = "S7B",
    objective_profile: str | None = None,
) -> dict[str, Any]:
    profile = resolve_objective_profile(objective_profile)
    if progress:
        quota_text = ",".join(f"{label}={count}" for label, count in quotas.as_dict().items())
        sys.stderr.write(
            f"{log_prefix} quota-init clusters={len(features)} {quota_text}\n"
        )
        sys.stderr.flush()
    greedy = greedy_assign(
        features,
        space,
        quotas,
        partition_labels=partition_labels,
        placement_labels=placement_labels,
        objective_profile=profile,
    )
    search_stats: dict[str, Any] = {}
    improved, n_accepted, n_passes, converged = pairwise_local_search(
        greedy,
        features,
        space,
        max_passes=max_passes,
        max_evals=max_evals,
        max_seconds=max_seconds,
        progress=progress,
        progress_every=progress_every,
        evaluator=evaluator,
        partition_labels=partition_labels,
        placement_labels=placement_labels,
        log_prefix=log_prefix,
        objective_profile=profile,
        search_stats=search_stats,
    )
    score = score_assignment(
        improved,
        features,
        space,
        partition_labels=partition_labels,
        objective_profile=profile,
    )
    greedy_score = score_assignment(
        greedy,
        features,
        space,
        partition_labels=partition_labels,
        objective_profile=profile,
    )
    return {
        "quotas": quotas,
        "greedy_assignment": greedy,
        "assignment": improved,
        "score": score,
        "greedy_score": greedy_score,
        "n_accepted_swaps": n_accepted,
        "n_local_search_passes": n_passes,
        "n_evals": int(search_stats.get("n_evals", 0)),
        "n_exact_evals": int(search_stats.get("n_exact_evals", 0)),
        "search_elapsed_seconds": float(search_stats.get("elapsed_seconds", 0.0)),
        "local_search_converged": converged,
        "comparison_tuple": score.comparison_tuple(improved),
        "objective_profile": profile,
    }


def select_preview_assignment(
    features: Mapping[str, ClusterFeature],
    space: FeatureSpace,
    quota_candidates: Sequence[Any],
    *,
    max_passes: int = 10_000,
    max_evals: int | None = None,
    max_seconds: float | None = None,
    progress: bool = False,
    progress_every: int = 5_000,
    evaluator: str = "screened",
    partition_labels: Sequence[str] | None = None,
    placement_labels: Sequence[str] | None = None,
    log_prefix: str = "S7B",
    objective_profile: str | None = None,
) -> dict[str, Any]:
    if not quota_candidates:
        raise S7PartitionError("no quota candidates")
    profile = resolve_objective_profile(objective_profile)
    best: dict[str, Any] | None = None
    all_results: list[dict[str, Any]] = []
    for index, quotas in enumerate(quota_candidates, start=1):
        if progress:
            sys.stderr.write(
                f"{log_prefix} quota-candidate {index}/{len(quota_candidates)} "
                f"{quotas.as_tuple}\n"
            )
            sys.stderr.flush()
        result = optimise_partition(
            features,
            space,
            quotas,
            max_passes=max_passes,
            max_evals=max_evals,
            max_seconds=max_seconds,
            progress=progress,
            progress_every=progress_every,
            evaluator=evaluator,
            partition_labels=partition_labels,
            placement_labels=placement_labels,
            log_prefix=log_prefix,
            objective_profile=profile,
        )
        all_results.append(result)
        key = result["comparison_tuple"]
        if best is None or key < best["comparison_tuple"]:
            best = result
    assert best is not None
    best["quota_candidates"] = [item.as_tuple for item in quota_candidates]
    best["all_quota_results"] = all_results
    return best


def evaluate_random_baselines(
    features: Mapping[str, ClusterFeature],
    space: FeatureSpace,
    quotas: Any,
    seeds: Sequence[int],
    *,
    partition_labels: Sequence[str] | None = None,
    objective_profile: str | None = None,
) -> dict[str, Any]:
    profile = resolve_objective_profile(objective_profile)
    scores: list[dict[str, Any]] = []
    for seed in seeds:
        assignment = random_whole_cluster_assignment(
            list(features), quotas, int(seed), partition_labels=partition_labels
        )
        score = score_assignment(
            assignment,
            features,
            space,
            partition_labels=partition_labels,
            objective_profile=profile,
        )
        scores.append(
            {
                "seed": int(seed),
                "O1": score.o1,
                "D_target": score.d_target,
                "D_evidence": score.d_evidence,
                "D_length": score.d_length,
                "D_source": score.d_source,
                "O3": score.o3,
                "R1": score.r1,
                "M_target": score.m_target,
                "M_evidence": score.m_evidence,
                "M_length": score.m_length,
                "M_source": score.m_source,
                "R3": score.r3,
            }
        )
    o1_values = [item["O1"] for item in scores]
    r1_values = [item["R1"] for item in scores]
    return {
        "n_seeds": len(seeds),
        "seeds": [int(seed) for seed in seeds],
        "objective_profile": profile,
        "scores": scores,
        "O1_min": min(o1_values) if o1_values else None,
        "O1_max": max(o1_values) if o1_values else None,
        "O1_mean": (sum(o1_values) / len(o1_values)) if o1_values else None,
        "D_target_min": min(item["D_target"] for item in scores) if scores else None,
        "D_evidence_min": min(item["D_evidence"] for item in scores) if scores else None,
        "D_length_min": min(item["D_length"] for item in scores) if scores else None,
        "D_source_min": min(item["D_source"] for item in scores) if scores else None,
        "R1_min": min(r1_values) if r1_values else None,
        "R1_max": max(r1_values) if r1_values else None,
        "R1_mean": (sum(r1_values) / len(r1_values)) if r1_values else None,
        "M_target_min": min(item["M_target"] for item in scores) if scores else None,
        "M_evidence_min": min(item["M_evidence"] for item in scores) if scores else None,
        "M_length_min": min(item["M_length"] for item in scores) if scores else None,
        "M_source_min": min(item["M_source"] for item in scores) if scores else None,
    }


def apply_assignment_to_identities(
    corpus_rows: Sequence[Mapping[str, str]],
    assignment: Mapping[str, str],
) -> list[dict[str, str]]:
    """Map each identity to its cluster partition without mutating input rows."""
    mapped: list[dict[str, str]] = []
    for row in corpus_rows:
        cluster_id = _blank(row.get("cluster_id"))
        if cluster_id not in assignment:
            raise S7PartitionError(f"cluster {cluster_id} is unassigned")
        mapped.append(
            {
                "scientific_identity_id": _blank(row.get("scientific_identity_id")),
                "cluster_id": cluster_id,
                "proposed_partition": assignment[cluster_id],
                "canonical_target_name": _blank(row.get("canonical_target_name")),
                "evidence_level": _blank(row.get("evidence_level")),
                "source_db": _blank(row.get("source_db")) or "(blank)",
                "target_family": _blank(row.get("target_family")) or UNKNOWN_FAMILY,
                "sequence_core_digest": hashlib.sha256(
                    _blank(row.get("sequence_core")).encode("utf-8")
                ).hexdigest(),
            }
        )
    return mapped


def assignment_integrity_gates(
    corpus_rows: Sequence[Mapping[str, str]],
    assignment: Mapping[str, str],
    features: Mapping[str, ClusterFeature],
    quotas: Any,
) -> dict[str, Any]:
    """Label-agnostic cluster/identity/core integrity checks."""
    cluster_ids = set(features)
    assigned = set(assignment)
    if assigned != cluster_ids:
        raise S7PartitionError("assignment cluster set does not match the corpus")
    if len(assignment) != len(cluster_ids):
        raise S7PartitionError("a cluster is assigned more than once")
    counts = Counter(assignment.values())
    expected = quotas.as_dict()
    for label, wanted in expected.items():
        if counts.get(label, 0) != wanted:
            raise S7PartitionError(
                f"{label} cluster count {counts.get(label, 0)} != quota {wanted}"
            )
    identity_partitions: dict[str, str] = {}
    core_partitions: dict[str, str] = {}
    for row in corpus_rows:
        identity = _blank(row.get("scientific_identity_id"))
        cluster_id = _blank(row.get("cluster_id"))
        core = _blank(row.get("sequence_core"))
        label = assignment[cluster_id]
        if identity in identity_partitions:
            raise S7PartitionError("scientific_identity_id appears more than once")
        identity_partitions[identity] = label
        previous = core_partitions.get(core)
        if previous is None:
            core_partitions[core] = label
        elif previous != label:
            raise S7PartitionError("sequence_core spans partitions")
    evidence = Counter(_blank(row.get("evidence_level")) for row in corpus_rows)
    types = {_blank(row.get("target_type")) for row in corpus_rows}
    return {
        "clusters_assigned_exactly_once": True,
        "identities_assigned_exactly_once": True,
        "cores_cross_partitions": 0,
        "cluster_crossings": 0,
        "n_identities": len(identity_partitions),
        "n_cores": len(core_partitions),
        "n_clusters": len(assignment),
        "label_counts": dict(counts),
        "E5": int(evidence.get("E5", 0)),
        "non_protein": 0 if types == {"protein"} else 1,
        "identity_sum": len(identity_partitions),
        "core_sum": len(core_partitions),
        "cluster_sum": sum(counts.values()),
        "identity_partitions": identity_partitions,
        "core_partitions": core_partitions,
    }


def integrity_gates(
    corpus_rows: Sequence[Mapping[str, str]],
    assignment: Mapping[str, str],
    features: Mapping[str, ClusterFeature],
    quotas: QuotaTriple,
) -> dict[str, Any]:
    base = assignment_integrity_gates(corpus_rows, assignment, features, quotas)
    counts = Counter(assignment.values())
    types = {_blank(row.get("target_type")) for row in corpus_rows}
    return {
        "clusters_assigned_exactly_once": True,
        "identities_assigned_exactly_once": True,
        "cores_cross_partitions": 0,
        "cluster_crossings": 0,
        "n_identities": base["n_identities"],
        "n_cores": base["n_cores"],
        "n_clusters": base["n_clusters"],
        "n_FT": counts["FT"],
        "n_REF": counts["REF"],
        "n_EVAL": counts["EVAL"],
        "E5": base["E5"],
        "non_protein": 0 if types == {"protein"} else 1,
        "identity_sum": base["identity_sum"],
        "core_sum": base["core_sum"],
        "cluster_sum": counts["FT"] + counts["REF"] + counts["EVAL"],
    }


def max_abs_share_deviation(
    partition_counts: Mapping[str, int],
    global_counts: Mapping[str, int],
    support: Sequence[str],
    n_partition: int,
    n_global: int,
) -> dict[str, Any]:
    worst_category = ""
    worst_delta = 0.0
    for category in support:
        p_share = (partition_counts.get(category, 0) / n_partition) if n_partition else 0.0
        g_share = (global_counts.get(category, 0) / n_global) if n_global else 0.0
        delta = abs(p_share - g_share)
        if delta > worst_delta or (
            math.isclose(delta, worst_delta) and category < worst_category
        ):
            worst_delta = delta
            worst_category = category
    return {"category": worst_category, "abs_share_delta": worst_delta}


def target_representation_diagnostics(
    corpus_rows: Sequence[Mapping[str, str]],
    assignment: Mapping[str, str],
    *,
    partition_labels: Sequence[str] | None = None,
) -> dict[str, Any]:
    labels = resolve_partition_labels(partition_labels)
    by_target: dict[str, dict[str, Any]] = {}
    for row in corpus_rows:
        target = _blank(row.get("canonical_target_name"))
        cluster_id = _blank(row.get("cluster_id"))
        label = assignment[cluster_id]
        bucket = by_target.setdefault(
            target,
            {"identities": 0, "clusters": set(), "partitions": set()},
        )
        bucket["identities"] += 1
        bucket["clusters"].add(cluster_id)
        bucket["partitions"].add(label)

    represented = {label: 0 for label in labels}
    exclusive = {label: 0 for label in labels}
    singleton_identities = {label: 0 for label in labels}
    singleton_clusters = {label: 0 for label in labels}
    n_two = 0
    n_three = 0
    singleton_targets = 0
    for target, bucket in by_target.items():
        parts = bucket["partitions"]
        for label in parts:
            if label in represented:
                represented[label] += 1
        if bucket["identities"] == 1:
            singleton_targets += 1
            label = next(iter(parts))
            if label in singleton_identities:
                singleton_identities[label] += 1
                singleton_clusters[label] += 1
        if len(parts) == 1:
            only = next(iter(parts))
            if only in exclusive:
                exclusive[only] += 1
        elif len(parts) == 2:
            n_two += 1
        elif len(parts) == 3:
            n_three += 1
    top = sorted(
        by_target.items(),
        key=lambda item: (-item[1]["identities"], item[0]),
    )[:15]
    top_rows = []
    n_identities = len(corpus_rows)
    partition_identity_n = Counter(
        assignment[_blank(row.get("cluster_id"))] for row in corpus_rows
    )
    for target, bucket in top:
        counts = {label: 0 for label in labels}
        for row in corpus_rows:
            if _blank(row.get("canonical_target_name")) != target:
                continue
            counts[assignment[_blank(row.get("cluster_id"))]] += 1
        top_rows.append(
            {
                "canonical_target_name": target,
                "n_global": bucket["identities"],
                "share_global": bucket["identities"] / n_identities,
                **{f"n_{label}": counts[label] for label in labels},
                **{
                    f"share_{label}": (
                        counts[label] / partition_identity_n[label]
                        if partition_identity_n[label]
                        else 0.0
                    )
                    for label in labels
                },
            }
        )
    return {
        "n_targets": len(by_target),
        "targets_represented": represented,
        "targets_exclusive": exclusive,
        "targets_in_two_partitions": n_two,
        "targets_in_three_partitions": n_three,
        "n_singleton_targets": singleton_targets,
        "singleton_target_identities": singleton_identities,
        "singleton_target_clusters": singleton_clusters,
        "top_targets": top_rows,
    }


def category_distribution_rows(
    support: Sequence[str],
    global_counts: Mapping[str, int],
    states: Mapping[str, PartitionCounts],
    *,
    attr: str,
    name_field: str,
    grain: str,
    partition_labels: Sequence[str] | None = None,
) -> list[dict[str, str]]:
    labels = resolve_partition_labels(partition_labels)
    rows: list[dict[str, str]] = []
    n_global = sum(int(value) for value in global_counts.values())
    count_suffix = "_cores" if grain == "length" else ""
    global_count_field = f"n_global{count_suffix}"
    for category in support:
        row: dict[str, str] = {
            name_field: category,
            global_count_field: str(int(global_counts.get(category, 0))),
            "share_global": format_fraction(int(global_counts.get(category, 0)), n_global),
        }
        n_parts = 0
        for label in labels:
            counts = getattr(states[label], attr)
            n_part = states[label].n_cores if grain == "length" else states[label].n_identities
            value = int(counts.get(category, 0))
            if value:
                n_parts += 1
            row[f"n_{label}{count_suffix}"] = str(value)
            row[f"share_{label}"] = format_fraction(value, n_part)
        if name_field == "canonical_target_name":
            row["n_partitions_represented"] = str(n_parts)
        rows.append(row)
    return rows


def build_preview_tables(
    *,
    features: Mapping[str, ClusterFeature],
    space: FeatureSpace,
    assignment: Mapping[str, str],
    score: ObjectiveScore,
    family_js: Mapping[str, float],
) -> dict[str, list[dict[str, str]]]:
    states = states_from_assignment(assignment, features, space)
    cluster_rows = [
        features[cluster_id].preview_row(assignment[cluster_id])
        for cluster_id in sorted(features)
    ]
    identity_rows: list[dict[str, str]] = []
    core_rows: list[dict[str, str]] = []
    for label in REPORT_PARTITION_ORDER:
        state = states[label]
        n_id = state.n_identities
        n_core = state.n_cores
        identity_rows.append(
            {
                "partition": label,
                "n_clusters": str(state.n_clusters()),
                "cluster_fraction": format_fraction(state.n_clusters(), space.n_clusters),
                "n_identities": str(n_id),
                "identity_fraction": format_fraction(n_id, space.n_identities),
                "n_canonical_targets_represented": str(
                    sum(1 for count in state.target.values() if count > 0)
                ),
                "n_e2": str(int(state.evidence.get("E2", 0))),
                "n_e3": str(int(state.evidence.get("E3", 0))),
                "n_e4": str(int(state.evidence.get("E4", 0))),
                "prop_e2": format_fraction(int(state.evidence.get("E2", 0)), n_id),
                "prop_e3": format_fraction(int(state.evidence.get("E3", 0)), n_id),
                "prop_e4": format_fraction(int(state.evidence.get("E4", 0)), n_id),
                "n_multi_target_clusters": str(state.n_multi_target_clusters),
                "n_multi_source_clusters": str(state.n_multi_source_clusters),
            }
        )
        core_rows.append(
            {
                "partition": label,
                "n_distinct_cores": str(n_core),
                "core_fraction": format_fraction(n_core, space.n_cores),
                "n_short_cores": str(int(state.length.get("short", 0))),
                "n_long_cores": str(int(state.length.get("long", 0))),
                "prop_short": format_fraction(int(state.length.get("short", 0)), n_core),
                "prop_long": format_fraction(int(state.length.get("long", 0)), n_core),
            }
        )
    target_rows = category_distribution_rows(
        space.targets,
        space.global_target,
        states,
        attr="target",
        name_field="canonical_target_name",
        grain="identity",
    )
    evidence_rows = category_distribution_rows(
        space.evidence,
        space.global_evidence,
        states,
        attr="evidence",
        name_field="evidence_level",
        grain="identity",
    )
    length_rows = category_distribution_rows(
        space.length_regimes,
        space.global_length,
        states,
        attr="length",
        name_field="length_regime",
        grain="length",
    )
    source_rows = category_distribution_rows(
        space.sources,
        space.global_source,
        states,
        attr="source",
        name_field="source_db",
        grain="identity",
    )
    family_rows = category_distribution_rows(
        space.families,
        space.global_family,
        states,
        attr="family",
        name_field="target_family",
        grain="identity",
    )
    for row in family_rows:
        row["role"] = "secondary diagnostic — not optimisation objective"
    divergence_rows = [
        {
            "criterion": "target",
            "role": "primary",
            "J_FT": format_float(score.j_target["FT"]),
            "J_REF": format_float(score.j_target["REF"]),
            "J_EVAL": format_float(score.j_target["EVAL"]),
            "D_worst_partition": format_float(score.d_target),
            "log_base": format_float(score.log_base, 1),
        },
        {
            "criterion": "evidence",
            "role": "primary",
            "J_FT": format_float(score.j_evidence["FT"]),
            "J_REF": format_float(score.j_evidence["REF"]),
            "J_EVAL": format_float(score.j_evidence["EVAL"]),
            "D_worst_partition": format_float(score.d_evidence),
            "log_base": format_float(score.log_base, 1),
        },
        {
            "criterion": "length_regime",
            "role": "primary",
            "J_FT": format_float(score.j_length["FT"]),
            "J_REF": format_float(score.j_length["REF"]),
            "J_EVAL": format_float(score.j_length["EVAL"]),
            "D_worst_partition": format_float(score.d_length),
            "log_base": format_float(score.log_base, 1),
        },
        {
            "criterion": "source",
            "role": "primary",
            "J_FT": format_float(score.j_source["FT"]),
            "J_REF": format_float(score.j_source["REF"]),
            "J_EVAL": format_float(score.j_source["EVAL"]),
            "D_worst_partition": format_float(score.d_source),
            "log_base": format_float(score.log_base, 1),
        },
        {
            "criterion": "target_family",
            "role": "secondary diagnostic — not optimisation objective",
            "J_FT": format_float(family_js["FT"]),
            "J_REF": format_float(family_js["REF"]),
            "J_EVAL": format_float(family_js["EVAL"]),
            "D_worst_partition": format_float(max(family_js.values())),
            "log_base": format_float(score.log_base, 1),
        },
        {
            "criterion": "O1",
            "role": "primary objective",
            "J_FT": "",
            "J_REF": "",
            "J_EVAL": "",
            "D_worst_partition": format_float(score.o1),
            "log_base": format_float(score.log_base, 1),
        },
        {
            "criterion": "O3",
            "role": "primary objective",
            "J_FT": "",
            "J_REF": "",
            "J_EVAL": "",
            "D_worst_partition": format_float(score.o3),
            "log_base": format_float(score.log_base, 1),
        },
    ]
    return {
        "cluster_partition_preview.csv": cluster_rows,
        "partition_identity_summary.csv": identity_rows,
        "partition_core_summary.csv": core_rows,
        "partition_target_distribution.csv": target_rows,
        "partition_evidence_distribution.csv": evidence_rows,
        "partition_length_regime_distribution.csv": length_rows,
        "partition_source_distribution.csv": source_rows,
        "partition_target_family_diagnostic.csv": family_rows,
        "partition_divergence_metrics.csv": divergence_rows,
    }


def build_preview_report(
    *,
    input_sha256: str,
    observed: Mapping[str, int],
    gmm: Mapping[str, Any],
    n_short: int,
    n_long: int,
    quota_candidates: Sequence[tuple[int, int, int]],
    selected_quotas: QuotaTriple,
    score: ObjectiveScore,
    family_js: Mapping[str, float],
    tables: Mapping[str, Sequence[Mapping[str, str]]],
    target_diag: Mapping[str, Any],
    integrity: Mapping[str, Any],
    random_diag: Mapping[str, Any] | None,
    n_accepted_swaps: int,
    n_local_search_passes: int,
    local_search_converged: bool,
    greedy_o1: float,
) -> str:
    identity_rows = list(tables["partition_identity_summary.csv"])
    core_rows = list(tables["partition_core_summary.csv"])
    source_rows = list(tables["partition_source_distribution.csv"])
    evidence_rows = list(tables["partition_evidence_distribution.csv"])
    length_rows = list(tables["partition_length_regime_distribution.csv"])
    by_label = {row["partition"]: row for row in identity_rows}
    core_by_label = {row["partition"]: row for row in core_rows}

    def _part_block(label: str) -> list[str]:
        ident = by_label[label]
        core = core_by_label[label]
        lines = [
            f"### {label}",
            "",
            f"- clusters = {ident['n_clusters']} ({ident['cluster_fraction']})",
            f"- identities = {ident['n_identities']} ({ident['identity_fraction']})",
            f"- distinct cores = {core['n_distinct_cores']} ({core['core_fraction']})",
            f"- canonical targets represented = {ident['n_canonical_targets_represented']}",
            (
                f"- evidence E2/E3/E4 = {ident['n_e2']}/{ident['n_e3']}/{ident['n_e4']}"
                f" (props {ident['prop_e2']}/{ident['prop_e3']}/{ident['prop_e4']})"
            ),
            (
                f"- short/long cores = {core['n_short_cores']}/{core['n_long_cores']}"
                f" (props {core['prop_short']}/{core['prop_long']})"
            ),
            f"- multi-target clusters = {ident['n_multi_target_clusters']}",
            f"- multi-source clusters = {ident['n_multi_source_clusters']}",
            "",
        ]
        return lines

    source_lines = ["source_db counts by partition (identity-grain `source_db`):", ""]
    for row in source_rows:
        source_lines.append(
            "- "
            + row["source_db"]
            + f": global {row['n_global']} ({row['share_global']}); "
            + ", ".join(
                f"{label} {row[f'n_{label}']} ({row[f'share_{label}']})"
                for label in REPORT_PARTITION_ORDER
            )
        )
    top_lines = ["Top targets (identity grain; absence of a singleton is not leakage):", ""]
    for row in target_diag["top_targets"]:
        top_lines.append(
            f"- {row['canonical_target_name']}: global {row['n_global']} "
            f"({format_float(row['share_global'], 6)}); "
            + ", ".join(
                f"{label} {row[f'n_{label}']}" for label in REPORT_PARTITION_ORDER
            )
        )
    random_lines: list[str]
    if random_diag:
        random_lines = [
            "## Random whole-cluster baseline (diagnostic only)",
            "",
            "This baseline is not eligible to become the scientific split.",
            "",
            f"- seeds = {random_diag['seeds']}",
            f"- random O1 min/mean/max = {format_float(random_diag['O1_min'])} / "
            f"{format_float(random_diag['O1_mean'])} / {format_float(random_diag['O1_max'])}",
            f"- optimised O1 = {format_float(score.o1)}",
            f"- random D_target min = {format_float(random_diag['D_target_min'])}; "
            f"optimised D_target = {format_float(score.d_target)}",
            f"- random D_evidence min = {format_float(random_diag['D_evidence_min'])}; "
            f"optimised D_evidence = {format_float(score.d_evidence)}",
            f"- random D_length min = {format_float(random_diag['D_length_min'])}; "
            f"optimised D_length = {format_float(score.d_length)}",
            f"- random D_source min = {format_float(random_diag['D_source_min'])}; "
            f"optimised D_source = {format_float(score.d_source)}",
            "",
        ]
    else:
        random_lines = ["## Random whole-cluster baseline (diagnostic only)", "", "Omitted.", ""]

    def _max_share_delta(rows: Sequence[Mapping[str, str]], share_global_key: str = "share_global") -> str:
        worst = 0.0
        worst_label = ""
        worst_category = ""
        category_key = next(
            key
            for key in rows[0].keys()
            if key
            not in {
                "n_global",
                "n_global_cores",
                "share_global",
                "n_FT",
                "n_REF",
                "n_EVAL",
                "n_FT_cores",
                "n_REF_cores",
                "n_EVAL_cores",
                "share_FT",
                "share_REF",
                "share_EVAL",
                "n_partitions_represented",
                "role",
            }
        ) if rows else ""
        for row in rows:
            g = float(row[share_global_key] or 0.0)
            for label in REPORT_PARTITION_ORDER:
                delta = abs(float(row[f"share_{label}"] or 0.0) - g)
                if delta > worst:
                    worst = delta
                    worst_label = label
                    worst_category = str(row.get(category_key, ""))
        if not rows:
            return "n/a"
        return f"{format_float(worst)} ({worst_label} vs global, category {worst_category})"

    known_family_global = space_family_known_share(tables)
    lines = [
        "# S7B partition preview — not frozen",
        "",
        "This artefact is a dry-run/preview of a deterministic whole-cluster",
        "FT/REF/EVAL assignment. REF and EVAL are **not frozen**. This preview",
        "must not be used for model development, fine-tuning, or hyperparameter",
        "decisions.",
        "",
        "## Frozen S7A input",
        "",
        f"- corpus_post_cap.csv SHA-256 = `{input_sha256}`",
        f"- identities = {observed['n_scientific_identities']}",
        f"- distinct sequence_core = {observed['n_distinct_sequence_core']}",
        f"- clusters = {observed['n_final_clusters']}",
        f"- canonical targets = {observed['n_canonical_targets']}",
        "",
        "## Frozen S6 length-regime provenance",
        "",
        "- assignment_method = `gmm_k2_maximum_posterior`",
        "- GMM source = frozen S6 `bimodality.json` `gmm_2` (not refit on post-cap)",
        f"- component means = {list(gmm['means'])}",
        f"- component weights = {list(gmm['weights'])}",
        "- grain = distinct `sequence_core`",
        f"- post-cap short cores = {n_short}",
        f"- post-cap long cores = {n_long}",
        "",
        "## Integer cluster quotas",
        "",
        f"- tied-optimal candidates (n_FT, n_REF, n_EVAL) = {list(quota_candidates)}",
        (
            f"- selected by scientific objective = "
            f"({selected_quotas.n_FT}, {selected_quotas.n_REF}, {selected_quotas.n_EVAL})"
        ),
        "",
        "## Objective",
        "",
        "- JSD log base = 2 (bits, bounded by 1)",
        "- D_criterion = max over partitions of J_criterion(partition || global)",
        "- O1 = max(D_target, D_evidence, D_length, D_source)",
        "- O2 = lexicographic minimum of the four D values sorted descending",
        "- O3 = sum of the four D values",
        "- final tie-break = sorted `cluster_id:partition` signature",
        "- arbitrary manually chosen criterion weights = none",
        "- target_family in primary objective = no",
        "",
        f"- greedy O1 before local search = {format_float(greedy_o1)}",
        f"- accepted pairwise swaps = {n_accepted_swaps}",
        f"- local-search passes (including terminal no-improve pass) = {n_local_search_passes}",
        f"- local-search converged (no-improve pass) = {local_search_converged}",
        "",
        "## Preview partition sizes",
        "",
        "| partition | clusters | cluster fraction | identities | identity fraction | cores | core fraction |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for label in REPORT_PARTITION_ORDER:
        ident = by_label[label]
        core = core_by_label[label]
        lines.append(
            f"| {label} | {ident['n_clusters']} | {ident['cluster_fraction']} | "
            f"{ident['n_identities']} | {ident['identity_fraction']} | "
            f"{core['n_distinct_cores']} | {core['core_fraction']} |"
        )
    lines.extend(["", "## Per-partition primary comparability", ""])
    for label in REPORT_PARTITION_ORDER:
        lines.extend(_part_block(label))
    lines.extend(
        [
            "### Evidence global vs partitions",
            "",
        ]
    )
    for row in evidence_rows:
        lines.append(
            f"- {row['evidence_level']}: global {row['n_global']} ({row['share_global']}); "
            + ", ".join(
                f"{label} {row[f'n_{label}']} ({row[f'share_{label}']})"
                for label in REPORT_PARTITION_ORDER
            )
        )
    lines.extend(["", "### Length regime (distinct-core grain)", ""])
    for row in length_rows:
        lines.append(
            f"- {row['length_regime']}: global {row['n_global_cores']} ({row['share_global']}); "
            + ", ".join(
                f"{label} {row[f'n_{label}_cores']} ({row[f'share_{label}']})"
                for label in REPORT_PARTITION_ORDER
            )
        )
    lines.extend(["", "### Source", ""])
    lines.extend(source_lines)
    lines.extend(
        [
            "",
            "## Primary divergence (JSD, log2 bits)",
            "",
            f"- J_target(FT/REF/EVAL) = {format_float(score.j_target['FT'])} / "
            f"{format_float(score.j_target['REF'])} / {format_float(score.j_target['EVAL'])}",
            f"- D_target = {format_float(score.d_target)}",
            f"- J_evidence(FT/REF/EVAL) = {format_float(score.j_evidence['FT'])} / "
            f"{format_float(score.j_evidence['REF'])} / {format_float(score.j_evidence['EVAL'])}",
            f"- D_evidence = {format_float(score.d_evidence)}",
            f"- J_length(FT/REF/EVAL) = {format_float(score.j_length['FT'])} / "
            f"{format_float(score.j_length['REF'])} / {format_float(score.j_length['EVAL'])}",
            f"- D_length = {format_float(score.d_length)}",
            f"- J_source(FT/REF/EVAL) = {format_float(score.j_source['FT'])} / "
            f"{format_float(score.j_source['REF'])} / {format_float(score.j_source['EVAL'])}",
            f"- D_source = {format_float(score.d_source)}",
            f"- O1 = {format_float(score.o1)}",
            f"- descending D vector = {list(score.lex_vector)}",
            f"- O3 = {format_float(score.o3)}",
            "",
            "There is no supervisor-defined numeric JSD pass threshold.",
            "",
            f"- max |share_target,p - share_target,global| = {_max_share_delta(list(tables['partition_target_distribution.csv']))}",
            f"- max |share_evidence,p - share_evidence,global| = {_max_share_delta(evidence_rows)}",
            f"- max |share_length,p - share_length,global| = {_max_share_delta(length_rows)}",
            f"- max |share_source,p - share_source,global| = {_max_share_delta(source_rows)}",
            "",
            "## Target representation diagnostics",
            "",
            f"- targets represented FT/REF/EVAL = "
            f"{target_diag['targets_represented']['FT']} / "
            f"{target_diag['targets_represented']['REF']} / "
            f"{target_diag['targets_represented']['EVAL']}",
            f"- singleton-target identities FT/REF/EVAL = "
            f"{target_diag['singleton_target_identities']['FT']} / "
            f"{target_diag['singleton_target_identities']['REF']} / "
            f"{target_diag['singleton_target_identities']['EVAL']}",
            f"- targets exclusive to FT/REF/EVAL = "
            f"{target_diag['targets_exclusive']['FT']} / "
            f"{target_diag['targets_exclusive']['REF']} / "
            f"{target_diag['targets_exclusive']['EVAL']}",
            f"- targets in exactly 2 partitions = {target_diag['targets_in_two_partitions']}",
            f"- targets in all 3 partitions = {target_diag['targets_in_three_partitions']}",
            "",
        ]
    )
    lines.extend(top_lines)
    lines.extend(
        [
            "",
            "Singleton-target absence from a partition is a whole-cluster coverage",
            "limitation, not leakage.",
            "",
            "## Secondary target-family diagnostic — not optimisation objective",
            "",
            f"- J_family(FT/REF/EVAL) = {format_float(family_js['FT'])} / "
            f"{format_float(family_js['REF'])} / {format_float(family_js['EVAL'])}",
            f"- D_family (diagnostic) = {format_float(max(family_js.values()))}",
            f"- known-family identity share (global diagnostic) = {known_family_global}",
            "",
            "Clusters were not moved to improve this metric.",
            "",
        ]
    )
    lines.extend(random_lines)
    lines.extend(
        [
            "## Integrity",
            "",
            f"- clusters assigned exactly once = {integrity['clusters_assigned_exactly_once']}",
            f"- identities assigned exactly once = {integrity['identities_assigned_exactly_once']}",
            f"- cores cross partitions = {integrity['cores_cross_partitions']}",
            f"- cluster crossings = {integrity['cluster_crossings']}",
            f"- E5 = {integrity['E5']}",
            f"- non-protein = {integrity['non_protein']}",
            "- S7A input mutated = no",
            "- authoritative partitioned corpus written = no",
            "- REF frozen = no",
            "- EVAL frozen = no",
            "",
            "STOP. Human review is required before any authoritative assignment.",
            "",
        ]
    )
    report = "\n".join(lines)
    assert_no_sequence_leak(report, label="s7b_partition_preview_report.md")
    return report


def enforce_application_config(config: Mapping[str, Any]) -> None:
    mode = str(config.get("mode") or "").strip()
    if mode != APPLY_MODE:
        raise S7PartitionError(f"S7B application mode must be apply, got {mode!r}")
    if config.get("write_authoritative_partitioned_corpus") is not True:
        raise S7PartitionError("S7B application must write the authoritative partitioned corpus")
    if config.get("freeze_ref") is not True or config.get("freeze_eval") is not True:
        raise S7PartitionError("S7B application must freeze REF and EVAL")
    if config.get("create_train_validation_split") is True:
        raise S7PartitionError("S7B application must not create an FT train/validation split")
    if config.get("write_corpus_final") is True:
        raise S7PartitionError("S7B application must not write corpus_final")
    does_not = {str(item) for item in config.get("does_not", [])}
    required = {
        "write_corpus_final",
        "create_train_validation_split",
        "promote_e5",
        "promote_non_protein",
        "rewrite_s5",
        "rewrite_s6",
        "rewrite_s7a",
        "start_s7c",
    }
    missing = sorted(required - does_not)
    if missing:
        raise S7PartitionError(f"S7B application config.does_not missing required exclusions: {missing}")


def cluster_assignment_rows(
    features: Mapping[str, ClusterFeature],
    assignment: Mapping[str, str],
) -> list[dict[str, str]]:
    return [
        features[cluster_id].assignment_row(assignment[cluster_id])
        for cluster_id in sorted(assignment)
    ]


def populate_partition_on_corpus(
    corpus_rows: Sequence[Mapping[str, str]],
    assignment: Mapping[str, str],
    fieldnames: Sequence[str],
) -> list[dict[str, str]]:
    """Copy frozen S7A rows in source order, filling only ``partition``."""
    if "partition" not in fieldnames:
        raise S7PartitionError("frozen S7A corpus is missing the partition column")
    populated: list[dict[str, str]] = []
    for row in corpus_rows:
        cluster_id = _blank(row.get("cluster_id"))
        if cluster_id not in assignment:
            raise S7PartitionError(f"cluster {cluster_id} is unassigned")
        new_row = {column: row.get(column, "") for column in fieldnames}
        new_row["partition"] = assignment[cluster_id]
        populated.append(new_row)
    return populated


def partition_subset_rows(
    partitioned_rows: Sequence[Mapping[str, str]],
    label: str,
) -> list[dict[str, str]]:
    if label not in VALID_PARTITION_LABELS:
        raise S7PartitionError(f"invalid partition label {label!r}")
    return [dict(row) for row in partitioned_rows if _blank(row.get("partition")) == label]


def semantic_identity_set_hash(rows: Sequence[Mapping[str, str]]) -> str:
    """Order-independent identity-set fingerprint using non-sequence identifiers."""
    lines: list[str] = []
    for row in sorted(rows, key=lambda item: _blank(item.get("scientific_identity_id"))):
        identity = _blank(row.get("scientific_identity_id"))
        cluster_id = _blank(row.get("cluster_id"))
        core_digest = _blank(row.get("sequence_core_sha256"))
        if not identity or not cluster_id:
            raise S7PartitionError("semantic identity fingerprint requires identity and cluster_id")
        if core_digest:
            lines.append(f"{identity}\t{cluster_id}\t{core_digest}")
        else:
            lines.append(f"{identity}\t{cluster_id}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def semantic_cluster_set_hash(rows: Sequence[Mapping[str, str]]) -> str:
    clusters = sorted({_blank(row.get("cluster_id")) for row in rows})
    if any(not item for item in clusters):
        raise S7PartitionError("semantic cluster fingerprint found a blank cluster_id")
    return hashlib.sha256("\n".join(clusters).encode("utf-8")).hexdigest()


def _mismatch(label: str, expected: Any, observed: Any) -> str | None:
    if expected != observed:
        return f"{label}: expected {expected}, got {observed}"
    return None


def _float_mismatch(label: str, expected: Any, observed: Any) -> str | None:
    if expected is None or observed is None:
        return _mismatch(label, expected, observed)
    try:
        if float(expected) != float(observed):
            return f"{label}: expected {expected}, got {observed}"
    except (TypeError, ValueError):
        return _mismatch(label, expected, observed)
    return None


def preview_application_parity_mismatches(
    *,
    preview_assignment: Mapping[str, str],
    application_assignment: Mapping[str, str],
    preview_quotas: Mapping[str, int],
    application_quotas: QuotaTriple,
    preview_tables: Mapping[str, Sequence[Mapping[str, str]]],
    application_tables: Mapping[str, Sequence[Mapping[str, str]]],
    preview_objective: Mapping[str, Any],
    application_score: ObjectiveScore,
    preview_target_diag: Mapping[str, Any] | None = None,
    application_target_diag: Mapping[str, Any] | None = None,
    preview_family_js: Mapping[str, float] | None = None,
    application_family_js: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Post-derivation comparison. Does not select or copy the assignment."""
    mismatches: list[str] = []
    cluster_compared = len(application_assignment)
    cluster_mismatches = 0
    mismatches.append(
        _mismatch(
            "cluster_set",
            sorted(preview_assignment),
            sorted(application_assignment),
        )
    )
    for cluster_id, label in application_assignment.items():
        if preview_assignment.get(cluster_id) != label:
            cluster_mismatches += 1
    if cluster_mismatches:
        mismatches.append(
            f"cluster assignment mismatches = {cluster_mismatches} / {cluster_compared}"
        )
    for label in REPORT_PARTITION_ORDER:
        preview_ids = {
            cluster_id
            for cluster_id, assigned in preview_assignment.items()
            if assigned == label
        }
        apply_ids = {
            cluster_id
            for cluster_id, assigned in application_assignment.items()
            if assigned == label
        }
        mismatches.append(_mismatch(f"{label}_cluster_set", sorted(preview_ids), sorted(apply_ids)))
    mismatches.append(
        _mismatch("n_FT", int(preview_quotas.get("n_FT", -1)), application_quotas.n_FT)
    )
    mismatches.append(
        _mismatch("n_REF", int(preview_quotas.get("n_REF", -1)), application_quotas.n_REF)
    )
    mismatches.append(
        _mismatch("n_EVAL", int(preview_quotas.get("n_EVAL", -1)), application_quotas.n_EVAL)
    )

    table_keys = (
        "partition_identity_summary.csv",
        "partition_core_summary.csv",
        "partition_target_distribution.csv",
        "partition_evidence_distribution.csv",
        "partition_length_regime_distribution.csv",
        "partition_source_distribution.csv",
        "partition_target_family_diagnostic.csv",
        "partition_divergence_metrics.csv",
    )
    aggregate_mismatches = 0
    for name in table_keys:
        preview_rows = [dict(row) for row in preview_tables.get(name, [])]
        apply_rows = [dict(row) for row in application_tables.get(name, [])]
        if preview_rows != apply_rows:
            aggregate_mismatches += 1
            mismatches.append(_mismatch(name, preview_rows, apply_rows))

    objective_mismatches = 0
    apply_objective = application_score.as_dict()
    for key in (
        "O1",
        "O3",
        "D_target",
        "D_evidence",
        "D_length",
        "D_source",
        "lexicographic_descending_D_vector",
        "J_target",
        "J_evidence",
        "J_length",
        "J_source",
    ):
        item = _float_tree_mismatch(key, preview_objective.get(key), apply_objective.get(key))
        if item:
            objective_mismatches += 1
            mismatches.append(item)

    if preview_target_diag is not None and application_target_diag is not None:
        for key in (
            "targets_represented",
            "targets_exclusive",
            "targets_in_two_partitions",
            "targets_in_three_partitions",
            "singleton_target_identities",
        ):
            item = _mismatch(
                key,
                jsonable(preview_target_diag.get(key)),
                jsonable(application_target_diag.get(key)),
            )
            if item:
                aggregate_mismatches += 1
                mismatches.append(item)
    if preview_family_js is not None and application_family_js is not None:
        item = _float_tree_mismatch("J_family", preview_family_js, application_family_js)
        if item:
            aggregate_mismatches += 1
            mismatches.append(item)

    compact = [item for item in mismatches if item]
    return {
        "cluster_assignments_compared": cluster_compared,
        "cluster_assignment_mismatches": cluster_mismatches,
        "aggregate_statistical_mismatches": aggregate_mismatches,
        "objective_mismatches": objective_mismatches,
        "semantic_mismatches_total": len(compact),
        "mismatches": compact,
    }


def _float_tree_mismatch(label: str, expected: Any, observed: Any) -> str | None:
    if isinstance(expected, Mapping) and isinstance(observed, Mapping):
        if sorted(expected) != sorted(observed):
            return _mismatch(label, expected, observed)
        for key in expected:
            item = _float_tree_mismatch(f"{label}.{key}", expected[key], observed[key])
            if item:
                return item
        return None
    if isinstance(expected, (list, tuple)) and isinstance(observed, (list, tuple)):
        if len(expected) != len(observed):
            return _mismatch(label, expected, observed)
        for index, (left, right) in enumerate(zip(expected, observed)):
            item = _float_tree_mismatch(f"{label}[{index}]", left, right)
            if item:
                return item
        return None
    if isinstance(expected, (int, float)) or isinstance(observed, (int, float)):
        return _float_mismatch(label, expected, observed)
    return _mismatch(label, expected, observed)


def approval_parity_mismatches(
    *,
    assignment: Mapping[str, str],
    features: Mapping[str, ClusterFeature],
    quotas: QuotaTriple,
    score: ObjectiveScore,
    approval: Mapping[str, Any],
) -> list[str]:
    mismatches: list[str] = []
    reviewed = approval.get("reviewed_preview") or {}
    approved_quotas = approval.get("approved_cluster_quotas") or reviewed
    mismatches.append(
        _mismatch("approved_n_FT", int(approved_quotas.get("FT", -1)), quotas.n_FT)
    )
    mismatches.append(
        _mismatch("approved_n_REF", int(approved_quotas.get("REF", -1)), quotas.n_REF)
    )
    mismatches.append(
        _mismatch("approved_n_EVAL", int(approved_quotas.get("EVAL", -1)), quotas.n_EVAL)
    )
    counts = Counter(assignment.values())
    identity_n = {label: 0 for label in REPORT_PARTITION_ORDER}
    core_n = {label: 0 for label in REPORT_PARTITION_ORDER}
    for cluster_id, label in assignment.items():
        identity_n[label] += features[cluster_id].n_identities
        core_n[label] += features[cluster_id].n_cores
    approved_identities = approval.get("approved_identities") or reviewed
    approved_cores = approval.get("approved_cores") or reviewed
    for label in REPORT_PARTITION_ORDER:
        mismatches.append(
            _mismatch(
                f"approved_{label}_identities",
                int(approved_identities.get(label, -1)),
                identity_n[label],
            )
        )
        mismatches.append(
            _mismatch(
                f"approved_{label}_cores",
                int(approved_cores.get(label, -1)),
                core_n[label],
            )
        )
        mismatches.append(
            _mismatch(
                f"approved_{label}_clusters",
                int(approved_quotas.get(label, -1)),
                counts[label],
            )
        )
    approved_objective = approval.get("approved_objective") or {}
    mismatches.append(_float_mismatch("approved_O1", approved_objective.get("O1"), score.o1))
    mismatches.append(
        _float_mismatch("approved_D_target", approved_objective.get("D_target"), score.d_target)
    )
    mismatches.append(
        _float_mismatch(
            "approved_D_evidence", approved_objective.get("D_evidence"), score.d_evidence
        )
    )
    mismatches.append(
        _float_mismatch("approved_D_length", approved_objective.get("D_length"), score.d_length)
    )
    mismatches.append(
        _float_mismatch("approved_D_source", approved_objective.get("D_source"), score.d_source)
    )
    mismatches.append(_float_mismatch("approved_O3", approved_objective.get("O3"), score.o3))
    return [item for item in mismatches if item]


def independent_partition_invariants(
    *,
    input_rows: Sequence[Mapping[str, str]],
    partitioned_rows: Sequence[Mapping[str, str]],
    ft_rows: Sequence[Mapping[str, str]],
    ref_rows: Sequence[Mapping[str, str]],
    eval_rows: Sequence[Mapping[str, str]],
    assignment_rows: Sequence[Mapping[str, str]],
    fieldnames: Sequence[str],
) -> dict[str, Any]:
    if list(fieldnames) != list(partitioned_rows[0].keys() if partitioned_rows else fieldnames):
        written_fields = list(partitioned_rows[0].keys()) if partitioned_rows else []
        if written_fields != list(fieldnames):
            raise S7PartitionError("corpus_partitioned.csv column order drifted")
    if len(partitioned_rows) != len(input_rows):
        raise S7PartitionError("corpus_partitioned.csv identity count drifted from frozen S7A")
    identity_seen: dict[str, str] = {}
    cluster_seen: dict[str, str] = {}
    core_seen: dict[str, str] = {}
    invalid_labels = 0
    blank_partition = 0
    field_changes = 0
    for original, written in zip(input_rows, partitioned_rows):
        if list(written.keys()) != list(fieldnames):
            raise S7PartitionError("corpus_partitioned.csv does not preserve column order")
        label = _blank(written.get("partition"))
        if not label:
            blank_partition += 1
        elif label not in VALID_PARTITION_LABELS:
            invalid_labels += 1
        for column in fieldnames:
            if column == "partition":
                continue
            if written.get(column, "") != original.get(column, ""):
                field_changes += 1
        identity = _blank(written.get("scientific_identity_id"))
        cluster_id = _blank(written.get("cluster_id"))
        core = _blank(written.get("sequence_core"))
        if identity in identity_seen:
            raise S7PartitionError("scientific_identity_id appears more than once")
        identity_seen[identity] = label
        previous_cluster = cluster_seen.get(cluster_id)
        if previous_cluster is None:
            cluster_seen[cluster_id] = label
        elif previous_cluster != label:
            raise S7PartitionError("cluster_id spans partitions")
        previous_core = core_seen.get(core)
        if previous_core is None:
            core_seen[core] = label
        elif previous_core != label:
            raise S7PartitionError("sequence_core spans partitions")

    subsets = {"FT": ft_rows, "REF": ref_rows, "EVAL": eval_rows}
    subset_identities: dict[str, list[str]] = {}
    for label, rows in subsets.items():
        subset_identities[label] = [_blank(row.get("scientific_identity_id")) for row in rows]
        expected = [
            dict(row) for row in partitioned_rows if _blank(row.get("partition")) == label
        ]
        if [dict(row) for row in rows] != expected:
            raise S7PartitionError(f"{label.lower()}.csv is not an exact row subset")
        if any(_blank(row.get("partition")) != label for row in rows):
            raise S7PartitionError(f"{label.lower()}.csv contains a foreign partition label")

    union_ids = (
        set(subset_identities["FT"])
        | set(subset_identities["REF"])
        | set(subset_identities["EVAL"])
    )
    if union_ids != set(identity_seen):
        raise S7PartitionError("FT/REF/EVAL identity union does not match corpus_partitioned")
    overlap = (
        (set(subset_identities["FT"]) & set(subset_identities["REF"]))
        | (set(subset_identities["FT"]) & set(subset_identities["EVAL"]))
        | (set(subset_identities["REF"]) & set(subset_identities["EVAL"]))
    )
    if overlap:
        raise S7PartitionError("an identity appears in more than one partition file")

    assignment_map = {
        _blank(row.get("cluster_id")): _blank(row.get("partition")) for row in assignment_rows
    }
    if assignment_map != cluster_seen:
        raise S7PartitionError("cluster_partition_assignment.csv disagrees with corpus_partitioned")

    evidence = Counter(_blank(row.get("evidence_level")) for row in partitioned_rows)
    types = {_blank(row.get("target_type")) for row in partitioned_rows}
    return {
        "n_identities": len(identity_seen),
        "n_cores": len(core_seen),
        "n_clusters": len(cluster_seen),
        "identity_sum": sum(len(items) for items in subset_identities.values()),
        "cluster_sum": sum(len({row["cluster_id"] for row in rows}) for rows in subsets.values()),
        "core_sum": sum(len({row["sequence_core"] for row in rows}) for rows in subsets.values()),
        "identities_assigned_exactly_once": True,
        "clusters_assigned_exactly_once": True,
        "cores_cross_partitions": 0,
        "cluster_crossings": 0,
        "partition_blank": blank_partition,
        "invalid_partition_labels": invalid_labels,
        "field_changes_excluding_partition": field_changes,
        "E5": int(evidence.get("E5", 0)),
        "non_protein": 0 if types == {"protein"} else 1,
        "n_FT": len(subset_identities["FT"]),
        "n_REF": len(subset_identities["REF"]),
        "n_EVAL": len(subset_identities["EVAL"]),
        "n_FT_clusters": len({row["cluster_id"] for row in ft_rows}),
        "n_REF_clusters": len({row["cluster_id"] for row in ref_rows}),
        "n_EVAL_clusters": len({row["cluster_id"] for row in eval_rows}),
        "n_FT_cores": len({row["sequence_core"] for row in ft_rows}),
        "n_REF_cores": len({row["sequence_core"] for row in ref_rows}),
        "n_EVAL_cores": len({row["sequence_core"] for row in eval_rows}),
        "n_FT_targets": len({row["canonical_target_name"] for row in ft_rows}),
        "n_REF_targets": len({row["canonical_target_name"] for row in ref_rows}),
        "n_EVAL_targets": len({row["canonical_target_name"] for row in eval_rows}),
    }


def independent_distribution_counts(
    partitioned_rows: Sequence[Mapping[str, str]],
    core_regimes: Mapping[str, str],
) -> dict[str, Any]:
    evidence = {label: Counter() for label in REPORT_PARTITION_ORDER}
    source = {label: Counter() for label in REPORT_PARTITION_ORDER}
    family = {label: Counter() for label in REPORT_PARTITION_ORDER}
    length = {label: Counter() for label in REPORT_PARTITION_ORDER}
    cores_seen = {label: set() for label in REPORT_PARTITION_ORDER}
    for row in partitioned_rows:
        label = _blank(row.get("partition"))
        if label not in VALID_PARTITION_LABELS:
            raise S7PartitionError(f"invalid partition label {label!r}")
        evidence[label][_blank(row.get("evidence_level"))] += 1
        source[label][_blank(row.get("source_db")) or "(blank)"] += 1
        family[label][_blank(row.get("target_family")) or UNKNOWN_FAMILY] += 1
        core = _blank(row.get("sequence_core"))
        if core not in cores_seen[label]:
            cores_seen[label].add(core)
            regime = core_regimes.get(core)
            if regime not in LENGTH_REGIME_LABELS:
                raise S7PartitionError("length regime missing during independent recount")
            length[label][regime] += 1
    known_family = sum(
        1
        for row in partitioned_rows
        if (_blank(row.get("target_family")) or UNKNOWN_FAMILY) != UNKNOWN_FAMILY
    )
    unknown_share = {
        label: (
            family[label].get(UNKNOWN_FAMILY, 0) / sum(family[label].values())
            if sum(family[label].values())
            else 0.0
        )
        for label in REPORT_PARTITION_ORDER
    }
    return {
        "evidence": {label: dict(evidence[label]) for label in REPORT_PARTITION_ORDER},
        "source": {label: dict(source[label]) for label in REPORT_PARTITION_ORDER},
        "length": {label: dict(length[label]) for label in REPORT_PARTITION_ORDER},
        "family_unknown_share": unknown_share,
        "known_family_identities": known_family,
        "n_identities": len(partitioned_rows),
    }


def assignment_from_partitioned_rows(
    partitioned_rows: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    assignment: dict[str, str] = {}
    for row in partitioned_rows:
        cluster_id = _blank(row.get("cluster_id"))
        label = _blank(row.get("partition"))
        previous = assignment.get(cluster_id)
        if previous is None:
            assignment[cluster_id] = label
        elif previous != label:
            raise S7PartitionError("cluster_id spans partitions in corpus_partitioned.csv")
    return assignment


def build_application_tables(
    features: Mapping[str, ClusterFeature],
    space: FeatureSpace,
    assignment: Mapping[str, str],
    score: ObjectiveScore,
    family_js: Mapping[str, float],
) -> dict[str, list[dict[str, str]]]:
    tables = build_preview_tables(
        features=features,
        space=space,
        assignment=assignment,
        score=score,
        family_js=family_js,
    )
    tables.pop("cluster_partition_preview.csv", None)
    tables["cluster_partition_assignment.csv"] = cluster_assignment_rows(features, assignment)
    return tables


def build_freeze_record(
    *,
    input_sha256: str,
    preview_assignment_sha256: str,
    authoritative_assignment_sha256: str,
    quotas: QuotaTriple,
    independent: Mapping[str, Any],
    output_hashes: Mapping[str, str],
    ref_identity_set_hash: str,
    ref_cluster_set_hash: str,
    eval_identity_set_hash: str,
    eval_cluster_set_hash: str,
    score: ObjectiveScore,
    semantic_mismatches_total: int,
    freeze_date: str = FREEZE_DATE,
    freeze_reason: str = FREEZE_REASON,
) -> dict[str, Any]:
    payload = {
        "contract_id": "s7b_partition_freeze",
        "checkpoint": "CHECKPOINT-3",
        "milestone": "S7B_partition_application_and_freeze",
        "decision_date": freeze_date,
        "freeze_date": freeze_date,
        "freeze_reason": freeze_reason,
        "input_s7a_sha256": input_sha256,
        "assignment_preview_sha256": preview_assignment_sha256,
        "authoritative_assignment_sha256": authoritative_assignment_sha256,
        "preview_application_mismatch_count": semantic_mismatches_total,
        "partition_quotas": {
            "FT": quotas.n_FT,
            "REF": quotas.n_REF,
            "EVAL": quotas.n_EVAL,
        },
        "FT": {
            "clusters": independent["n_FT_clusters"],
            "identities": independent["n_FT"],
            "cores": independent["n_FT_cores"],
            "targets_represented": independent["n_FT_targets"],
            "file_sha256": output_hashes.get("ft.csv", ""),
            "assigned": True,
            "train_validation_split": False,
            "frozen": False,
        },
        "REF": {
            "clusters": independent["n_REF_clusters"],
            "identities": independent["n_REF"],
            "cores": independent["n_REF_cores"],
            "targets_represented": independent["n_REF_targets"],
            "file_sha256": output_hashes.get("ref.csv", ""),
            "semantic_identity_set_hash": ref_identity_set_hash,
            "semantic_cluster_set_hash": ref_cluster_set_hash,
            "frozen": True,
        },
        "EVAL": {
            "clusters": independent["n_EVAL_clusters"],
            "identities": independent["n_EVAL"],
            "cores": independent["n_EVAL_cores"],
            "targets_represented": independent["n_EVAL_targets"],
            "file_sha256": output_hashes.get("eval.csv", ""),
            "semantic_identity_set_hash": eval_identity_set_hash,
            "semantic_cluster_set_hash": eval_cluster_set_hash,
            "frozen": True,
        },
        "corpus_partitioned_sha256": output_hashes.get("corpus_partitioned.csv", ""),
        "objective": score.as_dict(),
        "independence_rule": {
            "no_cluster_may_move_between_ft_ref_eval_to_improve_model_results": True,
            "no_ref_or_eval_identity_may_be_added_or_removed_because_of_fine_tuning": True,
            "no_hyperparameter_or_model_selection_result_may_alter_ref_eval": True,
            "later_scientific_correction_requires_documented_split_revision_new_hashes_and_human_approval": True,
            "s7c_operates_only_inside_ft": True,
        },
        "s7c_started": False,
        "ft_train_validation_split": False,
        "model_fine_tuning_started": False,
        "ref_calibration_started": False,
        "eval_model_evaluation_started": False,
        "sequences_included": False,
    }
    assert_no_sequence_leak(jsonable_dumps(payload), label="s7b_partition_freeze.json")
    return payload


def jsonable_dumps(value: Any) -> str:
    return json_dumps_safe(jsonable(value))


def json_dumps_safe(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def build_application_report(
    *,
    input_sha256: str,
    observed: Mapping[str, int],
    gmm: Mapping[str, Any],
    n_short: int,
    n_long: int,
    selected_quotas: QuotaTriple,
    score: ObjectiveScore,
    family_js: Mapping[str, float],
    tables: Mapping[str, Sequence[Mapping[str, str]]],
    target_diag: Mapping[str, Any],
    integrity: Mapping[str, Any],
    independent: Mapping[str, Any],
    preview_hashes: Mapping[str, str],
    output_hashes: Mapping[str, str],
    parity: Mapping[str, Any],
    n_accepted_swaps: int,
    n_local_search_passes: int,
    local_search_converged: bool,
    greedy_o1: float,
    freeze_date: str,
    ref_identity_set_hash: str,
    eval_identity_set_hash: str,
    determinism_ok: bool,
) -> str:
    identity_rows = list(tables["partition_identity_summary.csv"])
    core_rows = list(tables["partition_core_summary.csv"])
    by_label = {row["partition"]: row for row in identity_rows}
    core_by_label = {row["partition"]: row for row in core_rows}
    known_family_global = space_family_known_share(tables)
    lines = [
        "# S7B partition application and REF/EVAL freeze",
        "",
        "This report records the **authoritative S7B whole-cluster FT/REF/EVAL",
        "assignment** rederived from frozen S7A input with the same tested",
        "optimisation used for the reviewed preview. REF and EVAL are frozen.",
        "FT has been assigned but is **not** split into train/validation.",
        "S7C has not started. No `corpus_final` was written.",
        "",
        "The human approval record is audit-only. Cluster assignment was not",
        "copied from approval metadata or from the preview CSV; it was",
        "rederived and then compared.",
        "",
        "## Frozen S7A input",
        "",
        f"- corpus_post_cap.csv SHA-256 = `{input_sha256}`",
        f"- identities = {observed['n_scientific_identities']}",
        f"- distinct sequence_core = {observed['n_distinct_sequence_core']}",
        f"- clusters = {observed['n_final_clusters']}",
        f"- canonical targets = {observed['n_canonical_targets']}",
        "",
        "## Frozen S6 length-regime provenance",
        "",
        "- assignment_method = `gmm_k2_maximum_posterior`",
        "- GMM source = frozen S6 `bimodality.json` `gmm_2` (not refit on post-cap)",
        f"- component means = {list(gmm['means'])}",
        f"- component weights = {list(gmm['weights'])}",
        f"- post-cap short cores = {n_short}",
        f"- post-cap long cores = {n_long}",
        "",
        "## Authoritative quotas (cluster count, not identity count)",
        "",
        (
            f"- selected = ({selected_quotas.n_FT}, {selected_quotas.n_REF}, "
            f"{selected_quotas.n_EVAL})"
        ),
        "- EVAL therefore contains 13.98% of identities despite 9.95% of clusters",
        "- this follows the approved identity-weighted target objective plus",
        "  whole-cluster constraints; it is not leakage",
        "",
        "| partition | clusters | identities | cores | targets represented |",
        "| --- | --- | --- | --- | --- |",
    ]
    for label in REPORT_PARTITION_ORDER:
        ident = by_label[label]
        core = core_by_label[label]
        lines.append(
            f"| {label} | {ident['n_clusters']} | {ident['n_identities']} | "
            f"{core['n_distinct_cores']} | {ident['n_canonical_targets_represented']} |"
        )
    lines.extend(
        [
            "",
            "## Objective (approved deterministic operationalisation)",
            "",
            "This assignment is the approved deterministic operationalisation of",
            "the CHECKPOINT-3 whole-cluster split. It is not claimed to be a",
            "mathematically unique or globally optimal solution.",
            "",
            "- JSD log base = 2",
            "- weight-free minimax / lexicographic primary objective",
            "- target_family secondary diagnostic only",
            f"- greedy O1 before local search = {format_float(greedy_o1)}",
            f"- accepted pairwise swaps = {n_accepted_swaps}",
            f"- local-search passes = {n_local_search_passes}",
            f"- local-search converged = {local_search_converged}",
            f"- D_target = {format_float(score.d_target)}",
            f"- D_evidence = {format_float(score.d_evidence)}",
            f"- D_length = {format_float(score.d_length)}",
            f"- D_source = {format_float(score.d_source)}",
            f"- O1 = {format_float(score.o1)}",
            f"- descending D vector = {list(score.lex_vector)}",
            f"- O3 = {format_float(score.o3)}",
            "",
            "Target JSD dominates the minimax objective because the 411-target",
            "long tail is much harder to reproduce than evidence or two-regime",
            "length distributions. Source, evidence and length diagnostics were",
            "reviewed and accepted before freeze.",
            "",
            "## Preview / application parity",
            "",
            f"- cluster assignments compared = {parity['cluster_assignments_compared']}",
            f"- cluster assignment mismatches = {parity['cluster_assignment_mismatches']}",
            f"- aggregate/statistical mismatches = {parity['aggregate_statistical_mismatches']}",
            f"- objective mismatches = {parity['objective_mismatches']}",
            f"- semantic mismatches total = {parity['semantic_mismatches_total']}",
            "",
            "## Target representation",
            "",
            f"- targets represented FT/REF/EVAL = "
            f"{target_diag['targets_represented']['FT']} / "
            f"{target_diag['targets_represented']['REF']} / "
            f"{target_diag['targets_represented']['EVAL']}",
            f"- singleton-target identities FT/REF/EVAL = "
            f"{target_diag['singleton_target_identities']['FT']} / "
            f"{target_diag['singleton_target_identities']['REF']} / "
            f"{target_diag['singleton_target_identities']['EVAL']}",
            "",
            "REF contains zero globally singleton-target identities, but still",
            "represents 88 canonical targets across 114 identities. This is a",
            "consequence of the approved identity-weighted target-distribution",
            "objective and whole-cluster constraints, not leakage. No additional",
            "singleton-target balancing constraint was introduced.",
            "",
            "## Secondary target-family diagnostic — not optimisation objective",
            "",
            f"- J_family(FT/REF/EVAL) = {format_float(family_js['FT'])} / "
            f"{format_float(family_js['REF'])} / {format_float(family_js['EVAL'])}",
            f"- D_family (diagnostic) = {format_float(max(family_js.values()))}",
            f"- known-family identity share (global diagnostic) = {known_family_global}",
            "",
            "Clusters were not moved to improve this metric.",
            "",
            "## Integrity / leakage",
            "",
            f"- identities assigned exactly once = {independent['identities_assigned_exactly_once']}",
            f"- clusters assigned exactly once = {independent['clusters_assigned_exactly_once']}",
            f"- cores cross partitions = {independent['cores_cross_partitions']}",
            f"- cluster crossings = {independent['cluster_crossings']}",
            f"- partition blank = {independent['partition_blank']}",
            f"- invalid partition labels = {independent['invalid_partition_labels']}",
            f"- E5 = {independent['E5']}",
            f"- non-protein = {independent['non_protein']}",
            f"- field changes excluding partition = {independent['field_changes_excluding_partition']}",
            f"- determinism_ok = {determinism_ok}",
            "",
            "Frozen S5/S7A `cluster_id` is the leakage boundary. Sequence",
            "clustering was not re-run.",
            "",
            "## REF / EVAL freeze",
            "",
            f"- freeze date = {freeze_date}",
            f"- REF frozen = true; identity-set hash `{ref_identity_set_hash}`",
            f"- EVAL frozen = true; identity-set hash `{eval_identity_set_hash}`",
            "",
            "After this freeze:",
            "",
            "- no cluster may be moved between FT/REF/EVAL to improve model results",
            "- no REF or EVAL identity may be added or removed because of fine-tuning performance",
            "- no hyperparameter or model-selection result may alter REF/EVAL",
            "- any later legitimate scientific correction requires a documented split revision, new hashes, and explicit human approval",
            "- S7C operates only inside FT",
            "",
            "## Boundary",
            "",
            "- S7B authoritative assignment complete = yes",
            "- REF frozen = yes",
            "- EVAL frozen = yes",
            "- FT train/validation split = no",
            "- S7C started = no",
            "- model fine-tuning started = no",
            "- REF calibration started = no",
            "- EVAL model evaluation started = no",
            "",
            "STOP. Do not begin S7C.",
            "",
            "## Preview artefact hashes (preserved, not overwritten)",
            "",
        ]
    )
    for name in sorted(preview_hashes):
        lines.append(f"- `{name}` `{preview_hashes[name]}`")
    lines.extend(["", "## Authoritative output hashes", ""])
    for name in sorted(output_hashes):
        lines.append(f"- `{name}` `{output_hashes[name]}`")
    lines.append("")
    report = "\n".join(lines)
    assert_no_sequence_leak(report, label="s7b_partition_report.md")
    return report


def space_family_known_share(tables: Mapping[str, Sequence[Mapping[str, str]]]) -> str:
    family_rows = list(tables.get("partition_target_family_diagnostic.csv", []))
    known = 0
    total = 0
    for row in family_rows:
        n = int(row["n_global"])
        total += n
        if row["target_family"] != UNKNOWN_FAMILY:
            known += n
    return format_fraction(known, total) if total else ""


def jsonable(value: Any) -> Any:
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, QuotaTriple):
        return {
            "n_FT": value.n_FT,
            "n_REF": value.n_REF,
            "n_EVAL": value.n_EVAL,
            "sse": str(value.sse),
        }
    if isinstance(value, ObjectiveScore):
        return value.as_dict()
    if isinstance(value, ClusterFeature):
        return {
            "cluster_id": value.cluster_id,
            "n_identities": value.n_identities,
            "n_cores": value.n_cores,
            "n_distinct_targets": value.n_distinct_targets,
            "n_distinct_sources": value.n_distinct_sources,
            "multi_target": value.multi_target,
            "multi_source": value.multi_source,
        }
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(jsonable(item) for item in value)
    return value


__all__ = [
    "ABSDEV_COMPARISON_TUPLE_FIELDS",
    "APPLY_MODE",
    "CLUSTER_ASSIGNMENT_COLUMNS",
    "COMPARISON_TUPLE_FIELDS",
    "ClusterFeature",
    "DEFAULT_FRACTIONS",
    "DEFAULT_OBJECTIVE_PROFILE",
    "FREEZE_DATE",
    "FREEZE_REASON",
    "FeatureSpace",
    "JSD_LOG_BASE",
    "OBJECTIVE_PROFILE_ABSDEV",
    "OBJECTIVE_PROFILE_JSD",
    "ObjectiveScore",
    "PREVIEW_MODE",
    "PRIMARY_CRITERIA",
    "QuotaTriple",
    "S7PartitionError",
    "apply_assignment_to_identities",
    "approval_parity_mismatches",
    "assign_length_regimes",
    "assignment_from_partitioned_rows",
    "assignment_signature",
    "build_application_report",
    "build_application_tables",
    "build_cluster_features",
    "build_freeze_record",
    "build_preview_report",
    "build_preview_tables",
    "cluster_assignment_rows",
    "cluster_processing_order",
    "derive_integer_quotas",
    "enforce_application_config",
    "evaluate_random_baselines",
    "family_jsd_by_partition",
    "greedy_assign",
    "independent_distribution_counts",
    "independent_partition_invariants",
    "input_unmutated",
    "integrity_gates",
    "js_divergence",
    "load_frozen_s6_gmm",
    "max_abs_proportion_deviation",
    "optimise_partition",
    "pairwise_local_search",
    "partition_subset_rows",
    "populate_partition_on_corpus",
    "preview_application_parity_mismatches",
    "random_whole_cluster_assignment",
    "resolve_objective_profile",
    "score_assignment",
    "score_partition_states",
    "select_preview_assignment",
    "semantic_cluster_set_hash",
    "semantic_identity_set_hash",
    "states_from_assignment",
    "target_representation_diagnostics",
    "verify_frozen_identities",
    "worst_abs_deviation_category",
]

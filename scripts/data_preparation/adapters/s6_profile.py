"""GLOBAL S6 — pre-balancing corpus profile (read-only).

Profiles the frozen final S5 clustered corpus. Does not balance, apply
a target cap, assign FT/REF/EVAL, populate ``partition``, drop rows, or
begin S7. Exact S7 cluster-retention semantics are not specified in the
current v1.4 plan or code; candidate-cap analysis is diagnostic only.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from adapters.s4_scientific_common import (
    ScientificProposalError,
    split_pipe,
)
from adapters.s5_exact_dedup import (
    DEFAULT_OVERLAP_SOURCES,
    _blank,
    join_sorted_unique,
)
from adapters.s5_final_clustering import MERGE_MMSEQS_PLUS_ENA
from adapters.target_extraction_common import SEQ_LEAK_RE

S6ProfileError = ScientificProposalError

CANDIDATE_FRACTIONS: tuple[float, ...] = (0.02, 0.03, 0.05, 0.10)
PLAN_DEFAULT_FRACTION = 0.05
LENGTH_OUTLIER_NT = 100
EMERGENCY_CLUSTER_TRIGGER = 500
TOP_N_TARGETS = 30
GC_BASES = frozenset({"G", "C"})
NT_BASES = ("A", "U", "C", "G", "T")
EVIDENCE_ORDER = ("E1", "E2", "E3", "E4", "E5")

FORBIDDEN_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "apply_target_cap",
        "balancing",
        "create_corpus_final",
        "ft_ref_eval",
        "ft_ref_eval_assignment",
        "populate_partition",
        "select_final_max_target_fraction",
        "start_s7",
        "train_validation_split",
        "train_validation_test_split",
    }
)

FROZEN_S5_OUTPUT_NAMES: frozenset[str] = frozenset(
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
    }
)

CHECKPOINT3_DECISION_COLUMNS: tuple[str, ...] = (
    "decision_id",
    "title",
    "question",
    "why_it_matters",
    "relevant_data",
    "options",
    "current_plan_context",
    "corpus_size_or_diversity_effect",
    "human_decision",
    "human_notes",
    "status",
)

HUMAN_CHECKPOINT_FIELDS: tuple[str, ...] = ("human_decision", "human_notes")

TARGET_PROFILE_COLUMNS: tuple[str, ...] = (
    "canonical_target_name",
    "n_scientific_identities",
    "n_distinct_sequence_core",
    "n_clusters",
    "pct_identities",
    "pct_clusters",
    "target_family",
    "target_uniprot",
    "contributing_sources",
    "n_contributing_sources",
)

FAMILY_PROFILE_COLUMNS: tuple[str, ...] = (
    "target_family",
    "n_scientific_identities",
    "n_distinct_sequence_core",
    "n_clusters",
    "n_canonical_targets",
    "pct_identities",
    "pct_clusters",
)

PFAM_PROFILE_COLUMNS: tuple[str, ...] = (
    "group_kind",
    "group_id",
    "n_scientific_identities",
    "n_canonical_targets",
    "n_clusters",
)

SPARSE_TARGET_COLUMNS: tuple[str, ...] = (
    "canonical_target_name",
    "n_scientific_identities",
    "n_clusters",
    "n_distinct_sequence_core",
    "target_family",
    "sparse_class",
)

CAP_IMPACT_COLUMNS: tuple[str, ...] = (
    "max_target_fraction",
    "n_identities_denominator",
    "nominal_identity_threshold",
    "threshold_definition",
    "n_targets_above_threshold",
    "n_identities_from_overrepresented_targets",
    "raw_identity_excess",
    "n_clusters_touching_overrepresented_targets",
    "n_shared_clusters_among_those",
    "idealised_recordwise_capped_corpus_size",
    "idealised_recordwise_identities_removed",
    "cluster_union_upper_bound_identities_removed",
    "cluster_union_upper_bound_remaining_identities",
    "exclusive_clusters_can_absorb_all_excess",
    "s7_cluster_selection_specified",
    "note",
)

CAP_TARGET_COLUMNS: tuple[str, ...] = (
    "max_target_fraction",
    "canonical_target_name",
    "n_scientific_identities",
    "nominal_identity_threshold",
    "identity_excess",
    "n_clusters",
    "n_shared_clusters",
    "cluster_identity_sizes",
    "n_exclusive_clusters",
    "exclusive_cluster_identities",
)

LENGTH_PROFILE_COLUMNS: tuple[str, ...] = (
    "sequence_field",
    "stratum_kind",
    "stratum_value",
    "n",
    "min",
    "p05",
    "p25",
    "median",
    "mean",
    "p75",
    "p95",
    "max",
)

COMPOSITION_COLUMNS: tuple[str, ...] = (
    "weighting",
    "stratum_kind",
    "stratum_value",
    "n_sequences",
    "n_nucleotides",
    "frac_A",
    "frac_U",
    "frac_C",
    "frac_G",
    "frac_T",
    "frac_other",
    "gc_mean",
    "gc_median",
    "gc_p05",
    "gc_p25",
    "gc_p75",
    "gc_p95",
    "gc_min",
    "gc_max",
)

CLUSTER_PROFILE_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "n_distinct_sequence_core",
    "n_scientific_identities",
    "n_canonical_targets",
    "canonical_targets",
    "contributing_sources",
    "merge_basis",
    "ena_provenance_present",
    "is_singleton_core",
)

SOURCE_PROFILE_COLUMNS: tuple[str, ...] = (
    "source_db",
    "n_identities_donor",
    "pct_identities_donor",
    "n_identities_contributing",
    "n_identities_unique_attestation",
    "n_cores_unique_attestation",
)

EVIDENCE_PROFILE_COLUMNS: tuple[str, ...] = (
    "evidence_level",
    "n_scientific_identities",
    "pct_identities",
)

LICENSING_COLUMNS: tuple[str, ...] = (
    "redistribution_status",
    "n_scientific_identities",
    "pct_identities",
)

SOURCE_REGIME_COLUMNS: tuple[str, ...] = (
    "source_db",
    "n_distinct_cores",
    "median_length_nt",
    "n_shorter_regime",
    "n_longer_regime",
    "pct_shorter_regime",
    "pct_longer_regime",
    "assignment_method",
)

CORE_FULL_COMPARISON_COLUMNS: tuple[str, ...] = (
    "n_identities",
    "n_same_length",
    "pct_same_length",
    "median_core_nt",
    "median_full_nt",
    "median_full_minus_core_nt",
    "mean_full_minus_core_nt",
)

GMM_POSTERIOR_ASSIGNMENT_METHOD = "gmm_k2_maximum_posterior"

S7_UNSPECIFIED_ITEMS: tuple[str, ...] = (
    "denominator_definition",
    "floor_or_ceiling_rule",
    "which_whole_clusters_are_retained_or_removed",
    "treatment_of_clusters_containing_multiple_targets",
    "ordering_and_tie_breaking",
    "whether_removing_a_cluster_for_one_dominant_target_may_remove_identities_belonging_to_other_targets",
)


def present(value: Any) -> bool:
    return bool(_blank(value))


def as_int(value: Any, default: int = 0) -> int:
    text = _blank(value)
    if not text:
        return default
    return int(text)


def as_float(value: Any) -> float | None:
    text = _blank(value)
    if not text:
        return None
    return float(text)


def fmt_float(value: float | None, digits: int = 6) -> str:
    if value is None:
        return ""
    return f"{float(value):.{digits}f}"


def fmt_pct(numerator: int, denominator: int, digits: int = 2) -> str:
    if denominator == 0:
        return ""
    return f"{(100.0 * numerator / denominator):.{digits}f}"


def percentile_bundle(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {
            "n": 0.0,
            "min": 0.0,
            "p05": 0.0,
            "p25": 0.0,
            "median": 0.0,
            "mean": 0.0,
            "p75": 0.0,
            "p95": 0.0,
            "max": 0.0,
        }
    arr = np.sort(np.asarray(list(values), dtype=float))
    return {
        "n": float(arr.size),
        "min": float(np.min(arr)),
        "p05": float(np.percentile(arr, 5, method="linear")),
        "p25": float(np.percentile(arr, 25, method="linear")),
        "median": float(np.percentile(arr, 50, method="linear")),
        "mean": float(np.mean(arr)),
        "p75": float(np.percentile(arr, 75, method="linear")),
        "p95": float(np.percentile(arr, 95, method="linear")),
        "max": float(np.max(arr)),
    }


def gini_coefficient(counts: Sequence[int]) -> float:
    """Gini coefficient of a non-negative count vector.

    For sorted ``x_1 <= ... <= x_k``::

        G = 2 * sum(i * x_i) / (k * sum(x)) - (k + 1) / k

    ``G = 0`` is equality; ``G`` approaches 1 as concentration increases.
    """
    arr = np.asarray([int(v) for v in counts], dtype=float)
    if arr.size == 0:
        return 0.0
    total = float(arr.sum())
    if total <= 0:
        return 0.0
    ordered = np.sort(arr)
    n = float(ordered.size)
    idx = np.arange(1, ordered.size + 1, dtype=float)
    return float((2.0 * np.sum(idx * ordered) / (n * total)) - (n + 1.0) / n)


def shannon_entropy(counts: Sequence[int]) -> dict[str, float]:
    """Shannon entropy of a count vector using natural log (nats).

    ``H = -sum p_i ln p_i``, ``H_norm = H / ln(k)`` for ``k`` categories
    with ``k > 1``, and ``N_eff = exp(H)`` (effective number of categories).
    """
    arr = np.asarray([int(v) for v in counts], dtype=float)
    total = float(arr.sum())
    k = int(arr.size)
    if total <= 0 or k == 0:
        return {"shannon_nats": 0.0, "shannon_normalised": 0.0, "n_effective": 0.0, "n_categories": float(k)}
    probs = arr[arr > 0] / total
    entropy = float(-np.sum(probs * np.log(probs)))
    normalised = float(entropy / math.log(k)) if k > 1 else 0.0
    return {
        "shannon_nats": entropy,
        "shannon_normalised": normalised,
        "n_effective": float(math.exp(entropy)),
        "n_categories": float(k),
    }


def _gaussian_logpdf(x: np.ndarray, mean: float, var: float) -> np.ndarray:
    var = max(float(var), 1e-12)
    return -0.5 * (math.log(2.0 * math.pi * var) + (x - mean) ** 2 / var)


def fit_univariate_gmm(
    values: Sequence[float],
    *,
    n_components: int,
    max_iter: int = 200,
    tol: float = 1e-8,
) -> dict[str, Any]:
    """Deterministic 1-D Gaussian-mixture EM.

    This is a model-comparison diagnostic, not a proof of bimodality.
    Parameter count: K=1 uses mean+variance (2); K=2 uses two means, two
    variances, and one free weight (5).
    """
    arr = np.asarray(list(values), dtype=float)
    n = int(arr.size)
    if n == 0:
        raise S6ProfileError("GMM requires a non-empty sample")
    if n_components == 1:
        mean = float(np.mean(arr))
        var = float(np.var(arr, ddof=0))
        loglik = float(np.sum(_gaussian_logpdf(arr, mean, var)))
        n_params = 2
        bic = float(-2.0 * loglik + n_params * math.log(n))
        return {
            "n_components": 1,
            "means": [mean],
            "variances": [var],
            "weights": [1.0],
            "log_likelihood": loglik,
            "n_params": n_params,
            "bic": bic,
            "n_iter": 0,
        }
    if n_components != 2:
        raise S6ProfileError("S6 GMM diagnostic supports only 1 or 2 components")
    q1, q2 = np.quantile(arr, [1.0 / 3.0, 2.0 / 3.0])
    means = np.array([float(q1), float(q2)], dtype=float)
    if means[0] == means[1]:
        spread = float(np.std(arr, ddof=0)) or 1.0
        means[1] = means[0] + spread
    global_var = float(np.var(arr, ddof=0)) or 1.0
    variances = np.array([global_var, global_var], dtype=float)
    weights = np.array([0.5, 0.5], dtype=float)
    prev_loglik = -math.inf
    n_iter = 0
    loglik = -math.inf
    for n_iter in range(1, max_iter + 1):
        log_resp = np.stack(
            [
                math.log(max(weights[k], 1e-12)) + _gaussian_logpdf(arr, float(means[k]), float(variances[k]))
                for k in range(2)
            ],
            axis=1,
        )
        max_log = np.max(log_resp, axis=1, keepdims=True)
        resp = np.exp(log_resp - max_log)
        resp_sum = resp.sum(axis=1, keepdims=True)
        resp = resp / np.clip(resp_sum, 1e-12, None)
        loglik = float(np.sum(max_log.squeeze() + np.log(np.clip(resp_sum.squeeze(), 1e-12, None))))
        nk = resp.sum(axis=0)
        weights = nk / n
        for k in range(2):
            mass = float(nk[k])
            if mass <= 1e-8:
                continue
            means[k] = float(np.sum(resp[:, k] * arr) / mass)
            variances[k] = float(np.sum(resp[:, k] * (arr - means[k]) ** 2) / mass)
        if abs(loglik - prev_loglik) < tol:
            break
        prev_loglik = loglik
    n_params = 5
    bic = float(-2.0 * loglik + n_params * math.log(n))
    order = np.argsort(means)
    return {
        "n_components": 2,
        "means": [float(means[i]) for i in order],
        "variances": [float(variances[i]) for i in order],
        "weights": [float(weights[i]) for i in order],
        "log_likelihood": loglik,
        "n_params": n_params,
        "bic": bic,
        "n_iter": n_iter,
    }


def gmm_component_posteriors(
    values: Sequence[float],
    gmm: Mapping[str, Any],
) -> np.ndarray:
    """Return the posterior matrix (n_samples, n_components) for a fitted GMM.

    Fitted two-component means are stored in ascending order, so column 0 is
    the shorter-length regime and column 1 is the longer-length regime.
    """
    arr = np.asarray(list(values), dtype=float)
    means = [float(v) for v in gmm["means"]]
    variances = [float(v) for v in gmm["variances"]]
    weights = [float(v) for v in gmm["weights"]]
    if arr.size == 0:
        return np.zeros((0, len(means)), dtype=float)
    log_resp = np.stack(
        [
            math.log(max(weights[k], 1e-12))
            + _gaussian_logpdf(arr, means[k], variances[k])
            for k in range(len(means))
        ],
        axis=1,
    )
    max_log = np.max(log_resp, axis=1, keepdims=True)
    resp = np.exp(log_resp - max_log)
    resp = resp / np.clip(resp.sum(axis=1, keepdims=True), 1e-12, None)
    return resp


def gmm_posterior_assignment(
    values: Sequence[float],
    gmm: Mapping[str, Any],
) -> np.ndarray:
    """Assign each value to the GMM component with the greatest posterior.

    Exact posterior ties are assigned to the lower component index (the
    shorter-length regime for the sorted two-component length GMM) because
    ``numpy.argmax`` returns the first maximum.
    """
    posteriors = gmm_component_posteriors(values, gmm)
    if posteriors.size == 0:
        return np.zeros((0,), dtype=int)
    return np.argmax(posteriors, axis=1)


def build_source_length_regime_summary(
    core_items: Sequence[tuple[str, Mapping[str, str]]],
    gmm2: Mapping[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Assign distinct cores to the shorter/longer GMM regimes by donor source."""
    lengths = [length_of(row, "sequence_core") for _, row in core_items]
    assignments = gmm_posterior_assignment(lengths, gmm2)
    by_source: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"lengths": [], "short": 0, "long": 0}
    )
    n_short = 0
    n_long = 0
    for (_core, row), length, assign in zip(core_items, lengths, assignments):
        source = _blank(row.get("source_db")) or "(blank)"
        by_source[source]["lengths"].append(int(length))
        if int(assign) == 0:
            by_source[source]["short"] += 1
            n_short += 1
        else:
            by_source[source]["long"] += 1
            n_long += 1

    def _row(source: str, lengths_in: Sequence[int], n_shorter: int, n_longer: int) -> dict[str, str]:
        n = len(lengths_in)
        median = float(np.median(np.asarray(lengths_in, dtype=float))) if n else 0.0
        return {
            "source_db": source,
            "n_distinct_cores": str(n),
            "median_length_nt": fmt_float(median, 1),
            "n_shorter_regime": str(n_shorter),
            "n_longer_regime": str(n_longer),
            "pct_shorter_regime": fmt_pct(n_shorter, n) if n else "",
            "pct_longer_regime": fmt_pct(n_longer, n) if n else "",
            "assignment_method": GMM_POSTERIOR_ASSIGNMENT_METHOD,
        }

    rows = [
        _row(source, by_source[source]["lengths"], by_source[source]["short"], by_source[source]["long"])
        for source in sorted(by_source)
    ]
    overall = _row("all", lengths, n_short, n_long)
    return [overall, *rows], {
        "method": (
            "Each distinct sequence core is assigned to the two-component length "
            "GMM component with the higher posterior probability. Component 0 is "
            "the shorter-mean regime. Exact posterior ties are assigned to the "
            "shorter regime."
        ),
        "assignment_method": GMM_POSTERIOR_ASSIGNMENT_METHOD,
        "n_distinct_cores": len(lengths),
        "n_shorter": n_short,
        "n_longer": n_long,
        "component_means": [float(v) for v in gmm2["means"]],
        "component_weights": [float(v) for v in gmm2["weights"]],
    }


def build_core_full_comparison(
    corpus_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Identity-grain comparison of core vs full-construct lengths."""
    ordered = sorted(
        corpus_rows, key=lambda item: _blank(item.get("scientific_identity_id"))
    )
    core_lengths = [length_of(row, "sequence_core") for row in ordered]
    full_lengths = [length_of(row, "sequence_full") for row in ordered]
    n = len(ordered)
    n_same = sum(core == full for core, full in zip(core_lengths, full_lengths))
    deltas = [full - core for core, full in zip(core_lengths, full_lengths)]
    return {
        "n_identities": n,
        "n_same_length": n_same,
        "pct_same_length": (n_same / n) if n else 0.0,
        "median_core_nt": float(np.median(core_lengths)) if core_lengths else 0.0,
        "median_full_nt": float(np.median(full_lengths)) if full_lengths else 0.0,
        "median_full_minus_core_nt": float(np.median(deltas)) if deltas else 0.0,
        "mean_full_minus_core_nt": float(np.mean(deltas)) if deltas else 0.0,
        "identity_core_lengths": core_lengths,
        "identity_full_lengths": full_lengths,
    }


def classify_bimodality(gmm1: Mapping[str, Any], gmm2: Mapping[str, Any]) -> dict[str, Any]:
    """Cautious 1- vs 2-component GMM interpretation."""
    delta_bic = float(gmm1["bic"]) - float(gmm2["bic"])
    means = list(gmm2["means"])
    weights = list(gmm2["weights"])
    sep = abs(means[1] - means[0]) if len(means) == 2 else 0.0
    min_weight = min(weights) if weights else 0.0
    prefers_two = delta_bic > 6.0
    well_separated = sep >= 10.0
    both_used = min_weight >= 0.10
    if prefers_two and well_separated and both_used:
        conclusion = "evidence_of_material_bimodality"
    elif prefers_two or (sep >= 8.0 and min_weight >= 0.05):
        conclusion = "weak_evidence"
    else:
        conclusion = "no_material_evidence"
    return {
        "bic_1": float(gmm1["bic"]),
        "bic_2": float(gmm2["bic"]),
        "delta_bic_1_minus_2": delta_bic,
        "component_means": means,
        "component_weights": weights,
        "mean_separation": sep,
        "min_component_weight": min_weight,
        "conclusion": conclusion,
        "caveat": (
            "A lower BIC for two components means a two-Gaussian mixture describes "
            "the empirical length sample better; it is not mathematical proof of bimodality."
        ),
    }


def sequence_composition(sequences: Sequence[str]) -> dict[str, Any]:
    counts = Counter()
    gc_fractions: list[float] = []
    n_nt = 0
    for raw in sequences:
        seq = _blank(raw).upper()
        if not seq:
            continue
        n_nt += len(seq)
        local = Counter(seq)
        counts.update(local)
        gc = sum(local[base] for base in GC_BASES)
        gc_fractions.append(gc / len(seq))
    def frac(base: str) -> float:
        return (counts[base] / n_nt) if n_nt else 0.0
    known = sum(counts[base] for base in NT_BASES)
    gc_stats = percentile_bundle(gc_fractions)
    return {
        "n_sequences": len(sequences),
        "n_nucleotides": n_nt,
        "frac_A": frac("A"),
        "frac_U": frac("U"),
        "frac_C": frac("C"),
        "frac_G": frac("G"),
        "frac_T": frac("T"),
        "frac_other": ((n_nt - known) / n_nt) if n_nt else 0.0,
        "gc": gc_stats,
        "letter_counts": {base: int(counts[base]) for base in NT_BASES},
    }


def canonical_core_rows(corpus_rows: Sequence[Mapping[str, str]]) -> dict[str, Mapping[str, str]]:
    """One identity per distinct core, chosen by smallest scientific_identity_id."""
    chosen: dict[str, Mapping[str, str]] = {}
    for row in corpus_rows:
        core = _blank(row.get("sequence_core"))
        prev = chosen.get(core)
        identity = _blank(row.get("scientific_identity_id"))
        if prev is None or identity < _blank(prev.get("scientific_identity_id")):
            chosen[core] = row
    return chosen


def contributing_sources_of(row: Mapping[str, str]) -> list[str]:
    sources = split_pipe(row.get("contributing_sources", ""))
    if sources:
        return sources
    donor = _blank(row.get("source_db"))
    return [donor] if donor else []


def length_of(row: Mapping[str, str], field: str) -> int:
    if field == "sequence_core":
        stored = as_int(row.get("sequence_length_core"), default=0)
        return stored or len(_blank(row.get("sequence_core")))
    stored = as_int(row.get("sequence_length_full"), default=0)
    return stored or len(_blank(row.get("sequence_full")))


def enforce_authorised_config(config: Mapping[str, Any]) -> None:
    forbidden = sorted(FORBIDDEN_CONFIG_KEYS.intersection(config))
    if forbidden:
        raise S6ProfileError(f"S6 config contains forbidden keys: {forbidden}")
    does_not = {str(item) for item in config.get("does_not", [])}
    required = {
        "balancing",
        "apply_target_cap",
        "select_final_max_target_fraction",
        "populate_partition",
        "assign_ft_ref_eval",
        "start_s7",
    }
    missing = sorted(required - does_not)
    if missing:
        raise S6ProfileError(f"S6 config.does_not missing required exclusions: {missing}")


def assert_not_frozen_s5_path(path: Any) -> None:
    name = getattr(path, "name", str(path).rsplit("/", 1)[-1])
    if name in FROZEN_S5_OUTPUT_NAMES:
        raise S6ProfileError(f"S6 must not write frozen S5 artefact {name}")


def assert_no_sequence_leak(text: str, *, label: str) -> None:
    if SEQ_LEAK_RE.search(text or ""):
        raise S6ProfileError(f"{label} must not contain biological sequence strings")


def max_allowed_identities(n_identities: int, fraction: float) -> int:
    """Largest integer count with count / n_identities <= fraction."""
    if n_identities <= 0:
        return 0
    return int(math.floor(fraction * n_identities + 1e-12))


def validate_s6_inputs(
    corpus_rows: Sequence[Mapping[str, str]],
    *,
    cluster_summary_rows: Sequence[Mapping[str, str]],
    clusters_final_rows: Sequence[Mapping[str, str]] | None = None,
    expected_counts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    identities = [_blank(row.get("scientific_identity_id")) for row in corpus_rows]
    n_missing_id = sum(1 for item in identities if not item)
    n_dup_id = len(identities) - len(set(identities))
    if n_missing_id:
        errors.append(f"missing scientific_identity_id = {n_missing_id}")
    if n_dup_id:
        errors.append(f"duplicate scientific_identity_id = {n_dup_id}")
    cluster_ids = [_blank(row.get("cluster_id")) for row in corpus_rows]
    n_missing_cluster = sum(1 for item in cluster_ids if not item)
    if n_missing_cluster:
        errors.append(f"missing final cluster_id = {n_missing_cluster}")
    n_identities = len(corpus_rows)
    n_cores = len({_blank(row.get("sequence_core")) for row in corpus_rows})
    n_clusters = len({item for item in cluster_ids if item})
    reps = [_blank(row.get("scientific_identity_id")) for row in corpus_rows if row.get("is_cluster_representative") == "true"]
    n_without_rep = 0
    n_multi_rep = 0
    by_cluster: dict[str, list[str]] = defaultdict(list)
    for row in corpus_rows:
        if row.get("is_cluster_representative") == "true":
            by_cluster[_blank(row.get("cluster_id"))].append(_blank(row.get("scientific_identity_id")))
    for cluster_id in {item for item in cluster_ids if item}:
        n_rep = len(by_cluster.get(cluster_id, []))
        if n_rep == 0:
            n_without_rep += 1
        elif n_rep > 1:
            n_multi_rep += 1
    if n_without_rep:
        errors.append(f"clusters without representative = {n_without_rep}")
    if n_multi_rep:
        errors.append(f"clusters with >1 representative = {n_multi_rep}")
    n_partition = sum(1 for row in corpus_rows if present(row.get("partition")))
    if n_partition:
        errors.append(f"partition is populated for {n_partition} identities")
    if expected_counts:
        expected_map = {
            "n_scientific_identities": n_identities,
            "n_distinct_sequence_core": n_cores,
            "n_final_clusters": n_clusters,
            "n_missing_scientific_identity_id": n_missing_id,
            "n_duplicate_scientific_identity_id": n_dup_id,
            "n_missing_cluster_id": n_missing_cluster,
            "n_clusters_without_representative": n_without_rep,
            "n_clusters_with_gt1_representative": n_multi_rep,
        }
        for key, observed in expected_map.items():
            if key in expected_counts and observed != expected_counts[key]:
                errors.append(f"{key}: expected {expected_counts[key]}, got {observed}")
    if cluster_summary_rows and len(cluster_summary_rows) != n_clusters:
        errors.append(
            f"cluster_summary_final rows = {len(cluster_summary_rows)} != n_clusters {n_clusters}"
        )
    if clusters_final_rows is not None and len(clusters_final_rows) != n_cores:
        errors.append(
            f"clusters_final.tsv rows = {len(clusters_final_rows)} != n_distinct_sequence_core {n_cores}"
        )
    if errors:
        raise S6ProfileError("S6 input validation failed: " + "; ".join(errors))
    return {
        "n_scientific_identities": n_identities,
        "n_distinct_sequence_core": n_cores,
        "n_final_clusters": n_clusters,
        "n_missing_scientific_identity_id": n_missing_id,
        "n_duplicate_scientific_identity_id": n_dup_id,
        "n_missing_cluster_id": n_missing_cluster,
        "n_clusters_without_representative": n_without_rep,
        "n_clusters_with_gt1_representative": n_multi_rep,
        "n_representatives": len(reps),
        "n_partition_populated": n_partition,
    }


def _token_or_blank(value: Any, *, blank_label: str = "") -> str:
    text = _blank(value)
    return text if text else blank_label


def _family_label(row: Mapping[str, str]) -> str:
    return _token_or_blank(row.get("target_family"), blank_label="(blank)")


def build_target_profile(
    corpus_rows: Sequence[Mapping[str, str]],
    *,
    n_identities: int,
    n_clusters: int,
) -> list[dict[str, str]]:
    by_target: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in corpus_rows:
        by_target[_blank(row.get("canonical_target_name"))].append(row)
    out: list[dict[str, str]] = []
    for name, rows in by_target.items():
        cores = {_blank(row.get("sequence_core")) for row in rows}
        clusters = {_blank(row.get("cluster_id")) for row in rows}
        sources: set[str] = set()
        families = {_family_label(row) for row in rows}
        uniprots = {_blank(row.get("target_uniprot")) for row in rows if present(row.get("target_uniprot"))}
        for row in rows:
            sources.update(contributing_sources_of(row))
        n_id = len(rows)
        n_cl = len(clusters)
        out.append(
            {
                "canonical_target_name": name,
                "n_scientific_identities": str(n_id),
                "n_distinct_sequence_core": str(len(cores)),
                "n_clusters": str(n_cl),
                "pct_identities": fmt_pct(n_id, n_identities),
                "pct_clusters": fmt_pct(n_cl, n_clusters),
                "target_family": join_sorted_unique(families),
                "target_uniprot": join_sorted_unique(uniprots),
                "contributing_sources": join_sorted_unique(sources),
                "n_contributing_sources": str(len(sources)),
            }
        )
    out.sort(
        key=lambda row: (-int(row["n_scientific_identities"]), row["canonical_target_name"])
    )
    return out


def build_family_profile(
    corpus_rows: Sequence[Mapping[str, str]],
    *,
    n_identities: int,
    n_clusters: int,
) -> list[dict[str, str]]:
    by_family: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in corpus_rows:
        by_family[_family_label(row)].append(row)
    out: list[dict[str, str]] = []
    for family, rows in by_family.items():
        n_id = len(rows)
        n_core = len({_blank(row.get("sequence_core")) for row in rows})
        n_cl = len({_blank(row.get("cluster_id")) for row in rows})
        n_tg = len({_blank(row.get("canonical_target_name")) for row in rows})
        out.append(
            {
                "target_family": family,
                "n_scientific_identities": str(n_id),
                "n_distinct_sequence_core": str(n_core),
                "n_clusters": str(n_cl),
                "n_canonical_targets": str(n_tg),
                "pct_identities": fmt_pct(n_id, n_identities),
                "pct_clusters": fmt_pct(n_cl, n_clusters),
            }
        )
    out.sort(
        key=lambda row: (-int(row["n_scientific_identities"]), row["target_family"])
    )
    return out


def build_group_profile(
    corpus_rows: Sequence[Mapping[str, str]],
    field: str,
    *,
    kind: str,
) -> list[dict[str, str]]:
    by_group: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in corpus_rows:
        tokens = split_pipe(row.get(field, ""))
        if not tokens:
            continue
        for token in tokens:
            by_group[token].append(row)
    out: list[dict[str, str]] = []
    for group_id, rows in by_group.items():
        out.append(
            {
                "group_kind": kind,
                "group_id": group_id,
                "n_scientific_identities": str(len({_blank(r.get("scientific_identity_id")) for r in rows})),
                "n_canonical_targets": str(len({_blank(r.get("canonical_target_name")) for r in rows})),
                "n_clusters": str(len({_blank(r.get("cluster_id")) for r in rows})),
            }
        )
    out.sort(key=lambda row: (-int(row["n_scientific_identities"]), row["group_id"]))
    return out


def build_sparse_targets(target_rows: Sequence[Mapping[str, str]]) -> tuple[list[dict[str, str]], dict[str, int]]:
    one_identity = 0
    one_cluster = 0
    one_identity_one_cluster = 0
    redundant = 0
    rows: list[dict[str, str]] = []
    for row in target_rows:
        n_id = int(row["n_scientific_identities"])
        n_cl = int(row["n_clusters"])
        flags: list[str] = []
        if n_id == 1:
            one_identity += 1
            flags.append("one_identity")
        if n_cl == 1:
            one_cluster += 1
            flags.append("one_cluster")
        if n_id == 1 and n_cl == 1:
            one_identity_one_cluster += 1
            flags.append("one_identity_one_cluster")
        if n_id >= 5 and n_cl == 1:
            redundant += 1
            flags.append("ge5_identities_one_cluster")
        if not flags:
            continue
        rows.append(
            {
                "canonical_target_name": row["canonical_target_name"],
                "n_scientific_identities": row["n_scientific_identities"],
                "n_clusters": row["n_clusters"],
                "n_distinct_sequence_core": row["n_distinct_sequence_core"],
                "target_family": row["target_family"],
                "sparse_class": join_sorted_unique(flags),
            }
        )
    rows.sort(key=lambda row: (-int(row["n_scientific_identities"]), row["canonical_target_name"]))
    return rows, {
        "n_targets_one_identity": one_identity,
        "n_targets_one_cluster": one_cluster,
        "n_targets_one_identity_one_cluster": one_identity_one_cluster,
        "n_targets_ge5_identities_one_cluster": redundant,
    }


def _cluster_identity_index(
    corpus_rows: Sequence[Mapping[str, str]],
) -> dict[str, list[Mapping[str, str]]]:
    by_cluster: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in corpus_rows:
        by_cluster[_blank(row.get("cluster_id"))].append(row)
    return by_cluster


def build_candidate_cap_analysis(
    corpus_rows: Sequence[Mapping[str, str]],
    target_rows: Sequence[Mapping[str, str]],
    *,
    fractions: Sequence[float] = CANDIDATE_FRACTIONS,
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    n_identities = len(corpus_rows)
    by_cluster = _cluster_identity_index(corpus_rows)
    target_to_clusters: dict[str, set[str]] = defaultdict(set)
    cluster_targets: dict[str, set[str]] = defaultdict(set)
    cluster_n_identities = {cid: len(rows) for cid, rows in by_cluster.items()}
    target_cluster_identity_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in corpus_rows:
        target = _blank(row.get("canonical_target_name"))
        cluster_id = _blank(row.get("cluster_id"))
        target_to_clusters[target].add(cluster_id)
        cluster_targets[cluster_id].add(target)
        target_cluster_identity_counts[target][cluster_id] += 1
    impact_rows: list[dict[str, str]] = []
    detail_rows: list[dict[str, str]] = []
    for fraction in fractions:
        threshold = max_allowed_identities(n_identities, fraction)
        over: list[Mapping[str, str]] = [
            row
            for row in target_rows
            if int(row["n_scientific_identities"]) > threshold
        ]
        over_names = [row["canonical_target_name"] for row in over]
        excess = sum(int(row["n_scientific_identities"]) - threshold for row in over)
        over_identities = sum(int(row["n_scientific_identities"]) for row in over)
        touching: set[str] = set()
        for name in over_names:
            touching.update(target_to_clusters[name])
        shared = 0
        for cluster_id in touching:
            if len(cluster_targets[cluster_id]) > 1:
                shared += 1
        union_identities = sum(cluster_n_identities[cid] for cid in touching)
        exclusive_ok = True
        for name in over_names:
            identity_count = int(
                next(row["n_scientific_identities"] for row in over if row["canonical_target_name"] == name)
            )
            needed = identity_count - threshold
            exclusive_ids = 0
            n_exclusive = 0
            sizes: list[int] = []
            for cluster_id, n_here in sorted(target_cluster_identity_counts[name].items()):
                sizes.append(n_here)
                if len(cluster_targets[cluster_id]) == 1:
                    exclusive_ids += n_here
                    n_exclusive += 1
            if exclusive_ids < needed:
                exclusive_ok = False
            detail_rows.append(
                {
                    "max_target_fraction": fmt_float(fraction, 2),
                    "canonical_target_name": name,
                    "n_scientific_identities": str(identity_count),
                    "nominal_identity_threshold": str(threshold),
                    "identity_excess": str(needed),
                    "n_clusters": str(len(target_to_clusters[name])),
                    "n_shared_clusters": str(
                        sum(1 for cid in target_to_clusters[name] if len(cluster_targets[cid]) > 1)
                    ),
                    "cluster_identity_sizes": ",".join(str(v) for v in sorted(sizes, reverse=True)),
                    "n_exclusive_clusters": str(n_exclusive),
                    "exclusive_cluster_identities": str(exclusive_ids),
                }
            )
        impact_rows.append(
            {
                "max_target_fraction": fmt_float(fraction, 2),
                "n_identities_denominator": str(n_identities),
                "nominal_identity_threshold": str(threshold),
                "threshold_definition": "floor(fraction * n_identities); exceeds if identity_count > threshold (count/N > fraction is then true for integer counts)",
                "n_targets_above_threshold": str(len(over)),
                "n_identities_from_overrepresented_targets": str(over_identities),
                "raw_identity_excess": str(excess),
                "n_clusters_touching_overrepresented_targets": str(len(touching)),
                "n_shared_clusters_among_those": str(shared),
                "idealised_recordwise_capped_corpus_size": str(n_identities - excess),
                "idealised_recordwise_identities_removed": str(excess),
                "cluster_union_upper_bound_identities_removed": str(union_identities),
                "cluster_union_upper_bound_remaining_identities": str(n_identities - union_identities),
                "exclusive_clusters_can_absorb_all_excess": "true" if exclusive_ok else "false",
                "s7_cluster_selection_specified": "false",
                "note": (
                    "Idealised record-wise size is not executable S7 output. "
                    "Upper bound removes every cluster touching an overrepresented target, including collateral identities. "
                    "No whole-cluster retention rule is applied."
                ),
            }
        )
    return impact_rows, detail_rows, {"s7_cluster_selection_specified": False}


def build_uniprot_resolution(corpus_rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    targets = {_blank(row.get("canonical_target_name")) for row in corpus_rows}
    targets_with = {
        _blank(row.get("canonical_target_name"))
        for row in corpus_rows
        if present(row.get("target_uniprot"))
    }
    clusters_with = {
        _blank(row.get("cluster_id"))
        for row in corpus_rows
        if present(row.get("target_uniprot"))
    }
    all_clusters = {_blank(row.get("cluster_id")) for row in corpus_rows}
    n_id = len(corpus_rows)
    n_id_with = sum(1 for row in corpus_rows if present(row.get("target_uniprot")))
    n_family_blank = sum(1 for row in corpus_rows if not present(row.get("target_family")))
    n_family_unknown = sum(1 for row in corpus_rows if _blank(row.get("target_family")) == "unknown")
    n_pfam = sum(1 for row in corpus_rows if present(row.get("target_pfam")))
    n_interpro = sum(1 for row in corpus_rows if present(row.get("target_interpro")))
    return {
        "n_canonical_targets": len(targets),
        "n_targets_with_uniprot": len(targets_with),
        "n_targets_without_uniprot": len(targets) - len(targets_with),
        "n_identities_with_uniprot": n_id_with,
        "identity_weighted_rate": n_id_with / n_id if n_id else 0.0,
        "target_weighted_rate": len(targets_with) / len(targets) if targets else 0.0,
        "n_clusters_with_uniprot": len(clusters_with),
        "cluster_weighted_rate": len(clusters_with) / len(all_clusters) if all_clusters else 0.0,
        "n_identities_blank_target_family": n_family_blank,
        "n_identities_unknown_target_family": n_family_unknown,
        "n_identities_with_target_pfam": n_pfam,
        "n_identities_with_target_interpro": n_interpro,
        "n_targets_with_target_pfam": len(
            {_blank(row.get("canonical_target_name")) for row in corpus_rows if present(row.get("target_pfam"))}
        ),
        "n_targets_with_target_interpro": len(
            {
                _blank(row.get("canonical_target_name"))
                for row in corpus_rows
                if present(row.get("target_interpro"))
            }
        ),
    }


def build_polyspecificity(corpus_rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    cores: dict[str, set[str]] = defaultdict(set)
    core_identities: dict[str, list[str]] = defaultdict(list)
    for row in corpus_rows:
        core = _blank(row.get("sequence_core"))
        cores[core].add(_blank(row.get("canonical_target_name")))
        core_identities[core].append(_blank(row.get("scientific_identity_id")))
    shared = {core: names for core, names in cores.items() if len(names) > 1}
    n_shared_cores = len(shared)
    n_shared_identities = sum(len(core_identities[core]) for core in shared)
    dist = Counter(len(names) for names in shared.values())
    combinations = Counter(
        join_sorted_unique(names) for names in shared.values()
    )
    by_cluster: dict[str, set[str]] = defaultdict(set)
    for row in corpus_rows:
        by_cluster[_blank(row.get("cluster_id"))].add(_blank(row.get("canonical_target_name")))
    multi_target_clusters = [cid for cid, names in by_cluster.items() if len(names) > 1]
    cluster_multi_from_shared_core = 0
    cluster_multi_near_only = 0
    for cid in multi_target_clusters:
        members = [row for row in corpus_rows if _blank(row.get("cluster_id")) == cid]
        member_cores = {_blank(row.get("sequence_core")) for row in members}
        if any(core in shared for core in member_cores):
            cluster_multi_from_shared_core += 1
        else:
            cluster_multi_near_only += 1
    combo_rows = [
        {"targets": combo, "n_shared_sequence_cores": str(count)}
        for combo, count in sorted(combinations.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "n_shared_sequence_cores": n_shared_cores,
        "n_shared_core_identities": n_shared_identities,
        "targets_per_shared_core": {str(k): int(v) for k, v in sorted(dist.items())},
        "top_target_combinations": combo_rows[:20],
        "n_clusters_multi_target": len(multi_target_clusters),
        "n_multi_target_clusters_with_identical_shared_core": cluster_multi_from_shared_core,
        "n_multi_target_clusters_near_sequence_only": cluster_multi_near_only,
    }


def _length_row(field: str, kind: str, value: str, values: Sequence[int]) -> dict[str, str]:
    stats = percentile_bundle([float(v) for v in values])
    return {
        "sequence_field": field,
        "stratum_kind": kind,
        "stratum_value": value,
        "n": str(int(stats["n"])),
        "min": fmt_float(stats["min"], 1),
        "p05": fmt_float(stats["p05"], 3),
        "p25": fmt_float(stats["p25"], 3),
        "median": fmt_float(stats["median"], 3),
        "mean": fmt_float(stats["mean"], 3),
        "p75": fmt_float(stats["p75"], 3),
        "p95": fmt_float(stats["p95"], 3),
        "max": fmt_float(stats["max"], 1),
    }


def build_length_profile(
    corpus_rows: Sequence[Mapping[str, str]],
    *,
    top_targets: Sequence[str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows: list[dict[str, str]] = []
    outlier_rows: list[dict[str, str]] = []
    unique_cores = canonical_core_rows(corpus_rows)
    for row in corpus_rows:
        if length_of(row, "sequence_core") > LENGTH_OUTLIER_NT:
            outlier_rows.append(
                {
                    "scientific_identity_id": _blank(row.get("scientific_identity_id")),
                    "sequence_core_sha256": _blank(row.get("sequence_core_sha256")),
                    "cluster_id": _blank(row.get("cluster_id")),
                    "canonical_target_name": _blank(row.get("canonical_target_name")),
                    "source_db": _blank(row.get("source_db")),
                    "sequence_length_core": str(length_of(row, "sequence_core")),
                    "sequence_length_full": str(length_of(row, "sequence_full")),
                    "construct_scope": _blank(row.get("construct_scope")),
                    "alphabet_as_reported": _blank(row.get("alphabet_as_reported")),
                }
            )
    outlier_rows.sort(key=lambda row: row["scientific_identity_id"])
    for field in ("sequence_core", "sequence_full"):
        identity_lengths = [length_of(row, field) for row in corpus_rows]
        rows.append(_length_row(field, "overall_identities", "all", identity_lengths))
        if field == "sequence_core":
            core_lengths = [length_of(row, field) for row in unique_cores.values()]
            rows.append(_length_row(field, "overall_distinct_cores", "all", core_lengths))
        by_source: dict[str, list[int]] = defaultdict(list)
        by_scope: dict[str, list[int]] = defaultdict(list)
        by_chem: dict[str, list[int]] = defaultdict(list)
        by_target: dict[str, list[int]] = defaultdict(list)
        for row in corpus_rows:
            length = length_of(row, field)
            by_source[_blank(row.get("source_db")) or "(blank)"].append(length)
            by_scope[_blank(row.get("construct_scope")) or "(blank)"].append(length)
            by_chem[_blank(row.get("chemistry")) or "(blank)"].append(length)
            target = _blank(row.get("canonical_target_name"))
            if target in set(top_targets):
                by_target[target].append(length)
        for kind, mapping in (
            ("donor_source_db", by_source),
            ("construct_scope", by_scope),
            ("chemistry", by_chem),
            ("canonical_target_name", by_target),
        ):
            for key in sorted(mapping):
                rows.append(_length_row(field, kind, key, mapping[key]))
    return rows, {
        "n_identities_gt_100nt": len(outlier_rows),
        "n_cores_gt_100nt": len({row["sequence_core_sha256"] for row in outlier_rows}),
        "outliers": outlier_rows,
    }


def _composition_row(
    weighting: str,
    kind: str,
    value: str,
    sequences: Sequence[str],
) -> dict[str, str]:
    stats = sequence_composition(sequences)
    gc = stats["gc"]
    return {
        "weighting": weighting,
        "stratum_kind": kind,
        "stratum_value": value,
        "n_sequences": str(stats["n_sequences"]),
        "n_nucleotides": str(stats["n_nucleotides"]),
        "frac_A": fmt_float(stats["frac_A"]),
        "frac_U": fmt_float(stats["frac_U"]),
        "frac_C": fmt_float(stats["frac_C"]),
        "frac_G": fmt_float(stats["frac_G"]),
        "frac_T": fmt_float(stats["frac_T"]),
        "frac_other": fmt_float(stats["frac_other"]),
        "gc_mean": fmt_float(gc["mean"]),
        "gc_median": fmt_float(gc["median"]),
        "gc_p05": fmt_float(gc["p05"]),
        "gc_p25": fmt_float(gc["p25"]),
        "gc_p75": fmt_float(gc["p75"]),
        "gc_p95": fmt_float(gc["p95"]),
        "gc_min": fmt_float(gc["min"]),
        "gc_max": fmt_float(gc["max"]),
    }


def build_composition_profile(
    corpus_rows: Sequence[Mapping[str, str]],
    *,
    top_targets: Sequence[str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    unique_cores = canonical_core_rows(corpus_rows)
    rows: list[dict[str, str]] = [
        _composition_row("distinct_sequence_core", "overall", "all", list(unique_cores)),
        _composition_row(
            "identity_weighted",
            "overall",
            "all",
            [_blank(row.get("sequence_core")) for row in corpus_rows],
        ),
    ]
    by_source: dict[str, list[str]] = defaultdict(list)
    by_chem: dict[str, list[str]] = defaultdict(list)
    seen_core_source: set[tuple[str, str]] = set()
    seen_core_chem: set[tuple[str, str]] = set()
    for core, row in unique_cores.items():
        source = _blank(row.get("source_db")) or "(blank)"
        chem = _blank(row.get("chemistry")) or "(blank)"
        by_source[source].append(core)
        by_chem[chem].append(core)
        seen_core_source.add((core, source))
        seen_core_chem.add((core, chem))
    for source, seqs in sorted(by_source.items()):
        rows.append(_composition_row("distinct_sequence_core", "donor_source_db", source, seqs))
    for chem, seqs in sorted(by_chem.items()):
        rows.append(_composition_row("distinct_sequence_core", "chemistry", chem, seqs))
    by_target: dict[str, list[str]] = defaultdict(list)
    for row in corpus_rows:
        target = _blank(row.get("canonical_target_name"))
        if target in set(top_targets):
            by_target[target].append(_blank(row.get("sequence_core")))
    for target, seqs in sorted(by_target.items()):
        rows.append(_composition_row("identity_weighted", "canonical_target_name", target, seqs))
    distinct_stats = sequence_composition(list(unique_cores))
    identity_stats = sequence_composition([_blank(row.get("sequence_core")) for row in corpus_rows])
    del seen_core_source, seen_core_chem
    return rows, {
        "distinct_core": distinct_stats,
        "identity_weighted": identity_stats,
        "gc_values_distinct_core": [
            sum(1 for base in seq.upper() if base in GC_BASES) / len(seq)
            for seq in sorted(unique_cores)
            if seq
        ],
    }


def build_cluster_profile(
    corpus_rows: Sequence[Mapping[str, str]],
    cluster_summary_rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    summary_by_id = {_blank(row.get("cluster_id")): row for row in cluster_summary_rows}
    by_cluster = _cluster_identity_index(corpus_rows)
    rows: list[dict[str, str]] = []
    singleton = 0
    multi_seq = 0
    multi_target = 0
    multi_source = 0
    ena = 0
    ena_union = 0
    for cluster_id, members in sorted(by_cluster.items()):
        cores = {_blank(row.get("sequence_core")) for row in members}
        targets = {_blank(row.get("canonical_target_name")) for row in members}
        sources: set[str] = set()
        for row in members:
            sources.update(contributing_sources_of(row))
        summary = summary_by_id.get(cluster_id, {})
        merge_basis = _blank(summary.get("merge_basis")) or "mmseqs_only"
        ena_present = _blank(summary.get("ena_provenance_present")) == "true" or any(
            "ena" in contributing_sources_of(row) for row in members
        )
        n_cores = len(cores)
        if n_cores == 1:
            singleton += 1
        else:
            multi_seq += 1
        if len(targets) > 1:
            multi_target += 1
        if len(sources) > 1:
            multi_source += 1
        if ena_present:
            ena += 1
        if merge_basis == MERGE_MMSEQS_PLUS_ENA:
            ena_union += 1
        rows.append(
            {
                "cluster_id": cluster_id,
                "n_distinct_sequence_core": str(n_cores),
                "n_scientific_identities": str(len(members)),
                "n_canonical_targets": str(len(targets)),
                "canonical_targets": join_sorted_unique(targets),
                "contributing_sources": join_sorted_unique(sources),
                "merge_basis": merge_basis,
                "ena_provenance_present": "true" if ena_present else "false",
                "is_singleton_core": "true" if n_cores == 1 else "false",
            }
        )
    rows.sort(
        key=lambda row: (
            -int(row["n_distinct_sequence_core"]),
            -int(row["n_scientific_identities"]),
            row["cluster_id"],
        )
    )
    core_sizes = [int(row["n_distinct_sequence_core"]) for row in rows]
    identity_sizes = [int(row["n_scientific_identities"]) for row in rows]
    return rows, {
        "n_clusters": len(rows),
        "n_singleton_clusters": singleton,
        "singleton_fraction": singleton / len(rows) if rows else 0.0,
        "n_multi_sequence_clusters": multi_seq,
        "n_multi_target_clusters": multi_target,
        "n_multi_source_clusters": multi_source,
        "n_ena_provenance_clusters": ena,
        "n_ena_must_link_union_clusters": ena_union,
        "core_size_distribution": dict(sorted(Counter(core_sizes).items())),
        "identity_size_distribution": dict(sorted(Counter(identity_sizes).items())),
        "largest_core_size": max(core_sizes) if core_sizes else 0,
        "largest_identity_size": max(identity_sizes) if identity_sizes else 0,
    }


def build_source_profile(
    corpus_rows: Sequence[Mapping[str, str]],
    membership_rows: Sequence[Mapping[str, str]],
    overlap_matrix_rows: Sequence[Mapping[str, str]],
    *,
    source_keys: Sequence[str] = DEFAULT_OVERLAP_SOURCES,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    n_identities = len(corpus_rows)
    donor_counts = Counter(_blank(row.get("source_db")) for row in corpus_rows)
    contributing_counts = Counter()
    unique_identity_counts = Counter()
    unique_core_counts = Counter()
    identity_sources: dict[str, set[str]] = defaultdict(set)
    core_sources: dict[str, set[str]] = defaultdict(set)
    for row in corpus_rows:
        sources = set(contributing_sources_of(row))
        identity_sources[_blank(row.get("scientific_identity_id"))].update(sources)
        core_sources[_blank(row.get("sequence_core"))].update(sources)
        for source in sources:
            contributing_counts[source] += 1
        if len(sources) == 1:
            unique_identity_counts[next(iter(sources))] += 1
    for core, sources in core_sources.items():
        if len(sources) == 1:
            unique_core_counts[next(iter(sources))] += 1
    corroboration = Counter(as_int(row.get("corroboration_count"), default=1) for row in corpus_rows)
    n_multi = sum(1 for row in corpus_rows if as_int(row.get("corroboration_count"), default=1) > 1)
    rows: list[dict[str, str]] = []
    for source in source_keys:
        n_donor = int(donor_counts.get(source, 0))
        rows.append(
            {
                "source_db": source,
                "n_identities_donor": str(n_donor),
                "pct_identities_donor": fmt_pct(n_donor, n_identities),
                "n_identities_contributing": str(int(contributing_counts.get(source, 0))),
                "n_identities_unique_attestation": str(int(unique_identity_counts.get(source, 0))),
                "n_cores_unique_attestation": str(int(unique_core_counts.get(source, 0))),
            }
        )
    overlap = [
        {
            "source_a": _blank(row.get("source_a")),
            "source_b": _blank(row.get("source_b")),
            "n_shared_scientific_identities": _blank(row.get("n_shared_scientific_identities")),
            "n_shared_duplicate_groups": _blank(row.get("n_shared_duplicate_groups")),
        }
        for row in overlap_matrix_rows
    ]
    overlap.sort(key=lambda row: (row["source_a"], row["source_b"]))
    membership_by_source = Counter(_blank(row.get("source_db")) for row in membership_rows)
    return rows, {
        "donor_counts": dict(sorted(donor_counts.items())),
        "contributing_counts": dict(sorted(contributing_counts.items())),
        "unique_identity_counts": dict(sorted(unique_identity_counts.items())),
        "unique_core_counts": dict(sorted(unique_core_counts.items())),
        "corroboration_count_distribution": {str(k): int(v) for k, v in sorted(corroboration.items())},
        "n_identities_corroborated_gt1": n_multi,
        "n_membership_rows": len(membership_rows),
        "membership_source_counts": dict(sorted(membership_by_source.items())),
        "overlap_matrix": overlap,
        "definitions": {
            "donor_source": "source_db of the exact-dedup donor identity (single-valued)",
            "contributing_source": "pipe-delimited provenance sources merged onto the identity",
            "corroboration_count": "number of distinct contributing sources for the identity",
        },
    }


def build_evidence_profile(corpus_rows: Sequence[Mapping[str, str]]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    n_identities = len(corpus_rows)
    levels = Counter(_blank(row.get("evidence_level")) or "(blank)" for row in corpus_rows)
    rows = []
    for level in (*EVIDENCE_ORDER, "(blank)"):
        if level not in levels and level == "(blank)":
            continue
        count = int(levels.get(level, 0))
        if level not in levels:
            rows.append(
                {
                    "evidence_level": level,
                    "n_scientific_identities": "0",
                    "pct_identities": fmt_pct(0, n_identities),
                }
            )
            continue
        rows.append(
            {
                "evidence_level": level,
                "n_scientific_identities": str(count),
                "pct_identities": fmt_pct(count, n_identities),
            }
        )
    by_source: dict[str, Counter] = defaultdict(Counter)
    by_family: dict[str, Counter] = defaultdict(Counter)
    by_corr: dict[str, Counter] = defaultdict(Counter)
    for row in corpus_rows:
        level = _blank(row.get("evidence_level")) or "(blank)"
        by_source[_blank(row.get("source_db")) or "(blank)"][level] += 1
        by_family[_family_label(row)][level] += 1
        by_corr[str(as_int(row.get("corroboration_count"), default=1))][level] += 1
    n_e2 = int(levels.get("E2", 0))
    n_e3 = int(levels.get("E3", 0))
    n_e4 = int(levels.get("E4", 0))
    n_e5 = int(levels.get("E5", 0))
    return rows, {
        "counts": {str(k): int(v) for k, v in sorted(levels.items())},
        "n_e2": n_e2,
        "n_e3": n_e3,
        "n_e4": n_e4,
        "n_e5": n_e5,
        "pct_e2": n_e2 / n_identities if n_identities else 0.0,
        "pct_e3": n_e3 / n_identities if n_identities else 0.0,
        "pct_e4": n_e4 / n_identities if n_identities else 0.0,
        "by_donor_source": {src: dict(counter) for src, counter in sorted(by_source.items())},
        "by_target_family": {fam: dict(counter) for fam, counter in sorted(by_family.items())},
        "by_corroboration_count": {corr: dict(counter) for corr, counter in sorted(by_corr.items())},
    }


def build_affinity_profile(corpus_rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    n_identities = len(corpus_rows)
    with_value = [row for row in corpus_rows if present(row.get("canonical_affinity_value"))]
    types = Counter(
        _blank(row.get("canonical_affinity_type")) or "(blank)" for row in with_value
    )
    kd_logs: list[float] = []
    for row in with_value:
        if _blank(row.get("canonical_affinity_type")) != "Kd":
            continue
        molar = as_float(row.get("affinity_value_molar"))
        if molar is None or molar <= 0:
            continue
        kd_logs.append(math.log10(molar))
    kd_logs.sort()
    by_source = Counter(_blank(row.get("source_db")) for row in with_value)
    by_family = Counter(_family_label(row) for row in with_value)
    return {
        "n_with_canonical_affinity": len(with_value),
        "pct_with_canonical_affinity": len(with_value) / n_identities if n_identities else 0.0,
        "type_counts": dict(sorted(types.items())),
        "n_kd_log10_molar": len(kd_logs),
        "kd_log10_molar": percentile_bundle(kd_logs) if kd_logs else percentile_bundle([]),
        "by_donor_source": dict(sorted(by_source.items())),
        "by_target_family": dict(sorted(by_family.items())),
        "note": (
            "Canonical affinity is reported only where a scalar exists. "
            "Kd log10 molar statistics are Kd-only and are not averaged across multi-source observations."
        ),
    }


def build_chemistry_profile(corpus_rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    def counts(field: str) -> dict[str, int]:
        return dict(
            sorted(
                Counter(_blank(row.get(field)) or "(blank)" for row in corpus_rows).items()
            )
        )

    n_chem_conflict = sum(
        1
        for row in corpus_rows
        if "multiple_chemistries" in split_pipe(row.get("conflict_flags", ""))
    )
    return {
        "chemistry": counts("chemistry"),
        "molecule_type": counts("molecule_type"),
        "construct_scope": counts("construct_scope"),
        "trim_confidence": counts("trim_confidence"),
        "trim_status": counts("trim_status"),
        "t_to_u_applied": counts("t_to_u_applied"),
        "alphabet_as_reported": counts("alphabet_as_reported"),
        "n_identities_multiple_chemistries": n_chem_conflict,
    }


def build_licensing_profile(corpus_rows: Sequence[Mapping[str, str]]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    n_identities = len(corpus_rows)
    status_counts = Counter(_blank(row.get("redistribution_status")) or "(blank)" for row in corpus_rows)
    rows = [
        {
            "redistribution_status": status,
            "n_scientific_identities": str(count),
            "pct_identities": fmt_pct(int(count), n_identities),
        }
        for status, count in sorted(status_counts.items())
    ]
    restricted_or_unknown = [
        row
        for row in corpus_rows
        if _blank(row.get("redistribution_status")) in {"restricted", "unknown"}
    ]
    n_ru = len(restricted_or_unknown)
    n_ru_permissive = sum(
        1
        for row in restricted_or_unknown
        if row.get("independently_attested_by_permissive_source") == "true"
    )
    n_restricted = int(status_counts.get("restricted", 0))
    n_unknown = int(status_counts.get("unknown", 0))
    n_permissive = int(status_counts.get("permissive", 0))
    aptaindex_donor = [row for row in corpus_rows if _blank(row.get("source_db")) == "aptaindex"]
    aptaindex_contrib = [
        row for row in corpus_rows if "aptaindex" in contributing_sources_of(row)
    ]
    aptaindex_only = [
        row
        for row in aptaindex_contrib
        if contributing_sources_of(row) == ["aptaindex"]
    ]
    aptaindex_corroborated = [
        row
        for row in aptaindex_contrib
        if set(contributing_sources_of(row)) - {"aptaindex"}
    ]
    n_restricted_only = sum(
        1
        for row in corpus_rows
        if _blank(row.get("redistribution_status")) == "restricted"
        and contributing_sources_of(row) == ["aptaindex"]
    )
    return rows, {
        "n_permissive": n_permissive,
        "n_unknown": n_unknown,
        "n_restricted": n_restricted,
        "n_restricted_or_unknown": n_ru,
        "n_restricted_or_unknown_independently_permissive": n_ru_permissive,
        "fraction_restricted_unknown_independently_permissive": (
            n_ru_permissive / n_ru if n_ru else 0.0
        ),
        "n_identities_attributable_only_to_restricted_sources": n_restricted_only,
        "n_aptaindex_donor": len(aptaindex_donor),
        "n_aptaindex_contributing": len(aptaindex_contrib),
        "n_aptaindex_only": len(aptaindex_only),
        "n_aptaindex_corroborated_elsewhere": len(aptaindex_corroborated),
        "independently_attested_by_permissive_source_counts": dict(
            sorted(
                Counter(
                    _blank(row.get("independently_attested_by_permissive_source")) or "(blank)"
                    for row in corpus_rows
                ).items()
            )
        ),
        "note": "Descriptive/documentary only. Not a legal conclusion. S6 does not exclude records for licensing.",
    }


def build_majority_cluster_target_counts(
    corpus_rows: Sequence[Mapping[str, str]],
) -> list[int]:
    by_cluster = _cluster_identity_index(corpus_rows)
    majority: Counter[str] = Counter()
    for members in by_cluster.values():
        counts = Counter(_blank(row.get("canonical_target_name")) for row in members)
        top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
        majority[top] += 1
    return [int(v) for _, v in sorted(majority.items())]


def build_checkpoint3_decisions(
    *,
    headline: Mapping[str, Any],
    cap_rows: Sequence[Mapping[str, str]],
    evidence: Mapping[str, Any],
    s7_specified: bool,
) -> list[dict[str, str]]:
    cap_lines = []
    for row in cap_rows:
        cap_lines.append(
            f"{row['max_target_fraction']}: threshold={row['nominal_identity_threshold']} "
            f"targets_above={row['n_targets_above_threshold']} "
            f"excess={row['raw_identity_excess']} "
            f"idealised_recordwise_size={row['idealised_recordwise_capped_corpus_size']}"
        )
    decisions = [
        {
            "decision_id": "C3-01",
            "title": "Final MAX_TARGET_FRACTION",
            "question": "Which per-target identity-fraction cap should S7 apply?",
            "why_it_matters": (
                "The cap is the v1 balancing tool for the primary RNA corpus. "
                "It trades target concentration (especially NGF) against retained corpus size."
            ),
            "relevant_data": " | ".join(cap_lines),
            "options": "0.02|0.03|0.05|0.10|other/manual",
            "current_plan_context": "plan/config default = 0.05; final value deferred to CHECKPOINT-3; not preselected",
            "corpus_size_or_diversity_effect": (
                "See candidate-cap table. Idealised record-wise sizes are diagnostic only; "
                "executable S7 size depends on unspecified whole-cluster selection semantics."
            ),
            "human_decision": "",
            "human_notes": "",
            "status": "awaiting_supervisor_review",
        },
        {
            "decision_id": "C3-02",
            "title": "Further balancing beyond per-target cap",
            "question": "After the per-target cap, should v1 also balance by target family or another scheme?",
            "why_it_matters": (
                "target_family is the planned stratification axis, but family labels are sparse "
                "(many identities are unknown). Additional balancing is deferred in the v1 plan."
            ),
            "relevant_data": (
                f"identities={headline['n_scientific_identities']}; "
                f"targets={headline['n_canonical_targets']}; "
                f"families={headline['n_target_families']}; "
                f"enzyme_identities={headline['n_enzyme_identities']}"
            ),
            "options": "no|yes_target_family_balancing|yes_other_manual",
            "current_plan_context": "v1 defers target-family balancing beyond the per-target cap",
            "corpus_size_or_diversity_effect": "Not simulated. No family-balancing algorithm is applied in S6.",
            "human_decision": "",
            "human_notes": "",
            "status": "awaiting_supervisor_review",
        },
        {
            "decision_id": "C3-03",
            "title": "Evidence threshold",
            "question": "Retain the current E4 minimum, or relax to admit parked E5 records?",
            "why_it_matters": (
                "The <500-cluster emergency trigger is not met. Relaxing E4 would enlarge the "
                "corpus and change evidence mix; S6 does not promote E5."
            ),
            "relevant_data": (
                f"E2={evidence['n_e2']} ({fmt_pct(evidence['n_e2'], headline['n_scientific_identities'])}%); "
                f"E3={evidence['n_e3']} ({fmt_pct(evidence['n_e3'], headline['n_scientific_identities'])}%); "
                f"E4={evidence['n_e4']} ({fmt_pct(evidence['n_e4'], headline['n_scientific_identities'])}%); "
                f"E5_in_primary={evidence['n_e5']}; clusters={headline['n_final_clusters']}"
            ),
            "options": "retain_E4_minimum|admit_E5|other/manual",
            "current_plan_context": "current primary corpus is E2/E3/E4 with no E5; trigger <500 clusters is not met",
            "corpus_size_or_diversity_effect": "Not simulated. Parked E5 files exist for a later one-line filter change.",
            "human_decision": "",
            "human_notes": "",
            "status": "awaiting_supervisor_review",
        },
        {
            "decision_id": "C3-04",
            "title": "Protein-only policy",
            "question": "Retain the protein-only primary corpus, or admit parked non-protein records?",
            "why_it_matters": (
                "Non-protein promotion would change target-type mix and NDM-1 transfer framing. "
                "S6 does not promote non-protein records."
            ),
            "relevant_data": (
                f"primary identities={headline['n_scientific_identities']}; "
                "non-protein records remain parked upstream and are not in this corpus"
            ),
            "options": "retain_protein_only|admit_non_protein_parked_records|other/manual",
            "current_plan_context": "protein-only primary corpus; AptaDB non-protein lookup tables still absent",
            "corpus_size_or_diversity_effect": "Not simulated. Parked non-protein files exist for a later filter change.",
            "human_decision": "",
            "human_notes": "",
            "status": "awaiting_supervisor_review",
        },
    ]
    if not s7_specified:
        decisions.append(
            {
                "decision_id": "C3-05",
                "title": "S7 cap-selection semantics",
                "question": (
                    "What deterministic whole-cluster rule should S7 use when applying the per-target cap?"
                ),
                "why_it_matters": (
                    "The v1.4 plan requires a cluster-level cap but does not specify denominator, "
                    "floor/ceiling, cluster ranking, multi-target cluster treatment, or collateral removal. "
                    "S6 therefore reports bounds rather than a single resulting corpus size."
                ),
                "relevant_data": (
                    "unspecified: "
                    + "; ".join(S7_UNSPECIFIED_ITEMS)
                ),
                "options": "specify_deterministic_cluster_rule_in_S7|other/manual",
                "current_plan_context": (
                    "plan says apply the per-target cap at cluster level; no executable algorithm exists in code"
                ),
                "corpus_size_or_diversity_effect": (
                    "Until specified, S7 cannot emit a unique capped corpus size. "
                    "S6 reports record-wise idealised size and cluster-union upper-bound impact only."
                ),
                "human_decision": "",
                "human_notes": "",
                "status": "awaiting_supervisor_review",
            }
        )
    for row in decisions:
        for field_name in HUMAN_CHECKPOINT_FIELDS:
            if row[field_name] != "":
                raise S6ProfileError(f"{row['decision_id']} human field {field_name} must be blank")
        if SEQ_LEAK_RE.search(" ".join(row.values())):
            raise S6ProfileError(f"{row['decision_id']} contains a sequence-like token")
    return decisions


@dataclass
class S6Assembly:
    assertions: dict[str, Any]
    headline: dict[str, Any]
    target_rows: list[dict[str, str]]
    family_rows: list[dict[str, str]]
    pfam_rows: list[dict[str, str]]
    interpro_rows: list[dict[str, str]]
    sparse_rows: list[dict[str, str]]
    sparse_counts: dict[str, int]
    diversity: dict[str, Any]
    cap_rows: list[dict[str, str]]
    cap_target_rows: list[dict[str, str]]
    uniprot: dict[str, Any]
    polyspecificity: dict[str, Any]
    length_rows: list[dict[str, str]]
    length_outliers: dict[str, Any]
    bimodality: dict[str, Any]
    composition_rows: list[dict[str, str]]
    composition: dict[str, Any]
    cluster_rows: list[dict[str, str]]
    cluster_stats: dict[str, Any]
    source_rows: list[dict[str, str]]
    source_stats: dict[str, Any]
    evidence_rows: list[dict[str, str]]
    evidence: dict[str, Any]
    affinity: dict[str, Any]
    chemistry: dict[str, Any]
    licensing_rows: list[dict[str, str]]
    licensing: dict[str, Any]
    checkpoint3_decisions: list[dict[str, str]]
    qc: dict[str, Any]
    source_regime_rows: list[dict[str, str]] = field(default_factory=list)
    core_full_comparison: dict[str, Any] = field(default_factory=dict)
    core_lengths: list[int] = field(default_factory=list)
    identity_core_lengths: list[int] = field(default_factory=list)
    full_lengths: list[int] = field(default_factory=list)
    core_lengths_by_source: dict[str, list[int]] = field(default_factory=dict)
    gc_values: list[float] = field(default_factory=list)


def assemble_profile(
    corpus_rows: Sequence[Mapping[str, str]],
    *,
    cluster_summary_rows: Sequence[Mapping[str, str]],
    union_provenance_rows: Sequence[Mapping[str, str]] | None = None,
    membership_rows: Sequence[Mapping[str, str]],
    overlap_matrix_rows: Sequence[Mapping[str, str]],
    clusters_final_rows: Sequence[Mapping[str, str]] | None = None,
    expected_counts: Mapping[str, Any] | None = None,
    candidate_fractions: Sequence[float] = CANDIDATE_FRACTIONS,
) -> S6Assembly:
    del union_provenance_rows
    assertions = validate_s6_inputs(
        corpus_rows,
        cluster_summary_rows=cluster_summary_rows,
        clusters_final_rows=clusters_final_rows,
        expected_counts=expected_counts,
    )
    n_identities = assertions["n_scientific_identities"]
    n_clusters = assertions["n_final_clusters"]
    target_rows = build_target_profile(
        corpus_rows, n_identities=n_identities, n_clusters=n_clusters
    )
    family_rows = build_family_profile(
        corpus_rows, n_identities=n_identities, n_clusters=n_clusters
    )
    pfam_rows = build_group_profile(corpus_rows, "target_pfam", kind="pfam")
    interpro_rows = build_group_profile(corpus_rows, "target_interpro", kind="interpro")
    sparse_rows, sparse_counts = build_sparse_targets(target_rows)
    identity_counts = [int(row["n_scientific_identities"]) for row in target_rows]
    cluster_occupancy = [int(row["n_clusters"]) for row in target_rows]
    majority_counts = build_majority_cluster_target_counts(corpus_rows)
    diversity = {
        "identity_count_gini": gini_coefficient(identity_counts),
        "identity_count_shannon": shannon_entropy(identity_counts),
        "cluster_occupancy_gini": gini_coefficient(cluster_occupancy),
        "cluster_occupancy_shannon": shannon_entropy(cluster_occupancy),
        "cluster_majority_gini": gini_coefficient(majority_counts),
        "cluster_majority_shannon": shannon_entropy(majority_counts),
        "formulas": {
            "gini": "G = 2*sum(i*x_i)/(k*sum(x)) - (k+1)/k for sorted x",
            "shannon": "H = -sum p_i ln p_i (nats); H_norm = H/ln(k); N_eff = exp(H)",
            "primary_vector": "scientific-identity counts per canonical_target_name",
            "cluster_occupancy_vector": "n_clusters touching each canonical target (a cluster may count in more than one target)",
            "cluster_majority_vector": "each cluster assigned once to its majority target, alphabetical tie-break",
        },
    }
    cap_rows, cap_target_rows, cap_meta = build_candidate_cap_analysis(
        corpus_rows, target_rows, fractions=candidate_fractions
    )
    uniprot = build_uniprot_resolution(corpus_rows)
    poly = build_polyspecificity(corpus_rows)
    if expected_counts:
        if poly["n_shared_sequence_cores"] != expected_counts.get(
            "n_shared_sequence_cores", poly["n_shared_sequence_cores"]
        ):
            raise S6ProfileError("shared sequence_core count drifted")
        if poly["n_shared_core_identities"] != expected_counts.get(
            "n_shared_core_identities", poly["n_shared_core_identities"]
        ):
            raise S6ProfileError("shared-core identity count drifted")
    top_targets = [row["canonical_target_name"] for row in target_rows[:TOP_N_TARGETS]]
    length_rows, length_outliers = build_length_profile(corpus_rows, top_targets=top_targets)
    if expected_counts and length_outliers["n_identities_gt_100nt"] != expected_counts.get(
        "n_length_outliers_gt_100nt", length_outliers["n_identities_gt_100nt"]
    ):
        raise S6ProfileError("length-outlier count drifted")
    unique_cores = canonical_core_rows(corpus_rows)
    core_items = sorted(unique_cores.items(), key=lambda item: item[0])
    core_lengths = [length_of(row, "sequence_core") for _, row in core_items]
    core_full_comparison = build_core_full_comparison(corpus_rows)
    identity_core_lengths = list(core_full_comparison["identity_core_lengths"])
    full_lengths = list(core_full_comparison["identity_full_lengths"])
    gmm1 = fit_univariate_gmm(core_lengths, n_components=1)
    gmm2 = fit_univariate_gmm(core_lengths, n_components=2)
    source_regime_rows, source_regime_stats = build_source_length_regime_summary(
        core_items, gmm2
    )
    bimodality = {
        "sample": "distinct_sequence_core_lengths",
        "n": len(core_lengths),
        "gmm_1": gmm1,
        "gmm_2": gmm2,
        **classify_bimodality(gmm1, gmm2),
        "full_construct_gmm": classify_bimodality(
            fit_univariate_gmm(full_lengths, n_components=1),
            fit_univariate_gmm(full_lengths, n_components=2),
        ),
        "source_regime_method": source_regime_stats["method"],
        "source_regime_assignment_method": source_regime_stats["assignment_method"],
        "source_regime_rows": source_regime_rows,
        "n_cores_shorter_regime": source_regime_stats["n_shorter"],
        "n_cores_longer_regime": source_regime_stats["n_longer"],
    }
    composition_rows, composition = build_composition_profile(
        corpus_rows, top_targets=top_targets[:10]
    )
    cluster_rows, cluster_stats = build_cluster_profile(corpus_rows, cluster_summary_rows)
    source_rows, source_stats = build_source_profile(
        corpus_rows, membership_rows, overlap_matrix_rows
    )
    evidence_rows, evidence = build_evidence_profile(corpus_rows)
    affinity = build_affinity_profile(corpus_rows)
    chemistry = build_chemistry_profile(corpus_rows)
    licensing_rows, licensing = build_licensing_profile(corpus_rows)
    enzyme_row = next((row for row in family_rows if row["target_family"] == "enzyme"), None)
    n_enzyme = int(enzyme_row["n_scientific_identities"]) if enzyme_row else 0
    n_families = len({_family_label(row) for row in corpus_rows})
    largest_target = target_rows[0] if target_rows else {}
    headline = {
        "n_scientific_identities": n_identities,
        "n_distinct_sequence_core": assertions["n_distinct_sequence_core"],
        "n_final_clusters": n_clusters,
        "n_canonical_targets": len(target_rows),
        "n_target_families": n_families,
        "n_enzyme_identities": n_enzyme,
        "enzyme_identity_share": n_enzyme / n_identities if n_identities else 0.0,
        "largest_target_name": largest_target.get("canonical_target_name", ""),
        "largest_target_identities": int(largest_target.get("n_scientific_identities", "0") or 0),
        "largest_target_identity_share": (
            int(largest_target.get("n_scientific_identities", "0") or 0) / n_identities
            if n_identities
            else 0.0
        ),
        "singleton_cluster_fraction": cluster_stats["singleton_fraction"],
        "n_singleton_clusters": cluster_stats["n_singleton_clusters"],
        "emergency_cluster_trigger": EMERGENCY_CLUSTER_TRIGGER,
        "emergency_trigger_met": n_clusters < EMERGENCY_CLUSTER_TRIGGER,
        "n_length_outliers_gt_100nt": length_outliers["n_identities_gt_100nt"],
        "n_shared_sequence_cores": poly["n_shared_sequence_cores"],
        "n_shared_core_identities": poly["n_shared_core_identities"],
        "donor_source_counts": source_stats["donor_counts"],
        "evidence_counts": evidence["counts"],
        "identity_gini": diversity["identity_count_gini"],
        "identity_shannon_nats": diversity["identity_count_shannon"]["shannon_nats"],
        "uniprot_identity_rate": uniprot["identity_weighted_rate"],
        "uniprot_target_rate": uniprot["target_weighted_rate"],
        "n_restricted": licensing["n_restricted"],
        "n_unknown_redistribution": licensing["n_unknown"],
        "n_permissive": licensing["n_permissive"],
        "bimodality_conclusion_core": bimodality["conclusion"],
        "s7_cluster_selection_specified": cap_meta["s7_cluster_selection_specified"],
    }
    qc = {
        "scientific_identity_id_authoritative": True,
        "donor_record_id_not_unique_at_s5_grain": True,
        "n_length_outliers_retained": length_outliers["n_identities_gt_100nt"],
        "alphabet_distribution": chemistry["alphabet_as_reported"],
        "cluster_construction": (
            "final cluster_id = frozen MMseqs 90% membership union trusted ENA family must-links; "
            "not every pair in a final cluster is >=90% identical"
        ),
        "partition_blank": assertions["n_partition_populated"] == 0,
        "n_e5_in_primary": evidence["n_e5"],
    }
    checkpoint3 = build_checkpoint3_decisions(
        headline=headline,
        cap_rows=cap_rows,
        evidence=evidence,
        s7_specified=bool(cap_meta["s7_cluster_selection_specified"]),
    )
    core_by_source: dict[str, list[int]] = defaultdict(list)
    for core, row in core_items:
        core_by_source[_blank(row.get("source_db")) or "(blank)"].append(
            length_of(row, "sequence_core")
        )
    return S6Assembly(
        assertions=assertions,
        headline=headline,
        target_rows=target_rows,
        family_rows=family_rows,
        pfam_rows=pfam_rows,
        interpro_rows=interpro_rows,
        sparse_rows=sparse_rows,
        sparse_counts=sparse_counts,
        diversity=diversity,
        cap_rows=cap_rows,
        cap_target_rows=cap_target_rows,
        uniprot=uniprot,
        polyspecificity=poly,
        length_rows=length_rows,
        length_outliers=length_outliers,
        bimodality=bimodality,
        composition_rows=composition_rows,
        composition=composition,
        cluster_rows=cluster_rows,
        cluster_stats=cluster_stats,
        source_rows=source_rows,
        source_stats=source_stats,
        evidence_rows=evidence_rows,
        evidence=evidence,
        affinity=affinity,
        chemistry=chemistry,
        licensing_rows=licensing_rows,
        licensing=licensing,
        checkpoint3_decisions=checkpoint3,
        qc=qc,
        source_regime_rows=source_regime_rows,
        core_full_comparison={
            key: value
            for key, value in core_full_comparison.items()
            if key not in {"identity_core_lengths", "identity_full_lengths"}
        },
        core_lengths=core_lengths,
        identity_core_lengths=identity_core_lengths,
        full_lengths=full_lengths,
        core_lengths_by_source=dict(core_by_source),
        gc_values=list(composition["gc_values_distinct_core"]),
    )


def scientific_payload(assembly: S6Assembly) -> dict[str, Any]:
    """Timestamp-free payload used for determinism comparison."""
    return {
        "assertions": assembly.assertions,
        "headline": assembly.headline,
        "target_rows": assembly.target_rows,
        "family_rows": assembly.family_rows,
        "pfam_rows": assembly.pfam_rows,
        "interpro_rows": assembly.interpro_rows,
        "sparse_rows": assembly.sparse_rows,
        "sparse_counts": assembly.sparse_counts,
        "diversity": assembly.diversity,
        "cap_rows": assembly.cap_rows,
        "cap_target_rows": assembly.cap_target_rows,
        "uniprot": assembly.uniprot,
        "polyspecificity": assembly.polyspecificity,
        "length_rows": assembly.length_rows,
        "length_outliers": assembly.length_outliers,
        "bimodality": assembly.bimodality,
        "composition_rows": assembly.composition_rows,
        "cluster_rows": assembly.cluster_rows,
        "cluster_stats": assembly.cluster_stats,
        "source_rows": assembly.source_rows,
        "source_stats": assembly.source_stats,
        "evidence_rows": assembly.evidence_rows,
        "evidence": assembly.evidence,
        "affinity": assembly.affinity,
        "chemistry": assembly.chemistry,
        "licensing_rows": assembly.licensing_rows,
        "licensing": assembly.licensing,
        "checkpoint3_decisions": assembly.checkpoint3_decisions,
        "qc": assembly.qc,
        "source_regime_rows": assembly.source_regime_rows,
        "core_full_comparison": assembly.core_full_comparison,
    }


def _first_diff(left: Any, right: Any, path: str = "") -> str | None:
    if type(left) is not type(right) and not (
        isinstance(left, (int, float)) and isinstance(right, (int, float))
    ):
        return f"{path}: type {type(left)} != {type(right)}"
    if isinstance(left, dict):
        left_keys = set(left)
        right_keys = set(right)
        if left_keys != right_keys:
            return f"{path}: keys {sorted(left_keys ^ right_keys)}"
        for key in left:
            found = _first_diff(left[key], right[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: list length {len(left)} != {len(right)}"
        for index, (a, b) in enumerate(zip(left, right)):
            found = _first_diff(a, b, f"{path}[{index}]")
            if found:
                return found
        return None
    if left != right:
        return f"{path}: {left!r} != {right!r}"
    return None


def compare_assemblies(first: S6Assembly, second: S6Assembly) -> None:
    diff = _first_diff(scientific_payload(first), scientific_payload(second))
    if diff:
        raise S6ProfileError(f"S6 profile assembly is not deterministic: {diff}")


__all__ = [
    "CANDIDATE_FRACTIONS",
    "CHECKPOINT3_DECISION_COLUMNS",
    "CORE_FULL_COMPARISON_COLUMNS",
    "GMM_POSTERIOR_ASSIGNMENT_METHOD",
    "HUMAN_CHECKPOINT_FIELDS",
    "S6Assembly",
    "S6ProfileError",
    "S7_UNSPECIFIED_ITEMS",
    "SOURCE_REGIME_COLUMNS",
    "assemble_profile",
    "assert_no_sequence_leak",
    "assert_not_frozen_s5_path",
    "build_core_full_comparison",
    "build_source_length_regime_summary",
    "classify_bimodality",
    "compare_assemblies",
    "enforce_authorised_config",
    "fit_univariate_gmm",
    "gini_coefficient",
    "gmm_posterior_assignment",
    "max_allowed_identities",
    "scientific_payload",
    "shannon_entropy",
    "sequence_composition",
]

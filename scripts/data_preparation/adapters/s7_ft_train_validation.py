"""GLOBAL S7C — deterministic FT-only train/validation split.

Preview mode writes sequence-free dry-run artefacts. Apply mode rederives
the same v2 assignment from frozen ``ft.csv``, writes authoritative
TRAIN/VALIDATION corpus files under ignored ``data/``, and freezes both
subsets. Does not mutate ``ft.csv``, touch REF/EVAL, write corpus_final,
or start fine-tuning.

Comparison reference = the complete frozen FT population.
``target_family`` is a secondary diagnostic only.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping, Sequence

from adapters.s4_scientific_common import ScientificProposalError
from adapters.s7_partition import (
    ABSDEV_COMPARISON_TUPLE_FIELDS,
    APPLY_MODE,
    COMPARISON_TUPLE_FIELDS,
    EVIDENCE_LEVELS,
    JSD_LOG_BASE,
    OBJECTIVE_PROFILE_ABSDEV,
    UNKNOWN_FAMILY,
    ClusterFeature,
    FeatureSpace,
    ObjectiveScore,
    _blank,
    assignment_integrity_gates,
    assign_length_regimes,
    assignment_signature,
    assert_no_sequence_leak,
    build_cluster_features,
    category_distribution_rows,
    evaluate_random_baselines,
    family_jsd_by_partition,
    format_float,
    format_fraction,
    input_unmutated,
    jsonable,
    jsonable_dumps,
    max_abs_proportion_deviation,
    parse_fraction,
    score_assignment,
    select_preview_assignment,
    semantic_cluster_set_hash,
    semantic_identity_set_hash,
    states_from_assignment,
    target_representation_diagnostics,
)

S7CSplitError = ScientificProposalError

TRAIN_LABEL = "TRAIN"
VALIDATION_LABEL = "VALIDATION"
S7C_REPORT_LABELS: tuple[str, ...] = (TRAIN_LABEL, VALIDATION_LABEL)
S7C_PLACEMENT_LABELS: tuple[str, ...] = (TRAIN_LABEL, VALIDATION_LABEL)
S7C_OBJECTIVE_PROFILE = OBJECTIVE_PROFILE_ABSDEV
S7C_COMPARISON_TUPLE_FIELDS: tuple[str, ...] = ABSDEV_COMPARISON_TUPLE_FIELDS
PREVIEW_MODE = "preview"
V2_PREVIEW_DIR = "data/interim/s7c_ft_split_preview_v2"
PROTECTED_PREVIEW_DIRS: frozenset[str] = frozenset(
    {
        "data/interim/s7c_ft_split_preview",
        "data/interim/s7c_ft_split_preview_jsd_v1",
    }
)
ALL_PREVIEW_DIRS: frozenset[str] = frozenset(
    {*PROTECTED_PREVIEW_DIRS, V2_PREVIEW_DIR}
)
FREEZE_DATE = "2026-09-21"
FREEZE_REASON = (
    "approved v2 FT train/validation assignment frozen before any model "
    "training, checkpoint selection, hyperparameter comparison, REF "
    "calibration or EVAL evaluation"
)
DEFAULT_S7C_FRACTIONS: dict[str, Fraction] = {
    TRAIN_LABEL: Fraction(9, 10),
    VALIDATION_LABEL: Fraction(1, 10),
}
FROZEN_FT_SHA256 = "b680ace037be73f650e386a34d97db915e4925a2dcd59e3053b7542b6d6fb4ff"
FROZEN_REF_SHA256 = "6c8bf5cdec625bdddb9f42b18a15f435826bebabb119dfc268ff737c89b7408d"
FROZEN_EVAL_SHA256 = "88fe1d8c2c78ed9dc478306c7390cff7016cd49541cfb1019d48ba8c1272c89d"
FROZEN_REF_IDENTITY_SET_HASH = (
    "54a74c8bb8ef67f36dd4b054d6ed43f201bd38d41d75244d9b69eb1583951abc"
)
FROZEN_REF_CLUSTER_SET_HASH = (
    "84afc5a5bb030db9cbdddb7246ceaab3457ef8eb02f1192575433d5f77f6cd82"
)
FROZEN_EVAL_IDENTITY_SET_HASH = (
    "47ef50345fae50f14e99547426dbf3a3c34ed0caf49574005fb3f1da94315406"
)
FROZEN_EVAL_CLUSTER_SET_HASH = (
    "c923af78ef7b191b569c5ead859982eb7711460a6537d0a70612a1101ffa8138"
)
FORBIDDEN_S7C_OUTPUT_NAMES: frozenset[str] = frozenset(
    {
        "ft_train.csv",
        "ft_validation.csv",
        "FT_TRAIN.csv",
        "FT_VALIDATION.csv",
        "corpus_final.csv",
        "corpus_final.txt",
        "ft.csv",
        "ref.csv",
        "eval.csv",
        "corpus_partitioned.csv",
    }
)
FORBIDDEN_S7C_APPLY_OUTPUT_NAMES: frozenset[str] = frozenset(
    {
        "corpus_final.csv",
        "corpus_final.txt",
        "ft.csv",
        "ref.csv",
        "eval.csv",
        "corpus_partitioned.csv",
    }
)
CLUSTER_FT_SPLIT_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "proposed_ft_split",
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
CLUSTER_FT_SPLIT_ASSIGNMENT_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "ft_split",
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
    "ft_split",
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
    "ft_split",
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
    "n_TRAIN",
    "share_TRAIN",
    "abs_share_dev_TRAIN",
    "n_VALIDATION",
    "share_VALIDATION",
    "abs_share_dev_VALIDATION",
    "n_subsets_represented",
)
EVIDENCE_DISTRIBUTION_COLUMNS: tuple[str, ...] = (
    "evidence_level",
    "n_global",
    "share_global",
    "n_TRAIN",
    "share_TRAIN",
    "abs_share_dev_TRAIN",
    "n_VALIDATION",
    "share_VALIDATION",
    "abs_share_dev_VALIDATION",
)
LENGTH_DISTRIBUTION_COLUMNS: tuple[str, ...] = (
    "length_regime",
    "n_global_cores",
    "share_global",
    "n_TRAIN_cores",
    "share_TRAIN",
    "abs_share_dev_TRAIN",
    "n_VALIDATION_cores",
    "share_VALIDATION",
    "abs_share_dev_VALIDATION",
)
SOURCE_DISTRIBUTION_COLUMNS: tuple[str, ...] = (
    "source_db",
    "n_global",
    "share_global",
    "n_TRAIN",
    "share_TRAIN",
    "abs_share_dev_TRAIN",
    "n_VALIDATION",
    "share_VALIDATION",
    "abs_share_dev_VALIDATION",
    "validation_count_zero",
)
FAMILY_DIAGNOSTIC_COLUMNS: tuple[str, ...] = (
    "target_family",
    "role",
    "n_global",
    "share_global",
    "n_TRAIN",
    "share_TRAIN",
    "n_VALIDATION",
    "share_VALIDATION",
)
DIVERGENCE_COLUMNS: tuple[str, ...] = (
    "criterion",
    "role",
    "J_TRAIN",
    "J_VALIDATION",
    "D_worst_subset",
    "log_base",
)
ABSDEV_COLUMNS: tuple[str, ...] = (
    "criterion",
    "role",
    "A_TRAIN",
    "A_VALIDATION",
    "M_worst_subset",
    "A_TRAIN_pp",
    "A_VALIDATION_pp",
    "M_pp",
)
TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "cluster_ft_split_preview.csv": CLUSTER_FT_SPLIT_COLUMNS,
    "ft_split_assignment.csv": CLUSTER_FT_SPLIT_ASSIGNMENT_COLUMNS,
    "train_identity_summary.csv": IDENTITY_SUMMARY_COLUMNS,
    "validation_identity_summary.csv": IDENTITY_SUMMARY_COLUMNS,
    "train_core_summary.csv": CORE_SUMMARY_COLUMNS,
    "validation_core_summary.csv": CORE_SUMMARY_COLUMNS,
    "target_distribution.csv": TARGET_DISTRIBUTION_COLUMNS,
    "evidence_distribution.csv": EVIDENCE_DISTRIBUTION_COLUMNS,
    "length_regime_distribution.csv": LENGTH_DISTRIBUTION_COLUMNS,
    "source_distribution.csv": SOURCE_DISTRIBUTION_COLUMNS,
    "target_family_diagnostic.csv": FAMILY_DIAGNOSTIC_COLUMNS,
    "divergence_metrics.csv": DIVERGENCE_COLUMNS,
    "absolute_deviation_metrics.csv": ABSDEV_COLUMNS,
}
APPLICATION_TABLE_NAMES: tuple[str, ...] = (
    "ft_split_assignment.csv",
    "train_identity_summary.csv",
    "validation_identity_summary.csv",
    "train_core_summary.csv",
    "validation_core_summary.csv",
    "target_distribution.csv",
    "evidence_distribution.csv",
    "length_regime_distribution.csv",
    "source_distribution.csv",
    "target_family_diagnostic.csv",
    "divergence_metrics.csv",
    "absolute_deviation_metrics.csv",
)
PARITY_TABLE_NAMES: tuple[str, ...] = (
    "train_identity_summary.csv",
    "validation_identity_summary.csv",
    "train_core_summary.csv",
    "validation_core_summary.csv",
    "target_distribution.csv",
    "evidence_distribution.csv",
    "length_regime_distribution.csv",
    "source_distribution.csv",
    "target_family_diagnostic.csv",
    "divergence_metrics.csv",
    "absolute_deviation_metrics.csv",
)


@dataclass(frozen=True)
class QuotaPair:
    n_TRAIN: int
    n_VALIDATION: int
    sse: Fraction

    @property
    def as_tuple(self) -> tuple[int, int]:
        return (self.n_TRAIN, self.n_VALIDATION)

    def remaining(self) -> dict[str, int]:
        return {TRAIN_LABEL: self.n_TRAIN, VALIDATION_LABEL: self.n_VALIDATION}

    def as_dict(self) -> dict[str, int]:
        return dict(self.remaining())


@dataclass(frozen=True)
class RefEvalFreezeSnapshot:
    ref_sha256: str
    eval_sha256: str
    ref_identity_set_hash: str
    ref_cluster_set_hash: str
    eval_identity_set_hash: str
    eval_cluster_set_hash: str
    n_ref_clusters: int
    n_eval_clusters: int
    cluster_overlap: int
    ref_cluster_ids: frozenset[str]
    eval_cluster_ids: frozenset[str]
    ref_identity_ids: frozenset[str]
    eval_identity_ids: frozenset[str]

    def semantic_tuple(self) -> tuple[str, ...]:
        return (
            self.ref_sha256,
            self.eval_sha256,
            self.ref_identity_set_hash,
            self.ref_cluster_set_hash,
            self.eval_identity_set_hash,
            self.eval_cluster_set_hash,
        )


def assert_not_forbidden_s7c_output_path(path: Any) -> None:
    name = getattr(path, "name", str(path).rsplit("/", 1)[-1])
    if name in FORBIDDEN_S7C_OUTPUT_NAMES:
        raise S7CSplitError(f"S7C preview must not write forbidden artefact {name}")


def assert_not_forbidden_s7c_apply_output_path(path: Any) -> None:
    name = getattr(path, "name", str(path).rsplit("/", 1)[-1])
    if name in FORBIDDEN_S7C_APPLY_OUTPUT_NAMES:
        raise S7CSplitError(f"S7C application must not write forbidden artefact {name}")


def derive_integer_quota_pairs(
    n_clusters: int,
    fractions: Mapping[str, Any] | None = None,
) -> list[QuotaPair]:
    """Return all tied-optimal integer (TRAIN, VALIDATION) cluster quotas.

    Minimises ``sum_p (n_p / N - desired_p)^2`` over non-negative integers
    with ``n_TRAIN + n_VALIDATION = N``. Does not arbitrarily round before
    evaluating, and does not break TRAIN/VALIDATION ties by label order.
    """
    if n_clusters < 0:
        raise S7CSplitError("n_clusters must be non-negative")
    if n_clusters == 0:
        raise S7CSplitError("n_clusters must be positive")
    desired = dict(DEFAULT_S7C_FRACTIONS)
    if fractions:
        for label in S7C_REPORT_LABELS:
            if label not in fractions:
                raise S7CSplitError(f"missing desired fraction for {label}")
            desired[label] = parse_fraction(fractions[label])
    if sum(desired.values()) != 1:
        raise S7CSplitError("desired train/validation fractions must sum to 1")
    best_sse: Fraction | None = None
    winners: list[QuotaPair] = []
    for n_train in range(n_clusters + 1):
        n_val = n_clusters - n_train
        sse = (
            (Fraction(n_train, n_clusters) - desired[TRAIN_LABEL]) ** 2
            + (Fraction(n_val, n_clusters) - desired[VALIDATION_LABEL]) ** 2
        )
        candidate = QuotaPair(n_train, n_val, sse)
        if best_sse is None or sse < best_sse:
            best_sse = sse
            winners = [candidate]
        elif sse == best_sse:
            winners.append(candidate)
    winners.sort(key=lambda item: item.as_tuple)
    return winners


def blank_partition_copy(
    rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Working copy with blank ``partition`` for S7B feature construction."""
    copied: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        item["partition"] = ""
        copied.append(item)
    return copied


def verify_ft_split_input(
    rows: Sequence[Mapping[str, str]],
    expected: Mapping[str, int] | None = None,
    *,
    forbidden_cluster_ids: Sequence[str] | None = None,
    forbidden_identity_ids: Sequence[str] | None = None,
    ref_cluster_ids: Sequence[str] | None = None,
    eval_cluster_ids: Sequence[str] | None = None,
    ref_identity_ids: Sequence[str] | None = None,
    eval_identity_ids: Sequence[str] | None = None,
) -> dict[str, int]:
    """Require every supplied row to be an FT identity with frozen S5 clusters."""
    if not rows:
        raise S7CSplitError("S7C input is empty")
    identities = [_blank(row.get("scientific_identity_id")) for row in rows]
    if any(not item for item in identities):
        raise S7CSplitError("every identity must have scientific_identity_id")
    if len(identities) != len(set(identities)):
        raise S7CSplitError("scientific_identity_id values are not unique")
    partitions = {_blank(row.get("partition")) for row in rows}
    if "REF" in partitions:
        raise S7CSplitError("REF rows/clusters cannot enter the S7C FT split")
    if "EVAL" in partitions:
        raise S7CSplitError("EVAL rows/clusters cannot enter the S7C FT split")
    if partitions != {"FT"}:
        raise S7CSplitError(
            f"S7C input must contain only partition=FT, got {sorted(partitions)}"
        )
    cluster_ids = {_blank(row.get("cluster_id")) for row in rows}
    if any(not item for item in cluster_ids):
        raise S7CSplitError("every identity must have a retained S5 cluster_id")
    identity_ids = set(identities)
    ref_clusters = set(ref_cluster_ids or ())
    eval_clusters = set(eval_cluster_ids or ())
    extra_forbidden = set(forbidden_cluster_ids or ())
    if cluster_ids & ref_clusters:
        raise S7CSplitError("REF clusters cannot enter the S7C FT split")
    if cluster_ids & eval_clusters:
        raise S7CSplitError("EVAL clusters cannot enter the S7C FT split")
    if cluster_ids & extra_forbidden:
        raise S7CSplitError("non-FT clusters cannot enter the S7C FT split")
    if identity_ids & set(ref_identity_ids or ()):
        raise S7CSplitError("REF identities cannot enter the S7C FT split")
    if identity_ids & set(eval_identity_ids or ()):
        raise S7CSplitError("EVAL identities cannot enter the S7C FT split")
    if identity_ids & set(forbidden_identity_ids or ()):
        raise S7CSplitError("non-FT identities cannot enter the S7C FT split")
    core_clusters: dict[str, set[str]] = {}
    for row in rows:
        core = _blank(row.get("sequence_core"))
        cluster_id = _blank(row.get("cluster_id"))
        core_clusters.setdefault(core, set()).add(cluster_id)
    if any(not core for core in core_clusters):
        raise S7CSplitError("sequence_core is required")
    multi = {core: sorted(clusters) for core, clusters in core_clusters.items() if len(clusters) > 1}
    if multi:
        raise S7CSplitError("a sequence_core maps to more than one cluster")
    evidence = Counter(_blank(row.get("evidence_level")) for row in rows)
    if evidence.get("E5", 0) != 0:
        raise S7CSplitError("S7C input must not contain E5 identities")
    unexpected_evidence = sorted(level for level in evidence if level not in EVIDENCE_LEVELS)
    if unexpected_evidence:
        raise S7CSplitError(f"unexpected evidence levels: {unexpected_evidence}")
    types = {_blank(row.get("target_type")) for row in rows}
    if types != {"protein"}:
        raise S7CSplitError(f"input target types must all be protein, got {sorted(types)}")
    observed = {
        "n_scientific_identities": len(rows),
        "n_distinct_sequence_core": len(core_clusters),
        "n_final_clusters": len(cluster_ids),
        "n_canonical_targets": len(
            {_blank(row.get("canonical_target_name")) for row in rows}
        ),
    }
    if expected:
        for key, wanted in expected.items():
            if observed.get(key) != wanted:
                raise S7CSplitError(f"{key}: expected {wanted}, got {observed.get(key)}")
    return observed


def file_sha256(path: Any) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_ref_eval_freeze(
    ref_rows: Sequence[Mapping[str, str]],
    eval_rows: Sequence[Mapping[str, str]],
    *,
    ref_sha256: str,
    eval_sha256: str,
) -> RefEvalFreezeSnapshot:
    ref_clusters = frozenset(_blank(row.get("cluster_id")) for row in ref_rows)
    eval_clusters = frozenset(_blank(row.get("cluster_id")) for row in eval_rows)
    ref_ids = frozenset(_blank(row.get("scientific_identity_id")) for row in ref_rows)
    eval_ids = frozenset(_blank(row.get("scientific_identity_id")) for row in eval_rows)
    if any(not item for item in ref_clusters) or any(not item for item in eval_clusters):
        raise S7CSplitError("REF/EVAL freeze snapshot found a blank cluster_id")
    return RefEvalFreezeSnapshot(
        ref_sha256=ref_sha256,
        eval_sha256=eval_sha256,
        ref_identity_set_hash=semantic_identity_set_hash(ref_rows),
        ref_cluster_set_hash=semantic_cluster_set_hash(ref_rows),
        eval_identity_set_hash=semantic_identity_set_hash(eval_rows),
        eval_cluster_set_hash=semantic_cluster_set_hash(eval_rows),
        n_ref_clusters=len(ref_clusters),
        n_eval_clusters=len(eval_clusters),
        cluster_overlap=len(ref_clusters & eval_clusters),
        ref_cluster_ids=ref_clusters,
        eval_cluster_ids=eval_clusters,
        ref_identity_ids=ref_ids,
        eval_identity_ids=eval_ids,
    )


def assert_ref_eval_matches_expected(
    snapshot: RefEvalFreezeSnapshot,
    expected: Mapping[str, Any],
) -> None:
    checks = (
        ("ref_sha256", snapshot.ref_sha256, expected.get("ref_sha256")),
        ("eval_sha256", snapshot.eval_sha256, expected.get("eval_sha256")),
        (
            "ref_identity_set_hash",
            snapshot.ref_identity_set_hash,
            expected.get("ref_identity_set_hash"),
        ),
        (
            "ref_cluster_set_hash",
            snapshot.ref_cluster_set_hash,
            expected.get("ref_cluster_set_hash"),
        ),
        (
            "eval_identity_set_hash",
            snapshot.eval_identity_set_hash,
            expected.get("eval_identity_set_hash"),
        ),
        (
            "eval_cluster_set_hash",
            snapshot.eval_cluster_set_hash,
            expected.get("eval_cluster_set_hash"),
        ),
    )
    mismatches = [
        f"{name}: expected {wanted}, got {got}"
        for name, got, wanted in checks
        if wanted not in {None, ""} and got != wanted
    ]
    if mismatches:
        raise S7CSplitError(
            "REF/EVAL freeze guard failed: " + "; ".join(mismatches)
        )
    expected_ref_n = expected.get("n_ref_clusters")
    expected_eval_n = expected.get("n_eval_clusters")
    if expected_ref_n is not None and snapshot.n_ref_clusters != int(expected_ref_n):
        raise S7CSplitError("REF cluster count drifted from freeze")
    if expected_eval_n is not None and snapshot.n_eval_clusters != int(expected_eval_n):
        raise S7CSplitError("EVAL cluster count drifted from freeze")
    if snapshot.cluster_overlap != 0:
        raise S7CSplitError("REF/EVAL cluster overlap is not zero")


def assert_ref_eval_unchanged(
    before: RefEvalFreezeSnapshot,
    after: RefEvalFreezeSnapshot,
) -> None:
    if before.semantic_tuple() != after.semantic_tuple():
        raise S7CSplitError("REF/EVAL freeze hashes changed during S7C")
    if before.n_ref_clusters != after.n_ref_clusters:
        raise S7CSplitError("REF cluster count changed during S7C")
    if before.n_eval_clusters != after.n_eval_clusters:
        raise S7CSplitError("EVAL cluster count changed during S7C")
    if before.cluster_overlap != after.cluster_overlap:
        raise S7CSplitError("REF/EVAL overlap changed during S7C")


def frozen_ref_eval_expected(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(config or {})
    return {
        "ref_sha256": payload.get("expected_ref_sha256") or FROZEN_REF_SHA256,
        "eval_sha256": payload.get("expected_eval_sha256") or FROZEN_EVAL_SHA256,
        "ref_identity_set_hash": payload.get("expected_ref_identity_set_hash")
        or FROZEN_REF_IDENTITY_SET_HASH,
        "ref_cluster_set_hash": payload.get("expected_ref_cluster_set_hash")
        or FROZEN_REF_CLUSTER_SET_HASH,
        "eval_identity_set_hash": payload.get("expected_eval_identity_set_hash")
        or FROZEN_EVAL_IDENTITY_SET_HASH,
        "eval_cluster_set_hash": payload.get("expected_eval_cluster_set_hash")
        or FROZEN_EVAL_CLUSTER_SET_HASH,
        "n_ref_clusters": int(payload.get("expected_ref_clusters") or 80),
        "n_eval_clusters": int(payload.get("expected_eval_clusters") or 79),
    }


def format_pp(value: float, digits: int = 12) -> str:
    return format_float(value * 100.0, digits)


def annotate_abs_share_deviations(
    rows: Sequence[Mapping[str, str]],
    *,
    labels: Sequence[str] = S7C_REPORT_LABELS,
) -> list[dict[str, str]]:
    annotated: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        global_share = item.get("share_global") or "0"
        try:
            g = float(global_share)
        except ValueError:
            g = 0.0
        for label in labels:
            raw = item.get(f"share_{label}") or "0"
            try:
                p = float(raw) if raw else 0.0
            except ValueError:
                p = 0.0
            item[f"abs_share_dev_{label}"] = format_float(abs(p - g))
        annotated.append(item)
    return annotated


def assert_preview_dir_not_protected(path: Any, repo_root: Any | None = None) -> None:
    raw = str(path)
    normalised = raw.replace("\\", "/")
    for protected in PROTECTED_PREVIEW_DIRS:
        if normalised.rstrip("/") == protected.rstrip("/") or normalised.endswith(
            "/" + protected
        ):
            raise S7CSplitError(
                f"S7C v2 preview must not overwrite preserved v1 directory {protected}"
            )
    if repo_root is not None:
        try:
            relative = path.resolve().relative_to(repo_root.resolve())
        except ValueError:
            relative = None
        if relative is not None and str(relative).replace("\\", "/") in PROTECTED_PREVIEW_DIRS:
            raise S7CSplitError(
                f"S7C v2 preview must not overwrite preserved v1 directory {relative}"
            )


def select_s7c_assignment(
    features: Mapping[str, ClusterFeature],
    space: FeatureSpace,
    quota_candidates: Sequence[QuotaPair],
    *,
    max_passes: int = 10_000,
) -> dict[str, Any]:
    return select_preview_assignment(
        features,
        space,
        quota_candidates,
        max_passes=max_passes,
        partition_labels=S7C_REPORT_LABELS,
        placement_labels=S7C_PLACEMENT_LABELS,
        log_prefix="S7C",
        objective_profile=S7C_OBJECTIVE_PROFILE,
    )


def score_s7c_assignment(
    assignment: Mapping[str, str],
    features: Mapping[str, ClusterFeature],
    space: FeatureSpace,
) -> ObjectiveScore:
    return score_assignment(
        assignment,
        features,
        space,
        partition_labels=S7C_REPORT_LABELS,
        objective_profile=S7C_OBJECTIVE_PROFILE,
    )


def s7c_integrity_gates(
    corpus_rows: Sequence[Mapping[str, str]],
    assignment: Mapping[str, str],
    features: Mapping[str, ClusterFeature],
    quotas: QuotaPair,
    *,
    ref_cluster_ids: Sequence[str] | None = None,
    eval_cluster_ids: Sequence[str] | None = None,
    ref_identity_ids: Sequence[str] | None = None,
    eval_identity_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    unknown = sorted(set(assignment.values()) - set(S7C_REPORT_LABELS))
    if unknown:
        raise S7CSplitError(f"S7C assignment used non-train/validation labels: {unknown}")
    base = assignment_integrity_gates(corpus_rows, assignment, features, quotas)
    counts = Counter(assignment.values())
    assigned_clusters = set(assignment)
    assigned_identities = set(base["identity_partitions"])
    ref_clusters = set(ref_cluster_ids or ())
    eval_clusters = set(eval_cluster_ids or ())
    ref_ids = set(ref_identity_ids or ())
    eval_ids = set(eval_identity_ids or ())
    partitions = {_blank(row.get("partition")) for row in corpus_rows}
    return {
        "clusters_assigned_exactly_once": True,
        "identities_assigned_exactly_once": True,
        "cores_cross_partitions": 0,
        "cluster_crossings": 0,
        "n_identities": base["n_identities"],
        "n_cores": base["n_cores"],
        "n_clusters": base["n_clusters"],
        "n_TRAIN": counts[TRAIN_LABEL],
        "n_VALIDATION": counts[VALIDATION_LABEL],
        "E5": base["E5"],
        "non_protein": base["non_protein"],
        "identity_sum": base["identity_sum"],
        "core_sum": base["core_sum"],
        "cluster_sum": counts[TRAIN_LABEL] + counts[VALIDATION_LABEL],
        "ref_clusters_in_split": len(assigned_clusters & ref_clusters),
        "eval_clusters_in_split": len(assigned_clusters & eval_clusters),
        "ref_identities_in_split": len(assigned_identities & ref_ids),
        "eval_identities_in_split": len(assigned_identities & eval_ids),
        "input_partition_labels": sorted(partitions),
        "top_level_partition_altered": partitions != {"FT"},
    }


def s7c_target_diagnostics(
    corpus_rows: Sequence[Mapping[str, str]],
    assignment: Mapping[str, str],
) -> dict[str, Any]:
    diag = target_representation_diagnostics(
        corpus_rows, assignment, partition_labels=S7C_REPORT_LABELS
    )
    diag["targets_only_train"] = diag["targets_exclusive"][TRAIN_LABEL]
    diag["targets_only_validation"] = diag["targets_exclusive"][VALIDATION_LABEL]
    diag["targets_shared"] = diag["targets_in_two_partitions"]
    diag["targets_absent_from_validation"] = (
        diag["n_targets"] - diag["targets_represented"][VALIDATION_LABEL]
    )
    diag["targets_absent_from_train"] = (
        diag["n_targets"] - diag["targets_represented"][TRAIN_LABEL]
    )
    return diag


def _identity_summary_row(
    label: str,
    state: Any,
    space: FeatureSpace,
) -> dict[str, str]:
    n_id = state.n_identities
    return {
        "ft_split": label,
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


def _core_summary_row(
    label: str,
    state: Any,
    space: FeatureSpace,
) -> dict[str, str]:
    n_core = state.n_cores
    return {
        "ft_split": label,
        "n_distinct_cores": str(n_core),
        "core_fraction": format_fraction(n_core, space.n_cores),
        "n_short_cores": str(int(state.length.get("short", 0))),
        "n_long_cores": str(int(state.length.get("long", 0))),
        "prop_short": format_fraction(int(state.length.get("short", 0)), n_core),
        "prop_long": format_fraction(int(state.length.get("long", 0)), n_core),
    }


def build_s7c_preview_tables(
    *,
    features: Mapping[str, ClusterFeature],
    space: FeatureSpace,
    assignment: Mapping[str, str],
    score: ObjectiveScore,
    family_js: Mapping[str, float],
) -> dict[str, list[dict[str, str]]]:
    states = states_from_assignment(
        assignment, features, space, partition_labels=S7C_REPORT_LABELS
    )
    cluster_rows = []
    for cluster_id in sorted(features):
        row = features[cluster_id].preview_row(assignment[cluster_id])
        row["proposed_ft_split"] = row.pop("proposed_partition")
        cluster_rows.append(row)
    train_identity = [_identity_summary_row(TRAIN_LABEL, states[TRAIN_LABEL], space)]
    val_identity = [_identity_summary_row(VALIDATION_LABEL, states[VALIDATION_LABEL], space)]
    train_core = [_core_summary_row(TRAIN_LABEL, states[TRAIN_LABEL], space)]
    val_core = [_core_summary_row(VALIDATION_LABEL, states[VALIDATION_LABEL], space)]
    target_rows = annotate_abs_share_deviations(
        category_distribution_rows(
            space.targets,
            space.global_target,
            states,
            attr="target",
            name_field="canonical_target_name",
            grain="identity",
            partition_labels=S7C_REPORT_LABELS,
        )
    )
    for row in target_rows:
        row["n_subsets_represented"] = row.pop("n_partitions_represented")
    evidence_rows = annotate_abs_share_deviations(
        category_distribution_rows(
            space.evidence,
            space.global_evidence,
            states,
            attr="evidence",
            name_field="evidence_level",
            grain="identity",
            partition_labels=S7C_REPORT_LABELS,
        )
    )
    length_rows = annotate_abs_share_deviations(
        category_distribution_rows(
            space.length_regimes,
            space.global_length,
            states,
            attr="length",
            name_field="length_regime",
            grain="length",
            partition_labels=S7C_REPORT_LABELS,
        )
    )
    source_rows = annotate_abs_share_deviations(
        category_distribution_rows(
            space.sources,
            space.global_source,
            states,
            attr="source",
            name_field="source_db",
            grain="identity",
            partition_labels=S7C_REPORT_LABELS,
        )
    )
    for row in source_rows:
        row["validation_count_zero"] = "yes" if int(row["n_VALIDATION"]) == 0 else "no"
    family_rows = category_distribution_rows(
        space.families,
        space.global_family,
        states,
        attr="family",
        name_field="target_family",
        grain="identity",
        partition_labels=S7C_REPORT_LABELS,
    )
    for row in family_rows:
        row["role"] = "secondary diagnostic — not optimisation objective"
    divergence_rows = []
    for criterion, j_map, d_value, role in (
        ("target", score.j_target, score.d_target, "JSD diagnostic / tie-break"),
        ("evidence", score.j_evidence, score.d_evidence, "JSD diagnostic / tie-break"),
        ("length_regime", score.j_length, score.d_length, "JSD diagnostic / tie-break"),
        ("source", score.j_source, score.d_source, "JSD diagnostic / tie-break"),
        (
            "target_family",
            family_js,
            max(family_js.values()) if family_js else 0.0,
            "secondary diagnostic — not optimisation objective",
        ),
    ):
        divergence_rows.append(
            {
                "criterion": criterion,
                "role": role,
                "J_TRAIN": format_float(j_map[TRAIN_LABEL]),
                "J_VALIDATION": format_float(j_map[VALIDATION_LABEL]),
                "D_worst_subset": format_float(d_value),
                "log_base": format_float(score.log_base, 1),
            }
        )
    divergence_rows.extend(
        [
            {
                "criterion": "O1",
                "role": "JSD diagnostic (not primary)",
                "J_TRAIN": "",
                "J_VALIDATION": "",
                "D_worst_subset": format_float(score.o1),
                "log_base": format_float(score.log_base, 1),
            },
            {
                "criterion": "O3",
                "role": "JSD diagnostic (not primary)",
                "J_TRAIN": "",
                "J_VALIDATION": "",
                "D_worst_subset": format_float(score.o3),
                "log_base": format_float(score.log_base, 1),
            },
        ]
    )
    absdev_rows = []
    for criterion, a_map, m_value, role in (
        ("target", score.a_target, score.m_target, "primary"),
        ("evidence", score.a_evidence, score.m_evidence, "primary"),
        ("length_regime", score.a_length, score.m_length, "primary"),
        ("source", score.a_source, score.m_source, "primary"),
    ):
        a_train = float(a_map.get(TRAIN_LABEL, 0.0))
        a_val = float(a_map.get(VALIDATION_LABEL, 0.0))
        absdev_rows.append(
            {
                "criterion": criterion,
                "role": role,
                "A_TRAIN": format_float(a_train),
                "A_VALIDATION": format_float(a_val),
                "M_worst_subset": format_float(m_value),
                "A_TRAIN_pp": format_pp(a_train),
                "A_VALIDATION_pp": format_pp(a_val),
                "M_pp": format_pp(m_value),
            }
        )
    absdev_rows.extend(
        [
            {
                "criterion": "R1",
                "role": "primary objective",
                "A_TRAIN": "",
                "A_VALIDATION": "",
                "M_worst_subset": format_float(score.r1),
                "A_TRAIN_pp": "",
                "A_VALIDATION_pp": "",
                "M_pp": format_pp(score.r1),
            },
            {
                "criterion": "R3",
                "role": "primary objective",
                "A_TRAIN": "",
                "A_VALIDATION": "",
                "M_worst_subset": format_float(score.r3),
                "A_TRAIN_pp": "",
                "A_VALIDATION_pp": "",
                "M_pp": format_pp(score.r3),
            },
        ]
    )
    return {
        "cluster_ft_split_preview.csv": cluster_rows,
        "train_identity_summary.csv": train_identity,
        "validation_identity_summary.csv": val_identity,
        "train_core_summary.csv": train_core,
        "validation_core_summary.csv": val_core,
        "target_distribution.csv": target_rows,
        "evidence_distribution.csv": evidence_rows,
        "length_regime_distribution.csv": length_rows,
        "source_distribution.csv": source_rows,
        "target_family_diagnostic.csv": family_rows,
        "divergence_metrics.csv": divergence_rows,
        "absolute_deviation_metrics.csv": absdev_rows,
    }


def _worst_share_deviation(
    rows: Sequence[Mapping[str, str]],
    name_field: str,
    label: str,
) -> tuple[str, float]:
    worst_name = ""
    worst = -1.0
    for row in rows:
        try:
            g = float(row["share_global"])
            raw = row.get(f"share_{label}") or "0"
            p = float(raw) if raw else 0.0
        except (TypeError, ValueError):
            continue
        dev = abs(p - g)
        if dev > worst:
            worst = dev
            worst_name = str(row.get(name_field) or "")
    return worst_name, (worst if worst >= 0.0 else 0.0)


def _metric_block(score: ObjectiveScore) -> list[str]:
    def _pair(name: str, a_map: Mapping[str, float], m_value: float) -> list[str]:
        a_train = float(a_map.get(TRAIN_LABEL, 0.0))
        a_val = float(a_map.get(VALIDATION_LABEL, 0.0))
        return [
            f"- A_{name}(TRAIN) = {format_float(a_train)} ({format_pp(a_train)} pp)",
            f"- A_{name}(VALIDATION) = {format_float(a_val)} ({format_pp(a_val)} pp)",
            f"- M_{name} = {format_float(m_value)} ({format_pp(m_value)} pp)",
        ]

    lines = [
        "## Primary comparability (maximum absolute category-proportion deviation)",
        "",
        "Units are fractions of the relevant grain (identity or distinct core).",
        "Percentage points = fraction × 100. Complete frozen FT support.",
        "An absent category contributes its full FT proportion as deviation.",
        "",
    ]
    lines.extend(_pair("target", score.a_target, score.m_target))
    lines.extend(_pair("evidence", score.a_evidence, score.m_evidence))
    lines.extend(_pair("length", score.a_length, score.m_length))
    lines.extend(_pair("source", score.a_source, score.m_source))
    lines.extend(
        [
            f"- R1 = {format_float(score.r1)} ({format_pp(score.r1)} pp)",
            f"- descending M vector = {list(score.m_lex_vector)}",
            f"- R3 = {format_float(score.r3)} ({format_pp(score.r3)} pp)",
            "",
        ]
    )
    return lines


def family_known_share(family_rows: Sequence[Mapping[str, str]]) -> str:
    known = 0
    total = 0
    for row in family_rows:
        n = int(row["n_global"])
        total += n
        if row["target_family"] != UNKNOWN_FAMILY:
            known += n
    return format_fraction(known, total) if total else ""


def build_s7c_preview_report(
    *,
    input_sha256: str,
    observed: Mapping[str, int],
    gmm: Mapping[str, Any],
    n_short: int,
    n_long: int,
    quota_candidates: Sequence[tuple[int, int]],
    selected_quotas: QuotaPair,
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
    ref_eval_before: Mapping[str, Any],
    ref_eval_after: Mapping[str, Any],
) -> str:
    train_ident = list(tables["train_identity_summary.csv"])[0]
    val_ident = list(tables["validation_identity_summary.csv"])[0]
    train_core = list(tables["train_core_summary.csv"])[0]
    val_core = list(tables["validation_core_summary.csv"])[0]
    by_label = {TRAIN_LABEL: train_ident, VALIDATION_LABEL: val_ident}
    core_by_label = {TRAIN_LABEL: train_core, VALIDATION_LABEL: val_core}
    source_rows = list(tables["source_distribution.csv"])
    evidence_rows = list(tables["evidence_distribution.csv"])
    length_rows = list(tables["length_regime_distribution.csv"])
    family_rows = list(tables["target_family_diagnostic.csv"])
    target_rows = list(tables["target_distribution.csv"])
    target_worst_val_name, target_worst_val = _worst_share_deviation(
        target_rows, "canonical_target_name", VALIDATION_LABEL
    )
    target_worst_train_name, target_worst_train = _worst_share_deviation(
        target_rows, "canonical_target_name", TRAIN_LABEL
    )
    if target_worst_val >= target_worst_train:
        target_responsible, target_responsible_dev = target_worst_val_name, target_worst_val
        target_responsible_subset = VALIDATION_LABEL
    else:
        target_responsible, target_responsible_dev = target_worst_train_name, target_worst_train
        target_responsible_subset = TRAIN_LABEL
    evidence_worst_val_name, evidence_worst_val = _worst_share_deviation(
        evidence_rows, "evidence_level", VALIDATION_LABEL
    )
    evidence_worst_train_name, evidence_worst_train = _worst_share_deviation(
        evidence_rows, "evidence_level", TRAIN_LABEL
    )
    if evidence_worst_val >= evidence_worst_train:
        evidence_responsible = evidence_worst_val_name
    else:
        evidence_responsible = evidence_worst_train_name
    length_worst_val_name, length_worst_val = _worst_share_deviation(
        length_rows, "length_regime", VALIDATION_LABEL
    )
    length_worst_train_name, length_worst_train = _worst_share_deviation(
        length_rows, "length_regime", TRAIN_LABEL
    )
    if length_worst_val >= length_worst_train:
        length_responsible = length_worst_val_name
    else:
        length_responsible = length_worst_train_name

    def _part_block(label: str) -> list[str]:
        ident = by_label[label]
        core = core_by_label[label]
        return [
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

    source_lines = [
        "source_db counts by subset (identity-grain `source_db`; global = complete frozen FT):",
        "",
        "| source | full FT count/share | TRAIN count/share | VALIDATION count/share | validation abs share deviation | validation count = 0 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    absent_sources: list[str] = []
    for row in source_rows:
        zero = int(row["n_VALIDATION"]) == 0
        if zero:
            absent_sources.append(row["source_db"])
        source_lines.append(
            f"| {row['source_db']} | {row['n_global']} ({row['share_global']}) | "
            f"{row['n_TRAIN']} ({row['share_TRAIN']}) | "
            f"{row['n_VALIDATION']} ({row['share_VALIDATION']}) | "
            f"{row['abs_share_dev_VALIDATION']} | {'yes' if zero else 'no'} |"
        )
    source_worst_val_name, source_worst_val = _worst_share_deviation(
        source_rows, "source_db", VALIDATION_LABEL
    )
    source_worst_train_name, source_worst_train = _worst_share_deviation(
        source_rows, "source_db", TRAIN_LABEL
    )
    if source_worst_val >= source_worst_train:
        source_responsible, source_responsible_dev = source_worst_val_name, source_worst_val
        source_responsible_subset = VALIDATION_LABEL
    else:
        source_responsible, source_responsible_dev = source_worst_train_name, source_worst_train
        source_responsible_subset = TRAIN_LABEL
    source_lines.extend(
        [
            "",
            f"- sources with VALIDATION count = 0: {len(absent_sources)}"
            + (f" ({', '.join(absent_sources)})" if absent_sources else " (none)"),
            (
                f"- maximum source share deviation M_source = {format_float(score.m_source)}"
                f" ({format_pp(score.m_source)} pp); category = {source_responsible}"
                f" in {source_responsible_subset} (deviation {format_float(source_responsible_dev)})"
            ),
            "- absent sources are reported, not automatically failed.",
            "",
        ]
    )
    top_lines = [
        "Top 15 FT targets (identity grain; validation need not contain every target):",
        "",
        "| target | full FT | TRAIN | VALIDATION |",
        "| --- | --- | --- | --- |",
    ]
    for row in target_diag["top_targets"]:
        top_lines.append(
            f"| {row['canonical_target_name']} | {row['n_global']} | "
            f"{row[f'n_{TRAIN_LABEL}']} | {row[f'n_{VALIDATION_LABEL}']} |"
        )
    if random_diag:
        random_lines = [
            "## Random whole-cluster baseline (diagnostic only)",
            "",
            "This baseline is not eligible to become the scientific split.",
            "Some random splits may outperform individual secondary criteria",
            "while being worse under the absolute-deviation hierarchy.",
            "",
            f"- seeds = {random_diag['seeds']}",
            f"- random R1 min/mean/max = {format_float(random_diag['R1_min'])} / "
            f"{format_float(random_diag['R1_mean'])} / {format_float(random_diag['R1_max'])}",
            f"- optimised R1 = {format_float(score.r1)} ({format_pp(score.r1)} pp)",
            f"- random M_target min = {format_float(random_diag['M_target_min'])}; "
            f"optimised M_target = {format_float(score.m_target)}",
            f"- random M_evidence min = {format_float(random_diag['M_evidence_min'])}; "
            f"optimised M_evidence = {format_float(score.m_evidence)}",
            f"- random M_length min = {format_float(random_diag['M_length_min'])}; "
            f"optimised M_length = {format_float(score.m_length)}",
            f"- random M_source min = {format_float(random_diag['M_source_min'])}; "
            f"optimised M_source = {format_float(score.m_source)}",
            f"- random O1 (JSD) min/mean/max = {format_float(random_diag['O1_min'])} / "
            f"{format_float(random_diag['O1_mean'])} / {format_float(random_diag['O1_max'])}",
            f"- optimised O1 (JSD diagnostic) = {format_float(score.o1)}",
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
        random_lines = [
            "## Random whole-cluster baseline (diagnostic only)",
            "",
            "Omitted.",
            "",
        ]
    known_family = family_known_share(family_rows)
    unknown_n = sum(
        int(row["n_global"])
        for row in family_rows
        if row["target_family"] == UNKNOWN_FAMILY
    )
    known_n = sum(
        int(row["n_global"])
        for row in family_rows
        if row["target_family"] != UNKNOWN_FAMILY
    )
    lines = [
        "# S7C FT train/validation preview v2 — not frozen",
        "",
        "This artefact is a dry-run/preview of a deterministic whole-cluster",
        "split of frozen FT into TRAIN/VALIDATION using the revised",
        "maximum-absolute-proportion-deviation objective. The v1 raw-JSD",
        "preview is preserved and was not approved. Authoritative",
        "`ft_train.csv` / `ft_validation.csv` are **not written**. REF and",
        "EVAL remain frozen and byte-identical. This preview must not be used",
        "for model development, fine-tuning, or hyperparameter decisions.",
        "",
        "## Frozen authorities",
        "",
        f"- ft.csv SHA-256 = `{input_sha256}`",
        f"- FT identities = {observed['n_scientific_identities']}",
        f"- FT distinct sequence_core = {observed['n_distinct_sequence_core']}",
        f"- FT clusters = {observed['n_final_clusters']}",
        f"- FT canonical targets = {observed['n_canonical_targets']}",
        f"- REF SHA before = `{ref_eval_before['ref_sha256']}`",
        f"- REF SHA after = `{ref_eval_after['ref_sha256']}`",
        f"- EVAL SHA before = `{ref_eval_before['eval_sha256']}`",
        f"- EVAL SHA after = `{ref_eval_after['eval_sha256']}`",
        "",
        "## Frozen S6 length-regime provenance",
        "",
        "- assignment_method = `gmm_k2_maximum_posterior`",
        "- GMM source = frozen S6 `bimodality.json` `gmm_2` (not refit)",
        f"- component means = {list(gmm['means'])}",
        f"- component weights = {list(gmm['weights'])}",
        "- grain = distinct `sequence_core`",
        f"- FT short cores = {n_short}",
        f"- FT long cores = {n_long}",
        "",
        "## Integer cluster quotas",
        "",
        "- desired fractions TRAIN = 0.90, VALIDATION = 0.10 of FT cluster count",
        f"- tied-optimal candidates (n_TRAIN, n_VALIDATION) = {list(quota_candidates)}",
        (
            f"- selected by scientific objective = "
            f"({selected_quotas.n_TRAIN}, {selected_quotas.n_VALIDATION})"
        ),
        "",
        "## Objective",
        "",
        "- reference distribution = complete frozen FT",
        "- primary metric = maximum absolute category-proportion deviation",
        "- A_c(p) = max_k |P_p,c(k) - P_FT,c(k)| on complete FT support",
        "- M_c = max(A_c(TRAIN), A_c(VALIDATION))",
        "- R1 = max(M_target, M_evidence, M_length, M_source)",
        "- R2 = lexicographic minimum of the four M values sorted descending",
        "- R3 = M_target + M_evidence + M_length + M_source",
        "- JSD (log2 bits) is diagnostic and the next scientific tie-break only",
        "- JSD tie-break = descending D vector, then D_target+D_evidence+D_length+D_source",
        "- final tie-break = sorted `cluster_id:ft_split` signature",
        "- arbitrary manually chosen criterion weights = none",
        "- new hard source coverage constraint = no",
        "- target_family in primary objective = no",
        "",
        f"- greedy R1 before local search = {format_float(greedy_o1)}",
        f"- accepted pairwise swaps = {n_accepted_swaps}",
        f"- local-search passes (including terminal no-improve pass) = {n_local_search_passes}",
        f"- local-search converged (no-improve pass) = {local_search_converged}",
        "",
        "## Preview split sizes",
        "",
        "| subset | clusters | cluster fraction | identities | identity fraction | cores | core fraction |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for label in S7C_REPORT_LABELS:
        ident = by_label[label]
        core = core_by_label[label]
        lines.append(
            f"| {label} | {ident['n_clusters']} | {ident['cluster_fraction']} | "
            f"{ident['n_identities']} | {ident['identity_fraction']} | "
            f"{core['n_distinct_cores']} | {core['core_fraction']} |"
        )
    lines.extend(["", "## Per-subset primary comparability", ""])
    for label in S7C_REPORT_LABELS:
        lines.extend(_part_block(label))
    lines.extend(_metric_block(score))
    lines.extend(["### Evidence (identity grain; global = complete FT)", ""])
    for row in evidence_rows:
        lines.append(
            f"- {row['evidence_level']}: FT {row['n_global']} ({row['share_global']}); "
            + ", ".join(
                f"{label} {row[f'n_{label}']} ({row[f'share_{label}']})"
                for label in S7C_REPORT_LABELS
            )
            + f"; abs share dev TRAIN/VALIDATION = {row['abs_share_dev_TRAIN']}/{row['abs_share_dev_VALIDATION']}"
        )
    lines.extend(
        [
            (
                f"- M_evidence = {format_float(score.m_evidence)} ({format_pp(score.m_evidence)} pp);"
                f" category = {evidence_responsible}"
            ),
            "",
            "### Length regime (distinct-core grain)",
            "",
        ]
    )
    for row in length_rows:
        lines.append(
            f"- {row['length_regime']}: FT {row['n_global_cores']} ({row['share_global']}); "
            + ", ".join(
                f"{label} {row[f'n_{label}_cores']} ({row[f'share_{label}']})"
                for label in S7C_REPORT_LABELS
            )
            + f"; abs share dev TRAIN/VALIDATION = {row['abs_share_dev_TRAIN']}/{row['abs_share_dev_VALIDATION']}"
        )
    lines.extend(
        [
            (
                f"- M_length = {format_float(score.m_length)} ({format_pp(score.m_length)} pp);"
                f" category = {length_responsible}"
            ),
            "",
            "### Source",
            "",
        ]
    )
    lines.extend(source_lines)
    lines.extend(
        [
            "## JSD diagnostics (log2 bits; full FT support; tie-break only)",
            "",
            f"- J_target(TRAIN) = {format_float(score.j_target[TRAIN_LABEL])}",
            f"- J_target(VALIDATION) = {format_float(score.j_target[VALIDATION_LABEL])}",
            f"- D_target = {format_float(score.d_target)}",
            f"- J_evidence(TRAIN) = {format_float(score.j_evidence[TRAIN_LABEL])}",
            f"- J_evidence(VALIDATION) = {format_float(score.j_evidence[VALIDATION_LABEL])}",
            f"- D_evidence = {format_float(score.d_evidence)}",
            f"- J_length(TRAIN) = {format_float(score.j_length[TRAIN_LABEL])}",
            f"- J_length(VALIDATION) = {format_float(score.j_length[VALIDATION_LABEL])}",
            f"- D_length = {format_float(score.d_length)}",
            f"- J_source(TRAIN) = {format_float(score.j_source[TRAIN_LABEL])}",
            f"- J_source(VALIDATION) = {format_float(score.j_source[VALIDATION_LABEL])}",
            f"- D_source = {format_float(score.d_source)}",
            f"- O1 (JSD diagnostic) = {format_float(score.o1)}",
            f"- descending D vector = {list(score.lex_vector)}",
            f"- O3 (JSD diagnostic) = {format_float(score.o3)}",
            "",
            "JSD is not the primary optimisation scale. It is retained as a",
            "diagnostic and as the fourth scientific tie-break after R1/M-lex/R3.",
            "",
            "## Target representation diagnostics",
            "",
            f"- targets represented TRAIN = {target_diag['targets_represented'][TRAIN_LABEL]}",
            f"- targets represented VALIDATION = {target_diag['targets_represented'][VALIDATION_LABEL]}",
            f"- targets only in TRAIN = {target_diag['targets_only_train']}",
            f"- targets only in VALIDATION = {target_diag['targets_only_validation']}",
            f"- targets shared TRAIN/VALIDATION = {target_diag['targets_shared']}",
            f"- targets absent from VALIDATION = {target_diag['targets_absent_from_validation']}",
            f"- singleton-target identities TRAIN/VALIDATION = "
            f"{target_diag['singleton_target_identities'][TRAIN_LABEL]} / "
            f"{target_diag['singleton_target_identities'][VALIDATION_LABEL]}",
            f"- singleton-target clusters TRAIN/VALIDATION = "
            f"{target_diag['singleton_target_clusters'][TRAIN_LABEL]} / "
            f"{target_diag['singleton_target_clusters'][VALIDATION_LABEL]}",
            (
                f"- maximum target-share absolute deviation M_target = "
                f"{format_float(score.m_target)} ({format_pp(score.m_target)} pp); "
                f"category = {target_responsible} in {target_responsible_subset} "
                f"(deviation {format_float(target_responsible_dev)})"
            ),
            "",
            "Validation is not required to contain every target. Singleton-target",
            "absence is a whole-cluster coverage limitation, not leakage. Rare",
            "singleton absence is not strongly penalised because each contributes",
            "only a small FT proportion. There is no target-coverage hard constraint.",
            "",
        ]
    )
    lines.extend(top_lines)
    lines.extend(
        [
            "",
            "## Secondary target-family diagnostic — not optimisation objective",
            "",
            f"- known-family identities = {known_n}",
            f"- unknown-family identities = {unknown_n}",
            f"- known-family identity share (FT diagnostic) = {known_family}",
            f"- J_family(TRAIN) = {format_float(family_js[TRAIN_LABEL])}",
            f"- J_family(VALIDATION) = {format_float(family_js[VALIDATION_LABEL])}",
            f"- D_family (diagnostic) = {format_float(max(family_js.values()))}",
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
            f"- FT clusters assigned exactly once = {integrity['clusters_assigned_exactly_once']}",
            f"- FT identities assigned exactly once = {integrity['identities_assigned_exactly_once']}",
            f"- cores cross train/validation = {integrity['cores_cross_partitions']}",
            f"- cluster crossings = {integrity['cluster_crossings']}",
            f"- REF clusters in split = {integrity['ref_clusters_in_split']}",
            f"- EVAL clusters in split = {integrity['eval_clusters_in_split']}",
            f"- REF identities in split = {integrity['ref_identities_in_split']}",
            f"- EVAL identities in split = {integrity['eval_identities_in_split']}",
            f"- E5 = {integrity['E5']}",
            f"- non-protein = {integrity['non_protein']}",
            f"- top-level partition altered = {integrity['top_level_partition_altered']}",
            "- ft.csv mutated = no",
            "- REF mutated = no",
            "- EVAL mutated = no",
            "- authoritative FT train/validation files written = no",
            "- model fine-tuning started = no",
            "",
            "STOP. Human review is required before any authoritative FT train/validation freeze.",
            "",
        ]
    )
    report = "\n".join(lines)
    assert_no_sequence_leak(report, label="s7c_ft_split_preview_report.md")
    return report


def jsonable_s7c(value: Any) -> Any:
    if isinstance(value, QuotaPair):
        return {
            "n_TRAIN": value.n_TRAIN,
            "n_VALIDATION": value.n_VALIDATION,
            "sse": str(value.sse),
        }
    if isinstance(value, RefEvalFreezeSnapshot):
        return {
            "ref_sha256": value.ref_sha256,
            "eval_sha256": value.eval_sha256,
            "ref_identity_set_hash": value.ref_identity_set_hash,
            "ref_cluster_set_hash": value.ref_cluster_set_hash,
            "eval_identity_set_hash": value.eval_identity_set_hash,
            "eval_cluster_set_hash": value.eval_cluster_set_hash,
            "n_ref_clusters": value.n_ref_clusters,
            "n_eval_clusters": value.n_eval_clusters,
            "cluster_overlap": value.cluster_overlap,
        }
    return jsonable(value)


def enforce_s7c_preview_config(config: Mapping[str, Any]) -> None:
    mode = str(config.get("mode") or "").strip()
    if mode != PREVIEW_MODE:
        raise S7CSplitError(f"S7C mode must be preview, got {mode!r}")
    if config.get("write_authoritative_train_validation") is True:
        raise S7CSplitError("S7C preview must not write authoritative train/validation files")
    if config.get("freeze_ft_train") is True or config.get("freeze_ft_validation") is True:
        raise S7CSplitError("S7C preview must not freeze FT train/validation")
    if config.get("alter_top_level_partition") is True:
        raise S7CSplitError("S7C must not alter the top-level partition field")
    does_not = {str(item) for item in config.get("does_not", [])}
    required = {
        "write_ft_train_csv",
        "write_ft_validation_csv",
        "write_corpus_final",
        "alter_ft_csv",
        "alter_ref_csv",
        "alter_eval_csv",
        "alter_top_level_partition",
        "start_fine_tuning",
        "use_validation_for_model_decision",
        "promote_e5",
        "promote_non_protein",
    }
    missing = sorted(required - does_not)
    if missing:
        raise S7CSplitError(f"S7C config.does_not missing required exclusions: {missing}")


def enforce_s7c_application_config(config: Mapping[str, Any]) -> None:
    mode = str(config.get("mode") or "").strip()
    if mode != APPLY_MODE:
        raise S7CSplitError(f"S7C application mode must be apply, got {mode!r}")
    if config.get("write_authoritative_train_validation") is not True:
        raise S7CSplitError("S7C application must write authoritative train/validation files")
    if config.get("freeze_ft_train") is not True or config.get("freeze_ft_validation") is not True:
        raise S7CSplitError("S7C application must freeze FT train and validation")
    if config.get("alter_top_level_partition") is True:
        raise S7CSplitError("S7C must not alter the top-level partition field")
    if config.get("write_corpus_final") is True:
        raise S7CSplitError("S7C application must not write corpus_final")
    does_not = {str(item) for item in config.get("does_not", [])}
    required = {
        "write_corpus_final",
        "alter_ft_csv",
        "alter_ref_csv",
        "alter_eval_csv",
        "alter_top_level_partition",
        "start_fine_tuning",
        "start_s7d",
        "use_validation_for_model_decision",
        "promote_e5",
        "promote_non_protein",
    }
    missing = sorted(required - does_not)
    if missing:
        raise S7CSplitError(
            f"S7C application config.does_not missing required exclusions: {missing}"
        )


def _normalised_repo_relative(path: Any, repo_root: Any | None = None) -> str:
    raw = str(path).replace("\\", "/")
    if repo_root is not None:
        try:
            raw = str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
        except (ValueError, AttributeError):
            pass
    return raw.rstrip("/")


def assert_application_dir_not_preview(path: Any, repo_root: Any | None = None) -> None:
    relative = _normalised_repo_relative(path, repo_root)
    raw = str(path).replace("\\", "/")
    for protected in ALL_PREVIEW_DIRS:
        if (
            relative == protected
            or raw.rstrip("/") == protected
            or raw.endswith("/" + protected)
        ):
            raise S7CSplitError(
                f"S7C application must not write to a preserved preview directory {protected}"
            )


def ft_split_output_fieldnames(fieldnames: Sequence[str]) -> list[str]:
    fields = list(fieldnames)
    if "ft_split" in fields:
        return fields
    if "partition" in fields:
        fields.insert(fields.index("partition") + 1, "ft_split")
    else:
        fields.append("ft_split")
    return fields


def populate_ft_split_on_ft_rows(
    ft_rows: Sequence[Mapping[str, str]],
    assignment: Mapping[str, str],
    fieldnames: Sequence[str],
) -> tuple[list[dict[str, str]], list[str]]:
    """Copy frozen FT rows in source order, adding ``ft_split`` only."""
    output_fields = ft_split_output_fieldnames(fieldnames)
    if "partition" not in output_fields:
        raise S7CSplitError("FT input is missing the partition column")
    populated: list[dict[str, str]] = []
    for row in ft_rows:
        cluster_id = _blank(row.get("cluster_id"))
        if cluster_id not in assignment:
            raise S7CSplitError(f"cluster {cluster_id} is unassigned")
        new_row: dict[str, str] = {}
        for column in output_fields:
            if column == "ft_split":
                new_row[column] = assignment[cluster_id]
            else:
                new_row[column] = row.get(column, "")
        populated.append(new_row)
    return populated, output_fields


def ft_split_subset_rows(
    rows: Sequence[Mapping[str, str]],
    label: str,
) -> list[dict[str, str]]:
    if label not in S7C_REPORT_LABELS:
        raise S7CSplitError(f"invalid FT split label {label!r}")
    return [dict(row) for row in rows if _blank(row.get("ft_split")) == label]


def cluster_ft_split_assignment_rows(
    features: Mapping[str, ClusterFeature],
    assignment: Mapping[str, str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for cluster_id in sorted(assignment):
        row = features[cluster_id].assignment_row(assignment[cluster_id])
        row["ft_split"] = row.pop("partition")
        rows.append(row)
    return rows


def build_s7c_application_tables(
    *,
    features: Mapping[str, ClusterFeature],
    space: FeatureSpace,
    assignment: Mapping[str, str],
    score: ObjectiveScore,
    family_js: Mapping[str, float],
) -> dict[str, list[dict[str, str]]]:
    tables = build_s7c_preview_tables(
        features=features,
        space=space,
        assignment=assignment,
        score=score,
        family_js=family_js,
    )
    tables.pop("cluster_ft_split_preview.csv", None)
    tables["ft_split_assignment.csv"] = cluster_ft_split_assignment_rows(
        features, assignment
    )
    return tables


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


def s7c_preview_application_parity_mismatches(
    *,
    preview_assignment: Mapping[str, str],
    application_assignment: Mapping[str, str],
    preview_quotas: Mapping[str, int],
    application_quotas: QuotaPair,
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
    for label in S7C_REPORT_LABELS:
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
        mismatches.append(
            _mismatch(f"{label}_cluster_set", sorted(preview_ids), sorted(apply_ids))
        )
    mismatches.append(
        _mismatch("n_TRAIN", int(preview_quotas.get("n_TRAIN", -1)), application_quotas.n_TRAIN)
    )
    mismatches.append(
        _mismatch(
            "n_VALIDATION",
            int(preview_quotas.get("n_VALIDATION", -1)),
            application_quotas.n_VALIDATION,
        )
    )

    aggregate_mismatches = 0
    for name in PARITY_TABLE_NAMES:
        preview_rows = [dict(row) for row in preview_tables.get(name, [])]
        apply_rows = [dict(row) for row in application_tables.get(name, [])]
        if preview_rows != apply_rows:
            aggregate_mismatches += 1
            mismatches.append(_mismatch(name, preview_rows, apply_rows))

    objective_mismatches = 0
    apply_objective = application_score.as_dict()
    for key in (
        "R1",
        "R3",
        "M_target",
        "M_evidence",
        "M_length",
        "M_source",
        "A_target",
        "A_evidence",
        "A_length",
        "A_source",
        "lexicographic_descending_M_vector",
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
            "singleton_target_identities",
            "singleton_target_clusters",
            "targets_only_train",
            "targets_only_validation",
            "targets_shared",
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


def s7c_approval_parity_mismatches(
    *,
    assignment: Mapping[str, str],
    features: Mapping[str, ClusterFeature],
    quotas: QuotaPair,
    score: ObjectiveScore,
    target_diag: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> list[str]:
    mismatches: list[str] = []
    v2 = approval.get("v2") or {}
    approved_quotas = v2.get("approved_cluster_quotas") or approval.get("approved_cluster_quotas") or {}
    mismatches.append(
        _mismatch("approved_n_TRAIN", int(approved_quotas.get("TRAIN", -1)), quotas.n_TRAIN)
    )
    mismatches.append(
        _mismatch(
            "approved_n_VALIDATION",
            int(approved_quotas.get("VALIDATION", -1)),
            quotas.n_VALIDATION,
        )
    )
    counts = Counter(assignment.values())
    identity_n = {label: 0 for label in S7C_REPORT_LABELS}
    core_n = {label: 0 for label in S7C_REPORT_LABELS}
    for cluster_id, label in assignment.items():
        identity_n[label] += features[cluster_id].n_identities
        core_n[label] += features[cluster_id].n_cores
    approved_identities = v2.get("approved_identities") or approval.get("approved_identities") or {}
    approved_cores = v2.get("approved_cores") or approval.get("approved_cores") or {}
    for label in S7C_REPORT_LABELS:
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
    approved_objective = v2.get("approved_objective") or approval.get("approved_objective") or {}
    for key, observed in (
        ("R1", score.r1),
        ("R3", score.r3),
        ("M_target", score.m_target),
        ("M_evidence", score.m_evidence),
        ("M_length", score.m_length),
        ("M_source", score.m_source),
        ("D_target", score.d_target),
        ("D_evidence", score.d_evidence),
        ("D_length", score.d_length),
        ("D_source", score.d_source),
    ):
        mismatches.append(_float_mismatch(f"approved_{key}", approved_objective.get(key), observed))
    reviewed = v2.get("reviewed_preview") or approval.get("reviewed_preview") or {}
    represented = reviewed.get("targets_represented") or {}
    mismatches.append(
        _mismatch(
            "approved_TRAIN_targets",
            int(represented.get("TRAIN", -1)),
            int((target_diag.get("targets_represented") or {}).get(TRAIN_LABEL, -1)),
        )
    )
    mismatches.append(
        _mismatch(
            "approved_VALIDATION_targets",
            int(represented.get("VALIDATION", -1)),
            int((target_diag.get("targets_represented") or {}).get(VALIDATION_LABEL, -1)),
        )
    )
    return [item for item in mismatches if item]


def assignment_from_ft_split_rows(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    assignment: dict[str, str] = {}
    for row in rows:
        cluster_id = _blank(row.get("cluster_id"))
        label = _blank(row.get("ft_split"))
        previous = assignment.get(cluster_id)
        if previous is None:
            assignment[cluster_id] = label
        elif previous != label:
            raise S7CSplitError("cluster_id spans FT train/validation in written rows")
    return assignment


def independent_s7c_invariants(
    *,
    input_rows: Sequence[Mapping[str, str]],
    annotated_rows: Sequence[Mapping[str, str]],
    train_rows: Sequence[Mapping[str, str]],
    validation_rows: Sequence[Mapping[str, str]],
    assignment_rows: Sequence[Mapping[str, str]],
    fieldnames: Sequence[str],
    ref_rows: Sequence[Mapping[str, str]],
    eval_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    output_fields = ft_split_output_fieldnames(fieldnames)
    if list(annotated_rows[0].keys() if annotated_rows else output_fields) != output_fields:
        written_fields = list(annotated_rows[0].keys()) if annotated_rows else []
        if written_fields != output_fields:
            raise S7CSplitError("authoritative FT split column order drifted")
    if len(annotated_rows) != len(input_rows):
        raise S7CSplitError("annotated FT identity count drifted from frozen FT")
    identity_seen: dict[str, str] = {}
    cluster_seen: dict[str, str] = {}
    core_seen: dict[str, str] = {}
    invalid_labels = 0
    blank_split = 0
    field_changes = 0
    non_ft_partition = 0
    for original, written in zip(input_rows, annotated_rows):
        if list(written.keys()) != output_fields:
            raise S7CSplitError("authoritative FT split rows do not preserve column order")
        label = _blank(written.get("ft_split"))
        if not label:
            blank_split += 1
        elif label not in S7C_REPORT_LABELS:
            invalid_labels += 1
        if _blank(written.get("partition")) != "FT":
            non_ft_partition += 1
        for column in fieldnames:
            if written.get(column, "") != original.get(column, ""):
                field_changes += 1
        identity = _blank(written.get("scientific_identity_id"))
        cluster_id = _blank(written.get("cluster_id"))
        core = _blank(written.get("sequence_core"))
        if identity in identity_seen:
            raise S7CSplitError("scientific_identity_id appears more than once")
        identity_seen[identity] = label
        previous_cluster = cluster_seen.get(cluster_id)
        if previous_cluster is None:
            cluster_seen[cluster_id] = label
        elif previous_cluster != label:
            raise S7CSplitError("cluster_id spans train/validation")
        previous_core = core_seen.get(core)
        if previous_core is None:
            core_seen[core] = label
        elif previous_core != label:
            raise S7CSplitError("sequence_core spans train/validation")

    subsets = {TRAIN_LABEL: train_rows, VALIDATION_LABEL: validation_rows}
    subset_identities: dict[str, set[str]] = {}
    subset_clusters: dict[str, set[str]] = {}
    subset_cores: dict[str, set[str]] = {}
    for label, rows in subsets.items():
        subset_identities[label] = {_blank(row.get("scientific_identity_id")) for row in rows}
        subset_clusters[label] = {_blank(row.get("cluster_id")) for row in rows}
        subset_cores[label] = {_blank(row.get("sequence_core")) for row in rows}
        expected = [
            dict(row) for row in annotated_rows if _blank(row.get("ft_split")) == label
        ]
        if [dict(row) for row in rows] != expected:
            raise S7CSplitError(f"{label.lower()} file is not an exact row subset")
        if any(_blank(row.get("partition")) != "FT" for row in rows):
            raise S7CSplitError(f"{label.lower()} file altered top-level partition")
        if any(_blank(row.get("ft_split")) != label for row in rows):
            raise S7CSplitError(f"{label.lower()} file contains a foreign ft_split label")

    union_ids = subset_identities[TRAIN_LABEL] | subset_identities[VALIDATION_LABEL]
    if union_ids != set(identity_seen):
        raise S7CSplitError("TRAIN/VALIDATION identity union does not match frozen FT")
    identity_overlap = subset_identities[TRAIN_LABEL] & subset_identities[VALIDATION_LABEL]
    cluster_overlap = subset_clusters[TRAIN_LABEL] & subset_clusters[VALIDATION_LABEL]
    core_overlap = subset_cores[TRAIN_LABEL] & subset_cores[VALIDATION_LABEL]
    if identity_overlap:
        raise S7CSplitError("an identity appears in both TRAIN and VALIDATION")
    if cluster_overlap:
        raise S7CSplitError("a cluster appears in both TRAIN and VALIDATION")
    if core_overlap:
        raise S7CSplitError("a sequence_core appears in both TRAIN and VALIDATION")

    original_identities = {_blank(row.get("scientific_identity_id")) for row in input_rows}
    original_clusters = {_blank(row.get("cluster_id")) for row in input_rows}
    original_cores = {_blank(row.get("sequence_core")) for row in input_rows}
    if union_ids != original_identities:
        raise S7CSplitError("every original FT identity must appear exactly once")
    if (subset_clusters[TRAIN_LABEL] | subset_clusters[VALIDATION_LABEL]) != original_clusters:
        raise S7CSplitError("every original FT cluster must appear exactly once")
    if (subset_cores[TRAIN_LABEL] | subset_cores[VALIDATION_LABEL]) != original_cores:
        raise S7CSplitError("every original FT sequence_core must appear exactly once")

    assignment_map = {
        _blank(row.get("cluster_id")): _blank(row.get("ft_split")) for row in assignment_rows
    }
    if assignment_map != cluster_seen:
        raise S7CSplitError("ft_split_assignment.csv disagrees with train/validation files")

    ref_clusters = {_blank(row.get("cluster_id")) for row in ref_rows}
    eval_clusters = {_blank(row.get("cluster_id")) for row in eval_rows}
    ref_ids = {_blank(row.get("scientific_identity_id")) for row in ref_rows}
    eval_ids = {_blank(row.get("scientific_identity_id")) for row in eval_rows}
    train_val_clusters = subset_clusters[TRAIN_LABEL] | subset_clusters[VALIDATION_LABEL]
    train_val_ids = subset_identities[TRAIN_LABEL] | subset_identities[VALIDATION_LABEL]
    train_ref_clusters = len(subset_clusters[TRAIN_LABEL] & ref_clusters)
    train_eval_clusters = len(subset_clusters[TRAIN_LABEL] & eval_clusters)
    val_ref_clusters = len(subset_clusters[VALIDATION_LABEL] & ref_clusters)
    val_eval_clusters = len(subset_clusters[VALIDATION_LABEL] & eval_clusters)
    train_val_ref_ids = len(train_val_ids & ref_ids)
    train_val_eval_ids = len(train_val_ids & eval_ids)
    if train_ref_clusters or train_eval_clusters or val_ref_clusters or val_eval_clusters:
        raise S7CSplitError("TRAIN/VALIDATION clusters overlap REF or EVAL")
    if train_val_ref_ids or train_val_eval_ids:
        raise S7CSplitError("TRAIN/VALIDATION identities overlap REF or EVAL")

    evidence = Counter(_blank(row.get("evidence_level")) for row in annotated_rows)
    types = {_blank(row.get("target_type")) for row in annotated_rows}
    return {
        "n_identities": len(identity_seen),
        "n_cores": len(core_seen),
        "n_clusters": len(cluster_seen),
        "identity_sum": len(train_rows) + len(validation_rows),
        "cluster_sum": len(subset_clusters[TRAIN_LABEL]) + len(subset_clusters[VALIDATION_LABEL]),
        "core_sum": len(subset_cores[TRAIN_LABEL]) + len(subset_cores[VALIDATION_LABEL]),
        "identities_assigned_exactly_once": True,
        "clusters_assigned_exactly_once": True,
        "cores_cross_splits": 0,
        "cluster_crossings": 0,
        "identity_overlap": 0,
        "cluster_overlap": 0,
        "core_overlap": 0,
        "ft_split_blank": blank_split,
        "invalid_ft_split_labels": invalid_labels,
        "field_changes_excluding_ft_split": field_changes,
        "non_ft_partition": non_ft_partition,
        "E5": int(evidence.get("E5", 0)),
        "non_protein": 0 if types == {"protein"} else 1,
        "n_TRAIN": len(train_rows),
        "n_VALIDATION": len(validation_rows),
        "n_TRAIN_clusters": len(subset_clusters[TRAIN_LABEL]),
        "n_VALIDATION_clusters": len(subset_clusters[VALIDATION_LABEL]),
        "n_TRAIN_cores": len(subset_cores[TRAIN_LABEL]),
        "n_VALIDATION_cores": len(subset_cores[VALIDATION_LABEL]),
        "n_TRAIN_targets": len({row["canonical_target_name"] for row in train_rows}),
        "n_VALIDATION_targets": len({row["canonical_target_name"] for row in validation_rows}),
        "train_ref_clusters": train_ref_clusters,
        "train_eval_clusters": train_eval_clusters,
        "validation_ref_clusters": val_ref_clusters,
        "validation_eval_clusters": val_eval_clusters,
        "train_validation_ref_identities": train_val_ref_ids,
        "train_validation_eval_identities": train_val_eval_ids,
        "train_val_ref_eval_cluster_overlap": len(train_val_clusters & (ref_clusters | eval_clusters)),
    }


def independent_s7c_distribution_counts(
    annotated_rows: Sequence[Mapping[str, str]],
    core_regimes: Mapping[str, str],
) -> dict[str, Any]:
    evidence = {label: Counter() for label in S7C_REPORT_LABELS}
    source = {label: Counter() for label in S7C_REPORT_LABELS}
    length = {label: Counter() for label in S7C_REPORT_LABELS}
    cores_seen = {label: set() for label in S7C_REPORT_LABELS}
    for row in annotated_rows:
        label = _blank(row.get("ft_split"))
        if label not in S7C_REPORT_LABELS:
            raise S7CSplitError(f"invalid ft_split label {label!r}")
        evidence[label][_blank(row.get("evidence_level"))] += 1
        source[label][_blank(row.get("source_db")) or "(blank)"] += 1
        core = _blank(row.get("sequence_core"))
        if core not in cores_seen[label]:
            cores_seen[label].add(core)
            regime = core_regimes.get(core)
            if regime not in {"short", "long"}:
                raise S7CSplitError("length regime missing during independent recount")
            length[label][regime] += 1
    return {
        "evidence": {label: dict(evidence[label]) for label in S7C_REPORT_LABELS},
        "source": {label: dict(source[label]) for label in S7C_REPORT_LABELS},
        "length": {label: dict(length[label]) for label in S7C_REPORT_LABELS},
        "n_identities": len(annotated_rows),
    }


def build_s7c_freeze_record(
    *,
    input_sha256: str,
    preview_assignment_sha256: str,
    preview_manifest_sha256: str,
    authoritative_assignment_sha256: str,
    quotas: QuotaPair,
    independent: Mapping[str, Any],
    output_hashes: Mapping[str, str],
    train_identity_set_hash: str,
    train_cluster_set_hash: str,
    validation_identity_set_hash: str,
    validation_cluster_set_hash: str,
    ref_snapshot: Mapping[str, Any],
    eval_snapshot: Mapping[str, Any],
    score: ObjectiveScore,
    semantic_mismatches_total: int,
    freeze_date: str = FREEZE_DATE,
    freeze_reason: str = FREEZE_REASON,
) -> dict[str, Any]:
    payload = {
        "contract_id": "s7c_ft_split_freeze",
        "checkpoint": "CHECKPOINT-3",
        "milestone": "S7C_ft_train_validation_application_and_freeze",
        "decision_date": freeze_date,
        "freeze_date": freeze_date,
        "freeze_reason": freeze_reason,
        "frozen_ft_input_sha256": input_sha256,
        "approved_v2_preview_hash": preview_assignment_sha256,
        "approved_v2_preview_manifest_hash": preview_manifest_sha256,
        "authoritative_assignment_hash": authoritative_assignment_sha256,
        "preview_application_mismatch_count": semantic_mismatches_total,
        "split_quotas": {
            "TRAIN": quotas.n_TRAIN,
            "VALIDATION": quotas.n_VALIDATION,
        },
        "TRAIN": {
            "clusters": independent["n_TRAIN_clusters"],
            "identities": independent["n_TRAIN"],
            "cores": independent["n_TRAIN_cores"],
            "targets_represented": independent["n_TRAIN_targets"],
            "file_sha256": output_hashes.get("ft_train.csv", ""),
            "identity_set_hash": train_identity_set_hash,
            "cluster_set_hash": train_cluster_set_hash,
            "frozen": True,
        },
        "VALIDATION": {
            "clusters": independent["n_VALIDATION_clusters"],
            "identities": independent["n_VALIDATION"],
            "cores": independent["n_VALIDATION_cores"],
            "targets_represented": independent["n_VALIDATION_targets"],
            "file_sha256": output_hashes.get("ft_validation.csv", ""),
            "identity_set_hash": validation_identity_set_hash,
            "cluster_set_hash": validation_cluster_set_hash,
            "frozen": True,
        },
        "REF": {
            "file_sha256": ref_snapshot.get("ref_sha256") or ref_snapshot.get("file_sha256"),
            "identity_set_hash": ref_snapshot.get("ref_identity_set_hash")
            or ref_snapshot.get("identity_set_hash"),
            "cluster_set_hash": ref_snapshot.get("ref_cluster_set_hash")
            or ref_snapshot.get("cluster_set_hash"),
            "frozen": True,
        },
        "EVAL": {
            "file_sha256": eval_snapshot.get("eval_sha256") or eval_snapshot.get("file_sha256"),
            "identity_set_hash": eval_snapshot.get("eval_identity_set_hash")
            or eval_snapshot.get("identity_set_hash"),
            "cluster_set_hash": eval_snapshot.get("eval_cluster_set_hash")
            or eval_snapshot.get("cluster_set_hash"),
            "frozen": True,
        },
        "objective": score.as_dict(),
        "independence_rule": {
            "model_training_uses_ft_train_only": True,
            "checkpoint_selection_early_stopping_hyperparameter_comparison_uses_ft_validation_only": True,
            "ref_reserved_for_aptarank_and_reference_distribution_calibration": True,
            "eval_reserved_for_final_held_out_evaluation": True,
            "eval_may_later_evaluate_fine_tuned_rnagenesis_but_must_not_influence_training_checkpoint_or_hyperparameters": True,
            "no_cluster_may_move_among_train_validation_ref_eval_based_on_modelling_results": True,
            "later_scientific_correction_requires_documented_split_revision_new_hashes_and_human_approval": True,
        },
        "s7d_started": False,
        "model_fine_tuning_started": False,
        "ref_calibration_started": False,
        "eval_model_evaluation_started": False,
        "sequences_included": False,
    }
    assert_no_sequence_leak(jsonable_dumps(payload), label="s7c_ft_split_freeze.json")
    return payload


def build_s7c_application_report(
    *,
    input_sha256: str,
    observed: Mapping[str, int],
    gmm: Mapping[str, Any],
    n_short: int,
    n_long: int,
    selected_quotas: QuotaPair,
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
    greedy_r1: float,
    freeze_date: str,
    train_identity_set_hash: str,
    validation_identity_set_hash: str,
    ref_eval_before: Mapping[str, Any],
    ref_eval_after: Mapping[str, Any],
    determinism_ok: bool,
) -> str:
    train_ident = list(tables["train_identity_summary.csv"])[0]
    val_ident = list(tables["validation_identity_summary.csv"])[0]
    train_core = list(tables["train_core_summary.csv"])[0]
    val_core = list(tables["validation_core_summary.csv"])[0]
    source_rows = list(tables["source_distribution.csv"])
    evidence_rows = list(tables["evidence_distribution.csv"])
    length_rows = list(tables["length_regime_distribution.csv"])
    lines = [
        "# S7C FT train/validation application and freeze — v2",
        "",
        "This report records the **authoritative S7C whole-cluster FT",
        "TRAIN/VALIDATION assignment** rederived from frozen `ft.csv` with the",
        "same tested v2 maximum-absolute-proportion-deviation optimiser used",
        "for the approved preview. TRAIN and VALIDATION are frozen. REF and",
        "EVAL remain frozen and byte-identical to the S7B freeze. The v1",
        "raw-JSD preview is preserved and was not approved. No `corpus_final`",
        "was written. Model fine-tuning has not started.",
        "",
        "The human approval record is audit-only. Cluster assignment was not",
        "copied from approval metadata or from the preview CSV; it was",
        "rederived and then compared.",
        "",
        "## Frozen FT input",
        "",
        f"- ft.csv SHA-256 = `{input_sha256}`",
        f"- identities = {observed['n_scientific_identities']}",
        f"- distinct sequence_core = {observed['n_distinct_sequence_core']}",
        f"- clusters = {observed['n_final_clusters']}",
        f"- canonical targets = {observed['n_canonical_targets']}",
        "",
        "## Frozen S6 length-regime provenance",
        "",
        "- assignment_method = `gmm_k2_maximum_posterior`",
        "- GMM source = frozen S6 `bimodality.json` `gmm_2` (not refit)",
        f"- component means = {list(gmm['means'])}",
        f"- component weights = {list(gmm['weights'])}",
        f"- FT short cores = {n_short}",
        f"- FT long cores = {n_long}",
        "",
        "## Authoritative quotas (cluster count, not identity count)",
        "",
        (
            f"- selected = ({selected_quotas.n_TRAIN}, {selected_quotas.n_VALIDATION})"
        ),
        "- VALIDATION therefore contains a larger identity/core fraction than",
        "  its 10.08% cluster quota. That is an accepted consequence of",
        "  whole-cluster quota splitting and four-way distribution",
        "  comparability, not leakage.",
        "- validation-only targets are permitted. No target-coverage hard",
        "  constraint was added.",
        "",
        "| subset | clusters | identities | cores | targets represented |",
        "| --- | --- | --- | --- | --- |",
        (
            f"| TRAIN | {train_ident['n_clusters']} | {train_ident['n_identities']} | "
            f"{train_core['n_distinct_cores']} | {train_ident['n_canonical_targets_represented']} |"
        ),
        (
            f"| VALIDATION | {val_ident['n_clusters']} | {val_ident['n_identities']} | "
            f"{val_core['n_distinct_cores']} | {val_ident['n_canonical_targets_represented']} |"
        ),
        "",
        "## Objective (approved v2 deterministic operationalisation)",
        "",
        "- primary metric = maximum absolute category-proportion deviation",
        "- JSD is diagnostic / tie-break only",
        "- target_family secondary diagnostic only",
        "- arbitrary manually chosen criterion weights = none",
        "- new hard source coverage constraint = no",
        f"- greedy R1 before local search = {format_float(greedy_r1)}",
        f"- accepted pairwise swaps = {n_accepted_swaps}",
        f"- local-search passes = {n_local_search_passes}",
        f"- local-search converged = {local_search_converged}",
        f"- M_target = {format_float(score.m_target)}",
        f"- M_evidence = {format_float(score.m_evidence)}",
        f"- M_length = {format_float(score.m_length)}",
        f"- M_source = {format_float(score.m_source)}",
        f"- R1 = {format_float(score.r1)}",
        f"- descending M vector = {list(score.m_lex_vector)}",
        f"- R3 = {format_float(score.r3)}",
        f"- D_target = {format_float(score.d_target)}",
        f"- D_evidence = {format_float(score.d_evidence)}",
        f"- D_length = {format_float(score.d_length)}",
        f"- D_source = {format_float(score.d_source)}",
        "",
        "## Preview / application parity",
        "",
        f"- cluster assignments compared = {parity['cluster_assignments_compared']}",
        f"- cluster assignment mismatches = {parity['cluster_assignment_mismatches']}",
        f"- aggregate/statistical mismatches = {parity['aggregate_statistical_mismatches']}",
        f"- objective mismatches = {parity['objective_mismatches']}",
        f"- semantic mismatches total = {parity['semantic_mismatches_total']}",
        f"- v2 preview assignment SHA-256 = `{preview_hashes.get('cluster_ft_split_preview.csv', '')}`",
        f"- authoritative assignment SHA-256 = `{output_hashes.get('ft_split_assignment.csv', '')}`",
        "",
        "## Target representation",
        "",
        f"- targets represented TRAIN/VALIDATION = "
        f"{target_diag['targets_represented'][TRAIN_LABEL]} / "
        f"{target_diag['targets_represented'][VALIDATION_LABEL]}",
        f"- targets shared = {target_diag['targets_shared']}",
        f"- targets train-only = {target_diag['targets_only_train']}",
        f"- targets validation-only = {target_diag['targets_only_validation']}",
        f"- singleton-target identities TRAIN/VALIDATION = "
        f"{target_diag['singleton_target_identities'][TRAIN_LABEL]} / "
        f"{target_diag['singleton_target_identities'][VALIDATION_LABEL]}",
        "",
        "## Evidence / length / source (authoritative)",
        "",
    ]
    for row in evidence_rows:
        lines.append(
            f"- {row['evidence_level']}: FT {row['n_global']}; "
            f"TRAIN {row['n_TRAIN']}; VALIDATION {row['n_VALIDATION']}"
        )
    lines.append("")
    for row in length_rows:
        lines.append(
            f"- {row['length_regime']}: FT {row['n_global_cores']}; "
            f"TRAIN {row['n_TRAIN_cores']}; VALIDATION {row['n_VALIDATION_cores']}"
        )
    lines.append("")
    for row in source_rows:
        lines.append(
            f"- {row['source_db']}: FT {row['n_global']}; "
            f"TRAIN {row['n_TRAIN']}; VALIDATION {row['n_VALIDATION']}"
        )
    lines.extend(
        [
            "",
            "## TRAIN / VALIDATION freeze",
            "",
            f"- freeze date = {freeze_date}",
            f"- TRAIN file SHA-256 = `{output_hashes.get('ft_train.csv', '')}`",
            f"- TRAIN identity-set hash = `{train_identity_set_hash}`",
            f"- VALIDATION file SHA-256 = `{output_hashes.get('ft_validation.csv', '')}`",
            f"- VALIDATION identity-set hash = `{validation_identity_set_hash}`",
            "- TRAIN frozen = yes",
            "- VALIDATION frozen = yes",
            "",
            "After this freeze:",
            "",
            "- model training uses **FT TRAIN only**",
            "- checkpoint selection / early stopping / hyperparameter comparison",
            "  may use **FT VALIDATION only**",
            "- REF remains reserved for AptaRank / reference-distribution calibration",
            "- EVAL remains reserved for final held-out evaluation",
            "- EVAL may later evaluate fine-tuned RNAGenesis, but must not",
            "  influence training, checkpoint, or hyperparameter choices",
            "- no cluster may move among TRAIN/VALIDATION/REF/EVAL based on",
            "  modelling results",
            "",
            "Any later legitimate correction requires a documented split",
            "revision, new hashes, and explicit human approval.",
            "",
            "## REF / EVAL immutability",
            "",
            f"- REF SHA before = `{ref_eval_before['ref_sha256']}`",
            f"- REF SHA after = `{ref_eval_after['ref_sha256']}`",
            f"- EVAL SHA before = `{ref_eval_before['eval_sha256']}`",
            f"- EVAL SHA after = `{ref_eval_after['eval_sha256']}`",
            "- REF changed = no",
            "- EVAL changed = no",
            "",
            "## Integrity",
            "",
            f"- FT clusters assigned exactly once = {integrity['clusters_assigned_exactly_once']}",
            f"- FT identities assigned exactly once = {integrity['identities_assigned_exactly_once']}",
            f"- TRAIN/VALIDATION identity overlap = {independent['identity_overlap']}",
            f"- TRAIN/VALIDATION cluster overlap = {independent['cluster_overlap']}",
            f"- TRAIN/VALIDATION core overlap = {independent['core_overlap']}",
            f"- REF clusters in TRAIN/VALIDATION = {independent['train_val_ref_eval_cluster_overlap']}",
            f"- E5 = {independent['E5']}",
            f"- non-protein = {independent['non_protein']}",
            f"- top-level partition altered = {independent['non_ft_partition']}",
            f"- scientific fields changed excluding ft_split = {independent['field_changes_excluding_ft_split']}",
            f"- determinism_ok = {determinism_ok}",
            "- ft.csv mutated = no",
            "- REF mutated = no",
            "- EVAL mutated = no",
            "- model fine-tuning started = no",
            "- S7D started = no",
            "",
            f"- D_family diagnostic = {format_float(max(family_js.values()) if family_js else 0.0)}",
            "",
            "STOP. Do not begin S7D. Do not start model fine-tuning.",
            "",
        ]
    )
    report = "\n".join(lines)
    assert_no_sequence_leak(report, label="s7c_ft_split_report.md")
    return report


__all__ = [
    "ALL_PREVIEW_DIRS",
    "APPLICATION_TABLE_NAMES",
    "APPLY_MODE",
    "CLUSTER_FT_SPLIT_ASSIGNMENT_COLUMNS",
    "COMPARISON_TUPLE_FIELDS",
    "FREEZE_DATE",
    "FREEZE_REASON",
    "PARITY_TABLE_NAMES",
    "S7C_COMPARISON_TUPLE_FIELDS",
    "S7C_OBJECTIVE_PROFILE",
    "PROTECTED_PREVIEW_DIRS",
    "QuotaPair",
    "RefEvalFreezeSnapshot",
    "S7CSplitError",
    "S7C_PLACEMENT_LABELS",
    "S7C_REPORT_LABELS",
    "TABLE_COLUMNS",
    "TRAIN_LABEL",
    "VALIDATION_LABEL",
    "assignment_from_ft_split_rows",
    "assert_application_dir_not_preview",
    "assert_not_forbidden_s7c_apply_output_path",
    "assert_not_forbidden_s7c_output_path",
    "assert_preview_dir_not_protected",
    "assert_ref_eval_matches_expected",
    "assert_ref_eval_unchanged",
    "assignment_signature",
    "blank_partition_copy",
    "build_cluster_features",
    "build_s7c_application_report",
    "build_s7c_application_tables",
    "build_s7c_freeze_record",
    "build_s7c_preview_report",
    "build_s7c_preview_tables",
    "cluster_ft_split_assignment_rows",
    "derive_integer_quota_pairs",
    "enforce_s7c_application_config",
    "enforce_s7c_preview_config",
    "evaluate_random_baselines",
    "family_jsd_by_partition",
    "file_sha256",
    "frozen_ref_eval_expected",
    "ft_split_output_fieldnames",
    "ft_split_subset_rows",
    "independent_s7c_distribution_counts",
    "independent_s7c_invariants",
    "input_unmutated",
    "jsonable_s7c",
    "max_abs_proportion_deviation",
    "annotate_abs_share_deviations",
    "populate_ft_split_on_ft_rows",
    "s7c_approval_parity_mismatches",
    "s7c_integrity_gates",
    "s7c_preview_application_parity_mismatches",
    "s7c_target_diagnostics",
    "score_s7c_assignment",
    "select_s7c_assignment",
    "snapshot_ref_eval_freeze",
    "states_from_assignment",
    "verify_ft_split_input",
    "assign_length_regimes",
]

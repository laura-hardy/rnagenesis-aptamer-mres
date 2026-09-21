"""S5C 90% sequence-identity clustering helpers.

Clustering operates on distinct ``sequence_core`` values. Exact scientific
dedup has already occurred. Target labels have zero influence on cluster
composition. This module does not run CD-HIT, balance targets, assign
FT/REF/EVAL, or split train/validation.

Deterministic input sort
------------------------
FASTA and sequence-level tables are ordered by:

1. ``sequence_core_sha256`` ascending (raw SHA-256 hex of ``sequence_core``);
2. ``sequence_id`` ascending as a redundant stable tie-break.

Cluster IDs are derived from sorted member hashes, not MMseqs numeric labels.
"""

from __future__ import annotations

import hashlib
import math
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from adapters.s4_scientific_common import (
    ScientificProposalError,
    bool_token,
    fill_row,
    split_pipe,
)
from adapters.s5_exact_dedup import (
    CORPUS_DEDUP_COLUMNS,
    join_sorted_unique,
    _blank,
)
from adapters.target_extraction_common import SEQ_LEAK_RE
from common.leakage_matching import global_edit_identity
from common.sequence_normalisation import (
    ALPHABET_INVALID,
    ALPHABET_MISSING,
    classify_alphabet,
    load_normalisation_rules,
    validate_core_length,
)

S5SequenceClusteringError = ScientificProposalError

SEQUENCE_ID_PREFIX = "S5SEQ_"
CLUSTER_ID_PREFIX = "S5C_"
CLUSTER_MEMBERSHIP_DELIMITER = "\x1f"
SEQUENCE_FIELD = "sequence_core"
FROZEN_CORPUS_DEDUP_NAME = "corpus_dedup.csv"

AUTHORISED_PARAMETERS: dict[str, Any] = {
    "min_seq_id": 0.90,
    "coverage": 0.80,
    "cov_mode": 1,
    "sensitivity": 7.5,
    "sequence_field": SEQUENCE_FIELD,
}

FORBIDDEN_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "balancing",
        "cd-hit-est",
        "cdhit",
        "cdhit_fallback",
        "ft_ref_eval",
        "ft_ref_eval_assignment",
        "max_target_fraction",
        "partition",
        "target_cap",
        "train_validation_split",
        "train_validation_test_split",
        "u_to_t_derived_corpus",
    }
)

SEQUENCE_INPUT_COLUMNS: tuple[str, ...] = (
    "sequence_id",
    "sequence_core",
    "sequence_core_sha256",
    "sequence_length",
    "n_scientific_identities",
    "scientific_identity_ids",
    "canonical_target_names",
)

SEQUENCE_IDENTITY_MAP_COLUMNS: tuple[str, ...] = (
    "sequence_id",
    "sequence_core_sha256",
    "scientific_identity_id",
    "canonical_target_name",
)

CLUSTER_TSV_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "mmseqs_representative_sequence_id",
    "member_sequence_id",
    "member_sequence_core_sha256",
    "sequence_length",
    "member_is_mmseqs_representative",
)

CLUSTER_SUMMARY_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "n_distinct_sequences",
    "n_scientific_identities",
    "representative_sequence_id",
    "representative_sequence_core_sha256",
    "min_sequence_length",
    "median_sequence_length",
    "max_sequence_length",
    "n_targets",
    "n_sources",
    "contains_multi_target_identical_core",
    "ena_provenance_present",
)

CLUSTER_PROVENANCE_COLUMNS: tuple[str, ...] = (
    "sequence_id",
    "sequence_core_sha256",
    "mmseqs_representative_sequence_id",
    "mmseqs_representative_sequence_core_sha256",
    "is_mmseqs_sequence_representative",
)

CORPUS_CLUSTERED_COLUMNS: tuple[str, ...] = (
    *CORPUS_DEDUP_COLUMNS,
    *CLUSTER_PROVENANCE_COLUMNS,
)

IDENTITY_AUDIT_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "mmseqs_representative_sequence_id",
    "member_sequence_id",
    "representative_length",
    "member_length",
    "length_delta",
    "global_levenshtein_identity_diagnostic",
    "meets_configured_threshold_under_global_levenshtein_diagnostic",
    "mmseqs_identity_available",
    "mmseqs_coverage_available",
)

ENA_FAMILY_DIAGNOSTIC_COLUMNS: tuple[str, ...] = (
    "ena_family_id",
    "declared_multi_member",
    "n_s5_ena_membership_rows",
    "n_s5_ena_sequence_cores",
    "n_s5c_clusters",
    "contained_in_one_cluster",
    "cluster_ids",
)

PREFLIGHT_U_ID = "PRE_U_A"
PREFLIGHT_U_DUP_ID = "PRE_U_B"
PREFLIGHT_U_NEAR_ID = "PRE_U_NEAR"
PREFLIGHT_T_ID = "PRE_T_EQUIV"
PREFLIGHT_MIXED_ID = "PRE_MIXED_TU"
PREFLIGHT_FAR_ID = "PRE_FAR"


@dataclass
class SequenceClusteringResult:
    sequence_rows: list[dict[str, str]]
    identity_map_rows: list[dict[str, str]]
    cluster_rows: list[dict[str, str]]
    clustered_corpus: list[dict[str, str]]
    cluster_summary_rows: list[dict[str, str]]
    identity_audit_rows: list[dict[str, str]]
    ena_family_rows: list[dict[str, str]]
    diagnostics: dict[str, Any] = field(default_factory=dict)


def sequence_core_digest(sequence_core: str) -> str:
    core = _blank(sequence_core)
    if not core:
        raise S5SequenceClusteringError("sequence_core is required for sequence IDs")
    return hashlib.sha256(core.encode("utf-8")).hexdigest()


def make_sequence_id(sequence_core: str) -> str:
    """Order-independent sequence-level ID derived only from the sequence."""
    return SEQUENCE_ID_PREFIX + sequence_core_digest(sequence_core)


def stable_cluster_id(member_digests: Iterable[str]) -> str:
    """Persistent cluster ID from membership, independent of MMseqs labels."""
    payload = CLUSTER_MEMBERSHIP_DELIMITER.join(sorted(_blank(item) for item in member_digests))
    if not payload:
        raise S5SequenceClusteringError("cannot derive cluster_id from empty membership")
    return CLUSTER_ID_PREFIX + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def clustering_sort_key(row: Mapping[str, str]) -> tuple[str, str]:
    return (
        _blank(row.get("sequence_core_sha256")),
        _blank(row.get("sequence_id")),
    )


def enforce_authorised_parameters(config: Mapping[str, Any]) -> None:
    forbidden = sorted(set(config) & FORBIDDEN_CONFIG_KEYS)
    if forbidden:
        raise S5SequenceClusteringError(
            "S5C config contains forbidden S6/S7 or fallback keys: "
            + ", ".join(forbidden)
        )
    for key, expected in AUTHORISED_PARAMETERS.items():
        if key not in config:
            raise S5SequenceClusteringError(f"S5C config missing required parameter {key}")
        observed = config[key]
        if isinstance(expected, float):
            try:
                value = float(observed)
            except (TypeError, ValueError) as exc:
                raise S5SequenceClusteringError(
                    f"S5C parameter {key} must be numeric; got {observed!r}"
                ) from exc
            if not math.isclose(value, expected, rel_tol=0.0, abs_tol=1e-12):
                raise S5SequenceClusteringError(
                    f"S5C parameter {key}={observed!r} is not authorised; "
                    f"required {expected}"
                )
        elif observed != expected:
            raise S5SequenceClusteringError(
                f"S5C parameter {key}={observed!r} is not authorised; "
                f"required {expected!r}"
            )


def assert_not_corpus_dedup_path(path: Path) -> None:
    if path.name == FROZEN_CORPUS_DEDUP_NAME:
        raise S5SequenceClusteringError(
            "refusing to write clustered output onto frozen corpus_dedup.csv"
        )


def project_unique_sequence_cores(
    corpus_rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """One clustering-input row per distinct ``sequence_core``.

    Repeated cores across targets collapse to one sequence row. Target labels
    are recorded only as sidecar provenance and are never written into FASTA.
    """
    grouped: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in corpus_rows:
        core = _blank(row.get(SEQUENCE_FIELD) or row.get("sequence_core"))
        if not core:
            raise S5SequenceClusteringError("clustering projection requires sequence_core")
        grouped[core].append(row)

    sequence_rows: list[dict[str, str]] = []
    identity_map: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for core, rows in grouped.items():
        digest = sequence_core_digest(core)
        seq_id = SEQUENCE_ID_PREFIX + digest
        if seq_id in seen_ids:
            raise S5SequenceClusteringError("sequence_id collision")
        seen_ids.add(seq_id)
        identity_ids = sorted(
            {
                _blank(row.get("scientific_identity_id"))
                for row in rows
                if _blank(row.get("scientific_identity_id"))
            }
        )
        if len(identity_ids) != len(rows):
            raise S5SequenceClusteringError(
                "scientific_identity_id missing while projecting sequence cores"
            )
        targets = join_sorted_unique(row.get("canonical_target_name") for row in rows)
        sequence_rows.append(
            fill_row(
                SEQUENCE_INPUT_COLUMNS,
                {
                    "sequence_id": seq_id,
                    "sequence_core": core,
                    "sequence_core_sha256": digest,
                    "sequence_length": str(len(core)),
                    "n_scientific_identities": str(len(identity_ids)),
                    "scientific_identity_ids": "|".join(identity_ids),
                    "canonical_target_names": targets,
                },
            )
        )
        for row in rows:
            identity_map.append(
                fill_row(
                    SEQUENCE_IDENTITY_MAP_COLUMNS,
                    {
                        "sequence_id": seq_id,
                        "sequence_core_sha256": digest,
                        "scientific_identity_id": _blank(row.get("scientific_identity_id")),
                        "canonical_target_name": _blank(row.get("canonical_target_name")),
                    },
                )
            )
    sequence_rows.sort(key=clustering_sort_key)
    identity_map.sort(
        key=lambda row: (
            row["sequence_core_sha256"],
            row["sequence_id"],
            row["scientific_identity_id"],
        )
    )
    if len(sequence_rows) != len({row["sequence_id"] for row in sequence_rows}):
        raise S5SequenceClusteringError("sequence_id values are not unique")
    if len(sequence_rows) != len({row["sequence_core"] for row in sequence_rows}):
        raise S5SequenceClusteringError("projected sequence_core values are not unique")
    return sequence_rows, identity_map


def render_fasta(sequence_rows: Sequence[Mapping[str, str]]) -> str:
    """Render clustering FASTA. Headers are sequence IDs only; no target labels."""
    ordered = sorted(sequence_rows, key=clustering_sort_key)
    lines: list[str] = []
    for row in ordered:
        seq_id = _blank(row.get("sequence_id"))
        core = _blank(row.get("sequence_core"))
        if not seq_id or not core:
            raise S5SequenceClusteringError("FASTA requires sequence_id and sequence_core")
        if any(ch.isspace() for ch in seq_id):
            raise S5SequenceClusteringError("sequence_id must not contain whitespace")
        lines.append(f">{seq_id}")
        lines.append(core)
    return "\n".join(lines) + "\n"


def parse_mmseqs_cluster_tsv(
    text: str,
    *,
    input_sequence_ids: Sequence[str],
) -> list[tuple[str, str]]:
    """Parse MMseqs ``*_cluster.tsv`` into ``(representative, member)`` pairs."""
    expected = list(input_sequence_ids)
    expected_set = set(expected)
    if len(expected) != len(expected_set):
        raise S5SequenceClusteringError("input sequence IDs are not unique")
    pairs: list[tuple[str, str]] = []
    members_seen: list[str] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            raise S5SequenceClusteringError(
                f"MMseqs cluster TSV line {line_number} does not have two columns"
            )
        representative = parts[0].strip()
        member = parts[1].strip()
        if not representative or not member:
            raise S5SequenceClusteringError(
                f"MMseqs cluster TSV line {line_number} has a blank identifier"
            )
        if member not in expected_set or representative not in expected_set:
            unknown = member if member not in expected_set else representative
            raise S5SequenceClusteringError(
                f"unknown MMseqs sequence ID {unknown!r}"
            )
        pairs.append((representative, member))
        members_seen.append(member)
    member_counts = Counter(members_seen)
    duplicated = sorted(seq_id for seq_id, count in member_counts.items() if count > 1)
    if duplicated:
        raise S5SequenceClusteringError(
            "duplicate MMseqs membership for sequence IDs: " + ", ".join(duplicated)
        )
    missing = [seq_id for seq_id in expected if seq_id not in member_counts]
    if missing:
        raise S5SequenceClusteringError(
            "MMseqs output is missing input sequence IDs: " + ", ".join(missing)
        )
    extra = [seq_id for seq_id in member_counts if seq_id not in expected_set]
    if extra:
        raise S5SequenceClusteringError(
            "MMseqs output contains unexpected sequence IDs: " + ", ".join(extra)
        )
    if len(members_seen) != len(expected):
        raise S5SequenceClusteringError("MMseqs member count does not match input sequences")
    return pairs


def build_cluster_rows(
    pairs: Sequence[tuple[str, str]],
    sequence_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    by_id = {_blank(row["sequence_id"]): row for row in sequence_rows}
    grouped: dict[str, list[str]] = defaultdict(list)
    rep_by_member: dict[str, str] = {}
    for representative, member in pairs:
        grouped[representative].append(member)
        if member in rep_by_member:
            raise S5SequenceClusteringError(
                f"sequence {member} assigned to multiple MMseqs clusters"
            )
        rep_by_member[member] = representative

    cluster_rows: list[dict[str, str]] = []
    for representative, members in grouped.items():
        unique_members = sorted(set(members))
        if representative not in unique_members:
            raise S5SequenceClusteringError(
                f"MMseqs representative {representative} is not a member of its cluster"
            )
        digests = [by_id[member_id]["sequence_core_sha256"] for member_id in unique_members]
        cluster_id = stable_cluster_id(digests)
        for member_id in unique_members:
            member_row = by_id[member_id]
            cluster_rows.append(
                fill_row(
                    CLUSTER_TSV_COLUMNS,
                    {
                        "cluster_id": cluster_id,
                        "mmseqs_representative_sequence_id": representative,
                        "member_sequence_id": member_id,
                        "member_sequence_core_sha256": member_row["sequence_core_sha256"],
                        "sequence_length": member_row["sequence_length"],
                        "member_is_mmseqs_representative": bool_token(
                            member_id == representative
                        ),
                    },
                )
            )
    cluster_rows.sort(
        key=lambda row: (row["cluster_id"], row["member_sequence_id"])
    )
    _assert_one_cluster_per_sequence(cluster_rows)
    return cluster_rows


def _assert_one_cluster_per_sequence(cluster_rows: Sequence[Mapping[str, str]]) -> None:
    by_member: dict[str, set[str]] = defaultdict(set)
    for row in cluster_rows:
        by_member[row["member_sequence_id"]].add(row["cluster_id"])
    multi = {
        member: sorted(clusters)
        for member, clusters in by_member.items()
        if len(clusters) != 1
    }
    if multi:
        raise S5SequenceClusteringError(
            "sequence assigned to multiple clusters: " + ", ".join(sorted(multi))
        )


def membership_signature(
    cluster_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    members_by_cluster: dict[str, set[str]] = defaultdict(set)
    reps: dict[str, str] = {}
    for row in cluster_rows:
        cluster_id = row["cluster_id"]
        members_by_cluster[cluster_id].add(row["member_sequence_id"])
        if row["member_is_mmseqs_representative"] == "true":
            reps[cluster_id] = row["mmseqs_representative_sequence_id"]
    frozen = {
        cluster_id: frozenset(members)
        for cluster_id, members in members_by_cluster.items()
    }
    return {
        "cluster_ids": tuple(sorted(frozen)),
        "membership": {cluster_id: tuple(sorted(members)) for cluster_id, members in sorted(frozen.items())},
        "mmseqs_representatives": {cluster_id: reps[cluster_id] for cluster_id in sorted(reps)},
    }


def compare_cluster_runs(
    first: Sequence[Mapping[str, str]],
    second: Sequence[Mapping[str, str]],
) -> None:
    sig_a = membership_signature(first)
    sig_b = membership_signature(second)
    if sig_a["membership"] != sig_b["membership"]:
        raise S5SequenceClusteringError(
            "NO-GO: MMseqs cluster membership differed across identical runs"
        )
    if sig_a["cluster_ids"] != sig_b["cluster_ids"]:
        raise S5SequenceClusteringError(
            "NO-GO: stable cluster IDs differed despite claimed identical membership"
        )
    if sig_a["mmseqs_representatives"] != sig_b["mmseqs_representatives"]:
        raise S5SequenceClusteringError(
            "NO-GO: MMseqs representative selection differed across identical runs"
        )
    if list(first) != list(second):
        raise S5SequenceClusteringError(
            "NO-GO: canonical clusters.tsv rows are not byte-comparable across runs"
        )


def scientific_representatives(
    clustered_identities: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    """One scientific identity representative per cluster.

    Technical selection only: MMseqs representative core, then the
    lexicographically smallest ``scientific_identity_id``. Donor ``record_id``
    is never used.
    """
    chosen: dict[str, str] = {}
    candidates: dict[str, list[str]] = defaultdict(list)
    mmseqs_rep_core: dict[str, str] = {}
    for row in clustered_identities:
        cluster_id = _blank(row.get("cluster_id"))
        if row.get("is_mmseqs_sequence_representative") == "true":
            mmseqs_rep_core[cluster_id] = _blank(row.get("sequence_core"))
    for row in clustered_identities:
        cluster_id = _blank(row.get("cluster_id"))
        if _blank(row.get("sequence_core")) == mmseqs_rep_core.get(cluster_id):
            candidates[cluster_id].append(_blank(row.get("scientific_identity_id")))
    missing = sorted(set(mmseqs_rep_core) - set(candidates))
    if missing:
        raise S5SequenceClusteringError(
            "no scientific identities found for MMseqs representative cores"
        )
    for cluster_id, identity_ids in candidates.items():
        if not identity_ids:
            raise S5SequenceClusteringError(
                f"cluster {cluster_id} has no scientific representative candidates"
            )
        chosen[cluster_id] = min(identity_ids)
    return chosen


def broadcast_clusters(
    corpus_rows: Sequence[Mapping[str, str]],
    sequence_rows: Sequence[Mapping[str, str]],
    cluster_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    seq_by_core = {_blank(row["sequence_core"]): row for row in sequence_rows}
    seq_by_id = {_blank(row["sequence_id"]): row for row in sequence_rows}
    cluster_by_member = {
        row["member_sequence_id"]: row for row in cluster_rows
    }
    if len(cluster_by_member) != len(cluster_rows):
        raise S5SequenceClusteringError("cluster membership is not unique by sequence")

    annotated: list[dict[str, str]] = []
    for row in corpus_rows:
        core = _blank(row.get("sequence_core"))
        seq_row = seq_by_core.get(core)
        if seq_row is None:
            raise S5SequenceClusteringError(
                "scientific identity has no sequence-level clustering row"
            )
        cluster_row = cluster_by_member[seq_row["sequence_id"]]
        mmseqs_rep_id = cluster_row["mmseqs_representative_sequence_id"]
        mmseqs_rep_seq = seq_by_id[mmseqs_rep_id]
        values = {column: _blank(row.get(column)) for column in CORPUS_DEDUP_COLUMNS}
        values["cluster_id"] = cluster_row["cluster_id"]
        values["is_cluster_representative"] = "false"
        values["sequence_id"] = seq_row["sequence_id"]
        values["sequence_core_sha256"] = seq_row["sequence_core_sha256"]
        values["mmseqs_representative_sequence_id"] = mmseqs_rep_id
        values["mmseqs_representative_sequence_core_sha256"] = mmseqs_rep_seq[
            "sequence_core_sha256"
        ]
        values["is_mmseqs_sequence_representative"] = cluster_row[
            "member_is_mmseqs_representative"
        ]
        identity = _blank(row.get("scientific_identity_id"))
        if not identity:
            raise S5SequenceClusteringError(
                "clustering must key on scientific_identity_id; it is missing"
            )
        annotated.append(fill_row(CORPUS_CLUSTERED_COLUMNS, values))

    chosen = scientific_representatives(annotated)
    for row in annotated:
        row["is_cluster_representative"] = bool_token(
            row["scientific_identity_id"] == chosen.get(row["cluster_id"])
        )
    _assert_one_scientific_representative(annotated)
    _assert_shared_cores_share_cluster(annotated)
    return annotated


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
        raise S5SequenceClusteringError(
            f"{len(missing)} clusters lack a scientific representative"
        )
    extra = {
        cluster_id: identities
        for cluster_id, identities in by_cluster.items()
        if len(identities) != 1
    }
    if extra:
        raise S5SequenceClusteringError(
            "clusters with !=1 scientific representative: "
            + ", ".join(sorted(extra))
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
        raise S5SequenceClusteringError(
            "identical sequence_core values received different cluster IDs"
        )


def build_cluster_summary(
    clustered_corpus: Sequence[Mapping[str, str]],
    cluster_rows: Sequence[Mapping[str, str]],
    sequence_rows: Sequence[Mapping[str, str]],
    membership_rows: Sequence[Mapping[str, str]] | None = None,
) -> list[dict[str, str]]:
    seq_by_id = {row["sequence_id"]: row for row in sequence_rows}
    identities_by_cluster: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in clustered_corpus:
        identities_by_cluster[row["cluster_id"]].append(row)
    members_by_cluster: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in cluster_rows:
        members_by_cluster[row["cluster_id"]].append(row)

    ena_identities = _ena_identity_ids(membership_rows or (), clustered_corpus)
    summary: list[dict[str, str]] = []
    for cluster_id, members in members_by_cluster.items():
        identities = identities_by_cluster[cluster_id]
        lengths = [int(row["sequence_length"]) for row in members]
        targets = {
            _blank(row.get("canonical_target_name"))
            for row in identities
            if _blank(row.get("canonical_target_name"))
        }
        sources: set[str] = set()
        for row in identities:
            sources.update(split_pipe(row.get("contributing_sources") or ""))
            if _blank(row.get("source_db")):
                sources.add(_blank(row.get("source_db")))
        cores = Counter(_blank(row.get("sequence_core")) for row in identities)
        contains_shared_core = any(count > 1 for count in cores.values())
        rep = next(
            row for row in members if row["member_is_mmseqs_representative"] == "true"
        )
        ena_present = any(
            _blank(row.get("scientific_identity_id")) in ena_identities
            for row in identities
        )
        summary.append(
            fill_row(
                CLUSTER_SUMMARY_COLUMNS,
                {
                    "cluster_id": cluster_id,
                    "n_distinct_sequences": str(len(members)),
                    "n_scientific_identities": str(len(identities)),
                    "representative_sequence_id": rep["member_sequence_id"],
                    "representative_sequence_core_sha256": seq_by_id[rep["member_sequence_id"]][
                        "sequence_core_sha256"
                    ],
                    "min_sequence_length": str(min(lengths)),
                    "median_sequence_length": _format_median(lengths),
                    "max_sequence_length": str(max(lengths)),
                    "n_targets": str(len(targets)),
                    "n_sources": str(len(sources)),
                    "contains_multi_target_identical_core": bool_token(contains_shared_core),
                    "ena_provenance_present": bool_token(ena_present),
                },
            )
        )
    summary.sort(key=lambda row: row["cluster_id"])
    return summary


def _format_median(values: Sequence[int]) -> str:
    if not values:
        return ""
    value = median(values)
    if float(value) == int(value):
        return str(int(value))
    return str(value)


def _ena_identity_ids(
    membership_rows: Sequence[Mapping[str, str]],
    clustered_corpus: Sequence[Mapping[str, str]],
) -> set[str]:
    identities: set[str] = set()
    for row in membership_rows:
        if _blank(row.get("source_db")) == "ena":
            identity = _blank(row.get("scientific_identity_id"))
            if identity:
                identities.add(identity)
    for row in clustered_corpus:
        sources = set(split_pipe(row.get("contributing_sources") or ""))
        if "ena" in sources:
            identities.add(_blank(row.get("scientific_identity_id")))
    return identities


def build_identity_audit(
    cluster_rows: Sequence[Mapping[str, str]],
    sequence_rows: Sequence[Mapping[str, str]],
    *,
    min_seq_id: float = 0.90,
) -> list[dict[str, str]]:
    """Read-only diagnostic. Does not replace MMseqs as the clustering algorithm."""
    seq_by_id = {row["sequence_id"]: row for row in sequence_rows}
    members_by_cluster: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in cluster_rows:
        members_by_cluster[row["cluster_id"]].append(row)
    audit: list[dict[str, str]] = []
    for cluster_id, members in members_by_cluster.items():
        if len(members) < 2:
            continue
        rep = next(
            row for row in members if row["member_is_mmseqs_representative"] == "true"
        )
        rep_core = seq_by_id[rep["member_sequence_id"]]["sequence_core"]
        rep_len = len(rep_core)
        for member in members:
            member_core = seq_by_id[member["member_sequence_id"]]["sequence_core"]
            identity = global_edit_identity(rep_core, member_core)
            audit.append(
                fill_row(
                    IDENTITY_AUDIT_COLUMNS,
                    {
                        "cluster_id": cluster_id,
                        "mmseqs_representative_sequence_id": rep["member_sequence_id"],
                        "member_sequence_id": member["member_sequence_id"],
                        "representative_length": str(rep_len),
                        "member_length": str(len(member_core)),
                        "length_delta": str(len(member_core) - rep_len),
                        "global_levenshtein_identity_diagnostic": f"{identity:.6f}",
                        "meets_configured_threshold_under_global_levenshtein_diagnostic": bool_token(
                            identity >= min_seq_id
                        ),
                        "mmseqs_identity_available": "false",
                        "mmseqs_coverage_available": "false",
                    },
                )
            )
    audit.sort(
        key=lambda row: (
            row["cluster_id"],
            row["member_sequence_id"],
        )
    )
    return audit


def build_ena_family_diagnostics(
    membership_rows: Sequence[Mapping[str, str]],
    clustered_corpus: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    identity_cluster = {
        _blank(row.get("scientific_identity_id")): _blank(row.get("cluster_id"))
        for row in clustered_corpus
    }
    identity_core = {
        _blank(row.get("scientific_identity_id")): _blank(row.get("sequence_core"))
        for row in clustered_corpus
    }
    family_rows: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    declared_multi: set[str] = set()
    for row in membership_rows:
        if _blank(row.get("source_db")) != "ena":
            continue
        family_id = _blank(row.get("ena_effective_near_duplicate_family_id"))
        if not family_id:
            continue
        family_rows[family_id].append(row)
        size_raw = _blank(row.get("ena_effective_near_duplicate_family_size"))
        try:
            if size_raw and int(size_raw) > 1:
                declared_multi.add(family_id)
        except ValueError:
            continue

    cluster_families: dict[str, set[str]] = defaultdict(set)
    output_rows: list[dict[str, str]] = []
    for family_id, rows in family_rows.items():
        identities = [
            _blank(row.get("scientific_identity_id"))
            for row in rows
            if _blank(row.get("scientific_identity_id"))
        ]
        cores = {
            identity_core.get(identity, _blank(row.get("sequence_core")))
            for identity, row in zip(identities, rows)
        }
        cores.discard("")
        clusters = {identity_cluster.get(identity, "") for identity in identities}
        clusters.discard("")
        for cluster_id in clusters:
            cluster_families[cluster_id].add(family_id)
        output_rows.append(
            fill_row(
                ENA_FAMILY_DIAGNOSTIC_COLUMNS,
                {
                    "ena_family_id": family_id,
                    "declared_multi_member": bool_token(family_id in declared_multi),
                    "n_s5_ena_membership_rows": str(len(rows)),
                    "n_s5_ena_sequence_cores": str(len(cores)),
                    "n_s5c_clusters": str(len(clusters)),
                    "contained_in_one_cluster": bool_token(len(clusters) == 1),
                    "cluster_ids": "|".join(sorted(clusters)),
                },
            )
        )
    output_rows.sort(key=lambda row: row["ena_family_id"])
    multi_member = [
        row for row in output_rows if int(row["n_s5_ena_membership_rows"]) >= 2
    ]
    singleton_source = [
        row for row in output_rows if int(row["n_s5_ena_membership_rows"]) == 1
    ]
    multi_family_clusters = [
        cluster_id
        for cluster_id, families in cluster_families.items()
        if len(families) > 1
    ]
    contained = [row for row in multi_member if row["contained_in_one_cluster"] == "true"]
    split = [row for row in multi_member if row["contained_in_one_cluster"] == "false"]
    singleton_sharing = 0
    for row in singleton_source:
        cluster_ids = split_pipe(row["cluster_ids"])
        if any(cluster_id in {item for item in multi_family_clusters} for cluster_id in cluster_ids):
            singleton_sharing += 1
    diagnostics = {
        "n_ena_family_ids_represented": len(output_rows),
        "n_declared_multi_member_families_represented": len(declared_multi),
        "n_multi_member_families_with_at_least_two_s5_members": len(multi_member),
        "n_multi_member_families_contained_in_one_cluster": len(contained),
        "n_multi_member_families_split_across_gt1_cluster": len(split),
        "n_singleton_source_families": len(singleton_source),
        "n_singleton_source_families_sharing_cluster_with_another_ena_family": singleton_sharing,
        "n_clusters_containing_multiple_ena_families": len(multi_family_clusters),
        "multi_member_family_ids": [row["ena_family_id"] for row in multi_member],
        "contained_family_ids": [row["ena_family_id"] for row in contained],
        "split_family_ids": [row["ena_family_id"] for row in split],
        "multi_family_cluster_ids": sorted(multi_family_clusters),
        "adjudication": "deferred_to_s5d",
    }
    return output_rows, diagnostics


def sequence_population_diagnostics(
    corpus_rows: Sequence[Mapping[str, str]],
    sequence_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    cores = [_blank(row.get("sequence_core")) for row in corpus_rows]
    missing = sum(1 for core in cores if not core)
    identity_lengths = [len(core) for core in cores if core]
    core_lengths = [int(row["sequence_length"]) for row in sequence_rows]
    rules = load_normalisation_rules()
    identity_alphabet: Counter[str] = Counter()
    core_alphabet: Counter[str] = Counter()
    identity_outside = 0
    core_outside = 0
    for row in corpus_rows:
        core = _blank(row.get("sequence_core"))
        if not core:
            continue
        classified = classify_alphabet(
            core, rules=rules, molecule_type=row.get("molecule_type")
        )
        identity_alphabet[classified.alphabet] += 1
        if classified.alphabet in {ALPHABET_INVALID, ALPHABET_MISSING}:
            raise S5SequenceClusteringError(
                "invalid or missing sequence alphabet encountered; S4/S5 freeze is intact and S5C does not retype"
            )
        if not validate_core_length(core, rules).within_policy:
            identity_outside += 1
    seen_cores: set[str] = set()
    for row in sequence_rows:
        core = row["sequence_core"]
        classified = classify_alphabet(core, rules=rules)
        core_alphabet[classified.alphabet] += 1
        if not validate_core_length(core, rules).within_policy:
            core_outside += 1
        seen_cores.add(core)
    core_counts = Counter(cores)
    shared = {core: count for core, count in core_counts.items() if core and count > 1}
    return {
        "n_scientific_identities": len(corpus_rows),
        "n_distinct_sequence_core": len(sequence_rows),
        "n_missing_sequence_core": missing,
        "n_shared_sequence_cores": len(shared),
        "n_shared_core_identities": sum(shared.values()),
        "n_extra_identities_from_shared_cores": max(len(cores) - len(sequence_rows), 0),
        "sequence_id_unique": len({row["sequence_id"] for row in sequence_rows})
        == len(sequence_rows),
        "identity_length_min": min(identity_lengths) if identity_lengths else None,
        "identity_length_median": float(median(identity_lengths)) if identity_lengths else None,
        "identity_length_max": max(identity_lengths) if identity_lengths else None,
        "core_length_min": min(core_lengths) if core_lengths else None,
        "core_length_median": float(median(core_lengths)) if core_lengths else None,
        "core_length_max": max(core_lengths) if core_lengths else None,
        "n_identities_outside_20_100": identity_outside,
        "n_cores_outside_20_100": core_outside,
        "identity_alphabet_distribution": dict(sorted(identity_alphabet.items())),
        "core_alphabet_distribution": dict(sorted(core_alphabet.items())),
        "length_outliers_not_filtered": True,
        "alphabet_not_retyped": True,
    }


def structural_cluster_diagnostics(
    clustered_corpus: Sequence[Mapping[str, str]],
    cluster_rows: Sequence[Mapping[str, str]],
    cluster_summary_rows: Sequence[Mapping[str, str]],
    sequence_rows: Sequence[Mapping[str, str]],
    identity_audit_rows: Sequence[Mapping[str, str]],
    *,
    min_seq_id: float = 0.90,
) -> dict[str, Any]:
    n_sequences = len(sequence_rows)
    n_clusters = len(cluster_summary_rows)
    size_counts = Counter(int(row["n_distinct_sequences"]) for row in cluster_summary_rows)
    identity_counts = Counter(
        int(row["n_scientific_identities"]) for row in cluster_summary_rows
    )
    singletons = sum(1 for row in cluster_summary_rows if int(row["n_distinct_sequences"]) == 1)
    multi = n_clusters - singletons
    largest = max(size_counts) if size_counts else 0
    largest_clusters = [
        {
            "cluster_id": row["cluster_id"],
            "n_distinct_sequences": int(row["n_distinct_sequences"]),
            "n_scientific_identities": int(row["n_scientific_identities"]),
            "n_targets": int(row["n_targets"]),
        }
        for row in sorted(
            cluster_summary_rows,
            key=lambda item: (-int(item["n_distinct_sequences"]), item["cluster_id"]),
        )[:10]
    ]
    singleton_lengths = [
        int(row["sequence_length"])
        for row in cluster_rows
        if int(
            next(
                summary["n_distinct_sequences"]
                for summary in cluster_summary_rows
                if summary["cluster_id"] == row["cluster_id"]
            )
        )
        == 1
    ]
    multi_lengths = [
        int(row["sequence_length"])
        for row in cluster_rows
        if int(
            next(
                summary["n_distinct_sequences"]
                for summary in cluster_summary_rows
                if summary["cluster_id"] == row["cluster_id"]
            )
        )
        > 1
    ]
    n_rep_true = sum(
        1 for row in clustered_corpus if row.get("is_cluster_representative") == "true"
    )
    levenshtein_below = [
        row
        for row in identity_audit_rows
        if row["meets_configured_threshold_under_global_levenshtein_diagnostic"] == "false"
        and row["member_sequence_id"] != row["mmseqs_representative_sequence_id"]
    ]
    return {
        "n_clusters": n_clusters,
        "n_singleton_clusters": singletons,
        "n_multi_sequence_clusters": multi,
        "singleton_fraction": (singletons / n_clusters) if n_clusters else None,
        "largest_cluster_size": largest,
        "cluster_size_distribution": dict(sorted(size_counts.items())),
        "identities_per_cluster_distribution": dict(sorted(identity_counts.items())),
        "n_clusters_gt1_canonical_target": sum(
            1 for row in cluster_summary_rows if int(row["n_targets"]) > 1
        ),
        "n_clusters_gt1_source": sum(
            1 for row in cluster_summary_rows if int(row["n_sources"]) > 1
        ),
        "n_clusters_with_ena_provenance": sum(
            1 for row in cluster_summary_rows if row["ena_provenance_present"] == "true"
        ),
        "n_clusters_with_multi_target_identical_core": sum(
            1
            for row in cluster_summary_rows
            if row["contains_multi_target_identical_core"] == "true"
        ),
        "n_unique_sequence_cores_before_clustering": n_sequences,
        "n_clusters_after_clustering": n_clusters,
        "n_reduction_due_to_near_sequence_clustering": n_sequences - n_clusters,
        "n_clusters_whose_members_are_not_all_identical": multi,
        "scientific_identities_retained": len(clustered_corpus),
        "n_scientific_representatives": n_rep_true,
        "length_by_cluster_size": {
            "singleton_clusters": _length_stats(singleton_lengths),
            "multi_sequence_clusters": _length_stats(multi_lengths),
        },
        "largest_clusters": largest_clusters,
        "identity_audit": {
            "definition": (
                "global Levenshtein identity on native sequence_core; "
                "diagnostic only; not the MMseqs identity definition"
            ),
            "n_non_singleton_member_rows": len(identity_audit_rows),
            "n_member_vs_rep_below_threshold_under_levenshtein": len(levenshtein_below),
            "configured_min_seq_id": min_seq_id,
            "mmseqs_pairwise_identity_in_cluster_tsv": False,
            "clusters_not_rejected_for_definition_mismatch": True,
        },
        "no_row_removal": len(clustered_corpus),
    }


def _length_stats(values: Sequence[int]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "min": None, "median": None, "max": None}
    return {
        "n": len(values),
        "min": min(values),
        "median": float(median(values)),
        "max": max(values),
    }


def multi_target_preservation(
    clustered_corpus: Sequence[Mapping[str, str]],
    *,
    membership_rows: Sequence[Mapping[str, str]] | None = None,
    expected_shared_cores: int | None = None,
    expected_shared_identities: int | None = None,
    expected_shared_membership_rows: int | None = None,
) -> dict[str, Any]:
    core_groups: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in clustered_corpus:
        core_groups[_blank(row.get("sequence_core"))].append(row)
    shared = {core: rows for core, rows in core_groups.items() if len(rows) > 1}
    inconsistent = [
        sequence_core_digest(core)
        for core, rows in shared.items()
        if len({_blank(row.get("cluster_id")) for row in rows}) != 1
    ]
    if inconsistent:
        raise S5SequenceClusteringError(
            "shared sequence cores were assigned inconsistent cluster IDs"
        )
    targets_unchanged = all(
        _blank(row.get("canonical_target_name")) for rows in shared.values() for row in rows
    )
    shared_identities = {
        _blank(row.get("scientific_identity_id"))
        for rows in shared.values()
        for row in rows
    }
    membership_on_shared = []
    if membership_rows is not None:
        membership_on_shared = [
            row
            for row in membership_rows
            if _blank(row.get("sequence_core")) in shared
        ]
        missing_identities = [
            _blank(row.get("scientific_identity_id"))
            for row in membership_on_shared
            if _blank(row.get("scientific_identity_id")) not in shared_identities
        ]
        if missing_identities:
            raise S5SequenceClusteringError(
                "shared-core membership rows were dropped from the clustered corpus"
            )
    result = {
        "n_shared_sequence_cores": len(shared),
        "n_shared_core_identities": sum(len(rows) for rows in shared.values()),
        "n_shared_core_membership_rows": len(membership_on_shared),
        "shared_cores_consistent_cluster_id": True,
        "canonical_targets_present": targets_unchanged,
        "n_scientific_identities": len(clustered_corpus),
        "n_unique_scientific_identity_id": len(
            {_blank(row.get("scientific_identity_id")) for row in clustered_corpus}
        ),
        "n_missing_cluster_id": sum(
            1 for row in clustered_corpus if not _blank(row.get("cluster_id"))
        ),
        "n_clusters_with_several_sequences_and_several_targets": sum(
            1
            for cluster_id, rows in _group_by(clustered_corpus, "cluster_id").items()
            if len({_blank(row.get("sequence_core")) for row in rows}) > 1
            and len({_blank(row.get("canonical_target_name")) for row in rows}) > 1
        ),
        "s5a_326_is_membership_rows_not_identities": True,
    }
    if expected_shared_cores is not None and result["n_shared_sequence_cores"] != expected_shared_cores:
        raise S5SequenceClusteringError(
            "shared sequence core count drifted from the S5A/S5B freeze"
        )
    if (
        expected_shared_identities is not None
        and result["n_shared_core_identities"] != expected_shared_identities
    ):
        raise S5SequenceClusteringError(
            "shared-core scientific identity count drifted from the S5A/S5B freeze"
        )
    if (
        expected_shared_membership_rows is not None
        and result["n_shared_core_membership_rows"] != expected_shared_membership_rows
    ):
        raise S5SequenceClusteringError(
            "shared-core membership/relationship count drifted from the S5A/S5B freeze"
        )
    return result


def _group_by(
    rows: Sequence[Mapping[str, str]], key: str
) -> dict[str, list[Mapping[str, str]]]:
    grouped: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[_blank(row.get(key))].append(row)
    return grouped


def expected_count_errors(
    diagnostics: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    for key, wanted in expected.items():
        if key not in diagnostics:
            continue
        if diagnostics[key] != wanted:
            errors.append(f"{key}: expected {wanted}, got {diagnostics[key]}")
    return errors


def assemble_clustering(
    *,
    corpus_rows: Sequence[Mapping[str, str]],
    mmseqs_cluster_tsv: str,
    membership_rows: Sequence[Mapping[str, str]] | None = None,
    min_seq_id: float = 0.90,
    expected_counts: Mapping[str, Any] | None = None,
) -> SequenceClusteringResult:
    sequence_rows, identity_map = project_unique_sequence_cores(corpus_rows)
    pairs = parse_mmseqs_cluster_tsv(
        mmseqs_cluster_tsv,
        input_sequence_ids=[row["sequence_id"] for row in sequence_rows],
    )
    cluster_rows = build_cluster_rows(pairs, sequence_rows)
    clustered_corpus = broadcast_clusters(corpus_rows, sequence_rows, cluster_rows)
    summary = build_cluster_summary(
        clustered_corpus,
        cluster_rows,
        sequence_rows,
        membership_rows or (),
    )
    audit = build_identity_audit(
        cluster_rows, sequence_rows, min_seq_id=min_seq_id
    )
    ena_rows, ena_diag = build_ena_family_diagnostics(
        membership_rows or (), clustered_corpus
    )
    population = sequence_population_diagnostics(corpus_rows, sequence_rows)
    structural = structural_cluster_diagnostics(
        clustered_corpus,
        cluster_rows,
        summary,
        sequence_rows,
        audit,
        min_seq_id=min_seq_id,
    )
    multi = multi_target_preservation(
        clustered_corpus,
        membership_rows=membership_rows,
        expected_shared_cores=(expected_counts or {}).get("n_shared_sequence_cores"),
        expected_shared_identities=(expected_counts or {}).get("n_shared_core_identities"),
        expected_shared_membership_rows=(expected_counts or {}).get(
            "n_shared_core_membership_rows"
        ),
    )
    diagnostics: dict[str, Any] = {
        **population,
        **structural,
        "multi_target": multi,
        "ena_family_diagnostics": ena_diag,
        "n_missing_cluster_id": multi["n_missing_cluster_id"],
        "n_shared_core_membership_rows": multi["n_shared_core_membership_rows"],
        "fasta_sort": [
            "sequence_core_sha256 ascending",
            "sequence_id ascending",
        ],
        "cluster_id_convention": (
            "S5C_ + sha256 of sorted member sequence_core_sha256 values "
            "joined by U+001F"
        ),
        "representative_convention": (
            "preserve MMseqs sequence representative; scientific identity "
            "representative is the lexicographically smallest "
            "scientific_identity_id among identities carrying that core"
        ),
    }
    if expected_counts:
        errors = expected_count_errors(diagnostics, expected_counts)
        if errors:
            raise S5SequenceClusteringError(
                "S5C expected-count regression:\n" + "\n".join(errors)
            )
    if diagnostics["n_scientific_identities"] != diagnostics["scientific_identities_retained"]:
        raise S5SequenceClusteringError("NO-GO: clustering removed scientific identities")
    return SequenceClusteringResult(
        sequence_rows=sequence_rows,
        identity_map_rows=identity_map,
        cluster_rows=cluster_rows,
        clustered_corpus=clustered_corpus,
        cluster_summary_rows=summary,
        identity_audit_rows=audit,
        ena_family_rows=ena_rows,
        diagnostics=diagnostics,
    )


def preflight_synthetic_sequences() -> dict[str, str]:
    """Runtime-constructed synthetic sequences; source literals stay <20 nt."""
    rna_a = "AGCUAGGAUC" + "CGAUAGCUUA" + "GGCAUCGGAU" + "AGCUAGCUAA"
    rna_near = "AGCUAGGAUC" + "CGAUAGCUUA" + "GGCAUCGGAU" + "AGCUAGCAAC"
    rna_far = "GGGAACCCAA" + "AGGGCCCUUU" + "AAAGCGCGCG" + "AAUUUCCGGA"
    return {
        PREFLIGHT_U_ID: rna_a,
        PREFLIGHT_U_DUP_ID: rna_a,
        PREFLIGHT_U_NEAR_ID: rna_near,
        PREFLIGHT_T_ID: rna_a.replace("U", "T"),
        PREFLIGHT_MIXED_ID: rna_a[:20].replace("U", "T") + rna_a[20:],
        PREFLIGHT_FAR_ID: rna_far,
    }


def interpret_rna_u_preflight(
    pairs: Sequence[tuple[str, str]],
) -> dict[str, Any]:
    member_to_rep = {member: representative for representative, member in pairs}
    u_cluster = {
        member_to_rep.get(PREFLIGHT_U_ID),
        member_to_rep.get(PREFLIGHT_U_DUP_ID),
    }
    identical_u_clustered = len(u_cluster) == 1 and None not in u_cluster
    near_with_u = member_to_rep.get(PREFLIGHT_U_NEAR_ID) == member_to_rep.get(
        PREFLIGHT_U_ID
    )
    t_with_u = member_to_rep.get(PREFLIGHT_T_ID) == member_to_rep.get(PREFLIGHT_U_ID)
    mixed_with_u = member_to_rep.get(PREFLIGHT_MIXED_ID) == member_to_rep.get(
        PREFLIGHT_U_ID
    )
    far_rep = member_to_rep.get(PREFLIGHT_FAR_ID)
    u_rep = member_to_rep.get(PREFLIGHT_U_ID)
    far_separate = far_rep is not None and u_rep is not None and far_rep != u_rep
    accepts_u = identical_u_clustered
    u_valid_nucleotide = identical_u_clustered and near_with_u
    go = bool(accepts_u and u_valid_nucleotide and far_separate)
    return {
        "accepts_acgu_fasta": True,
        "identical_u_sequences_cluster": identical_u_clustered,
        "near_identical_u_sequences_cluster": near_with_u,
        "u_treated_as_valid_nucleotide": u_valid_nucleotide,
        "u_internally_equivalent_to_t": t_with_u,
        "mixed_t_u_follows_u_t_equivalence": mixed_with_u,
        "distant_sequence_not_clustered_with_u_pair": far_separate,
        "input_transcoded_u_to_t": False,
        "derived_u_to_t_corpus_created": False,
        "go": go,
        "membership": {
            member: representative for representative, member in sorted(pairs)
        },
    }


def mmseqs_command(
    *,
    fasta_path: Path,
    output_prefix: Path,
    tmp_dir: Path,
    min_seq_id: float,
    coverage: float,
    cov_mode: int,
    sensitivity: float,
    threads: int,
    mmseqs_bin: str,
) -> list[str]:
    return [
        mmseqs_bin,
        "easy-cluster",
        str(fasta_path),
        str(output_prefix),
        str(tmp_dir),
        "--min-seq-id",
        _mmseqs_float(min_seq_id),
        "-c",
        _mmseqs_float(coverage),
        "--cov-mode",
        str(int(cov_mode)),
        "-s",
        _mmseqs_float(sensitivity),
        "--threads",
        str(int(threads)),
    ]


def _mmseqs_float(value: float) -> str:
    if float(value) == 0.9:
        return "0.9"
    if float(value) == 0.8:
        return "0.8"
    if float(value) == 7.5:
        return "7.5"
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text


def run_mmseqs_easy_cluster(
    *,
    fasta_path: Path,
    output_prefix: Path,
    tmp_dir: Path,
    min_seq_id: float,
    coverage: float,
    cov_mode: int,
    sensitivity: float,
    threads: int = 1,
    mmseqs_bin: str = "mmseqs",
) -> dict[str, Any]:
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    command = mmseqs_command(
        fasta_path=fasta_path,
        output_prefix=output_prefix,
        tmp_dir=tmp_dir,
        min_seq_id=min_seq_id,
        coverage=coverage,
        cov_mode=cov_mode,
        sensitivity=sensitivity,
        threads=threads,
        mmseqs_bin=mmseqs_bin,
    )
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    tsv_path = Path(str(output_prefix) + "_cluster.tsv")
    if completed.returncode != 0 or not tsv_path.is_file():
        raise S5SequenceClusteringError(
            "MMseqs2 easy-cluster failed: "
            + (completed.stderr or completed.stdout or f"exit {completed.returncode}")
        )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "cluster_tsv_path": tsv_path,
        "cluster_tsv_text": tsv_path.read_text(encoding="utf-8"),
        "rep_seq_fasta": Path(str(output_prefix) + "_rep_seq.fasta"),
        "all_seqs_fasta": Path(str(output_prefix) + "_all_seqs.fasta"),
    }


def discover_mmseqs_environment() -> dict[str, Any]:
    mmseqs_path = shutil.which("mmseqs")
    version = ""
    if mmseqs_path:
        completed = subprocess.run(
            [mmseqs_path, "version"],
            check=False,
            capture_output=True,
            text=True,
        )
        version = (completed.stdout or completed.stderr or "").strip().splitlines()[0] if (completed.stdout or completed.stderr) else ""
    cd_hit = shutil.which("cd-hit-est")
    return {
        "mmseqs_path": mmseqs_path or "",
        "mmseqs_version": version,
        "cd_hit_est_path": cd_hit or "",
        "cd_hit_est_installed": bool(cd_hit),
        "cd_hit_fallback_run": False,
    }


def build_s5c_report(
    diagnostics: Mapping[str, Any],
    *,
    tool: Mapping[str, Any],
    preflight: Mapping[str, Any],
    command: Sequence[str],
) -> str:
    ena = diagnostics.get("ena_family_diagnostics") or {}
    multi = diagnostics.get("multi_target") or {}
    identity_audit = diagnostics.get("identity_audit") or {}
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
    alphabet_id = diagnostics.get("identity_alphabet_distribution") or {}
    alphabet_core = diagnostics.get("core_alphabet_distribution") or {}
    largest_lines = []
    for item in diagnostics.get("largest_clusters") or []:
        largest_lines.append(
            f"- {item['cluster_id']}: {item['n_distinct_sequences']} sequences, "
            f"{item['n_scientific_identities']} identities, "
            f"{item['n_targets']} targets"
        )
    contained = ena.get("contained_family_ids") or []
    split = ena.get("split_family_ids") or []
    family_lines = [
        f"- {family_id}: contained_in_one_cluster=true"
        for family_id in contained
    ] + [
        f"- {family_id}: contained_in_one_cluster=false"
        for family_id in split
    ]
    length_by_size = diagnostics.get("length_by_cluster_size") or {}
    singleton_len = length_by_size.get("singleton_clusters") or {}
    multi_len = length_by_size.get("multi_sequence_clusters") or {}
    text = "\n".join(
        [
            "# Global S5C — 90% sequence-identity clustering",
            "",
            "S5C clusters exact-deduplicated primary sequences at 90% identity.",
            "It does not run CD-HIT, adjudicate ENA-family recall, balance",
            "targets, assign FT/REF/EVAL, or begin S6/S7.",
            "",
            "## Tool",
            "",
            f"- tool: {tool.get('tool_name', 'mmseqs2')}",
            f"- path: {tool.get('mmseqs_path')}",
            f"- version: {tool.get('mmseqs_version')}",
            f"- installation: {tool.get('installation_method')}",
            f"- CD-HIT installed: {tool.get('cd_hit_est_installed')}",
            f"- CD-HIT fallback run: {tool.get('cd_hit_fallback_run')}",
            f"- command: {' '.join(command)}",
            "",
            "## RNA/U preflight",
            "",
            f"- accepts A/C/G/U FASTA: {preflight.get('accepts_acgu_fasta')}",
            f"- identical U sequences cluster: {preflight.get('identical_u_sequences_cluster')}",
            f"- near-identical U sequences cluster: {preflight.get('near_identical_u_sequences_cluster')}",
            f"- U treated as valid nucleotide: {preflight.get('u_treated_as_valid_nucleotide')}",
            f"- U internally equivalent to T: {preflight.get('u_internally_equivalent_to_t')}",
            f"- mixed T/U follows that equivalence: {preflight.get('mixed_t_u_follows_u_t_equivalence')}",
            f"- input transcoded U→T: {preflight.get('input_transcoded_u_to_t')}",
            f"- derived U→T corpus created: {preflight.get('derived_u_to_t_corpus_created')}",
            f"- preflight GO: {preflight.get('go')}",
            "",
            "Authoritative `sequence_core` values were clustered as frozen.",
            "S4 molecule/alphabet decisions were not reopened.",
            "",
            "## Sequence-level input",
            "",
            f"- scientific identities: {diagnostics.get('n_scientific_identities')}",
            f"- distinct sequence_core / clustering rows: {diagnostics.get('n_distinct_sequence_core')}",
            f"- unique sequence IDs: {diagnostics.get('sequence_id_unique')}",
            f"- missing sequence_core: {diagnostics.get('n_missing_sequence_core')}",
            f"- shared cores: {diagnostics.get('n_shared_sequence_cores')}",
            f"- identities on shared cores: {diagnostics.get('n_shared_core_identities')}",
            f"- extra identities from shared cores: {diagnostics.get('n_extra_identities_from_shared_cores')}",
            f"- identity length min/median/max: {diagnostics.get('identity_length_min')} / "
            f"{diagnostics.get('identity_length_median')} / {diagnostics.get('identity_length_max')}",
            f"- core length min/median/max: {diagnostics.get('core_length_min')} / "
            f"{diagnostics.get('core_length_median')} / {diagnostics.get('core_length_max')}",
            f"- identities outside 20–100 nt (reported, not filtered): "
            f"{diagnostics.get('n_identities_outside_20_100')}",
            f"- cores outside 20–100 nt (reported, not filtered): "
            f"{diagnostics.get('n_cores_outside_20_100')}",
            f"- identity alphabet: {alphabet_id}",
            f"- core alphabet: {alphabet_core}",
            f"- FASTA sort: {diagnostics.get('fasta_sort')}",
            "",
            "## Cluster results",
            "",
            f"- clusters: {diagnostics.get('n_clusters')}",
            f"- singleton clusters: {diagnostics.get('n_singleton_clusters')}",
            f"- multi-sequence clusters: {diagnostics.get('n_multi_sequence_clusters')}",
            f"- singleton fraction: {diagnostics.get('singleton_fraction')}",
            f"- largest cluster size: {diagnostics.get('largest_cluster_size')}",
            f"- unique cores before clustering: {diagnostics.get('n_unique_sequence_cores_before_clustering')}",
            f"- clusters after clustering: {diagnostics.get('n_clusters_after_clustering')}",
            f"- reduction due to near-sequence clustering: "
            f"{diagnostics.get('n_reduction_due_to_near_sequence_clustering')}",
            f"- clusters whose members are not all identical: "
            f"{diagnostics.get('n_clusters_whose_members_are_not_all_identical')}",
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
            "",
            "Length by cluster size (sequence-level):",
            f"- singleton clusters n/min/median/max: {singleton_len.get('n')} / "
            f"{singleton_len.get('min')} / {singleton_len.get('median')} / {singleton_len.get('max')}",
            f"- multi-sequence clusters n/min/median/max: {multi_len.get('n')} / "
            f"{multi_len.get('min')} / {multi_len.get('median')} / {multi_len.get('max')}",
            "",
            "Reduction is a clustering statistic, not balancing or downsampling.",
            "No scientific identity was removed.",
            "",
            "## Broadcast",
            "",
            f"- clustered corpus rows: {diagnostics.get('scientific_identities_retained')}",
            f"- unique scientific_identity_id: {multi.get('n_unique_scientific_identity_id')}",
            f"- missing cluster_id: {diagnostics.get('n_missing_cluster_id')}",
            f"- scientific representatives: {diagnostics.get('n_scientific_representatives')}",
            "",
            "## Multi-target preservation",
            "",
            f"- shared sequence cores: {multi.get('n_shared_sequence_cores')}",
            f"- scientific identities on those cores: {multi.get('n_shared_core_identities')}",
            f"- S4/S5A membership rows on those cores: {multi.get('n_shared_core_membership_rows')}",
            f"- shared cores consistent cluster ID: {multi.get('shared_cores_consistent_cluster_id')}",
            f"- clusters with several sequences and several targets: "
            f"{multi.get('n_clusters_with_several_sequences_and_several_targets')}",
            "",
            "Scientific identities were not merged within a cluster.",
            "",
            "## Identity/threshold audit",
            "",
            f"- definition: {identity_audit.get('definition')}",
            f"- non-singleton member rows inspected: {identity_audit.get('n_non_singleton_member_rows')}",
            f"- member-vs-representative below 0.90 under global Levenshtein: "
            f"{identity_audit.get('n_member_vs_rep_below_threshold_under_levenshtein')}",
            f"- MMseqs pairwise identity present in cluster.tsv: "
            f"{identity_audit.get('mmseqs_pairwise_identity_in_cluster_tsv')}",
            "MMseqs clusters were not rejected because a different identity",
            "definition differs.",
            "",
            "## ENA family diagnostics for S5D",
            "",
            "These are raw structural diagnostics. S5C does not decide whether",
            "recall is adequate and does not run the CD-HIT fallback.",
            "",
            f"- family IDs represented: {ena.get('n_ena_family_ids_represented')}",
            f"- declared multi-member families represented: "
            f"{ena.get('n_declared_multi_member_families_represented')}",
            f"- families with ≥2 S5 ENA members: "
            f"{ena.get('n_multi_member_families_with_at_least_two_s5_members')}",
            f"- of those, contained in one cluster: "
            f"{ena.get('n_multi_member_families_contained_in_one_cluster')}",
            f"- of those, split across >1 cluster: "
            f"{ena.get('n_multi_member_families_split_across_gt1_cluster')}",
            f"- singleton-source families: {ena.get('n_singleton_source_families')}",
            f"- singleton-source families sharing a cluster with another ENA family: "
            f"{ena.get('n_singleton_source_families_sharing_cluster_with_another_ena_family')}",
            f"- clusters containing multiple ENA families: "
            f"{ena.get('n_clusters_containing_multiple_ena_families')}",
            "",
            "16-family containment:",
            *family_lines,
            "",
            f"- adjudication: {ena.get('adjudication')}",
            "",
            "## Boundary",
            "",
            "- S4 unchanged",
            "- S5A freeze unchanged",
            "- exact-dedup policy unchanged",
            "- no scientific identities removed",
            "- no CD-HIT fallback",
            "- no balancing, target cap, FT/REF/EVAL, or train/validation split",
            "- no U→T derived corpus",
            "",
        ]
    )
    if SEQ_LEAK_RE.search(text or ""):
        raise S5SequenceClusteringError(
            "s5c_sequence_clustering_report.md must not contain biological sequences"
        )
    return text if text.endswith("\n") else text + "\n"

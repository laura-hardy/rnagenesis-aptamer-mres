"""S5D CD-HIT-est fallback clustering helpers.

Scientific command is the plan fallback ``cd-hit-est -c 0.9 -n 8``.
``-T 1`` and ``-d 0`` are execution-only (single-thread determinism and full
sequence-ID preservation in ``.clstr``). This module does not change the
identity threshold, add coverage flags, or overwrite the frozen MMseqs S5C
candidate.
"""

from __future__ import annotations

import hashlib
import math
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from adapters.s4_scientific_common import (
    ScientificProposalError,
    bool_token,
    fill_row,
)
from adapters.s5_exact_dedup import CORPUS_DEDUP_COLUMNS, _blank
from adapters.s5_sequence_clustering import (
    CLUSTER_SUMMARY_COLUMNS,
    SEQUENCE_FIELD,
    clustering_sort_key,
    make_sequence_id,
    project_unique_sequence_cores,
    render_fasta,
    sequence_core_digest,
    stable_cluster_id,
    structural_cluster_diagnostics,
    sequence_population_diagnostics,
    multi_target_preservation,
    expected_count_errors,
    build_cluster_summary,
    PREFLIGHT_FAR_ID,
    PREFLIGHT_MIXED_ID,
    PREFLIGHT_T_ID,
    PREFLIGHT_U_DUP_ID,
    PREFLIGHT_U_ID,
    PREFLIGHT_U_NEAR_ID,
    preflight_synthetic_sequences,
)

S5CdHitError = ScientificProposalError

AUTHORISED_CDHIT_PARAMETERS: dict[str, Any] = {
    "identity_threshold": 0.90,
    "word_size": 8,
    "sequence_field": SEQUENCE_FIELD,
}

FORBIDDEN_CDHIT_FLAGS: frozenset[str] = frozenset(
    {
        "-aS",
        "-aL",
        "-s",
        "-S",
        "-G",
        "-n",
        "-c",
        "balancing",
        "partition",
        "target_cap",
        "ft_ref_eval",
        "train_validation_split",
    }
)

CLUSTER_TSV_CDHIT_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "cdhit_representative_sequence_id",
    "member_sequence_id",
    "member_sequence_core_sha256",
    "sequence_length",
    "member_is_cdhit_representative",
)

CLUSTER_PROVENANCE_CDHIT_COLUMNS: tuple[str, ...] = (
    "sequence_id",
    "sequence_core_sha256",
    "cdhit_representative_sequence_id",
    "cdhit_representative_sequence_core_sha256",
    "is_cdhit_sequence_representative",
)

CORPUS_CLUSTERED_CDHIT_COLUMNS: tuple[str, ...] = (
    *CORPUS_DEDUP_COLUMNS,
    *CLUSTER_PROVENANCE_CDHIT_COLUMNS,
)

FINAL_CLUSTER_TSV_COLUMNS: tuple[str, ...] = (
    "cluster_id",
    "representative_sequence_id",
    "member_sequence_id",
    "member_sequence_core_sha256",
    "sequence_length",
    "member_is_sequence_representative",
)

CLSTR_MEMBER_RE = re.compile(
    r"^\s*\d+\s+(\d+)nt,\s*>(\S+?)\.\.\.\s+(\*|at\s+\S+)\s*$"
)
CLSTR_HEADER_RE = re.compile(r"^>Cluster\s+\d+\s*$")


def enforce_cdhit_parameters(config: Mapping[str, Any]) -> None:
    for key in ("identity_threshold", "word_size", "sequence_field"):
        if key not in config:
            raise S5CdHitError(f"S5D config missing required parameter {key}")
    identity = float(config["identity_threshold"])
    if not math.isclose(identity, 0.90, rel_tol=0.0, abs_tol=1e-12):
        raise S5CdHitError("S5D identity threshold is not the authorised 0.90")
    if int(config["word_size"]) != 8:
        raise S5CdHitError("S5D word size is not the authorised -n 8")
    if config["sequence_field"] != SEQUENCE_FIELD:
        raise S5CdHitError("S5D must cluster sequence_core")
    extra_flags = config.get("extra_cdhit_flags") or []
    for flag in extra_flags:
        token = str(flag).split()[0]
        if token in {"-aS", "-aL", "-s", "-S", "-G"} or token.startswith("-a"):
            raise S5CdHitError(
                f"S5D refuses unauthorised CD-HIT scientific flag {flag!r}"
            )
    forbidden = sorted(set(config) & FORBIDDEN_CDHIT_FLAGS)
    if forbidden:
        raise S5CdHitError(
            "S5D config contains forbidden scientific keys: " + ", ".join(forbidden)
        )


def comparison_nucleotides(sequence_core: str) -> str:
    """Characterwise U→T comparison representation. Does not alter sequence_core."""
    core = _blank(sequence_core)
    return core.replace("U", "T").replace("u", "t")


def build_comparison_fasta_rows(
    sequence_rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Build a comparison-only FASTA projection. Original cores are untouched."""
    projected: list[dict[str, str]] = []
    original_shas: list[str] = []
    comparison_shas: list[str] = []
    for row in sorted(sequence_rows, key=clustering_sort_key):
        core = _blank(row.get("sequence_core"))
        seq_id = _blank(row.get("sequence_id"))
        comparison = comparison_nucleotides(core)
        if len(comparison) != len(core):
            raise S5CdHitError("U→T comparison representation changed sequence length")
        if seq_id != make_sequence_id(core):
            raise S5CdHitError("comparison FASTA must keep original S5SEQ IDs")
        original_sha = sequence_core_digest(core)
        comparison_sha = hashlib.sha256(comparison.encode("utf-8")).hexdigest()
        original_shas.append(original_sha)
        comparison_shas.append(comparison_sha)
        projected.append(
            {
                "sequence_id": seq_id,
                "sequence_core": comparison,
                "sequence_core_sha256": original_sha,
                "original_sequence_core": core,
                "comparison_sequence_sha256": comparison_sha,
                "sequence_length": str(len(core)),
            }
        )
    if len({row["sequence_id"] for row in projected}) != len(projected):
        raise S5CdHitError("comparison FASTA sequence IDs are not one-to-one")
    diagnostics = {
        "n_sequences": len(projected),
        "length_preserved": True,
        "one_to_one_sequence_ids": True,
        "original_cores_unmodified": True,
        "original_sequence_sha256": hashlib.sha256(
            "".join(original_shas).encode("utf-8")
        ).hexdigest(),
        "comparison_sequence_sha256": hashlib.sha256(
            "".join(comparison_shas).encode("utf-8")
        ).hexdigest(),
        "representation": "nucleotide_comparison_U_to_T",
        "not_transcription_or_reclassification": True,
    }
    return projected, diagnostics


def parse_cdhit_clstr(
    text: str,
    *,
    input_sequence_ids: Sequence[str],
) -> list[tuple[str, str]]:
    """Parse CD-HIT ``.clstr`` into ``(representative, member)`` pairs."""
    expected = list(input_sequence_ids)
    expected_set = set(expected)
    if len(expected) != len(expected_set):
        raise S5CdHitError("input sequence IDs are not unique")
    pairs: list[tuple[str, str]] = []
    members_seen: list[str] = []
    current_rep = ""
    current_members: list[str] = []
    saw_cluster = False

    def _flush() -> None:
        nonlocal current_rep, current_members
        if not current_members:
            return
        if not current_rep:
            raise S5CdHitError("CD-HIT cluster is missing a representative marked *")
        if current_rep not in current_members:
            raise S5CdHitError(
                "CD-HIT representative is not a member of its own cluster"
            )
        for member in current_members:
            pairs.append((current_rep, member))
            members_seen.append(member)
        current_rep = ""
        current_members = []

    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if CLSTR_HEADER_RE.match(line):
            if saw_cluster:
                _flush()
            saw_cluster = True
            continue
        match = CLSTR_MEMBER_RE.match(line)
        if match is None:
            raise S5CdHitError(
                f"unrecognised CD-HIT .clstr line {line_number}"
            )
        seq_id = match.group(2)
        marker = match.group(3)
        if seq_id not in expected_set:
            raise S5CdHitError(f"unknown CD-HIT sequence ID {seq_id!r}")
        current_members.append(seq_id)
        if marker == "*":
            if current_rep:
                raise S5CdHitError(
                    f"CD-HIT cluster has multiple representatives near line {line_number}"
                )
            current_rep = seq_id
    if saw_cluster or current_members:
        _flush()

    member_counts = Counter(members_seen)
    duplicated = sorted(seq_id for seq_id, count in member_counts.items() if count > 1)
    if duplicated:
        raise S5CdHitError(
            "duplicate CD-HIT membership for sequence IDs: " + ", ".join(duplicated)
        )
    missing = [seq_id for seq_id in expected if seq_id not in member_counts]
    if missing:
        raise S5CdHitError(
            "CD-HIT output is missing input sequence IDs: " + ", ".join(missing)
        )
    extra = [seq_id for seq_id in member_counts if seq_id not in expected_set]
    if extra:
        raise S5CdHitError(
            "CD-HIT output contains unexpected sequence IDs: " + ", ".join(extra)
        )
    if len(members_seen) != len(expected):
        raise S5CdHitError("CD-HIT member count does not match input sequences")
    return pairs


def build_cdhit_cluster_rows(
    pairs: Sequence[tuple[str, str]],
    sequence_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    by_id = {_blank(row["sequence_id"]): row for row in sequence_rows}
    grouped: dict[str, list[str]] = defaultdict(list)
    rep_by_member: dict[str, str] = {}
    for representative, member in pairs:
        grouped[representative].append(member)
        if member in rep_by_member:
            raise S5CdHitError(f"sequence {member} assigned to multiple CD-HIT clusters")
        rep_by_member[member] = representative

    cluster_rows: list[dict[str, str]] = []
    for representative, members in grouped.items():
        unique_members = sorted(set(members))
        if representative not in unique_members:
            raise S5CdHitError(
                f"CD-HIT representative {representative} is not a member of its cluster"
            )
        digests = [by_id[member_id]["sequence_core_sha256"] for member_id in unique_members]
        cluster_id = stable_cluster_id(digests)
        for member_id in unique_members:
            member_row = by_id[member_id]
            cluster_rows.append(
                fill_row(
                    CLUSTER_TSV_CDHIT_COLUMNS,
                    {
                        "cluster_id": cluster_id,
                        "cdhit_representative_sequence_id": representative,
                        "member_sequence_id": member_id,
                        "member_sequence_core_sha256": member_row["sequence_core_sha256"],
                        "sequence_length": member_row["sequence_length"],
                        "member_is_cdhit_representative": bool_token(
                            member_id == representative
                        ),
                    },
                )
            )
    cluster_rows.sort(key=lambda row: (row["cluster_id"], row["member_sequence_id"]))
    by_member: dict[str, set[str]] = defaultdict(set)
    for row in cluster_rows:
        by_member[row["member_sequence_id"]].add(row["cluster_id"])
    multi = {member: clusters for member, clusters in by_member.items() if len(clusters) != 1}
    if multi:
        raise S5CdHitError(
            "sequence assigned to multiple clusters: " + ", ".join(sorted(multi))
        )
    return cluster_rows


def cdhit_membership_signature(
    cluster_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    members_by_cluster: dict[str, set[str]] = defaultdict(set)
    reps: dict[str, str] = {}
    for row in cluster_rows:
        cluster_id = row["cluster_id"]
        members_by_cluster[cluster_id].add(row["member_sequence_id"])
        if row["member_is_cdhit_representative"] == "true":
            reps[cluster_id] = row["cdhit_representative_sequence_id"]
    return {
        "cluster_ids": tuple(sorted(members_by_cluster)),
        "membership": {
            cluster_id: tuple(sorted(members))
            for cluster_id, members in sorted(members_by_cluster.items())
        },
        "cdhit_representatives": {cluster_id: reps[cluster_id] for cluster_id in sorted(reps)},
    }


def compare_cdhit_cluster_runs(
    first: Sequence[Mapping[str, str]],
    second: Sequence[Mapping[str, str]],
) -> None:
    sig_a = cdhit_membership_signature(first)
    sig_b = cdhit_membership_signature(second)
    if sig_a["membership"] != sig_b["membership"]:
        raise S5CdHitError("NO-GO: CD-HIT cluster membership differed across identical runs")
    if sig_a["cluster_ids"] != sig_b["cluster_ids"]:
        raise S5CdHitError(
            "NO-GO: stable cluster IDs differed despite claimed identical membership"
        )
    if sig_a["cdhit_representatives"] != sig_b["cdhit_representatives"]:
        raise S5CdHitError(
            "NO-GO: CD-HIT representative selection differed across identical runs"
        )
    if list(first) != list(second):
        raise S5CdHitError(
            "NO-GO: canonical clusters_cdhit.tsv rows are not byte-comparable across runs"
        )


def scientific_representatives_cdhit(
    clustered_identities: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    chosen: dict[str, str] = {}
    candidates: dict[str, list[str]] = defaultdict(list)
    rep_core: dict[str, str] = {}
    for row in clustered_identities:
        cluster_id = _blank(row.get("cluster_id"))
        if row.get("is_cdhit_sequence_representative") == "true":
            rep_core[cluster_id] = _blank(row.get("sequence_core"))
    for row in clustered_identities:
        cluster_id = _blank(row.get("cluster_id"))
        if _blank(row.get("sequence_core")) == rep_core.get(cluster_id):
            candidates[cluster_id].append(_blank(row.get("scientific_identity_id")))
    if sorted(rep_core) != sorted(candidates):
        raise S5CdHitError("no scientific identities found for CD-HIT representative cores")
    for cluster_id, identity_ids in candidates.items():
        if not identity_ids:
            raise S5CdHitError(f"cluster {cluster_id} has no scientific representative candidates")
        chosen[cluster_id] = min(identity_ids)
    return chosen


def broadcast_cdhit_clusters(
    corpus_rows: Sequence[Mapping[str, str]],
    sequence_rows: Sequence[Mapping[str, str]],
    cluster_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    seq_by_core = {_blank(row["sequence_core"]): row for row in sequence_rows}
    seq_by_id = {_blank(row["sequence_id"]): row for row in sequence_rows}
    cluster_by_member = {row["member_sequence_id"]: row for row in cluster_rows}
    if len(cluster_by_member) != len(cluster_rows):
        raise S5CdHitError("cluster membership is not unique by sequence")

    annotated: list[dict[str, str]] = []
    for row in corpus_rows:
        core = _blank(row.get("sequence_core"))
        seq_row = seq_by_core.get(core)
        if seq_row is None:
            raise S5CdHitError("scientific identity has no sequence-level clustering row")
        cluster_row = cluster_by_member[seq_row["sequence_id"]]
        rep_id = cluster_row["cdhit_representative_sequence_id"]
        rep_seq = seq_by_id[rep_id]
        if comparison_nucleotides(core) == core and core != seq_row["sequence_core"]:
            raise S5CdHitError("transformed comparison sequence leaked into clustered corpus")
        values = {column: _blank(row.get(column)) for column in CORPUS_DEDUP_COLUMNS}
        values["cluster_id"] = cluster_row["cluster_id"]
        values["is_cluster_representative"] = "false"
        values["sequence_id"] = seq_row["sequence_id"]
        values["sequence_core_sha256"] = seq_row["sequence_core_sha256"]
        values["cdhit_representative_sequence_id"] = rep_id
        values["cdhit_representative_sequence_core_sha256"] = rep_seq["sequence_core_sha256"]
        values["is_cdhit_sequence_representative"] = cluster_row[
            "member_is_cdhit_representative"
        ]
        identity = _blank(row.get("scientific_identity_id"))
        if not identity:
            raise S5CdHitError(
                "clustering must key on scientific_identity_id; it is missing"
            )
        annotated.append(fill_row(CORPUS_CLUSTERED_CDHIT_COLUMNS, values))
        if annotated[-1]["sequence_core"] != core:
            raise S5CdHitError("clustered corpus sequence_core drifted from the S5A freeze")

    chosen = scientific_representatives_cdhit(annotated)
    for row in annotated:
        row["is_cluster_representative"] = bool_token(
            row["scientific_identity_id"] == chosen.get(row["cluster_id"])
        )
    _assert_one_scientific_representative(annotated)
    _assert_shared_cores_share_cluster(annotated)
    _assert_no_comparison_leak(annotated, sequence_rows)
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
        raise S5CdHitError(f"{len(missing)} clusters lack a scientific representative")
    extra = {
        cluster_id: identities
        for cluster_id, identities in by_cluster.items()
        if len(identities) != 1
    }
    if extra:
        raise S5CdHitError(
            "clusters with !=1 scientific representative: " + ", ".join(sorted(extra))
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
        raise S5CdHitError("identical sequence_core values received different cluster IDs")


def _assert_no_comparison_leak(
    clustered_corpus: Sequence[Mapping[str, str]],
    sequence_rows: Sequence[Mapping[str, str]],
) -> None:
    original = {row["sequence_id"]: row["sequence_core"] for row in sequence_rows}
    for row in clustered_corpus:
        seq_id = _blank(row.get("sequence_id"))
        core = _blank(row.get("sequence_core"))
        if original.get(seq_id) != core:
            raise S5CdHitError(
                "transformed comparison sequence leaked into clustered corpus"
            )


def project_final_cluster_rows(
    cluster_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    projected: list[dict[str, str]] = []
    for row in cluster_rows:
        projected.append(
            fill_row(
                FINAL_CLUSTER_TSV_COLUMNS,
                {
                    "cluster_id": row["cluster_id"],
                    "representative_sequence_id": row["cdhit_representative_sequence_id"],
                    "member_sequence_id": row["member_sequence_id"],
                    "member_sequence_core_sha256": row["member_sequence_core_sha256"],
                    "sequence_length": row["sequence_length"],
                    "member_is_sequence_representative": row[
                        "member_is_cdhit_representative"
                    ],
                },
            )
        )
    return projected


def interpret_cdhit_rna_u_preflight(
    pairs: Sequence[tuple[str, str]],
) -> dict[str, Any]:
    member_to_rep = {member: representative for representative, member in pairs}
    u_cluster = {
        member_to_rep.get(PREFLIGHT_U_ID),
        member_to_rep.get(PREFLIGHT_U_DUP_ID),
    }
    identical_u_clustered = len(u_cluster) == 1 and None not in u_cluster
    near_with_u = member_to_rep.get(PREFLIGHT_U_NEAR_ID) == member_to_rep.get(PREFLIGHT_U_ID)
    t_with_u = member_to_rep.get(PREFLIGHT_T_ID) == member_to_rep.get(PREFLIGHT_U_ID)
    mixed_with_u = member_to_rep.get(PREFLIGHT_MIXED_ID) == member_to_rep.get(PREFLIGHT_U_ID)
    far_rep = member_to_rep.get(PREFLIGHT_FAR_ID)
    u_rep = member_to_rep.get(PREFLIGHT_U_ID)
    far_separate = far_rep is not None and u_rep is not None and far_rep != u_rep
    native_u_works = identical_u_clustered and near_with_u and far_separate
    return {
        "accepts_acgu_fasta": True,
        "identical_u_sequences_cluster": identical_u_clustered,
        "near_identical_u_sequences_cluster": near_with_u,
        "u_treated_as_valid_nucleotide": identical_u_clustered and near_with_u,
        "u_internally_equivalent_to_t": t_with_u,
        "mixed_t_u_follows_u_t_equivalence": mixed_with_u,
        "distant_sequence_not_clustered_with_u_pair": far_separate,
        "native_u_works": native_u_works,
        "input_transcoded_u_to_t": False,
        "derived_u_to_t_corpus_created": False,
        "go": native_u_works,
        "membership": {
            member: representative for representative, member in sorted(pairs)
        },
    }


def cdhit_command(
    *,
    fasta_path: Path,
    output_prefix: Path,
    cdhit_bin: str,
    identity_threshold: float = 0.9,
    word_size: int = 8,
    threads: int = 1,
    description_length: int = 0,
) -> list[str]:
    identity = "0.9" if math.isclose(identity_threshold, 0.9, abs_tol=1e-12) else str(identity_threshold)
    return [
        cdhit_bin,
        "-i",
        str(fasta_path),
        "-o",
        str(output_prefix),
        "-c",
        identity,
        "-n",
        str(int(word_size)),
        "-T",
        str(int(threads)),
        "-d",
        str(int(description_length)),
    ]


def run_cdhit_est(
    *,
    fasta_path: Path,
    output_prefix: Path,
    cdhit_bin: str = "cd-hit-est",
    identity_threshold: float = 0.9,
    word_size: int = 8,
    threads: int = 1,
    description_length: int = 0,
) -> dict[str, Any]:
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    command = cdhit_command(
        fasta_path=fasta_path,
        output_prefix=output_prefix,
        cdhit_bin=cdhit_bin,
        identity_threshold=identity_threshold,
        word_size=word_size,
        threads=threads,
        description_length=description_length,
    )
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    clstr_path = Path(str(output_prefix) + ".clstr")
    if completed.returncode != 0 or not clstr_path.is_file():
        raise S5CdHitError(
            "cd-hit-est failed: "
            + (completed.stderr or completed.stdout or f"exit {completed.returncode}")
        )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "output_fasta_path": Path(str(output_prefix)),
        "clstr_path": clstr_path,
        "clstr_text": clstr_path.read_text(encoding="utf-8"),
    }


def discover_cdhit_environment() -> dict[str, Any]:
    path = shutil.which("cd-hit-est") or ""
    version = ""
    identity_semantics = ""
    help_text = ""
    if path:
        completed = subprocess.run(
            [path, "-h"], check=False, capture_output=True, text=True
        )
        help_text = completed.stdout or completed.stderr or ""
        for line in help_text.splitlines():
            if "CD-HIT version" in line or "====== CD-HIT" in line:
                version = line.strip(" =")
                break
        if "number of identical amino acids or bases in alignment" in help_text:
            identity_semantics = (
                "global sequence identity = number of identical bases in "
                "alignment divided by the full length of the shorter sequence"
            )
    return {
        "cd_hit_est_path": path,
        "cd_hit_est_version": version,
        "cd_hit_est_installed": bool(path),
        "identity_semantics": identity_semantics,
        "help_excerpt": "\n".join(help_text.splitlines()[:40]),
    }


@dataclass
class CdHitClusteringResult:
    sequence_rows: list[dict[str, str]]
    cluster_rows: list[dict[str, str]]
    clustered_corpus: list[dict[str, str]]
    cluster_summary_rows: list[dict[str, str]]
    diagnostics: dict[str, Any] = field(default_factory=dict)


def assemble_cdhit_clustering(
    *,
    corpus_rows: Sequence[Mapping[str, str]],
    clstr_text: str,
    membership_rows: Sequence[Mapping[str, str]] | None = None,
    expected_counts: Mapping[str, Any] | None = None,
    used_comparison_fasta: bool = False,
) -> CdHitClusteringResult:
    sequence_rows, _identity_map = project_unique_sequence_cores(corpus_rows)
    pairs = parse_cdhit_clstr(
        clstr_text,
        input_sequence_ids=[row["sequence_id"] for row in sequence_rows],
    )
    cluster_rows = build_cdhit_cluster_rows(pairs, sequence_rows)
    clustered_corpus = broadcast_cdhit_clusters(corpus_rows, sequence_rows, cluster_rows)
    summary = build_cluster_summary(
        clustered_corpus,
        [
            {
                **row,
                "mmseqs_representative_sequence_id": row["cdhit_representative_sequence_id"],
                "member_is_mmseqs_representative": row["member_is_cdhit_representative"],
            }
            for row in cluster_rows
        ],
        sequence_rows,
        membership_rows or (),
    )
    population = sequence_population_diagnostics(corpus_rows, sequence_rows)
    structural = structural_cluster_diagnostics(
        clustered_corpus,
        [
            {
                **row,
                "mmseqs_representative_sequence_id": row["cdhit_representative_sequence_id"],
                "member_is_mmseqs_representative": row["member_is_cdhit_representative"],
            }
            for row in cluster_rows
        ],
        summary,
        sequence_rows,
        [],
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
    n_assigned = len({row["member_sequence_id"] for row in cluster_rows})
    mechanical = {
        "n_input_unique_cores": len(sequence_rows),
        "n_assigned_unique_cores": n_assigned,
        "all_cores_assigned_exactly_once": n_assigned == len(sequence_rows),
        "n_scientific_identities": len(clustered_corpus),
        "n_unique_scientific_identity_id": len(
            {_blank(row.get("scientific_identity_id")) for row in clustered_corpus}
        ),
        "n_missing_cluster_id": sum(
            1 for row in clustered_corpus if not _blank(row.get("cluster_id"))
        ),
        "used_comparison_fasta": used_comparison_fasta,
        "comparison_sequence_written_to_clustered_corpus": False,
    }
    diagnostics: dict[str, Any] = {
        **population,
        **structural,
        "multi_target": multi,
        **mechanical,
        "all_cores_assigned": mechanical["all_cores_assigned_exactly_once"],
        "cluster_id_convention": (
            "S5C_ + sha256 of sorted member sequence_core_sha256 values joined by U+001F"
        ),
        "representative_convention": (
            "preserve CD-HIT sequence representative; scientific identity "
            "representative is the lexicographically smallest "
            "scientific_identity_id among identities carrying that core"
        ),
    }
    if expected_counts:
        errors = expected_count_errors(diagnostics, expected_counts)
        if errors:
            raise S5CdHitError("S5D expected-count regression:\n" + "\n".join(errors))
    if diagnostics["n_scientific_identities"] != diagnostics["scientific_identities_retained"]:
        raise S5CdHitError("NO-GO: CD-HIT clustering removed scientific identities")
    if diagnostics["n_missing_cluster_id"] != 0:
        raise S5CdHitError("NO-GO: missing cluster_id after CD-HIT broadcast")
    return CdHitClusteringResult(
        sequence_rows=sequence_rows,
        cluster_rows=cluster_rows,
        clustered_corpus=clustered_corpus,
        cluster_summary_rows=summary,
        diagnostics=diagnostics,
    )


def representative_by_cluster_from_cdhit(
    cluster_rows: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in cluster_rows:
        if row["member_is_cdhit_representative"] == "true":
            mapping[row["cluster_id"]] = row["member_sequence_id"]
    return mapping


def representative_by_cluster_from_mmseqs(
    cluster_rows: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in cluster_rows:
        flag = row.get("member_is_mmseqs_representative") or row.get(
            "member_is_cdhit_representative"
        )
        if flag == "true":
            mapping[row["cluster_id"]] = row["member_sequence_id"]
    return mapping

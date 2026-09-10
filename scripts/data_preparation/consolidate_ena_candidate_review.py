#!/usr/bin/env python3
"""Consolidate ENA candidate outputs into clerical-review tables.

Stage 3 (after inspection + candidate processing). Does not replace prior
stages. Supports:

  build-review   — exact/near-duplicate consolidation + review templates
  apply-review   — validate and apply filled manual-review decisions
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ena_candidate_rules import (
    stable_group_id,
)
from ena_candidate_rules import _truthy  # noqa: E402 — shared helper
from ena_review_rules import (
    RNA_IDENTITY_PLAUSIBLE,
    assign_near_duplicate_families,
    classify_evidence_scope,
    is_protein_compatible_type,
    join_unique,
    recoverable_rna_sequence,
    repair_target,
    review_eligibility,
    short_sequence_family_context,
    strongest_binding_summary,
    strongest_evidence_scope,
    validate_manual_include,
)
from ena_review_rules import assess_sequence_quality  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE_DIRS = [
    REPO_ROOT / "data" / "raw" / "ENA" / "candidates",
    REPO_ROOT / "data" / "raw" / "ena" / "candidates",
]
DEFAULT_OUTPUT_DIRS = [
    REPO_ROOT / "data" / "raw" / "ENA" / "review",
    REPO_ROOT / "data" / "raw" / "ena" / "review",
]

REQUIRED_CANDIDATE_FILES = [
    "ena_candidate_records.csv",
    "ena_candidate_groups.csv",
    "ena_candidate_review_queue.csv",
]

logger = logging.getLogger("consolidate_ena_candidate_review")


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------


def configure_logging(log_path: Path, log_level: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str).fillna("")


def resolve_candidate_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    for cand in DEFAULT_CANDIDATE_DIRS:
        if cand.exists():
            return cand
    return DEFAULT_CANDIDATE_DIRS[0]


def resolve_output_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    for out in DEFAULT_OUTPUT_DIRS:
        # Prefer sibling of existing candidates
        parent_cand = out.parent / "candidates"
        if parent_cand.exists():
            return out
    return DEFAULT_OUTPUT_DIRS[0]


def load_candidate_tables(candidate_dir: Path) -> dict[str, pd.DataFrame]:
    missing = [f for f in REQUIRED_CANDIDATE_FILES if not (candidate_dir / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing candidate files in {candidate_dir}: {', '.join(missing)}"
        )
    tables = {name: _read_csv(candidate_dir / name) for name in REQUIRED_CANDIDATE_FILES}
    for optional in (
        "ena_candidate_exclusions.csv",
        "ena_candidate_evidence_long.csv",
        "ena_candidate_references.csv",
    ):
        path = candidate_dir / optional
        if path.exists():
            tables[optional] = _read_csv(path)
    return tables


def _write_csv(df: pd.DataFrame, path: Path, *, excel: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8-sig" if excel else "utf-8"
    df.to_csv(path, index=False, encoding=encoding)


def _pipe_unique(series: pd.Series) -> str:
    return join_unique(series.tolist(), sep=" | ")


def _median_int(values: list[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return int(round((s[mid - 1] + s[mid]) / 2))


# ---------------------------------------------------------------------------
# Annotation of accession-level working table
# ---------------------------------------------------------------------------


def build_working_accessions(
    records: pd.DataFrame,
    review_queue: pd.DataFrame,
) -> pd.DataFrame:
    """Annotate review-queue accessions (plus their experiment-group mates)."""
    queue_acc = set(review_queue["accession"].astype(str))
    queue_groups = set(
        review_queue.loc[review_queue["candidate_group"] != "", "candidate_group"].astype(str)
    )

    # Include all members of experiment groups that appear in the queue, so
    # group-level stats are complete; sequence review focuses on queue rows.
    in_scope = records["accession"].isin(queue_acc) | (
        records["candidate_experiment_group"].isin(queue_groups)
        & (records["candidate_experiment_group"] != "")
    )
    work = records.loc[in_scope].copy()
    work["in_review_queue"] = work["accession"].isin(queue_acc).map(lambda x: "1" if x else "0")

    repairs: list[dict[str, Any]] = []
    qualities: list[dict[str, Any]] = []
    scopes: list[str] = []

    for _, row in work.iterrows():
        context = " || ".join(
            [
                str(row.get("description", "")),
                str(row.get("reference_titles", "")),
                str(row.get("target_evidence_text", "")),
            ]
        )
        repair = repair_target(
            target_raw=str(row.get("target_raw", "")),
            target_type=str(row.get("target_type", "")),
            target_normalized=str(row.get("target_normalized", "")),
            context_text=context,
        )
        rna = recoverable_rna_sequence(
            str(row.get("sequence_rna_normalized", "")),
            str(row.get("sequence_deposited", "")),
        )
        quality = assess_sequence_quality(
            rna,
            description=str(row.get("description", "")),
            sequence_role=str(row.get("sequence_role", "")),
            contains_t7_flag=row.get("contains_t7_promoter_like_motif", False),
        )
        scope = classify_evidence_scope(
            binding_evidence_status=str(row.get("binding_evidence_status", "")),
            binding_evidence_types=str(row.get("binding_evidence_types", "")),
            binding_evidence_strength=str(row.get("binding_evidence_strength", "")),
            binding_evidence_text=str(row.get("binding_evidence_text", "")),
            selection_evidence=str(row.get("selection_evidence", "")),
            description=str(row.get("description", "")),
            reference_titles=str(row.get("reference_titles", "")),
            accession_count=1,
        )
        repairs.append(repair.to_row())
        qualities.append(quality.to_row())
        scopes.append(scope)

    repair_df = pd.DataFrame(repairs)
    quality_df = pd.DataFrame(qualities)
    work = work.reset_index(drop=True)
    work["target_proposed"] = repair_df["target_proposed"].astype(str)
    work["target_type_proposed"] = repair_df["target_type_proposed"].astype(str)
    work["target_region_proposed"] = repair_df["target_region_proposed"].astype(str)
    work["target_organism_or_context"] = repair_df["target_organism_or_context"].astype(str)
    work["target_key"] = repair_df["target_key"].astype(str)
    work["repair_action"] = repair_df["repair_action"].astype(str)
    work["repair_evidence_phrase"] = repair_df["evidence_phrase"].astype(str)
    work["repair_notes"] = repair_df["notes"].astype(str)
    work["repair_was_generic"] = repair_df["was_generic"].map(lambda x: "1" if x else "0")
    work["repair_type_changed"] = repair_df["type_changed"].map(lambda x: "1" if x else "0")
    work["repair_region_extracted"] = repair_df["region_extracted"].map(
        lambda x: "1" if x else "0"
    )
    work["repair_unresolved"] = repair_df["unresolved"].map(lambda x: "1" if x else "0")
    work["repair_candidate_names"] = repair_df["candidate_names"].astype(str)

    work["sequence_rna_review"] = quality_df["sequence_rna"].astype(str)
    work["sequence_length_review"] = quality_df["sequence_length"].astype(str)
    work["is_concrete"] = quality_df["is_concrete"].map(lambda x: "1" if x else "0")
    work["contains_ambiguous_bases"] = quality_df["contains_ambiguous_bases"].map(
        lambda x: "1" if x else "0"
    )
    work["ambiguous_base_count"] = quality_df["ambiguous_base_count"].astype(str)
    work["ambiguous_base_fraction"] = quality_df["ambiguous_base_fraction"].map(
        lambda x: f"{float(x):.4f}"
    )
    work["longest_ambiguous_run"] = quality_df["longest_ambiguous_run"].astype(str)
    work["ambiguity_symbols_present"] = quality_df["ambiguity_symbols_present"].astype(str)
    work["contains_t7_promoter"] = quality_df["contains_t7_promoter"].map(
        lambda x: "1" if x else "0"
    )
    work["sequence_quality_status"] = quality_df["sequence_quality_status"].astype(str)
    work["length_status"] = quality_df["length_status"].astype(str)
    work["evidence_scope_record"] = scopes

    return work


# ---------------------------------------------------------------------------
# Exact consolidation
# ---------------------------------------------------------------------------


def exact_review_key(rna_seq: str, target_key: str, is_concrete: bool) -> str:
    if not is_concrete or not rna_seq or not target_key:
        return ""
    return f"{rna_seq}||{target_key}"


def build_sequence_target_units(work: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Collapse exact RNA+target duplicates among review-queue accessions."""
    queue = work[work["in_review_queue"] == "1"].copy()

    # Map sequence → other targets (conflict detection across all queue rows)
    seq_to_targets: dict[str, set[str]] = defaultdict(set)
    seq_to_target_labels: dict[str, set[str]] = defaultdict(set)
    for _, row in queue.iterrows():
        seq = str(row["sequence_rna_review"])
        if not seq or row["is_concrete"] != "1":
            continue
        tk = str(row["target_key"])
        if tk:
            seq_to_targets[seq].add(tk)
            seq_to_target_labels[seq].add(str(row["target_proposed"]))

    units: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    target_repair_rows: list[dict[str, Any]] = []

    # Group by exact key when available; otherwise one unit per accession
    groups: dict[str, list[pd.Series]] = defaultdict(list)
    ungroupeable: list[pd.Series] = []
    for _, row in queue.iterrows():
        key = exact_review_key(
            str(row["sequence_rna_review"]),
            str(row["target_key"]),
            row["is_concrete"] == "1",
        )
        if key:
            groups[key].append(row)
        else:
            ungroupeable.append(row)

    def _emit_unit(rows: list[pd.Series], key: str) -> None:
        accessions = [str(r["accession"]) for r in rows]
        unit_id = stable_group_id("revu", key or "|".join(sorted(accessions)))
        seq = str(rows[0]["sequence_rna_review"])
        target_proposed = str(rows[0]["target_proposed"])
        # Prefer non-unknown proposed name if mixed
        for r in rows:
            if str(r["target_proposed"]) not in {"", "unknown"}:
                target_proposed = str(r["target_proposed"])
                break

        target_keys = {str(r["target_key"]) for r in rows if str(r["target_key"])}
        other_targets = sorted(
            seq_to_target_labels.get(seq, set()) - {target_proposed, ""}
        )
        # Also list other keys
        other_keys = sorted(seq_to_targets.get(seq, set()) - target_keys)
        conflict = "1" if (other_targets or len(seq_to_targets.get(seq, set())) > 1) else "0"

        row_dicts = [r.to_dict() for r in rows]
        for rd in row_dicts:
            rd["evidence_scope"] = rd.get("evidence_scope_record", "none")
        binding_summary, best_scope = strongest_binding_summary(row_dicts)
        # Recompute scope with consolidated accession count (do not upgrade)
        family_scope = classify_evidence_scope(
            binding_evidence_status=join_unique(r.get("binding_evidence_status", "") for r in rows),
            binding_evidence_types=join_unique(r.get("binding_evidence_types", "") for r in rows),
            binding_evidence_strength=join_unique(r.get("binding_evidence_strength", "") for r in rows),
            binding_evidence_text=join_unique(r.get("binding_evidence_text", "") for r in rows),
            selection_evidence=join_unique(r.get("selection_evidence", "") for r in rows),
            description=join_unique(r.get("description", "") for r in rows),
            reference_titles=join_unique(r.get("reference_titles", "") for r in rows),
            accession_count=len(rows),
        )
        # Never upgrade individual → keep min of family-aware and per-record best
        # If per-record said individual but consolidation shows patent family, prefer family
        if best_scope.startswith("individual") and family_scope in {
            "patent_claim_level",
            "experiment_or_family_level",
        }:
            evidence_scope = family_scope
        else:
            evidence_scope = strongest_evidence_scope([best_scope, family_scope])

        exp_groups = [str(r.get("candidate_experiment_group", "")) for r in rows]
        exp_group = next((g for g in exp_groups if g), "")

        concerns = []
        if conflict == "1":
            concerns.append("target_conflict")
        if any(str(r["contains_ambiguous_bases"]) == "1" for r in rows):
            concerns.append("ambiguous_bases")
        if any(str(r["contains_t7_promoter"]) == "1" for r in rows):
            concerns.append("t7_promoter")
        if any(str(r["sequence_quality_status"]) == "degenerate_library_template" for r in rows):
            concerns.append("library_template")
        if str(rows[0]["length_status"]) in {
            "under_15_high_concern",
            "15_to_19_short_review",
        }:
            concerns.append("short_sequence")
        if str(rows[0]["length_status"]) in {
            "201_to_500_likely_construct",
            "over_500_construct_or_non_aptamer",
        }:
            concerns.append("long_construct")
        if any(_truthy(r.get("sequence_target_conflict")) for r in rows):
            concerns.append("existing_sequence_target_conflict_flag")

        existing_matches = join_unique(
            f"{r.get('matched_existing_source', '')}:{r.get('matched_existing_target', '')}"
            for r in rows
            if str(r.get("matched_existing_sequence", "")).strip()
        )

        # Priority: protein + concrete + binding > others
        priority = "medium"
        if is_protein_compatible_type(str(rows[0]["target_type_proposed"])) and rows[0]["is_concrete"] == "1":
            if evidence_scope.startswith("individual"):
                priority = "high"
            elif evidence_scope in {"experiment_or_family_level", "patent_claim_level"}:
                priority = "high"
            else:
                priority = "medium"
        if "library_template" in concerns or "long_construct" in concerns:
            priority = "low"

        deposited_examples = join_unique(r.get("sequence_deposited", "") for r in rows)
        unit = {
            "review_unit_id": unit_id,
            "experiment_group_id": exp_group,
            "rna_sequence": seq,
            "deposited_sequence_examples": deposited_examples[:2000],
            "sequence_length": str(rows[0]["sequence_length_review"]),
            "target_proposed": target_proposed,
            "target_type_proposed": str(rows[0]["target_type_proposed"]),
            "target_region_proposed": join_unique(r.get("target_region_proposed", "") for r in rows),
            "target_key": str(rows[0]["target_key"]),
            "accession_count": str(len(rows)),
            "accessions": "|".join(sorted(accessions)),
            "exact_sequence_group": join_unique(r.get("exact_sequence_group", "") for r in rows),
            "near_duplicate_family_id": "",
            "near_duplicate_family_size": "",
            "sequence_variant_relationships": "",
            "descriptions": join_unique(r.get("description", "") for r in rows),
            "references": join_unique(r.get("reference_titles", "") for r in rows),
            "doi_values": join_unique(r.get("doi_values", "") for r in rows),
            "pubmed_values": join_unique(r.get("pubmed_values", "") for r in rows),
            "rna_identity_statuses": join_unique(r.get("rna_identity_status", "") for r in rows),
            "sequence_role_statuses": join_unique(r.get("sequence_role", "") for r in rows),
            "binding_evidence_summary": binding_summary,
            "binding_evidence_level": join_unique(
                r.get("binding_evidence_strength", "") for r in rows
            ),
            "selection_evidence_summary": join_unique(
                r.get("selection_evidence", "") for r in rows
            ),
            "evidence_scope": evidence_scope,
            "contains_t7_promoter": "1" if any(str(r["contains_t7_promoter"]) == "1" for r in rows) else "0",
            "contains_ambiguous_bases": str(rows[0]["contains_ambiguous_bases"]),
            "ambiguous_base_count": str(rows[0]["ambiguous_base_count"]),
            "ambiguous_base_fraction": str(rows[0]["ambiguous_base_fraction"]),
            "longest_ambiguous_run": str(rows[0]["longest_ambiguous_run"]),
            "ambiguity_symbols_present": str(rows[0].get("ambiguity_symbols_present", "")),
            "sequence_quality_status": str(rows[0]["sequence_quality_status"]),
            "length_status": str(rows[0]["length_status"]),
            "same_sequence_other_targets": " | ".join(other_targets),
            "target_conflict_flag": conflict,
            "existing_dataset_matches": existing_matches,
            "review_priority": priority,
            "automatic_concern_flags": ";".join(concerns),
            "manual_include": "",
            "manual_target_corrected": "",
            "manual_sequence_corrected": "",
            "manual_exclusion_reason": "",
            "manual_notes": "",
            "allow_ambiguous_include": "",
            "is_concrete": str(rows[0]["is_concrete"]),
            "in_main_template": "",
            "eligibility_bucket": "",
        }
        units.append(unit)

        for r in rows:
            provenance.append(
                {
                    "review_unit_id": unit_id,
                    "accession": str(r["accession"]),
                    "experiment_group_id": str(r.get("candidate_experiment_group", "")),
                    "sequence_deposited": str(r.get("sequence_deposited", "")),
                    "sequence_rna_normalized": str(r.get("sequence_rna_review", "")),
                    "target_raw": str(r.get("target_raw", "")),
                    "target_type_raw": str(r.get("target_type", "")),
                    "description": str(r.get("description", "")),
                    "reference": str(r.get("reference_titles", "")),
                    "binding_evidence": (
                        f"{r.get('binding_evidence_strength', '')}:"
                        f"{r.get('binding_evidence_types', '')}"
                    ),
                    "selection_evidence": str(r.get("selection_evidence", "")),
                    "sequence_role": str(r.get("sequence_role", "")),
                    "source_candidate_tier": str(r.get("candidate_tier", "")),
                    "source_warnings": str(r.get("parse_warnings", "")),
                }
            )

        for r in rows:
            needs_repair_review = (
                _truthy(r.get("repair_type_changed"))
                or _truthy(r.get("repair_region_extracted"))
                or _truthy(r.get("repair_was_generic"))
                or _truthy(r.get("repair_unresolved"))
                or bool(str(r.get("repair_candidate_names", "")).count("|"))
                or conflict == "1"
            )
            if needs_repair_review:
                target_repair_rows.append(
                    {
                        "accession": str(r["accession"]),
                        "review_unit_id": unit_id,
                        "target_raw": str(r.get("target_raw", "")),
                        "target_type_raw": str(r.get("target_type", "")),
                        "target_normalized_raw": str(r.get("target_normalized", "")),
                        "target_proposed": str(r.get("target_proposed", "")),
                        "target_type_proposed": str(r.get("target_type_proposed", "")),
                        "target_region_proposed": str(r.get("target_region_proposed", "")),
                        "target_organism_or_context": str(r.get("target_organism_or_context", "")),
                        "repair_action": str(r.get("repair_action", "")),
                        "evidence_phrase": str(r.get("repair_evidence_phrase", "")),
                        "repair_notes": str(r.get("repair_notes", "")),
                        "type_changed": str(r.get("repair_type_changed", "")),
                        "was_generic": str(r.get("repair_was_generic", "")),
                        "region_extracted": str(r.get("repair_region_extracted", "")),
                        "unresolved": str(r.get("repair_unresolved", "")),
                        "candidate_names": str(r.get("repair_candidate_names", "")),
                        "target_conflict_flag": conflict,
                        "same_sequence_other_targets": " | ".join(other_targets),
                        "description": str(r.get("description", ""))[:500],
                    }
                )

    for key, rows in groups.items():
        _emit_unit(rows, key)
    for row in ungroupeable:
        _emit_unit([row], "")

    units_df = pd.DataFrame(units)
    prov_df = pd.DataFrame(provenance)
    repair_df = pd.DataFrame(target_repair_rows).drop_duplicates()
    return units_df, prov_df, repair_df


def attach_near_duplicates(units_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if units_df.empty:
        return units_df, pd.DataFrame()

    unit_list = units_df.to_dict(orient="records")
    # Use display target for family summary; clustering uses target_key
    unit_to_family, family_summaries, unit_rels = assign_near_duplicate_families(unit_list)

    fam_sizes = Counter(unit_to_family.values())
    out = units_df.copy()
    out["near_duplicate_family_id"] = out["review_unit_id"].map(
        lambda i: unit_to_family.get(str(i), "")
    )
    out["near_duplicate_family_size"] = out["near_duplicate_family_id"].map(
        lambda f: str(fam_sizes[f]) if f else ""
    )
    out["sequence_variant_relationships"] = out["review_unit_id"].map(
        lambda i: " | ".join(unit_rels.get(str(i), []))
    )

    # Fill target_proposed display name into family summaries
    id_to_target = dict(zip(out["review_unit_id"], out["target_proposed"]))
    fam_rows = []
    for fam_id, summary in family_summaries.items():
        member_ids = summary["review_unit_ids"].split("|")
        display_target = id_to_target.get(member_ids[0], summary.get("target_proposed", ""))
        # Prefer any non-empty proposed from members
        for mid in member_ids:
            t = id_to_target.get(mid, "")
            if t and t != "unknown":
                display_target = t
                break
        summary = dict(summary)
        summary["target_proposed"] = display_target
        fam_rows.append(summary)

    fam_df = pd.DataFrame(fam_rows)
    return out, fam_df


# ---------------------------------------------------------------------------
# Experiment-group review
# ---------------------------------------------------------------------------


def build_experiment_group_review(
    work: pd.DataFrame,
    units_df: pd.DataFrame,
    fam_df: pd.DataFrame,
    groups_table: pd.DataFrame,
) -> pd.DataFrame:
    """One row per candidate experiment / patent family present in scope."""
    # Groups that appear in queue
    queue = work[work["in_review_queue"] == "1"]
    group_ids = sorted(
        {
            g
            for g in queue["candidate_experiment_group"].tolist()
            if str(g).strip()
        }
    )

    # Also include ungrouped queue accessions as singleton pseudo-groups? Spec
    # says experiment_group_id — only real groups.
    rows = []
    fam_by_group = defaultdict(set)
    if not fam_df.empty and "experiment_group_id" in fam_df.columns:
        for _, fr in fam_df.iterrows():
            fam_by_group[str(fr["experiment_group_id"])].add(str(fr["family_id"]))

    units_by_group = defaultdict(list)
    if not units_df.empty:
        for _, ur in units_df.iterrows():
            units_by_group[str(ur["experiment_group_id"])].append(ur)

    group_meta = {}
    if not groups_table.empty:
        exp = groups_table[groups_table["group_type"] == "candidate_experiment"]
        for _, gr in exp.iterrows():
            group_meta[str(gr["group_id"])] = gr

    for gid in group_ids:
        members = work[work["candidate_experiment_group"] == gid]
        if members.empty:
            continue
        accessions = sorted(members["accession"].astype(str).tolist())
        lengths = [
            int(x)
            for x in members["sequence_length_review"].tolist()
            if str(x).isdigit() and int(x) > 0
        ]
        deposited_seqs = members["sequence_deposited"].astype(str)
        rna_seqs = members["sequence_rna_review"].astype(str)
        concrete = members[members["is_concrete"] == "1"]
        seq_target_keys = {
            exact_review_key(str(r["sequence_rna_review"]), str(r["target_key"]), True)
            for _, r in concrete.iterrows()
            if exact_review_key(str(r["sequence_rna_review"]), str(r["target_key"]), True)
        }

        tier_counts = members["candidate_tier"].value_counts().to_dict()
        tier_str = ";".join(f"{k}:{v}" for k, v in sorted(tier_counts.items()))

        # Exact duplicate count: deposited sequences appearing >=2
        dep_counts = deposited_seqs[deposited_seqs != ""].value_counts()
        exact_dup_count = int((dep_counts >= 2).sum())

        unit_rows = units_by_group.get(gid, [])
        binding_summaries = [str(u.get("binding_evidence_summary", "")) for u in unit_rows]
        scopes = [str(u.get("evidence_scope", "")) for u in unit_rows]
        if not scopes:
            scopes = members["evidence_scope_record"].tolist()

        meta = group_meta.get(gid)
        rep = str(meta["representative_accession"]) if meta is not None else accessions[0]
        common_desc = (
            str(meta["common_description"])
            if meta is not None
            else join_unique(members["description"].tolist())[:500]
        )
        common_ref = (
            str(meta["common_reference"])
            if meta is not None
            else join_unique(members["reference_titles"].tolist())[:500]
        )

        concerns = []
        if int((members["sequence_quality_status"] == "degenerate_library_template").sum()) > 0:
            concerns.append("contains_library_templates")
        if int((members["length_status"] == "under_15_high_concern").sum()) > 0:
            concerns.append("contains_very_short_sequences")
        if int((members["contains_t7_promoter"] == "1").sum()) > 0:
            concerns.append("contains_t7_promoter")
        if members["target_type_proposed"].nunique() > 3:
            concerns.append("heterogeneous_targets")
        if (
            "repair_was_generic" in members.columns
            and any(str(x) == "1" for x in members["repair_was_generic"].tolist())
        ):
            concerns.append("generic_targets_present")

        # Recommended action — advisory only; do not pre-fill manual_group_include
        if is_protein_compatible_type(
            Counter(members["target_type_proposed"]).most_common(1)[0][0]
        ) and int((members["is_concrete"] == "1").sum()) > 0:
            recommended = "inspect_sequence_level"
        else:
            recommended = "likely_low_priority_or_exclude"

        # Dominant proposed target
        tgt_counts = (
            members.loc[members["target_proposed"] != "", "target_proposed"]
            .value_counts()
        )
        target_proposed = tgt_counts.index[0] if len(tgt_counts) else ""
        ttype_counts = members["target_type_proposed"].value_counts()
        target_type_proposed = ttype_counts.index[0] if len(ttype_counts) else ""
        region = join_unique(members["target_region_proposed"].tolist())

        rows.append(
            {
                "experiment_group_id": gid,
                "representative_accession": rep,
                "member_accession_count": str(len(members)),
                "unique_deposited_sequence_count": str(deposited_seqs[deposited_seqs != ""].nunique()),
                "unique_rna_sequence_count": str(rna_seqs[rna_seqs != ""].nunique()),
                "unique_sequence_target_count": str(len(seq_target_keys)),
                "accessions": "|".join(accessions),
                "common_description": common_desc,
                "all_descriptions": join_unique(members["description"].tolist()),
                "common_reference": common_ref,
                "all_references": join_unique(members["reference_titles"].tolist()),
                "doi_values": join_unique(members["doi_values"].tolist()),
                "pubmed_values": join_unique(members["pubmed_values"].tolist()),
                "target_raw_values": join_unique(members["target_raw"].tolist()),
                "target_proposed": target_proposed,
                "target_type_proposed": target_type_proposed,
                "target_region_proposed": region,
                "rna_identity_summary": join_unique(members["rna_identity_status"].tolist()),
                "binding_evidence_summary": join_unique(binding_summaries)[:1000]
                or join_unique(
                    f"{s}:{t}"
                    for s, t in zip(
                        members["binding_evidence_strength"],
                        members["binding_evidence_types"],
                    )
                )[:1000],
                "binding_evidence_level": join_unique(
                    members["binding_evidence_strength"].tolist()
                ),
                "selection_evidence_summary": join_unique(
                    members["selection_evidence"].tolist()
                ),
                "sequence_length_min": str(min(lengths) if lengths else ""),
                "sequence_length_median": str(_median_int(lengths) if lengths else ""),
                "sequence_length_max": str(max(lengths) if lengths else ""),
                "concrete_sequence_count": str(int((members["is_concrete"] == "1").sum())),
                "ambiguous_sequence_count": str(
                    int((members["contains_ambiguous_bases"] == "1").sum())
                ),
                "library_template_count": str(
                    int(
                        (members["sequence_quality_status"] == "degenerate_library_template").sum()
                    )
                ),
                "short_sequence_count": str(
                    int(
                        members["length_status"].isin(
                            ["under_15_high_concern", "15_to_19_short_review"]
                        ).sum()
                    )
                ),
                "long_construct_count": str(
                    int(
                        members["length_status"].isin(
                            [
                                "201_to_500_likely_construct",
                                "over_500_construct_or_non_aptamer",
                            ]
                        ).sum()
                    )
                ),
                "t7_promoter_count": str(int((members["contains_t7_promoter"] == "1").sum())),
                "exact_duplicate_count": str(exact_dup_count),
                "near_duplicate_family_count": str(len(fam_by_group.get(gid, set()))),
                "current_tier_counts": tier_str,
                "group_concerns": ";".join(concerns),
                "recommended_group_action": recommended,
                "manual_group_include": "",
                "manual_target_corrected": "",
                "manual_target_type_corrected": "",
                "manual_group_notes": "",
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Special review files + template
# ---------------------------------------------------------------------------


def build_ambiguous_library_file(units_df: pd.DataFrame) -> pd.DataFrame:
    if units_df.empty:
        return pd.DataFrame()
    mask = units_df["sequence_quality_status"] == "degenerate_library_template"
    cols = [
        "review_unit_id",
        "experiment_group_id",
        "rna_sequence",
        "sequence_length",
        "target_proposed",
        "target_type_proposed",
        "accession_count",
        "accessions",
        "ambiguous_base_count",
        "ambiguous_base_fraction",
        "longest_ambiguous_run",
        "ambiguity_symbols_present",
        "descriptions",
        "sequence_quality_status",
        "binding_evidence_summary",
        "evidence_scope",
        "automatic_concern_flags",
    ]
    cols = [c for c in cols if c in units_df.columns]
    return units_df.loc[mask, cols].copy()


def build_short_sequence_review(
    units_df: pd.DataFrame,
    fam_df: pd.DataFrame,
) -> pd.DataFrame:
    if units_df.empty:
        return pd.DataFrame()
    short = units_df[
        units_df["length_status"].isin(["under_15_high_concern", "15_to_19_short_review"])
    ].copy()
    if short.empty:
        return short

    fam_seqs: dict[str, list[str]] = defaultdict(list)
    if not fam_df.empty:
        id_to_seq = dict(zip(units_df["review_unit_id"], units_df["rna_sequence"]))
        for _, fr in fam_df.iterrows():
            for uid in str(fr["review_unit_ids"]).split("|"):
                fam_seqs[str(fr["family_id"])].append(id_to_seq.get(uid, ""))

    rows = []
    for _, row in short.iterrows():
        fam_id = str(row.get("near_duplicate_family_id", ""))
        family_sequences = fam_seqs.get(fam_id, [])
        if not family_sequences:
            # Fall back to same experiment group + target
            sibs = units_df[
                (units_df["experiment_group_id"] == row["experiment_group_id"])
                & (units_df["target_key"] == row.get("target_key", ""))
            ]["rna_sequence"].tolist()
            family_sequences = [str(s) for s in sibs]
        ctx = short_sequence_family_context(
            str(row["rna_sequence"]),
            family_sequences,
            description=str(row.get("descriptions", "")),
        )
        rows.append(
            {
                **{k: row.get(k, "") for k in [
                    "review_unit_id",
                    "experiment_group_id",
                    "rna_sequence",
                    "sequence_length",
                    "length_status",
                    "target_proposed",
                    "target_type_proposed",
                    "accession_count",
                    "accessions",
                    "near_duplicate_family_id",
                    "near_duplicate_family_size",
                    "descriptions",
                    "contains_ambiguous_bases",
                    "sequence_quality_status",
                    "binding_evidence_summary",
                    "evidence_scope",
                    "automatic_concern_flags",
                ]},
                **ctx,
            }
        )
    return pd.DataFrame(rows)


def mark_eligibility(units_df: pd.DataFrame) -> pd.DataFrame:
    out = units_df.copy()
    in_main = []
    buckets = []
    for _, row in out.iterrows():
        # RNA identity: accept if any status is plausible
        statuses = [s.strip() for s in str(row.get("rna_identity_statuses", "")).split("|")]
        rna_ok_status = next(
            (s for s in statuses if s in RNA_IDENTITY_PLAUSIBLE),
            statuses[0] if statuses else "",
        )
        ok, bucket = review_eligibility(
            rna_identity_status=rna_ok_status,
            target_type_proposed=str(row.get("target_type_proposed", "")),
            sequence_quality_status=str(row.get("sequence_quality_status", "")),
            length_status=str(row.get("length_status", "")),
            evidence_scope=str(row.get("evidence_scope", "")),
            binding_evidence_summary=str(row.get("binding_evidence_summary", "")),
            selection_evidence_summary=str(row.get("selection_evidence_summary", "")),
            descriptions=str(row.get("descriptions", "")),
        )
        # Short sequences with otherwise plausible evidence stay eligible
        if (
            not ok
            and bucket.startswith("sequence_quality")
            and str(row.get("length_status")) in {
                "under_15_high_concern",
                "15_to_19_short_review",
            }
        ):
            ok2, bucket2 = review_eligibility(
                rna_identity_status=rna_ok_status,
                target_type_proposed=str(row.get("target_type_proposed", "")),
                sequence_quality_status="concrete_candidate_sequence",
                length_status="20_to_120_typical_range",
                evidence_scope=str(row.get("evidence_scope", "")),
                binding_evidence_summary=str(row.get("binding_evidence_summary", "")),
                selection_evidence_summary=str(row.get("selection_evidence_summary", "")),
                descriptions=str(row.get("descriptions", "")),
            )
            if ok2:
                ok, bucket = True, ""
        in_main.append("1" if ok else "0")
        buckets.append(bucket)
    out["in_main_template"] = in_main
    out["eligibility_bucket"] = buckets
    return out


def build_manual_review_template(units_df: pd.DataFrame) -> pd.DataFrame:
    main = units_df[units_df["in_main_template"] == "1"].copy()
    if main.empty:
        return pd.DataFrame()

    main["_len"] = pd.to_numeric(main["sequence_length"], errors="coerce").fillna(0)
    main = main.sort_values(
        by=[
            "experiment_group_id",
            "target_proposed",
            "near_duplicate_family_id",
            "_len",
            "rna_sequence",
        ]
    )
    template = pd.DataFrame(
        {
            "manual_include": "",
            "manual_target_corrected": "",
            "manual_sequence_corrected": "",
            "manual_exclusion_reason": "",
            "manual_notes": "",
            "allow_ambiguous_include": "",
            "review_unit_id": main["review_unit_id"],
            "experiment_group_id": main["experiment_group_id"],
            "target_proposed": main["target_proposed"],
            "target_region_proposed": main["target_region_proposed"],
            "target_type_proposed": main["target_type_proposed"],
            "rna_sequence": main["rna_sequence"],
            "sequence_length": main["sequence_length"],
            "sequence_quality_status": main["sequence_quality_status"],
            "length_status": main["length_status"],
            "near_duplicate_family_id": main["near_duplicate_family_id"],
            "near_duplicate_family_size": main["near_duplicate_family_size"],
            "accession_count": main["accession_count"],
            "accessions": main["accessions"],
            "aptamer_or_patent_description": main["descriptions"],
            "binding_evidence_summary": main["binding_evidence_summary"],
            "evidence_scope": main["evidence_scope"],
            "selection_evidence_summary": main["selection_evidence_summary"],
            "references": main["references"],
            "automatic_concern_flags": main["automatic_concern_flags"],
            "review_priority": main["review_priority"],
            "contains_ambiguous_bases": main["contains_ambiguous_bases"],
            "same_sequence_other_targets": main["same_sequence_other_targets"],
            "target_conflict_flag": main["target_conflict_flag"],
        }
    )
    return template


# ---------------------------------------------------------------------------
# QC report
# ---------------------------------------------------------------------------


def write_qc_report(
    path: Path,
    *,
    accession_rows_before: int,
    units_df: pd.DataFrame,
    group_df: pd.DataFrame,
    fam_df: pd.DataFrame,
    repair_df: pd.DataFrame,
    template_df: pd.DataFrame,
    ambiguous_df: pd.DataFrame,
    short_df: pd.DataFrame,
    work: pd.DataFrame,
) -> None:
    queue = work[work["in_review_queue"] == "1"]
    concrete = queue[queue["is_concrete"] == "1"]
    unique_seqs = concrete["sequence_rna_review"].nunique()
    unique_keys = {
        exact_review_key(str(r["sequence_rna_review"]), str(r["target_key"]), True)
        for _, r in concrete.iterrows()
        if exact_review_key(str(r["sequence_rna_review"]), str(r["target_key"]), True)
    }

    length_counts = Counter(units_df["length_status"].tolist()) if not units_df.empty else Counter()
    under_15 = length_counts.get("under_15_high_concern", 0)
    mid_short = length_counts.get("15_to_19_short_review", 0)
    typical = length_counts.get("20_to_120_typical_range", 0)
    over_200 = (
        length_counts.get("201_to_500_likely_construct", 0)
        + length_counts.get("over_500_construct_or_non_aptamer", 0)
    )

    type_changed = int(repair_df["type_changed"].map(_truthy).sum()) if not repair_df.empty and "type_changed" in repair_df else 0
    generic = int(repair_df["was_generic"].map(_truthy).sum()) if not repair_df.empty and "was_generic" in repair_df else 0
    region = int(repair_df["region_extracted"].map(_truthy).sum()) if not repair_df.empty and "region_extracted" in repair_df else 0
    conflicts = (
        int((units_df["target_conflict_flag"] == "1").sum()) if not units_df.empty else 0
    )
    amb_rows = (
        int((units_df["contains_ambiguous_bases"] == "1").sum()) if not units_df.empty else 0
    )

    reduction = accession_rows_before - len(template_df)
    reduction_pct = (
        100.0 * reduction / accession_rows_before if accession_rows_before else 0.0
    )

    lines = [
        "# ENA review consolidation QC report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "This report summarises **clerical consolidation** of provisional ENA",
        "candidate outputs. Manual inclusion decisions are not pre-filled.",
        "",
        "## Consolidation burden",
        "",
        "| metric | count |",
        "|---|---:|",
        f"| original accession-level review rows | {accession_rows_before} |",
        f"| unique exact RNA sequences (queue, concrete) | {unique_seqs} |",
        f"| unique exact sequence–target units (keys) | {len(unique_keys)} |",
        f"| experiment groups in group review | {len(group_df)} |",
        f"| rows after exact consolidation | {len(units_df)} |",
        f"| near-duplicate families | {len(fam_df)} |",
        f"| main manual-review template rows | {len(template_df)} |",
        f"| group-review rows | {len(group_df)} |",
        f"| reduction vs accession rows (template) | {reduction} ({reduction_pct:.1f}%) |",
        "",
        "## Sequence quality",
        "",
        "| metric | count |",
        "|---|---:|",
        f"| rows with ambiguity symbols | {amb_rows} |",
        f"| classified as library templates | {len(ambiguous_df)} |",
        f"| under 15 nt | {under_15} |",
        f"| 15–19 nt | {mid_short} |",
        f"| 20–120 nt | {typical} |",
        f"| over 200 nt | {over_200} |",
        f"| short-sequence review rows | {len(short_df)} |",
        "",
        "## Target repair",
        "",
        "| metric | count |",
        "|---|---:|",
        f"| target-repair review rows | {len(repair_df)} |",
        f"| target type changes | {type_changed} |",
        f"| generic targets → unknown | {generic} |",
        f"| region/domain extractions | {region} |",
        f"| sequence–target conflicts | {conflicts} |",
        "",
        "## Largest experiment groups",
        "",
    ]

    if group_df.empty:
        lines.append("_None._")
    else:
        g2 = group_df.copy()
        g2["_n"] = pd.to_numeric(g2["member_accession_count"], errors="coerce").fillna(0)
        g2 = g2.sort_values("_n", ascending=False).head(15)
        lines += [
            "| members | group_id | target_proposed | concerns |",
            "|---:|---|---|---|",
        ]
        for _, r in g2.iterrows():
            lines.append(
                f"| {r['member_accession_count']} | {r['experiment_group_id']} | "
                f"{str(r['target_proposed'])[:40]} | {str(r['group_concerns'])[:60]} |"
            )

    lines += ["", "## Largest near-duplicate families", ""]
    if fam_df.empty:
        lines.append("_None._")
    else:
        f2 = fam_df.copy()
        f2["_n"] = pd.to_numeric(f2["member_count"], errors="coerce").fillna(0)
        f2 = f2.sort_values("_n", ascending=False).head(15)
        lines += [
            "| members | family_id | target | relationships |",
            "|---:|---|---|---|",
        ]
        for _, r in f2.iterrows():
            lines.append(
                f"| {r['member_count']} | {r['family_id']} | "
                f"{str(r['target_proposed'])[:40]} | {str(r['relationship_summary'])[:50]} |"
            )

    lines += [
        "",
        "## Limitations",
        "",
        "- Near-duplicate grouping is restricted to experiment group + target.",
        "- Family-level patent binding claims are not upgraded to individual evidence.",
        "- Ambiguous bases are never silently removed.",
        "- Manual inclusion columns are left blank for human review.",
        "- Short sequences are flagged, not auto-rejected.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------


def run_build_review(
    candidate_dir: Path,
    output_dir: Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = [
        "ena_experiment_group_review.csv",
        "ena_sequence_target_review.csv",
        "ena_sequence_family_summary.csv",
        "ena_target_repair_review.csv",
        "ena_ambiguous_library_sequences.csv",
        "ena_short_sequence_review.csv",
        "ena_sequence_target_provenance.csv",
        "ena_review_qc_report.md",
        "ena_manual_review_template.csv",
    ]
    existing = [f for f in outputs if (output_dir / f).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"Output files exist in {output_dir}; pass --overwrite to replace: "
            f"{', '.join(existing[:5])}"
        )

    tables = load_candidate_tables(candidate_dir)
    records = tables["ena_candidate_records.csv"]
    groups = tables["ena_candidate_groups.csv"]
    queue = tables["ena_candidate_review_queue.csv"]
    accession_rows_before = len(queue)

    logger.info("Loaded %d records, %d review-queue rows", len(records), len(queue))
    work = build_working_accessions(records, queue)
    logger.info("Working accession rows (queue + group mates): %d", len(work))

    units_df, prov_df, repair_df = build_sequence_target_units(work)
    logger.info("Exact-consolidated review units: %d", len(units_df))
    units_df, fam_df = attach_near_duplicates(units_df)
    logger.info("Near-duplicate families: %d", len(fam_df))

    units_df = mark_eligibility(units_df)
    group_df = build_experiment_group_review(work, units_df, fam_df, groups)
    ambiguous_df = build_ambiguous_library_file(units_df)
    short_df = build_short_sequence_review(units_df, fam_df)
    template_df = build_manual_review_template(units_df)

    # Drop helper columns from published sequence-target review
    publish_cols = [
        c
        for c in [
            "review_unit_id",
            "experiment_group_id",
            "rna_sequence",
            "deposited_sequence_examples",
            "sequence_length",
            "target_proposed",
            "target_type_proposed",
            "target_region_proposed",
            "accession_count",
            "accessions",
            "exact_sequence_group",
            "near_duplicate_family_id",
            "near_duplicate_family_size",
            "sequence_variant_relationships",
            "descriptions",
            "references",
            "doi_values",
            "pubmed_values",
            "rna_identity_statuses",
            "sequence_role_statuses",
            "binding_evidence_summary",
            "binding_evidence_level",
            "selection_evidence_summary",
            "evidence_scope",
            "contains_t7_promoter",
            "contains_ambiguous_bases",
            "ambiguous_base_count",
            "ambiguous_base_fraction",
            "longest_ambiguous_run",
            "sequence_quality_status",
            "length_status",
            "same_sequence_other_targets",
            "target_conflict_flag",
            "existing_dataset_matches",
            "review_priority",
            "automatic_concern_flags",
            "manual_include",
            "manual_target_corrected",
            "manual_sequence_corrected",
            "manual_exclusion_reason",
            "manual_notes",
        ]
        if c in units_df.columns
    ]
    seq_review = units_df[publish_cols].copy()

    _write_csv(group_df, output_dir / "ena_experiment_group_review.csv")
    _write_csv(seq_review, output_dir / "ena_sequence_target_review.csv")
    _write_csv(fam_df, output_dir / "ena_sequence_family_summary.csv")
    _write_csv(repair_df, output_dir / "ena_target_repair_review.csv")
    _write_csv(ambiguous_df, output_dir / "ena_ambiguous_library_sequences.csv")
    _write_csv(short_df, output_dir / "ena_short_sequence_review.csv")
    _write_csv(prov_df, output_dir / "ena_sequence_target_provenance.csv")
    _write_csv(template_df, output_dir / "ena_manual_review_template.csv", excel=True)

    # Empty selected/rejected placeholders (filled by apply-review)
    empty_selected = pd.DataFrame(
        columns=[
            "sequence",
            "target",
            "target_region",
            "target_type",
            "review_unit_id",
            "experiment_group_id",
            "accessions",
            "references",
            "binding_evidence",
            "evidence_scope",
            "selection_evidence",
            "sequence_length",
            "near_duplicate_family_id",
            "manual_notes",
            "source_database",
            "provenance",
        ]
    )
    empty_rejected = pd.DataFrame(
        columns=list(template_df.columns) + ["rejection_stage"]
        if not template_df.empty
        else ["review_unit_id", "manual_include", "manual_exclusion_reason", "rejection_stage"]
    )
    if not (output_dir / "ena_selected_after_manual_review.csv").exists() or overwrite:
        _write_csv(empty_selected, output_dir / "ena_selected_after_manual_review.csv")
    if not (output_dir / "ena_rejected_after_manual_review.csv").exists() or overwrite:
        _write_csv(empty_rejected, output_dir / "ena_rejected_after_manual_review.csv")

    write_qc_report(
        output_dir / "ena_review_qc_report.md",
        accession_rows_before=accession_rows_before,
        units_df=units_df,
        group_df=group_df,
        fam_df=fam_df,
        repair_df=repair_df,
        template_df=template_df,
        ambiguous_df=ambiguous_df,
        short_df=short_df,
        work=work,
    )

    stats = {
        "accession_rows_before": accession_rows_before,
        "review_units": len(units_df),
        "experiment_groups": len(group_df),
        "near_duplicate_families": len(fam_df),
        "target_repair_rows": len(repair_df),
        "library_templates": len(ambiguous_df),
        "short_sequences": len(short_df),
        "manual_template_rows": len(template_df),
    }
    logger.info("Build-review complete: %s", stats)
    return stats


# ---------------------------------------------------------------------------
# Apply review
# ---------------------------------------------------------------------------


class ReviewValidationError(Exception):
    def __init__(self, failures: list[str]):
        self.failures = failures
        super().__init__(
            f"{len(failures)} validation failure(s):\n" + "\n".join(f"  - {f}" for f in failures)
        )


def apply_manual_review(
    review_file: Path,
    output_dir: Path,
) -> dict[str, Any]:
    df = pd.read_csv(review_file, dtype=str).fillna("")
    failures: list[str] = []

    if "review_unit_id" not in df.columns or "manual_include" not in df.columns:
        raise ReviewValidationError(
            ["review file must contain review_unit_id and manual_include columns"]
        )

    # Unique review_unit_id
    dup_ids = df["review_unit_id"][df["review_unit_id"].duplicated(keep=False)]
    for uid in sorted(set(dup_ids.tolist())):
        if uid:
            failures.append(f"duplicate review_unit_id: {uid}")

    # Validate manual_include values
    normalised = []
    for idx, val in enumerate(df["manual_include"].tolist()):
        norm = validate_manual_include(val)
        if norm is None:
            failures.append(
                f"row {idx}: manual_include must be blank, 0, or 1 (got {val!r})"
            )
            normalised.append("")
        else:
            normalised.append(norm)
    df = df.copy()
    df["manual_include"] = normalised

    included = df[df["manual_include"] == "1"]
    rejected = df[df["manual_include"] == "0"]
    unreviewed = df[df["manual_include"] == ""]

    # Ambiguity check for included rows
    amb_re = __import__("re").compile(r"[NRYSWKMBDHV]", __import__("re").IGNORECASE)

    for idx, row in included.iterrows():
        uid = str(row.get("review_unit_id", ""))
        seq = str(row.get("manual_sequence_corrected") or row.get("rna_sequence") or "").strip()
        target = str(row.get("manual_target_corrected") or row.get("target_proposed") or "").strip()
        if not seq:
            failures.append(f"{uid}: included row missing RNA sequence")
        if not target or target.lower() == "unknown":
            failures.append(f"{uid}: included row missing corrected/proposed target")
        if seq and amb_re.search(seq):
            override = str(row.get("allow_ambiguous_include", "")).strip()
            if override not in {"1", "true", "TRUE", "yes"}:
                failures.append(
                    f"{uid}: included sequence contains ambiguity symbols; "
                    "set allow_ambiguous_include=1 to override"
                )

    if failures:
        raise ReviewValidationError(failures)

    selected_rows = []
    for _, row in included.iterrows():
        seq = str(row.get("manual_sequence_corrected") or row.get("rna_sequence") or "").strip()
        target = str(row.get("manual_target_corrected") or row.get("target_proposed") or "").strip()
        selected_rows.append(
            {
                "sequence": seq,
                "target": target,
                "target_region": str(row.get("target_region_proposed", "")),
                "target_type": str(row.get("target_type_proposed", "")),
                "review_unit_id": str(row.get("review_unit_id", "")),
                "experiment_group_id": str(row.get("experiment_group_id", "")),
                "accessions": str(row.get("accessions", "")),
                "references": str(row.get("references", "")),
                "binding_evidence": str(row.get("binding_evidence_summary", "")),
                "evidence_scope": str(row.get("evidence_scope", "")),
                "selection_evidence": str(row.get("selection_evidence_summary", "")),
                "sequence_length": str(len(seq)),
                "near_duplicate_family_id": str(row.get("near_duplicate_family_id", "")),
                "manual_notes": str(row.get("manual_notes", "")),
                "source_database": "ENA",
                "provenance": (
                    f"ENA review_unit_id={row.get('review_unit_id', '')}; "
                    f"accessions={row.get('accessions', '')}"
                ),
            }
        )

    rejected_out = rejected.copy()
    rejected_out["rejection_stage"] = "manual_review"

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(pd.DataFrame(selected_rows), output_dir / "ena_selected_after_manual_review.csv")
    _write_csv(rejected_out, output_dir / "ena_rejected_after_manual_review.csv")

    summary = {
        "included": len(included),
        "rejected": len(rejected),
        "unreviewed": len(unreviewed),
    }
    logger.info(
        "Applied review: included=%d rejected=%d unreviewed=%d",
        summary["included"],
        summary["rejected"],
        summary["unreviewed"],
    )
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Consolidate ENA candidates into clerical-review tables."
    )
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build-review", help="Build consolidation and review templates")
    b.add_argument("--candidate-dir", type=Path, default=None)
    b.add_argument("--output-dir", type=Path, default=None)
    b.add_argument("--overwrite", action="store_true")
    b.add_argument("--log-level", default="INFO")

    a = sub.add_parser("apply-review", help="Apply filled manual-review decisions")
    a.add_argument(
        "--review-file",
        type=Path,
        required=True,
        help="Path to filled ena_manual_review_template.csv",
    )
    a.add_argument("--output-dir", type=Path, default=None)
    a.add_argument("--log-level", default="INFO")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "ena_review_processing_log.txt"
    configure_logging(log_path, args.log_level)

    try:
        if args.command == "build-review":
            candidate_dir = resolve_candidate_dir(args.candidate_dir)
            run_build_review(
                candidate_dir=candidate_dir,
                output_dir=output_dir,
                overwrite=args.overwrite,
            )
        elif args.command == "apply-review":
            apply_manual_review(
                review_file=args.review_file,
                output_dir=output_dir,
            )
        else:
            logger.error("Unknown command: %s", args.command)
            return 2
    except ReviewValidationError as exc:
        logger.error("%s", exc)
        return 1
    except Exception:
        logger.exception("ENA review consolidation failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

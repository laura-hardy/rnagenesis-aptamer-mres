#!/usr/bin/env python3
"""ENA review v2: repair targets/evidence, then group-first clerical review.

Stage 4 corrective layer. Does not overwrite ``data/raw/ena/review/``.

Commands:
  build-review           — repair + compact group-review template (+ provenance)
  apply-group-review     — apply group 0/1 decisions → sequence-level template
  apply-sequence-review  — apply sequence 0/1 decisions → accepted/rejected exports
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from ena_candidate_rules import stable_group_id
from ena_review_rules import (
    IUPAC_ALL,
    IUPAC_AMBIGUITY,
    RNA_IDENTITY_PLAUSIBLE,
    assess_sequence_quality,
    assign_near_duplicate_families,
    is_generic_target_phrase,
    join_unique,
    recoverable_rna_sequence,
    validate_manual_include,
)
from ena_review_v2_rules import (
    TARGET_ALIASES,
    classify_conflict_type,
    conflict_is_biological,
    is_protein_compatible_v2,
    is_retention_recommendation,
    normalize_target_comparison_key,
    preferred_display_name,
    propose_promoter_trim,
    recommend_group_action,
    repair_binding_evidence_v2,
    repair_target_v2,
    strongest_evidence_scope_v2,
    validate_manual_group_include,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVIEW_DIRS = [
    REPO_ROOT / "data" / "raw" / "ena" / "review",
    REPO_ROOT / "data" / "raw" / "ENA" / "review",
]
DEFAULT_CANDIDATE_DIRS = [
    REPO_ROOT / "data" / "raw" / "ena" / "candidates",
    REPO_ROOT / "data" / "raw" / "ENA" / "candidates",
]
DEFAULT_OUTPUT_DIRS = [
    REPO_ROOT / "data" / "raw" / "ena" / "review_v2",
    REPO_ROOT / "data" / "raw" / "ENA" / "review_v2",
]

logger = logging.getLogger("refine_ena_manual_review")


class ReviewValidationError(ValueError):
    pass


# ---------------------------------------------------------------------------
# IO helpers
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


def _write_csv(df: pd.DataFrame, path: Path, *, excel: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8-sig" if excel else "utf-8"
    if df.empty and len(df.columns) == 0:
        path.write_text("", encoding=encoding)
        return
    df.to_csv(path, index=False, encoding=encoding)


def _median_int(values: list[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return int(round((s[mid - 1] + s[mid]) / 2))


def resolve_dir(explicit: Path | None, defaults: list[Path]) -> Path:
    if explicit is not None:
        return explicit
    for d in defaults:
        if d.exists():
            return d
    return defaults[0]


# ---------------------------------------------------------------------------
# Load stage-3 + candidate inputs
# ---------------------------------------------------------------------------


def load_inputs(
    review_dir: Path,
    candidate_dir: Path | None,
) -> dict[str, pd.DataFrame]:
    required = [
        "ena_sequence_target_review.csv",
        "ena_sequence_target_provenance.csv",
        "ena_experiment_group_review.csv",
    ]
    missing = [f for f in required if not (review_dir / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing stage-3 review files in {review_dir}: {', '.join(missing)}"
        )
    tables = {name: _read_csv(review_dir / name) for name in required}
    if candidate_dir and (candidate_dir / "ena_candidate_records.csv").exists():
        tables["ena_candidate_records.csv"] = _read_csv(
            candidate_dir / "ena_candidate_records.csv"
        )
    return tables


def _candidate_lookup(tables: dict[str, pd.DataFrame]) -> dict[str, dict[str, Any]]:
    if "ena_candidate_records.csv" not in tables:
        return {}
    rec = tables["ena_candidate_records.csv"]
    out: dict[str, dict[str, Any]] = {}
    for _, row in rec.iterrows():
        out[str(row.get("accession", ""))] = row.to_dict()
    return out


# ---------------------------------------------------------------------------
# Accession-level repair
# ---------------------------------------------------------------------------


def build_repaired_accessions(
    provenance: pd.DataFrame,
    units: pd.DataFrame,
    candidates: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """One row per provenance accession with v2 target + evidence repairs."""
    unit_by_id = {
        str(r["review_unit_id"]): r.to_dict()
        for _, r in units.iterrows()
    }
    rows: list[dict[str, Any]] = []
    for _, prow in provenance.iterrows():
        acc = str(prow.get("accession", ""))
        uid = str(prow.get("review_unit_id", ""))
        unit = unit_by_id.get(uid, {})
        cand = candidates.get(acc, {})

        target_raw = str(prow.get("target_raw", "") or unit.get("target_proposed", ""))
        prior_type = str(
            prow.get("target_type_raw", "")
            or unit.get("target_type_proposed", "")
            or cand.get("target_type", "")
        )
        description = str(
            prow.get("description", "")
            or unit.get("descriptions", "")
            or cand.get("description", "")
        )
        reference = str(
            prow.get("reference", "")
            or unit.get("references", "")
            or cand.get("reference_titles", "")
        )
        context = " || ".join(filter(None, [description, reference, str(cand.get("target_evidence_text", ""))]))

        repair = repair_target_v2(target_raw, target_type=prior_type, context_text=context)

        rna = recoverable_rna_sequence(
            str(prow.get("sequence_rna_normalized", "") or unit.get("rna_sequence", "")),
            str(prow.get("sequence_deposited", "") or cand.get("sequence_deposited", "")),
        )
        quality = assess_sequence_quality(
            rna,
            description=description,
            sequence_role=str(prow.get("sequence_role", "") or cand.get("sequence_role", "")),
            contains_t7_flag=cand.get("contains_t7_promoter_like_motif", False),
        )
        trim = propose_promoter_trim(rna)

        # Parse prior binding fields from provenance "strength:types" blob
        be_blob = str(prow.get("binding_evidence", "") or "")
        be_strength = ""
        be_types = ""
        if ":" in be_blob:
            parts = be_blob.split(":", 1)
            be_strength, be_types = parts[0], parts[1]
        else:
            be_types = be_blob
        be_strength = be_strength or str(unit.get("binding_evidence_level", "") or cand.get("binding_evidence_strength", ""))
        be_text = str(cand.get("binding_evidence_text", "") or description)
        prior_scope = str(unit.get("evidence_scope", "") or "")

        evidence = repair_binding_evidence_v2(
            description=description,
            reference_titles=reference,
            binding_evidence_status=str(cand.get("binding_evidence_status", "")),
            binding_evidence_types=be_types or str(cand.get("binding_evidence_types", "")),
            binding_evidence_strength=be_strength or str(cand.get("binding_evidence_strength", "")),
            binding_evidence_text=be_text,
            selection_evidence=str(prow.get("selection_evidence", "") or cand.get("selection_evidence", "")),
            feature_notes=str(cand.get("feature_notes", "")),
            prior_scope=prior_scope,
            accession_count=1,
        )

        rows.append(
            {
                "accession": acc,
                "review_unit_id_v1": uid,
                "experiment_group_id": str(
                    prow.get("experiment_group_id", "")
                    or unit.get("experiment_group_id", "")
                    or cand.get("candidate_experiment_group", "")
                ),
                "sequence_deposited": str(prow.get("sequence_deposited", "") or cand.get("sequence_deposited", "")),
                "rna_sequence": quality.sequence_rna,
                "sequence_length": str(quality.sequence_length),
                "is_concrete": "1" if quality.is_concrete else "0",
                "contains_ambiguous_bases": "1" if quality.contains_ambiguous_bases else "0",
                "ambiguous_base_count": str(quality.ambiguous_base_count),
                "longest_ambiguous_run": str(quality.longest_ambiguous_run),
                "ambiguity_symbols": quality.ambiguity_symbols_present,
                "sequence_quality_status": quality.sequence_quality_status,
                "length_status": quality.length_status,
                "contains_t7_promoter": "1" if quality.contains_t7_promoter else "0",
                "possible_post_promoter_sequence": trim.possible_post_promoter_sequence,
                "post_promoter_sequence_length": str(trim.post_promoter_sequence_length),
                "promoter_trim_status": trim.promoter_trim_status,
                "description": description,
                "reference": reference,
                "rna_identity_status": str(
                    cand.get("rna_identity_status", "")
                    or (str(unit.get("rna_identity_statuses", "")).split("|")[0] if unit.get("rna_identity_statuses") else "")
                ),
                "sequence_role": str(prow.get("sequence_role", "") or cand.get("sequence_role", "")),
                "selection_evidence": str(prow.get("selection_evidence", "") or cand.get("selection_evidence", "")),
                "source_candidate_tier": str(prow.get("source_candidate_tier", "") or cand.get("candidate_tier", "")),
                "doi_values": str(cand.get("doi_values", "") or unit.get("doi_values", "")),
                "pubmed_values": str(cand.get("pubmed_values", "") or unit.get("pubmed_values", "")),
                "publication_or_patent_identifier": _extract_pub_id(description, reference),
                # Target v2
                "target_raw": repair.target_raw,
                "target_name": repair.target_name,
                "target_display_name": repair.target_display_name,
                "target_comparison_key": repair.target_comparison_key,
                "target_region": repair.target_region,
                "target_context": repair.target_context,
                "target_type": repair.target_type,
                "target_repair_reason": repair.target_repair_reason,
                "target_confidence": repair.target_confidence,
                "target_type_prior": repair.prior_type,
                "target_type_changed": "1" if repair.type_changed else "0",
                "target_alias_applied": "1" if repair.alias_applied else "0",
                "target_was_generic": "1" if repair.was_generic else "0",
                "target_unresolved": "1" if repair.unresolved else "0",
                "target_notes": repair.notes,
                # Evidence v2
                "binding_evidence_strength": evidence.binding_evidence_strength,
                "binding_evidence_type": evidence.binding_evidence_type,
                "evidence_scope": evidence.evidence_scope,
                "binding_evidence_text": evidence.binding_evidence_text,
                "evidence_prior_scope": evidence.prior_scope,
                "evidence_repair_reason": evidence.repair_reason,
                "evidence_upgraded_from_none": "1" if evidence.upgraded_from_none else "0",
                "evidence_downgraded_from_individual": "1" if evidence.downgraded_from_individual else "0",
            }
        )
    return pd.DataFrame(rows)


def _extract_pub_id(description: str, reference: str) -> str:
    text = f"{description} {reference}"
    m = re_search_pub(text)
    return m or ""


def re_search_pub(text: str) -> str:
    import re

    m = re.search(
        r"\b((?:WO|US|EP|KR|JP|CN)\s*\d[\d/\-A-Za-z]*)",
        text or "",
        flags=re.IGNORECASE,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    m = re.search(r"\b(PMID[:\s]?\d+)\b", text or "", flags=re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


# ---------------------------------------------------------------------------
# Exact sequence + target consolidation (including ambiguous)
# ---------------------------------------------------------------------------


def consolidate_sequence_target_units(acc_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Collapse exact RNA string + comparison key; retain all provenance."""
    # Sequence → set of (key, region, display)
    seq_targets: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for _, row in acc_df.iterrows():
        seq = str(row["rna_sequence"])
        if not seq:
            continue
        seq_targets[seq].add(
            (
                str(row["target_comparison_key"]),
                str(row["target_region"]),
                str(row["target_display_name"]),
            )
        )

    groups: dict[str, list[pd.Series]] = defaultdict(list)
    for _, row in acc_df.iterrows():
        seq = str(row["rna_sequence"])
        key = str(row["target_comparison_key"])
        if not seq or not key:
            # Still emit singleton units so provenance is not lost
            uid_key = f"singleton|{row['accession']}"
            groups[uid_key].append(row)
            continue
        groups[f"{seq}||{key}"].append(row)

    units: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    conflict_rows: list[dict[str, Any]] = []

    for gkey, rows in groups.items():
        accessions = sorted({str(r["accession"]) for r in rows})
        unit_id = stable_group_id("rev2", gkey)
        seq = str(rows[0]["rna_sequence"])
        # Prefer best display name
        display = ""
        for r in rows:
            d = str(r["target_display_name"])
            if d and d.lower() != "unknown":
                display = d
                break
        if not display:
            display = str(rows[0]["target_display_name"])

        cmp_key = str(rows[0]["target_comparison_key"])
        region = join_unique(r.get("target_region", "") for r in rows)
        ttype = Counter(str(r["target_type"]) for r in rows).most_common(1)[0][0]

        other = seq_targets.get(seq, set())
        conflict_type = classify_conflict_type(sorted(other)) if other else "no_conflict"
        # If only this key present → no conflict
        other_keys = {k for k, _, _ in other}
        if len(other_keys) <= 1 and conflict_type == "orthographic_alias_only":
            # Single comparison key with display variants only within alias set
            conflict_type = "no_conflict"

        # Recompute with all labels for this sequence
        if len(other_keys) > 1:
            conflict_type = classify_conflict_type(sorted(other))
        elif any(k in {"UNKNOWN", "COMPOUND"} for k in other_keys) and len(other) > 1:
            conflict_type = classify_conflict_type(sorted(other))

        other_labels = sorted(
            {
                n
                for k, _, n in other
                if n and normalize_target_comparison_key(n) != cmp_key and k != cmp_key
            }
        )

        scopes = [str(r["evidence_scope"]) for r in rows]
        evidence_scope = strongest_evidence_scope_v2(scopes)
        # Prefer non-individual if any patent claim present among family
        if any(s == "patent_claim_level" for s in scopes) and evidence_scope.startswith("individual"):
            evidence_scope = "patent_claim_level"
        # Pick representative evidence type/strength matching scope
        ev_type = str(rows[0]["binding_evidence_type"])
        ev_strength = str(rows[0]["binding_evidence_strength"])
        for r in rows:
            if str(r["evidence_scope"]) == evidence_scope:
                ev_type = str(r["binding_evidence_type"])
                ev_strength = str(r["binding_evidence_strength"])
                break

        exp_groups = sorted(
            {str(r["experiment_group_id"]) for r in rows if str(r.get("experiment_group_id", "")).strip()}
        )
        exp_group = exp_groups[0] if exp_groups else ""
        title = join_unique(r.get("description", "") for r in rows)
        # Compact representative title: first description only
        rep_title = next((str(r["description"]) for r in rows if str(r["description"]).strip()), "")

        concerns = []
        if conflict_is_biological(conflict_type):
            concerns.append(f"conflict:{conflict_type}")
        if any(str(r.get("contains_ambiguous_bases", "")) == "1" for r in rows):
            concerns.append("ambiguous_bases")
        if any(str(r["sequence_quality_status"]) == "degenerate_library_template" for r in rows):
            concerns.append("library_template")
        if any(str(r.get("contains_t7_promoter", "")) == "1" for r in rows):
            concerns.append("t7_promoter")
        if str(rows[0].get("length_status", "")) in {"under_15_high_concern", "15_to_19_short_review"}:
            concerns.append("short_sequence")
        if any(str(r.get("unresolved_target", "")) == "1" for r in rows):
            concerns.append("unresolved_target")
        if any(str(r.get("manual_target_applied", "")) == "1" for r in rows):
            concerns.append("group_manual_target_applied")
        if any(str(r.get("manual_target_type_applied", "")) == "1" for r in rows):
            concerns.append("group_manual_type_applied")

        trim_status = join_unique(r.get("promoter_trim_status", "") for r in rows)
        post_seq = next(
            (str(r.get("possible_post_promoter_sequence", "")) for r in rows if str(r.get("possible_post_promoter_sequence", ""))),
            "",
        )

        unit = {
            "review_unit_id": unit_id,
            "experiment_group_id": exp_group,
            "experiment_group_ids": "|".join(exp_groups),
            "rna_sequence": seq,
            "sequence_length": str(rows[0].get("sequence_length", len(seq))),
            "sequence_quality_status": str(rows[0]["sequence_quality_status"]),
            "length_status": str(rows[0].get("length_status", "")),
            "is_concrete": str(rows[0].get("is_concrete", "0")),
            "contains_ambiguous_bases": str(rows[0].get("contains_ambiguous_bases", "0")),
            "ambiguous_base_count": str(rows[0].get("ambiguous_base_count", "0")),
            "longest_ambiguous_run": str(rows[0].get("longest_ambiguous_run", "0")),
            "ambiguity_symbols": str(rows[0].get("ambiguity_symbols", "")),
            "target_raw_variants": join_unique(r.get("target_raw", "") for r in rows),
            "target_name": str(rows[0].get("target_name", "")) or display,
            "target_display_name": display,
            "target_comparison_key": cmp_key,
            "target_region": region,
            "target_context": join_unique(r.get("target_context", "") for r in rows),
            "target_type": ttype,
            "target_repair_reason": join_unique(r.get("target_repair_reason", "") for r in rows),
            "target_confidence": Counter(
                str(r.get("target_confidence", "moderate") or "moderate") for r in rows
            ).most_common(1)[0][0],
            "unresolved_target": "1" if any(str(r.get("unresolved_target", "")) == "1" for r in rows) else "0",
            "manual_target_applied": "1" if any(str(r.get("manual_target_applied", "")) == "1" for r in rows) else "0",
            "manual_target_type_applied": "1" if any(str(r.get("manual_target_type_applied", "")) == "1" for r in rows) else "0",
            "accession_count": str(len(accessions)),
            "accessions": "|".join(accessions),
            "binding_evidence_type": ev_type,
            "binding_evidence_strength": ev_strength,
            "evidence_scope": evidence_scope,
            "binding_evidence_text": join_unique(r.get("binding_evidence_text", "") for r in rows)[:800],
            "selection_evidence_summary": join_unique(r.get("selection_evidence", "") for r in rows),
            "representative_title": rep_title[:500],
            "descriptions": title[:2000],
            "references": join_unique(r.get("reference", "") for r in rows)[:2000],
            "publication_or_patent_identifier": join_unique(
                r.get("publication_or_patent_identifier", "") for r in rows
            ),
            "rna_identity_statuses": join_unique(r.get("rna_identity_status", "") for r in rows),
            "sequence_role_statuses": join_unique(r.get("sequence_role", "") for r in rows),
            "conflict_type": conflict_type,
            "genuine_target_conflict": "1" if conflict_is_biological(conflict_type) else "0",
            "same_sequence_other_targets": " | ".join(other_labels),
            "automatic_concern_flags": ";".join(concerns),
            "near_duplicate_family_id": "",
            "near_duplicate_family_size": "",
            "possible_post_promoter_sequence": post_seq,
            "post_promoter_sequence_length": str(len(post_seq)) if post_seq else "",
            "promoter_trim_status": trim_status,
            "consolidated_from_v1_units": join_unique(r.get("review_unit_id_v1", "") for r in rows),
            "manual_include": "",
            "manual_target_corrected": "",
            "manual_sequence_corrected": "",
            "manual_exclusion_reason": "",
            "manual_notes": "",
            "allow_ambiguous_include": "",
        }
        units.append(unit)

        for r in rows:
            provenance.append(
                {
                    "review_unit_id": unit_id,
                    "accession": str(r["accession"]),
                    "experiment_group_id": str(r["experiment_group_id"]),
                    "sequence_deposited": str(r["sequence_deposited"]),
                    "rna_sequence": str(r["rna_sequence"]),
                    "target_raw": str(r["target_raw"]),
                    "target_name": str(r.get("target_name", "")),
                    "target_display_name": str(r["target_display_name"]),
                    "target_comparison_key": str(r["target_comparison_key"]),
                    "target_region": str(r.get("target_region", "")),
                    "target_type": str(r["target_type"]),
                    "target_repair_reason": str(r.get("target_repair_reason", "")),
                    "unresolved_target": str(r.get("unresolved_target", "0")),
                    "manual_target_applied": str(r.get("manual_target_applied", "0")),
                    "manual_target_type_applied": str(r.get("manual_target_type_applied", "0")),
                    "description": str(r.get("description", "")),
                    "reference": str(r.get("reference", "")),
                    "binding_evidence_type": str(r.get("binding_evidence_type", "")),
                    "binding_evidence_strength": str(r.get("binding_evidence_strength", "")),
                    "evidence_scope": str(r.get("evidence_scope", "")),
                    "evidence_repair_reason": str(r.get("evidence_repair_reason", "")),
                    "selection_evidence": str(r.get("selection_evidence", "")),
                    "sequence_role": str(r.get("sequence_role", "")),
                    "sequence_quality_status": str(r.get("sequence_quality_status", "")),
                    "ambiguity_symbols": str(r.get("ambiguity_symbols", "")),
                    "ambiguous_base_count": str(r.get("ambiguous_base_count", "")),
                    "longest_ambiguous_run": str(r.get("longest_ambiguous_run", "")),
                    "promoter_trim_status": str(r.get("promoter_trim_status", "")),
                    "possible_post_promoter_sequence": str(r.get("possible_post_promoter_sequence", "")),
                    "source_candidate_tier": str(r.get("source_candidate_tier", "")),
                    "review_unit_id_v1": str(r.get("review_unit_id_v1", "")),
                }
            )

        if conflict_is_biological(conflict_type):
            conflict_rows.append(
                {
                    "review_unit_id": unit_id,
                    "rna_sequence": seq,
                    "target_display_name": display,
                    "target_comparison_key": cmp_key,
                    "target_region": region,
                    "conflict_type": conflict_type,
                    "same_sequence_other_targets": " | ".join(other_labels),
                    "accessions": "|".join(accessions),
                    "experiment_group_id": exp_group,
                }
            )

    units_df = pd.DataFrame(units)
    prov_df = pd.DataFrame(provenance)
    conflict_df = pd.DataFrame(conflict_rows).drop_duplicates()
    return units_df, prov_df, conflict_df


def attach_near_duplicates(units_df: pd.DataFrame) -> pd.DataFrame:
    if units_df.empty:
        return units_df
    unit_list = []
    for _, u in units_df.iterrows():
        d = u.to_dict()
        d["target_key"] = d.get("target_comparison_key", "")
        unit_list.append(d)
    unit_to_family, _, _ = assign_near_duplicate_families(
        unit_list,
        seq_key="rna_sequence",
        group_key="experiment_group_id",
        target_key="target_key",
        id_key="review_unit_id",
    )
    fam_sizes = Counter(unit_to_family.values())
    out = units_df.copy()
    out["near_duplicate_family_id"] = out["review_unit_id"].map(
        lambda i: unit_to_family.get(str(i), "")
    )
    out["near_duplicate_family_size"] = out["near_duplicate_family_id"].map(
        lambda f: str(fam_sizes[f]) if f else ""
    )
    return out


# ---------------------------------------------------------------------------
# Repair audit tables
# ---------------------------------------------------------------------------


def build_target_repairs(acc_df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "accession",
        "experiment_group_id",
        "target_raw",
        "target_name",
        "target_display_name",
        "target_comparison_key",
        "target_region",
        "target_context",
        "target_type",
        "target_type_prior",
        "target_repair_reason",
        "target_confidence",
        "target_type_changed",
        "target_alias_applied",
        "target_was_generic",
        "target_unresolved",
        "target_notes",
        "description",
    ]
    # Prefer rows where something interesting happened
    mask = (
        (acc_df["target_type_changed"] == "1")
        | (acc_df["target_alias_applied"] == "1")
        | (acc_df["target_was_generic"] == "1")
        | (acc_df["target_unresolved"] == "1")
        | (acc_df["target_region"] != "")
        | (~acc_df["target_repair_reason"].isin(["unchanged", ""]))
    )
    out = acc_df.loc[mask, cols].drop_duplicates()
    return out


def build_target_aliases_table() -> pd.DataFrame:
    rows = []
    seen_keys: set[str] = set()
    for ortho, display in sorted(TARGET_ALIASES.items()):
        key = normalize_target_comparison_key(display)
        if key in seen_keys and ortho == key:
            continue
        rows.append(
            {
                "alias_orthographic_form": ortho,
                "preferred_display_name": display,
                "target_comparison_key": key,
                "notes": "configured_alias",
            }
        )
        seen_keys.add(key)
    return pd.DataFrame(rows)


def build_evidence_repairs(acc_df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "accession",
        "experiment_group_id",
        "evidence_prior_scope",
        "evidence_scope",
        "binding_evidence_type",
        "binding_evidence_strength",
        "evidence_repair_reason",
        "evidence_upgraded_from_none",
        "evidence_downgraded_from_individual",
        "binding_evidence_text",
        "description",
        "reference",
    ]
    mask = (
        (acc_df["evidence_upgraded_from_none"] == "1")
        | (acc_df["evidence_downgraded_from_individual"] == "1")
        | (~acc_df["evidence_repair_reason"].isin(["preserved_prior", "no_evidence", ""]))
    )
    return acc_df.loc[mask, cols].drop_duplicates()


# ---------------------------------------------------------------------------
# Group review template
# ---------------------------------------------------------------------------


GROUP_TEMPLATE_COLUMNS = [
    "manual_group_include",
    "manual_target_corrected",
    "manual_target_type_corrected",
    "manual_group_notes",
    "experiment_group_id",
    "representative_accession",
    "target_display_name",
    "target_type",
    "target_region",
    "representative_title",
    "publication_or_patent_identifier",
    "member_accession_count",
    "unique_exact_sequence_count",
    "concrete_sequence_count",
    "ambiguous_sequence_count",
    "library_template_count",
    "short_sequence_count",
    "promoter_or_template_count",
    "sequence_length_min",
    "sequence_length_median",
    "sequence_length_max",
    "binding_evidence_type",
    "binding_evidence_strength",
    "evidence_scope",
    "selection_evidence_summary",
    "recommended_group_action",
    "group_concerns",
    "sample_sequence_1",
    "sample_sequence_2",
    "sample_sequence_3",
]


def build_group_review(
    acc_df: pd.DataFrame,
    units_df: pd.DataFrame,
    stage3_groups: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    group_ids = sorted(
        {g for g in acc_df["experiment_group_id"].tolist() if str(g).strip()}
    )
    units_by_group: dict[str, list[dict]] = defaultdict(list)
    for _, u in units_df.iterrows():
        units_by_group[str(u["experiment_group_id"])].append(u.to_dict())

    meta = {}
    if not stage3_groups.empty and "experiment_group_id" in stage3_groups.columns:
        for _, gr in stage3_groups.iterrows():
            meta[str(gr["experiment_group_id"])] = gr.to_dict()

    template_rows: list[dict[str, Any]] = []
    provenance_rows: list[dict[str, Any]] = []

    for gid in group_ids:
        members = acc_df[acc_df["experiment_group_id"] == gid]
        if members.empty:
            continue
        accessions = sorted(members["accession"].astype(str).tolist())
        lengths = [
            int(x)
            for x in members["sequence_length"].tolist()
            if str(x).isdigit() and int(x) > 0
        ]
        rna_seqs = members["rna_sequence"].astype(str)
        concrete_n = int((members["is_concrete"] == "1").sum())
        amb_n = int((members["contains_ambiguous_bases"] == "1").sum())
        lib_n = int((members["sequence_quality_status"] == "degenerate_library_template").sum())
        short_n = int(
            members["length_status"].isin(
                ["under_15_high_concern", "15_to_19_short_review"]
            ).sum()
        )
        promo_n = int(
            (
                (members["contains_t7_promoter"] == "1")
                | (members["sequence_quality_status"] == "promoter_or_template_requires_review")
            ).sum()
        )
        unique_exact = int(rna_seqs[rna_seqs != ""].nunique())

        # Dominant target
        tgt_counts = members.loc[
            members["target_display_name"] != "", "target_display_name"
        ].value_counts()
        target_display = tgt_counts.index[0] if len(tgt_counts) else ""
        ttype_counts = members["target_type"].value_counts()
        target_type = ttype_counts.index[0] if len(ttype_counts) else "unknown"
        region = join_unique(members["target_region"].tolist())

        unit_rows = units_by_group.get(gid, [])
        scopes = [str(u.get("evidence_scope", "")) for u in unit_rows] or members[
            "evidence_scope"
        ].tolist()
        evidence_scope = strongest_evidence_scope_v2(scopes)
        ev_type = Counter(
            str(x) for x in (
                [u.get("binding_evidence_type", "") for u in unit_rows]
                or members["binding_evidence_type"].tolist()
            )
            if x
        )
        binding_evidence_type = ev_type.most_common(1)[0][0] if ev_type else "none"
        ev_str = Counter(
            str(x)
            for x in (
                [u.get("binding_evidence_strength", "") for u in unit_rows]
                or members["binding_evidence_strength"].tolist()
            )
            if x
        )
        binding_evidence_strength = ev_str.most_common(1)[0][0] if ev_str else "none"

        m = meta.get(gid, {})
        rep_acc = str(m.get("representative_accession", "") or accessions[0])
        # Compact title: prefer stage3 common_reference / first description
        rep_title = str(
            m.get("common_reference", "")
            or m.get("common_description", "")
            or next((d for d in members["description"].tolist() if str(d).strip()), "")
        )[:400]
        pub_id = join_unique(members["publication_or_patent_identifier"].tolist())

        concerns = []
        if lib_n:
            concerns.append("contains_library_templates")
        if short_n:
            concerns.append("contains_short_sequences")
        if promo_n:
            concerns.append("contains_promoter_or_template")
        if any(str(x) == "1" for x in members["target_was_generic"].tolist()):
            concerns.append("generic_targets_present")
        if members["target_comparison_key"].nunique() > 3:
            concerns.append("heterogeneous_targets")
        if any(str(u.get("genuine_target_conflict", "")) == "1" for u in unit_rows):
            concerns.append("genuine_target_conflicts")
        if any(
            s not in RNA_IDENTITY_PLAUSIBLE
            for s in members["rna_identity_status"].tolist()
            if s
        ):
            # only if none are plausible
            if not any(s in RNA_IDENTITY_PLAUSIBLE for s in members["rna_identity_status"].tolist() if s):
                concerns.append("rna_identity_uncertain")
        if any("uncertain" in str(r).lower() for r in members["sequence_role"].tolist()):
            concerns.append("sequence_roles_uncertain")

        action = recommend_group_action(
            target_type=target_type,
            target_display_name=target_display,
            rna_identity_statuses=members["rna_identity_status"].tolist(),
            concrete_sequence_count=concrete_n,
            library_template_count=lib_n,
            promoter_or_template_count=promo_n,
            member_count=len(members),
            binding_evidence_type=binding_evidence_type,
            evidence_scope=evidence_scope,
            descriptions=join_unique(members["description"].tolist())[:2000],
            group_concerns=concerns,
        )

        # Sample sequences (compact — up to 3 unique)
        samples = []
        for s in rna_seqs.tolist():
            if s and s not in samples:
                samples.append(s)
            if len(samples) >= 3:
                break
        while len(samples) < 3:
            samples.append("")

        template_rows.append(
            {
                "manual_group_include": "",
                "manual_target_corrected": "",
                "manual_target_type_corrected": "",
                "manual_group_notes": "",
                "experiment_group_id": gid,
                "representative_accession": rep_acc,
                "target_display_name": target_display,
                "target_type": target_type,
                "target_region": region,
                "representative_title": rep_title,
                "publication_or_patent_identifier": pub_id,
                "member_accession_count": str(len(members)),
                "unique_exact_sequence_count": str(unique_exact),
                "concrete_sequence_count": str(concrete_n),
                "ambiguous_sequence_count": str(amb_n),
                "library_template_count": str(lib_n),
                "short_sequence_count": str(short_n),
                "promoter_or_template_count": str(promo_n),
                "sequence_length_min": str(min(lengths) if lengths else ""),
                "sequence_length_median": str(_median_int(lengths) if lengths else ""),
                "sequence_length_max": str(max(lengths) if lengths else ""),
                "binding_evidence_type": binding_evidence_type,
                "binding_evidence_strength": binding_evidence_strength,
                "evidence_scope": evidence_scope,
                "selection_evidence_summary": join_unique(
                    members["selection_evidence"].tolist()
                )[:500],
                "recommended_group_action": action,
                "group_concerns": ";".join(concerns),
                "sample_sequence_1": samples[0],
                "sample_sequence_2": samples[1],
                "sample_sequence_3": samples[2],
            }
        )

        provenance_rows.append(
            {
                "experiment_group_id": gid,
                "accessions": "|".join(accessions),
                "all_descriptions": join_unique(members["description"].tolist()),
                "all_references": join_unique(members["reference"].tolist()),
                "target_raw_values": join_unique(members["target_raw"].tolist()),
                "target_display_names": join_unique(members["target_display_name"].tolist()),
                "target_types": join_unique(members["target_type"].tolist()),
                "target_comparison_keys": join_unique(members["target_comparison_key"].tolist()),
                "rna_identity_summary": join_unique(members["rna_identity_status"].tolist()),
                "sequence_role_summary": join_unique(members["sequence_role"].tolist()),
                "doi_values": join_unique(members["doi_values"].tolist()),
                "pubmed_values": join_unique(members["pubmed_values"].tolist()),
                "binding_evidence_texts": join_unique(
                    members["binding_evidence_text"].tolist()
                )[:3000],
                "evidence_scopes": join_unique(members["evidence_scope"].tolist()),
                "review_unit_ids": "|".join(
                    sorted({str(u.get("review_unit_id", "")) for u in unit_rows if u.get("review_unit_id")})
                ),
                "unique_rna_sequences": str(unique_exact),
                "recommended_group_action": action,
            }
        )

    template = pd.DataFrame(template_rows)
    if not template.empty:
        template = template[GROUP_TEMPLATE_COLUMNS]
    provenance = pd.DataFrame(provenance_rows)
    return template, provenance


# ---------------------------------------------------------------------------
# Sequence review template (after group filtering)
# ---------------------------------------------------------------------------


SEQUENCE_TEMPLATE_COLUMNS = [
    "manual_include",
    "manual_target_corrected",
    "manual_sequence_corrected",
    "manual_exclusion_reason",
    "manual_notes",
    "allow_ambiguous_include",
    "review_unit_id",
    "experiment_group_id",
    "experiment_group_ids",
    "target_display_name",
    "target_comparison_key",
    "target_region",
    "target_type",
    "unresolved_target",
    "rna_sequence",
    "sequence_length",
    "sequence_quality_status",
    "length_status",
    "near_duplicate_family_id",
    "near_duplicate_family_size",
    "accession_count",
    "accessions",
    "binding_evidence_type",
    "binding_evidence_strength",
    "evidence_scope",
    "representative_title",
    "automatic_concern_flags",
    "genuine_target_conflict",
]


def _unit_group_ids(row: pd.Series | dict[str, Any]) -> set[str]:
    raw = str(row.get("experiment_group_ids", "") or row.get("experiment_group_id", "") or "")
    return {g for g in raw.split("|") if g.strip()}


def build_sequence_review_for_groups(
    units_df: pd.DataFrame,
    prov_df: pd.DataFrame,
    retained_group_ids: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if units_df.empty or not retained_group_ids:
        empty_t = pd.DataFrame(columns=SEQUENCE_TEMPLATE_COLUMNS)
        return empty_t, pd.DataFrame()

    if "experiment_group_ids" not in units_df.columns:
        units_df = units_df.copy()
        units_df["experiment_group_ids"] = units_df["experiment_group_id"]

    mask = units_df.apply(
        lambda r: bool(_unit_group_ids(r) & retained_group_ids),
        axis=1,
    )
    subset = units_df.loc[mask].copy()
    if "unresolved_target" not in subset.columns:
        subset["unresolved_target"] = "0"
    if "target_comparison_key" not in subset.columns:
        subset["target_comparison_key"] = subset["target_display_name"].map(
            normalize_target_comparison_key
        )
    subset["_len"] = pd.to_numeric(subset["sequence_length"], errors="coerce").fillna(0)
    subset = subset.sort_values(
        by=["experiment_group_id", "target_display_name", "_len", "rna_sequence"]
    )
    subset = subset.drop(columns=["_len"])
    template = pd.DataFrame(
        {
            "manual_include": "",
            "manual_target_corrected": "",
            "manual_sequence_corrected": "",
            "manual_exclusion_reason": "",
            "manual_notes": "",
            "allow_ambiguous_include": "",
            "review_unit_id": subset["review_unit_id"],
            "experiment_group_id": subset["experiment_group_id"],
            "experiment_group_ids": subset["experiment_group_ids"],
            "target_display_name": subset["target_display_name"],
            "target_comparison_key": subset["target_comparison_key"],
            "target_region": subset["target_region"],
            "target_type": subset["target_type"],
            "unresolved_target": subset["unresolved_target"],
            "rna_sequence": subset["rna_sequence"],
            "sequence_length": subset["sequence_length"],
            "sequence_quality_status": subset["sequence_quality_status"],
            "length_status": subset["length_status"],
            "near_duplicate_family_id": subset["near_duplicate_family_id"],
            "near_duplicate_family_size": subset["near_duplicate_family_size"],
            "accession_count": subset["accession_count"],
            "accessions": subset["accessions"],
            "binding_evidence_type": subset["binding_evidence_type"],
            "binding_evidence_strength": subset["binding_evidence_strength"],
            "evidence_scope": subset["evidence_scope"],
            "representative_title": subset["representative_title"],
            "automatic_concern_flags": subset["automatic_concern_flags"],
            "genuine_target_conflict": subset["genuine_target_conflict"],
        }
    )
    # Provenance only for retained units
    retained_uids = set(subset["review_unit_id"].astype(str))
    seq_prov = prov_df[prov_df["review_unit_id"].isin(retained_uids)].copy()
    return template, seq_prov


def expected_sequence_rows_if_recommended(units_df: pd.DataFrame, group_df: pd.DataFrame) -> int:
    retained = set(
        group_df.loc[
            group_df["recommended_group_action"].map(is_retention_recommendation),
            "experiment_group_id",
        ].astype(str)
    )
    if units_df.empty:
        return 0
    if "experiment_group_ids" in units_df.columns:
        return int(
            units_df.apply(lambda r: bool(_unit_group_ids(r) & retained), axis=1).sum()
        )
    return int(units_df["experiment_group_id"].isin(retained).sum())


# ---------------------------------------------------------------------------
# QC report
# ---------------------------------------------------------------------------


def write_qc_report(
    path: Path,
    *,
    group_df: pd.DataFrame,
    units_df: pd.DataFrame,
    repair_df: pd.DataFrame,
    evidence_df: pd.DataFrame,
    conflict_df: pd.DataFrame,
    acc_df: pd.DataFrame,
    alias_df: pd.DataFrame,
) -> None:
    n_groups = len(group_df)
    n_retain = int(group_df["recommended_group_action"].map(is_retention_recommendation).sum()) if n_groups else 0
    n_reject = int(
        group_df["recommended_group_action"].astype(str).str.startswith("reject_").sum()
    ) if n_groups else 0
    n_unresolved = int(
        (group_df["recommended_group_action"] == "insufficient_information").sum()
    ) if n_groups else 0

    type_repairs = int((acc_df["target_type_changed"] == "1").sum()) if not acc_df.empty else 0
    alias_hits = int((acc_df["target_alias_applied"] == "1").sum()) if not acc_df.empty else 0
    # False conflicts removed = sequences where stage would have conflicted on
    # orthographic forms but v2 says no_conflict / orthographic_alias_only
    false_removed = 0
    genuine = 0
    if not units_df.empty:
        false_removed = int((units_df["conflict_type"] == "orthographic_alias_only").sum())
        # Also count FGF-style cases now no_conflict that share alias key
        genuine = int((units_df["genuine_target_conflict"] == "1").sum())

    upgraded = int((acc_df["evidence_upgraded_from_none"] == "1").sum()) if not acc_df.empty else 0
    downgraded = int((acc_df["evidence_downgraded_from_individual"] == "1").sum()) if not acc_df.empty else 0

    # Ambiguous consolidations: units with ambiguity and accession_count > 1
    amb_consol = 0
    if not units_df.empty:
        amb_consol = int(
            (
                (units_df["contains_ambiguous_bases"] == "1")
                & (pd.to_numeric(units_df["accession_count"], errors="coerce").fillna(0) > 1)
            ).sum()
        )

    expected_seq = expected_sequence_rows_if_recommended(units_df, group_df)

    lines = [
        "# ENA group-review QC report (review v2)",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Corrective stage 4: target/evidence repair and group-first clerical review.",
        "Manual decisions are not pre-filled.",
        "",
        "## Summary",
        "",
        "| metric | count |",
        "|---|---:|",
        f"| experiment groups assessed | {n_groups} |",
        f"| groups recommended for retention | {n_retain} |",
        f"| groups recommended for rejection | {n_reject} |",
        f"| unresolved groups (insufficient_information) | {n_unresolved} |",
        f"| target-repair audit rows | {len(repair_df)} |",
        f"| target-type repairs | {type_repairs} |",
        f"| alias dictionary entries | {len(alias_df)} |",
        f"| alias applications (accession rows) | {alias_hits} |",
        f"| orthographic-only conflict labels | {false_removed} |",
        f"| genuine / unresolved conflict units | {genuine} |",
        f"| conflict CSV rows (biological only) | {len(conflict_df)} |",
        f"| evidence upgraded from none/selection → patent claim | {upgraded} |",
        f"| evidence downgraded from individual → patent/family | {downgraded} |",
        f"| ambiguous duplicate rows consolidated (units) | {amb_consol} |",
        f"| compact group-review row count | {n_groups} |",
        f"| sequence rows if all recommended groups retained | {expected_seq} |",
        f"| total consolidated sequence–target units | {len(units_df)} |",
        "",
        "## Experiment groups",
        "",
        "| experiment_group_id | target | members | evidence_scope | recommended_action | concerns |",
        "|---|---|---:|---|---|---|",
    ]
    if not group_df.empty:
        for _, g in group_df.sort_values("experiment_group_id").iterrows():
            lines.append(
                "| {gid} | {tgt} | {n} | {scope} | {act} | {c} |".format(
                    gid=g["experiment_group_id"],
                    tgt=str(g["target_display_name"]).replace("|", "/")[:40],
                    n=g["member_accession_count"],
                    scope=g["evidence_scope"],
                    act=g["recommended_group_action"],
                    c=str(g["group_concerns"]).replace("|", ";")[:60],
                )
            )
    else:
        lines.append("| _(none)_ | | | | | |")

    lines.extend(["", "## Recommended action counts", ""])
    if not group_df.empty:
        for act, cnt in group_df["recommended_group_action"].value_counts().items():
            lines.append(f"- `{act}`: {cnt}")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def run_build_review(
    review_dir: Path,
    candidate_dir: Path | None,
    output_dir: Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sentinel = output_dir / "ena_group_review_template.csv"
    if sentinel.exists() and not overwrite:
        raise FileExistsError(
            f"{sentinel} exists; pass --overwrite to replace review_v2 outputs"
        )

    tables = load_inputs(review_dir, candidate_dir)
    candidates = _candidate_lookup(tables)
    logger.info(
        "Loaded stage-3 review: %d units, %d provenance, %d groups",
        len(tables["ena_sequence_target_review.csv"]),
        len(tables["ena_sequence_target_provenance.csv"]),
        len(tables["ena_experiment_group_review.csv"]),
    )

    acc_df = build_repaired_accessions(
        tables["ena_sequence_target_provenance.csv"],
        tables["ena_sequence_target_review.csv"],
        candidates,
    )
    logger.info("Repaired %d accession-level rows", len(acc_df))

    units_df, full_prov_df, conflict_df = consolidate_sequence_target_units(acc_df)
    units_df = attach_near_duplicates(units_df)
    logger.info(
        "Consolidated to %d sequence–target units; %d biological conflicts",
        len(units_df),
        len(conflict_df),
    )

    repair_df = build_target_repairs(acc_df)
    alias_df = build_target_aliases_table()
    evidence_df = build_evidence_repairs(acc_df)

    group_df, group_prov_df = build_group_review(
        acc_df,
        units_df,
        tables["ena_experiment_group_review.csv"],
    )
    logger.info("Built compact group-review template: %d rows", len(group_df))

    # Persist core outputs (sequence template deferred until apply-group-review)
    _write_csv(group_df, output_dir / "ena_group_review_template.csv", excel=True)
    _write_csv(group_prov_df, output_dir / "ena_group_review_provenance.csv")
    _write_csv(repair_df, output_dir / "ena_target_repairs.csv")
    _write_csv(alias_df, output_dir / "ena_target_aliases.csv")
    _write_csv(evidence_df, output_dir / "ena_evidence_repairs.csv")
    _write_csv(conflict_df, output_dir / "ena_sequence_conflicts.csv")
    # Internal working tables used by apply-group-review
    _write_csv(units_df, output_dir / "ena_sequence_target_units_v2.csv")
    _write_csv(full_prov_df, output_dir / "ena_sequence_review_provenance_all.csv")

    write_qc_report(
        output_dir / "ena_group_review_qc_report.md",
        group_df=group_df,
        units_df=units_df,
        repair_df=repair_df,
        evidence_df=evidence_df,
        conflict_df=conflict_df,
        acc_df=acc_df,
        alias_df=alias_df,
    )

    expected = expected_sequence_rows_if_recommended(units_df, group_df)
    n_retain = int(group_df["recommended_group_action"].map(is_retention_recommendation).sum())

    summary = {
        "accessions": len(acc_df),
        "units": len(units_df),
        "groups": len(group_df),
        "groups_recommended_retain": n_retain,
        "conflicts_biological": len(conflict_df),
        "target_repairs": len(repair_df),
        "evidence_repairs": len(evidence_df),
        "expected_sequence_rows_if_recommended": expected,
        "upgraded_evidence": int((acc_df["evidence_upgraded_from_none"] == "1").sum()),
        "downgraded_evidence": int((acc_df["evidence_downgraded_from_individual"] == "1").sum()),
        "type_repairs": int((acc_df["target_type_changed"] == "1").sum()),
        "alias_applications": int((acc_df["target_alias_applied"] == "1").sum()),
    }
    logger.info("Build summary: %s", summary)
    return summary


# Groups retained by the clerk but still lacking a named molecular target.
UNRESOLVED_TARGET_GROUP_IDS = frozenset(
    {
        "experiment_aa2c06865e",  # no named target
        "experiment_00caf42363",  # generic "genome editing enzyme"
    }
)

UNRESOLVED_TARGET_PHRASES = frozenset(
    {
        "genome editing enzyme",
        "genome-editing enzyme",
        "unknown",
        "",
    }
)


def effective_group_target(row: pd.Series | dict[str, Any]) -> tuple[str, str, bool, bool]:
    """Return (display_name, target_type, target_was_corrected, type_was_corrected)."""
    corrected = str(row.get("manual_target_corrected", "") or "").strip()
    display = corrected if corrected else str(row.get("target_display_name", "") or "").strip()
    type_corr = str(row.get("manual_target_type_corrected", "") or "").strip()
    ttype = type_corr if type_corr else str(row.get("target_type", "") or "").strip() or "unknown"
    return display, ttype, bool(corrected), bool(type_corr)


def is_unresolved_effective_target(display: str, group_id: str = "") -> bool:
    if group_id in UNRESOLVED_TARGET_GROUP_IDS:
        return True
    cleaned = (display or "").strip()
    if not cleaned or cleaned.lower() in UNRESOLVED_TARGET_PHRASES:
        return True
    if is_generic_target_phrase(cleaned):
        return True
    return False


def accession_df_from_provenance(prov_df: pd.DataFrame) -> pd.DataFrame:
    """Rebuild accession-level working rows from build-review provenance."""
    rows: list[dict[str, Any]] = []
    for _, prow in prov_df.iterrows():
        rna = str(prow.get("rna_sequence", "") or "")
        quality = assess_sequence_quality(
            rna,
            description=str(prow.get("description", "")),
            sequence_role=str(prow.get("sequence_role", "")),
        )
        trim = propose_promoter_trim(rna)
        amb_sym = str(prow.get("ambiguity_symbols", "") or quality.ambiguity_symbols_present)
        amb_count = str(prow.get("ambiguous_base_count", "") or quality.ambiguous_base_count)
        long_run = str(prow.get("longest_ambiguous_run", "") or quality.longest_ambiguous_run)
        rows.append(
            {
                "accession": str(prow.get("accession", "")),
                "review_unit_id_v1": str(prow.get("review_unit_id_v1", "")),
                "experiment_group_id": str(prow.get("experiment_group_id", "")),
                "sequence_deposited": str(prow.get("sequence_deposited", "")),
                "rna_sequence": rna,
                "sequence_length": str(quality.sequence_length),
                "is_concrete": "1" if quality.is_concrete else "0",
                "contains_ambiguous_bases": "1" if quality.contains_ambiguous_bases else "0",
                "ambiguous_base_count": amb_count,
                "longest_ambiguous_run": long_run,
                "ambiguity_symbols": amb_sym,
                "sequence_quality_status": str(
                    prow.get("sequence_quality_status", "") or quality.sequence_quality_status
                ),
                "length_status": quality.length_status,
                "contains_t7_promoter": "1" if quality.contains_t7_promoter else "0",
                "possible_post_promoter_sequence": str(
                    prow.get("possible_post_promoter_sequence", "")
                    or trim.possible_post_promoter_sequence
                ),
                "post_promoter_sequence_length": str(
                    trim.post_promoter_sequence_length
                    if trim.possible_post_promoter_sequence
                    else prow.get("post_promoter_sequence_length", "")
                ),
                "promoter_trim_status": str(
                    prow.get("promoter_trim_status", "") or trim.promoter_trim_status
                ),
                "description": str(prow.get("description", "")),
                "reference": str(prow.get("reference", "")),
                "rna_identity_status": str(prow.get("rna_identity_status", "")),
                "sequence_role": str(prow.get("sequence_role", "")),
                "selection_evidence": str(prow.get("selection_evidence", "")),
                "source_candidate_tier": str(prow.get("source_candidate_tier", "")),
                "doi_values": "",
                "pubmed_values": "",
                "publication_or_patent_identifier": "",
                "target_raw": str(prow.get("target_raw", "")),
                "target_name": str(prow.get("target_name", "")),
                "target_display_name": str(prow.get("target_display_name", "")),
                "target_comparison_key": str(prow.get("target_comparison_key", "")),
                "target_region": str(prow.get("target_region", "")),
                "target_context": str(prow.get("target_context", "")),
                "target_type": str(prow.get("target_type", "") or "unknown"),
                "target_repair_reason": str(prow.get("target_repair_reason", "")),
                "target_confidence": "moderate",
                "target_type_prior": str(prow.get("target_type", "")),
                "target_type_changed": "0",
                "target_alias_applied": "0",
                "target_was_generic": "0",
                "target_unresolved": "0",
                "target_notes": "",
                "binding_evidence_strength": str(prow.get("binding_evidence_strength", "")),
                "binding_evidence_type": str(prow.get("binding_evidence_type", "")),
                "evidence_scope": str(prow.get("evidence_scope", "")),
                "binding_evidence_text": str(prow.get("binding_evidence_text", "")),
                "evidence_prior_scope": "",
                "evidence_repair_reason": str(prow.get("evidence_repair_reason", "")),
                "evidence_upgraded_from_none": "0",
                "evidence_downgraded_from_individual": "0",
                "manual_target_applied": "0",
                "manual_target_type_applied": "0",
                "unresolved_target": "0",
            }
        )
    return pd.DataFrame(rows)


def apply_group_corrections_to_accessions(
    acc_df: pd.DataFrame,
    retained_groups: pd.DataFrame,
) -> pd.DataFrame:
    """Overwrite targets/types for retained groups; recalculate comparison keys."""
    out = acc_df.copy()
    meta: dict[str, dict[str, Any]] = {}
    for _, grow in retained_groups.iterrows():
        gid = str(grow["experiment_group_id"])
        display, ttype, tgt_corr, type_corr = effective_group_target(grow)
        # Canonicalise display via alias dictionary
        display_pref = preferred_display_name(display, fallback=display) if display else display
        cmp_key = normalize_target_comparison_key(display_pref) if display_pref else "UNKNOWN"
        unresolved = is_unresolved_effective_target(display_pref, gid)
        meta[gid] = {
            "target_display_name": display_pref,
            "target_name": display_pref,
            "target_type": ttype or "unknown",
            "target_comparison_key": cmp_key or "UNKNOWN",
            "manual_target_applied": "1" if tgt_corr else "0",
            "manual_target_type_applied": "1" if type_corr else "0",
            "unresolved_target": "1" if unresolved else "0",
            "target_repair_reason": (
                "group_manual_correction"
                if (tgt_corr or type_corr)
                else "group_effective_unchanged"
            ),
        }

    for idx, row in out.iterrows():
        gid = str(row["experiment_group_id"])
        if gid not in meta:
            continue
        m = meta[gid]
        out.at[idx, "target_display_name"] = m["target_display_name"]
        out.at[idx, "target_name"] = m["target_name"]
        out.at[idx, "target_type"] = m["target_type"]
        out.at[idx, "target_comparison_key"] = m["target_comparison_key"]
        out.at[idx, "manual_target_applied"] = m["manual_target_applied"]
        out.at[idx, "manual_target_type_applied"] = m["manual_target_type_applied"]
        out.at[idx, "unresolved_target"] = m["unresolved_target"]
        out.at[idx, "target_unresolved"] = m["unresolved_target"]
        out.at[idx, "target_repair_reason"] = m["target_repair_reason"]
        if m["manual_target_applied"] == "1":
            out.at[idx, "target_raw"] = m["target_display_name"]
    return out


def validate_sequence_template_against_groups(
    seq_template: pd.DataFrame,
    retained_groups: pd.DataFrame,
) -> list[str]:
    """Fail clearly if corrected group targets/types are not propagated."""
    errors: list[str] = []
    if seq_template.empty:
        return errors

    for _, grow in retained_groups.iterrows():
        gid = str(grow["experiment_group_id"])
        eff_display, eff_type, tgt_corr, type_corr = effective_group_target(grow)
        eff_display = preferred_display_name(eff_display, fallback=eff_display) if eff_display else eff_display
        eff_key = normalize_target_comparison_key(eff_display) if eff_display else ""
        unresolved = is_unresolved_effective_target(eff_display, gid)

        # Rows whose group membership includes this experiment group
        if "experiment_group_ids" in seq_template.columns:
            mask = seq_template["experiment_group_ids"].fillna("").map(
                lambda s: gid in str(s).split("|")
            ) | (seq_template["experiment_group_id"] == gid)
        else:
            mask = seq_template["experiment_group_id"] == gid
        rows = seq_template.loc[mask]
        if rows.empty:
            # Retained group with no sequences is unusual but not a propagation failure
            continue

        displays = set(rows["target_display_name"].astype(str))
        types = set(rows["target_type"].astype(str))
        keys = set(rows["target_comparison_key"].astype(str)) if "target_comparison_key" in rows.columns else set()

        if not unresolved:
            if tgt_corr and eff_display and eff_display not in displays:
                # Alias-equivalent display is OK
                if not any(normalize_target_comparison_key(d) == eff_key for d in displays):
                    errors.append(
                        f"{gid}: expected corrected target {eff_display!r} in sequence "
                        f"template; found {sorted(displays)}"
                    )
            if type_corr and eff_type and eff_type not in types:
                errors.append(
                    f"{gid}: expected corrected type {eff_type!r} in sequence "
                    f"template; found {sorted(types)}"
                )
            if eff_key and keys and eff_key not in keys:
                # All rows for this group should share the effective key
                if not keys.issubset({eff_key, "UNKNOWN"}):
                    errors.append(
                        f"{gid}: expected comparison key {eff_key!r}; found {sorted(keys)}"
                    )
        else:
            if "unresolved_target" in rows.columns and not (rows["unresolved_target"] == "1").all():
                errors.append(f"{gid}: unresolved retained group not flagged on all sequence rows")

    return errors


def write_apply_group_qc_report(
    path: Path,
    *,
    retained: pd.DataFrame,
    seq_template: pd.DataFrame,
    conflict_df: pd.DataFrame,
    tests_passed: int | None,
    alias_conflicts_removed: int,
) -> None:
    retained_ids = set(retained["experiment_group_id"].astype(str))
    if seq_template.empty:
        canonical = 0
        n_tgt = n_type = n_unresolved = n_genuine = 0
    else:
        all_gids: set[str] = set()
        for _, r in seq_template.iterrows():
            all_gids |= _unit_group_ids(r)
        canonical = len(all_gids & retained_ids)
        n_tgt = int((seq_template.get("automatic_concern_flags", pd.Series(dtype=str))
                     .fillna("")
                     .astype(str)
                     .str.contains("group_manual_target_applied")).sum()) if not seq_template.empty else 0
        # Prefer explicit columns when present
        if "manual_target_applied" in seq_template.columns:
            n_tgt = int((seq_template["manual_target_applied"] == "1").sum())
        else:
            # Infer from retained corrections reflected in display
            corr_gids = {
                str(r["experiment_group_id"])
                for _, r in retained.iterrows()
                if str(r.get("manual_target_corrected", "")).strip()
            }
            n_tgt = int(
                seq_template.apply(
                    lambda r: bool(_unit_group_ids(r) & corr_gids), axis=1
                ).sum()
            ) if corr_gids else 0
        corr_type_gids = {
            str(r["experiment_group_id"])
            for _, r in retained.iterrows()
            if str(r.get("manual_target_type_corrected", "")).strip()
        }
        n_type = int(
            seq_template.apply(
                lambda r: bool(_unit_group_ids(r) & corr_type_gids), axis=1
            ).sum()
        ) if corr_type_gids else 0
        n_unresolved = int((seq_template["unresolved_target"] == "1").sum()) if "unresolved_target" in seq_template.columns else 0
        n_genuine = int((seq_template["genuine_target_conflict"] == "1").sum())

    lines = [
        "# ENA apply-group-review QC report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Sequence-level template after applying group 0/1 decisions and manual",
        "target / target-type corrections. Sequence `manual_include` is blank.",
        "",
        "## Summary",
        "",
        "| metric | count |",
        "|---|---:|",
        f"| retained groups | {len(retained)} |",
        f"| canonical groups represented in sequence template | {canonical} |",
        f"| sequence-review rows | {len(seq_template)} |",
        f"| rows receiving manual target corrections | {n_tgt} |",
        f"| rows receiving manual target-type corrections | {n_type} |",
        f"| unresolved-target rows | {n_unresolved} |",
        f"| genuine conflicts after repair | {n_genuine} |",
        f"| conflict CSV rows | {len(conflict_df)} |",
        f"| alias-only conflicts removed | {alias_conflicts_removed} |",
        f"| tests passed | {tests_passed if tests_passed is not None else 'n/a'} |",
        "",
        "## Retained groups (effective targets)",
        "",
        "| experiment_group_id | effective_target | effective_type | unresolved |",
        "|---|---|---|---|",
    ]
    for _, g in retained.sort_values("experiment_group_id").iterrows():
        disp, ttype, _, _ = effective_group_target(g)
        disp = preferred_display_name(disp, fallback=disp) if disp else disp
        unresolved = "yes" if is_unresolved_effective_target(disp, str(g["experiment_group_id"])) else ""
        lines.append(
            f"| {g['experiment_group_id']} | {str(disp).replace('|', '/')[:50]} | {ttype} | {unresolved} |"
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_apply_group_review(
    group_review_file: Path,
    output_dir: Path,
    *,
    tests_passed: int | None = None,
) -> dict[str, Any]:
    if not group_review_file.exists():
        raise FileNotFoundError(group_review_file)
    group_df = _read_csv(group_review_file)

    if "manual_group_include" not in group_df.columns:
        raise ReviewValidationError("missing column manual_group_include")

    normalised = []
    for i, val in enumerate(group_df["manual_group_include"].tolist()):
        nv = validate_manual_group_include(val)
        if nv is None:
            raise ReviewValidationError(
                f"row {i}: manual_group_include must be blank, 0, or 1 (got {val!r})"
            )
        normalised.append(nv)
    group_df = group_df.copy()
    group_df["manual_group_include"] = normalised

    retained = group_df[group_df["manual_group_include"] == "1"].copy()
    rejected = group_df[group_df["manual_group_include"] == "0"].copy()
    unreviewed = group_df[group_df["manual_group_include"] == ""].copy()

    _write_csv(retained, output_dir / "ena_groups_retained_after_review.csv", excel=True)
    _write_csv(rejected, output_dir / "ena_groups_rejected_after_review.csv", excel=True)

    prov_all_path = output_dir / "ena_sequence_review_provenance_all.csv"
    if not prov_all_path.exists():
        raise FileNotFoundError(
            "Missing ena_sequence_review_provenance_all.csv; run build-review first"
        )
    prov_all = _read_csv(prov_all_path)

    # Accession-level rebuild → apply corrections → re-consolidate
    acc_df = accession_df_from_provenance(prov_all)
    # Restrict to retained groups before correction/consolidation
    retained_ids = set(retained["experiment_group_id"].astype(str))
    acc_retained = acc_df[acc_df["experiment_group_id"].isin(retained_ids)].copy()
    if acc_retained.empty:
        seq_template = pd.DataFrame(columns=SEQUENCE_TEMPLATE_COLUMNS)
        seq_prov = pd.DataFrame()
        conflict_df = pd.DataFrame()
        alias_removed = 0
    else:
        before_keys = set(
            zip(
                acc_retained["rna_sequence"].astype(str),
                acc_retained["target_comparison_key"].astype(str),
            )
        )
        acc_corrected = apply_group_corrections_to_accessions(acc_retained, retained)
        # Count alias reconciliations (TSA56 family / FGF2) that collapse keys
        after_keys = set(
            zip(
                acc_corrected["rna_sequence"].astype(str),
                acc_corrected["target_comparison_key"].astype(str),
            )
        )
        units_df, full_prov_df, conflict_df = consolidate_sequence_target_units(acc_corrected)
        units_df = attach_near_duplicates(units_df)

        # Alias-only conflicts removed: sequences that previously had multiple
        # orthographic keys now share one key and are not biological conflicts
        alias_removed = 0
        if not units_df.empty:
            # Pre-correction would have flagged FGF2/FGF-2 and TSA56 variants
            pre_conflict_pairs = 0
            seq_to_keys_before: dict[str, set[str]] = defaultdict(set)
            for seq, key in before_keys:
                if seq and key and key not in {"UNKNOWN", ""}:
                    seq_to_keys_before[seq].add(key)
            for seq, keys in seq_to_keys_before.items():
                if len(keys) > 1:
                    # Check whether post-correction keys collapse
                    post = units_df[units_df["rna_sequence"] == seq]
                    post_keys = set(post["target_comparison_key"].astype(str))
                    post_keys.discard("")
                    if len(post_keys) <= 1 and (
                        post.empty or (post["genuine_target_conflict"] == "0").all()
                    ):
                        alias_removed += 1
                    pre_conflict_pairs += 1
            # Prefer counting units that are orthographic-only resolved
            tsa_keys = {
                normalize_target_comparison_key("TSA56"),
                normalize_target_comparison_key("TST56"),
                normalize_target_comparison_key("TSG56"),
            }
            if len(tsa_keys) == 1:
                # All three aliases share a key — count accession rows updated
                alias_removed = max(
                    alias_removed,
                    int(
                        (
                            acc_corrected["target_comparison_key"]
                            == normalize_target_comparison_key("TSA56")
                        ).sum()
                        and len(tsa_keys) == 1
                    ),
                )
            # Simpler metric: number of retained accession rows whose display was
            # alias-normalised to TSA56 / FGF2 from a variant spelling
            alias_removed = int(
                (
                    (acc_corrected["manual_target_applied"] == "1")
                    & (
                        acc_corrected["target_comparison_key"].isin(
                            [
                                normalize_target_comparison_key("TSA56"),
                                normalize_target_comparison_key("FGF2"),
                            ]
                        )
                    )
                ).sum()
            )
            # Plus automatic alias collapses without manual correction
            auto_alias = 0
            for seq, keys in seq_to_keys_before.items():
                normed = {normalize_target_comparison_key(k) for k in keys}
                # If raw keys differed but normalised keys match
                if len(keys) > 1 and len(normed) == 1:
                    auto_alias += 1
            alias_removed = max(alias_removed, auto_alias)

        seq_template, seq_prov = build_sequence_review_for_groups(
            units_df, full_prov_df, retained_ids
        )

        # Carry applied flags onto template for QC when present on units
        if not seq_template.empty and not units_df.empty:
            flag_map = units_df.set_index("review_unit_id")
            if "manual_target_applied" in units_df.columns:
                seq_template["manual_target_applied"] = seq_template["review_unit_id"].map(
                    lambda i: flag_map.at[i, "manual_target_applied"] if i in flag_map.index else "0"
                )
            if "manual_target_type_applied" in units_df.columns:
                seq_template["manual_target_type_applied"] = seq_template["review_unit_id"].map(
                    lambda i: flag_map.at[i, "manual_target_type_applied"] if i in flag_map.index else "0"
                )

        errors = validate_sequence_template_against_groups(seq_template, retained)
        if errors:
            raise ReviewValidationError(
                "group corrections not propagated to sequence template:\n- "
                + "\n- ".join(errors)
            )

        # Refresh working units for retained apply (do not overwrite build-all)
        _write_csv(units_df, output_dir / "ena_sequence_target_units_after_group_review.csv")

    _write_csv(seq_template, output_dir / "ena_sequence_review_template.csv", excel=True)
    _write_csv(seq_prov, output_dir / "ena_sequence_review_provenance.csv")
    _write_csv(conflict_df, output_dir / "ena_sequence_conflicts.csv")

    write_apply_group_qc_report(
        output_dir / "ena_apply_group_review_qc_report.md",
        retained=retained,
        seq_template=seq_template,
        conflict_df=conflict_df,
        tests_passed=tests_passed,
        alias_conflicts_removed=alias_removed if not acc_retained.empty else 0,
    )

    summary = {
        "groups_total": len(group_df),
        "groups_retained": len(retained),
        "groups_rejected": len(rejected),
        "groups_unreviewed": len(unreviewed),
        "sequence_review_rows": len(seq_template),
        "unresolved_target_rows": int(
            (seq_template["unresolved_target"] == "1").sum()
        ) if not seq_template.empty and "unresolved_target" in seq_template.columns else 0,
        "genuine_conflicts": int(
            (seq_template["genuine_target_conflict"] == "1").sum()
        ) if not seq_template.empty else 0,
        "conflict_csv_rows": len(conflict_df),
    }
    logger.info("Apply-group-review summary: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Apply sequence-level review
# ---------------------------------------------------------------------------


SEQUENCE_REVIEW_REQUIRED_COLUMNS = [
    "review_unit_id",
    "experiment_group_id",
    "manual_include",
    "manual_target_corrected",
    "manual_sequence_corrected",
    "manual_exclusion_reason",
    "manual_notes",
    "allow_ambiguous_include",
    "target_display_name",
    "target_region",
    "target_type",
    "rna_sequence",
    "accessions",
]

APPLY_SEQUENCE_OUTPUT_FILES = [
    "ena_selected_after_manual_review.csv",
    "ena_rejected_after_manual_review.csv",
    "ena_unreviewed_after_manual_review.csv",
    "ena_selected_sequence_provenance.csv",
    "ena_apply_sequence_review_qc_report.md",
    "ena_apply_sequence_review_log.txt",
]

SELECTED_CORE_COLUMNS = [
    "sequence",
    "target",
    "target_region",
    "target_type",
    "sequence_length",
    "review_unit_id",
    "review_unit_ids",
    "experiment_group_id",
    "experiment_group_ids",
    "accession_count",
    "accessions",
    "near_duplicate_family_id",
    "binding_evidence_type",
    "binding_evidence_strength",
    "evidence_scope",
    "representative_title",
    "manual_target_corrected",
    "manual_sequence_corrected",
    "manual_notes",
    "automatic_concern_flags",
    "source_database",
]

SELECTED_EXTRA_COLUMNS = [
    "sequence_original",
    "target_original",
    "sequence_corrected_applied",
    "target_corrected_applied",
    "allow_ambiguous_include",
    "sequence_quality_status",
    "length_status",
    "selection_evidence_summary",
    "references",
    "doi_values",
    "pubmed_values",
    "genuine_target_conflict",
    "unresolved_target",
    "near_duplicate_family_size",
    "consolidated_from_n_units",
    "target_comparison_key",
]


def _split_pipe(value: Any) -> list[str]:
    return [p.strip() for p in str(value or "").split("|") if p.strip()]


def _join_pipe(values: Iterable[Any]) -> str:
    seen: list[str] = []
    for v in values:
        s = str(v or "").strip()
        if s and s not in seen:
            seen.append(s)
    return "|".join(seen)


def normalize_effective_sequence(raw: str) -> str:
    """Trim, drop internal whitespace, uppercase; preserve nucleotide symbols."""
    return "".join(str(raw or "").split()).upper()


def derive_effective_sequence(row: pd.Series | dict[str, Any]) -> tuple[str, bool]:
    corrected = str(row.get("manual_sequence_corrected", "") or "").strip()
    if corrected:
        return normalize_effective_sequence(corrected), True
    return normalize_effective_sequence(str(row.get("rna_sequence", "") or "")), False


def derive_effective_target(row: pd.Series | dict[str, Any]) -> tuple[str, bool]:
    corrected = str(row.get("manual_target_corrected", "") or "").strip()
    if corrected:
        return corrected, True
    return str(row.get("target_display_name", "") or "").strip(), False


def accepted_pair_key(sequence: str, target: str) -> tuple[str, str]:
    return sequence, normalize_target_comparison_key(target)


def validate_sequence_symbols(sequence: str) -> tuple[list[str], bool]:
    """Return (invalid_chars, has_ambiguity)."""
    invalid = sorted({ch for ch in sequence if ch not in IUPAC_ALL})
    has_amb = any(ch in IUPAC_AMBIGUITY for ch in sequence)
    return invalid, has_amb


def is_placeholder_accepted_target(display: str) -> bool:
    cleaned = (display or "").strip()
    if not cleaned:
        return True
    if cleaned.lower() in UNRESOLVED_TARGET_PHRASES or cleaned.lower() == "unknown":
        return True
    if is_generic_target_phrase(cleaned):
        return True
    return False


def validate_sequence_review_frame(df: pd.DataFrame) -> list[str]:
    """Validate identifiers and decision fields; return error messages."""
    errors: list[str] = []
    missing = [c for c in SEQUENCE_REVIEW_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"missing required columns: {', '.join(missing)}")
        return errors

    empty_ids = [
        i
        for i, uid in enumerate(df["review_unit_id"].tolist())
        if not str(uid or "").strip()
    ]
    for i in empty_ids:
        errors.append(f"row {i}: review_unit_id is empty")

    seen: dict[str, int] = {}
    for i, uid in enumerate(df["review_unit_id"].tolist()):
        uid_s = str(uid or "").strip()
        if not uid_s:
            continue
        if uid_s in seen:
            errors.append(
                f"duplicate review_unit_id {uid_s!r} at rows {seen[uid_s]} and {i}"
            )
        else:
            seen[uid_s] = i

    for i, val in enumerate(df["manual_include"].tolist()):
        if validate_manual_include(val) is None:
            uid = str(df.iloc[i].get("review_unit_id", ""))
            errors.append(
                f"row {i} review_unit_id={uid}: invalid manual_include {val!r} "
                "(allowed: blank, 0, 1)"
            )

    for i, val in enumerate(df["allow_ambiguous_include"].tolist()):
        if validate_manual_include(val) is None:
            uid = str(df.iloc[i].get("review_unit_id", ""))
            errors.append(
                f"row {i} review_unit_id={uid}: invalid allow_ambiguous_include "
                f"{val!r} (allowed: blank, 0, 1)"
            )

    return errors


def validate_accepted_sequence_rows(accepted: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    for i, row in accepted.iterrows():
        uid = str(row.get("review_unit_id", ""))
        seq, _ = derive_effective_sequence(row)
        target, _ = derive_effective_target(row)
        allow_amb = validate_manual_include(row.get("allow_ambiguous_include", "")) or ""

        if not seq:
            errors.append(f"{uid}: accepted row has empty effective sequence")
            continue
        invalid, has_amb = validate_sequence_symbols(seq)
        if invalid:
            errors.append(
                f"{uid}: accepted sequence contains non-IUPAC characters "
                f"{''.join(invalid)!r}"
            )
        if has_amb and allow_amb != "1":
            errors.append(
                f"{uid}: accepted sequence contains ambiguity symbols; "
                "set allow_ambiguous_include=1 to override"
            )
        if is_placeholder_accepted_target(target):
            errors.append(
                f"{uid}: accepted row missing a concrete named target "
                f"(effective_target={target!r})"
            )
    return errors


def _pick_evidence_fields(rows: list[dict[str, Any]]) -> tuple[str, str, str]:
    scopes = [str(r.get("evidence_scope", "") or "") for r in rows]
    best_scope = strongest_evidence_scope_v2(scopes)
    # Map experiment_family_level back if original used experiment_or_family_level
    originals = [s for s in scopes if s]
    if best_scope == "experiment_family_level":
        if any(s == "experiment_or_family_level" for s in originals):
            if not any(s == "experiment_family_level" for s in originals):
                best_scope = "experiment_or_family_level"
    ev_type = str(rows[0].get("binding_evidence_type", "") or "")
    ev_strength = str(rows[0].get("binding_evidence_strength", "") or "")
    for r in rows:
        if str(r.get("evidence_scope", "") or "") in {
            best_scope,
            "experiment_or_family_level" if best_scope == "experiment_family_level" else best_scope,
        }:
            ev_type = str(r.get("binding_evidence_type", "") or "")
            ev_strength = str(r.get("binding_evidence_strength", "") or "")
            break
    return best_scope, ev_type, ev_strength


def consolidate_accepted_pairs(
    accepted: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Collapse exact effective_sequence + target-key pairs; retain provenance IDs."""
    if accepted.empty:
        return pd.DataFrame(columns=SELECTED_CORE_COLUMNS + SELECTED_EXTRA_COLUMNS), []

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for _, row in accepted.iterrows():
        seq, seq_corr = derive_effective_sequence(row)
        target, tgt_corr = derive_effective_target(row)
        display = preferred_display_name(target, fallback=target) if target else target
        key = accepted_pair_key(seq, display)
        payload = row.to_dict()
        payload["_effective_sequence"] = seq
        payload["_effective_target"] = display
        payload["_sequence_corrected"] = seq_corr
        payload["_target_corrected"] = tgt_corr
        payload["_pair_key"] = key
        buckets[key].append(payload)

    selected_rows: list[dict[str, Any]] = []
    consolidation_events: list[dict[str, Any]] = []

    for key, rows in buckets.items():
        seq = rows[0]["_effective_sequence"]
        # Prefer a manually corrected display, else preferred_display_name already applied
        target = rows[0]["_effective_target"]
        for r in rows:
            if r["_target_corrected"]:
                target = r["_effective_target"]
                break

        unit_ids = sorted({str(r.get("review_unit_id", "")).strip() for r in rows if str(r.get("review_unit_id", "")).strip()})
        group_ids: list[str] = []
        for r in rows:
            group_ids.extend(_split_pipe(r.get("experiment_group_ids", "")))
            gid = str(r.get("experiment_group_id", "") or "").strip()
            if gid:
                group_ids.append(gid)
        group_ids = list(dict.fromkeys(group_ids))

        accessions: list[str] = []
        for r in rows:
            accessions.extend(_split_pipe(r.get("accessions", "")))
        accessions = list(dict.fromkeys(sorted(set(accessions))))

        regions = _join_pipe(r.get("target_region", "") for r in rows)
        types = [str(r.get("target_type", "") or "").strip() for r in rows if str(r.get("target_type", "") or "").strip()]
        ttype = Counter(types).most_common(1)[0][0] if types else ""

        evidence_scope, ev_type, ev_strength = _pick_evidence_fields(rows)
        fam_ids = _join_pipe(r.get("near_duplicate_family_id", "") for r in rows)
        titles = join_unique(r.get("representative_title", "") for r in rows)
        notes = join_unique(r.get("manual_notes", "") for r in rows)
        flags = _join_pipe(
            f
            for r in rows
            for f in str(r.get("automatic_concern_flags", "") or "").replace(";", "|").split("|")
            if f.strip()
        )

        seq_corr_any = any(r["_sequence_corrected"] for r in rows)
        tgt_corr_any = any(r["_target_corrected"] for r in rows)
        manual_seq = ""
        if seq_corr_any:
            for r in rows:
                if r["_sequence_corrected"]:
                    manual_seq = normalize_effective_sequence(
                        str(r.get("manual_sequence_corrected", "") or "")
                    )
                    break
        manual_tgt = ""
        if tgt_corr_any:
            for r in rows:
                if r["_target_corrected"]:
                    manual_tgt = str(r.get("manual_target_corrected", "") or "").strip()
                    break

        originals_seq = _join_pipe(
            normalize_effective_sequence(str(r.get("rna_sequence", "") or "")) for r in rows
        )
        originals_tgt = join_unique(str(r.get("target_display_name", "") or "") for r in rows)

        allow_amb = "1" if any(
            (validate_manual_include(r.get("allow_ambiguous_include", "")) or "") == "1"
            for r in rows
        ) else ""

        quality = join_unique(r.get("sequence_quality_status", "") for r in rows)
        length_status = join_unique(r.get("length_status", "") for r in rows)
        sel_ev = join_unique(
            r.get("selection_evidence_summary", r.get("selection_evidence", ""))
            for r in rows
        )
        refs = join_unique(r.get("references", r.get("reference", "")) for r in rows)
        dois = _join_pipe(r.get("doi_values", "") for r in rows)
        pmids = _join_pipe(r.get("pubmed_values", "") for r in rows)

        selected_rows.append(
            {
                "sequence": seq,
                "target": target,
                "target_region": regions,
                "target_type": ttype,
                "sequence_length": str(len(seq)),
                "review_unit_id": unit_ids[0] if unit_ids else "",
                "review_unit_ids": "|".join(unit_ids),
                "experiment_group_id": group_ids[0] if group_ids else "",
                "experiment_group_ids": "|".join(group_ids),
                "accession_count": str(len(accessions)),
                "accessions": "|".join(accessions),
                "near_duplicate_family_id": fam_ids,
                "binding_evidence_type": ev_type,
                "binding_evidence_strength": ev_strength,
                "evidence_scope": evidence_scope,
                "representative_title": titles,
                "manual_target_corrected": manual_tgt,
                "manual_sequence_corrected": manual_seq,
                "manual_notes": notes,
                "automatic_concern_flags": flags,
                "source_database": "ENA",
                "sequence_original": originals_seq,
                "target_original": originals_tgt,
                "sequence_corrected_applied": "1" if seq_corr_any else "0",
                "target_corrected_applied": "1" if tgt_corr_any else "0",
                "allow_ambiguous_include": allow_amb,
                "sequence_quality_status": quality,
                "length_status": length_status,
                "selection_evidence_summary": sel_ev,
                "references": refs,
                "doi_values": dois,
                "pubmed_values": pmids,
                "genuine_target_conflict": "1"
                if any(str(r.get("genuine_target_conflict", "")) == "1" for r in rows)
                else "0",
                "unresolved_target": "1"
                if any(str(r.get("unresolved_target", "")) == "1" for r in rows)
                else "0",
                "near_duplicate_family_size": join_unique(
                    r.get("near_duplicate_family_size", "") for r in rows
                ),
                "consolidated_from_n_units": str(len(rows)),
                "target_comparison_key": key[1],
            }
        )

        if len(rows) > 1:
            consolidation_events.append(
                {
                    "target_comparison_key": key[1],
                    "sequence_length": len(seq),
                    "n_units": len(rows),
                    "review_unit_ids": "|".join(unit_ids),
                    "accessions": "|".join(accessions),
                    "experiment_group_ids": "|".join(group_ids),
                }
            )

    selected = pd.DataFrame(selected_rows)
    if not selected.empty:
        ordered = [c for c in SELECTED_CORE_COLUMNS + SELECTED_EXTRA_COLUMNS if c in selected.columns]
        extras = [c for c in selected.columns if c not in ordered]
        selected = selected[ordered + extras]
        selected["_len"] = pd.to_numeric(selected["sequence_length"], errors="coerce").fillna(0)
        selected = selected.sort_values(
            by=["target", "_len", "sequence"],
            kind="mergesort",
        ).drop(columns=["_len"]).reset_index(drop=True)
    return selected, consolidation_events


def build_selected_provenance(
    selected: pd.DataFrame,
    provenance: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str], int]:
    """Join accepted review units to sequence provenance; one row per unit/accession."""
    if selected.empty:
        return pd.DataFrame(), [], 0

    accepted_units: list[str] = []
    for _, row in selected.iterrows():
        accepted_units.extend(_split_pipe(row.get("review_unit_ids", "")))
        uid = str(row.get("review_unit_id", "") or "").strip()
        if uid:
            accepted_units.append(uid)
    accepted_units = list(dict.fromkeys(accepted_units))
    accepted_set = set(accepted_units)

    if provenance.empty or "review_unit_id" not in provenance.columns:
        return pd.DataFrame(), accepted_units, 0

    matched = provenance[provenance["review_unit_id"].astype(str).isin(accepted_set)].copy()
    matched_units = set(matched["review_unit_id"].astype(str))
    missing = sorted(accepted_set - matched_units)
    return matched, missing, len(matched)


def write_apply_sequence_qc_report(
    path: Path,
    *,
    total_rows: int,
    accepted_before: int,
    selected: pd.DataFrame,
    rejected: pd.DataFrame,
    unreviewed: pd.DataFrame,
    invalid_decision_count: int,
    consolidation_events: list[dict[str, Any]],
    unresolved_duplicate_errors: list[str],
    provenance_matched_units: int,
    provenance_rows: int,
    provenance_missing: list[str],
    output_counts: dict[str, int],
) -> None:
    reviewed = accepted_before + len(rejected)
    pct = (100.0 * reviewed / total_rows) if total_rows else 0.0

    n_seq_corr = int((selected.get("sequence_corrected_applied", pd.Series(dtype=str)) == "1").sum()) if not selected.empty else 0
    n_tgt_corr = int((selected.get("target_corrected_applied", pd.Series(dtype=str)) == "1").sum()) if not selected.empty else 0
    n_amb = int((selected.get("allow_ambiguous_include", pd.Series(dtype=str)) == "1").sum()) if not selected.empty else 0
    under20 = 0
    promoter_n = 0
    conflict_n = 0
    concern_n = 0
    if not selected.empty:
        under20 = int(pd.to_numeric(selected["sequence_length"], errors="coerce").fillna(0).lt(20).sum())
        promoter_n = int(
            selected["automatic_concern_flags"].fillna("").astype(str).str.contains("promoter", case=False).sum()
        )
        if "genuine_target_conflict" in selected.columns:
            conflict_n = int((selected["genuine_target_conflict"] == "1").sum())
        concern_n = int((selected["automatic_concern_flags"].fillna("").astype(str).str.strip() != "").sum())

    unique_seqs = int(selected["sequence"].nunique()) if not selected.empty else 0
    unique_tgts = int(selected["target"].nunique()) if not selected.empty else 0
    group_ids: set[str] = set()
    accession_ids: set[str] = set()
    if not selected.empty:
        for _, r in selected.iterrows():
            group_ids.update(_split_pipe(r.get("experiment_group_ids", "")))
            accession_ids.update(_split_pipe(r.get("accessions", "")))

    def _count_table(series: pd.Series, title: str) -> list[str]:
        lines = [f"### {title}", "", "| value | count |", "|---|---:|"]
        if series.empty:
            lines.append("| _(none)_ | 0 |")
        else:
            for val, cnt in series.fillna("").astype(str).value_counts().items():
                label = val if val else "_(blank)_"
                lines.append(f"| {label.replace('|', '/')} | {cnt} |")
        lines.append("")
        return lines

    length_bins = Counter()
    if not selected.empty:
        for length in pd.to_numeric(selected["sequence_length"], errors="coerce").fillna(0).astype(int):
            if length < 20:
                length_bins["under_20"] += 1
            elif length <= 120:
                length_bins["20_to_120"] += 1
            elif length <= 200:
                length_bins["121_to_200"] += 1
            elif length <= 500:
                length_bins["201_to_500"] += 1
            else:
                length_bins["over_500"] += 1

    excl = rejected["manual_exclusion_reason"] if not rejected.empty and "manual_exclusion_reason" in rejected.columns else pd.Series(dtype=str)
    missing_reason = int((excl.fillna("").astype(str).str.strip() == "").sum()) if not rejected.empty else 0

    lines = [
        "# ENA apply-sequence-review QC report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Accepted unique RNA aptamer sequence – named protein target pairs after",
        "exact consolidation of sequence-level clerical decisions.",
        "",
        "## Review decisions",
        "",
        "| metric | count |",
        "|---|---:|",
        f"| total sequence-review rows | {total_rows} |",
        f"| accepted rows before exact consolidation | {accepted_before} |",
        f"| final accepted unique sequence–target pairs | {len(selected)} |",
        f"| rejected rows | {len(rejected)} |",
        f"| unreviewed rows | {len(unreviewed)} |",
        f"| percentage reviewed | {pct:.1f}% |",
        f"| rows with invalid decisions | {invalid_decision_count} |",
        "",
        "## Accepted corpus summary",
        "",
        "| metric | count |",
        "|---|---:|",
        f"| unique accepted sequences | {unique_seqs} |",
        f"| unique accepted targets | {unique_tgts} |",
        f"| accepted experiment groups | {len(group_ids)} |",
        f"| accepted accession count | {len(accession_ids)} |",
        "",
    ]
    if not selected.empty:
        lines.extend(_count_table(selected["target"], "Counts by target"))
        lines.extend(_count_table(selected["target_type"], "Counts by target type"))
        lines.extend(_count_table(selected["evidence_scope"], "Counts by evidence scope"))
        lines.extend(
            _count_table(selected["binding_evidence_strength"], "Counts by binding-evidence strength")
        )
        lines.extend(
            _count_table(selected["sequence_quality_status"], "Counts by sequence-quality status")
        )
    lines.extend(
        [
            "### Accepted sequence-length distribution",
            "",
            "| bin | count |",
            "|---|---:|",
        ]
    )
    for label in ["under_20", "20_to_120", "121_to_200", "201_to_500", "over_500"]:
        lines.append(f"| {label} | {length_bins.get(label, 0)} |")
    lines.append("")

    lines.extend(
        [
            "## Manual corrections",
            "",
            "| metric | count |",
            "|---|---:|",
            f"| manually corrected targets | {n_tgt_corr} |",
            f"| manually corrected sequences | {n_seq_corr} |",
            f"| ambiguous sequences accepted through explicit override | {n_amb} |",
            f"| accepted sequences under 20 nt | {under20} |",
            f"| accepted promoter/template-flagged records | {promoter_n} |",
            f"| accepted records with target-conflict flags | {conflict_n} |",
            f"| accepted rows carrying automatic concern flags | {concern_n} |",
            "",
            "## Duplicate handling",
            "",
            "| metric | count |",
            "|---|---:|",
            f"| duplicate accepted sequence–target pairs found | {len(consolidation_events)} |",
            f"| number consolidated | {len(consolidation_events)} |",
            f"| unresolved duplicate errors | {len(unresolved_duplicate_errors)} |",
            "",
        ]
    )
    if consolidation_events:
        lines.extend(
            [
                "| target_key | n_units | review_unit_ids | accessions |",
                "|---|---:|---|---|",
            ]
        )
        for ev in consolidation_events:
            lines.append(
                f"| {ev['target_comparison_key']} | {ev['n_units']} | "
                f"{ev['review_unit_ids']} | {ev['accessions']} |"
            )
        lines.append("")
    if unresolved_duplicate_errors:
        lines.append("Unresolved duplicate errors:")
        lines.append("")
        for err in unresolved_duplicate_errors:
            lines.append(f"- {err}")
        lines.append("")

    lines.extend(
        [
            "## Rejections",
            "",
        ]
    )
    lines.extend(_count_table(excl, "Counts by manual_exclusion_reason"))
    lines.extend(
        [
            f"Rejected rows lacking an exclusion reason: **{missing_reason}**",
            "",
            "## Provenance",
            "",
            "| metric | count |",
            "|---|---:|",
            f"| accepted review units matched to provenance | {provenance_matched_units} |",
            f"| accepted accessions exported (provenance rows) | {provenance_rows} |",
            f"| missing or unmatched provenance review units | {len(provenance_missing)} |",
            "",
        ]
    )
    if provenance_missing:
        lines.append("Unmatched accepted review_unit_id values:")
        lines.append("")
        for uid in provenance_missing[:50]:
            lines.append(f"- {uid}")
        if len(provenance_missing) > 50:
            lines.append(f"- … and {len(provenance_missing) - 50} more")
        lines.append("")

    lines.extend(
        [
            "## Outputs",
            "",
            "| file | rows |",
            "|---|---:|",
        ]
    )
    for name, count in output_counts.items():
        lines.append(f"| {name} | {count} |")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_apply_sequence_review(
    sequence_review_file: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
    provenance_file: Path | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "ena_apply_sequence_review_log.txt"

    existing = [output_dir / name for name in APPLY_SEQUENCE_OUTPUT_FILES if (output_dir / name).exists()]
    # Allow rewriting the log itself when present; block data products without --overwrite
    blocking = [p for p in existing if p.name != "ena_apply_sequence_review_log.txt"]
    if blocking and not overwrite:
        raise FileExistsError(
            "Outputs already exist; pass --overwrite to replace: "
            + ", ".join(p.name for p in blocking)
        )

    logger.info("Input sequence review file: %s", sequence_review_file)
    logger.info("Output directory: %s", output_dir)

    if not sequence_review_file.exists():
        raise FileNotFoundError(sequence_review_file)

    df = _read_csv(sequence_review_file)
    errors = validate_sequence_review_frame(df)
    if errors:
        raise ReviewValidationError(
            "sequence review validation failed:\n- " + "\n- ".join(errors)
        )

    work = df.copy()
    work["manual_include"] = [
        validate_manual_include(v) or "" for v in work["manual_include"].tolist()
    ]
    work["allow_ambiguous_include"] = [
        validate_manual_include(v) or "" for v in work["allow_ambiguous_include"].tolist()
    ]

    accepted = work[work["manual_include"] == "1"].copy()
    rejected = work[work["manual_include"] == "0"].copy()
    unreviewed = work[work["manual_include"] == ""].copy()

    accepted_errors = validate_accepted_sequence_rows(accepted)
    if accepted_errors:
        raise ReviewValidationError(
            "accepted-row validation failed:\n- " + "\n- ".join(accepted_errors)
        )

    selected, consolidation_events = consolidate_accepted_pairs(accepted)
    unresolved_duplicate_errors: list[str] = []

    prov_path = provenance_file or (output_dir / "ena_sequence_review_provenance.csv")
    if not selected.empty and not prov_path.exists():
        raise FileNotFoundError(
            f"Required provenance file missing: {prov_path}. "
            "Run apply-group-review before apply-sequence-review."
        )
    if prov_path.exists():
        try:
            provenance = _read_csv(prov_path)
        except pd.errors.EmptyDataError as exc:
            raise ReviewValidationError(
                f"provenance file is empty or unreadable: {prov_path}"
            ) from exc
    else:
        provenance = pd.DataFrame()
    selected_prov, provenance_missing, provenance_rows = build_selected_provenance(
        selected, provenance
    )
    if not selected.empty and provenance_missing:
        logger.warning(
            "Missing provenance for %d accepted review unit(s): %s",
            len(provenance_missing),
            ", ".join(provenance_missing[:20]),
        )

    accepted_units = set()
    if not selected.empty:
        for _, row in selected.iterrows():
            accepted_units.update(_split_pipe(row.get("review_unit_ids", "")))
            uid = str(row.get("review_unit_id", "") or "").strip()
            if uid:
                accepted_units.add(uid)
    provenance_matched_units = len(accepted_units) - len(provenance_missing)

    _write_csv(selected, output_dir / "ena_selected_after_manual_review.csv", excel=True)
    _write_csv(rejected, output_dir / "ena_rejected_after_manual_review.csv", excel=True)
    _write_csv(unreviewed, output_dir / "ena_unreviewed_after_manual_review.csv", excel=True)
    _write_csv(selected_prov, output_dir / "ena_selected_sequence_provenance.csv")

    output_counts = {
        "ena_selected_after_manual_review.csv": len(selected),
        "ena_rejected_after_manual_review.csv": len(rejected),
        "ena_unreviewed_after_manual_review.csv": len(unreviewed),
        "ena_selected_sequence_provenance.csv": len(selected_prov),
    }
    write_apply_sequence_qc_report(
        output_dir / "ena_apply_sequence_review_qc_report.md",
        total_rows=len(work),
        accepted_before=len(accepted),
        selected=selected,
        rejected=rejected,
        unreviewed=unreviewed,
        invalid_decision_count=0,
        consolidation_events=consolidation_events,
        unresolved_duplicate_errors=unresolved_duplicate_errors,
        provenance_matched_units=provenance_matched_units,
        provenance_rows=provenance_rows,
        provenance_missing=provenance_missing,
        output_counts=output_counts,
    )
    output_counts["ena_apply_sequence_review_qc_report.md"] = 1

    summary = {
        "total_rows": len(work),
        "accepted_before_consolidation": len(accepted),
        "accepted_unique_pairs": len(selected),
        "rejected": len(rejected),
        "unreviewed": len(unreviewed),
        "target_corrections": int(
            (selected.get("target_corrected_applied", pd.Series(dtype=str)) == "1").sum()
        )
        if not selected.empty
        else 0,
        "sequence_corrections": int(
            (selected.get("sequence_corrected_applied", pd.Series(dtype=str)) == "1").sum()
        )
        if not selected.empty
        else 0,
        "ambiguous_overrides": int(
            (selected.get("allow_ambiguous_include", pd.Series(dtype=str)) == "1").sum()
        )
        if not selected.empty
        else 0,
        "duplicate_consolidations": len(consolidation_events),
        "provenance_rows": provenance_rows,
        "provenance_missing": len(provenance_missing),
        "output_dir": str(output_dir),
    }
    logger.info("Decision counts: accepted=%d rejected=%d unreviewed=%d", len(accepted), len(rejected), len(unreviewed))
    logger.info(
        "Duplicate handling: %d exact pair(s) consolidated",
        len(consolidation_events),
    )
    logger.info(
        "Provenance joins: %d rows for %d units (%d unmatched)",
        provenance_rows,
        provenance_matched_units,
        len(provenance_missing),
    )
    for name, count in output_counts.items():
        logger.info("Wrote %s (%s rows)", output_dir / name, count)
    logger.info("Apply-sequence-review completed successfully: %s", summary)

    # Ensure dedicated processing log exists even if logging was configured elsewhere
    if not log_path.exists():
        log_path.write_text(
            "\n".join(
                [
                    f"input={sequence_review_file}",
                    f"output_dir={output_dir}",
                    f"summary={summary}",
                    "status=success",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--log-level", default="INFO")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build-review", help="Repair targets/evidence; write group template")
    b.add_argument("--review-dir", type=Path, default=None)
    b.add_argument("--candidate-dir", type=Path, default=None)
    b.add_argument("--output-dir", type=Path, default=None)
    b.add_argument("--overwrite", action="store_true")

    a = sub.add_parser(
        "apply-group-review",
        help="Apply group 0/1 decisions; write sequence template for retained groups",
    )
    a.add_argument("--group-review-file", type=Path, required=True)
    a.add_argument("--output-dir", type=Path, default=None)

    s = sub.add_parser(
        "apply-sequence-review",
        help="Apply sequence-level 0/1 decisions; export accepted/rejected RNA–target pairs",
    )
    s.add_argument("--sequence-review-file", type=Path, required=True)
    s.add_argument("--output-dir", type=Path, default=None)
    s.add_argument("--overwrite", action="store_true")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_dir = resolve_dir(getattr(args, "output_dir", None), DEFAULT_OUTPUT_DIRS)
    if args.command == "apply-sequence-review":
        log_path = output_dir / "ena_apply_sequence_review_log.txt"
    else:
        log_path = output_dir / "ena_review_v2_log.txt"
    configure_logging(log_path, args.log_level)

    try:
        if args.command == "build-review":
            review_dir = resolve_dir(args.review_dir, DEFAULT_REVIEW_DIRS)
            cand = resolve_dir(args.candidate_dir, DEFAULT_CANDIDATE_DIRS)
            if not cand.exists():
                cand = None
            run_build_review(
                review_dir=review_dir,
                candidate_dir=cand,
                output_dir=output_dir,
                overwrite=args.overwrite,
            )
        elif args.command == "apply-group-review":
            run_apply_group_review(
                group_review_file=args.group_review_file,
                output_dir=output_dir,
            )
        elif args.command == "apply-sequence-review":
            run_apply_sequence_review(
                sequence_review_file=args.sequence_review_file,
                output_dir=output_dir,
                overwrite=args.overwrite,
            )
        else:
            parser.error(f"unknown command {args.command}")
            return 2
    except (FileNotFoundError, FileExistsError, ReviewValidationError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

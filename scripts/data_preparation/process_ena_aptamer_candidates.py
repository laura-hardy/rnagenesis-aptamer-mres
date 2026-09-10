#!/usr/bin/env python3
"""Process ENA inspection outputs into conservative aptamer–protein candidate tables.

This is a triage / evidence-assembly stage. It does **not** write a final
fine-tuning corpus, does not auto-trim promoters/primers, and does not call
external literature APIs.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ena_candidate_rules import (
    NON_CORE_TARGET_TYPES,
    PROTEIN_COMPATIBLE_TARGET_TYPES,
    EvidenceItem,
    assess_binding,
    assess_rna_identity,
    assess_selection,
    assess_sequence_role,
    assess_target,
    assign_candidate_tier,
    exclusion_category_for,
    extract_feature_sequence,
    recommended_review_action,
    rna_normalize_sequence,
    stable_group_id,
)
from ena_candidate_rules import (  # noqa: E402  — shared helpers
    _pipe_split,
    _truthy,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INSPECTION_DIR = REPO_ROOT / "data" / "raw" / "ena" / "inspection"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "raw" / "ena" / "candidates"
DEFAULT_EMBL_CANDIDATES = [
    REPO_ROOT / "data" / "raw" / "ENA" / "ena_embl_20260720-0853.txt",
    REPO_ROOT / "data" / "raw" / "ena" / "ena_embl_20260720-0853.txt",
]

REQUIRED_INSPECTION_FILES = [
    "ena_record_inventory.csv",
    "ena_record_class_signals.csv",
    "ena_feature_table_long.csv",
    "ena_reference_summary.csv",
    "ena_duplicate_summary.csv",
    "ena_sequence_diagnostics.csv",
]

logger = logging.getLogger("process_ena_aptamer_candidates")


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


def load_inspection_tables(inspection_dir: Path) -> dict[str, pd.DataFrame]:
    missing = [f for f in REQUIRED_INSPECTION_FILES if not (inspection_dir / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing inspection files in {inspection_dir}: {', '.join(missing)}"
        )
    tables = {name: _read_csv(inspection_dir / name) for name in REQUIRED_INSPECTION_FILES}
    offsets = inspection_dir / "ena_record_offsets.csv"
    if offsets.exists():
        tables["ena_record_offsets.csv"] = _read_csv(offsets)
    return tables


def resolve_embl_path(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.exists() else None
    for cand in DEFAULT_EMBL_CANDIDATES:
        if cand.exists():
            return cand
    return None


def load_optional_external_indexes(repo_root: Path) -> dict[str, Any]:
    """Build exact-match indexes from local aptamer datasets if present."""
    indexes: dict[str, Any] = {
        "by_seq": {},
        "by_rna_seq": {},
        "by_doi": {},
        "by_pmid": {},
    }
    aptabase = repo_root / "data" / "raw" / "aptabase" / "aptabase_cleaned.csv"
    if not aptabase.exists():
        logger.info("Optional AptaBase cleaned file not found; skipping external matches")
        return indexes
    try:
        df = pd.read_csv(aptabase, dtype=str).fillna("")
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not read AptaBase cleaned file: %s", exc)
        return indexes

    for _, row in df.iterrows():
        seq = str(row.get("sequence_clean", "") or "").upper().replace(" ", "")
        target = str(row.get("target_specific", "") or row.get("target_general", "") or "")
        doi = str(row.get("doi", "") or "").strip().lower()
        pmid = str(row.get("pmid", "") or "").strip()
        payload = {
            "source": "aptabase_cleaned",
            "target": target,
            "sequence": seq,
        }
        if seq:
            indexes["by_seq"].setdefault(seq, payload)
            indexes["by_rna_seq"].setdefault(rna_normalize_sequence(seq), payload)
        if doi and doi.lower() not in {"nan", "none"}:
            indexes["by_doi"].setdefault(doi, payload)
        if pmid and pmid.lower() not in {"nan", "none"}:
            indexes["by_pmid"].setdefault(pmid, payload)
    logger.info(
        "Loaded optional external indexes: seq=%d doi=%d pmid=%d",
        len(indexes["by_seq"]),
        len(indexes["by_doi"]),
        len(indexes["by_pmid"]),
    )
    return indexes


# ---------------------------------------------------------------------------
# Merge working table
# ---------------------------------------------------------------------------


def build_working_table(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    inv = tables["ena_record_inventory.csv"].copy()
    seq = tables["ena_sequence_diagnostics.csv"][
        ["accession", "sequence_deposited", "sequence_alphabet", "contains_t7_promoter_like_motif",
         "t7_promoter_start", "t7_promoter_match", "t7_promoter_position", "discrepancies"]
    ].copy()
    if "sequence_alphabet" not in inv.columns:
        seq_keep = seq[["accession", "sequence_deposited", "sequence_alphabet"]]
    else:
        seq_keep = seq[["accession", "sequence_deposited"]]

    df = inv.merge(seq_keep, on="accession", how="left")
    if "sequence_deposited" not in df.columns:
        raise ValueError("sequence_deposited missing after merge")
    df["sequence_deposited"] = df["sequence_deposited"].fillna("")
    if "reported_length" in df.columns:
        length_source = df["reported_length"]
    else:
        length_source = pd.Series(0, index=df.index, dtype="int64")
    df["record_length"] = (
        pd.to_numeric(length_source, errors="coerce").fillna(0).astype(int)
    )
    return df


def build_feature_lookup(feature_long: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Choose the best non-source aptamer-related feature per accession, if any."""
    if feature_long.empty:
        return {}
    fl = feature_long.copy()
    fl = fl[fl["feature_key"].str.lower() != "source"]
    if fl.empty:
        return {}

    preferred_keys = {"ncrna", "misc_rna", "misc_feature", "regulatory", "primer_bind"}
    lookup: dict[str, dict[str, Any]] = {}
    for acc, grp in fl.groupby("accession"):
        feats = grp.drop_duplicates(subset=["feature_index"])
        scored = []
        for _, row in feats.iterrows():
            key = str(row.get("feature_key", "")).lower()
            score = 0
            if key in preferred_keys:
                score += 5
            if key == "ncrna":
                score += 3
            try:
                length = int(float(row.get("feature_length") or 0))
            except ValueError:
                length = 0
            score += min(length, 200) / 200.0
            is_comp = _truthy(row.get("feature_is_complement"))
            scored.append((score, row, is_comp, length))
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0]
        row = best[1]
        lookup[str(acc)] = {
            "feature_key": row.get("feature_key", ""),
            "feature_start": row.get("feature_start", ""),
            "feature_end": row.get("feature_end", ""),
            "feature_length": best[3],
            "is_complement": best[2],
            "feature_is_full_record": _truthy(row.get("feature_is_full_record")),
            "feature_location_raw": row.get("feature_location_raw", ""),
        }
    return lookup


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def _common_or_mixed(values: list[str]) -> str:
    cleaned = [v for v in values if v]
    if not cleaned:
        return ""
    uniq = sorted(set(cleaned))
    if len(uniq) == 1:
        return uniq[0]
    if len(uniq) <= 3:
        return "MIXED:" + " | ".join(uniq)
    return f"MIXED:{len(uniq)}_values"


def _first_title(reference_titles: str) -> str:
    parts = _pipe_split(reference_titles)
    return parts[0] if parts else ""


def assign_group_ids(df: pd.DataFrame, dup_df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["exact_sequence_group"] = ""
    out["rna_normalized_sequence_group"] = ""
    out["reverse_complement_group"] = ""
    out["reference_group"] = ""
    out["description_group"] = ""
    out["candidate_experiment_group"] = ""

    # Exact sequence from duplicate summary + singleton keys
    exact_map: dict[str, str] = {}
    rc_map: dict[str, str] = {}
    for _, row in dup_df.iterrows():
        dtype = row.get("duplicate_type", "")
        accs = str(row.get("accessions", "")).split("|")
        gid = stable_group_id(dtype if dtype else "dup", str(row.get("group_key", "")))
        if dtype == "exact_sequence":
            for a in accs:
                if a:
                    exact_map[a] = gid
        elif dtype == "reverse_complement":
            for a in accs:
                if a:
                    rc_map[a] = gid

    rna_groups: dict[str, str] = {}
    desc_groups: dict[str, str] = {}
    ref_groups: dict[str, str] = {}

    for idx, row in out.iterrows():
        acc = row["accession"]
        seq = str(row.get("sequence_deposited", "") or "")
        if acc in exact_map:
            out.at[idx, "exact_sequence_group"] = exact_map[acc]
        elif seq:
            out.at[idx, "exact_sequence_group"] = stable_group_id("exact_sequence", seq.upper())
        if acc in rc_map:
            out.at[idx, "reverse_complement_group"] = rc_map[acc]

        rna_seq = rna_normalize_sequence(seq) if seq else ""
        if rna_seq:
            if rna_seq not in rna_groups:
                rna_groups[rna_seq] = stable_group_id("rna_norm", rna_seq)
            out.at[idx, "rna_normalized_sequence_group"] = rna_groups[rna_seq]

        desc = str(row.get("description", "") or "")
        if desc:
            if desc not in desc_groups:
                desc_groups[desc] = stable_group_id("description", desc)
            out.at[idx, "description_group"] = desc_groups[desc]

        title = _first_title(str(row.get("reference_titles", "") or ""))
        doi = _pipe_split(row.get("doi_values", ""))
        pmid = _pipe_split(row.get("pubmed_values", ""))
        ref_key = ""
        if doi:
            ref_key = "DOI:" + doi[0].lower()
        elif pmid:
            ref_key = "PMID:" + pmid[0]
        elif title:
            ref_key = "TITLE:" + title
        if ref_key:
            if ref_key not in ref_groups:
                ref_groups[ref_key] = stable_group_id("reference", ref_key)
            out.at[idx, "reference_group"] = ref_groups[ref_key]

        # Experiment group: prefer DOI/PMID, else shared title, else patent family.
        # Non-patent records without publication linkage stay accession-singleton here;
        # shared free-text descriptions are already captured by description_group.
        if ref_key.startswith("DOI:") or ref_key.startswith("PMID:"):
            exp_key = ref_key
        elif title:
            exp_key = "TITLE:" + title
        else:
            patent_match = re.match(
                r"(?i)^((?:WO|US|EP|JP|KR|CN)\s*\d+[^:/]*)(?:-[A-Z])?(?:/\d+)?:\s*(.*)$",
                desc,
            )
            if patent_match:
                exp_key = f"PATENT:{patent_match.group(1)}: {patent_match.group(2).strip()}"
            else:
                exp_key = f"ACC:{acc}"
        out.at[idx, "candidate_experiment_group"] = stable_group_id("experiment", exp_key)

    return out


GROUP_TABLE_COLUMNS = [
    "group_id",
    "group_type",
    "member_count",
    "accessions",
    "common_description",
    "common_reference",
    "common_target_text",
    "common_sequence_length",
    "sequence_variation_summary",
    "selection_evidence_summary",
    "protein_target_evidence_summary",
    "representative_accession",
    "group_review_priority",
    "group_notes",
]


def build_groups_table(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_cols = [
        ("exact_sequence", "exact_sequence_group"),
        ("rna_normalized_sequence", "rna_normalized_sequence_group"),
        ("reverse_complement", "reverse_complement_group"),
        ("reference", "reference_group"),
        ("description", "description_group"),
        ("candidate_experiment", "candidate_experiment_group"),
    ]
    for gtype, col in group_cols:
        for gid, grp in df[df[col] != ""].groupby(col):
            accs = grp["accession"].tolist()
            # Omit singletons to keep the group table reviewable.
            if len(accs) < 2:
                continue
            targets = [t for t in grp.get("target_raw", pd.Series(dtype=str)).astype(str).tolist() if t]
            target_set = sorted(set(targets))
            mols = sorted(set(grp["molecule_type"].astype(str).tolist()))
            organisms = sorted(set(grp["organism"].astype(str).tolist()))
            lengths = sorted({int(x) for x in grp["record_length"].tolist()})
            t7_n = int(grp["contains_t7_promoter_like_motif"].map(_truthy).sum()) if "contains_t7_promoter_like_motif" in grp else 0
            natural_n = int(grp["signal_natural_or_genomic"].map(_truthy).sum()) if "signal_natural_or_genomic" in grp else 0
            synthetic_n = int(
                grp["organism"].astype(str).str.lower().isin(["synthetic construct", "artificial sequences"]).sum()
            )
            notes = []
            if len(target_set) > 1:
                notes.append("conflicting_targets")
            if any("dna" in m.lower() for m in mols) and any("rna" in m.lower() for m in mols):
                notes.append("mixed_dna_rna_molecule_types")
            if natural_n and synthetic_n:
                notes.append("mixed_natural_and_synthetic")
            if t7_n:
                notes.append(f"t7_promoter_like:{t7_n}")
            if len(lengths) > 1:
                notes.append(f"length_range:{min(lengths)}-{max(lengths)}")

            priority = 5
            if gtype == "candidate_experiment" and len(accs) >= 20:
                priority = 1
            elif len(accs) >= 10:
                priority = 2
            elif "conflicting_targets" in notes:
                priority = 1

            rows.append(
                {
                    "group_id": gid,
                    "group_type": gtype,
                    "member_count": len(accs),
                    "accessions": "|".join(accs),
                    "common_description": _common_or_mixed(grp["description"].astype(str).tolist()),
                    "common_reference": _common_or_mixed(
                        [_first_title(t) for t in grp["reference_titles"].astype(str).tolist()]
                    ),
                    "common_target_text": _common_or_mixed(targets) if targets else "",
                    "common_sequence_length": _common_or_mixed([str(x) for x in lengths]),
                    "sequence_variation_summary": (
                        f"unique_deposited_seqs={grp['sequence_deposited'].nunique()}"
                    ),
                    "selection_evidence_summary": _common_or_mixed(
                        grp.get("selection_evidence", pd.Series(dtype=str)).astype(str).tolist()
                    ),
                    "protein_target_evidence_summary": _common_or_mixed(
                        [
                            f"{a}:{b}"
                            for a, b in zip(
                                grp.get("target_raw", pd.Series(dtype=str))
                                .astype(str)
                                .tolist(),
                                grp.get("target_type", pd.Series(dtype=str))
                                .astype(str)
                                .tolist(),
                            )
                            if a
                        ]
                    ),
                    "representative_accession": accs[0],
                    "group_review_priority": priority,
                    "group_notes": ";".join(notes),
                }
            )
    if not rows:
        return pd.DataFrame(columns=GROUP_TABLE_COLUMNS)
    return pd.DataFrame(rows)


def annotate_group_membership(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    group_key = out["exact_sequence_group"].astype(str)
    sizes = out.groupby("exact_sequence_group")["accession"].transform("count")
    # Empty group IDs mean no deposited-sequence grouping; do not treat those
    # records as duplicates of each other.
    out["group_member_count"] = sizes.where(group_key != "", 1).astype(int)
    # representative: first accession lexicographically within exact group
    rep = (
        out.sort_values("accession")
        .groupby("exact_sequence_group")["accession"]
        .transform("first")
    )
    out["representative_of_group"] = (out["accession"] == rep) | (group_key == "")
    out["duplicate_status"] = out["group_member_count"].apply(
        lambda n: "exact_duplicate_member" if int(n) > 1 else "unique_sequence"
    )

    # Conflicts: same exact sequence, different targets
    conflict_accs: set[str] = set()
    for gid, grp in out.groupby("exact_sequence_group"):
        if not gid:
            continue
        targets = sorted(
            {t for t in grp["target_normalized"].astype(str).tolist() if t}
        )
        if len(targets) > 1:
            conflict_accs.update(grp["accession"].tolist())
    out["sequence_target_conflict"] = out["accession"].isin(conflict_accs)
    return out


# ---------------------------------------------------------------------------
# Per-record processing
# ---------------------------------------------------------------------------


def process_record(
    row: dict[str, Any],
    feature_info: dict[str, Any] | None,
    external: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[EvidenceItem]]:
    evidence: list[EvidenceItem] = []
    accession = str(row.get("accession", ""))

    rna = assess_rna_identity(row)
    evidence.extend(rna.evidence)
    target = assess_target(row)
    evidence.extend(target.evidence)
    binding = assess_binding(row, target.fields)
    evidence.extend(binding.evidence)
    selection = assess_selection(row)
    evidence.extend(selection.evidence)
    role = assess_sequence_role(row, rna.fields, feature_info)
    evidence.extend(role.evidence)
    tier = assign_candidate_tier(row, rna.fields, target.fields, binding.fields, selection.fields, role.fields)
    evidence.extend(tier.evidence)

    feat_seq = {
        "feature_sequence_deposited": "",
        "feature_sequence_rna_normalized": "",
        "feature_start": "",
        "feature_end": "",
        "feature_strand": "",
        "feature_sequence_extraction_method": "",
    }
    if feature_info and feature_info.get("feature_start") not in ("", None):
        # Only extract when coordinates look clear and feature is aptamer-related
        key = str(feature_info.get("feature_key", "")).lower()
        if key in {"ncrna", "misc_rna", "misc_feature", "regulatory"}:
            is_full = feature_info.get("feature_is_full_record")
            # Always allow complement extraction; for non-full also extract
            if feature_info.get("is_complement") or not is_full:
                feat_seq = extract_feature_sequence(
                    str(row.get("sequence_deposited", "") or ""),
                    feature_info.get("feature_start"),
                    feature_info.get("feature_end"),
                    bool(feature_info.get("is_complement")),
                )
                if feat_seq["feature_sequence_deposited"]:
                    evidence.append(
                        EvidenceItem(
                            accession=accession,
                            evidence_category="sequence_role",
                            evidence_type="feature_sequence_extracted",
                            source_field="feature_location",
                            source_text=str(feature_info.get("feature_location_raw", "")),
                            normalized_value=feat_seq["feature_sequence_extraction_method"],
                            evidence_strength="moderate",
                            supports_candidate=True,
                            notes=f"start={feat_seq['feature_start']};end={feat_seq['feature_end']}",
                        )
                    )

    warnings = []
    pw = str(row.get("parse_warnings", "") or "")
    if pw:
        warnings.append(pw)
    if not row.get("doi_values"):
        warnings.append("missing_DOI")
    if not row.get("pubmed_values"):
        warnings.append("missing_PMID")
    if _truthy(row.get("contains_t7_promoter_like_motif")):
        warnings.append("possible_promoter_present")

    matched = {
        "matched_existing_sequence": False,
        "matched_existing_source": "",
        "matched_existing_target": "",
        "match_type": "",
    }
    if external:
        seq = str(row.get("sequence_deposited", "") or "").upper()
        rna_seq = str(rna.fields.get("sequence_rna_normalized", "") or "")
        hit = None
        match_type = ""
        if seq and seq in external.get("by_seq", {}):
            hit = external["by_seq"][seq]
            match_type = "exact_deposited_sequence"
        elif rna_seq and rna_seq in external.get("by_rna_seq", {}):
            hit = external["by_rna_seq"][rna_seq]
            match_type = "exact_rna_normalized_sequence"
        else:
            for d in _pipe_split(row.get("doi_values", "")):
                if d.lower() in external.get("by_doi", {}):
                    hit = external["by_doi"][d.lower()]
                    match_type = "exact_DOI"
                    break
            if hit is None:
                for p in _pipe_split(row.get("pubmed_values", "")):
                    if p in external.get("by_pmid", {}):
                        hit = external["by_pmid"][p]
                        match_type = "exact_PMID"
                        break
        if hit:
            matched = {
                "matched_existing_sequence": True,
                "matched_existing_source": hit.get("source", ""),
                "matched_existing_target": hit.get("target", ""),
                "match_type": match_type,
            }

    result = {
        "accession": accession,
        "sequence_version": row.get("sequence_version", ""),
        "description": row.get("description", ""),
        "organism": row.get("organism", ""),
        "molecule_type": row.get("molecule_type", ""),
        "record_length": row.get("record_length", row.get("reported_length", "")),
        "sequence_deposited": row.get("sequence_deposited", ""),
        **rna.fields,
        **{k: target.fields.get(k, "") for k in [
            "target_raw", "target_normalized", "target_type", "target_confidence",
            "target_source", "target_evidence_text",
        ]},
        **binding.fields,
        **role.fields,
        **feat_seq,
        "contains_t7_promoter_like_motif": _truthy(row.get("contains_t7_promoter_like_motif")),
        **selection.fields,
        "doi_values": row.get("doi_values", ""),
        "pubmed_values": row.get("pubmed_values", ""),
        "reference_titles": row.get("reference_titles", ""),
        "exact_sequence_group": row.get("exact_sequence_group", ""),
        "rna_normalized_sequence_group": row.get("rna_normalized_sequence_group", ""),
        "reference_group": row.get("reference_group", ""),
        "candidate_experiment_group": row.get("candidate_experiment_group", ""),
        "description_group": row.get("description_group", ""),
        "reverse_complement_group": row.get("reverse_complement_group", ""),
        "group_member_count": row.get("group_member_count", 1),
        "representative_of_group": row.get("representative_of_group", False),
        "duplicate_status": row.get("duplicate_status", ""),
        "sequence_target_conflict": row.get("sequence_target_conflict", False),
        **tier.fields,
        "parse_warnings": "|".join(warnings),
        "source_file": row.get("source_file", "ena_record_inventory.csv"),
        **matched,
        # carry inspection signals used in grouping notes
        "signal_natural_or_genomic": _truthy(row.get("signal_natural_or_genomic")),
        "signal_riboswitch_related": _truthy(row.get("signal_riboswitch_related")),
        "signal_dna_template_or_promoter": _truthy(row.get("signal_dna_template_or_promoter")),
        "mentions_selex": _truthy(row.get("mentions_selex")),
    }
    return result, evidence


# ---------------------------------------------------------------------------
# Output builders
# ---------------------------------------------------------------------------


CANDIDATE_COLUMNS = [
    "accession", "sequence_version", "description", "organism", "molecule_type",
    "record_length", "sequence_deposited", "sequence_rna_normalized",
    "rna_identity_status", "rna_identity_confidence", "rna_identity_evidence",
    "rna_normalization_applied", "rna_normalization_reason",
    "target_raw", "target_normalized", "target_type", "target_confidence",
    "target_source", "target_evidence_text",
    "binding_evidence_status", "binding_evidence_types", "binding_evidence_strength",
    "binding_evidence_text", "affinity_raw", "affinity_value", "affinity_unit",
    "assay_or_method",
    "sequence_role", "sequence_role_confidence", "sequence_role_evidence",
    "feature_sequence_deposited", "feature_sequence_rna_normalized",
    "feature_start", "feature_end", "feature_strand", "feature_sequence_extraction_method",
    "contains_t7_promoter_like_motif",
    "selection_evidence", "selection_evidence_strength",
    "doi_values", "pubmed_values", "reference_titles",
    "exact_sequence_group", "rna_normalized_sequence_group", "reference_group",
    "candidate_experiment_group", "group_member_count", "representative_of_group",
    "duplicate_status", "sequence_target_conflict",
    "candidate_tier", "candidate_rationale", "manual_review_required",
    "review_priority", "corpus_relevance_status", "parse_warnings", "source_file",
    "matched_existing_sequence", "matched_existing_source", "matched_existing_target",
    "match_type",
]


def build_exclusions(candidates: pd.DataFrame) -> pd.DataFrame:
    mask = candidates["candidate_tier"].isin(
        ["Tier_D_non_core_or_exclude", "Tier_E_insufficient_information"]
    )
    rows = []
    evidence_limit = 200
    for _, row in candidates[mask].iterrows():
        tier_fields = {
            "candidate_tier": row["candidate_tier"],
            "candidate_rationale": row["candidate_rationale"],
        }
        target = {"target_raw": row["target_raw"], "target_type": row["target_type"]}
        role = {"sequence_role": row["sequence_role"]}
        rna = {"rna_identity_status": row["rna_identity_status"]}
        supporting = str(row.get("target_evidence_text", "") or "") or str(
            row.get("binding_evidence_text", "") or ""
        )
        rows.append(
            {
                "accession": row["accession"],
                "candidate_tier": row["candidate_tier"],
                "exclusion_category": exclusion_category_for(tier_fields, target, role, rna),
                "exclusion_reason": row["candidate_rationale"],
                "target_raw": row["target_raw"],
                "target_type": row["target_type"],
                "rna_identity_status": row["rna_identity_status"],
                "sequence_role": row["sequence_role"],
                "binding_evidence_status": row["binding_evidence_status"],
                "supporting_evidence": supporting[:evidence_limit],
                "manual_review_needed": bool(row["manual_review_required"]),
            }
        )
    return pd.DataFrame(rows)


def build_review_queue(candidates: pd.DataFrame, max_records: int | None) -> pd.DataFrame:
    review = candidates[candidates["manual_review_required"].map(_truthy)].copy()
    # Also include large experiment groups' representatives even if not flagged
    large = candidates["group_member_count"].astype(int) >= 20
    review = pd.concat([review, candidates[large]], ignore_index=True).drop_duplicates(subset=["accession"])
    review = review.sort_values(["review_priority", "accession"])
    if max_records is not None:
        review = review.head(max_records)

    rows = []
    for _, row in review.iterrows():
        uncertainty = []
        if row["target_source"] == "reference_title":
            uncertainty.append("target_from_title_only")
        if row["sequence_role"] in {
            "unknown_sequence_role",
            "promoter_plus_rna_template",
            "dna_template_for_rna_aptamer",
            "aptamer_embedded_in_construct",
        }:
            uncertainty.append(f"sequence_role={row['sequence_role']}")
        if not row["doi_values"] and not row["pubmed_values"]:
            uncertainty.append("missing_DOI_PMID")
        if _truthy(row.get("sequence_target_conflict")):
            uncertainty.append("sequence_target_conflict")
        if int(row.get("group_member_count", 1) or 1) >= 20:
            uncertainty.append("bulk_clone_or_experiment_family")
        rows.append(
            {
                "review_priority": row["review_priority"],
                "accession": row["accession"],
                "candidate_group": row["candidate_experiment_group"],
                "candidate_tier": row["candidate_tier"],
                "aptamer_description": row["description"],
                "sequence_deposited": row["sequence_deposited"],
                "sequence_rna_normalized": row["sequence_rna_normalized"],
                "target_raw": row["target_raw"],
                "target_type": row["target_type"],
                "binding_evidence_summary": f"{row['binding_evidence_strength']}:{row['binding_evidence_types']}",
                "selection_evidence_summary": row["selection_evidence"],
                "sequence_role": row["sequence_role"],
                "reference_summary": _first_title(str(row["reference_titles"])),
                "main_uncertainty": ";".join(uncertainty) or row["candidate_rationale"],
                "recommended_review_action": recommended_review_action(
                    str(row["candidate_tier"]),
                    str(row["sequence_role"]),
                    str(row["target_source"]),
                    str(row["binding_evidence_strength"]),
                    bool(_truthy(row.get("sequence_target_conflict"))),
                ),
            }
        )
    return pd.DataFrame(rows)


def build_target_normalization_review(candidates: pd.DataFrame) -> pd.DataFrame:
    mask = (
        (candidates["target_type"] == "unknown")
        | (candidates["target_confidence"].isin(["low", "none"]))
        | (candidates["target_source"] == "reference_title")
    )
    cols = [
        "accession", "target_raw", "target_normalized", "target_type",
        "target_confidence", "target_source", "target_evidence_text",
        "candidate_tier", "description",
    ]
    return candidates.loc[mask, cols].copy()


def build_reference_table(ref_df: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    keep = candidates[["accession", "candidate_tier", "candidate_experiment_group"]]
    merged = ref_df.merge(keep, on="accession", how="left")
    return merged


def write_qc_report(
    path: Path,
    candidates: pd.DataFrame,
    groups: pd.DataFrame,
    review: pd.DataFrame,
) -> None:
    tier_counts = candidates["candidate_tier"].value_counts().to_dict()
    target_counts = candidates["target_type"].value_counts().to_dict()
    binding_strength = candidates["binding_evidence_strength"].value_counts().to_dict()
    role_counts = candidates["sequence_role"].value_counts().to_dict()
    rna_counts = candidates["rna_identity_status"].value_counts().to_dict()

    protein_n = int(candidates["target_type"].isin(PROTEIN_COMPATIBLE_TARGET_TYPES).sum())
    nonprotein_n = int(candidates["target_type"].isin(NON_CORE_TARGET_TYPES | {"peptide"}).sum())
    binding_any = int((candidates["binding_evidence_strength"] != "none").sum())
    affinity_n = int((candidates["affinity_raw"].astype(str).str.len() > 0).sum())
    potential = int((candidates["corpus_relevance_status"] == "potential_rna_protein_pair").sum())
    possible = int((candidates["corpus_relevance_status"] == "possible_rna_protein_pair").sum())

    if groups is None or groups.empty or "group_type" not in groups.columns:
        exp_groups = pd.DataFrame(columns=GROUP_TABLE_COLUMNS)
        exact_groups = pd.DataFrame(columns=GROUP_TABLE_COLUMNS)
    else:
        exp_groups = groups[groups["group_type"] == "candidate_experiment"].sort_values(
            "member_count", ascending=False
        )
        exact_groups = groups[groups["group_type"] == "exact_sequence"].sort_values(
            "member_count", ascending=False
        )
    conflicts = int(candidates["sequence_target_conflict"].map(_truthy).sum())
    unique_seq = candidates["sequence_deposited"].nunique()
    unique_rna = candidates.loc[
        candidates["sequence_rna_normalized"].astype(str).str.len() > 0, "sequence_rna_normalized"
    ].nunique()

    def _md_counts(d: dict) -> str:
        if not d:
            return "_none_\n"
        lines = ["| value | count |", "|---|---:|"]
        for k, v in sorted(d.items(), key=lambda kv: (-kv[1], str(kv[0]))):
            lines.append(f"| {k} | {v} |")
        return "\n".join(lines) + "\n"

    top_a = candidates[candidates["candidate_tier"] == "Tier_A_high_confidence"].head(15)
    strong_unclear = candidates[
        (candidates["binding_evidence_strength"] == "strong")
        & (candidates["sequence_role"].isin([
            "unknown_sequence_role",
            "promoter_plus_rna_template",
            "dna_template_for_rna_aptamer",
            "aptamer_embedded_in_construct",
        ]))
    ].head(15)
    protein_no_sel = candidates[
        candidates["target_type"].isin(PROTEIN_COMPATIBLE_TARGET_TYPES)
        & (candidates["selection_evidence_strength"] == "none")
    ].head(15)

    lines = [
        "# ENA candidate processing QC report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "This report summarises a **provisional triage**. It is not a final corpus.",
        "",
        "## Candidate counts",
        "",
        "| metric | count |",
        "|---|---:|",
        f"| total records assessed | {len(candidates)} |",
        f"| Tier A | {tier_counts.get('Tier_A_high_confidence', 0)} |",
        f"| Tier B | {tier_counts.get('Tier_B_plausible_needs_review', 0)} |",
        f"| Tier C | {tier_counts.get('Tier_C_sequence_role_uncertain', 0)} |",
        f"| Tier D | {tier_counts.get('Tier_D_non_core_or_exclude', 0)} |",
        f"| Tier E | {tier_counts.get('Tier_E_insufficient_information', 0)} |",
        f"| potential RNA–protein pairs | {potential} |",
        f"| possible RNA–protein pairs | {possible} |",
        f"| protein-compatible target records | {protein_n} |",
        f"| non-protein / non-core target records | {nonprotein_n} |",
        f"| records with binding evidence (not none) | {binding_any} |",
        f"| records with quantitative affinity | {affinity_n} |",
        f"| records in manual-review queue | {len(review)} |",
        "",
        "### Tier distribution",
        "",
        _md_counts(tier_counts),
        "## Group structure",
        "",
        f"- candidate experiment groups: **{len(exp_groups)}**",
        f"- exact-sequence duplicate groups (size≥2): **{len(exact_groups)}**",
        f"- unique deposited sequences: **{unique_seq}**",
        f"- unique RNA-normalised sequences: **{unique_rna}**",
        f"- records in same-sequence multiple-target conflicts: **{conflicts}**",
        "",
        "### Largest experiment groups",
        "",
        "| members | representative | notes | common reference / description |",
        "|---:|---|---|---|",
    ]
    for _, g in exp_groups.head(15).iterrows():
        ref = (g["common_reference"] or g["common_description"] or "")[:80]
        lines.append(
            f"| {g['member_count']} | {g['representative_accession']} | {g['group_notes']} | {ref} |"
        )
    lines += [
        "",
        "### Largest exact-sequence groups",
        "",
        "| members | representative | length summary | notes |",
        "|---:|---|---|---|",
    ]
    for _, g in exact_groups.head(10).iterrows():
        lines.append(
            f"| {g['member_count']} | {g['representative_accession']} | {g['common_sequence_length']} | {g['group_notes']} |"
        )

    lines += [
        "",
        "## RNA identity",
        "",
        _md_counts(rna_counts),
        f"- RNA records represented with T (normalisation applied): "
        f"**{int(candidates['rna_normalization_applied'].map(_truthy).sum())}**",
        f"- promoter-bearing (T7-like): "
        f"**{int(candidates['contains_t7_promoter_like_motif'].map(_truthy).sum())}**",
        "",
        "## Target types",
        "",
        _md_counts(target_counts),
        "## Binding evidence",
        "",
        "### By strength",
        "",
        _md_counts(binding_strength),
        "### By status",
        "",
        _md_counts(candidates["binding_evidence_status"].value_counts().to_dict()),
        "## Sequence roles",
        "",
        _md_counts(role_counts),
        "## Review priorities",
        "",
        "### Top high-confidence (Tier A) candidates",
        "",
    ]
    if top_a.empty:
        lines.append("_None assigned._")
    else:
        lines.append("| accession | target | binding | role | rationale |")
        lines.append("|---|---|---|---|---|")
        for _, r in top_a.iterrows():
            lines.append(
                f"| {r['accession']} | {r['target_raw'][:40]} | {r['binding_evidence_strength']} | "
                f"{r['sequence_role']} | {str(r['candidate_rationale'])[:60]} |"
            )

    lines += [
        "",
        "### Strong-binding records with unclear sequence role",
        "",
    ]
    if strong_unclear.empty:
        lines.append("_None._")
    else:
        lines.append("| accession | role | target |")
        lines.append("|---|---|---|")
        for _, r in strong_unclear.iterrows():
            lines.append(f"| {r['accession']} | {r['sequence_role']} | {r['target_raw'][:40]} |")

    lines += [
        "",
        "### Protein-target records lacking selection evidence (sample)",
        "",
    ]
    if protein_no_sel.empty:
        lines.append("_None._")
    else:
        lines.append("| accession | target_type | target_raw | tier |")
        lines.append("|---|---|---|---|")
        for _, r in protein_no_sel.iterrows():
            lines.append(
                f"| {r['accession']} | {r['target_type']} | {str(r['target_raw'])[:40]} | {r['candidate_tier']} |"
            )

    conflict_rows = candidates[candidates["sequence_target_conflict"].map(_truthy)].head(20)
    lines += [
        "",
        "### Records with conflicting targets (same sequence)",
        "",
    ]
    if conflict_rows.empty:
        lines.append("_None._")
    else:
        lines.append("| accession | target | exact_sequence_group |")
        lines.append("|---|---|---|")
        for _, r in conflict_rows.iterrows():
            lines.append(
                f"| {r['accession']} | {r['target_raw'][:40]} | {r['exact_sequence_group']} |"
            )

    lines += [
        "",
        "## Limitations",
        "",
        "- ENA records are not a curated aptamer database.",
        "- Many records lack DOI and PMID.",
        "- Sequence deposits may include templates or flanks; this stage does not trim them.",
        "- Absence of SELEX wording is not proof of no selection.",
        "- Target extraction is often based on free text and may be incomplete or wrong.",
        "- Candidate tiers are provisional and must not be treated as inclusion decisions.",
        "- Literature verification remains necessary before corpus inclusion.",
        "- Optional exact matches to local datasets (e.g. AptaBase) are informational only.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_pipeline(
    inspection_dir: Path,
    output_dir: Path,
    embl_path: Path | None = None,
    overwrite: bool = False,
    max_review_records: int | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.glob("ena_candidate_*.csv")) and not overwrite:
        raise FileExistsError(
            f"Outputs already exist in {output_dir}; pass --overwrite to replace them"
        )

    logger.info("Loading inspection tables from %s", inspection_dir)
    tables = load_inspection_tables(inspection_dir)
    if embl_path:
        logger.info("EMBL path available for optional recovery: %s", embl_path)
    else:
        logger.info("No EMBL file resolved; proceeding from inspection CSVs only")

    working = build_working_table(tables)
    working["source_file"] = str(inspection_dir / "ena_record_inventory.csv")
    logger.info("Working table rows: %d", len(working))

    logger.info("Assigning group identifiers")
    working = assign_group_ids(working, tables["ena_duplicate_summary.csv"])

    feature_lookup = build_feature_lookup(tables["ena_feature_table_long.csv"])
    external = load_optional_external_indexes(REPO_ROOT)

    logger.info("Classifying %d records", len(working))
    candidate_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    for _, series in working.iterrows():
        row = series.to_dict()
        feat = feature_lookup.get(str(row["accession"]))
        result, evidence = process_record(row, feat, external)
        # preserve group ids already on row
        for gcol in [
            "exact_sequence_group",
            "rna_normalized_sequence_group",
            "reverse_complement_group",
            "reference_group",
            "description_group",
            "candidate_experiment_group",
        ]:
            result[gcol] = row.get(gcol, result.get(gcol, ""))
        candidate_rows.append(result)
        evidence_rows.extend(e.to_row() for e in evidence)

    candidates = pd.DataFrame(candidate_rows)
    candidates = annotate_group_membership(candidates)

    logger.info("Building group summaries")
    groups = build_groups_table(candidates)

    exclusions = build_exclusions(candidates)
    review = build_review_queue(candidates, max_review_records)
    target_review = build_target_normalization_review(candidates)
    refs = build_reference_table(tables["ena_reference_summary.csv"], candidates)
    evidence_df = pd.DataFrame(evidence_rows)

    paths = {
        "ena_candidate_records.csv": output_dir / "ena_candidate_records.csv",
        "ena_candidate_groups.csv": output_dir / "ena_candidate_groups.csv",
        "ena_candidate_references.csv": output_dir / "ena_candidate_references.csv",
        "ena_candidate_evidence_long.csv": output_dir / "ena_candidate_evidence_long.csv",
        "ena_candidate_review_queue.csv": output_dir / "ena_candidate_review_queue.csv",
        "ena_candidate_exclusions.csv": output_dir / "ena_candidate_exclusions.csv",
        "ena_target_normalization_review.csv": output_dir / "ena_target_normalization_review.csv",
        "ena_candidate_qc_report.md": output_dir / "ena_candidate_qc_report.md",
    }

    candidates.reindex(columns=[c for c in CANDIDATE_COLUMNS if c in candidates.columns]).to_csv(
        paths["ena_candidate_records.csv"], index=False
    )
    groups.to_csv(paths["ena_candidate_groups.csv"], index=False)
    refs.to_csv(paths["ena_candidate_references.csv"], index=False)
    evidence_df.to_csv(paths["ena_candidate_evidence_long.csv"], index=False)
    review.to_csv(paths["ena_candidate_review_queue.csv"], index=False)
    exclusions.to_csv(paths["ena_candidate_exclusions.csv"], index=False)
    target_review.to_csv(paths["ena_target_normalization_review.csv"], index=False)
    write_qc_report(paths["ena_candidate_qc_report.md"], candidates, groups, review)

    logger.info("Wrote %d candidate rows to %s", len(candidates), output_dir)
    logger.info(
        "Tier counts: %s",
        candidates["candidate_tier"].value_counts().to_dict(),
    )
    return paths


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build conservative ENA aptamer–protein candidate tables from inspection outputs."
    )
    p.add_argument("--inspection-dir", type=Path, default=DEFAULT_INSPECTION_DIR)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--input-embl", type=Path, default=None, help="Optional EMBL flat file for recovery")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--max-review-records", type=int, default=None)
    p.add_argument("--log-level", default="INFO")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / "ena_candidate_processing_log.txt"
    configure_logging(log_path, args.log_level)
    embl = resolve_embl_path(args.input_embl)
    try:
        run_pipeline(
            inspection_dir=args.inspection_dir,
            output_dir=args.output_dir,
            embl_path=embl,
            overwrite=args.overwrite,
            max_review_records=args.max_review_records,
        )
    except Exception:
        logger.exception("Candidate processing failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

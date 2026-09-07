#!/usr/bin/env python3
"""Finalize manually accepted ENA aptamer records into a clean supplement.

Produces a validated, internally deduplicated ENA source dataset awaiting
future master-corpus integration. Does **not** compare against other
datasets, create a master corpus, or call external APIs.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from ena_candidate_rules import PROTEIN_COMPATIBLE_TARGET_TYPES, stable_group_id
from ena_review_rules import join_unique
from ena_review_v2_rules import strongest_evidence_scope_v2

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    REPO_ROOT / "data" / "raw" / "ENA" / "review_v2" / "ena_selected_after_manual_review.csv"
)
DEFAULT_PROVENANCE = (
    REPO_ROOT / "data" / "raw" / "ENA" / "review_v2" / "ena_selected_sequence_provenance.csv"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "processed" / "ena"

logger = logging.getLogger("finalize_ena_aptamer_supplement")

VALID_RNA_RE = re.compile(r"^[ACGU]+$")

# Strength ordering for consolidation only — not a quantitative score.
EVIDENCE_STRENGTH_RANK = {
    "none": 0,
    "": 0,
    "weak": 1,
    "moderate": 2,
    "strong": 3,
}

# Editable canonical display map keyed by orthographic comparison form.
# Safe formatting / explicit clerical aliases only — not a synonym ontology.
TARGET_CANONICAL_ALIASES: dict[str, str] = {
    # Explicit clerical mappings
    "PAP": "Prostatic acid phosphatase",
    "PROSTATICACIDPHOSPHATASE": "Prostatic acid phosphatase",
    "ECOLITERMINATIONFACTORRF1": "Escherichia coli termination factor RF1",
    "ESCHERICHIACOLITERMINATIONFACTORRF1": "Escherichia coli termination factor RF1",
    "HUMANCYCLINT1": "human cyclin T1",
    "PRION": "prion protein",
    "PRIONPROTEIN": "prion protein",
    # Orthographic variants already handled earlier
    "FGF2": "FGF2",
    "FGF1": "FGF1",
    "IL17": "IL-17",
    "IL17A": "IL-17A",
    "IL21": "IL-21",
    "IL6": "IL-6",
    "TNFALPHA": "TNF-α",
    "TNFA": "TNF-α",
    "TNFΑ": "TNF-α",
    "ERBB2": "ErbB2",
    "HER2": "HER2",
    "VEGFA": "VEGF-A",
    "VEGF": "VEGF",
    "ADAMTS5": "ADAMTS5",
    "ALPPL2": "ALPPL2",
    "CTHRC1": "CTHRC1",
    "PDGF": "PDGF",
    "TSA56": "TSA56",
    "TST56": "TSA56",
    "TSG56": "TSA56",
    "NGF": "NGF",
    "ASK1": "ASK1",
    "HMGB1": "HMGB1",
}

_GREEK_MAP = str.maketrans(
    {
        "α": "ALPHA",
        "β": "BETA",
        "γ": "GAMMA",
        "δ": "DELTA",
        "ε": "EPSILON",
        "Α": "A",
        "Β": "B",
        "Γ": "G",
    }
)

CLEAN_CORE_COLUMNS = [
    "clean_record_id",
    "sequence_rna_clean",
    "sequence_length_clean",
    "target_canonical",
    "target_type",
    "target_region",
    "target_comparison_key",
    "binding_evidence_type",
    "binding_evidence_strength",
    "evidence_scope",
    "supporting_accessions",
    "supporting_review_unit_ids",
    "supporting_experiment_group_ids",
    "internal_duplicate_count",
    "sequence_quality_status",
    "length_status",
    "automatic_concern_flags",
    "near_duplicate_family_id",
    "source_dataset",
    "source_database",
    "processing_status",
]

CLEAN_SECONDARY_COLUMNS = [
    "sequence",
    "sequence_original",
    "manual_sequence_corrected",
    "target_reviewed",
    "target_original",
    "manual_target_corrected",
    "representative_title",
    "supporting_titles",
    "binding_evidence_type_all",
    "binding_evidence_strength_max",
    "evidence_scope_all",
    "manual_notes",
    "t_to_u_conversion_applied",
    "sequence_cleaning_actions",
    "sequence_validation_status",
    "reported_or_reviewed_length",
    "sequence_length_matches",
    "sequence_length_difference",
    "target_canonicalization_actions",
    "same_sequence_multiple_targets",
    "other_targets_for_same_sequence",
    "accepted_under_20_nt",
    "accepted_promoter_or_template_flag",
    "accepted_with_other_concern",
    "processing_date_utc",
    "future_master_deduplication_status",
]

OUTPUT_FILES = [
    "ena_aptamer_supplement_clean.csv",
    "ena_aptamer_supplement_provenance.csv",
    "ena_aptamer_supplement_rejected_final_qc.csv",
    "ena_aptamer_supplement_qc_report.md",
    "ena_aptamer_supplement_processing_log.txt",
]


class FinalizeValidationError(ValueError):
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


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if df.empty and len(df.columns) == 0:
        path.write_text("", encoding="utf-8-sig")
        return
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _split_pipe(value: Any) -> list[str]:
    return [p.strip() for p in str(value or "").split("|") if p.strip()]


def _join_pipe(values: Iterable[Any]) -> str:
    seen: list[str] = []
    for v in values:
        s = str(v or "").strip()
        if s and s not in seen:
            seen.append(s)
    return "|".join(seen)


# ---------------------------------------------------------------------------
# Sequence cleaning
# ---------------------------------------------------------------------------


def orthographic_target_key(name: str) -> str:
    """Uppercase; strip spaces/punctuation; expand Greek letters."""
    if not name:
        return ""
    text = str(name).strip().translate(_GREEK_MAP)
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = text.upper()
    return re.sub(r"[^A-Z0-9]+", "", text)


def clean_rna_sequence(raw: str) -> tuple[str, list[str], bool]:
    """Return (clean_seq, actions, t_to_u_applied). Does not alter ``raw``."""
    actions: list[str] = []
    text = str(raw or "")
    stripped = text.strip()
    if stripped != text:
        actions.append("trim_whitespace")
    no_ws = "".join(stripped.split())
    if no_ws != stripped:
        actions.append("remove_internal_whitespace")
    upper = no_ws.upper()
    if upper != no_ws:
        actions.append("uppercase")
    t_to_u = "T" in upper
    clean = upper.replace("T", "U")
    if t_to_u:
        actions.append("t_to_u")
    if not actions and clean:
        actions.append("unchanged")
    return clean, actions, t_to_u


def validate_clean_sequence(clean: str) -> str:
    if not clean:
        return "missing_sequence"
    if not VALID_RNA_RE.fullmatch(clean):
        return "invalid_character"
    return "valid_rna_sequence"


def explain_length_mismatch(
    reviewed_sequence: str,
    clean: str,
    reported_length: int | None,
) -> tuple[bool, int, str]:
    """Return (matches_or_explained, difference, note)."""
    clean_len = len(clean)
    if reported_length is None:
        return True, 0, "no_reported_length"
    diff = reported_length - clean_len
    if diff == 0:
        return True, 0, "exact_match"

    raw = str(reviewed_sequence or "")
    raw_len = len(raw)
    no_ws_len = len("".join(raw.split()))
    # Whitespace-only explanation: reported counted raw chars including spaces,
    # or reported equals pre-clean compacted length that matches clean.
    if reported_length == raw_len and no_ws_len == clean_len and raw_len != clean_len:
        return True, diff, "explained_by_whitespace"
    if reported_length == no_ws_len and no_ws_len == clean_len:
        return True, 0, "exact_match_after_whitespace_normalisation"
    # T→U never changes length; cannot explain a numeric disagreement.
    return False, diff, "unresolved_length_mismatch"


# ---------------------------------------------------------------------------
# Target canonicalisation
# ---------------------------------------------------------------------------


def canonicalise_target(reviewed_target: str) -> tuple[str, str, list[str]]:
    """Return (canonical_display, comparison_key, actions)."""
    reviewed = str(reviewed_target or "").strip()
    actions: list[str] = []
    if not reviewed:
        return "", "", ["missing_target"]

    ortho = orthographic_target_key(reviewed)
    if ortho in TARGET_CANONICAL_ALIASES:
        canonical = TARGET_CANONICAL_ALIASES[ortho]
        if canonical != reviewed:
            actions.append(f"alias:{reviewed}->{canonical}")
        else:
            actions.append("alias_identity")
    else:
        canonical = re.sub(r"\s+", " ", reviewed)
        actions.append("preserve_reviewed")

    key = orthographic_target_key(canonical)
    # Ensure PAP / prostatic acid phosphatase share one key via alias display
    if key in TARGET_CANONICAL_ALIASES:
        canonical = TARGET_CANONICAL_ALIASES[key]
        key = orthographic_target_key(canonical)
    return canonical, key, actions


def is_invalid_canonical_target(canonical: str, target_type: str) -> str | None:
    if not canonical.strip():
        return "missing_canonical_target"
    if canonical.strip().lower() in {"unknown", ""}:
        return "unknown_target"
    ttype = str(target_type or "").strip()
    if ttype not in PROTEIN_COMPATIBLE_TARGET_TYPES:
        return f"unsupported_target_type:{ttype or 'blank'}"
    return None


# ---------------------------------------------------------------------------
# Evidence helpers
# ---------------------------------------------------------------------------


def max_evidence_strength(values: Iterable[str]) -> str:
    best = "none"
    best_rank = -1
    for v in values:
        s = str(v or "").strip().lower()
        rank = EVIDENCE_STRENGTH_RANK.get(s, 0)
        if rank > best_rank:
            best = s if s else "none"
            best_rank = rank
    return best


def prefer_evidence_type(rows: list[dict[str, Any]], chosen_scope: str) -> str:
    for r in rows:
        if str(r.get("evidence_scope", "") or "") == chosen_scope:
            return str(r.get("binding_evidence_type", "") or "")
    return str(rows[0].get("binding_evidence_type", "") or "") if rows else ""


# ---------------------------------------------------------------------------
# Row processing
# ---------------------------------------------------------------------------


def process_input_row(row: pd.Series, processing_date: str) -> dict[str, Any]:
    reviewed_seq = str(row.get("sequence", "") or "")
    clean, actions, t_to_u = clean_rna_sequence(reviewed_seq)
    status = validate_clean_sequence(clean)

    reported_raw = str(row.get("sequence_length", "") or "").strip()
    reported: int | None
    try:
        reported = int(reported_raw) if reported_raw else None
    except ValueError:
        reported = None

    length_ok, length_diff, length_note = explain_length_mismatch(
        reviewed_seq, clean, reported
    )
    if status == "valid_rna_sequence" and not length_ok:
        status = "length_mismatch"

    target_reviewed = str(row.get("target", "") or "").strip()
    canonical, cmp_key, tgt_actions = canonicalise_target(target_reviewed)
    target_error = is_invalid_canonical_target(
        canonical, str(row.get("target_type", "") or "")
    )

    concern_flags = str(row.get("automatic_concern_flags", "") or "")
    under_20 = "1" if clean and len(clean) < 20 else "0"
    promoter = (
        "1"
        if re.search(r"promoter|template", concern_flags, flags=re.IGNORECASE)
        else "0"
    )
    tokens = [t.strip() for t in re.split(r"[;|]", concern_flags) if t.strip()]
    non_promoter = [
        t for t in tokens if "promoter" not in t.lower() and "template" not in t.lower()
    ]
    other_concern = "1" if non_promoter else "0"

    rejection_reason = ""
    rejection_notes = ""
    if status == "missing_sequence":
        rejection_reason = "missing_sequence"
    elif status == "invalid_character":
        rejection_reason = "invalid_nucleotide_characters"
        bad = sorted({ch for ch in clean if ch not in set("ACGU")})
        rejection_notes = f"non_acgu={''.join(bad)}"
    elif status == "length_mismatch":
        rejection_reason = "unresolved_length_mismatch"
        rejection_notes = (
            f"reported={reported_raw}; clean_len={len(clean)}; note={length_note}"
        )
    elif target_error:
        rejection_reason = target_error
        status = status if status != "valid_rna_sequence" else "valid_rna_sequence"

    return {
        **{k: str(row.get(k, "") or "") for k in row.index},
        "sequence_rna_clean": clean,
        "sequence_length_clean": str(len(clean)) if clean else "0",
        "sequence_cleaning_actions": "|".join(actions),
        "t_to_u_conversion_applied": "1" if t_to_u else "0",
        "sequence_validation_status": status,
        "reported_or_reviewed_length": reported_raw,
        "sequence_length_matches": "1" if length_ok and status != "length_mismatch" else "0",
        "sequence_length_difference": str(length_diff),
        "target_reviewed": target_reviewed,
        "target_canonical": canonical,
        "target_comparison_key": cmp_key,
        "target_canonicalization_actions": "|".join(tgt_actions),
        "accepted_under_20_nt": under_20,
        "accepted_promoter_or_template_flag": promoter,
        "accepted_with_other_concern": other_concern,
        "processing_date_utc": processing_date,
        "final_qc_rejection_reason": rejection_reason,
        "final_qc_notes": rejection_notes,
        "_length_note": length_note,
    }


def make_clean_record_id(sequence_rna_clean: str, target_comparison_key: str) -> str:
    return stable_group_id("ena", f"{sequence_rna_clean}||{target_comparison_key}")


def consolidate_valid_rows(
    valid_rows: list[dict[str, Any]],
    processing_date: str,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in valid_rows:
        key = (row["sequence_rna_clean"], row["target_comparison_key"])
        buckets[key].append(row)

    # Same sequence, multiple canonical targets
    seq_to_targets: dict[str, set[str]] = defaultdict(set)
    for (seq, key), rows in buckets.items():
        seq_to_targets[seq].add(rows[0]["target_canonical"])

    clean_rows: list[dict[str, Any]] = []
    dup_events: list[dict[str, Any]] = []

    for (seq, key), rows in buckets.items():
        record_id = make_clean_record_id(seq, key)
        unit_ids = []
        for r in rows:
            unit_ids.extend(_split_pipe(r.get("review_unit_ids", "")))
            unit_ids.extend(_split_pipe(r.get("review_unit_id", "")))
        unit_ids = list(dict.fromkeys([u for u in unit_ids if u]))

        group_ids = []
        for r in rows:
            group_ids.extend(_split_pipe(r.get("experiment_group_ids", "")))
            group_ids.extend(_split_pipe(r.get("experiment_group_id", "")))
        group_ids = list(dict.fromkeys([g for g in group_ids if g]))

        accessions = []
        for r in rows:
            accessions.extend(_split_pipe(r.get("accessions", "")))
        accessions = sorted(set(accessions))

        titles = join_unique(r.get("representative_title", "") for r in rows)
        scopes = [str(r.get("evidence_scope", "") or "") for r in rows]
        scope_all = _join_pipe(scopes)
        strength_all = [str(r.get("binding_evidence_strength", "") or "") for r in rows]
        strength_max = max_evidence_strength(strength_all)
        # Strongest scope for representative fields; do not upgrade patent→individual
        best_scope = strongest_evidence_scope_v2(scopes)
        if best_scope == "experiment_family_level" and any(
            s == "experiment_or_family_level" for s in scopes
        ) and "experiment_family_level" not in scopes:
            best_scope = "experiment_or_family_level"
        # Prefer an original scope string present in the data
        if best_scope not in scopes:
            for s in scopes:
                if s:
                    best_scope = s
                    break
        ev_type = prefer_evidence_type(rows, best_scope)
        ev_type_all = _join_pipe(r.get("binding_evidence_type", "") for r in rows)

        regions = _join_pipe(r.get("target_region", "") for r in rows)
        types = [str(r.get("target_type", "") or "") for r in rows if str(r.get("target_type", "") or "")]
        ttype = Counter(types).most_common(1)[0][0] if types else ""

        other_targets = sorted(seq_to_targets[seq] - {rows[0]["target_canonical"]})
        same_multi = "1" if other_targets else "0"

        quality = join_unique(r.get("sequence_quality_status", "") for r in rows)
        length_status = join_unique(r.get("length_status", "") for r in rows)
        flags = _join_pipe(
            t
            for r in rows
            for t in re.split(r"[;|]", str(r.get("automatic_concern_flags", "") or ""))
            if t.strip()
        )
        fam = _join_pipe(r.get("near_duplicate_family_id", "") for r in rows)
        notes = join_unique(r.get("manual_notes", "") for r in rows)
        cleaning = _join_pipe(r.get("sequence_cleaning_actions", "") for r in rows)
        tgt_actions = _join_pipe(r.get("target_canonicalization_actions", "") for r in rows)
        t_to_u = "1" if any(r.get("t_to_u_conversion_applied") == "1" for r in rows) else "0"

        under_20 = "1" if len(seq) < 20 else "0"
        promoter = (
            "1"
            if re.search(r"promoter|template", flags, flags=re.IGNORECASE)
            else "0"
        )
        tokens = [t.strip() for t in re.split(r"[;|]", flags) if t.strip()]
        non_promoter = [
            t for t in tokens if "promoter" not in t.lower() and "template" not in t.lower()
        ]
        other_concern = "1" if non_promoter else "0"

        # Preserve first-row reviewed sequence fields (unchanged source values)
        primary = rows[0]
        clean_rows.append(
            {
                "clean_record_id": record_id,
                "sequence_rna_clean": seq,
                "sequence_length_clean": str(len(seq)),
                "target_canonical": primary["target_canonical"],
                "target_type": ttype,
                "target_region": regions,
                "target_comparison_key": key,
                "binding_evidence_type": ev_type,
                "binding_evidence_strength": (
                    strength_max
                    if any(str(s).strip() for s in strength_all)
                    else ""
                ),
                "evidence_scope": best_scope,
                "supporting_accessions": "|".join(accessions),
                "supporting_review_unit_ids": "|".join(unit_ids),
                "supporting_experiment_group_ids": "|".join(group_ids),
                "internal_duplicate_count": str(len(rows)),
                "sequence_quality_status": quality,
                "length_status": length_status,
                "automatic_concern_flags": flags,
                "near_duplicate_family_id": fam,
                "source_dataset": "ENA_manual_reviewed_supplement",
                "source_database": "ENA",
                "processing_status": "validated_pending_master_corpus_integration",
                "sequence": str(primary.get("sequence", "") or ""),
                "sequence_original": str(primary.get("sequence_original", "") or ""),
                "manual_sequence_corrected": str(
                    primary.get("manual_sequence_corrected", "") or ""
                ),
                "target_reviewed": str(primary.get("target_reviewed", "") or ""),
                "target_original": str(primary.get("target_original", "") or ""),
                "manual_target_corrected": str(
                    primary.get("manual_target_corrected", "") or ""
                ),
                "representative_title": str(
                    primary.get("representative_title", "") or ""
                ),
                "supporting_titles": titles,
                "binding_evidence_type_all": ev_type_all,
                "binding_evidence_strength_max": strength_max,
                "evidence_scope_all": scope_all,
                "manual_notes": notes,
                "t_to_u_conversion_applied": t_to_u,
                "sequence_cleaning_actions": cleaning,
                "sequence_validation_status": "valid_rna_sequence",
                "reported_or_reviewed_length": str(
                    primary.get("reported_or_reviewed_length", "") or ""
                ),
                "sequence_length_matches": str(
                    primary.get("sequence_length_matches", "") or ""
                ),
                "sequence_length_difference": str(
                    primary.get("sequence_length_difference", "") or ""
                ),
                "target_canonicalization_actions": tgt_actions,
                "same_sequence_multiple_targets": same_multi,
                "other_targets_for_same_sequence": "|".join(other_targets),
                "accepted_under_20_nt": under_20,
                "accepted_promoter_or_template_flag": promoter,
                "accepted_with_other_concern": other_concern,
                "processing_date_utc": processing_date,
                "future_master_deduplication_status": "not_yet_performed",
                # Useful retained provenance-ish fields
                "accession_count": str(len(accessions)),
                "doi_values": _join_pipe(r.get("doi_values", "") for r in rows),
                "pubmed_values": _join_pipe(r.get("pubmed_values", "") for r in rows),
                "selection_evidence_summary": join_unique(
                    r.get("selection_evidence_summary", "") for r in rows
                ),
            }
        )
        if len(rows) > 1:
            dup_events.append(
                {
                    "clean_record_id": record_id,
                    "target_comparison_key": key,
                    "n_rows": len(rows),
                    "supporting_review_unit_ids": "|".join(unit_ids),
                    "supporting_accessions": "|".join(accessions),
                }
            )

    clean = pd.DataFrame(clean_rows)
    if not clean.empty:
        ordered = [c for c in CLEAN_CORE_COLUMNS + CLEAN_SECONDARY_COLUMNS if c in clean.columns]
        extras = [c for c in clean.columns if c not in ordered]
        clean["_len"] = pd.to_numeric(clean["sequence_length_clean"], errors="coerce").fillna(0)
        clean = (
            clean.sort_values(by=["target_canonical", "_len", "sequence_rna_clean"], kind="mergesort")
            .drop(columns=["_len"])
            .reset_index(drop=True)
        )
        clean = clean[ordered + extras]
    return clean, dup_events


def build_provenance_export(
    clean: pd.DataFrame,
    provenance: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Join clean records to accession provenance."""
    if clean.empty:
        return pd.DataFrame(), [], []

    unit_to_clean: dict[str, list[dict[str, str]]] = defaultdict(list)
    for _, row in clean.iterrows():
        meta = {
            "clean_record_id": str(row["clean_record_id"]),
            "sequence_rna_clean": str(row["sequence_rna_clean"]),
            "target_canonical": str(row["target_canonical"]),
            "sequence_reviewed": str(row.get("sequence", "") or ""),
            "target_reviewed": str(row.get("target_reviewed", "") or ""),
        }
        for uid in _split_pipe(row.get("supporting_review_unit_ids", "")):
            unit_to_clean[uid].append(meta)

    out_rows: list[dict[str, Any]] = []
    matched_clean_ids: set[str] = set()
    if not provenance.empty and "review_unit_id" in provenance.columns:
        for _, prow in provenance.iterrows():
            uid = str(prow.get("review_unit_id", "") or "")
            for meta in unit_to_clean.get(uid, []):
                matched_clean_ids.add(meta["clean_record_id"])
                out_rows.append(
                    {
                        "clean_record_id": meta["clean_record_id"],
                        "sequence_rna_clean": meta["sequence_rna_clean"],
                        "target_canonical": meta["target_canonical"],
                        "review_unit_id": uid,
                        "experiment_group_id": str(prow.get("experiment_group_id", "") or ""),
                        "accession": str(prow.get("accession", "") or ""),
                        "sequence_deposited": str(prow.get("sequence_deposited", "") or ""),
                        "sequence_reviewed": meta["sequence_reviewed"],
                        "target_raw": str(prow.get("target_raw", "") or ""),
                        "target_reviewed": meta["target_reviewed"],
                        "description": str(prow.get("description", "") or ""),
                        "reference_or_patent_title": str(prow.get("reference", "") or ""),
                        "binding_evidence": str(prow.get("binding_evidence_type", "") or ""),
                        "evidence_scope": str(prow.get("evidence_scope", "") or ""),
                        "source_warnings": _join_pipe(
                            [
                                prow.get("ambiguity_symbols", ""),
                                prow.get("promoter_trim_status", ""),
                                prow.get("evidence_repair_reason", ""),
                            ]
                        ),
                    }
                )

    all_clean_ids = set(clean["clean_record_id"].astype(str))
    unmatched_clean = sorted(all_clean_ids - matched_clean_ids)
    prov_units = set(provenance["review_unit_id"].astype(str)) if not provenance.empty else set()
    clean_units = set(unit_to_clean)
    unmatched_prov_units = sorted(prov_units - clean_units)
    return pd.DataFrame(out_rows), unmatched_clean, unmatched_prov_units


def write_qc_report(
    path: Path,
    *,
    input_df: pd.DataFrame,
    processed: list[dict[str, Any]],
    clean: pd.DataFrame,
    rejected: pd.DataFrame,
    provenance_out: pd.DataFrame,
    dup_events: list[dict[str, Any]],
    unmatched_clean: list[str],
    unmatched_prov: list[str],
) -> None:
    def _count_table(series: pd.Series, title: str) -> list[str]:
        lines = [f"### {title}", "", "| value | count |", "|---|---:|"]
        if series.empty:
            lines.append("| _(none)_ | 0 |")
        else:
            for val, cnt in series.fillna("").astype(str).value_counts().items():
                label = (val if val else "_(blank)_").replace("|", "/")
                lines.append(f"| {label} | {cnt} |")
        lines.append("")
        return lines

    n_in = len(input_df)
    in_seqs = int(input_df["sequence"].nunique()) if n_in and "sequence" in input_df.columns else 0
    in_tgts = int(input_df["target"].nunique()) if n_in and "target" in input_df.columns else 0
    in_acc: set[str] = set()
    in_groups: set[str] = set()
    for _, r in input_df.iterrows():
        in_acc.update(_split_pipe(r.get("accessions", "")))
        in_groups.update(_split_pipe(r.get("experiment_group_ids", "")))
        in_groups.update(_split_pipe(r.get("experiment_group_id", "")))

    t_to_u_rows = [r for r in processed if r.get("t_to_u_conversion_applied") == "1"]
    ws_rows = [
        r
        for r in processed
        if "whitespace" in str(r.get("sequence_cleaning_actions", ""))
    ]
    invalid = [r for r in processed if r.get("sequence_validation_status") == "invalid_character"]
    missing = [r for r in processed if r.get("sequence_validation_status") == "missing_sequence"]
    length_bad = [r for r in processed if r.get("sequence_validation_status") == "length_mismatch"]
    valid_n = sum(1 for r in processed if r.get("final_qc_rejection_reason") == "")

    alias_applied = [
        r
        for r in processed
        if "alias:" in str(r.get("target_canonicalization_actions", ""))
    ]
    pap_merge = [
        r
        for r in processed
        if r.get("target_comparison_key") == orthographic_target_key("Prostatic acid phosphatase")
    ]
    target_rejects = rejected[
        rejected["final_qc_rejection_reason"].str.contains("target", case=False, na=False)
    ] if not rejected.empty else rejected

    multi_tgt = int((clean.get("same_sequence_multiple_targets", pd.Series(dtype=str)) == "1").sum()) if not clean.empty else 0
    under20 = int((clean.get("accepted_under_20_nt", pd.Series(dtype=str)) == "1").sum()) if not clean.empty else 0
    promoter_n = int((clean.get("accepted_promoter_or_template_flag", pd.Series(dtype=str)) == "1").sum()) if not clean.empty else 0
    other_n = int((clean.get("accepted_with_other_concern", pd.Series(dtype=str)) == "1").sum()) if not clean.empty else 0

    length_bins: Counter[str] = Counter()
    if not clean.empty:
        for length in pd.to_numeric(clean["sequence_length_clean"], errors="coerce").fillna(0).astype(int):
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

    lines = [
        "# ENA aptamer supplement — final cleaning QC report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Validated ENA source dataset awaiting future master-corpus integration.",
        "Deduplication against other aptamer datasets has **not** yet been performed.",
        "",
        "## Input summary",
        "",
        "| metric | count |",
        "|---|---:|",
        f"| manually accepted input rows | {n_in} |",
        f"| unique input sequences | {in_seqs} |",
        f"| unique input targets | {in_tgts} |",
        f"| input accessions | {len(in_acc)} |",
        f"| input experiment groups | {len(in_groups)} |",
        "",
        "## Sequence cleaning",
        "",
        "| metric | count |",
        "|---|---:|",
        f"| records receiving T-to-U conversion | {len(t_to_u_rows)} |",
        f"| records with whitespace removed | {len(ws_rows)} |",
        f"| invalid sequences | {len(invalid)} |",
        f"| missing sequences | {len(missing)} |",
        f"| length mismatches (unresolved) | {len(length_bad)} |",
        f"| final valid A/C/G/U sequences (pre-dedup, non-rejected) | {valid_n} |",
        f"| records rejected by final sequence/target QC | {len(rejected)} |",
        "",
        "### T-to-U conversions (accessions / review units)",
        "",
    ]
    if t_to_u_rows:
        for r in t_to_u_rows:
            lines.append(
                f"- review_unit_id={r.get('review_unit_id', '')}; "
                f"accessions={r.get('accessions', '')}"
            )
    else:
        lines.append("_None_")
    lines.append("")

    lines.extend(
        [
            "## Target cleaning",
            "",
            "| metric | count |",
            "|---|---:|",
            f"| target aliases applied | {len(alias_applied)} |",
            f"| canonical target count (clean output) | {int(clean['target_canonical'].nunique()) if not clean.empty else 0} |",
            f"| PAP / prostatic acid phosphatase rows | {len(pap_merge)} |",
            f"| records rejected due to target validation | {len(target_rejects)} |",
            "",
        ]
    )
    if alias_applied:
        lines.append("### Canonicalisation actions (sample)")
        lines.append("")
        for r in alias_applied[:40]:
            lines.append(
                f"- {r.get('target_reviewed', '')} → {r.get('target_canonical', '')} "
                f"({r.get('target_canonicalization_actions', '')})"
            )
        if len(alias_applied) > 40:
            lines.append(f"- … and {len(alias_applied) - 40} more")
        lines.append("")

    consolidated_rows = sum(ev["n_rows"] - 1 for ev in dup_events)
    lines.extend(
        [
            "## Internal ENA deduplication",
            "",
            "| metric | count |",
            "|---|---:|",
            f"| input rows before internal deduplication | {valid_n} |",
            f"| final unique sequence–target pairs | {len(clean)} |",
            f"| duplicate groups found | {len(dup_events)} |",
            f"| rows consolidated | {consolidated_rows} |",
            f"| same-sequence / different-target cases retained | {multi_tgt} |",
            "",
            "Deduplication against other aptamer datasets has **not yet been performed**.",
            "",
        ]
    )
    if dup_events:
        largest = sorted(dup_events, key=lambda e: e["n_rows"], reverse=True)[:10]
        lines.extend(
            [
                "### Largest duplicate groups",
                "",
                "| clean_record_id | n_rows | accessions |",
                "|---|---:|---|",
            ]
        )
        for ev in largest:
            lines.append(
                f"| {ev['clean_record_id']} | {ev['n_rows']} | {ev['supporting_accessions']} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Accepted-data summary",
            "",
            "| metric | count |",
            "|---|---:|",
            f"| final clean rows | {len(clean)} |",
            f"| unique RNA sequences | {int(clean['sequence_rna_clean'].nunique()) if not clean.empty else 0} |",
            f"| unique canonical targets | {int(clean['target_canonical'].nunique()) if not clean.empty else 0} |",
            f"| records under 20 nt | {under20} |",
            f"| promoter/template-flagged records | {promoter_n} |",
            f"| records carrying other concern flags | {other_n} |",
            "",
        ]
    )
    if not clean.empty:
        lines.extend(_count_table(clean["target_canonical"], "Counts by target"))
        lines.extend(_count_table(clean["target_type"], "Counts by target type"))
        lines.extend(_count_table(clean["evidence_scope"], "Counts by evidence scope"))
        lines.extend(
            _count_table(clean["binding_evidence_strength"], "Counts by binding-evidence strength")
        )
    lines.extend(
        [
            "### Sequence-length distribution",
            "",
            "| bin | count |",
            "|---|---:|",
        ]
    )
    for label in ["under_20", "20_to_120", "121_to_200", "201_to_500", "over_500"]:
        lines.append(f"| {label} | {length_bins.get(label, 0)} |")
    lines.append("")

    # Target imbalance
    lines.extend(["## Target imbalance", ""])
    if clean.empty:
        lines.append("_No clean rows._")
        lines.append("")
    else:
        vc = clean["target_canonical"].value_counts()
        total = len(clean)
        lines.extend(
            [
                "| target | count | percent |",
                "|---|---:|---:|",
            ]
        )
        for tgt, cnt in vc.head(15).items():
            pct = 100.0 * cnt / total if total else 0.0
            lines.append(f"| {str(tgt).replace('|', '/')} | {cnt} | {pct:.1f}% |")
        lines.extend(
            [
                "",
                "ENA patent families may dominate this supplement. Weighting or",
                "downsampling may later be considered during master-corpus construction.",
                "",
            ]
        )

    lines.extend(
        [
            "## Provenance",
            "",
            "| metric | count |",
            "|---|---:|",
            f"| clean records with provenance | {len(clean) - len(unmatched_clean)} |",
            f"| provenance rows | {len(provenance_out)} |",
            f"| unique accessions in provenance | {int(provenance_out['accession'].nunique()) if not provenance_out.empty else 0} |",
            f"| unmatched clean records | {len(unmatched_clean)} |",
            f"| unmatched provenance review units | {len(unmatched_prov)} |",
            "",
            "## Future work",
            "",
            "The next future stage will be:",
            "",
            "1. build the master aptamer corpus from all accepted data sources;",
            "2. harmonise the schemas;",
            "3. canonicalise targets across sources;",
            "4. cluster and deduplicate sequences across datasets;",
            "5. resolve conflicting provenance;",
            "6. determine the final unit used for fine-tuning;",
            "7. perform sequence-similarity-aware train, validation and test splitting.",
            "",
            "These steps are **not** implemented in this stage.",
            "",
            "## Outputs",
            "",
            "| file | rows |",
            "|---|---:|",
            f"| ena_aptamer_supplement_clean.csv | {len(clean)} |",
            f"| ena_aptamer_supplement_provenance.csv | {len(provenance_out)} |",
            f"| ena_aptamer_supplement_rejected_final_qc.csv | {len(rejected)} |",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_finalize(
    input_path: Path,
    provenance_path: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    blocking = [
        output_dir / name
        for name in OUTPUT_FILES
        if (output_dir / name).exists() and name != "ena_aptamer_supplement_processing_log.txt"
    ]
    if blocking and not overwrite:
        raise FileExistsError(
            "Outputs already exist; pass --overwrite to replace: "
            + ", ".join(p.name for p in blocking)
        )

    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if not provenance_path.exists():
        raise FileNotFoundError(provenance_path)

    # Snapshot input mtime/size to assert we never rewrite the reviewed source
    input_stat = input_path.stat()

    logger.info("Input: %s", input_path)
    logger.info("Provenance input: %s", provenance_path)
    logger.info("Output directory: %s", output_dir)

    input_df = _read_csv(input_path)
    provenance_df = _read_csv(provenance_path)
    processing_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    processed = [process_input_row(row, processing_date) for _, row in input_df.iterrows()]

    rejected_rows = []
    valid_rows = []
    for row in processed:
        if row.get("final_qc_rejection_reason"):
            rejected_rows.append(
                {
                    "review_unit_id": row.get("review_unit_id", ""),
                    "review_unit_ids": row.get("review_unit_ids", ""),
                    "accessions": row.get("accessions", ""),
                    "sequence": row.get("sequence", ""),
                    "target": row.get("target", ""),
                    "target_canonical": row.get("target_canonical", ""),
                    "sequence_rna_clean": row.get("sequence_rna_clean", ""),
                    "target_type": row.get("target_type", ""),
                    "final_qc_rejection_reason": row.get("final_qc_rejection_reason", ""),
                    "final_qc_notes": row.get("final_qc_notes", ""),
                    "sequence_validation_status": row.get("sequence_validation_status", ""),
                    "sequence_cleaning_actions": row.get("sequence_cleaning_actions", ""),
                }
            )
        else:
            valid_rows.append(row)

    clean, dup_events = consolidate_valid_rows(valid_rows, processing_date)
    provenance_out, unmatched_clean, unmatched_prov = build_provenance_export(
        clean, provenance_df
    )

    # Missing provenance → final-QC rejection of those clean records
    if unmatched_clean:
        logger.warning(
            "Clean records missing provenance (%d): %s",
            len(unmatched_clean),
            ", ".join(unmatched_clean[:20]),
        )
        keep_mask = ~clean["clean_record_id"].isin(unmatched_clean)
        dropped = clean.loc[~keep_mask].copy()
        for _, row in dropped.iterrows():
            rejected_rows.append(
                {
                    "review_unit_id": _split_pipe(row.get("supporting_review_unit_ids", ""))[0]
                    if _split_pipe(row.get("supporting_review_unit_ids", ""))
                    else "",
                    "review_unit_ids": row.get("supporting_review_unit_ids", ""),
                    "accessions": row.get("supporting_accessions", ""),
                    "sequence": row.get("sequence", ""),
                    "target": row.get("target_reviewed", ""),
                    "target_canonical": row.get("target_canonical", ""),
                    "sequence_rna_clean": row.get("sequence_rna_clean", ""),
                    "target_type": row.get("target_type", ""),
                    "final_qc_rejection_reason": "missing_accession_provenance",
                    "final_qc_notes": f"clean_record_id={row.get('clean_record_id', '')}",
                    "sequence_validation_status": row.get("sequence_validation_status", ""),
                    "sequence_cleaning_actions": row.get("sequence_cleaning_actions", ""),
                }
            )
        clean = clean.loc[keep_mask].reset_index(drop=True)
        provenance_out, unmatched_clean, unmatched_prov = build_provenance_export(
            clean, provenance_df
        )
        if unmatched_clean:
            raise FinalizeValidationError(
                "clean records still lack provenance after rejection pass: "
                + ", ".join(unmatched_clean[:20])
            )

    rejected_columns = [
        "review_unit_id",
        "review_unit_ids",
        "accessions",
        "sequence",
        "target",
        "target_canonical",
        "sequence_rna_clean",
        "target_type",
        "final_qc_rejection_reason",
        "final_qc_notes",
        "sequence_validation_status",
        "sequence_cleaning_actions",
    ]
    rejected = pd.DataFrame(rejected_rows, columns=rejected_columns)

    _write_csv(clean, output_dir / "ena_aptamer_supplement_clean.csv")
    _write_csv(provenance_out, output_dir / "ena_aptamer_supplement_provenance.csv")
    _write_csv(rejected, output_dir / "ena_aptamer_supplement_rejected_final_qc.csv")
    write_qc_report(
        output_dir / "ena_aptamer_supplement_qc_report.md",
        input_df=input_df,
        processed=processed,
        clean=clean,
        rejected=rejected,
        provenance_out=provenance_out,
        dup_events=dup_events,
        unmatched_clean=unmatched_clean,
        unmatched_prov=unmatched_prov,
    )

    # Confirm input untouched
    after_stat = input_path.stat()
    if (after_stat.st_mtime_ns, after_stat.st_size) != (input_stat.st_mtime_ns, input_stat.st_size):
        raise FinalizeValidationError(
            f"Input file was modified during processing: {input_path}"
        )

    summary = {
        "input_rows": len(input_df),
        "t_to_u_conversions": sum(
            1 for r in processed if r.get("t_to_u_conversion_applied") == "1"
        ),
        "target_aliases_applied": sum(
            1 for r in processed if "alias:" in str(r.get("target_canonicalization_actions", ""))
        ),
        "duplicate_groups": len(dup_events),
        "final_clean_pairs": len(clean),
        "final_qc_rejected": len(rejected),
        "unique_canonical_targets": int(clean["target_canonical"].nunique()) if not clean.empty else 0,
        "provenance_rows": len(provenance_out),
        "output_dir": str(output_dir),
    }
    logger.info("Finalize summary: %s", summary)
    logger.info("Completed successfully")
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--provenance-input", type=Path, default=DEFAULT_PROVENANCE)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--log-level", default="INFO")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "ena_aptamer_supplement_processing_log.txt"
    configure_logging(log_path, args.log_level)
    try:
        run_finalize(
            input_path=Path(args.input),
            provenance_path=Path(args.provenance_input),
            output_dir=output_dir,
            overwrite=args.overwrite,
        )
    except (FileNotFoundError, FileExistsError, FinalizeValidationError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

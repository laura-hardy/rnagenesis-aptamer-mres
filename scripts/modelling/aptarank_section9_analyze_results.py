#!/usr/bin/env python3
"""Validate and summarize the frozen Section 9 NDM-1 AptaRank run.

The deployed AptaRank browser application remains the scorer. This adapter
pins and validates the prepared upload, restricted provenance keys, untouched
browser downloads, and manual PDF review. It joins results by opaque candidate
ID and emits aggregate, sequence-free outputs only. Tier 1 and Tier 2 remain
separate; no combined score or candidate shortlist is produced.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import stat
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path


PACKAGE_ID = "section9_generated_conditions_ndm1_evaluation_preset_v1"
PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_7.md"
PLAN_SHA256 = "24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9"
PUBLIC_RELATIVE = f"data/aptarank_eval/sequence/{PACKAGE_ID}"
RESULT_RELATIVE = f"results/aptarank/evaluation/{PACKAGE_ID}"
PRIVATE_RELATIVE = f"aptarank_eval/{PACKAGE_ID}"
PINS = {
    "upload/candidate_upload.csv": "abb9ab3281b972c77486306b5a15302a6aee7ee98b3011fb52946fb8cd4f4b0b",
    "records/preparation_manifest.json": "c9bf3bf6f74a212033324661e614b9105f8e7cb9e41b4a579383e6b5c75acfed",
    "records/run_sheet.json": "371f5c59052972aeda69fb6e63f16278a8cd1a09cdb6f8305539e84b6f7e5a87",
    "records/target_settings.json": "6c311ed838ad8e1b0cf22527f80e8d91a9b5bbb67347d3d0eef04d9682476541",
    "records/validation_report.json": "b977440aa94df0b7570c8b4ba1a499733ddd4edf03b4f9e2f1e445602991fb74",
    "records/expected_cell_manifest.json": "91848e59d20205a360a9f74b97edea57eac2ff781c01c3e2a923a1b241715a71",
}
PRIVATE_PINS = {
    "m9b2_private_membership_key.jsonl": "904e8fa58f67c3d57563e03dba40db0a60a9229d015c354ae1e848c9f9d8468c",
    "source_candidate_key.json": "746f0eea3e53de4550284865a6f4f2a763b339557d4ab45885cb67f9ecd46356",
}
RAW_PINS = {
    "raw/run_ndm1_section9_1134.csv": "30182cfe8eb9691c5e816c1dffd1aac02a83b5d0ef42f5cba172b05c82a5e985",
    "raw/section9_ndm1_1134.pdf": "931850ac4cd51a4fa291bfc1d8fdd757fd4c20f6362f3ec87615dcdf63bfe5c7",
}
CONDITIONS = ("B0", "B1", "B2", "D1")
UPLOAD_FIELDS = ("id", "sequence")
EXPORT_FIELDS = ("rank", "candidate", "aptamer-likeness", "compatibility", "shuffle", "len", "sequence")
COMPATIBILITY = ("strong", "moderate", "weak")
SHUFFLE = ("pass", "fail")
CANDIDATE_ID = re.compile(r"cand_[0-9a-f]{32}\Z")
STATUS = "PROVISIONAL_SECTION9_ANALYSIS_AWAITING_INDEPENDENT_REVIEW_AND_EXPLICIT_RESULT_COMMITMENT"
CAVITY_WARNING = (
    "This cavity is oddly shaped: its robust extent and equivalent-sphere diameter "
    "disagree by more than 2\u00d7. The geometric comparison assumes a roughly convex pocket."
)


class Section9AnalysisError(ValueError):
    """Raised when any frozen input or analysis invariant fails."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def byte_record(payload: bytes) -> dict[str, object]:
    return {"sha256": sha256_bytes(payload), "byte_count": len(payload)}


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def read_regular(path: Path) -> bytes:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise Section9AnalysisError(f"not a regular file: {path}")
    return path.read_bytes()


def read_pinned(path: Path, digest: str, role: str) -> bytes:
    payload = read_regular(path)
    observed = sha256_bytes(payload)
    if observed != digest:
        raise Section9AnalysisError(f"{role} hash mismatch: expected {digest}, observed {observed}")
    return payload


def parse_json(payload: bytes, role: str) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Section9AnalysisError(f"{role} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise Section9AnalysisError(f"{role} is not a JSON object")
    return value


def parse_csv(payload: bytes, fields: tuple[str, ...], role: str) -> list[dict[str, str]]:
    if b"\r" in payload:
        raise Section9AnalysisError(f"{role} contains a carriage return")
    try:
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8"), newline=""))
    except UnicodeDecodeError as exc:
        raise Section9AnalysisError(f"{role} is not UTF-8") from exc
    if tuple(reader.fieldnames or ()) != fields:
        raise Section9AnalysisError(f"{role} fields drifted")
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise Section9AnalysisError(f"{role} contains malformed rows")
    return rows


def parse_upload(payload: bytes) -> dict[str, str]:
    rows = parse_csv(payload, UPLOAD_FIELDS, "candidate upload")
    by_id: dict[str, str] = {}
    sequences: set[str] = set()
    for row in rows:
        candidate, sequence = row["id"], row["sequence"]
        if CANDIDATE_ID.fullmatch(candidate) is None:
            raise Section9AnalysisError("candidate upload contains an invalid opaque ID")
        if candidate in by_id or sequence in sequences:
            raise Section9AnalysisError("candidate upload IDs and sequences must be unique")
        if not sequence or set(sequence) - set("ACGU") or not 20 <= len(sequence) <= 100:
            raise Section9AnalysisError("candidate upload sequence is outside the frozen input rules")
        by_id[candidate] = sequence
        sequences.add(sequence)
    if len(by_id) != 800:
        raise Section9AnalysisError("candidate upload does not contain exactly 800 distinct rows")
    return by_id


def decimal_score(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise Section9AnalysisError("aptamer-likeness is not a decimal") from exc
    if not result.is_finite() or not Decimal(0) <= result <= Decimal(1):
        raise Section9AnalysisError("aptamer-likeness must be finite and in [0,1]")
    return result


def validate_export(payload: bytes, upload: dict[str, str]) -> list[dict[str, object]]:
    rows = parse_csv(payload, EXPORT_FIELDS, "downloaded shortlist")
    if len(rows) != len(upload):
        raise Section9AnalysisError("downloaded shortlist does not contain one row per upload row")
    validated: list[dict[str, object]] = []
    for row in rows:
        candidate = row["candidate"]
        if candidate not in upload or row["sequence"] != upload[candidate]:
            raise Section9AnalysisError("downloaded shortlist does not reconcile to upload by opaque ID")
        try:
            rank, length = int(row["rank"]), int(row["len"])
        except ValueError as exc:
            raise Section9AnalysisError("rank or length is not an integer") from exc
        if length != len(row["sequence"]):
            raise Section9AnalysisError("downloaded length does not match sequence")
        if row["compatibility"] not in COMPATIBILITY or row["shuffle"] not in SHUFFLE:
            raise Section9AnalysisError("downloaded categorical token is outside the frozen schema")
        validated.append({
            "rank": rank,
            "candidate": candidate,
            "score": decimal_score(row["aptamer-likeness"]),
            "compatibility": row["compatibility"],
            "shuffle": row["shuffle"],
            "length": length,
        })
    if len({row["candidate"] for row in validated}) != len(upload) or {row["candidate"] for row in validated} != set(upload):
        raise Section9AnalysisError("downloaded candidate IDs are duplicated, missing, or unexpected")
    ranked = sorted(validated, key=lambda row: int(row["rank"]))
    if [row["rank"] for row in ranked] != list(range(1, len(upload) + 1)):
        raise Section9AnalysisError("downloaded ranks are not complete from 1 through N")
    for left, right in zip(ranked, ranked[1:]):
        if left["score"] < right["score"]:
            raise Section9AnalysisError("increasing rank does not follow non-increasing score")
        if left["score"] == right["score"] and left["candidate"] > right["candidate"]:
            raise Section9AnalysisError("score ties are not ordered by ascending candidate ID")
    return ranked


def validate_source_key(payload: bytes, upload: dict[str, str]) -> dict[str, dict[str, object]]:
    document = parse_json(payload, "source candidate key")
    if document.get("package_id") != PACKAGE_ID or document.get("sequence_strings_included") is not False:
        raise Section9AnalysisError("source candidate key markers drifted")
    memberships = document.get("memberships")
    if not isinstance(memberships, list) or len(memberships) != len(upload):
        raise Section9AnalysisError("source candidate key does not contain one membership per upload row")
    by_id: dict[str, dict[str, object]] = {}
    for row in memberships:
        if not isinstance(row, dict):
            raise Section9AnalysisError("source candidate key membership is not an object")
        candidate, condition = row.get("candidate_id"), row.get("condition")
        if candidate not in upload or condition not in CONDITIONS or candidate in by_id:
            raise Section9AnalysisError("source candidate key IDs or conditions do not reconcile")
        sequence = upload[str(candidate)]
        if row.get("length") != len(sequence) or row.get("sequence_sha256") != sha256_bytes(sequence.encode()):
            raise Section9AnalysisError("source candidate key digest or length does not reconcile")
        by_id[str(candidate)] = row
    if set(by_id) != set(upload):
        raise Section9AnalysisError("source candidate key is incomplete")
    if len(upload) == 800 and Counter(row["condition"] for row in by_id.values()) != Counter({c: 200 for c in CONDITIONS}):
        raise Section9AnalysisError("source candidate key condition accounting drifted")
    return by_id


def validate_membership_key(payload: bytes, source: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise Section9AnalysisError("membership key is not UTF-8") from exc
    if len(lines) != 800 or any(not line for line in lines):
        raise Section9AnalysisError("membership key does not contain exactly 800 JSONL records")
    by_id: dict[str, dict[str, object]] = {}
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise Section9AnalysisError("membership key contains invalid JSON") from exc
        candidate = row.get("candidate_id")
        if candidate not in source or candidate in by_id:
            raise Section9AnalysisError("membership key candidate IDs do not reconcile")
        if row.get("condition") != source[candidate]["condition"] or row.get("length") != source[candidate]["length"]:
            raise Section9AnalysisError("membership key condition or length does not reconcile")
        occurrences = row.get("source_occurrences")
        if not isinstance(occurrences, list) or not occurrences:
            raise Section9AnalysisError("membership key lacks source occurrences")
        by_id[candidate] = row
    if set(by_id) != set(source):
        raise Section9AnalysisError("membership key is incomplete")
    return by_id


def quantile_type7(values: list[Decimal], probability: Decimal) -> Decimal:
    ordered = sorted(values)
    if not ordered:
        raise Section9AnalysisError("cannot summarize an empty group")
    h = Decimal(len(ordered) - 1) * probability
    lower = int(h)
    fraction = h - Decimal(lower)
    if lower == len(ordered) - 1:
        return ordered[lower]
    return ordered[lower] + fraction * (ordered[lower + 1] - ordered[lower])


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    scores = [row["score"] for row in rows]
    with localcontext() as context:
        context.prec = 50
        mean = sum(scores, Decimal(0)) / Decimal(len(scores))
    compatibility = Counter(str(row["compatibility"]) for row in rows)
    shuffle = Counter(str(row["shuffle"]) for row in rows)
    cross = {band: {token: 0 for token in SHUFFLE} for band in COMPATIBILITY}
    for row in rows:
        cross[str(row["compatibility"])][str(row["shuffle"])] += 1
    return {
        "n": len(rows),
        "aptamer_likeness": {
            "minimum": decimal_text(min(scores)),
            "q1_type7": decimal_text(quantile_type7(scores, Decimal("0.25"))),
            "median_type7": decimal_text(quantile_type7(scores, Decimal("0.5"))),
            "mean": decimal_text(mean),
            "q3_type7": decimal_text(quantile_type7(scores, Decimal("0.75"))),
            "maximum": decimal_text(max(scores)),
        },
        "shuffle": {token: shuffle[token] for token in SHUFFLE},
        "compatibility": {band: compatibility[band] for band in COMPATIBILITY},
        "compatibility_favourable_strong_or_moderate": compatibility["strong"] + compatibility["moderate"],
        "tier_cross_tabulation": cross,
    }


def subgroup_label(row: dict[str, object], membership: dict[str, dict[str, object]]) -> tuple[str | None, str | None]:
    member = membership[str(row["candidate"])]
    condition = str(member["condition"])
    values: set[str] = set()
    key: str | None = None
    if condition == "D1":
        key = "d1_training_seed"
    elif condition == "B1":
        key = "technical_block"
    if key is None:
        return None, None
    for occurrence in member["source_occurrences"]:
        provenance = occurrence.get("provenance", {})
        value = provenance.get(key)
        if value is not None:
            values.add(str(value))
    if len(values) != 1:
        raise Section9AnalysisError(f"{condition} selected membership does not map to one {key}")
    return key, next(iter(values))


def subtract(left: str, right: str) -> str:
    return decimal_text(Decimal(left) - Decimal(right))


def percentage_points(left: int, left_n: int, right: int, right_n: int) -> str:
    return decimal_text(Decimal(100) * (Decimal(left) / Decimal(left_n) - Decimal(right) / Decimal(right_n)))


def validate_run_records(result_root: Path, raw_csv: bytes, raw_pdf: bytes) -> tuple[dict[str, object], dict[str, object]]:
    raw_manifest = parse_json(read_regular(result_root / "records/raw_artifact_manifest.json"), "raw manifest")
    visual = parse_json(read_regular(result_root / "records/pdf_visual_review.json"), "PDF visual review")
    if raw_manifest.get("package_id") != PACKAGE_ID or visual.get("package_id") != PACKAGE_ID:
        raise Section9AnalysisError("run-record package ID drifted")
    artifacts = raw_manifest.get("artifacts", {})
    if artifacts.get("downloaded_shortlist") != {"byte_count": len(raw_csv), "path": "raw/run_ndm1_section9_1134.csv", "sha256": sha256_bytes(raw_csv)}:
        raise Section9AnalysisError("raw manifest shortlist record drifted")
    if artifacts.get("result_pdf") != {"byte_count": len(raw_pdf), "path": "raw/section9_ndm1_1134.pdf", "sha256": sha256_bytes(raw_pdf)}:
        raise Section9AnalysisError("raw manifest PDF record drifted")
    geometry = visual.get("target_geometry", {})
    if geometry.get("warning_exact") != CAVITY_WARNING:
        raise Section9AnalysisError("required target-geometry warning is absent or altered")
    if visual.get("tier_relationship_display") != {"n": 800, "p_value": 0.0421, "raw_tier2_numeric_values_exported": False, "spearman_rho": -0.072}:
        raise Section9AnalysisError("PDF relationship observation drifted")
    if raw_manifest.get("download_accounting") != {"exclusion_register_available": False, "other_raw_artifacts_available": False, "scored_rows": 800, "uploaded_rows": 800}:
        raise Section9AnalysisError("raw download accounting drifted")
    return raw_manifest, visual


def build_analysis(repo: Path, private_root: Path) -> tuple[dict[str, object], dict[str, object], str]:
    read_pinned(repo / PLAN_RELATIVE, PLAN_SHA256, "governing plan")
    public_root = repo / PUBLIC_RELATIVE
    result_root = repo / RESULT_RELATIVE
    private_package = private_root / PRIVATE_RELATIVE
    public_payloads = {name: read_pinned(public_root / name, digest, name) for name, digest in PINS.items()}
    private_payloads = {name: read_pinned(private_package / name, digest, name) for name, digest in PRIVATE_PINS.items()}
    raw_payloads = {name: read_pinned(result_root / name, digest, name) for name, digest in RAW_PINS.items()}

    upload = parse_upload(public_payloads["upload/candidate_upload.csv"])
    source = validate_source_key(private_payloads["source_candidate_key.json"], upload)
    membership = validate_membership_key(private_payloads["m9b2_private_membership_key.jsonl"], source)
    rows = validate_export(raw_payloads["raw/run_ndm1_section9_1134.csv"], upload)
    raw_manifest, visual = validate_run_records(
        result_root,
        raw_payloads["raw/run_ndm1_section9_1134.csv"],
        raw_payloads["raw/section9_ndm1_1134.pdf"],
    )

    enriched: list[dict[str, object]] = []
    for row in rows:
        candidate = str(row["candidate"])
        condition = str(source[candidate]["condition"])
        if int(source[candidate]["length"]) != row["length"]:
            raise Section9AnalysisError("result length does not reconcile to restricted source key")
        enriched.append({**row, "condition": condition})

    by_condition = {
        condition: summarize([row for row in enriched if row["condition"] == condition])
        for condition in CONDITIONS
    }
    if any(summary["n"] != 200 for summary in by_condition.values()):
        raise Section9AnalysisError("condition result denominators are not 200 each")

    subgroup_rows: dict[str, dict[str, list[dict[str, object]]]] = {
        "B1_technical_block": defaultdict(list),
        "D1_training_seed": defaultdict(list),
    }
    for row in enriched:
        key, value = subgroup_label(row, membership)
        if key == "technical_block":
            subgroup_rows["B1_technical_block"][str(value)].append(row)
        elif key == "d1_training_seed":
            subgroup_rows["D1_training_seed"][str(value)].append(row)
    subgroups = {
        family: {label: summarize(group) for label, group in sorted(groups.items())}
        for family, groups in subgroup_rows.items()
    }
    if {k: v["n"] for k, v in subgroups["B1_technical_block"].items()} != {"A": 100, "B": 100}:
        raise Section9AnalysisError("B1 technical-block denominators drifted")
    if {k: v["n"] for k, v in subgroups["D1_training_seed"].items()} != {"43": 100, "44": 100}:
        raise Section9AnalysisError("D1 training-seed denominators drifted")

    def comparison(left: str, right: str) -> dict[str, str]:
        lhs, rhs = by_condition[left], by_condition[right]
        return {
            "mean_aptamer_likeness_difference": subtract(lhs["aptamer_likeness"]["mean"], rhs["aptamer_likeness"]["mean"]),
            "median_aptamer_likeness_difference": subtract(lhs["aptamer_likeness"]["median_type7"], rhs["aptamer_likeness"]["median_type7"]),
            "shuffle_pass_percentage_point_difference": percentage_points(lhs["shuffle"]["pass"], lhs["n"], rhs["shuffle"]["pass"], rhs["n"]),
            "strong_or_moderate_percentage_point_difference": percentage_points(lhs["compatibility_favourable_strong_or_moderate"], lhs["n"], rhs["compatibility_favourable_strong_or_moderate"], rhs["n"]),
        }

    overall = summarize(enriched)
    summary = {
        "schema_version": "mres-aptarank-section9-analysis-summary-v1",
        "status": STATUS,
        "package_id": PACKAGE_ID,
        "denominators": {
            "uploaded": 800,
            "scored": 800,
            "technically_excluded": 0,
            "condition_memberships": {condition: 200 for condition in CONDITIONS},
            "d1_training_seed": {"43": 100, "44": 100},
            "b1_technical_block": {"A": 100, "B": 100},
        },
        "overall": overall,
        "by_condition": by_condition,
        "subgroups": subgroups,
        "prespecified_comparisons": {
            "primary_D1_minus_B1": comparison("D1", "B1"),
            "secondary_D1_minus_B2": comparison("D1", "B2"),
            "external_D1_minus_B0_descriptive_only": comparison("D1", "B0"),
        },
        "tier_relationship": {
            "source": "untouched AptaRank result PDF",
            "spearman_rho": visual["tier_relationship_display"]["spearman_rho"],
            "p_value": visual["tier_relationship_display"]["p_value"],
            "n": visual["tier_relationship_display"]["n"],
            "numeric_tier2_values_exported": False,
            "locally_recomputed": False,
            "interpretation": "negligible-magnitude weak negative association; the nominal p-value is not evidence of biological dependence or independence",
        },
        "target_geometry_limitation": {
            "warning_exact": CAVITY_WARNING,
            "implication": "Tier 2 geometry is less reliable for this non-convex cavity because the displayed comparison simplifies the pocket to a roughly convex shape.",
        },
        "method_boundaries": {
            "tier1_and_tier2_reported_separately": True,
            "combined_score_created": False,
            "section9_candidates_enter_supervisor_shortlist": False,
            "candidate_rows_or_seeds_treated_as_independent_training_replicates": False,
            "binding_or_function_claimed": False,
        },
    }
    manifest = {
        "schema_version": "mres-aptarank-section9-analysis-manifest-v1",
        "status": STATUS,
        "package_id": PACKAGE_ID,
        "inputs": {
            "governing_plan": {"path": PLAN_RELATIVE, "sha256": PLAN_SHA256},
            "public_package": {name: byte_record(payload) for name, payload in public_payloads.items()},
            "restricted_inputs": {name: byte_record(payload) for name, payload in private_payloads.items()},
            "raw_run_artifacts": {name: byte_record(payload) for name, payload in raw_payloads.items()},
            "raw_artifact_manifest": byte_record(read_regular(result_root / "records/raw_artifact_manifest.json")),
            "pdf_visual_review": byte_record(read_regular(result_root / "records/pdf_visual_review.json")),
        },
        "checks": {
            "all_pinned_hashes_match": True,
            "upload_export_join_by_opaque_id": True,
            "upload_export_sequences_and_lengths_match": True,
            "ranks_complete_and_score_ordered": True,
            "all_800_candidates_scored": True,
            "condition_and_subgroup_denominators_reconcile": True,
            "target_geometry_warning_preserved": True,
            "numeric_tier2_values_not_reconstructed": True,
            "scores_recomputed": False,
        },
    }
    report = render_report(summary, raw_manifest)
    return summary, manifest, report


def pct(numerator: int, denominator: int) -> str:
    return f"{100 * numerator / denominator:.1f}%"


def render_report(summary: dict[str, object], raw_manifest: dict[str, object]) -> str:
    lines = [
        "# Section 9 generated-condition comparison against NDM-1",
        "",
        f"Status: `{STATUS}`",
        "",
        "## Validated accounting",
        "",
        "The frozen 800-row upload reconciled exactly to the downloaded shortlist by opaque candidate ID. All 800 candidates were scored, with no technical exclusions and no replacement. Each condition contributes 200 scored memberships; D1 retains 100 candidates from training seed 43 and 100 from seed 44, and B1 retains 100 candidates from each technical block.",
        "",
        "The run used AptaRank 0.1.0, schema 1.0.0, git revision `49a85609e352`, the Evaluation preset, seed 42, 99 candidate shuffles, 200 sampled structures, `corpus_weighted_mean`, and scoring signature `95a49467ef3c6186`. The prepared target was NDM-1/5ZGX chain A in pocket/groove mode, identifier `0fde4d5e4370`. The displayed ranking runtime was 29 seconds.",
        "",
        "## Condition-level results",
        "",
        "| Condition | n | Tier 1 mean | Tier 1 median | IQR | Shuffle pass | Strong | Moderate | Weak | Strong or moderate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for condition in CONDITIONS:
        item = summary["by_condition"][condition]
        score = item["aptamer_likeness"]
        lines.append(
            f"| {condition} | {item['n']} | {Decimal(score['mean']):.3f} | {Decimal(score['median_type7']):.3f} | "
            f"{Decimal(score['q1_type7']):.3f}\u2013{Decimal(score['q3_type7']):.3f} | "
            f"{item['shuffle']['pass']}/{item['n']} ({pct(item['shuffle']['pass'], item['n'])}) | "
            f"{item['compatibility']['strong']} | {item['compatibility']['moderate']} | {item['compatibility']['weak']} | "
            f"{item['compatibility_favourable_strong_or_moderate']}/{item['n']} ({pct(item['compatibility_favourable_strong_or_moderate'], item['n'])}) |"
        )
    simultaneous = {
        condition: summary["by_condition"][condition]["tier_cross_tabulation"]["strong"]["pass"]
        + summary["by_condition"][condition]["tier_cross_tabulation"]["moderate"]["pass"]
        for condition in CONDITIONS
    }
    lines.extend([
        "",
        "As a descriptive cross-tabulation of the separate outputs, shuffle `pass` coincided with a `strong` or `moderate` compatibility band for "
        f"{simultaneous['B0']}/200 B0, {simultaneous['B1']}/200 B1, {simultaneous['B2']}/200 B2 and {simultaneous['D1']}/200 D1 candidates. "
        "This is not a combined score, a Section 9 selection threshold or a supervisor-shortlist rule.",
    ])
    primary = summary["prespecified_comparisons"]["primary_D1_minus_B1"]
    secondary = summary["prespecified_comparisons"]["secondary_D1_minus_B2"]
    lines.extend([
        "",
        "B1 versus D1 is the primary controlled downstream comparison. Relative to B1, D1's Tier 1 mean and median differences were "
        f"{Decimal(primary['mean_aptamer_likeness_difference']):+.3f} and {Decimal(primary['median_aptamer_likeness_difference']):+.3f}; "
        f"its shuffle-pass rate differed by {Decimal(primary['shuffle_pass_percentage_point_difference']):+.1f} percentage points and its strong-or-moderate compatibility rate by {Decimal(primary['strong_or_moderate_percentage_point_difference']):+.1f} points.",
        "",
        "B2 is the secondary non-neural, data-scale comparator. Relative to B2, D1's Tier 1 mean and median differences were "
        f"{Decimal(secondary['mean_aptamer_likeness_difference']):+.3f} and {Decimal(secondary['median_aptamer_likeness_difference']):+.3f}; "
        f"its shuffle-pass rate differed by {Decimal(secondary['shuffle_pass_percentage_point_difference']):+.1f} percentage points and its strong-or-moderate compatibility rate by {Decimal(secondary['strong_or_moderate_percentage_point_difference']):+.1f} points.",
        "",
        "B0 remains an external descriptive baseline because its 36-nt length regime differs from the other conditions. No candidate-level hypothesis test or training-population confidence interval is reported: candidate rows, generation seeds and technical blocks are not independent training replicates, and D1 has only two training seeds.",
        "",
        "## D1 seed and B1 block summaries",
        "",
        "| Stratum | n | Tier 1 mean | Tier 1 median | Shuffle pass | Strong | Moderate | Weak |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for family, label in (("B1_technical_block", "B1 block"), ("D1_training_seed", "D1 seed")):
        for subgroup, item in summary["subgroups"][family].items():
            score = item["aptamer_likeness"]
            lines.append(
                f"| {label} {subgroup} | {item['n']} | {Decimal(score['mean']):.3f} | {Decimal(score['median_type7']):.3f} | "
                f"{item['shuffle']['pass']}/{item['n']} ({pct(item['shuffle']['pass'], item['n'])}) | "
                f"{item['compatibility']['strong']} | {item['compatibility']['moderate']} | {item['compatibility']['weak']} |"
            )
    relation = summary["tier_relationship"]
    lines.extend([
        "",
        "## Relationship between the separate tiers",
        "",
        f"The untouched AptaRank PDF reports Spearman rho = {relation['spearman_rho']:.3f}, p = {relation['p_value']:.4f}, n = {relation['n']} for Tier 1 aptamer-likeness versus the target-compatibility control percentile. The magnitude is negligible and weakly negative. The nominal p-value should not be overinterpreted: it does not establish biological dependence or independence, the candidate rows are not training replicates, and the numeric Tier 2 percentiles were not included in the CSV and therefore were not independently recomputed.",
        "",
        "## Target-geometry warning and interpretation boundary",
        "",
        f"> {CAVITY_WARNING}",
        "",
        "This warning materially limits the Tier 2 interpretation. The selected NDM-1 cavity is non-convex enough that its robust extent and equivalent-sphere diameter disagree substantially, while the deployed geometric comparison assumes a roughly convex pocket. The strong/moderate/weak labels are therefore retained only as target-specific, REF-control-relative prioritisation categories from the frozen tool. They must not be treated as probabilities of binding or evidence of affinity, specificity, inhibition, target recognition or experimental function.",
        "",
        "Section 6 showed moderate Tier 1 separation from uniform controls but low shuffle-pass sensitivity, while Section 8 gave weak-to-mixed cognate Tier 2 results with no shuffle passes. Those findings, together with the cavity warning here, mean that favourable Section 9 outputs are descriptive computational prioritisation signals only. Tier 1 and Tier 2 remain separate; no combined score was formed, and no candidate from this 800-member comparison enters the supervisor-review shortlist.",
    ])
    return "\n".join(lines) + "\n"


def write_outputs(repo: Path, summary: dict[str, object], manifest: dict[str, object], report: str) -> Path:
    output = repo / RESULT_RELATIVE / "derived/analysis_v1"
    output.mkdir(parents=True, exist_ok=True)
    payloads = {
        "analysis_summary.json": canonical_json(summary),
        "analysis_manifest.json": canonical_json(manifest),
        "section9_results.md": report.encode("utf-8"),
    }
    for name, payload in payloads.items():
        (output / name).write_bytes(payload)
    sums = "".join(f"{sha256_bytes(payload)}  {name}\n" for name, payload in sorted(payloads.items()))
    (output / "SHA256SUMS").write_text(sums, encoding="ascii", newline="")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--private-root",
        type=Path,
        default=Path("/Users/laura/Desktop/rnagenesis-aptamer-mres-private"),
    )
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    summary, manifest, report = build_analysis(args.repo.resolve(), args.private_root.resolve())
    if args.check_only:
        print(json.dumps({"status": summary["status"], "checks": manifest["checks"]}, sort_keys=True))
        return
    output = write_outputs(args.repo.resolve(), summary, manifest, report)
    print(output)


if __name__ == "__main__":
    main()

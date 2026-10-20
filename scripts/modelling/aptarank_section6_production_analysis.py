#!/usr/bin/env python3
"""Validate and summarize one production Section 6 Tier 1 EVAL export.

The frozen Section 6 modules remain unchanged. This adapter binds their
prespecified validation and statistics to exact production artifacts, emits
aggregate-only public outputs, and leaves final result commitment explicit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import aptarank_section6_analysis as analysis
import aptarank_section6_prepare_upload as preparation


PLAN_SHA256 = "ebb0e66dd35c7ed20abecacf710ea7a90dd0e2737ba1973af66e8f0753e22c9d"
ANALYSIS_SHA256 = "f4051c232d1a5be0c12fc959006957c439973e67baf32e4e3fdd31544f0ae3bf"
UPLOAD_SHA256 = "5554f68fd94d1754ff9bcc87fba81be7dc8391af7e45703400796f4a5a336ad2"
PRIVATE_KEY_SHA256 = "be1a40990875a3d02bcdf3ebed6a6a5fb57104fa93f78df41c2ca544b7dc8408"
RUN_SHEET_SHA256 = "069e68885436432ab8fa5a71b72aaab7c67dedacfec70a4917c2f8a4df71c057"
STATUS = "PROVISIONAL_SECTION6_ANALYSIS_AWAITING_EXPLICIT_RESULT_COMMITMENT"
EXCLUSION_COLUMNS = ("row", "id", "sequence", "reason")
CANDIDATE_TOKEN = re.compile(rb"cand_[0-9a-f]{32}")


class ProductionAnalysisError(ValueError):
    """Fail-closed production analysis error."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def read_pinned(path: Path, expected_sha256: str, role: str) -> bytes:
    payload = path.read_bytes()
    observed = sha256_bytes(payload)
    if observed != expected_sha256:
        raise ProductionAnalysisError(
            f"{role} SHA-256 mismatch: expected {expected_sha256}, observed {observed}"
        )
    return payload


def parse_exclusions(payload: bytes) -> list[dict[str, str]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProductionAnalysisError("exclusion register is not UTF-8") from exc
    reader = csv.DictReader(text.splitlines())
    if tuple(reader.fieldnames or ()) != EXCLUSION_COLUMNS:
        raise ProductionAnalysisError("exclusion register header is unexpected")
    rows = list(reader)
    if not rows:
        raise ProductionAnalysisError("exclusion register is empty")
    failures = []
    seen = set()
    for row in rows:
        candidate_id = row["id"]
        reason = row["reason"].strip()
        if candidate_id in seen:
            raise ProductionAnalysisError("exclusion register contains a duplicate candidate id")
        if not reason:
            raise ProductionAnalysisError("exclusion register contains an empty reason")
        seen.add(candidate_id)
        failures.append({"candidate_id": candidate_id, "reason": reason})
    return failures


def as_fraction(token: str | int | float) -> Fraction:
    if isinstance(token, int):
        return Fraction(token)
    if isinstance(token, float):
        return Fraction(Decimal(str(token)))
    if "/" in token:
        return Fraction(token)
    return Fraction(Decimal(token))


def decimal_text(token: str | int | float, places: int = 3) -> str:
    return f"{float(as_fraction(token)):.{places}f}"


def percent_text(token: str | int | float, places: int = 1) -> str:
    return f"{100 * float(as_fraction(token)):.{places}f}%"


def validate_production_denominators(summary: dict[str, object]) -> None:
    denominators = summary["denominators"]
    expected = {
        "input_candidates": 308,
        "evaluable_scores": 306,
        "technical_failures": 2,
        "complete_score_pairs": 153,
        "incomplete_score_pairs": 1,
        "pre_rejection_clusters": 79,
        "clusters_with_complete_score_pairs": 79,
        "paired_shuffle_pairs": 153,
        "imputed_replicates": 0,
    }
    for key, value in expected.items():
        if denominators.get(key) != value:
            raise ProductionAnalysisError(
                f"production denominator {key} is {denominators.get(key)!r}, expected {value!r}"
            )
    expected_by_class = {"eval_core": 153, "paired_uniform_shuffle": 153}
    if denominators.get("evaluable_scores_by_class") != expected_by_class:
        raise ProductionAnalysisError("evaluable class denominators are unexpected")
    if denominators.get("shuffle_valid_by_class") != expected_by_class:
        raise ProductionAnalysisError("shuffle-valid class denominators are unexpected")
    if denominators.get("bootstrap_replicates") != 10000:
        raise ProductionAnalysisError("bootstrap replicate count is unexpected")
    for count in denominators.get("bootstrap_defined_replicates", {}).values():
        if count != 10000:
            raise ProductionAnalysisError("a bootstrap target has fewer than 10,000 defined replicates")
    for count in denominators.get("bootstrap_undefined_replicates", {}).values():
        if count != 0:
            raise ProductionAnalysisError("a bootstrap target has undefined replicates")


def aggregate_result(summary: dict[str, object], generated_at_utc: str) -> dict[str, object]:
    return {
        "status": STATUS,
        "generated_at_utc": generated_at_utc,
        "governing_plan": {"version": "3.5", "section": 6, "sha256": PLAN_SHA256},
        "production_run": True,
        "scientific_result_committed": False,
        "scorer_owner": "deployed AptaRank UI",
        "scores_recomputed": False,
        "favourable_direction": summary["favourable_direction"],
        "denominators": summary["denominators"],
        "class_summaries": summary["class_summaries"],
        "paired": summary["paired"],
        "auroc": summary["auroc"],
        "shuffle": summary["shuffle"],
        "secondary_test": summary["secondary_test"],
        "bootstrap": summary["bootstrap"],
        "analyzed_bytes": summary["analyzed_bytes"],
        "raw_run_artifacts": summary["raw_run_artifacts"],
        "five_component_table": summary["five_component_table"],
        "interpretation_limits": [
            "uniform RNA is a synthetic floor, not an experimental non-binder",
            "AUROC is descriptive against the paired uniform null, not universal aptamer classification",
            "AptaRank scores are computational prioritisation evidence, not binding or functional validation",
            "the five-component descriptive table is unavailable because no verified deployed component export exists",
            "two technical exclusions removed one complete matched pair and were not replaced",
        ],
    }


def render_report(result: dict[str, object]) -> bytes:
    d = result["denominators"]
    classes = result["class_summaries"]
    real = classes["eval_core"]
    control = classes["paired_uniform_shuffle"]
    paired = result["paired"]
    auroc = result["auroc"]
    shuffle = result["shuffle"]
    secondary = result["secondary_test"]
    bootstrap = result["bootstrap"]
    paired_ci = bootstrap["paired_median_difference"]["interval"]
    auroc_ci = bootstrap["auroc"]["interval"]
    pass_ci = bootstrap["paired_shuffle_pass_difference"]["interval"]
    text = f"""# Section 6 Tier 1 EVAL provisional analysis

Status: `{STATUS}`

## Technical accounting

- Input candidates: {d['input_candidates']}
- Evaluable scores: {d['evaluable_scores']} ({d['evaluable_scores_by_class']['eval_core']} EVAL cores; {d['evaluable_scores_by_class']['paired_uniform_shuffle']} paired controls)
- Technical exclusions: {d['technical_failures']}; one complete matched pair, with no replacement
- Complete score pairs: {d['complete_score_pairs']}
- Pre-rejection clusters represented among complete pairs: {d['clusters_with_complete_score_pairs']} of {d['pre_rejection_clusters']}
- Cluster bootstrap: {d['bootstrap_replicates']} replicates; zero undefined or imputed replicates for every target

## Aptamer-likeness

| Group | n | Mean | Median | Q1 | Q3 | IQR |
|---|---:|---:|---:|---:|---:|---:|
| EVAL core | {real['count']} | {decimal_text(real['mean'])} | {decimal_text(real['median'])} | {decimal_text(real['q1'])} | {decimal_text(real['q3'])} | {decimal_text(real['iqr'])} |
| Paired uniform control | {control['count']} | {decimal_text(control['mean'])} | {decimal_text(control['median'])} | {decimal_text(control['q1'])} | {decimal_text(control['q3'])} | {decimal_text(control['iqr'])} |

- Median paired difference, EVAL minus control: {decimal_text(paired['median_difference'])} (cluster-bootstrap 95% CI {decimal_text(paired_ci['low'])} to {decimal_text(paired_ci['high'])}).
- Mean paired difference: {decimal_text(paired['mean_difference'])}.
- Descriptive AUROC against the paired uniform null: {decimal_text(auroc['value'])} (cluster-bootstrap 95% CI {decimal_text(auroc_ci['low'])} to {decimal_text(auroc_ci['high'])}).
- Secondary Wilcoxon signed-rank test: W+ = {secondary['statistic']}, two-sided p = {secondary['p_value']:.6g}; zeros discarded, average ranks for ties, normal approximation without continuity correction.

The frozen REF-calibrated Tier 1 score distinguishes EVAL cores from their exact-length uniform controls in this comparison. The effect is positive and moderate rather than near-perfect. AUROC is descriptive for this synthetic null and is not a universal aptamer classifier.

## Candidate-specific shuffle checks

- EVAL cores passing: {d['shuffle_pass_by_class']['eval_core']}/{d['shuffle_valid_by_class']['eval_core']} ({percent_text(shuffle['real_pass_rate'])}).
- Uniform controls passing: {d['shuffle_pass_by_class']['paired_uniform_shuffle']}/{d['shuffle_valid_by_class']['paired_uniform_shuffle']} ({percent_text(shuffle['control_pass_rate'])}).
- Paired pass-rate difference, EVAL minus control: {percent_text(shuffle['paired_pass_difference'])} (cluster-bootstrap 95% CI {percent_text(pass_ci['low'])} to {percent_text(pass_ci['high'])}).

Shuffle-pass sensitivity is low in both groups, and the paired difference is uncertain and compatible with no difference. The positive composite-score separation must not be described as broad success against the stronger dinucleotide-preserving null.

## Availability and interpretation limits

The production five-component table is unavailable because the UI did not provide a verified component-level export. Component values were not recomputed locally.

AptaRank scores are computational prioritisation evidence. They do not demonstrate binding, affinity, specificity, inhibition, target recognition or experimental function. Uniform RNA is a synthetic floor rather than an experimental non-binder. Final result commitment remains subject to explicit approval.
"""
    return text.encode("utf-8")


def ensure_public(payloads: dict[str, bytes], private_key: bytes) -> None:
    forbidden = (private_key,)
    for role, payload in payloads.items():
        if CANDIDATE_TOKEN.search(payload):
            raise ProductionAnalysisError(f"opaque candidate id leaked into public output {role}")
        if any(token in payload for token in forbidden):
            raise ProductionAnalysisError(f"restricted private-key bytes leaked into public output {role}")


def analyze(arguments: argparse.Namespace) -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    read_pinned(root / "scripts/modelling/aptarank_section6_analysis.py", ANALYSIS_SHA256, "analysis module")
    upload = read_pinned(arguments.upload, UPLOAD_SHA256, "candidate upload")
    private_key = read_pinned(arguments.private_key, PRIVATE_KEY_SHA256, "private key")
    run_sheet_bytes = read_pinned(arguments.run_sheet, RUN_SHEET_SHA256, "run sheet")
    export = arguments.export.read_bytes()
    exclusions = arguments.exclusions.read_bytes()
    result_page = arguments.result_page.read_bytes()
    failures = parse_exclusions(exclusions)
    run_sheet = json.loads(run_sheet_bytes.decode("utf-8"))
    summary = analysis.summarize_section6(
        upload,
        private_key,
        export,
        failures=failures,
        run_sheet=run_sheet,
        raw_artifacts=[
            {"role": "excluded_sequences_register", "available": True, "payload": exclusions},
            {"role": "result_page_pdf", "available": True, "payload": result_page},
            {"role": "five_component_export", "available": False},
            {"role": "ui_log", "available": False},
        ],
    )
    validate_production_denominators(summary)
    generated_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result = aggregate_result(summary, generated_at_utc)
    result_bytes = canonical_json_bytes(result)
    report_bytes = render_report(result)
    public = {
        "analysis_summary.json": result_bytes,
        "section6_tier1_results.md": report_bytes,
    }
    manifest = {
        "status": STATUS,
        "generated_at_utc": generated_at_utc,
        "inputs": {
            "candidate_upload": summary["analyzed_bytes"]["candidate_upload"],
            "downloaded_export": summary["analyzed_bytes"]["downloaded_export"],
            "private_key": {"sha256": sha256_bytes(private_key), "byte_count": len(private_key)},
            "run_sheet": {"sha256": sha256_bytes(run_sheet_bytes), "byte_count": len(run_sheet_bytes)},
            "exclusion_register": {"sha256": sha256_bytes(exclusions), "byte_count": len(exclusions)},
            "result_page_pdf": {"sha256": sha256_bytes(result_page), "byte_count": len(result_page)},
        },
        "method": {"analysis_module_sha256": ANALYSIS_SHA256, "scores_recomputed": False},
        "outputs": {
            name: {"sha256": sha256_bytes(payload), "byte_count": len(payload)}
            for name, payload in sorted(public.items())
        },
    }
    public["analysis_manifest.json"] = canonical_json_bytes(manifest)
    ensure_public(public, private_key)
    public["SHA256SUMS"] = preparation.sha256sums(public)
    preparation.publish(arguments.output, {name: (payload, 0o644) for name, payload in public.items()})
    return {
        "status": "PASS",
        "output": str(arguments.output),
        "downloaded_export": summary["analyzed_bytes"]["downloaded_export"],
        "denominators": summary["denominators"],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload", required=True, type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--export", required=True, type=Path)
    parser.add_argument("--exclusions", required=True, type=Path)
    parser.add_argument("--run-sheet", required=True, type=Path)
    parser.add_argument("--result-page", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    report = analyze(arguments)
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ProductionAnalysisError, analysis.Section6Error, preparation.PreparationError, OSError, csv.Error, json.JSONDecodeError) as exc:
        sys.stderr.write(f"section6_production_analysis_failed: {exc}\n")
        raise SystemExit(1)

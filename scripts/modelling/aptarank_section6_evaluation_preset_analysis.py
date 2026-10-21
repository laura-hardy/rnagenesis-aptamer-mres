#!/usr/bin/env python3
"""Validate and summarize the same-input rigorous Section 6 rerun.

This adapter changes no statistical method. It binds the frozen Section 6
analysis to the exact Evaluation-preset run sheet and raw downloads, writes
aggregate-only public outputs, and leaves review and result commitment open.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import aptarank_section6_analysis as analysis
import aptarank_section6_prepare_upload as preparation
import aptarank_section6_production_analysis as historical


PLAN_SHA256 = "24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9"
ANALYSIS_SHA256 = "f4051c232d1a5be0c12fc959006957c439973e67baf32e4e3fdd31544f0ae3bf"
HISTORICAL_ADAPTER_SHA256 = "db0127ec0c245e187a482dc2c00330dccc1b0d9e8e28f8bfdca1d87f80317286"
PREPARATION_SHA256 = "a9413fc4874d8a54e522cc37c618c3d7fb0116fae18f5ac1bc694219864e629c"
UPLOAD_SHA256 = "5554f68fd94d1754ff9bcc87fba81be7dc8391af7e45703400796f4a5a336ad2"
PRIVATE_KEY_SHA256 = "be1a40990875a3d02bcdf3ebed6a6a5fb57104fa93f78df41c2ca544b7dc8408"
RUN_SHEET_SHA256 = "0dbe9ab773d68537605990d50df1cc50e4f5c8080118b3d6e25d5f683603db0f"
RAW_MANIFEST_SHA256 = "87380a7adb8e8f698cb1db320dea8b07f0d5a8548f947c8e0a790deeed5e99c0"
EXPORT_SHA256 = "e5db367e2f2ea9e6f023db32345533d1a7a09a26996166700ed02c4cd6e97e4c"
EXCLUSIONS_SHA256 = "91ff501e648389b2c8234c0bd2460ea8a8c2d63ccf56a37c8079abc2b82d3d3e"
RESULT_PAGE_SHA256 = "e511504b1f912c26950ba3702de6ef7c102cff0219ba8cb7e9d0c736af05fd46"
STATUS = "PROVISIONAL_SECTION6_EVALUATION_PRESET_ANALYSIS_AWAITING_INDEPENDENT_REVIEW_AND_EXPLICIT_RESULT_COMMITMENT"
RUN_SHEET_VALIDATION_OWNER = "v3.7_evaluation_preset_adapter"
CANDIDATE_TOKEN = re.compile(rb"cand_[0-9a-f]{32}")


class RigorousAnalysisError(ValueError):
    """Fail-closed rigorous rerun analysis error."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_pinned(path: Path, expected_sha256: str, role: str) -> bytes:
    payload = path.read_bytes()
    observed = sha256_bytes(payload)
    if observed != expected_sha256:
        raise RigorousAnalysisError(
            f"{role} SHA-256 mismatch: expected {expected_sha256}, observed {observed}"
        )
    return payload


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_run_sheet(run_sheet: dict[str, object]) -> None:
    expected = {
        "preset": "Evaluation",
        "preset_role": "paper_rigorous_mode",
        "seed": 42,
        "candidate_shuffles": 99,
        "sampled_structures": 200,
        "protein_target": None,
        "expected_compatibility_token": "not evaluated",
    }
    for key, value in expected.items():
        if run_sheet.get(key) != value:
            raise RigorousAnalysisError(
                f"run-sheet {key} is {run_sheet.get(key)!r}, expected {value!r}"
            )


def aggregate_result(summary: dict[str, object], generated_at_utc: str) -> dict[str, object]:
    return {
        "status": STATUS,
        "generated_at_utc": generated_at_utc,
        "governing_plan": {"version": "3.7", "section": 6, "sha256": PLAN_SHA256},
        "production_run": True,
        "scientific_result_committed": False,
        "independent_review_complete": False,
        "scorer_owner": "deployed AptaRank UI",
        "scores_recomputed": False,
        "preset": {
            "ui_name": "Evaluation",
            "role": "paper_rigorous_mode",
            "seed": 42,
            "candidate_shuffles": 99,
            "sampled_structures": 200,
            "sampled_structures_source": "pinned_run_sheet_not_independently_displayed_in_result_pdf",
        },
        "lineage": {
            "historical_standard_result": "results/aptarank/evaluation/section6_tier1_eval_v1",
            "same_candidate_upload": True,
            "same_private_key_pairs_clusters_and_controls": True,
            "results_pooled": False,
            "result_selected_by_favourability": False,
            "only_intended_method_change": "Standard_to_Evaluation_preset",
            "run_sheet_validation_owner": RUN_SHEET_VALIDATION_OWNER,
            "frozen_standard_only_run_sheet_gate_invoked": False,
            "reason": "the frozen module accepts only the historical Standard template; v3.7 requires strict Evaluation-preset validation before unchanged calculations",
        },
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
            "the historical Standard result is preserved separately and is not pooled with this rerun",
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
    text = f"""# Section 6 Tier 1 EVAL rigorous rerun: provisional analysis

Status: `{STATUS}`

## Run identity and technical accounting

- Named UI preset: Evaluation (paper rigorous mode)
- Frozen run-sheet settings: seed 42, 99 candidate shuffles and 200 sampled structures
- Input candidates: {d['input_candidates']}
- Evaluable scores: {d['evaluable_scores']} ({d['evaluable_scores_by_class']['eval_core']} EVAL cores; {d['evaluable_scores_by_class']['paired_uniform_shuffle']} paired controls)
- Technical exclusions: {d['technical_failures']}; one complete matched pair, with no replacement
- Complete score pairs: {d['complete_score_pairs']}
- Pre-rejection clusters represented among complete pairs: {d['clusters_with_complete_score_pairs']} of {d['pre_rejection_clusters']}
- Cluster bootstrap: {d['bootstrap_replicates']} replicates; zero undefined or imputed replicates for every target

The candidate upload, private key, pair and cluster membership, controls, exclusions and estimands are unchanged from the historical Standard run. The runs are not pooled.

## Aptamer-likeness

| Group | n | Mean | Median | Q1 | Q3 | IQR |
|---|---:|---:|---:|---:|---:|---:|
| EVAL core | {real['count']} | {historical.decimal_text(real['mean'])} | {historical.decimal_text(real['median'])} | {historical.decimal_text(real['q1'])} | {historical.decimal_text(real['q3'])} | {historical.decimal_text(real['iqr'])} |
| Paired uniform control | {control['count']} | {historical.decimal_text(control['mean'])} | {historical.decimal_text(control['median'])} | {historical.decimal_text(control['q1'])} | {historical.decimal_text(control['q3'])} | {historical.decimal_text(control['iqr'])} |

- Median paired difference, EVAL minus control: {historical.decimal_text(paired['median_difference'])} (cluster-bootstrap 95% CI {historical.decimal_text(paired_ci['low'])} to {historical.decimal_text(paired_ci['high'])}).
- Mean paired difference: {historical.decimal_text(paired['mean_difference'])}.
- Descriptive AUROC against the paired uniform null: {historical.decimal_text(auroc['value'])} (cluster-bootstrap 95% CI {historical.decimal_text(auroc_ci['low'])} to {historical.decimal_text(auroc_ci['high'])}).
- Secondary Wilcoxon signed-rank test: W+ = {secondary['statistic']}, two-sided p = {secondary['p_value']:.6g}; zeros discarded, average ranks for ties, normal approximation without continuity correction.

## Candidate-specific shuffle checks

- EVAL cores passing: {d['shuffle_pass_by_class']['eval_core']}/{d['shuffle_valid_by_class']['eval_core']} ({historical.percent_text(shuffle['real_pass_rate'])}).
- Uniform controls passing: {d['shuffle_pass_by_class']['paired_uniform_shuffle']}/{d['shuffle_valid_by_class']['paired_uniform_shuffle']} ({historical.percent_text(shuffle['control_pass_rate'])}).
- Paired pass-rate difference, EVAL minus control: {historical.percent_text(shuffle['paired_pass_difference'])} (cluster-bootstrap 95% CI {historical.percent_text(pass_ci['low'])} to {historical.percent_text(pass_ci['high'])}).

## Interpretation boundary

This is a provisional calculation awaiting independent review and explicit scientific result commitment. The five-component table is unavailable because no verified component-level export was provided; no component was recomputed. AptaRank scores are computational prioritisation evidence and do not demonstrate binding, affinity, specificity, inhibition, target recognition or experimental function. Uniform RNA is a synthetic floor rather than an experimental non-binder.
"""
    return text.encode("utf-8")


def ensure_public(payloads: dict[str, bytes], private_key: bytes) -> None:
    for role, payload in payloads.items():
        if CANDIDATE_TOKEN.search(payload):
            raise RigorousAnalysisError(f"opaque candidate id leaked into public output {role}")
        if private_key in payload:
            raise RigorousAnalysisError(f"restricted private-key bytes leaked into public output {role}")


def analyze(arguments: argparse.Namespace) -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    read_pinned(root / "docs/aptarank_full_mres_thesis_evaluation_plan_v3_7.md", PLAN_SHA256, "governing plan")
    read_pinned(root / "scripts/modelling/aptarank_section6_analysis.py", ANALYSIS_SHA256, "analysis module")
    read_pinned(root / "scripts/modelling/aptarank_section6_production_analysis.py", HISTORICAL_ADAPTER_SHA256, "historical adapter")
    read_pinned(root / "scripts/modelling/aptarank_section6_prepare_upload.py", PREPARATION_SHA256, "preparation module")
    upload = read_pinned(arguments.upload, UPLOAD_SHA256, "candidate upload")
    private_key = read_pinned(arguments.private_key, PRIVATE_KEY_SHA256, "private key")
    run_sheet_bytes = read_pinned(arguments.run_sheet, RUN_SHEET_SHA256, "run sheet")
    read_pinned(arguments.raw_manifest, RAW_MANIFEST_SHA256, "raw artifact manifest")
    export = read_pinned(arguments.export, EXPORT_SHA256, "downloaded export")
    exclusions = read_pinned(arguments.exclusions, EXCLUSIONS_SHA256, "exclusion register")
    result_page = read_pinned(arguments.result_page, RESULT_PAGE_SHA256, "result page PDF")

    run_sheet = json.loads(run_sheet_bytes.decode("utf-8"))
    validate_run_sheet(run_sheet)
    failures = historical.parse_exclusions(exclusions)
    summary = analysis.summarize_section6(
        upload,
        private_key,
        export,
        failures=failures,
        # The frozen method module's run-sheet gate intentionally accepts only
        # the historical Standard template. The v3.7 adapter has already
        # pinned and strictly validated Evaluation/42/99/200 above. Passing no
        # run sheet here leaves every score, join, rank, exclusion, statistic,
        # bootstrap and artifact check unchanged without mislabelling the run.
        run_sheet=None,
        raw_artifacts=[
            {"role": "excluded_sequences_register", "available": True, "payload": exclusions},
            {"role": "result_page_pdf", "available": True, "payload": result_page},
            {"role": "five_component_export", "available": False},
            {"role": "ui_log", "available": False},
        ],
    )
    historical.validate_production_denominators(summary)
    generated_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result = aggregate_result(summary, generated_at_utc)
    public = {
        "analysis_summary.json": canonical_json_bytes(result),
        "section6_tier1_rigorous_results.md": render_report(result),
    }
    manifest = {
        "status": STATUS,
        "generated_at_utc": generated_at_utc,
        "inputs": {
            "candidate_upload": summary["analyzed_bytes"]["candidate_upload"],
            "downloaded_export": summary["analyzed_bytes"]["downloaded_export"],
            "private_key": {"sha256": sha256_bytes(private_key), "byte_count": len(private_key)},
            "run_sheet": {"sha256": sha256_bytes(run_sheet_bytes), "byte_count": len(run_sheet_bytes)},
            "raw_artifact_manifest": {"sha256": RAW_MANIFEST_SHA256},
            "exclusion_register": {"sha256": sha256_bytes(exclusions), "byte_count": len(exclusions)},
            "result_page_pdf": {"sha256": sha256_bytes(result_page), "byte_count": len(result_page)},
        },
        "method": {
            "analysis_module_sha256": ANALYSIS_SHA256,
            "historical_adapter_sha256": HISTORICAL_ADAPTER_SHA256,
            "run_sheet_validation_owner": RUN_SHEET_VALIDATION_OWNER,
            "frozen_standard_only_run_sheet_gate_invoked": False,
            "statistical_method_changed": False,
            "scores_recomputed": False,
        },
        "lineage": result["lineage"],
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
        "point_estimates": {
            "paired_median_difference": summary["paired"]["median_difference"],
            "auroc": summary["auroc"]["value"],
            "eval_shuffle_pass_rate": summary["shuffle"]["real_pass_rate"],
            "control_shuffle_pass_rate": summary["shuffle"]["control_pass_rate"],
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload", required=True, type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--export", required=True, type=Path)
    parser.add_argument("--exclusions", required=True, type=Path)
    parser.add_argument("--run-sheet", required=True, type=Path)
    parser.add_argument("--raw-manifest", required=True, type=Path)
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
    except (
        RigorousAnalysisError,
        historical.ProductionAnalysisError,
        analysis.Section6Error,
        preparation.PreparationError,
        OSError,
        csv.Error,
        json.JSONDecodeError,
    ) as exc:
        sys.stderr.write(f"section6_evaluation_preset_analysis_failed: {exc}\n")
        raise SystemExit(1)

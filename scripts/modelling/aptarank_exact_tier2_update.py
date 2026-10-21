#!/usr/bin/env python3
"""Validate and summarize later-discovered exact AptaRank Tier 2 exports.

The browser application remains the scorer. This adapter preserves the
previous Section 8 closure and Section 9 analysis, re-runs their existing
validation gates, and joins untouched exact-score exports by opaque candidate
ID. It writes only aggregate, sequence-free supplemental outputs. It neither
reconstructs a Tier 2 score nor creates a combined Tier 1/Tier 2 score.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

import aptarank_section8_validate_results as section8
import aptarank_section9_analyze_results as section9


SECTION8_STATUS = (
    "PROVISIONAL_SECTION8_EXACT_TIER2_SUPPLEMENT_"
    "AWAITING_INDEPENDENT_REVIEW_AND_EXPLICIT_RECOMMITMENT"
)
SECTION9_STATUS = section9.STATUS
EXACT_FIELDS = (
    "",
    "candidate",
    "rank",
    "tier1",
    "control_percentile",
    "mismatch",
    "band",
    "selected",
)
EXACT_RAW = {
    "grk2_pocket": {
        "relative": (
            "results/aptarank/evaluation/section8_grk2_3uzs_evaluation_preset_v1/"
            "supplemental_exact_tier2_v1/raw/section8_3uzs.csv"
        ),
        "sha256": "9845ba9cc1fbbd713ce9be5316a0a6911b0c378bfb58cfac347efad01bc9fe57",
    },
    "hewl_surface": {
        "relative": (
            "results/aptarank/evaluation/section8_lysozyme_4m4o_evaluation_preset_v1/"
            "supplemental_exact_tier2_v1/raw/section8_4m4o.csv"
        ),
        "sha256": "6fa421f8c2b0b1981324884d84b3c5e24bfad48805c4350ed724dcf9e1626cd2",
    },
    "section9": {
        "relative": (
            "results/aptarank/evaluation/section9_generated_conditions_ndm1_evaluation_preset_v1/"
            "supplemental_exact_tier2_v1/raw/section9_ndm1.csv"
        ),
        "sha256": "6d0255ea827bf2e2156873737a59eee3f7c7aa54e02f5ff2dc60315aa617def0",
    },
}
PINNED_HISTORICAL = {
    "section8_validation_summary": (
        "results/aptarank/evaluation/section8_two_target_panel_evaluation_preset_v1/"
        "validation_v1/section8_validation_summary.json",
        "163f1f1b0b994015ee9f6827064142ae3ead4905743eba04a1b61fdfa8db1218",
    ),
    "section8_interpretation": (
        "results/aptarank/evaluation/section8_two_target_panel_evaluation_preset_v1/"
        "interpretation_v1/interpretation_record.json",
        "70ed1bce9a1b8985d34d03ff212a4b7b4514a1916886d9c040987e1110191bf7",
    ),
    "section8_closure": (
        "results/aptarank/evaluation/section8_two_target_panel_evaluation_preset_v1/"
        "closure/section8_closure_record.json",
        "7de67471948c0630595342879c5da4fd091442271cf462321fc624eb139b5da8",
    ),
    "section9_analysis_v1_summary": (
        "results/aptarank/evaluation/section9_generated_conditions_ndm1_evaluation_preset_v1/"
        "derived/analysis_v1/analysis_summary.json",
        "391e4cc2489965aa8465ff2c6eb99d9adac7b9f908aa50d6686dfcecec4c109f",
    ),
    "section9_analysis_v1_manifest": (
        "results/aptarank/evaluation/section9_generated_conditions_ndm1_evaluation_preset_v1/"
        "derived/analysis_v1/analysis_manifest.json",
        "1c94133aef4372aaee84843665c5f68528eed0312ece9fb10d5539584da4d51a",
    ),
}
CANDIDATE_TOKEN_BYTES = re.compile(rb"cand_[0-9a-f]{32}")


class ExactTier2UpdateError(ValueError):
    """Raised when an exact-score export or its lineage fails validation."""


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def read_pinned(repo: Path, relative: str, digest: str, role: str) -> bytes:
    path = repo / relative
    payload = path.read_bytes()
    observed = section9.sha256_bytes(payload)
    if observed != digest:
        raise ExactTier2UpdateError(
            f"{role} hash mismatch: expected {digest}, observed {observed}"
        )
    return payload


def decimal_value(text: str, role: str, *, unit_interval: bool = False) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ExactTier2UpdateError(f"{role} is not a decimal") from exc
    if not value.is_finite() or (unit_interval and not Decimal(0) <= value <= Decimal(1)):
        raise ExactTier2UpdateError(f"{role} is outside its valid range")
    return value


def parse_exact_export(payload: bytes, expected_n: int) -> list[dict[str, object]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ExactTier2UpdateError("exact Tier 2 export is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != EXACT_FIELDS:
        raise ExactTier2UpdateError("exact Tier 2 export fields drifted")
    raw = list(reader)
    if len(raw) != expected_n:
        raise ExactTier2UpdateError("exact Tier 2 export row count drifted")
    rows: list[dict[str, object]] = []
    for index, row in enumerate(raw):
        if None in row or any(value is None for value in row.values()):
            raise ExactTier2UpdateError("exact Tier 2 export contains a malformed row")
        try:
            exported_index, rank = int(row[""]), int(row["rank"])
        except ValueError as exc:
            raise ExactTier2UpdateError("exact Tier 2 index or rank is not an integer") from exc
        if exported_index != index or rank != index + 1:
            raise ExactTier2UpdateError("exact Tier 2 row index or rank is incomplete")
        band = row["band"]
        percentile = decimal_value(row["control_percentile"], "control percentile", unit_interval=True)
        if band not in section9.COMPATIBILITY:
            raise ExactTier2UpdateError("exact Tier 2 band is invalid")
        expected_band = "strong" if percentile >= Decimal("0.95") else "moderate" if percentile >= Decimal("0.75") else "weak"
        if band != expected_band:
            raise ExactTier2UpdateError("exact Tier 2 band does not follow the displayed thresholds")
        if row["selected"] not in {"true", "false"}:
            raise ExactTier2UpdateError("exact Tier 2 selected marker is invalid")
        rows.append({
            "candidate": row["candidate"],
            "rank": rank,
            "tier1": decimal_value(row["tier1"], "Tier 1 score", unit_interval=True),
            "control_percentile": percentile,
            "mismatch": decimal_value(row["mismatch"], "mismatch"),
            "band": band,
            "selected": row["selected"] == "true",
        })
    if len({row["candidate"] for row in rows}) != expected_n:
        raise ExactTier2UpdateError("exact Tier 2 candidate IDs are duplicated")
    return rows


def reconcile_exact(
    exact: list[dict[str, object]],
    validated: list[dict[str, object]],
) -> None:
    if len(exact) != len(validated):
        raise ExactTier2UpdateError("exact and validated exports have different denominators")
    for exact_row, old_row in zip(exact, validated):
        if (
            exact_row["candidate"] != old_row["candidate"]
            or exact_row["rank"] != old_row["rank"]
            or exact_row["tier1"] != old_row["score"]
            or exact_row["band"] != old_row["compatibility"]
        ):
            raise ExactTier2UpdateError("exact Tier 2 export does not reconcile to the original export")


def summarize_percentiles(rows: list[dict[str, object]]) -> dict[str, object]:
    values = [row["control_percentile"] for row in rows]
    with localcontext() as context:
        context.prec = 50
        mean = sum(values, Decimal(0)) / Decimal(len(values))
    bands = Counter(str(row["band"]) for row in rows)
    return {
        "n": len(rows),
        "control_percentile": {
            "minimum": section9.decimal_text(min(values)),
            "q1_type7": section9.decimal_text(section9.quantile_type7(values, Decimal("0.25"))),
            "median_type7": section9.decimal_text(section9.quantile_type7(values, Decimal("0.5"))),
            "mean": section9.decimal_text(mean),
            "q3_type7": section9.decimal_text(section9.quantile_type7(values, Decimal("0.75"))),
            "maximum": section9.decimal_text(max(values)),
        },
        "compatibility": {band: bands[band] for band in section9.COMPATIBILITY},
        "strong_or_moderate": bands["strong"] + bands["moderate"],
    }


def average_ranks(values: list[Decimal]) -> list[Decimal]:
    ordered = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [Decimal(0)] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        average = (Decimal(start + 1) + Decimal(end)) / Decimal(2)
        for position in range(start, end):
            ranks[ordered[position]] = average
        start = end
    return ranks


def spearman_rho(left: list[Decimal], right: list[Decimal]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ExactTier2UpdateError("Spearman inputs have invalid denominators")
    x, y = average_ranks(left), average_ranks(right)
    mean_x = sum(x, Decimal(0)) / Decimal(len(x))
    mean_y = sum(y, Decimal(0)) / Decimal(len(y))
    covariance = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    variance_x = sum((a - mean_x) ** 2 for a in x)
    variance_y = sum((b - mean_y) ** 2 for b in y)
    if not variance_x or not variance_y:
        raise ExactTier2UpdateError("Spearman correlation is undefined")
    return float(covariance / (variance_x * variance_y).sqrt())


def section8_update(repo: Path, private_root: Path) -> tuple[dict[str, object], dict[str, object], str]:
    historical = {
        role: section9.byte_record(read_pinned(repo, relative, digest, role))
        for role, (relative, digest) in PINNED_HISTORICAL.items()
        if role.startswith("section8_")
    }
    cases = []
    exact_inputs = {}
    for case in section8.CASES:
        old_summary, _, _ = section8.validate_case(repo, private_root, case)
        result_root = repo / str(case["result_directory"])
        upload_bytes = section8.read_pinned(
            repo / str(case["public_package"]) / "upload/candidate_upload.csv",
            str(case["upload_sha256"]),
            "candidate upload",
        )
        _, upload = section8.parse_upload(upload_bytes)
        old_export = section8.read_pinned(
            result_root / "raw" / str(case["export_name"]),
            str(case["export_sha256"]),
            "downloaded shortlist",
        )
        validated = section8.validate_export(old_export, upload)
        exact_spec = EXACT_RAW[str(case["case_id"])]
        exact_bytes = read_pinned(repo, exact_spec["relative"], exact_spec["sha256"], "exact Tier 2 export")
        exact = parse_exact_export(exact_bytes, int(case["core_count"]))
        reconcile_exact(exact, validated)
        exact_inputs[str(case["case_id"])] = {
            "path": exact_spec["relative"],
            **section9.byte_record(exact_bytes),
        }
        cases.append({
            "case_id": case["case_id"],
            "case_label": case["case_label"],
            "target": old_summary["target"],
            "denominators": old_summary["denominators"],
            "rows_in_rank_order": [
                {
                    "rank": row["rank"],
                    "tier1_aptamer_likeness": section9.decimal_text(row["tier1"]),
                    "tier2_control_percentile": section9.decimal_text(row["control_percentile"]),
                    "tier2_mismatch": section9.decimal_text(row["mismatch"]),
                    "compatibility_band": row["band"],
                    "candidate_shuffle": validated[index]["shuffle"],
                    "length": validated[index]["length"],
                }
                for index, row in enumerate(exact)
            ],
            "interpretation": (
                "clearly weak target-compatibility annotation for the single configured GRK2 core"
                if case["case_id"] == "grk2_pocket"
                else "mixed annotations: one weak result and one moderate result only just above the 0.75 threshold"
            ),
        })
    summary = {
        "schema_version": "mres-aptarank-section8-exact-tier2-supplement-v1",
        "status": SECTION8_STATUS,
        "scientific_result_committed": False,
        "historical_section8_closure_preserved": True,
        "scores_recomputed": False,
        "source": "untouched deployed AptaRank exact Tier 1/Tier 2 exports",
        "cases": cases,
        "updated_panel_interpretation": (
            "The exact target-control percentiles sharpen but do not materially change the closed conclusion. "
            "The illustrative panel remains weak to mixed and not confirmatory: GRK2 is weak at 0.106, "
            "the two lysozyme cores are weak at 0.462 and moderate at 0.753, no core is strong, and all "
            "candidate-specific shuffle checks fail."
        ),
        "scope_limits": [
            "target-specific mismatch and percentile values are not compared numerically across GRK2 pocket and lysozyme surface modes",
            "the three cognate cores do not calibrate sensitivity or specificity",
            "no binding, affinity, specificity, inhibition, target-discrimination or experimental-function claim",
        ],
    }
    manifest = {
        "schema_version": "mres-aptarank-section8-exact-tier2-supplement-manifest-v1",
        "status": SECTION8_STATUS,
        "historical_inputs": historical,
        "exact_score_inputs": exact_inputs,
        "checks": {
            "existing_section8_validation_rerun": True,
            "exact_ids_ranks_tier1_and_bands_reconcile": True,
            "control_percentiles_finite_and_in_closed_unit_interval": True,
            "bands_follow_0_75_and_0_95_thresholds": True,
            "scores_recomputed": False,
            "cross_target_numeric_comparison_performed": False,
            "historical_closure_modified": False,
        },
    }
    report = """# Section 8 exact Tier 2 supplemental evidence

Status: `{status}`

This versioned addendum preserves the previously closed Section 8 artifacts. It validates later-discovered untouched scorer exports against the original opaque identifiers, ranks, Tier 1 scores and compatibility bands. The numeric Tier 2 values were exported by AptaRank and were not reconstructed locally.

## GRK2/3UZS pocket case

The single 28-nt cognate core has Tier 1 aptamer-likeness 0.342, target-control percentile 0.106, mismatch 5.678 and a `weak` band. Its candidate-specific shuffle check is `fail`. This is clearly weak target-aware annotation for the configured case, not evidence against experimental binding.

## Lysozyme/4M4O surface case

The 59-nt core has Tier 1 aptamer-likeness 0.673, target-control percentile 0.462, mismatch 1118.838 and a `weak` band. The 45-nt core has Tier 1 aptamer-likeness 0.589, target-control percentile 0.753, mismatch 374.709 and a `moderate` band; its percentile is only 0.003 above the displayed moderate threshold. Both candidate-specific shuffle checks are `fail`.

## Updated interpretation

The quantitative values sharpen but do not materially change the closed conclusion: the two descriptive cognate cases remain weak to mixed and not confirmatory. No core is `strong`, only one is `moderate`, and all three fail their candidate-specific shuffled-control checks. Mismatch magnitudes and control percentiles are target- and mode-specific, so no numerical GRK2-versus-lysozyme comparison is made. These outputs remain computational prioritisation evidence, not evidence of binding, affinity, specificity, inhibition or experimental function.

Independent review and explicit re-approval are required before this addendum updates the committed Section 8 interpretation.
""".format(status=SECTION8_STATUS)
    return summary, manifest, report


def section9_update(repo: Path, private_root: Path) -> tuple[dict[str, object], dict[str, object], str]:
    old_summary, old_manifest, _ = section9.build_analysis(repo, private_root)
    historical = {
        role: section9.byte_record(read_pinned(repo, relative, digest, role))
        for role, (relative, digest) in PINNED_HISTORICAL.items()
        if role.startswith("section9_")
    }
    public_root = repo / section9.PUBLIC_RELATIVE
    private_package = private_root / section9.PRIVATE_RELATIVE
    result_root = repo / section9.RESULT_RELATIVE
    upload = section9.parse_upload(section9.read_pinned(
        public_root / "upload/candidate_upload.csv",
        section9.PINS["upload/candidate_upload.csv"],
        "candidate upload",
    ))
    source = section9.validate_source_key(section9.read_pinned(
        private_package / "source_candidate_key.json",
        section9.PRIVATE_PINS["source_candidate_key.json"],
        "source key",
    ), upload)
    membership = section9.validate_membership_key(section9.read_pinned(
        private_package / "m9b2_private_membership_key.jsonl",
        section9.PRIVATE_PINS["m9b2_private_membership_key.jsonl"],
        "membership key",
    ), source)
    original = section9.validate_export(section9.read_pinned(
        result_root / "raw/run_ndm1_section9_1134.csv",
        section9.RAW_PINS["raw/run_ndm1_section9_1134.csv"],
        "downloaded shortlist",
    ), upload)
    exact_spec = EXACT_RAW["section9"]
    exact_bytes = read_pinned(repo, exact_spec["relative"], exact_spec["sha256"], "Section 9 exact Tier 2 export")
    exact = parse_exact_export(exact_bytes, 800)
    reconcile_exact(exact, original)
    enriched = [{**row, "condition": source[str(row["candidate"])]["condition"]} for row in exact]
    by_condition = {
        condition: summarize_percentiles([row for row in enriched if row["condition"] == condition])
        for condition in section9.CONDITIONS
    }
    subgroup_rows: dict[str, dict[str, list[dict[str, object]]]] = {
        "B1_technical_block": defaultdict(list),
        "D1_training_seed": defaultdict(list),
    }
    for row in enriched:
        key, value = section9.subgroup_label(row, membership)
        if key == "technical_block":
            subgroup_rows["B1_technical_block"][str(value)].append(row)
        elif key == "d1_training_seed":
            subgroup_rows["D1_training_seed"][str(value)].append(row)
    subgroups = {
        family: {label: summarize_percentiles(rows) for label, rows in sorted(groups.items())}
        for family, groups in subgroup_rows.items()
    }

    def comparison(left: str, right: str) -> dict[str, object]:
        lhs, rhs = by_condition[left], by_condition[right]
        return {
            "mean_control_percentile_difference": section9.subtract(
                lhs["control_percentile"]["mean"], rhs["control_percentile"]["mean"]
            ),
            "median_control_percentile_difference": section9.subtract(
                lhs["control_percentile"]["median_type7"], rhs["control_percentile"]["median_type7"]
            ),
            "strong_percentage_point_difference": section9.percentage_points(
                lhs["compatibility"]["strong"], lhs["n"], rhs["compatibility"]["strong"], rhs["n"]
            ),
            "moderate_percentage_point_difference": section9.percentage_points(
                lhs["compatibility"]["moderate"], lhs["n"], rhs["compatibility"]["moderate"], rhs["n"]
            ),
        }

    rho = spearman_rho(
        [row["tier1"] for row in exact],
        [row["control_percentile"] for row in exact],
    )
    if not math.isclose(rho, -0.071883614342812, rel_tol=0, abs_tol=1e-15):
        raise ExactTier2UpdateError("independent Spearman recalculation drifted")
    summary = {
        **old_summary,
        "schema_version": "mres-aptarank-section9-analysis-summary-v2-exact-tier2",
        "status": SECTION9_STATUS,
        "scientific_result_committed": False,
        "supersedes_analysis_version": "analysis_v1",
        "exact_tier2": {
            "source": "untouched deployed AptaRank exact Tier 1/Tier 2 export",
            "scores_recomputed": False,
            "overall": summarize_percentiles(exact),
            "by_condition": by_condition,
            "subgroups": subgroups,
            "prespecified_comparisons": {
                "primary_D1_minus_B1": comparison("D1", "B1"),
                "secondary_D1_minus_B2": comparison("D1", "B2"),
                "external_D1_minus_B0_descriptive_only": comparison("D1", "B0"),
            },
        },
        "tier_relationship": {
            "source": "untouched exact scorer export; p-value retained from result PDF",
            "spearman_rho_recomputed_from_export": rho,
            "spearman_rho_pdf_rounded": -0.072,
            "p_value_pdf": 0.0421,
            "n": 800,
            "numeric_tier2_values_exported": True,
            "scores_locally_reconstructed": False,
            "interpretation": "negligible-magnitude weak negative association; not evidence of biological dependence or independence",
        },
        "updated_interpretation": (
            "Exact control percentiles sharpen but do not materially change the provisional conclusion. "
            "D1 exceeds B1 in mean and median percentile and in moderate-band count, but not in strong-band count; "
            "D1 is only slightly above B2 in mean percentile and has the same median. Tier 1 and Tier 2 remain separate."
        ),
    }
    manifest = {
        "schema_version": "mres-aptarank-section9-analysis-manifest-v2-exact-tier2",
        "status": SECTION9_STATUS,
        "historical_inputs": historical,
        "analysis_v1_revalidated": old_manifest["checks"],
        "exact_score_input": {"path": exact_spec["relative"], **section9.byte_record(exact_bytes)},
        "checks": {
            "existing_section9_analysis_rerun": True,
            "exact_ids_ranks_tier1_and_bands_reconcile": True,
            "control_percentiles_finite_and_in_closed_unit_interval": True,
            "bands_follow_0_75_and_0_95_thresholds": True,
            "condition_and_subgroup_denominators_reconcile": True,
            "spearman_recomputed_from_export": True,
            "scores_reconstructed": False,
            "combined_tier_score_created": False,
            "target_geometry_warning_preserved": summary["target_geometry_limitation"]["warning_exact"] == section9.CAVITY_WARNING,
        },
    }
    report = render_section9_report(summary)
    return summary, manifest, report


def pct(count: int, n: int) -> str:
    return f"{100 * count / n:.1f}%"


def render_section9_report(summary: dict[str, object]) -> str:
    exact = summary["exact_tier2"]
    lines = [
        "# Section 9 generated-condition comparison against NDM-1: exact Tier 2 update",
        "",
        f"Status: `{SECTION9_STATUS}`",
        "",
        "This v2 analysis preserves the validated 800-row accounting and all Tier 1 results from analysis v1, then joins a later-discovered untouched AptaRank exact-score export by opaque candidate ID. The control percentiles are scorer outputs and were not reconstructed locally. Tier 1 and Tier 2 remain separate.",
        "",
        "## Exact target-control percentiles",
        "",
        "| Condition | n | Mean | Median | IQR | Strong | Moderate | Weak |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for condition in section9.CONDITIONS:
        item = exact["by_condition"][condition]
        score = item["control_percentile"]
        bands = item["compatibility"]
        lines.append(
            f"| {condition} | {item['n']} | {Decimal(score['mean']):.3f} | "
            f"{Decimal(score['median_type7']):.3f} | {Decimal(score['q1_type7']):.3f}\u2013{Decimal(score['q3_type7']):.3f} | "
            f"{bands['strong']} ({pct(bands['strong'], item['n'])}) | "
            f"{bands['moderate']} ({pct(bands['moderate'], item['n'])}) | "
            f"{bands['weak']} ({pct(bands['weak'], item['n'])}) |"
        )
    primary = exact["prespecified_comparisons"]["primary_D1_minus_B1"]
    secondary = exact["prespecified_comparisons"]["secondary_D1_minus_B2"]
    lines.extend([
        "",
        "For the primary B1-versus-D1 comparison, D1 has a +0.029 mean and +0.162 median control-percentile difference. Its strong-band rate is 0.5 percentage points lower (10 versus 11 candidates), while its moderate-band rate is 6.0 points higher (46 versus 34). The favourable-band advantage is therefore carried by additional `moderate` annotations, not additional `strong` annotations.",
        "",
        "Relative to B2, D1 has a +0.016 mean percentile difference, the same median percentile, a +0.5-point strong-band difference and a +4.0-point moderate-band difference. B0 remains an external descriptive comparator because its length regime differs.",
        "",
        "## Seed and block descriptives",
        "",
        "| Stratum | n | Mean | Median | Strong | Moderate | Weak |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for family, label in (("B1_technical_block", "B1 block"), ("D1_training_seed", "D1 seed")):
        for subgroup, item in exact["subgroups"][family].items():
            score = item["control_percentile"]
            bands = item["compatibility"]
            lines.append(
                f"| {label} {subgroup} | {item['n']} | {Decimal(score['mean']):.3f} | "
                f"{Decimal(score['median_type7']):.3f} | {bands['strong']} | {bands['moderate']} | {bands['weak']} |"
            )
    rho = summary["tier_relationship"]["spearman_rho_recomputed_from_export"]
    lines.extend([
        "",
        "## Relationship and limits",
        "",
        f"The exact export gives Spearman rho = {rho:.6f} for Tier 1 versus target-control percentile, matching the PDF's rounded -0.072 (PDF p = 0.0421, n = 800). The association is negligible in magnitude and weakly negative. It does not justify a combined score or a biological-dependence claim.",
        "",
        f"> {section9.CAVITY_WARNING}",
        "",
        "The exact scores do not remove this geometric limitation. They distinguish where observations lie inside the target-specific control distribution, but they are not binding probabilities and do not demonstrate affinity, specificity, inhibition, target recognition or experimental function. Candidate rows, technical blocks and generation seeds are not independent training replicates; D1 still has only two training seeds. No Section 9 candidate enters the supervisor-review shortlist.",
        "",
        "The quantitative update therefore sharpens but does not materially change the provisional interpretation. Independent review and explicit result commitment remain pending.",
    ])
    if primary["mean_control_percentile_difference"] != "0.02869321533923303541145":
        raise ExactTier2UpdateError("primary comparison drifted")
    if secondary["median_control_percentile_difference"] != "0":
        raise ExactTier2UpdateError("secondary comparison drifted")
    return "\n".join(lines) + "\n"


def ensure_public(payloads: dict[str, bytes]) -> None:
    for role, payload in payloads.items():
        if CANDIDATE_TOKEN_BYTES.search(payload):
            raise ExactTier2UpdateError(f"opaque candidate ID leaked into {role}")
        if re.search(rb"(?:[ACGU]{20,})", payload):
            raise ExactTier2UpdateError(f"RNA sequence leaked into {role}")


def write_bundle(output: Path, summary: dict[str, object], manifest: dict[str, object], report_name: str, report: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ExactTier2UpdateError(f"output directory is not empty: {output}")
    payloads = {
        "analysis_summary.json": canonical_json(summary),
        "analysis_manifest.json": canonical_json(manifest),
        report_name: report.encode("utf-8"),
    }
    ensure_public(payloads)
    for name, payload in payloads.items():
        (output / name).write_bytes(payload)
    checksums = "".join(
        f"{section9.sha256_bytes(payload)}  {name}\n"
        for name, payload in sorted(payloads.items())
    )
    (output / "SHA256SUMS").write_text(checksums, encoding="ascii", newline="")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--private-root",
        type=Path,
        default=Path("/Users/laura/Desktop/rnagenesis-aptamer-mres-private"),
    )
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    repo, private_root = args.repo.resolve(), args.private_root.resolve()
    s8_private = private_root / "aptarank_eval/section8_two_target_panel_evaluation_preset_v2"
    s8_summary, s8_manifest, s8_report = section8_update(repo, s8_private)
    s9_summary, s9_manifest, s9_report = section9_update(repo, private_root)
    if args.check_only:
        print(json.dumps({
            "section8_status": s8_summary["status"],
            "section9_status": s9_summary["status"],
            "section8_checks": s8_manifest["checks"],
            "section9_checks": s9_manifest["checks"],
        }, sort_keys=True))
        return
    write_bundle(
        repo / (
            "results/aptarank/evaluation/section8_two_target_panel_evaluation_preset_v1/"
            "supplemental_exact_tier2_v1/derived/analysis_v1"
        ),
        s8_summary,
        s8_manifest,
        "section8_exact_tier2_addendum.md",
        s8_report,
    )
    write_bundle(
        repo / section9.RESULT_RELATIVE / "derived/analysis_v2_exact_tier2",
        s9_summary,
        s9_manifest,
        "section9_results.md",
        s9_report,
    )
    print("Section 8 exact-score addendum and Section 9 exact-score v2 written")


if __name__ == "__main__":
    main()

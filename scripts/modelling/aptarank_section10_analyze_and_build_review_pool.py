#!/usr/bin/env python3
"""Validate Section 10 and build the frozen supervisor-review pool.

The deployed AptaRank browser application remains the scorer. This adapter
pins and validates the reviewed 30,000-row upload, restricted provenance,
untouched full-score and exact Tier 2 exports, exclusions, result PDF record,
and prospective v3.8/v3.9 decision rules. It writes sequence-free public
analysis and a local ignored sequence-bearing supervisor package. It does not
run AptaRank, reconstruct a Tier 2 score, change a gate, or make the later
manual supervisor decision.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import stat
from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

try:
    from scripts.modelling import aptarank_candidate_preparation as m9b
    from scripts.modelling import aptarank_section10_prepare_d1_full_pool as preparation
    from scripts.modelling import aptarank_section9_analyze_results as section9_analysis
except ModuleNotFoundError:
    import aptarank_candidate_preparation as m9b
    import aptarank_section10_prepare_d1_full_pool as preparation
    import aptarank_section9_analyze_results as section9_analysis


PACKAGE_ID = preparation.PACKAGE_ID
STATUS = (
    "PROVISIONAL_SECTION10_VALIDATION_ANALYSIS_AND_REVIEW_POOL_"
    "AWAITING_INDEPENDENT_REVIEW_AND_EXPLICIT_RESULT_COMMITMENT"
)
PLAN_V39_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_9.md"
PLAN_V39_SHA256 = "88be515dcb04dd3db9f4ec7392b70ce90de085a601d15ac00facc43f509ad274"
PUBLIC_RELATIVE = f"data/aptarank_eval/sequence/{PACKAGE_ID}"
RESULT_RELATIVE = f"results/aptarank/evaluation/{PACKAGE_ID}"
PRIVATE_RELATIVE = f"aptarank_eval/{PACKAGE_ID}"
PUBLIC_PINS = {
    "README.md": "f11da39adb11dcd610aee0648710543c5da7115cdf272033782c22e1c0fadaf4",
    "records/expected_cell_manifest.json": "fe573aabe13facd7dfae06984ba9be0c79973f2f9803d50598e7cafe9d011846",
    "records/preparation_manifest.json": "786a56c972cb993184cf8f64293d4d314c5ca73a17cd9823d324710b9dd605a1",
    "records/review_pool_rule.json": "ba62d76f6f690559b1b1d4988ced580c40252d844ebe8160ef3abe4bc72974cd",
    "records/run_sheet.json": "f30721375ba1794fc20c4ec09284ebb9c65dd5f5d1022e198fe68f7506ea1b32",
    "records/target_settings.json": "e24246e3743f8707251829452acf79eefad0aafd1347d600a06cd1abcfaa7972",
    "records/validation_report.json": "9909e92d2842075db48b1b6c6be39c63fea71b57ac427dc2cf6473ed5e4a9e92",
    "upload/candidate_upload.csv": "e932bf9db6b7bc8d29ccdffa4289f37cca87bab3f7ca77c002f81377ad1f284b",
}
PRIVATE_PINS = {
    "blinding_secret.bin": "cd04c8eebf31985bb0057e369805e82939b89010802334f66b3683e79fdde7b7",
    "m9b2_private_membership_key.jsonl": "f247a7465c9d8e07f35b5db944ca479dff6eb5a8a9de02f116b4d075688202b6",
    "source_candidate_key.json": "fb7e6b0248f3748a1ec4280327e3669b5422c173ec085f30417ae851250d153d",
}
RAW_PINS = {
    "raw/d1_ndm1_125.pdf": "9ebc8fe271bb78268cbd601254fdbff6232cf535bef3c3bd185c1708e2719d6b",
    "raw/excluded_sequences_d1_ndm1_125.csv": "d5259d83ad7616b4499255a2039fbe6ba97f0df511239784934edeb0aabc1915",
    "raw/run_d1_ndm1_125_shortlist.csv": "257cbaa523638abf67aa6109bfce37127aab07eccfbcf82e6cfe448a9d8a650f",
    "raw/tier1_tier2_exact_d1_ndm1_125.csv": "b5501b2004e26f6345ec0ad6ddd00892c4460ed67243feeffed34115db4e32b3",
}
RECORD_PINS = {
    "records/pdf_visual_review.json": "5065cea943bf09b8681494adf660944e708262f755324d608e300a784b411f17",
    "records/raw_archive_inventory.json": "14fb973ed6f18cdbc70e8825c57962159ec76663212c24753f3a20c6718fee05",
}
FULL_FIELDS = ("rank", "candidate", "aptamer-likeness", "compatibility", "shuffle", "len", "sequence")
EXACT_FIELDS = ("", "candidate", "rank", "tier1", "control_percentile", "mismatch", "band", "selected")
EXCLUSION_FIELDS = ("row", "id", "sequence", "reason")
COMPATIBILITY = {"strong", "moderate", "weak", "not evaluated"}
FAVOURABLE = {"strong", "moderate"}
SHUFFLE = {"pass", "fail"}
CANDIDATE_ID = re.compile(r"cand_[0-9a-f]{32}\Z")
LONG_EXCLUSION = re.compile(r"length ([0-9]+) above maximum 100\Z")
SHORT_EXCLUSION = re.compile(r"length ([0-9]+) below minimum 20\Z")
CAVITY_WARNING = (
    "This cavity is oddly shaped: its robust extent and equivalent-sphere diameter "
    "disagree by more than 2\u00d7. The geometric comparison assumes a roughly convex pocket."
)


class Section10AnalysisError(RuntimeError):
    """Raised when any Section 10 production invariant fails."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def byte_record(payload: bytes) -> dict[str, object]:
    return {"sha256": sha256_bytes(payload), "byte_count": len(payload)}


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def read_regular(path: Path) -> bytes:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise Section10AnalysisError(f"not a regular file: {path}")
    return path.read_bytes()


def read_pinned(path: Path, digest: str, role: str) -> bytes:
    payload = read_regular(path)
    observed = sha256_bytes(payload)
    if observed != digest:
        raise Section10AnalysisError(f"{role} hash mismatch: expected {digest}, observed {observed}")
    return payload


def parse_json(payload: bytes, role: str) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Section10AnalysisError(f"{role} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise Section10AnalysisError(f"{role} is not a JSON object")
    return value


def parse_csv(payload: bytes, fields: tuple[str, ...], role: str) -> list[dict[str, str]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Section10AnalysisError(f"{role} is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != fields:
        raise Section10AnalysisError(f"{role} fields drifted")
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise Section10AnalysisError(f"{role} contains malformed rows")
    return rows


def decimal_value(text: str, role: str, *, unit_interval: bool = False) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise Section10AnalysisError(f"{role} is not a decimal") from exc
    if not value.is_finite() or (unit_interval and not Decimal(0) <= value <= Decimal(1)):
        raise Section10AnalysisError(f"{role} is outside its valid range")
    return value


def validate_preparation_lineage(
    repo: Path,
    private_root: Path,
    public_payloads: dict[str, bytes],
    private_payloads: dict[str, bytes],
) -> tuple[list[dict[str, str]], dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    read_pinned(repo / preparation.PLAN_RELATIVE, preparation.PLAN_SHA256, "v3.8 plan")
    read_pinned(repo / PLAN_V39_RELATIVE, PLAN_V39_SHA256, "v3.9 plan")
    source_payload = read_pinned(repo / preparation.SOURCE_RELATIVE, preparation.SOURCE_SHA256, "D1 source")
    membership_payload = read_pinned(repo / preparation.MEMBERSHIP_RELATIVE, preparation.MEMBERSHIP_SHA256, "attempt membership")
    records, sources, accounting = preparation.build_full_d1_records(source_payload, membership_payload)
    if accounting != preparation.EXPECTED_COUNTS:
        raise Section10AnalysisError("rebuilt D1 accounting drifted")
    secret = private_payloads["blinding_secret.bin"]
    if len(secret) != 32:
        raise Section10AnalysisError("blinding secret is not 32 bytes")
    sequences = sorted(sources, key=lambda value: value.encode("utf-8"))
    candidate_ids = m9b.assign_candidate_ids(sequences, secret, m9b.TRUNCATION_BYTES)
    rebuilt_upload = m9b._candidate_upload_bytes(sequences, candidate_ids)
    upload = public_payloads["upload/candidate_upload.csv"]
    if rebuilt_upload != upload:
        raise Section10AnalysisError("candidate upload does not reproduce from the frozen source and secret")
    upload_rows = preparation.validate_upload(upload, candidate_ids, sources)
    rebuilt_membership = m9b._private_key_bytes(records, candidate_ids)
    if rebuilt_membership != private_payloads["m9b2_private_membership_key.jsonl"]:
        raise Section10AnalysisError("restricted membership key does not reproduce")
    rebuilt_source_key = preparation.build_source_candidate_key(upload_rows, rebuilt_membership, sources)
    if rebuilt_source_key != private_payloads["source_candidate_key.json"]:
        raise Section10AnalysisError("restricted source key does not reproduce")
    if preparation.expected_cells(upload_rows) != public_payloads["records/expected_cell_manifest.json"]:
        raise Section10AnalysisError("expected-cell manifest does not reproduce")
    source_document = parse_json(private_payloads["source_candidate_key.json"], "source candidate key")
    source_rows = source_document.get("memberships")
    if not isinstance(source_rows, list) or len(source_rows) != 30000:
        raise Section10AnalysisError("source candidate key denominator drifted")
    source_by_id = {str(row["candidate_id"]): row for row in source_rows if isinstance(row, dict)}
    private_rows = [json.loads(line) for line in rebuilt_membership.decode("utf-8").splitlines()]
    private_by_id = {str(row["candidate_id"]): row for row in private_rows}
    if len(source_by_id) != 30000 or len(private_by_id) != 30000:
        raise Section10AnalysisError("restricted key IDs are duplicated")
    return upload_rows, source_by_id, private_by_id


def validate_full_export(payload: bytes, upload: dict[str, str]) -> list[dict[str, object]]:
    rows = parse_csv(payload, FULL_FIELDS, "full scored export")
    if len(rows) != 29583:
        raise Section10AnalysisError("full scored-export denominator drifted")
    validated: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in rows:
        candidate = row["candidate"]
        if candidate not in upload or candidate in seen or row["sequence"] != upload[candidate]:
            raise Section10AnalysisError("full scored export does not join uniquely to the upload")
        seen.add(candidate)
        try:
            rank, length = int(row["rank"]), int(row["len"])
        except ValueError as exc:
            raise Section10AnalysisError("full scored rank or length is invalid") from exc
        if length != len(row["sequence"]):
            raise Section10AnalysisError("full scored length does not match sequence")
        if row["compatibility"] not in COMPATIBILITY or row["shuffle"] not in SHUFFLE:
            raise Section10AnalysisError("full scored categorical token is invalid")
        if rank <= 1000 and row["compatibility"] == "not evaluated":
            raise Section10AnalysisError("a top-1000 candidate lacks compatibility evaluation")
        if rank > 1000 and row["compatibility"] != "not evaluated":
            raise Section10AnalysisError("compatibility was unexpectedly evaluated outside the top 1000")
        validated.append({
            "rank": rank,
            "candidate": candidate,
            "score": decimal_value(row["aptamer-likeness"], "Tier 1 score", unit_interval=True),
            "score_text": row["aptamer-likeness"],
            "compatibility": row["compatibility"],
            "shuffle": row["shuffle"],
            "length": length,
            "sequence": row["sequence"],
        })
    if [row["rank"] for row in validated] != list(range(1, 29584)):
        raise Section10AnalysisError("full scored ranks are not complete and ordered")
    for left, right in zip(validated, validated[1:]):
        if left["score"] < right["score"]:
            raise Section10AnalysisError("Tier 1 rank does not follow non-increasing score")
        if left["score"] == right["score"] and left["candidate"] > right["candidate"]:
            raise Section10AnalysisError("Tier 1 score ties do not use ascending opaque ID")
    return validated


def validate_exclusions(payload: bytes, upload: dict[str, str], scored_ids: set[str]) -> list[dict[str, object]]:
    rows = parse_csv(payload, EXCLUSION_FIELDS, "exclusion register")
    if len(rows) != 417:
        raise Section10AnalysisError("exclusion denominator drifted")
    validated = []
    seen: set[str] = set()
    below = above = 0
    for row in rows:
        candidate = row["id"]
        if candidate not in upload or candidate in scored_ids or candidate in seen:
            raise Section10AnalysisError("excluded ID is missing, duplicated, or also scored")
        seen.add(candidate)
        sequence = upload[candidate]
        match = SHORT_EXCLUSION.fullmatch(row["reason"])
        if match:
            below += 1
            if int(match.group(1)) != len(sequence) or not len(sequence) < 20 or row["sequence"] != sequence:
                raise Section10AnalysisError("short exclusion does not reconcile to upload")
        else:
            match = LONG_EXCLUSION.fullmatch(row["reason"])
            if match is None:
                raise Section10AnalysisError("exclusion reason is outside the frozen length rule")
            above += 1
            if int(match.group(1)) != len(sequence) or not len(sequence) > 100:
                raise Section10AnalysisError("long exclusion length does not reconcile to upload")
            if row["sequence"] != sequence[:59] + "\u2026":
                raise Section10AnalysisError("long exclusion display prefix does not match upload")
        try:
            displayed_row = int(row["row"])
        except ValueError as exc:
            raise Section10AnalysisError("exclusion row token is not an integer") from exc
        validated.append({"candidate": candidate, "length": len(sequence), "reason": row["reason"], "displayed_row": displayed_row})
    if (below, above) != (11, 406) or scored_ids | seen != set(upload) or scored_ids & seen:
        raise Section10AnalysisError("scored/excluded accounting does not reconcile to all 30,000 uploads")
    return validated


def validate_exact_export(payload: bytes, full_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = parse_csv(payload, EXACT_FIELDS, "exact Tier 1/Tier 2 export")
    if len(rows) != 1000:
        raise Section10AnalysisError("exact Tier 2 export denominator drifted")
    validated = []
    seen: set[str] = set()
    for index, (row, full) in enumerate(zip(rows, full_rows[:1000])):
        try:
            exported_index, rank = int(row[""]), int(row["rank"])
        except ValueError as exc:
            raise Section10AnalysisError("exact export index or rank is invalid") from exc
        if exported_index != index or rank != index + 1:
            raise Section10AnalysisError("exact export index or rank is incomplete")
        candidate = row["candidate"]
        tier1 = decimal_value(row["tier1"], "exact Tier 1", unit_interval=True)
        percentile = decimal_value(row["control_percentile"], "control percentile", unit_interval=True)
        mismatch = decimal_value(row["mismatch"], "Tier 2 mismatch")
        band = row["band"]
        expected_band = "strong" if percentile >= Decimal("0.95") else "moderate" if percentile >= Decimal("0.75") else "weak"
        if (
            candidate in seen
            or candidate != full["candidate"]
            or rank != full["rank"]
            or tier1 != full["score"]
            or band != full["compatibility"]
            or band != expected_band
        ):
            raise Section10AnalysisError("exact Tier 2 row does not reconcile to the full export")
        if row["selected"] not in {"true", "false"}:
            raise Section10AnalysisError("exact selected token is invalid")
        seen.add(candidate)
        validated.append({
            **full,
            "exact_export_row_index": exported_index,
            "control_percentile": percentile,
            "control_percentile_text": row["control_percentile"],
            "mismatch": mismatch,
            "mismatch_text": row["mismatch"],
            "band": band,
        })
    return validated


def quantile_type7(values: list[Decimal], probability: Decimal) -> Decimal:
    return section9_analysis.quantile_type7(values, probability)


def decimal_text(value: Decimal) -> str:
    return section9_analysis.decimal_text(value)


def score_summary(rows: list[dict[str, object]], field: str) -> dict[str, str]:
    values = [row[field] for row in rows]
    with localcontext() as context:
        context.prec = 50
        mean = sum(values, Decimal(0)) / Decimal(len(values))
    return {
        "minimum": decimal_text(min(values)),
        "q1_type7": decimal_text(quantile_type7(values, Decimal("0.25"))),
        "median_type7": decimal_text(quantile_type7(values, Decimal("0.5"))),
        "mean": decimal_text(mean),
        "q3_type7": decimal_text(quantile_type7(values, Decimal("0.75"))),
        "maximum": decimal_text(max(values)),
    }


def average_ranks(values: list[Decimal]) -> list[Decimal]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [Decimal(0)] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        average = (Decimal(start + 1) + Decimal(end)) / Decimal(2)
        for position in range(start, end):
            ranks[order[position]] = average
        start = end
    return ranks


def spearman_rho(left: list[Decimal], right: list[Decimal]) -> float:
    x, y = average_ranks(left), average_ranks(right)
    mean_x = sum(x, Decimal(0)) / Decimal(len(x))
    mean_y = sum(y, Decimal(0)) / Decimal(len(y))
    covariance = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    variance_x = sum((a - mean_x) ** 2 for a in x)
    variance_y = sum((b - mean_y) ** 2 for b in y)
    if not variance_x or not variance_y:
        raise Section10AnalysisError("Spearman correlation is undefined")
    return float(covariance / (variance_x * variance_y).sqrt())


def percent(count: int, denominator: int) -> str:
    with localcontext() as context:
        context.prec = 50
        return decimal_text(Decimal(100) * Decimal(count) / Decimal(denominator))


def one_provenance_value(row: dict[str, object], key: str) -> str:
    occurrences = row.get("source_occurrences")
    if not isinstance(occurrences, list) or not occurrences:
        raise Section10AnalysisError("restricted membership lacks source occurrences")
    values = {str(item.get("provenance", {}).get(key)) for item in occurrences}
    if len(values) != 1 or "None" in values:
        raise Section10AnalysisError(f"candidate does not map to one {key}")
    return next(iter(values))


def build_pool(
    exact_rows: list[dict[str, object]],
    source_by_id: dict[str, dict[str, object]],
    private_by_id: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    eligible = [
        row for row in exact_rows
        if row["shuffle"] == "pass" and row["band"] in FAVOURABLE
    ]
    ordered = sorted(eligible, key=lambda row: (int(row["rank"]), str(row["candidate"])))
    if ordered != eligible or len(ordered) != 137:
        raise Section10AnalysisError("joint eligibility count or Tier 1 ordering drifted")
    enriched = []
    for row in ordered:
        candidate = str(row["candidate"])
        source = source_by_id.get(candidate)
        private = private_by_id.get(candidate)
        if source is None or private is None:
            raise Section10AnalysisError("eligible candidate lacks restricted provenance")
        sequence = str(row["sequence"])
        if (
            source.get("sequence_sha256") != sha256_bytes(sequence.encode("ascii"))
            or source.get("length") != len(sequence)
            or private.get("length") != len(sequence)
        ):
            raise Section10AnalysisError("eligible sequence does not reconcile to restricted provenance")
        seed = one_provenance_value(private, "d1_training_seed")
        block = one_provenance_value(private, "technical_block")
        enriched.append({
            **row,
            "source_candidate_id": source["source_candidate_id"],
            "source_record_ids": source["source_record_ids"],
            "source_occurrences": private["source_occurrences"],
            "d1_training_seed": seed,
            "technical_block": block,
            "technical_warning": CAVITY_WARNING,
        })
    return enriched, enriched[:100]


def public_pool_summary(eligible: list[dict[str, object]], pool: list[dict[str, object]]) -> dict[str, object]:
    return {
        "jointly_eligible": len(eligible),
        "retained_for_supervisor_review": len(pool),
        "capped_out": len(eligible) - len(pool),
        "eligible_compatibility": dict(sorted(Counter(str(row["band"]) for row in eligible).items())),
        "retained_compatibility": dict(sorted(Counter(str(row["band"]) for row in pool).items())),
        "capped_out_compatibility": dict(sorted(Counter(str(row["band"]) for row in eligible[100:]).items())),
        "eligible_training_seed": dict(sorted(Counter(str(row["d1_training_seed"]) for row in eligible).items())),
        "retained_training_seed": dict(sorted(Counter(str(row["d1_training_seed"]) for row in pool).items())),
        "retained_length": {
            "minimum": min(int(row["length"]) for row in pool),
            "maximum": max(int(row["length"]) for row in pool),
            "unique_lengths": len({int(row["length"]) for row in pool}),
        },
        "retained_tier1_rank": {
            "best": min(int(row["rank"]) for row in pool),
            "worst": max(int(row["rank"]) for row in pool),
            "first_capped_out": int(eligible[100]["rank"]),
        },
        "manual_supervisor_decisions_complete": False,
        "finally_retained_after_supervisor_review": None,
    }


def build_analysis(repo: Path, private_root: Path) -> tuple[dict[str, object], dict[str, object], str, list[dict[str, object]]]:
    public_root = repo / PUBLIC_RELATIVE
    result_root = repo / RESULT_RELATIVE
    private_package = private_root / PRIVATE_RELATIVE
    public_payloads = {name: read_pinned(public_root / name, digest, name) for name, digest in PUBLIC_PINS.items()}
    private_payloads = {name: read_pinned(private_package / name, digest, name) for name, digest in PRIVATE_PINS.items()}
    raw_payloads = {name: read_pinned(result_root / name, digest, name) for name, digest in RAW_PINS.items()}
    record_payloads = {name: read_pinned(result_root / name, digest, name) for name, digest in RECORD_PINS.items()}
    upload_rows, source_by_id, private_by_id = validate_preparation_lineage(repo, private_root, public_payloads, private_payloads)
    upload = {row["id"]: row["sequence"] for row in upload_rows}
    if len(upload) != 30000:
        raise Section10AnalysisError("upload IDs are duplicated")
    full = validate_full_export(raw_payloads["raw/run_d1_ndm1_125_shortlist.csv"], upload)
    exclusions = validate_exclusions(raw_payloads["raw/excluded_sequences_d1_ndm1_125.csv"], upload, {str(row["candidate"]) for row in full})
    exact = validate_exact_export(raw_payloads["raw/tier1_tier2_exact_d1_ndm1_125.csv"], full)
    eligible, pool = build_pool(exact, source_by_id, private_by_id)

    rule = parse_json(public_payloads["records/review_pool_rule.json"], "review-pool rule")
    if (
        rule.get("maximum_pool_size") != 100
        or rule.get("strong_precedes_moderate") is not False
        or rule.get("combined_tier1_tier2_numeric_score") is not False
    ):
        raise Section10AnalysisError("frozen review-pool rule drifted")
    visual = parse_json(record_payloads["records/pdf_visual_review.json"], "PDF visual review")
    if visual.get("visible_target_warning") != CAVITY_WARNING.replace("2\u00d7", "2x"):
        raise Section10AnalysisError("PDF cavity warning drifted")
    rho = spearman_rho(
        [row["score"] for row in exact],
        [row["control_percentile"] for row in exact],
    )
    if not math.isclose(rho, 0.007855649652876636, rel_tol=0, abs_tol=1e-15):
        raise Section10AnalysisError("exact-export Spearman rho drifted")

    shuffle_pass_full = sum(row["shuffle"] == "pass" for row in full)
    shuffle_pass_top1000 = sum(row["shuffle"] == "pass" for row in exact)
    bands_top1000 = Counter(str(row["band"]) for row in exact)
    favourable_top1000 = bands_top1000["strong"] + bands_top1000["moderate"]
    funnel = [
        {"stage": "uploaded_sequences", "count": 30000, "previous_denominator": None, "pass_rate_from_previous_percent": None, "retained_from_upload_percent": "100"},
        {"stage": "valid_scored_records", "count": 29583, "previous_denominator": 30000, "pass_rate_from_previous_percent": percent(29583, 30000), "retained_from_upload_percent": percent(29583, 30000)},
        {"stage": "exact_top_1000_target_results", "count": 1000, "previous_denominator": 29583, "pass_rate_from_previous_percent": percent(1000, 29583), "retained_from_upload_percent": percent(1000, 30000)},
        {"stage": "top_1000_shuffle_pass", "count": shuffle_pass_top1000, "previous_denominator": 1000, "pass_rate_from_previous_percent": percent(shuffle_pass_top1000, 1000), "retained_from_upload_percent": percent(shuffle_pass_top1000, 30000)},
        {"stage": "shuffle_pass_and_favourable_compatibility", "count": len(eligible), "previous_denominator": shuffle_pass_top1000, "pass_rate_from_previous_percent": percent(len(eligible), shuffle_pass_top1000), "retained_from_upload_percent": percent(len(eligible), 30000)},
        {"stage": "tier1_ordered_jointly_eligible", "count": len(eligible), "previous_denominator": len(eligible), "pass_rate_from_previous_percent": "100", "retained_from_upload_percent": percent(len(eligible), 30000)},
        {"stage": "supervisor_review_pool_after_cap", "count": len(pool), "previous_denominator": len(eligible), "pass_rate_from_previous_percent": percent(len(pool), len(eligible)), "retained_from_upload_percent": percent(len(pool), 30000)},
    ]
    summary = {
        "schema_version": "mres-aptarank-section10-analysis-summary-v1",
        "status": STATUS,
        "package_id": PACKAGE_ID,
        "scientific_result_committed": False,
        "supervisor_review_complete": False,
        "scores_recomputed": False,
        "combined_tier1_tier2_score_created": False,
        "denominators": {
            "uploaded": 30000,
            "scored": len(full),
            "technical_exclusions": len(exclusions),
            "otherwise_missing": 0,
            "exact_tier2_exported": len(exact),
            "shuffle_pass_full_scored_export": shuffle_pass_full,
            "shuffle_pass_top_1000": shuffle_pass_top1000,
            "strong_top_1000": bands_top1000["strong"],
            "moderate_top_1000": bands_top1000["moderate"],
            "weak_top_1000": bands_top1000["weak"],
            "pooled_favourable_top_1000": favourable_top1000,
            "jointly_eligible": len(eligible),
            "retained_for_supervisor_review": len(pool),
            "capped_out": len(eligible) - len(pool),
            "manually_reviewed": 0,
            "finally_retained_after_supervisor_review": None,
            "not_retained_after_supervisor_review": None,
        },
        "funnel": funnel,
        "technical_exclusions": {
            "below_20_nt": sum(int(row["length"]) < 20 for row in exclusions),
            "above_100_nt": sum(int(row["length"]) > 100 for row in exclusions),
            "replaced_or_replenished": False,
        },
        "score_analysis": {
            "tier1_all_scored": score_summary(full, "score"),
            "tier1_top_1000": score_summary(exact, "score"),
            "tier1_jointly_eligible": score_summary(eligible, "score"),
            "tier1_supervisor_pool": score_summary(pool, "score"),
            "tier2_control_percentile_top_1000": score_summary(exact, "control_percentile"),
            "tier2_control_percentile_jointly_eligible": score_summary(eligible, "control_percentile"),
            "tier2_control_percentile_supervisor_pool": score_summary(pool, "control_percentile"),
            "tier1_tier2_spearman": {
                "rho_exact_export": rho,
                "rho_pdf_rounded": visual["visible_tier_relationship"]["spearman_rho"],
                "p_value_pdf": visual["visible_tier_relationship"]["two_sided_p"],
                "n": 1000,
            },
        },
        "review_pool": public_pool_summary(eligible, pool),
        "target_geometry_limitation": {
            "warning_exact": CAVITY_WARNING,
            "applies_to_every_review_candidate": True,
        },
        "interpretation": (
            "The deterministic computational pool contains the 100 best Tier 1 ranks among 137 D1 candidates "
            "that passed the candidate-specific shuffle check and had strong or moderate NDM-1 compatibility. "
            "Compatibility was a pooled coarse gate, not an ordering variable, and no Tier 1/Tier 2 composite was formed."
        ),
        "claim_boundary": (
            "The pool contains computationally prioritised D1 candidates for joint supervisor review and future "
            "experimental consideration; it is not a binder set or evidence of affinity, specificity, inhibition, "
            "target recognition, experimental function, or predictive validity."
        ),
    }
    manifest = {
        "schema_version": "mres-aptarank-section10-analysis-manifest-v1",
        "status": STATUS,
        "package_id": PACKAGE_ID,
        "analysis_adapter": byte_record(read_regular(Path(__file__).resolve())),
        "inputs": {
            "plans": {
                "v3_8": {"path": preparation.PLAN_RELATIVE, "sha256": preparation.PLAN_SHA256},
                "v3_9": {"path": PLAN_V39_RELATIVE, "sha256": PLAN_V39_SHA256},
            },
            "public_package": {name: byte_record(payload) for name, payload in public_payloads.items()},
            "restricted_package": {name: byte_record(payload) for name, payload in private_payloads.items()},
            "raw_artifacts": {name: byte_record(payload) for name, payload in raw_payloads.items()},
            "run_records": {name: byte_record(payload) for name, payload in record_payloads.items()},
        },
        "checks": {
            "frozen_D1_source_and_attempt_membership_rebuilt": True,
            "all_30000_opaque_ids_recomputed_from_restricted_secret": True,
            "upload_and_both_restricted_keys_reproduced_byte_exactly": True,
            "29583_scored_plus_417_excluded_equals_30000_uploaded": True,
            "all_scored_and_excluded_rows_join_by_opaque_id": True,
            "ranks_scores_sequences_lengths_and_ties_validate": True,
            "exact_top_1000_reconciles_to_full_export": True,
            "tier2_bands_follow_0_75_and_0_95_thresholds": True,
            "v3_8_shuffle_and_pooled_favourable_gates_applied": True,
            "Tier_1_primary_order_and_cap_100_applied": True,
            "strong_does_not_precede_moderate": True,
            "no_gate_relaxed_and_no_exclusion_replenished": True,
            "no_combined_score_created": True,
            "target_geometry_warning_preserved": True,
        },
    }
    report = render_report(summary)
    return summary, manifest, report, pool


def render_report(summary: dict[str, object]) -> str:
    funnel = summary["funnel"]
    lines = [
        "# Section 10 D1 full-pool NDM-1 validation and supervisor-review pool",
        "",
        f"Status: `{STATUS}`",
        "",
        "## Validated accounting and attrition",
        "",
        "| Stage | Records | Pass rate from previous stage | Retained from 30,000 uploads |",
        "|---|---:|---:|---:|",
    ]
    for row in funnel:
        previous = "n.a." if row["pass_rate_from_previous_percent"] is None else f"{Decimal(row['pass_rate_from_previous_percent']):.4f}%"
        lines.append(
            f"| {str(row['stage']).replace('_', ' ')} | {row['count']:,} | {previous} | "
            f"{Decimal(row['retained_from_upload_percent']):.4f}% |"
        )
    d = summary["denominators"]
    lines.extend([
        "",
        "The tool scored 29,583 of 30,000 uploads and recorded 417 technical exclusions: 11 below 20 nt and 406 above 100 nt. No row is otherwise missing, and no exclusion was replaced or replenished. Across all 29,583 scored candidates, 1,486 (5.0232%) have shuffle `pass`; candidates outside the Tier 1 top 1,000 have no Tier 2 compatibility evaluation and therefore cannot enter the frozen pool.",
        "",
        "Within the exact top 1,000, 558 candidates (55.8000%) have shuffle `pass`. The compatibility distribution is 69 `strong`, 167 `moderate` and 764 `weak`; 236/1,000 (23.6000%) are in the pooled favourable class. Applying both mandatory gates leaves 137/1,000 jointly eligible candidates (13.7000%). Tier 1 ordering retains 100 and caps out 37.",
        "",
        "## Deterministic supervisor-review pool",
        "",
        f"The retained pool contains {summary['review_pool']['retained_compatibility']['strong']} `strong` and {summary['review_pool']['retained_compatibility']['moderate']} `moderate` candidates. It contains {summary['review_pool']['retained_training_seed']['43']} candidates from D1 training seed 43 and {summary['review_pool']['retained_training_seed']['44']} from seed 44. Tier 1 ranks span {summary['review_pool']['retained_tier1_rank']['best']} to {summary['review_pool']['retained_tier1_rank']['worst']}; the first capped-out jointly eligible candidate is rank {summary['review_pool']['retained_tier1_rank']['first_capped_out']}.",
        "",
        "`Strong` does not precede `moderate`. The bands are pooled only for eligibility; Tier 1 rank supplies the order, with ascending opaque ID already enforcing exact Tier 1 score ties in the validated tool export. No Tier 1/Tier 2 numerical composite was formed.",
        "",
        "## Score analysis",
        "",
        "| Population | n | Tier 1 mean | Tier 1 median | Tier 1 IQR |",
        "|---|---:|---:|---:|---:|",
    ])
    for label, key, n in (
        ("All scored", "tier1_all_scored", 29583),
        ("Exact top 1,000", "tier1_top_1000", 1000),
        ("Jointly eligible", "tier1_jointly_eligible", 137),
        ("Supervisor-review pool", "tier1_supervisor_pool", 100),
    ):
        item = summary["score_analysis"][key]
        lines.append(
            f"| {label} | {n:,} | {Decimal(item['mean']):.3f} | {Decimal(item['median_type7']):.3f} | "
            f"{Decimal(item['q1_type7']):.3f}\u2013{Decimal(item['q3_type7']):.3f} |"
        )
    relation = summary["score_analysis"]["tier1_tier2_spearman"]
    lines.extend([
        "",
        f"Across the exact top 1,000, Spearman rho between Tier 1 and the exported control percentile is {relation['rho_exact_export']:.6f}, matching the PDF's rounded {relation['rho_pdf_rounded']:.3f} (PDF p = {relation['p_value_pdf']:.3f}). The association is negligible and is not used in selection.",
        "",
        "## Required target limitation",
        "",
        f"> {CAVITY_WARNING}",
        "",
        "The warning applies to every retained candidate. The compatibility annotation remains a coarse target-specific eligibility gate rather than evidence of binding or a fine-grained ordering signal.",
        "",
        "## Decision boundary",
        "",
        "This is a supervisor-review pool of computationally prioritised D1 candidates. Manual review is still pending. Under v3.9, the biologist-supervisor assessment may remove candidates and retain at most 50 for future experimental consideration, but it cannot add a candidate outside this deterministic pool. Every retain/not-retain decision, reviewer, date and reason must be recorded.",
    ])
    if d["jointly_eligible"] != 137 or d["retained_for_supervisor_review"] != 100:
        raise Section10AnalysisError("report accounting drifted")
    return "\n".join(lines) + "\n"


def build_restricted_outputs(pool: list[dict[str, object]]) -> dict[str, bytes]:
    number_lines = [str(row["rank"]) for row in pool]
    sequence_buffer = io.StringIO(newline="")
    writer = csv.writer(sequence_buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(["tool_candidate_number", "exact_export_row_index", "opaque_candidate_id", "sequence"])
    for row in pool:
        writer.writerow([row["rank"], row["exact_export_row_index"], row["candidate"], row["sequence"]])
    records = []
    for review_order, row in enumerate(pool, start=1):
        records.append({
            "review_order": review_order,
            "tool_candidate_number": row["rank"],
            "tool_candidate_number_source_field": "rank",
            "exact_export_row_index": row["exact_export_row_index"],
            "opaque_candidate_id": row["candidate"],
            "sequence": row["sequence"],
            "length": row["length"],
            "tier1_rank": row["rank"],
            "tier1_score": row["score_text"],
            "shuffle": row["shuffle"],
            "compatibility": row["band"],
            "tier2_control_percentile": row["control_percentile_text"],
            "tier2_mismatch": row["mismatch_text"],
            "d1_training_seed": row["d1_training_seed"],
            "technical_block": row["technical_block"],
            "source_candidate_id": row["source_candidate_id"],
            "source_record_ids": row["source_record_ids"],
            "source_occurrences": row["source_occurrences"],
            "technical_warning": row["technical_warning"],
            "manual_review": {
                "supervisor": None,
                "review_date": None,
                "decision": None,
                "reason": None,
            },
        })
    jsonl = "".join(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n" for row in records).encode("utf-8")
    readme = (
        "# Section 10 supervisor-review package\n\n"
        "Restricted local sequence-bearing output. Do not commit or upload this directory.\n\n"
        "`dashboard_candidate_numbers.txt` lists the one-based AptaRank Tier 1 `rank` values used as tool candidate numbers. "
        "`supervisor_review_sequences.txt` pairs those numbers with the exact-export row index, opaque ID and sequence for dashboard review. "
        "`supervisor_review_records.jsonl` preserves full restricted provenance, scores, warnings and blank manual-decision fields.\n\n"
        "The 100 rows are the deterministic v3.8 pool. Manual v3.9 review may remove candidates and retain at most 50, but cannot add another candidate.\n"
    ).encode("utf-8")
    outputs = {
        "README.md": readme,
        "dashboard_candidate_numbers.txt": ("\n".join(number_lines) + "\n").encode("ascii"),
        "supervisor_review_sequences.txt": sequence_buffer.getvalue().encode("utf-8"),
        "supervisor_review_records.jsonl": jsonl,
    }
    outputs["restricted_manifest.json"] = canonical_json({
        "schema_version": "mres-aptarank-section10-supervisor-package-v1",
        "status": "DETERMINISTIC_COMPUTATIONAL_POOL_READY_FOR_MANUAL_SUPERVISOR_REVIEW",
        "package_id": PACKAGE_ID,
        "sequence_bearing": True,
        "git_commit_allowed": False,
        "candidate_count": 100,
        "final_manual_decisions_complete": False,
        "artifacts": {name: byte_record(payload) for name, payload in outputs.items()},
    })
    return outputs


def ensure_public(payloads: dict[str, bytes], pool: list[dict[str, object]]) -> None:
    for role, payload in payloads.items():
        if re.search(rb"cand_[0-9a-f]{32}", payload):
            raise Section10AnalysisError(f"opaque candidate ID leaked into {role}")
        for row in pool:
            sequence = str(row["sequence"]).encode("ascii")
            if sequence in payload:
                raise Section10AnalysisError(f"review-pool sequence leaked into {role}")


def write_outputs(repo: Path, summary: dict[str, object], manifest: dict[str, object], report: str, pool: list[dict[str, object]]) -> tuple[Path, Path]:
    public_dir = repo / RESULT_RELATIVE / "derived/analysis_v1"
    restricted_dir = repo / RESULT_RELATIVE / "restricted/supervisor_review_v1"
    if public_dir.exists() and any(public_dir.iterdir()):
        raise Section10AnalysisError(f"public output directory is not empty: {public_dir}")
    if restricted_dir.exists() and any(restricted_dir.iterdir()):
        raise Section10AnalysisError(f"restricted output directory is not empty: {restricted_dir}")
    public_payloads = {
        "analysis_summary.json": canonical_json(summary),
        "analysis_manifest.json": canonical_json(manifest),
        "section10_results.md": report.encode("utf-8"),
    }
    ensure_public(public_payloads, pool)
    restricted_payloads = build_restricted_outputs(pool)
    public_dir.mkdir(parents=True, exist_ok=True)
    restricted_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(restricted_dir, 0o700)
    for name, payload in public_payloads.items():
        (public_dir / name).write_bytes(payload)
    public_sums = "".join(f"{sha256_bytes(payload)}  {name}\n" for name, payload in sorted(public_payloads.items()))
    (public_dir / "SHA256SUMS").write_text(public_sums, encoding="ascii", newline="")
    for name, payload in restricted_payloads.items():
        path = restricted_dir / name
        path.write_bytes(payload)
        os.chmod(path, 0o600)
    restricted_sums = "".join(f"{sha256_bytes(payload)}  {name}\n" for name, payload in sorted(restricted_payloads.items()))
    sums_path = restricted_dir / "SHA256SUMS"
    sums_path.write_text(restricted_sums, encoding="ascii", newline="")
    os.chmod(sums_path, 0o600)
    return public_dir, restricted_dir


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
    summary, manifest, report, pool = build_analysis(args.repo.resolve(), args.private_root.resolve())
    if args.check_only:
        print(json.dumps({
            "status": summary["status"],
            "denominators": summary["denominators"],
            "checks": manifest["checks"],
        }, sort_keys=True))
        return
    public_dir, restricted_dir = write_outputs(args.repo.resolve(), summary, manifest, report, pool)
    print(json.dumps({"public": str(public_dir), "restricted": str(restricted_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()

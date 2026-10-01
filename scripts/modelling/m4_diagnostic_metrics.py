#!/usr/bin/env python3
"""Core M4 diagnostic metrics for a frozen generation sample.

Requested-length exact-hit rates use every raw attempt as the denominator,
before filtering. Invalid and unparseable accounted attempts are non-hits.
A valid-only rate may be reported beside that metric. It does not replace it.
These metrics do not select a checkpoint by themselves, cluster sequences, or
embed them. A low exact-hit rate is not an execution-success requirement.
"""

from __future__ import annotations

import re

EXACT_HIT_DENOMINATOR = "raw_attempts"
EXACT_HIT_RATE_IS_EXECUTION_SUCCESS_REQUIREMENT = False
LOW_EXACT_HIT_RATE_RERUNS_OR_INVALIDATES_THE_DIAGNOSTIC_POOL = False
INDEPENDENT_BIOLOGICAL_REPLICATES = False
VALID_ONLY_EXACT_HIT_LABEL = "valid_outputs_only_diagnostic_not_the_approved_metric"
CANONICAL_SEQUENCE = re.compile(r"^[ACGU]+$")

DEFERRED_BEYOND_M4 = (
    "clustering_identity_threshold",
    "clustering_dependent_claims",
    "frozen_representation_metrics",
    "representation_aggregation_rules",
)

IMPLEMENTED_METRIC_IDS = (
    "raw_attempts",
    "parsed_outputs",
    "valid_outputs",
    "invalid_outputs",
    "empty_or_unparseable_outputs",
    "exact_length_hits",
    "exact_hit_rate",
    "exact_hit_rate_valid_outputs_diagnostic",
    "eos_marker_observations",
    "early_eos_observations",
    "cleaned_length_distribution",
    "length_shortfall_distribution",
    "length_excess_distribution",
    "unique_valid_outputs",
    "duplicates",
    "largest_duplicate_multiplicity",
    "largest_duplicate_share",
)

HARD_GUARDRAIL_IDS = (
    "valid_nonempty_acgu_fraction",
    "empty_or_unparseable_fraction",
    "unique_fraction",
    "exact_train_match_rate",
    "largest_duplicate_share",
)

LEDGER_FIELDS = (
    "original_attempt_index",
    "invocation_index",
    "batch_position",
    "requested_target_length",
    "max_seq_len",
    "invocation_seed",
    "raw_decoded_text",
    "raw_length",
    "leading_boundary_marker_run",
    "trailing_boundary_marker_run",
    "cleaned_sequence",
    "cleaned_length",
    "validity",
    "invalid_reason",
    "eos_marker_observed",
    "early_eos",
    "exact_length_hit",
    "length_delta",
)

LARGEST_DUPLICATE_SHARE_NUMERATOR = "count_of_the_most_frequent_valid_output"
LARGEST_DUPLICATE_SHARE_DENOMINATOR = "valid_outputs"
LARGEST_DUPLICATE_SHARE_MAXIMUM = 0.01

GUARDRAIL_THRESHOLDS = {
    "valid_nonempty_acgu_fraction": {"comparison": "minimum", "threshold": 0.99},
    "empty_or_unparseable_fraction": {"comparison": "maximum", "threshold": 0.01},
    "unique_fraction": {"comparison": "minimum", "threshold": 0.95},
    "exact_train_match_rate": {"comparison": "maximum", "threshold": 0.01},
    "largest_duplicate_share": {
        "comparison": "maximum",
        "threshold": LARGEST_DUPLICATE_SHARE_MAXIMUM,
    },
}


class DiagnosticMetricError(ValueError):
    """The attempt ledger cannot be summarised."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def _rate(numerator, denominator):
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _distribution(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [{"value": value, "count": counts[value]} for value in sorted(counts)]


def _duplicate_summary(sequences):
    counts = {}
    for sequence in sequences:
        counts[sequence] = counts.get(sequence, 0) + 1
    unique = len(counts)
    duplicates = len(sequences) - unique
    if not counts:
        return {
            "unique_valid_outputs": 0,
            "duplicates": 0,
            "largest_duplicate_multiplicity": 0,
            "largest_duplicate_share": None,
            "largest_duplicate_share_status": "undefined_empty_valid_denominator",
        }
    multiplicity = max(counts.values())
    return {
        "unique_valid_outputs": unique,
        "duplicates": duplicates,
        "largest_duplicate_multiplicity": multiplicity,
        "largest_duplicate_share": multiplicity / len(sequences),
        "largest_duplicate_share_status": (
            LARGEST_DUPLICATE_SHARE_NUMERATOR + "_over_" + LARGEST_DUPLICATE_SHARE_DENOMINATOR
        ),
    }


def _require(condition, detail):
    if not condition:
        raise DiagnosticMetricError("ledger_inconsistent", detail)


def recomputed_validity(cleaned):
    return isinstance(cleaned, str) and CANONICAL_SEQUENCE.fullmatch(cleaned) is not None


def validate_attempt_record(attempt):
    """Require the audited schema and recompute flags from the cleaned body.

    Derived flags that disagree with the cleaned sequence are a ledger
    failure. They are not silently trusted.
    """
    if not isinstance(attempt, dict):
        raise DiagnosticMetricError("attempt_ledger_invalid", "attempt is not a record")
    if tuple(attempt) != LEDGER_FIELDS:
        raise DiagnosticMetricError("ledger_schema_invalid", "attempt fields drifted")
    requested = attempt["requested_target_length"]
    cleaned = attempt["cleaned_sequence"]
    raw = attempt["raw_decoded_text"]
    _require(type(attempt["original_attempt_index"]) is int, "original_attempt_index is not an integer")
    _require(type(attempt["invocation_index"]) is int, "invocation_index is not an integer")
    _require(type(attempt["batch_position"]) is int, "batch_position is not an integer")
    _require(type(requested) is int and requested >= 1, "requested_target_length is not a positive integer")
    _require(type(attempt["max_seq_len"]) is int, "max_seq_len is not an integer")
    _require(type(attempt["invocation_seed"]) is int, "invocation_seed is not an integer")
    _require(isinstance(raw, str), "raw_decoded_text is not text")
    _require(type(attempt["raw_length"]) is int and attempt["raw_length"] == len(raw), "raw_length drifted")
    _require(isinstance(attempt["leading_boundary_marker_run"], str), "leading boundary run is not text")
    _require(isinstance(attempt["trailing_boundary_marker_run"], str), "trailing boundary run is not text")
    _require(isinstance(cleaned, str), "cleaned_sequence is not text")
    _require(
        type(attempt["cleaned_length"]) is int and attempt["cleaned_length"] == len(cleaned),
        "cleaned_length does not match the cleaned sequence",
    )
    valid = recomputed_validity(cleaned)
    _require(attempt["validity"] is valid, "validity flag does not match the cleaned sequence")
    if valid:
        _require(attempt["invalid_reason"] is None, "a valid sequence carries an invalid reason")
    else:
        _require(
            isinstance(attempt["invalid_reason"], str) and attempt["invalid_reason"] != "",
            "an invalid sequence lacks an invalid reason",
        )
    _require(type(attempt["eos_marker_observed"]) is bool, "eos_marker_observed is not a boolean")
    expected_hit = bool(valid and len(cleaned) == requested)
    _require(attempt["exact_length_hit"] is expected_hit, "exact_length_hit does not match the raw-attempt rule")
    _require(
        type(attempt["length_delta"]) is int and attempt["length_delta"] == len(cleaned) - requested,
        "length_delta drifted",
    )
    expected_early = bool(valid and attempt["eos_marker_observed"] is True and len(cleaned) < requested)
    _require(attempt["early_eos"] is expected_early, "early_eos does not match validity, EOS, and length")
    if attempt["early_eos"] is True:
        _require(attempt["exact_length_hit"] is False, "early EOS was counted as an exact hit")
    parsed = raw != "" or cleaned != "" or attempt["raw_length"] == 0
    empty_or_unparseable = (not valid) and (cleaned == "" or raw == "")
    return {
        "valid": valid,
        "parsed": parsed and isinstance(raw, str),
        "empty_or_unparseable": (not valid) and (cleaned == "" or raw == ""),
        "exact_length_hit": expected_hit,
        "requested": requested,
        "cleaned": cleaned,
        "cleaned_length": len(cleaned),
    }


def _empty_bucket():
    return {
        "raw_attempts": 0,
        "parsed_outputs": 0,
        "valid_outputs": 0,
        "invalid_outputs": 0,
        "empty_or_unparseable_outputs": 0,
        "exact_length_hits": 0,
        "eos_marker_observations": 0,
        "early_eos_observations": 0,
        "cleaned_lengths": [],
        "shortfalls": [],
        "excesses": [],
        "valid_sequences": [],
    }


def _consume(bucket, attempt, checked):
    bucket["raw_attempts"] += 1
    if checked["parsed"]:
        bucket["parsed_outputs"] += 1
    cleaned_length = checked["cleaned_length"]
    requested = checked["requested"]
    bucket["cleaned_lengths"].append(cleaned_length)
    if cleaned_length < requested:
        bucket["shortfalls"].append(requested - cleaned_length)
    elif cleaned_length > requested:
        bucket["excesses"].append(cleaned_length - requested)
    if checked["valid"]:
        bucket["valid_outputs"] += 1
        bucket["valid_sequences"].append(checked["cleaned"])
    else:
        bucket["invalid_outputs"] += 1
    if checked["empty_or_unparseable"]:
        bucket["empty_or_unparseable_outputs"] += 1
    if checked["exact_length_hit"]:
        bucket["exact_length_hits"] += 1
    if attempt["eos_marker_observed"] is True:
        bucket["eos_marker_observations"] += 1
    if attempt["early_eos"] is True:
        bucket["early_eos_observations"] += 1


def _finish(bucket):
    duplicates = _duplicate_summary(bucket["valid_sequences"])
    raw_attempts = bucket["raw_attempts"]
    valid_outputs = bucket["valid_outputs"]
    return {
        "raw_attempts": raw_attempts,
        "parsed_outputs": bucket["parsed_outputs"],
        "valid_outputs": valid_outputs,
        "invalid_outputs": bucket["invalid_outputs"],
        "empty_or_unparseable_outputs": bucket["empty_or_unparseable_outputs"],
        "exact_length_hits": bucket["exact_length_hits"],
        "exact_hit_rate": _rate(bucket["exact_length_hits"], raw_attempts),
        "exact_hit_rate_denominator": EXACT_HIT_DENOMINATOR,
        "exact_hit_rate_valid_outputs_diagnostic": {
            "label": VALID_ONLY_EXACT_HIT_LABEL,
            "rate": _rate(bucket["exact_length_hits"], valid_outputs),
            "denominator": "valid_outputs",
            "replaces_approved_raw_attempt_metric": False,
        },
        "eos_marker_observations": bucket["eos_marker_observations"],
        "early_eos_observations": bucket["early_eos_observations"],
        "cleaned_length_distribution": _distribution(bucket["cleaned_lengths"]),
        "length_shortfall_distribution": _distribution(bucket["shortfalls"]),
        "length_excess_distribution": _distribution(bucket["excesses"]),
        "unique_valid_outputs": duplicates["unique_valid_outputs"],
        "duplicates": duplicates["duplicates"],
        "largest_duplicate_multiplicity": duplicates["largest_duplicate_multiplicity"],
        "largest_duplicate_share": duplicates["largest_duplicate_share"],
        "largest_duplicate_share_status": duplicates["largest_duplicate_share_status"],
    }


def summarise_attempts(attempts):
    """Summarise every mapped attempt. Do not drop invalid or mismatched rows."""
    if not isinstance(attempts, list):
        raise DiagnosticMetricError("attempt_ledger_invalid", "attempts must be a list")
    overall = _empty_bucket()
    by_length = {}
    for attempt in attempts:
        checked = validate_attempt_record(attempt)
        _consume(overall, attempt, checked)
        bucket = by_length.setdefault(checked["requested"], _empty_bucket())
        _consume(bucket, attempt, checked)
    per_length = []
    for requested in sorted(by_length):
        row = _finish(by_length[requested])
        row["requested_target_length"] = requested
        per_length.append(row)
    finished = _finish(overall)
    finished.update(
        {
            "schema_version": "m4-diagnostic-metrics-1",
            "by_requested_length": per_length,
            "exact_hit_rate_is_execution_success_requirement": (
                EXACT_HIT_RATE_IS_EXECUTION_SUCCESS_REQUIREMENT
            ),
            "low_exact_hit_rate_invalidates_or_reruns_the_diagnostic_pool": (
                LOW_EXACT_HIT_RATE_RERUNS_OR_INVALIDATES_THE_DIAGNOSTIC_POOL
            ),
            "independent_biological_replicates": INDEPENDENT_BIOLOGICAL_REPLICATES,
            "sample_description": "frozen_diagnostic_generation_sample",
            "all_raw_attempts_remain_visible": True,
            "invalid_or_unparseable_attempts_are_non_hits": True,
            "exact_hit_rate_computed_before_filtering": True,
            "deferred_beyond_m4": list(DEFERRED_BEYOND_M4),
            "implemented_metric_ids": list(IMPLEMENTED_METRIC_IDS),
        }
    )
    return finished


def _threshold_decision(guardrail_id, value, applicable):
    rule = GUARDRAIL_THRESHOLDS[guardrail_id]
    if not applicable or value is None:
        return {
            "id": guardrail_id,
            "value": value,
            "comparison": rule["comparison"],
            "threshold": rule["threshold"],
            "passed": False,
            "status": "undefined_empty_valid_denominator",
        }
    if rule["comparison"] == "minimum":
        passed = value >= rule["threshold"]
    else:
        passed = value <= rule["threshold"]
    return {
        "id": guardrail_id,
        "value": value,
        "comparison": rule["comparison"],
        "threshold": rule["threshold"],
        "passed": passed,
        "status": "evaluated",
    }


def evaluate_hard_guardrails(attempts, train_cores):
    """Eligibility guardrails from recomputed ledger fields.

    Exact-hit rate is not an eligibility threshold. Clustering and
    representation metrics stay deferred.
    """
    summary = summarise_attempts(attempts)
    if not isinstance(train_cores, (set, frozenset, list, tuple)):
        raise DiagnosticMetricError("train_reference_invalid", "TRAIN cores are missing")
    cores = []
    seen = set()
    for core in train_cores:
        if not isinstance(core, str) or CANONICAL_SEQUENCE.fullmatch(core) is None:
            raise DiagnosticMetricError("train_reference_invalid", "TRAIN core is not canonical A/C/G/U")
        if core not in seen:
            seen.add(core)
            cores.append(core)
    train = set(cores)
    matches = 0
    for attempt in attempts:
        checked = validate_attempt_record(attempt)
        if checked["valid"] and checked["cleaned"] in train:
            matches += 1
    raw = summary["raw_attempts"]
    valid = summary["valid_outputs"]
    unique = summary["unique_valid_outputs"]
    share = summary["largest_duplicate_share"]
    values = {
        "valid_nonempty_acgu_fraction": _rate(valid, raw),
        "empty_or_unparseable_fraction": _rate(summary["empty_or_unparseable_outputs"], raw),
        "unique_fraction": _rate(unique, valid),
        "exact_train_match_rate": _rate(matches, valid),
        "largest_duplicate_share": share,
    }
    decisions = []
    for guardrail_id in HARD_GUARDRAIL_IDS:
        if guardrail_id in ("valid_nonempty_acgu_fraction", "empty_or_unparseable_fraction"):
            applicable = raw > 0
        elif guardrail_id == "largest_duplicate_share":
            applicable = valid > 0 and share is not None
        else:
            applicable = valid > 0
        decisions.append(_threshold_decision(guardrail_id, values[guardrail_id], applicable))
    return {
        "schema_version": "m4-hard-guardrail-evaluation-1",
        "raw_attempts": raw,
        "valid_outputs": valid,
        "exact_train_matches": matches,
        "largest_duplicate_share": share,
        "largest_duplicate_share_numerator": LARGEST_DUPLICATE_SHARE_NUMERATOR,
        "largest_duplicate_share_denominator": LARGEST_DUPLICATE_SHARE_DENOMINATOR,
        "largest_duplicate_share_maximum": LARGEST_DUPLICATE_SHARE_MAXIMUM,
        "values": values,
        "decisions": decisions,
        "checkpoint_eligible": all(item["passed"] is True for item in decisions),
        "exact_hit_rate_is_an_eligibility_threshold": False,
        "approved_exact_hit_rate": summary["exact_hit_rate"],
        "approved_exact_hit_rate_denominator": EXACT_HIT_DENOMINATOR,
        "deferred_beyond_m4": list(DEFERRED_BEYOND_M4),
    }

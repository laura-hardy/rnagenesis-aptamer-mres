#!/usr/bin/env python3
"""Synthetic-only M9A overlap and TRAIN-leakage definitions.

The functions accept in-memory parsed rows and, for leakage, a caller-supplied
collection of distinct canonical TRAIN cores. They do not open a ledger, TRAIN,
VALIDATION, REF, EVAL, a model, a checkpoint, a structure resource, or an
AptaRank resource. There is no filesystem production entry point. A synthetic
call is not production validation, and it does not complete M9A, M9B, or M9C.
"""

from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from generator_eval_analysis import (
    OBSERVED_RANGE_STATEMENT,
    WEIGHTED_QUANTILE_RULE,
    _exact_observation_weight,
    weighted_empirical_quantiles,
)
from generator_eval_derived_ledger import (
    DERIVED_FIELDS,
    _contains_sequence_text,
    freeze_derived_row,
    sequence_free_accounting,
)
from generator_eval_parser import (
    CANONICAL_SEQUENCE,
    OUTCOME_VALID,
    _is_path_object,
    enforce_firewall,
    reject_control_string,
)
from m6_diagnostic_generation import (
    EDIT_SIMILARITY_DEFINITION,
    _quantiles,
    nearest_train,
)

STATUS = "FROZEN_DEFINITIONS_SYNTHETIC_ONLY_PRODUCTION_INPUTS_UNOPENED"
CONTRACT_ID = "m9a-overlap-leakage-definitions-v1"
CONDITIONS = ("B0", "B1", "B2", "D1")
CONDITION_PAIRS = (
    ("B0", "B1"),
    ("B0", "B2"),
    ("B0", "D1"),
    ("B1", "B2"),
    ("B1", "D1"),
    ("B2", "D1"),
)
D1_SEEDS = (43, 44)
PRODUCTION_MANIFEST_SHA256 = "9aa5f60f939a8b25d031967ed3466a26d9d8e2d0610c76ec0b5db4cb43c2cc80"
COMBINED_LEDGER_SHA256 = "d50c30e85b26e39e8a25ea2660f9a7fa07433417de757364eb36799ca8c6073e"
GOVERNING_PLAN_SHA256 = "fc6963f01f7d4ab311774865bda15626facdb753ffa0db06b01b338d88162b51"
PRODUCTION_EXTENSION_FIELDS = (
    "ledger_schema",
    "is_valid_canonical",
    "valid_sequence_multiplicity",
    "is_exact_duplicate_within_condition",
)
DEFINITION_GROUPS = (
    "cross_condition_overlap",
    "distinct_sequence_sensitivity",
    "exact_train_leakage",
    "nearest_train_normalized_edit_distance",
)
REQUIRED_DEFINITION_FIELDS = ("numerator", "denominator", "grain", "direction")
ROW_QUANTILE_CONVENTION = "int(round(p * (n - 1))) on values sorted ascending"


class OverlapLeakageError(ValueError):
    """The frozen overlap or leakage definition refused the request."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def _require(mapping, key, label):
    if type(mapping) is not dict or key not in mapping:
        raise OverlapLeakageError("definition_absent", label + " is absent")
    value = mapping[key]
    if value is None or value == "" or value == [] or value == {}:
        raise OverlapLeakageError("definition_absent", label + " is absent")
    return value


def _require_sha256(value, label, expected):
    if type(value) is not str or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise OverlapLeakageError("definition_absent", label + " is absent")
    if value != expected:
        raise OverlapLeakageError("digest_mismatch", label + " does not match the frozen digest")
    return value


def assert_frozen_definitions(contract):
    """Fail closed when a required frozen definition is absent."""
    if type(contract) is not dict:
        if _is_path_object(contract) or type(contract) is str:
            reject_control_string(contract)
        raise OverlapLeakageError("contract_invalid", "the contract is not an in-memory object")
    if contract.get("status") != STATUS:
        raise OverlapLeakageError("contract_status_invalid", "the contract status is not the frozen synthetic status")
    if contract.get("contract_id") != CONTRACT_ID:
        raise OverlapLeakageError("contract_status_invalid", "the contract identity is not the frozen identity")
    if contract.get("synthetic_execution_is_production_validation") is not False:
        raise OverlapLeakageError("contract_status_invalid", "a synthetic run is not production validation")
    if contract.get("m9a_complete") is not False or contract.get("m9b_complete") is not False or contract.get("m9c_complete") is not False:
        raise OverlapLeakageError("milestone_completion_refused", "M9A, M9B, and M9C are not complete")
    if contract.get("production_train_loader") is not False or contract.get("filesystem_production_entry_point") is not False:
        raise OverlapLeakageError("production_entry_refused", "this gate has no production loader or filesystem entry point")
    references = _require(contract, "references", "references")
    if references.get("parser_version") != "m9-biological-parser-v1":
        raise OverlapLeakageError("definition_absent", "parser m9-biological-parser-v1 is absent")
    if references.get("adapter_version") != "m9-source-adapter-v2":
        raise OverlapLeakageError("definition_absent", "adapter m9-source-adapter-v2 is absent")
    manifest = _require(references, "production_manifest", "production manifest")
    _require_sha256(manifest.get("sha256"), "production manifest digest", PRODUCTION_MANIFEST_SHA256)
    if manifest.get("opened_by_this_contract") is not False:
        raise OverlapLeakageError("production_input_refused", "the production manifest stays unopened")
    ledger = _require(references, "combined_ledger", "combined ledger")
    _require_sha256(ledger.get("sha256"), "combined ledger digest", COMBINED_LEDGER_SHA256)
    if ledger.get("opened_by_this_contract") is not False:
        raise OverlapLeakageError("production_input_refused", "the combined ledger stays unopened")
    if ledger.get("valid_canonical_attempt_rows") != 120080:
        raise OverlapLeakageError("definition_absent", "the 120,080 valid canonical attempt-row count is absent")
    plan = _require(references, "governing_plan", "governing plan")
    _require_sha256(plan.get("sha256"), "governing plan digest", GOVERNING_PLAN_SHA256)
    gep2 = _require(references, "gep2_metric_specification", "GEP-2 metric specification")
    if gep2.get("freeze_status") != "draft" or gep2.get("remains_draft") is not True:
        raise OverlapLeakageError("definition_absent", "the draft status of the GEP-2 metric specification is absent")
    if references.get("cross_condition_overlap_computed_on_production_rows") is not False:
        raise OverlapLeakageError("production_result_refused", "production cross-condition overlap is not computed")
    if references.get("train_leakage_computed_on_production_rows") is not False:
        raise OverlapLeakageError("production_result_refused", "production TRAIN leakage is not computed")
    label = _require(contract, "within_condition_distinct_sum_label", "within-condition distinct sum label")
    if label.get("field") != "overall.distinct_valid_sequences" or label.get("value") != 120063:
        raise OverlapLeakageError("definition_absent", "the within-condition distinct-sum label is absent")
    if label.get("is_global_distinctness") is not False:
        raise OverlapLeakageError("global_distinctness_relabel_refused", "the within-condition sum is not global distinctness")
    definitions = _require(contract, "definitions", "definitions")
    for name in DEFINITION_GROUPS:
        group = definitions.get(name)
        if type(group) is not dict:
            raise OverlapLeakageError("definition_absent", name + " is absent")
        for field in REQUIRED_DEFINITION_FIELDS:
            _require(group, field, name + " " + field)
    overlap = definitions["cross_condition_overlap"]
    pairs = _require(overlap, "condition_pairs", "condition_pairs")
    expected_pairs = [list(pair) for pair in CONDITION_PAIRS]
    if pairs != expected_pairs:
        raise OverlapLeakageError("condition_pairs_invalid", "condition pairs differ from the frozen six unordered pairs")
    if overlap.get("b0_role") != "external_comparator" or overlap.get("b0_pooled_into_b1_b2_d1_aggregate") is not False:
        raise OverlapLeakageError("definition_absent", "the B0 external-comparator definition is absent")
    leakage = definitions["exact_train_leakage"]
    if leakage.get("historical_0_01_guardrail_used_as_decision_threshold") is not False:
        raise OverlapLeakageError("guardrail_threshold_refused", "the historical 0.01 guardrail is not a decision threshold")
    if leakage.get("partial_match") is not False or leakage.get("substring_match") is not False:
        raise OverlapLeakageError("match_definition_refused", "TRAIN leakage is full parsed-string membership")
    d1 = _require(leakage, "d1", "D1 leakage definition")
    if d1.get("expected_training_seeds") != [43, 44]:
        raise OverlapLeakageError("definition_absent", "the D1 seed pair is absent")
    if d1.get("confidence_interval") is not False or d1.get("bootstrap") is not False or d1.get("hypothesis_test") is not False:
        raise OverlapLeakageError("inference_refused", "D1 leakage has no confidence interval, bootstrap, or hypothesis test")
    nearest = definitions["nearest_train_normalized_edit_distance"]
    pooled = _require(nearest, "pooled_equal_mixture_distance_quantile", "pooled D1 distance quantile")
    if pooled.get("rule") != WEIGHTED_QUANTILE_RULE or pooled.get("new_rule_invented") is not False:
        raise OverlapLeakageError("definition_absent", "the existing weighted-quantile rule is absent")
    if nearest.get("edit_similarity_is_sequence_identity") is not False:
        raise OverlapLeakageError("definition_absent", "edit similarity is not sequence identity")
    return contract


def _begin(contract, controls):
    enforce_firewall(controls)
    return assert_frozen_definitions(contract)


def _refuse_control_value(value):
    """Refuse a path, role, protected filename, or path-like object.

    A canonical sequence string is not a control value. ``reject_control_string``
    returns without effect for that string.
    """
    if _is_path_object(value):
        reject_control_string(value)
        raise OverlapLeakageError("filesystem_path_refused", "a filesystem path argument is refused")
    if type(value) is str:
        reject_control_string(value)


def _reject_non_collection(value, code, detail):
    if _is_path_object(value) or type(value) is str:
        _refuse_control_value(value)
        raise OverlapLeakageError(code, detail)


def validate_train_cores(train_cores):
    """Accept only a nonempty in-memory collection of distinct canonical cores.

    A list or tuple preserves duplicate declarations and fails closed on them.
    A set or frozenset is already a distinct collection. Either form must be
    nonempty and every core must match ``^[ACGU]+$``.
    """
    _reject_non_collection(train_cores, "train_cores_invalid", "TRAIN cores are not an in-memory collection")
    if isinstance(train_cores, (set, frozenset)):
        declared = list(train_cores)
    elif type(train_cores) in (list, tuple):
        declared = list(train_cores)
    else:
        raise OverlapLeakageError("train_cores_invalid", "TRAIN cores are not an in-memory collection")
    if not declared:
        raise OverlapLeakageError("train_cores_empty", "TRAIN cores are empty")
    seen = set()
    for core in declared:
        if _is_path_object(core):
            _refuse_control_value(core)
        if type(core) is not str:
            raise OverlapLeakageError("train_core_invalid", "a TRAIN core is not canonical A/C/G/U")
        _refuse_control_value(core)
        if CANONICAL_SEQUENCE.fullmatch(core) is None:
            raise OverlapLeakageError("train_core_invalid", "a TRAIN core is not canonical A/C/G/U")
        if core in seen:
            raise OverlapLeakageError("duplicate_train_cores", "a supplied TRAIN core is duplicated")
        seen.add(core)
    return seen


def _normalize_row(row):
    if type(row) is not dict:
        _reject_non_collection(row, "row_invalid", "a parsed row is not an object")
        raise OverlapLeakageError("row_invalid", "a parsed row is not an object")
    unexpected = [key for key in row if key not in DERIVED_FIELDS and key not in PRODUCTION_EXTENSION_FIELDS]
    if unexpected:
        raise OverlapLeakageError("row_invalid", "a parsed row has an unexpected field")
    if "is_valid_canonical" in row and row["is_valid_canonical"] is not (row.get("outcome") == OUTCOME_VALID):
        raise OverlapLeakageError("row_invalid", "is_valid_canonical disagrees with the parsed outcome")
    stripped = {key: row[key] if key in row else None for key in DERIVED_FIELDS}
    if "requested_biological_length_available" not in row:
        stripped["requested_biological_length_available"] = False
    if "equal_seed_weighting_applied" not in row:
        stripped["equal_seed_weighting_applied"] = False
    return freeze_derived_row(stripped)


def _rows(rows):
    _reject_non_collection(rows, "rows_invalid", "parsed rows are not an in-memory list")
    if type(rows) is not list:
        raise OverlapLeakageError("rows_invalid", "parsed rows are not an in-memory list")
    frozen = [_normalize_row(row) for row in rows]
    identifiers = []
    for row in frozen:
        record_id = row["record_id"]
        if type(record_id) is not str or record_id == "":
            raise OverlapLeakageError("record_id_invalid", "a parsed row has no record id")
        identifiers.append(record_id)
    if len(set(identifiers)) != len(identifiers):
        raise OverlapLeakageError("record_id_duplicated", "a parsed row id is duplicated")
    return frozen


def _partition(rows):
    grouped = {condition: [] for condition in CONDITIONS}
    for row in rows:
        condition = row["condition"]
        if condition not in grouped:
            raise OverlapLeakageError("condition_invalid", "a parsed row has an unknown condition")
        grouped[condition].append(row)
    return grouped


def _valid_sequences(rows):
    sequences = []
    for row in rows:
        if row["outcome"] != OUTCOME_VALID:
            continue
        sequence = row["parsed_sequence"]
        if type(sequence) is not str or CANONICAL_SEQUENCE.fullmatch(sequence) is None:
            raise OverlapLeakageError("valid_sequence_invalid", "a valid row is not canonical A/C/G/U")
        sequences.append(sequence)
    return sequences


def _rate(numerator, denominator):
    if type(numerator) is not int or type(denominator) is not int or isinstance(numerator, bool) or isinstance(denominator, bool):
        raise OverlapLeakageError("rate_invalid", "a rate numerator or denominator is not an integer")
    if numerator < 0 or denominator < 0 or numerator > denominator:
        raise OverlapLeakageError("rate_invalid", "a rate count is outside its denominator")
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": None if denominator == 0 else numerator / denominator,
    }


def _row_coverage(source_sequences, target_members):
    numerator = sum(1 for sequence in source_sequences if sequence in target_members)
    return _rate(numerator, len(source_sequences))


def _attempt_accounting(grouped):
    accounting = {}
    for condition in CONDITIONS:
        projection = sequence_free_accounting(grouped[condition])
        projection["role"] = "external_comparator" if condition == "B0" else "generation_condition"
        projection["invalid_rows_deleted"] = False
        projection["invalid_rows_excluded_from_valid_denominators"] = True
        accounting[condition] = projection
    return accounting


def _within_condition_sum(contract, accounting):
    label = contract["within_condition_distinct_sum_label"]
    synthetic_sum = sum(accounting[condition]["unique_valid_sequences"] for condition in CONDITIONS)
    return {
        "synthetic_sum_of_within_condition_distinct_counts": synthetic_sum,
        "synthetic_sum_is_global_distinctness": False,
        "production_field": label["field"],
        "production_value": label["value"],
        "production_meaning": label["meaning"],
        "production_value_is_global_distinctness": False,
        "production_value_reused_as_global_distinctness": False,
    }


def _global_membership(sequences_by_condition):
    membership = {}
    for condition in CONDITIONS:
        for sequence in set(sequences_by_condition[condition]):
            membership.setdefault(sequence, set()).add(condition)
    exactly = {1: 0, 2: 0, 3: 0, 4: 0}
    pattern_counts = {}
    for conditions in membership.values():
        key = tuple(condition for condition in CONDITIONS if condition in conditions)
        exactly[len(key)] += 1
        pattern_counts[key] = pattern_counts.get(key, 0) + 1
    patterns = [
        {"conditions": list(key), "distinct_sequence_count": pattern_counts[key]}
        for key in sorted(pattern_counts, key=lambda item: (len(item), item))
    ]
    union_size = len(membership)
    pattern_sum = sum(item["distinct_sequence_count"] for item in patterns)
    exactly_sum = exactly[1] + exactly[2] + exactly[3] + exactly[4]
    del membership
    if pattern_sum != union_size or exactly_sum != union_size:
        raise OverlapLeakageError(
            "membership_reconciliation_failed",
            "membership counts do not sum to the global union",
        )
    return {
        "global_distinct_valid_sequence_count": union_size,
        "distinct_sequences_in_exactly_n_conditions": {str(count): exactly[count] for count in (1, 2, 3, 4)},
        "membership_patterns": patterns,
        "membership_pattern_counts_sum_to_global_union": True,
        "exactly_n_condition_counts_sum_to_global_union": True,
        "sequence_strings_emitted": False,
        "sequence_hashes_emitted": False,
    }


def _pair(condition_a, condition_b, sequences_by_condition):
    sequences_a = sequences_by_condition[condition_a]
    sequences_b = sequences_by_condition[condition_b]
    members_a = set(sequences_a)
    members_b = set(sequences_b)
    shared = len(members_a & members_b)
    union = len(members_a | members_b)
    includes_b0 = condition_a == "B0" or condition_b == "B0"
    return {
        "condition_a": condition_a,
        "condition_b": condition_b,
        "unordered": True,
        "b0_role": "external_comparator" if includes_b0 else None,
        "calculated_identically": True,
        "pooled_into_b1_b2_d1_aggregate": False,
        "b0_included_in_causal_comparison": False,
        "row_coverage": {
            "a_to_b": _row_coverage(sequences_a, members_b),
            "b_to_a": _row_coverage(sequences_b, members_a),
        },
        "distinct": {
            "shared_sequence_count": shared,
            "a_distinct_coverage_by_b": _rate(shared, len(members_a)),
            "b_distinct_coverage_by_a": _rate(shared, len(members_b)),
            "union_count": union,
            "jaccard": _rate(shared, union),
        },
    }


def _assert_sequence_free(summary):
    if _contains_sequence_text(summary):
        raise OverlapLeakageError("summary_sequence_leak", "the summary contains sequence text")
    return summary


def _common_header(contract):
    return {
        "contract_id": contract["contract_id"],
        "status": contract["status"],
        "synthetic_execution_is_production_validation": False,
        "m9a_complete": False,
        "m9b_complete": False,
        "m9c_complete": False,
        "sequence_strings_emitted": False,
        "sequence_hashes_emitted": False,
        "b0_role": "external_comparator",
        "b0_pooled_into_b1_b2_d1_aggregate": False,
        "b0_included_in_causal_comparison": False,
    }


def cross_condition_overlap(rows, contract, **controls):
    """Unordered-pair overlap on valid canonical rows, plus sequence-free global accounting."""
    frozen_contract = _begin(contract, controls)
    parsed = _rows(rows)
    grouped = _partition(parsed)
    sequences = {condition: _valid_sequences(grouped[condition]) for condition in CONDITIONS}
    accounting = _attempt_accounting(grouped)
    summary = _common_header(frozen_contract)
    summary.update(
        {
            "input_population": "valid_canonical_parsed_rows_only",
            "invalid_rows_deleted": False,
            "invalid_rows_excluded_from_valid_denominators": True,
            "attempt_accounting": accounting,
            "within_condition_distinct_sum": _within_condition_sum(frozen_contract, accounting),
            "pairs": [_pair(condition_a, condition_b, sequences) for condition_a, condition_b in CONDITION_PAIRS],
            "global_sequence_free_accounting": _global_membership(sequences),
        }
    )
    return _assert_sequence_free(summary)


def _leakage_rates(sequences, train_cores):
    row_numerator = sum(1 for sequence in sequences if sequence in train_cores)
    distinct = set(sequences)
    distinct_numerator = sum(1 for sequence in distinct if sequence in train_cores)
    return {
        "row": _rate(row_numerator, len(sequences)),
        "distinct": _rate(distinct_numerator, len(distinct)),
    }


def _condition_leakage(grouped, train_cores):
    reported = {}
    for condition in CONDITIONS:
        rates = _leakage_rates(_valid_sequences(grouped[condition]), train_cores)
        reported[condition] = {
            "role": "external_comparator" if condition == "B0" else "generation_condition",
            "pooled_into_b1_b2_d1_aggregate": False,
            "row_leakage": rates["row"],
            "distinct_sequence_sensitivity": rates["distinct"],
            "partial_match": False,
            "substring_match": False,
            "identity_threshold": None,
            "historical_0_01_guardrail_used_as_decision_threshold": False,
        }
    return reported


def _d1_rows_by_seed(rows):
    grouped = {seed: [] for seed in D1_SEEDS}
    seen = set()
    for row in rows:
        seed = row["d1_training_seed"]
        if type(seed) is not int or isinstance(seed, bool) or seed not in D1_SEEDS:
            raise OverlapLeakageError("d1_seed_invalid", "a D1 training seed is outside the frozen pair")
        seen.add(seed)
        grouped[seed].append(row)
    for seed in D1_SEEDS:
        if seed not in seen:
            raise OverlapLeakageError(
                "d1_seed_missing",
                "expected D1 training seed %d is absent and is not replaced with a pooled estimate" % seed,
            )
    return grouped


def _d1_exact_leakage(rows, train_cores):
    grouped = _d1_rows_by_seed(rows)
    reports = {}
    for seed in D1_SEEDS:
        sequences = _valid_sequences(grouped[seed])
        if not sequences:
            raise OverlapLeakageError(
                "d1_valid_denominator_zero",
                "D1 training seed %d has a zero valid denominator and is not replaced with a pooled estimate" % seed,
            )
        reports[seed] = _leakage_rates(sequences, train_cores)
    rates = (reports[43]["row"]["rate"], reports[44]["row"]["rate"])
    pooled = _leakage_rates(_valid_sequences(rows), train_cores)
    return {
        "expected_training_seeds": [43, 44],
        "seed_43_valid_conditional_row_rate": reports[43]["row"],
        "seed_44_valid_conditional_row_rate": reports[44]["row"],
        "seed_43_distinct_sequence_sensitivity": reports[43]["distinct"],
        "seed_44_distinct_sequence_sensitivity": reports[44]["distinct"],
        "unweighted_arithmetic_mean_of_seed_specific_row_rates": (rates[0] + rates[1]) / 2,
        "observed_range": {"minimum": min(rates), "maximum": max(rates)},
        "observed_range_statement": OBSERVED_RANGE_STATEMENT,
        "confidence_interval": None,
        "bootstrap": False,
        "hypothesis_test": False,
        "actual_attempt_pooled": {
            "label": "actual_attempt_pooled",
            "separately_labelled": True,
            "replaces_seed_specific_rates": False,
            "row_leakage": pooled["row"],
            "distinct_sequence_sensitivity": pooled["distinct"],
        },
    }


def exact_train_leakage(rows, train_cores, contract, **controls):
    """Exact full-string TRAIN membership. The historical 0.01 guardrail is not applied."""
    frozen_contract = _begin(contract, controls)
    cores = validate_train_cores(train_cores)
    parsed = _rows(rows)
    grouped = _partition(parsed)
    summary = _common_header(frozen_contract)
    summary.update(
        {
            "match": "full_parsed_string_membership",
            "partial_match": False,
            "substring_match": False,
            "identity_threshold": None,
            "historical_0_01_guardrail_used_as_decision_threshold": False,
            "production_train_loader": False,
            "supplied_distinct_train_core_count": len(cores),
            "by_condition": _condition_leakage(grouped, cores),
            "d1": _d1_exact_leakage(grouped["D1"], cores),
        }
    )
    return _assert_sequence_free(summary)


def _distance_block(rows, train_core_list):
    sequences = _valid_sequences(rows)
    distinct = sorted(set(sequences))
    nearest = {sequence: nearest_train(sequence, train_core_list) for sequence in distinct}
    projected = [nearest[sequence] for sequence in sequences]
    if projected:
        maximum_similarity = 1.0 - min(projected)
    else:
        maximum_similarity = None
    return {
        "valid_row_count": len(projected),
        "distinct_valid_sequence_count": len(distinct),
        "distinct_distance_computations": len(distinct),
        "row_distance_projections": len(projected),
        "nearest_train_normalized_edit_distance": _quantiles(projected),
        "maximum_edit_similarity_to_train": maximum_similarity,
        "maximum_edit_similarity_definition": EDIT_SIMILARITY_DEFINITION,
        "edit_similarity_is_sequence_identity": False,
        "thresholds_defined": False,
        "historical_0_01_guardrail_used_as_decision_threshold": False,
        "quantile_convention": ROW_QUANTILE_CONVENTION,
    }


def _d1_distance(rows, train_core_list):
    grouped = _d1_rows_by_seed(rows)
    per_seed = {}
    observations = []
    absent_reason = None
    for seed in D1_SEEDS:
        valid_rows = [row for row in grouped[seed] if row["outcome"] == OUTCOME_VALID]
        per_seed[str(seed)] = _distance_block(grouped[seed], train_core_list)
        if not valid_rows:
            absent_reason = "zero_valid_denominator"
            continue
        if absent_reason is not None:
            continue
        weight = _exact_observation_weight(len(D1_SEEDS), len(valid_rows))
        nearest = {}
        for row in valid_rows:
            sequence = row["parsed_sequence"]
            if sequence not in nearest:
                nearest[sequence] = nearest_train(sequence, train_core_list)
            observations.append((nearest[sequence], weight, row["record_id"]))
    pooled = None
    if absent_reason is None:
        pooled = weighted_empirical_quantiles(observations)
        if pooled is None:
            absent_reason = "no_observations"
    return {
        "by_training_seed": per_seed,
        "pooled_equal_mixture_distance_quantiles": pooled,
        "pooled_equal_mixture_distance_quantiles_absent": pooled is None,
        "pooled_equal_mixture_absent_reason": absent_reason,
        "pooled_equal_mixture_rule": None if pooled is None else WEIGHTED_QUANTILE_RULE,
        "new_quantile_rule_invented": False,
    }


def nearest_train_distance_summaries(rows, train_cores, contract, **controls):
    """Project one nearest-TRAIN distance per distinct sequence back onto valid rows.

    D1 seed-specific quantiles use the frozen row-quantile convention. The
    pooled equal-mixture quantile reuses ``inclusive_cumulative_weight_exact_v2``
    only when both expected seeds have a positive valid-row count.
    """
    frozen_contract = _begin(contract, controls)
    cores = validate_train_cores(train_cores)
    core_list = sorted(cores)
    parsed = _rows(rows)
    grouped = _partition(parsed)
    by_condition = {}
    for condition in CONDITIONS:
        block = _distance_block(grouped[condition], core_list)
        block["role"] = "external_comparator" if condition == "B0" else "generation_condition"
        block["pooled_into_b1_b2_d1_aggregate"] = False
        by_condition[condition] = block
    summary = _common_header(frozen_contract)
    summary.update(
        {
            "production_train_loader": False,
            "supplied_distinct_train_core_count": len(cores),
            "by_condition": by_condition,
            "d1": _d1_distance(grouped["D1"], core_list),
        }
    )
    return _assert_sequence_free(summary)

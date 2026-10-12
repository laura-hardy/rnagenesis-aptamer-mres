#!/usr/bin/env python3
"""ARP-2B synthetic Tier 1 joining and accounting.

This module normalizes a future AptaRank download into one disposition per
expected candidate. Normalization here means accounting: it is not the
AptaRank normalized-MFE component. The deployed AptaRank UI remains the
scorer. The no-argument command runs bundled synthetic fixtures only.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from fractions import Fraction

PACKAGE_ID = "ARP-2B"
SCHEMA_VERSION = "aptarank-tier1-arp2b-draft-r2"
SPEC_RELATIVE = "config/modelling/aptarank_tier1_analysis_spec.json"
ARP2A_RELATIVE = "docs/aptarank_arp2a_tier1_reconciliation.md"
GOVERNING_PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan.md"
FIXTURE_RELATIVE = "tests/modelling/fixtures/aptarank_arp2"
SCORER_OWNER = "deployed AptaRank UI"
JOIN_KEY = "candidate_id"
PAIRED_DIRECTION = "real_minus_control"
COUNT_LABEL = "synthetic"
PRIVATE_KEY_ROLE = "synthetic_private_key"
CLASS_LABELS = ("real", "uniform_control")
PRIVATE_KEY_FIELDS = (
    "candidate_id",
    "class_label",
    "pair_id",
    "parent_core_id",
    "cluster_id",
    "length",
)
PRIVATE_KEY_DOCUMENT_FIELDS = (
    "fixture_role",
    "count_label",
    "candidates",
)
IDENTIFIER_FIELDS = (
    "candidate_id",
    "pair_id",
    "parent_core_id",
    "cluster_id",
)
PAIR_AGREEMENT_FIELDS = (
    "parent_core_id",
    "cluster_id",
    "length",
)
UNRESOLVED_IDS = tuple("U%d" % index for index in range(1, 39))
LOCAL_RECOMPUTATION_IDS = tuple("U%d" % index for index in range(1, 22))
COMPONENT_TABLE_IDS = tuple("U%d" % index for index in range(1, 12))
PRODUCTION_DESIGN_CONSTANTS = {
    "ref_calibration_cores": 113,
    "eval_cores": 154,
    "blinded_input_rows_before_technical_rejection": 308,
    "eval_clusters_before_technical_rejection": 79,
}
RECOMPUTATION_REQUESTS = (
    "normalized_mfe",
    "ensemble_defect",
    "positional_entropy",
    "stem_fraction",
    "gc_fraction",
    "empirical_ref_calibration",
    "composite",
    "composite_aptamer_likeness",
    "aptamer_likeness",
    "component",
    "component_table",
    "dinucleotide_shuffle",
    "shuffle",
    "shuffle_p_value",
)
BLOCKED_OUTPUTS = (
    {
        "output": "median_and_iqr",
        "blocking_ids": ["U30"],
        "reason": (
            "Median and IQR stay blocked until the quantile convention in U30 is prespecified."
        ),
    },
    {
        "output": "aggregate_paired_effect_functional_and_ci",
        "blocking_ids": ["U31"],
        "reason": (
            "The real-minus-control direction is fixed. The aggregate paired-effect "
            "functional and its confidence interval stay blocked by U31."
        ),
    },
    {
        "output": "auroc",
        "blocking_ids": ["U29", "U32"],
        "reason": "AUROC stays blocked. Live score direction is U29 and tie handling is U32.",
    },
    {
        "output": "shuffle_pass_rates_or_interpretation",
        "blocking_ids": ["U19", "U21", "U33"],
        "reason": (
            "Shuffle tokens stay uninterpreted. Pass rates and shuffle interpretation "
            "stay blocked by U19, U21, and U33."
        ),
    },
    {
        "output": "secondary_paired_test",
        "blocking_ids": ["U34"],
        "reason": "The secondary paired test stays blocked by U34. No test is selected or computed.",
    },
    {
        "output": "bootstrap_intervals",
        "blocking_ids": ["U35", "U36", "U37", "U38"],
        "reason": "Bootstrap intervals stay blocked by U35, U36, U37, and U38. No resample is drawn.",
    },
    {
        "output": "component_table_without_verified_deployment",
        "blocking_ids": list(COMPONENT_TABLE_IDS),
        "reason": (
            "No component table is supplied by a verified deployment. "
            "Local component recomputation stays blocked."
        ),
    },
    {
        "output": "local_scorer_recomputation",
        "blocking_ids": list(LOCAL_RECOMPUTATION_IDS),
        "reason": (
            "The deployed AptaRank UI is the scorer. Local recomputation of scorer "
            "internals stays blocked by U1 through U21."
        ),
    },
    {
        "output": "uniform_control_generation",
        "blocking_ids": ["U22", "U23", "U24"],
        "reason": "Uniform-control generation stays blocked by U22, U23, and U24.",
    },
    {
        "output": "opaque_production_ids",
        "blocking_ids": ["U25", "U26"],
        "reason": "Opaque production-id creation stays blocked by U25 and U26.",
    },
    {
        "output": "full_ranking_schema",
        "blocking_ids": ["U27", "U28", "U29"],
        "reason": "A full-ranking schema stays blocked by U27, U28, and U29. ARP-1 is unchanged.",
    },
)
IMPLEMENTED = (
    "Validate a synthetic private key before set, sort, or id lookup.",
    "Reuse ARP-1 parsing and mechanical validation for uploads, export rows, and explicit failures.",
    "Join validated export rows and explicit failures to the private key by opaque candidate id.",
    "Account for every expected candidate exactly once.",
    "Construct real and uniform_control pairs without using row position.",
    "Distinguish group-level evaluable rows from complete pairs.",
    "Preserve technical failures as missing technical outcomes and never as numeric zero.",
    "Retain a successful exported score of zero as a numeric value.",
    "Preserve finite aptamer-likeness tokens and represent each nonempty group arithmetic mean as an exact rational.",
    "Require one parent_core_id for each pair_id.",
    "Reject a repeated canonical sequence inside the supplied candidate upload without closing U23.",
    "Report the pre-rejection cluster count from the private key.",
    "Record the real-minus-control direction and the eligible paired-difference count.",
    "Leave unresolved statistical and UI-dependent results blocked.",
    "Record production design constants without enforcing them on synthetic fixtures.",
)
TOP_LEVEL_KEYS = (
    "package_id",
    "schema_version",
    "status",
    "deployment_verified",
    "eval_access",
    "scientific_result",
    "full_tier1_statistical_analysis",
    "aggregate_tier1_tier2_score",
    "scorer_owner",
    "provisional_camera_ready_formula_adopted",
    "governing_plan",
    "arp2a_reconciliation",
    "analysis_module",
    "arp1_dependency",
    "production_design_constants",
    "scoring_boundary",
    "interpretation_boundary",
    "private_key_contract",
    "reconciliation_contract",
    "report_contract",
    "implemented",
    "blocked_outputs",
    "unresolved_ids",
    "unresolved_register",
    "rules",
)
RULE_KEYS = (
    "opaque_id",
    "length_type",
    "unique_candidate_ids",
    "pair_cardinality",
    "pair_class_composition",
    "pair_field_agreement",
    "join_by_candidate_id",
    "exactly_one_disposition",
    "zero_score_is_numeric",
    "technical_failure_not_zero",
    "no_row_position",
    "production_counts_not_enforced_on_synthetic",
    "no_local_rescoring",
    "no_aggregate_tier_score",
    "no_binding_interpretation",
    "one_parent_core_per_pair",
    "duplicate_candidate_sequence",
    "exact_arithmetic_mean",
    "reviewed_specification",
)
SCORING_BOUNDARY_FLAGS = (
    "local_recompute_normalized_mfe",
    "local_recompute_ensemble_defect",
    "local_recompute_positional_entropy",
    "local_recompute_stem_fraction",
    "local_recompute_gc_fraction",
    "local_recompute_empirical_ref_calibration",
    "local_recompute_composite_aptamer_likeness",
    "local_recompute_dinucleotide_shuffles",
    "local_recompute_shuffle_p_values",
)
BUNDLED_FIXTURES = {
    "private_key": "synthetic_private_key.json",
    "candidate_upload": "synthetic_candidate_upload.csv",
    "shortlist_export": "synthetic_shortlist_export.csv",
    "failure_accounting": "synthetic_failure_accounting.json",
}
EMPTY_FIXTURES = {
    "private_key": "empty_private_key.json",
    "candidate_upload": "empty_candidate_upload.csv",
    "shortlist_export": "empty_shortlist_export.csv",
    "failure_accounting": "empty_failure_accounting.json",
}
ALLOWED_FIXTURE_NAMES = frozenset(tuple(BUNDLED_FIXTURES.values()) + tuple(EMPTY_FIXTURES.values()))
SYNTHETIC_ONLY_STATEMENT = (
    "This demonstration used only synthetic fixtures and loaded no EVAL, REF, "
    "VALIDATION, TRAIN, production pool or checkpoint."
)
UNDEFINED_MEAN_REASON = "undefined: no evaluable exported score in this group"
MEAN_APPROXIMATION_PRECISION = 28
MEAN_APPROXIMATION_ROUNDING = "ROUND_HALF_EVEN"
TECHNICAL_NOT_SCIENTIFIC = (
    "This output is synthetic joining and accounting. It is not a scientific result "
    "and it is not the full Tier 1 statistical analysis."
)


def _load_arp1():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aptarank_io_preflight.py")
    spec = importlib.util.spec_from_file_location("aptarank_io_preflight_for_arp2b", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


arp1 = _load_arp1()


class AptaRankTier1Error(ValueError):
    """The synthetic Tier 1 accounting contract refused the input."""

    def __init__(self, code, detail, errors=None):
        if errors is None:
            errors = [{"code": code, "detail": detail}]
        self.errors = list(errors)
        self.code = self.errors[0]["code"]
        self.detail = self.errors[0]["detail"]
        super().__init__(self.code + ": " + self.detail)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def spec_path():
    return os.path.join(repo_root(), SPEC_RELATIVE)


def fixture_root():
    return os.path.join(repo_root(), FIXTURE_RELATIVE)


def _raise_from(errors):
    try:
        errors.raise_if_any()
    except arp1.AptaRankIOError as exc:
        raise AptaRankTier1Error(exc.code, exc.detail, exc.errors) from exc


def _require(condition, code, detail):
    if not condition:
        raise AptaRankTier1Error(code, detail)


def _keys_match(document, expected):
    if len(document) != len(expected):
        return False
    for key in expected:
        if key not in document:
            return False
    return True


def _blocked_copy():
    blocked = []
    for item in BLOCKED_OUTPUTS:
        blocked.append(
            {
                "output": item["output"],
                "value": None,
                "blocking_ids": list(item["blocking_ids"]),
                "reason": item["reason"],
            }
        )
    return blocked


def validate_spec_document(spec):
    """Refuse a spec that leaves draft status or resolves a blocked decision."""
    _require(isinstance(spec, dict), "spec_invalid", "the analysis spec is not an object")
    _require(_keys_match(spec, TOP_LEVEL_KEYS), "spec_schema_drift", "the analysis spec keys changed")
    _require(spec["package_id"] == PACKAGE_ID, "spec_invalid", "the package id is not ARP-2B")
    _require(spec["schema_version"] == SCHEMA_VERSION, "spec_invalid", "the schema version is not the ARP-2B draft")
    _require(spec["status"] == "draft", "spec_invalid", "ARP-2B status must remain draft")
    if spec["deployment_verified"] is True:
        raise AptaRankTier1Error("deployment_verified_refused", "ARP-2B cannot mark the deployment verified")
    _require(spec["deployment_verified"] is False, "spec_invalid", "deployment_verified must remain false")
    if spec["eval_access"] != "locked":
        raise AptaRankTier1Error("eval_access_refused", "ARP-2B keeps EVAL access locked")
    _require(spec["scientific_result"] is False, "spec_invalid", "the analysis spec is not a scientific result")
    _require(spec["full_tier1_statistical_analysis"] is False, "spec_invalid", "ARP-2B does not implement the full Tier 1 analysis")
    if spec["aggregate_tier1_tier2_score"] is not False:
        raise AptaRankTier1Error("combined_score_refused", "ARP-2B defines no combined Tier 1 and Tier 2 score")
    _require(spec["scorer_owner"] == SCORER_OWNER, "spec_invalid", "the scorer owner must remain the deployed AptaRank UI")
    if spec["provisional_camera_ready_formula_adopted"] is not False:
        raise AptaRankTier1Error("provisional_formula_refused", "ARP-2B does not adopt a provisional camera-ready formula")
    plan = spec["governing_plan"]
    _require(isinstance(plan, dict), "spec_invalid", "the governing plan record is missing")
    _require(plan.get("path") == GOVERNING_PLAN_RELATIVE, "spec_invalid", "the governing plan path is not pinned")
    _require(plan.get("version") == "3.2", "spec_invalid", "the governing plan version is not pinned")
    _require(isinstance(plan.get("sha256"), str) and len(plan["sha256"]) == 64, "spec_invalid", "the governing plan hash is missing")
    arp2a = spec["arp2a_reconciliation"]
    _require(isinstance(arp2a, dict), "spec_invalid", "the ARP-2A record is missing")
    _require(arp2a.get("path") == ARP2A_RELATIVE, "spec_invalid", "the ARP-2A path is not pinned")
    _require(isinstance(arp2a.get("sha256"), str) and len(arp2a["sha256"]) == 64, "spec_invalid", "the ARP-2A hash is missing")
    _require(arp2a.get("modified_by_arp2b") is False, "spec_invalid", "ARP-2A must remain unchanged")
    module = spec["analysis_module"]
    _require(isinstance(module, dict), "spec_invalid", "the analysis module record is missing")
    _require(module.get("path") == "scripts/modelling/aptarank_tier1_analysis.py", "spec_invalid", "the analysis module path is not pinned")
    _require(isinstance(module.get("sha256"), str) and len(module["sha256"]) == 64, "spec_invalid", "the analysis module hash is missing")
    dependency = spec["arp1_dependency"]
    _require(isinstance(dependency, dict), "spec_invalid", "the ARP-1 dependency record is missing")
    _require(dependency.get("module_path") == "scripts/modelling/aptarank_io_preflight.py", "spec_invalid", "the ARP-1 module path drifted")
    _require(dependency.get("spec_path") == "config/modelling/aptarank_io_spec.json", "spec_invalid", "the ARP-1 spec path drifted")
    _require(dependency.get("schema_version") == arp1.SCHEMA_VERSION, "spec_invalid", "the ARP-1 schema version drifted")
    _require(dependency.get("modified_by_arp2b") is False, "spec_invalid", "ARP-2B must not modify ARP-1")
    _require(
        isinstance(dependency.get("module_sha256"), str) and len(dependency["module_sha256"]) == 64,
        "spec_invalid",
        "the ARP-1 module hash is missing",
    )
    _require(
        isinstance(dependency.get("spec_sha256"), str) and len(dependency["spec_sha256"]) == 64,
        "spec_invalid",
        "the ARP-1 specification hash is missing",
    )
    constants = spec["production_design_constants"]
    _require(isinstance(constants, dict), "spec_invalid", "production design constants are missing")
    for key, value in PRODUCTION_DESIGN_CONSTANTS.items():
        _require(constants.get(key) == value, "spec_invalid", "a production design constant drifted")
    _require(constants.get("enforce_on_synthetic_fixtures") is False, "spec_invalid", "synthetic fixtures are not production counts")
    _require(constants.get("fixture_count_label") == COUNT_LABEL, "spec_invalid", "fixture counts must be labelled synthetic")
    boundary = spec["scoring_boundary"]
    _require(isinstance(boundary, dict), "spec_invalid", "the scoring boundary is missing")
    _require(boundary.get("scorer_owner") == SCORER_OWNER, "spec_invalid", "the scoring boundary owner drifted")
    _require(boundary.get("provisional_camera_ready_formula_adopted") is False, "provisional_formula_refused", "a provisional formula was adopted")
    for flag in SCORING_BOUNDARY_FLAGS:
        if boundary.get(flag) is not False:
            raise AptaRankTier1Error("recomputation_refused", "local scorer recomputation must stay false")
    interpretation = spec["interpretation_boundary"]
    _require(isinstance(interpretation, dict), "spec_invalid", "the interpretation boundary is missing")
    _require(interpretation.get("binding_interpretation") is False, "spec_invalid", "binding interpretation is not allowed")
    _require(interpretation.get("affinity_interpretation") is False, "spec_invalid", "affinity interpretation is not allowed")
    _require(interpretation.get("selectivity_interpretation") is False, "spec_invalid", "selectivity interpretation is not allowed")
    _require(interpretation.get("uniform_controls_are_synthetic_floor") is True, "spec_invalid", "uniform controls are a synthetic floor")
    _require(interpretation.get("aggregate_tier1_tier2_score") is False, "combined_score_refused", "ARP-2B defines no combined Tier 1 and Tier 2 score")
    private_key = spec["private_key_contract"]
    _require(isinstance(private_key, dict), "spec_invalid", "the private-key contract is missing")
    _require(private_key.get("fields") == list(PRIVATE_KEY_FIELDS), "spec_invalid", "private-key fields drifted")
    _require(private_key.get("class_labels") == list(CLASS_LABELS), "spec_invalid", "class labels drifted")
    _require(private_key.get("join_uses_row_position") is False, "spec_invalid", "row position is not a join key")
    reconciliation = spec["reconciliation_contract"]
    _require(isinstance(reconciliation, dict), "spec_invalid", "the reconciliation contract is missing")
    _require(reconciliation.get("join_key") == JOIN_KEY, "spec_invalid", "the join key drifted")
    _require(reconciliation.get("join_uses_row_position") is False, "spec_invalid", "row position is not a join key")
    _require(reconciliation.get("missing_results_are_zero") is False, "spec_invalid", "missing results are not zeros")
    _require(reconciliation.get("paired_difference_direction") == PAIRED_DIRECTION, "spec_invalid", "the paired direction drifted")
    _require(reconciliation.get("reuses_arp1_mechanical_validation") is True, "spec_invalid", "ARP-1 mechanical validation must be reused")
    report_contract = spec["report_contract"]
    _require(isinstance(report_contract, dict), "spec_invalid", "the report contract is missing")
    _require(report_contract.get("aggregate_report_contains_sequences") is False, "spec_invalid", "the aggregate report must not contain sequences")
    _require(report_contract.get("candidate_level_biological_table") is False, "spec_invalid", "ARP-2B emits no candidate-level biological table")
    _require(
        isinstance(report_contract.get("exact_mean_representation"), str) and report_contract["exact_mean_representation"].strip(),
        "spec_invalid",
        "the exact mean representation is missing",
    )
    _require(
        isinstance(report_contract.get("duplicate_sequence_scope"), str) and "U23" in report_contract["duplicate_sequence_scope"],
        "spec_invalid",
        "the duplicate-sequence scope must keep U23 unresolved",
    )
    _require(spec["implemented"] == list(IMPLEMENTED), "spec_invalid", "the implemented list drifted")
    _require(spec["blocked_outputs"] == [dict(item) for item in BLOCKED_OUTPUTS], "spec_invalid", "the blocked-output list drifted")
    _require(spec["unresolved_ids"] == list(UNRESOLVED_IDS), "spec_invalid", "unresolved ids must remain U1 through U38")
    register = spec["unresolved_register"]
    _require(isinstance(register, list), "spec_invalid", "the unresolved register is missing")
    _require([item.get("id") for item in register] == list(UNRESOLVED_IDS), "spec_invalid", "the unresolved register drifted")
    for item in register:
        _require(item.get("status") == "unresolved", "spec_invalid", "an unresolved decision was closed")
        _require(item.get("value") is None, "spec_invalid", "an unresolved decision was given a value")
        _require(isinstance(item.get("note"), str) and item["note"].strip(), "spec_invalid", "an unresolved decision has no note")
    rules = spec["rules"]
    _require(isinstance(rules, dict) and _keys_match(rules, RULE_KEYS), "spec_invalid", "analysis rules drifted")
    for key in RULE_KEYS:
        _require(isinstance(rules.get(key), str) and rules[key].strip(), "spec_invalid", "an analysis rule is missing")


def _pinned_hash(relative, expected, code, detail):
    actual = arp1.sha256_bytes(arp1.read_bytes(os.path.join(repo_root(), relative)))
    if actual != expected:
        raise AptaRankTier1Error(code, detail)


def _decode_spec_object(spec_bytes):
    if not isinstance(spec_bytes, bytes):
        raise AptaRankTier1Error(
            "spec_bytes_mismatch",
            "specification bytes do not decode to the specification object",
        )
    try:
        decoded = json.loads(spec_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AptaRankTier1Error(
            "spec_bytes_mismatch",
            "specification bytes do not decode to the specification object",
        ) from exc
    if not isinstance(decoded, dict):
        raise AptaRankTier1Error(
            "spec_bytes_mismatch",
            "specification bytes do not decode to the specification object",
        )
    return decoded


def _require_reviewed_spec(spec, spec_bytes):
    """Accept only bytes that decode to this object and match every pinned file.

    The object must already be the reviewed specification. A caller-supplied
    substitute is not accepted by the public analysis path.
    """
    decoded = _decode_spec_object(spec_bytes)
    if decoded != spec:
        raise AptaRankTier1Error(
            "spec_bytes_mismatch",
            "specification bytes do not decode to the specification object",
        )
    on_disk = arp1.read_bytes(spec_path())
    if spec_bytes != on_disk:
        raise AptaRankTier1Error(
            "spec_bytes_mismatch",
            "specification bytes do not match the on-disk reviewed specification",
        )
    validate_spec_document(spec)
    _pinned_hash(
        GOVERNING_PLAN_RELATIVE,
        spec["governing_plan"]["sha256"],
        "governing_plan_hash_mismatch",
        "the governing plan hash does not match the analysis spec",
    )
    _pinned_hash(
        ARP2A_RELATIVE,
        spec["arp2a_reconciliation"]["sha256"],
        "arp2a_hash_mismatch",
        "the ARP-2A hash does not match the analysis spec",
    )
    module_hash = arp1.sha256_bytes(arp1.read_bytes(os.path.abspath(__file__)))
    if module_hash != spec["analysis_module"]["sha256"]:
        raise AptaRankTier1Error("analysis_module_hash_mismatch", "the analysis module hash does not match the spec")
    dependency = spec["arp1_dependency"]
    _pinned_hash(
        dependency["module_path"],
        dependency["module_sha256"],
        "arp1_module_hash_mismatch",
        "the ARP-1 module hash does not match the analysis spec",
    )
    _pinned_hash(
        dependency["spec_path"],
        dependency["spec_sha256"],
        "arp1_spec_hash_mismatch",
        "the ARP-1 specification hash does not match the analysis spec",
    )
    return spec


def load_spec():
    """Load the on-disk specification and every pinned dependency."""
    spec_bytes = arp1.read_bytes(spec_path())
    try:
        spec = json.loads(spec_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AptaRankTier1Error("spec_invalid", "the analysis spec is not readable JSON") from exc
    if not isinstance(spec, dict):
        raise AptaRankTier1Error("spec_invalid", "the analysis spec is not readable JSON")
    _require_reviewed_spec(spec, spec_bytes)
    return spec, spec_bytes


def load_fixture_bytes(name):
    if not isinstance(name, str) or os.path.basename(name) != name or name not in ALLOWED_FIXTURE_NAMES:
        raise AptaRankTier1Error("fixture_name_refused", "ARP-2B loads only bundled synthetic fixture names")
    path = os.path.join(fixture_root(), name)
    root = os.path.realpath(fixture_root())
    resolved = os.path.realpath(path)
    if os.path.dirname(resolved) != root:
        raise AptaRankTier1Error("fixture_name_refused", "ARP-2B loads only bundled synthetic fixture names")
    return arp1.read_bytes(resolved)


def load_bundled_parts(mapping=None):
    selected = BUNDLED_FIXTURES if mapping is None else mapping
    return {role: load_fixture_bytes(name) for role, name in selected.items()}


def refuse_local_recomputation(request):
    """Refuse component, composite, calibration, and shuffle recomputation."""
    label = request if isinstance(request, str) and request.strip() else "unspecified"
    if not isinstance(request, str) or request not in RECOMPUTATION_REQUESTS:
        raise AptaRankTier1Error(
            "recomputation_refused",
            "local recomputation of %s is blocked by U1 through U21" % label,
        )
    raise AptaRankTier1Error(
        "recomputation_refused",
        "local recomputation of %s is blocked by U1 through U21" % request,
    )


def refuse_blocked_operation(operation):
    """Refuse control generation, production ids, and a full-ranking schema."""
    if operation == "generate_uniform_controls":
        raise AptaRankTier1Error(
            "control_generation_refused",
            "uniform-control generation is blocked by U22, U23, and U24",
        )
    if operation == "create_opaque_production_ids":
        raise AptaRankTier1Error(
            "opaque_production_id_refused",
            "opaque production-id creation is blocked by U25 and U26",
        )
    if operation == "full_ranking_schema":
        raise AptaRankTier1Error(
            "full_ranking_schema_refused",
            "a full-ranking schema is blocked by U27, U28, and U29",
        )
    raise AptaRankTier1Error("blocked_operation_refused", "the requested operation is not implemented")


def _reject_path_input(value, role):
    if isinstance(value, str):
        raise AptaRankTier1Error(
            "path_refused",
            "%s must be supplied as bytes or an object, not a path or role name" % role,
        )


def _parse_object(value, role):
    _reject_path_input(value, role)
    if isinstance(value, dict):
        return value
    if isinstance(value, bytes):
        try:
            document = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AptaRankTier1Error("malformed_json", role + " is not a JSON object") from exc
        if not isinstance(document, dict):
            raise AptaRankTier1Error("malformed_json", role + " is not a JSON object")
        return document
    raise AptaRankTier1Error("input_type_refused", role + " must be bytes or an object")


def _identifier_ok(value):
    return isinstance(value, str) and arp1.ID_TEXT.fullmatch(value) is not None


def _positive_json_integer(value):
    return type(value) is int and value > 0


def _validate_private_key_types(document, errors):
    """Check private-key types without set, sort, or id lookup.

    Invalid identifiers are rejected here. Pair grouping starts only after
    every identifier and length has a valid type.
    """
    if not isinstance(document, dict) or not _keys_match(document, PRIVATE_KEY_DOCUMENT_FIELDS):
        errors.add("invalid_private_key_document", "the private key does not match the synthetic document schema")
        return None
    if document.get("fixture_role") != PRIVATE_KEY_ROLE:
        errors.add("invalid_private_key_document", "the private key fixture role is not synthetic")
        return None
    if document.get("count_label") != COUNT_LABEL:
        errors.add("invalid_count_label", "private-key counts must be labelled synthetic")
        return None
    candidates = document.get("candidates")
    if not isinstance(candidates, list):
        errors.add("invalid_private_key_document", "private-key candidates are not a list")
        return None
    typed = []
    valid = True
    for index, row in enumerate(candidates, start=1):
        if not isinstance(row, dict) or not _keys_match(row, PRIVATE_KEY_FIELDS):
            errors.add("invalid_private_key_record", "private-key record %d does not match the field schema" % index)
            valid = False
            continue
        row_ok = True
        for field in IDENTIFIER_FIELDS:
            if not _identifier_ok(row[field]):
                errors.add(
                    "invalid_private_key_identifier",
                    "private-key %s at record %d is not a nonempty opaque id" % (field, index),
                )
                row_ok = False
        class_label = row["class_label"]
        if not isinstance(class_label, str) or class_label not in CLASS_LABELS:
            errors.add(
                "invalid_private_key_class_label",
                "private-key class_label at record %d is not real or uniform_control" % index,
            )
            row_ok = False
        if not _positive_json_integer(row["length"]):
            errors.add(
                "invalid_private_key_length",
                "private-key length at record %d is not a positive JSON integer" % index,
            )
            row_ok = False
        if row_ok:
            typed.append(
                {
                    "candidate_id": row["candidate_id"],
                    "class_label": row["class_label"],
                    "pair_id": row["pair_id"],
                    "parent_core_id": row["parent_core_id"],
                    "cluster_id": row["cluster_id"],
                    "length": row["length"],
                }
            )
        else:
            valid = False
    if not valid:
        return None
    return typed


def _validate_private_key_pairs(typed, errors):
    seen = set()
    duplicates = False
    for row in typed:
        candidate_id = row["candidate_id"]
        if candidate_id in seen:
            errors.add("duplicate_private_key_candidate_id", "private-key candidate id %s is duplicated" % candidate_id)
            duplicates = True
        seen.add(candidate_id)
    if duplicates:
        return
    groups = {}
    order = []
    for row in typed:
        pair_id = row["pair_id"]
        if pair_id not in groups:
            groups[pair_id] = []
            order.append(pair_id)
        groups[pair_id].append(row)
    for pair_id in order:
        members = groups[pair_id]
        if len(members) != 2:
            errors.add(
                "pair_cardinality",
                "pair %s does not contain exactly two expected candidates" % pair_id,
            )
            continue
        labels = [member["class_label"] for member in members]
        if labels.count("real") != 1 or labels.count("uniform_control") != 1:
            errors.add(
                "pair_class_composition",
                "pair %s does not contain exactly one real and one uniform_control" % pair_id,
            )
        for field in PAIR_AGREEMENT_FIELDS:
            if members[0][field] != members[1][field]:
                errors.add(
                    "pair_field_inconsistency",
                    "pair %s members do not share the same %s" % (pair_id, field),
                )
    _reject_parent_core_across_pairs(typed, errors)


def _reject_parent_core_across_pairs(typed, errors):
    """Require one pair id for each parent core after identifier types are valid."""
    parent_to_pair = {}
    reported = set()
    for row in typed:
        parent_id = row["parent_core_id"]
        pair_id = row["pair_id"]
        previous = parent_to_pair.get(parent_id)
        if previous is None:
            parent_to_pair[parent_id] = pair_id
        elif previous != pair_id and parent_id not in reported:
            errors.add(
                "duplicate_parent_core_across_pairs",
                "parent core %s is assigned to more than one pair" % parent_id,
            )
            reported.add(parent_id)


def validate_private_key(document):
    """Validate a synthetic private key.

    Type checks finish before any set, sort, or candidate-id lookup. Pair
    grouping runs only after every identifier and length is valid.
    """
    errors = arp1.ErrorList()
    typed = _validate_private_key_types(document, errors)
    if typed is None:
        _raise_from(errors)
        return None
    _validate_private_key_pairs(typed, errors)
    _raise_from(errors)
    return typed


def _fraction_from_score_token(token):
    if not isinstance(token, str):
        raise AptaRankTier1Error("nonfinite_aptamer_likeness", "exported aptamer-likeness is not a finite decimal")
    try:
        value = Decimal(token)
    except Exception as exc:
        raise AptaRankTier1Error("nonfinite_aptamer_likeness", "exported aptamer-likeness is not a finite decimal") from exc
    if not value.is_finite():
        raise AptaRankTier1Error("nonfinite_aptamer_likeness", "exported aptamer-likeness is not a finite decimal")
    return Fraction(value)


def _minimum_decimal_places(tokens):
    places = 0
    for token in tokens:
        exponent = Decimal(token).as_tuple().exponent
        if not isinstance(exponent, int):
            raise AptaRankTier1Error("nonfinite_aptamer_likeness", "exported aptamer-likeness is not a finite decimal")
        if exponent < 0:
            places = max(places, -exponent)
    return places


def _decimal_places_required(fraction):
    denominator = fraction.denominator
    twos = 0
    fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return None
    return max(twos, fives)


def _format_scaled(fraction, places):
    scaled = fraction * (10 ** places)
    if scaled.denominator != 1:
        return None
    negative = scaled.numerator < 0
    digits = str(abs(scaled.numerator)).zfill(places + 1)
    if places == 0:
        text = digits
    else:
        text = digits[:-places] + "." + digits[-places:]
    if negative:
        return "-" + text
    return text


def _render_exact_decimal(fraction, minimum_places):
    required = _decimal_places_required(fraction)
    if required is None:
        return None
    return _format_scaled(fraction, max(minimum_places, required))


def _labeled_decimal_approximation(mean):
    context = Context(prec=MEAN_APPROXIMATION_PRECISION, rounding=ROUND_HALF_EVEN)
    with localcontext(context):
        rendered = Decimal(mean.numerator) / Decimal(mean.denominator)
        text = format(rendered, "f")
    return {
        "text": text,
        "precision": MEAN_APPROXIMATION_PRECISION,
        "rounding": MEAN_APPROXIMATION_ROUNDING,
        "exact": False,
    }


def _arithmetic_mean(tokens):
    """Return an exact rational mean, or an undefined empty-group record.

    Each preserved token becomes a Fraction from its Decimal value. The sum
    uses rational addition, so a nonterminating decimal expansion stays defined
    and the active Decimal context cannot shorten the numerator.
    """
    preserved = list(tokens)
    if not preserved:
        return {
            "value": None,
            "numerator": None,
            "denominator": 0,
            "exact_numerator": None,
            "exact_denominator": None,
            "undefined": True,
            "reason": UNDEFINED_MEAN_REASON,
            "score_tokens": [],
            "decimal_approximation": None,
        }
    parts = [_fraction_from_score_token(token) for token in preserved]
    total = sum(parts, Fraction(0, 1))
    count = len(preserved)
    mean = total / count
    places = _minimum_decimal_places(preserved)
    numerator_text = _render_exact_decimal(total, places)
    if numerator_text is None:
        raise AptaRankTier1Error("internal_error", "the exact score sum did not terminate")
    value = _render_exact_decimal(mean, places)
    return {
        "value": value,
        "numerator": numerator_text,
        "denominator": count,
        "exact_numerator": str(mean.numerator),
        "exact_denominator": str(mean.denominator),
        "undefined": False,
        "reason": None,
        "score_tokens": preserved,
        "decimal_approximation": None if value is not None else _labeled_decimal_approximation(mean),
    }


def _cluster_count(rows):
    clusters = []
    for row in rows:
        if row["cluster_id"] not in clusters:
            clusters.append(row["cluster_id"])
    return len(clusters)


def _class_counts(rows, predicate):
    counts = {label: 0 for label in CLASS_LABELS}
    for row in rows:
        if predicate(row):
            counts[row["class_label"]] += 1
    return counts


def _failure_reasons(failure_document):
    reasons = {}
    for item in failure_document["failures"]:
        if isinstance(item, dict) and isinstance(item.get("candidate_id"), str):
            reasons[item["candidate_id"]] = item.get("reason")
    return reasons


def _check_private_key_lengths(key_rows, candidates, exports, parsed_lengths, errors):
    upload_lengths = {}
    for row in candidates:
        upload_lengths[row["id"]] = len(row["sequence"])
    export_lengths = {}
    for row, parsed in zip(exports, parsed_lengths):
        export_lengths[row["candidate"]] = parsed
    for row in key_rows:
        candidate_id = row["candidate_id"]
        if upload_lengths.get(candidate_id) != row["length"]:
            errors.add(
                "length_mismatch",
                "candidate %s private-key length does not match the uploaded sequence length" % candidate_id,
            )
        if candidate_id in export_lengths and export_lengths[candidate_id] != row["length"]:
            errors.add(
                "length_mismatch",
                "candidate %s private-key length does not match the exported len" % candidate_id,
            )


def _reject_duplicate_upload_sequences(candidates, errors):
    """Reject one canonical sequence under more than one uploaded candidate id.

    ARP-1 has already parsed the upload and checked the A/C/G/U alphabet.
    Comparison uses those exact strings. This looks only inside the supplied
    candidate upload. It does not consult a known-core inventory and does not
    close U23.
    """
    if not candidates:
        return
    groups = {}
    order = []
    for row in candidates:
        sequence = row.get("sequence")
        candidate_id = row.get("id")
        if not isinstance(sequence, str) or arp1.SEQUENCE_TEXT.fullmatch(sequence) is None:
            continue
        if not isinstance(candidate_id, str) or arp1.ID_TEXT.fullmatch(candidate_id) is None:
            continue
        if sequence not in groups:
            groups[sequence] = []
            order.append(sequence)
        if candidate_id not in groups[sequence]:
            groups[sequence].append(candidate_id)
    for sequence in order:
        candidate_ids = groups[sequence]
        if len(candidate_ids) < 2:
            continue
        errors.add(
            "duplicate_candidate_sequence",
            "candidates %s repeat one sequence inside the supplied candidate upload" % ", ".join(candidate_ids),
        )


def _score_tokens(exports, errors):
    tokens = {}
    for row in exports:
        token = row["aptamer-likeness"]
        if arp1.classify_likeness(token) != "finite":
            errors.add("nonfinite_aptamer_likeness", "exported aptamer-likeness is not a finite decimal")
            continue
        tokens[row["candidate"]] = token
    return tokens


def _pair_members(key_rows):
    groups = {}
    order = []
    for row in key_rows:
        if row["pair_id"] not in groups:
            groups[row["pair_id"]] = {}
            order.append(row["pair_id"])
        groups[row["pair_id"]][row["class_label"]] = row
    return order, groups


def _incomplete_reason(pair_id, real_row, control_row, real_state, control_state, surviving):
    failed = []
    if real_state != "exported":
        failed.append("real candidate %s" % real_row["candidate_id"])
    if control_state != "exported":
        failed.append("uniform_control candidate %s" % control_row["candidate_id"])
    survival = (
        "a surviving exported member remains in its unpaired group count and mean"
        if surviving
        else "neither member contributes a numeric score"
    )
    return (
        "pair %s is incomplete because %s %s an explicit technical failure and no numeric score; "
        "%s; this pair is excluded from paired differences"
        % (
            pair_id,
            " and ".join(failed),
            "have" if len(failed) > 1 else "has",
            survival,
        )
    )


def _blocked_section():
    return {item["output"]: item for item in _blocked_copy()}


def _build_report(spec, key_rows, failure_document, dispositions, score_tokens):
    disposition_by_id = {}
    for item in dispositions:
        disposition_by_id[item["candidate_id"]] = item["disposition"]
    reasons = _failure_reasons(failure_document)
    order, groups = _pair_members(key_rows)
    diagnostics = []
    evaluable_tokens = {label: [] for label in CLASS_LABELS}
    complete_pairs = []
    incomplete_pairs = []
    directions = []
    for pair_id in order:
        members = groups[pair_id]
        real_row = members["real"]
        control_row = members["uniform_control"]
        states = {}
        for label, row in (("real", real_row), ("uniform_control", control_row)):
            state = disposition_by_id[row["candidate_id"]]
            states[label] = state
            exported = state == "exported"
            token = score_tokens.get(row["candidate_id"]) if exported else None
            if exported:
                evaluable_tokens[label].append(token)
            diagnostics.append(
                {
                    "candidate_id": row["candidate_id"],
                    "class_label": label,
                    "pair_id": pair_id,
                    "disposition": state,
                    "score_token": token,
                    "evaluable": exported,
                    "numeric_zero_retained": bool(exported and Decimal(token) == 0),
                    "missing_result_stored_as_zero": False,
                    "failure_reason": None if exported else reasons.get(row["candidate_id"]),
                }
            )
        if states["real"] == "exported" and states["uniform_control"] == "exported":
            delta = Decimal(score_tokens[real_row["candidate_id"]]) - Decimal(
                score_tokens[control_row["candidate_id"]]
            )
            if not isinstance(delta, Decimal):
                raise AptaRankTier1Error("internal_error", "the paired difference was not constructed")
            complete_pairs.append(pair_id)
            directions.append({"pair_id": pair_id, "direction": PAIRED_DIRECTION})
        else:
            surviving = states["real"] == "exported" or states["uniform_control"] == "exported"
            incomplete_pairs.append(
                {
                    "pair_id": pair_id,
                    "reason": _incomplete_reason(
                        pair_id,
                        real_row,
                        control_row,
                        states["real"],
                        states["uniform_control"],
                        surviving,
                    ),
                    "real_candidate_id": real_row["candidate_id"],
                    "uniform_control_candidate_id": control_row["candidate_id"],
                    "real_disposition": states["real"],
                    "uniform_control_disposition": states["uniform_control"],
                    "excluded_from_paired_differences": True,
                    "surviving_member_remains_in_group_mean": surviving,
                }
            )
    means = {label: _arithmetic_mean(evaluable_tokens[label]) for label in CLASS_LABELS}
    blocked = _blocked_section()
    input_counts = _class_counts(key_rows, lambda row: True)
    evaluable_counts = _class_counts(
        key_rows,
        lambda row: disposition_by_id[row["candidate_id"]] == "exported",
    )
    failure_counts = _class_counts(
        key_rows,
        lambda row: disposition_by_id[row["candidate_id"]] == "technical_failure",
    )
    return {
        "package_id": PACKAGE_ID,
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "spec_status": spec["status"],
        "scorer_owner": SCORER_OWNER,
        "scientific_result": False,
        "full_tier1_statistical_analysis": False,
        "technical_versus_scientific": TECHNICAL_NOT_SCIENTIFIC,
        "fixture_count_label": COUNT_LABEL,
        "deployment_verified": False,
        "eval_access": "locked",
        "join_key": JOIN_KEY,
        "join_uses_row_position": False,
        "missing_results_are_zero": False,
        "uniform_controls_are_synthetic_floor": True,
        "aggregate_tier1_tier2_score": False,
        "binding_interpretation": False,
        "affinity_interpretation": False,
        "selectivity_interpretation": False,
        "provisional_camera_ready_formula_adopted": False,
        "input_candidate_count": len(key_rows),
        "input_pair_count": len(order),
        "cluster_count_before_technical_rejection": _cluster_count(key_rows),
        "input_counts_by_class": input_counts,
        "evaluable_counts_by_class": evaluable_counts,
        "technical_failure_counts_by_class": failure_counts,
        "complete_pair_count": len(complete_pairs),
        "incomplete_pair_count": len(incomplete_pairs),
        "incomplete_pairs": incomplete_pairs,
        "paired_difference_count": len(directions),
        "paired_difference_directions": directions,
        "paired_difference_method_status": "eligible_count_only_functional_blocked",
        "arithmetic_means": means,
        "rows_imputed_as_zero": 0,
        "production_design_constants": {
            "values": dict(PRODUCTION_DESIGN_CONSTANTS),
            "applied_to_this_report": False,
            "reason": "Synthetic fixture counts are labelled synthetic and are not checked against production design constants.",
        },
        "synthetic_candidate_diagnostics": diagnostics,
        "candidate_level_biological_table": False,
        "blocked_outputs": blocked,
        "implemented": list(IMPLEMENTED),
        "local_recomputations": {name: False for name in SCORING_BOUNDARY_FLAGS},
        "data_access": {
            "eval_loaded": False,
            "ref_loaded": False,
            "validation_loaded": False,
            "train_loaded": False,
            "production_pools_loaded": False,
            "checkpoints_loaded": False,
            "statement": SYNTHETIC_ONLY_STATEMENT,
        },
        "errors": [],
    }


def _collect_sequences(candidates, exports):
    found = []
    for rows in (candidates, exports):
        if not rows:
            continue
        for row in rows:
            sequence = row.get("sequence")
            if isinstance(sequence, str) and sequence:
                found.append(sequence)
    return found


def _analyze_tier1(
    spec,
    spec_bytes,
    private_key,
    candidate_upload,
    shortlist_export,
    failure_accounting,
    revision=None,
):
    """Join inputs using a specification object already proved against its bytes."""
    spec = _require_reviewed_spec(spec, spec_bytes)
    _reject_path_input(candidate_upload, "candidate_upload")
    _reject_path_input(shortlist_export, "shortlist_export")
    if not isinstance(candidate_upload, bytes) or not isinstance(shortlist_export, bytes):
        raise AptaRankTier1Error("input_type_refused", "upload and export inputs must be bytes")
    key_document = _parse_object(private_key, "private_key")
    failure_document = _parse_object(failure_accounting, "failure_accounting")
    key_rows = validate_private_key(key_document)
    errors = arp1.ErrorList()
    manifest = {
        "fixture_role": "synthetic_expected_cell_manifest",
        "profile_id": arp1.PROFILE_ID,
        "expected_candidate_ids": [row["candidate_id"] for row in key_rows],
        "expected_export_fields": list(arp1.SHORTLIST_COLUMNS),
    }
    checked_manifest = arp1._check_manifest(manifest, errors)
    checked_failures = arp1._check_failures(failure_document, errors)
    if checked_failures is not None and failure_document.get("profile_id") != arp1.PROFILE_ID:
        errors.add("profile_not_selected", "the synthetic failure profile must be the ARP-1 target-free profile")
        checked_failures = None
    candidates = arp1.parse_csv_rows(
        candidate_upload,
        arp1.CANDIDATE_COLUMNS,
        errors,
        "candidate upload",
    )
    exports = arp1.parse_csv_rows(
        shortlist_export,
        arp1.SHORTLIST_COLUMNS,
        errors,
        "shortlist export",
    )
    arp1._check_candidate_rows(candidates, errors)
    _reject_duplicate_upload_sequences(candidates, errors)
    profile = arp1.load_spec()[0]["synthetic_run_profiles"][arp1.PROFILE_ID]
    parsed_lengths = arp1._check_shortlist_rows(exports, errors, profile)
    summary = None
    if None not in (candidates, exports, checked_failures, checked_manifest) and not errors.items:
        summary = arp1._reconcile(
            candidates,
            exports,
            checked_failures,
            checked_manifest,
            parsed_lengths,
            errors,
        )
        if not errors.items:
            _check_private_key_lengths(key_rows, candidates, exports, parsed_lengths, errors)
    _raise_from(errors)
    score_tokens = _score_tokens(exports, errors)
    _raise_from(errors)
    report = _build_report(spec, key_rows, checked_failures, summary["dispositions"], score_tokens)
    if revision is not None:
        report["package_revision"] = revision
    arp1.ensure_sequence_free(report, _collect_sequences(candidates, exports))
    return report


def analyze_tier1(
    private_key,
    candidate_upload,
    shortlist_export,
    failure_accounting,
    *,
    recompute=None,
    revision=None,
    **rejected,
):
    """Join a synthetic download to a synthetic private key by candidate id.

    The on-disk reviewed specification is loaded and pinned on every call.
    Caller-supplied specification objects and bytes are refused. Inputs are
    objects or original bytes. Paths and role names are refused.
    """
    if rejected:
        raise AptaRankTier1Error(
            "spec_injection_refused",
            "the public analysis path accepts only the on-disk reviewed specification",
        )
    if recompute is not None:
        refuse_local_recomputation(recompute)
    spec, spec_bytes = load_spec()
    return _analyze_tier1(
        spec,
        spec_bytes,
        private_key,
        candidate_upload,
        shortlist_export,
        failure_accounting,
        revision=revision,
    )


def _git_text(args):
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def demonstration_revision(spec, spec_bytes):
    return {
        "git_head": _git_text(["rev-parse", "HEAD"]),
        "git_branch": _git_text(["rev-parse", "--abbrev-ref", "HEAD"]),
        "analysis_module_sha256": arp1.sha256_bytes(arp1.read_bytes(os.path.abspath(__file__))),
        "analysis_spec_sha256": arp1.sha256_bytes(spec_bytes),
        "governing_plan_sha256": spec["governing_plan"]["sha256"],
        "arp2a_sha256": spec["arp2a_reconciliation"]["sha256"],
        "arp1_module_sha256": spec["arp1_dependency"]["module_sha256"],
        "arp1_spec_sha256": spec["arp1_dependency"]["spec_sha256"],
    }


def run_demonstration():
    spec, spec_bytes = load_spec()
    parts = load_bundled_parts()
    revision = demonstration_revision(spec, spec_bytes)
    return analyze_tier1(
        parts["private_key"],
        parts["candidate_upload"],
        parts["shortlist_export"],
        parts["failure_accounting"],
        revision=revision,
    )


def render_report(report):
    lines = [
        "ARP-2B synthetic Tier 1 joining and accounting",
        SYNTHETIC_ONLY_STATEMENT,
        "package_id: " + report["package_id"],
        "schema_version: " + report["schema_version"],
        "spec_status: " + report["spec_status"],
        "scorer_owner: " + report["scorer_owner"],
        "deployment_verified: " + json.dumps(report["deployment_verified"]),
        "eval_access: " + report["eval_access"],
        "fixture_count_label: " + report["fixture_count_label"],
        "scientific_result: " + json.dumps(report["scientific_result"]),
        "full_tier1_statistical_analysis: " + json.dumps(report["full_tier1_statistical_analysis"]),
        report["technical_versus_scientific"],
        "join_key: " + report["join_key"],
        "join_uses_row_position: " + json.dumps(report["join_uses_row_position"]),
        "missing_results_are_zero: " + json.dumps(report["missing_results_are_zero"]),
        "uniform_controls_are_synthetic_floor: " + json.dumps(report["uniform_controls_are_synthetic_floor"]),
        "aggregate_tier1_tier2_score: " + json.dumps(report["aggregate_tier1_tier2_score"]),
        "binding_interpretation: " + json.dumps(report["binding_interpretation"]),
        "affinity_interpretation: " + json.dumps(report["affinity_interpretation"]),
        "selectivity_interpretation: " + json.dumps(report["selectivity_interpretation"]),
        "input_candidate_count: %d" % report["input_candidate_count"],
        "input_pair_count: %d" % report["input_pair_count"],
        "cluster_count_before_technical_rejection: %d" % report["cluster_count_before_technical_rejection"],
        "complete_pair_count: %d" % report["complete_pair_count"],
        "incomplete_pair_count: %d" % report["incomplete_pair_count"],
        "paired_difference_count: %d" % report["paired_difference_count"],
        "paired_difference_method_status: " + report["paired_difference_method_status"],
        "rows_imputed_as_zero: %d" % report["rows_imputed_as_zero"],
        "candidate_level_biological_table: " + json.dumps(report["candidate_level_biological_table"]),
    ]
    for label in CLASS_LABELS:
        lines.append("input_count_%s: %d" % (label, report["input_counts_by_class"][label]))
        lines.append("evaluable_count_%s: %d" % (label, report["evaluable_counts_by_class"][label]))
        lines.append("technical_failure_count_%s: %d" % (label, report["technical_failure_counts_by_class"][label]))
        mean = report["arithmetic_means"][label]
        if mean["undefined"]:
            exact = "undefined"
        else:
            exact = "%s/%s" % (mean["exact_numerator"], mean["exact_denominator"])
        lines.append(
            "arithmetic_mean_%s: %s denominator %d exact %s"
            % (label, json.dumps(mean["value"]), mean["denominator"], exact)
        )
        if mean["reason"] is not None:
            lines.append("arithmetic_mean_%s_reason: %s" % (label, mean["reason"]))
    lines.append("paired_difference_directions:")
    for item in report["paired_difference_directions"]:
        lines.append("  %s: %s" % (item["pair_id"], item["direction"]))
    lines.append("incomplete_pairs:")
    for item in report["incomplete_pairs"]:
        lines.append("  %s: %s" % (item["pair_id"], item["reason"]))
    lines.append("synthetic_candidate_diagnostics:")
    for item in report["synthetic_candidate_diagnostics"]:
        lines.append(
            "  %s: %s score %s"
            % (item["candidate_id"], item["disposition"], json.dumps(item["score_token"]))
        )
    lines.append("blocked_outputs:")
    for name, item in report["blocked_outputs"].items():
        lines.append("  %s: null %s" % (name, ",".join(item["blocking_ids"])))
    lines.append(report["data_access"]["statement"])
    lines.append("production_design_constants_applied: " + json.dumps(report["production_design_constants"]["applied_to_this_report"]))
    if "package_revision" in report:
        revision = report["package_revision"]
        lines.append("git_head: " + revision["git_head"])
        lines.append("git_branch: " + revision["git_branch"])
        lines.append("analysis_module_sha256: " + revision["analysis_module_sha256"])
        lines.append("analysis_spec_sha256: " + revision["analysis_spec_sha256"])
        lines.append("governing_plan_sha256: " + revision["governing_plan_sha256"])
        lines.append("arp2a_sha256: " + revision["arp2a_sha256"])
        lines.append("arp1_module_sha256: " + revision["arp1_module_sha256"])
        lines.append("arp1_spec_sha256: " + revision["arp1_spec_sha256"])
    lines.append("errors: %d" % len(report["errors"]))
    return "\n".join(lines) + "\n"


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        sys.stderr.write(
            "arp2b_cli_rejected: ARP-2B does not accept paths, protected role names, "
            "an EVAL unlock, or any other argument\n"
        )
        return 2
    report = run_demonstration()
    sys.stdout.write(render_report(report))
    return 0 if report["status"] == "passed" and report["eval_access"] == "locked" else 1


if __name__ == "__main__":
    raise SystemExit(main())

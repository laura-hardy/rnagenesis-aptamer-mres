#!/usr/bin/env python3
"""GEP-1 synthetic generator-evaluation contract and preflight.

This pathway is fail-closed. The default mode is synthetic preflight.
It does not load EVAL, REF, VALIDATION, or TRAIN, and it does not open
pools, checkpoints, or model outputs. It does not change metric
definitions. Metric arithmetic that is checked here calls the existing
M4 ledger functions on caller-supplied synthetic rows only.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys

PACKAGE_ID = "GEP-1"
SCHEMA_VERSION = "generator-eval-preflight-gep1-r3"
GOVERNING_PLAN_VERSION = "3.4"
GOVERNING_PLAN_REVISION_DATE = "17 October 2026"
HISTORICAL_M9C_PLAN_VERSION = "3.3"
HISTORICAL_M9C_PLAN_REVISION_DATE = "12 October 2026"
SYNTHETIC_RAW_CONTRACT = "synthetic-m8-raw-attempt-bundle-v1"
SYNTHETIC_PARSER_ADAPTER_VERSION = "synthetic-m8-parser-adapter-v2"
SOURCE_MANIFEST_SCHEMA = "synthetic-m8-source-manifest-v2"
DERIVED_PROVENANCE_SCHEMA = "synthetic-m8-derived-provenance-v1"
REPLENISHMENT_PROHIBITED_STATEMENT = (
    "Replenishment is prohibited. Invalid or duplicate attempts are not filtered, "
    "deduplicated, truncated, padded, topped up, replaced, or replenished."
)
# Known before parsing. derived_ledger_sha256 is not an input.
SOURCE_MANIFEST_REQUIRED = (
    "source_artifact_id",
    "source_artifact_sha256",
    "source_byte_size",
    "parser_adapter_version",
    "replenishment_prohibited",
)
SOURCE_MANIFEST_OPTIONAL = (
    "expected_attempt_count",
    "expected_derived_ledger_sha256",
)
DERIVED_PROVENANCE_FIELDS = (
    "source_artifact_id",
    "source_artifact_sha256",
    "parser_adapter_version",
    "derived_row_count",
    "derived_ledger_sha256",
    "replenishment_prohibited",
)
PARSE_OUTCOME_VALID = "valid_canonical_sequence"
PARSE_OUTCOME_EMPTY = "empty_output"
PARSE_OUTCOME_UNPARSEABLE = "unparseable_output"
PARSE_OUTCOME_NON_SEQUENCE = "non_sequence_output"
PARSE_OUTCOME_NON_ACGU = "parsed_non_acgu"
PARSE_OUTCOMES = (
    PARSE_OUTCOME_VALID,
    PARSE_OUTCOME_EMPTY,
    PARSE_OUTCOME_UNPARSEABLE,
    PARSE_OUTCOME_NON_SEQUENCE,
    PARSE_OUTCOME_NON_ACGU,
)
FAILURE_REASONS = (
    PARSE_OUTCOME_EMPTY,
    PARSE_OUTCOME_UNPARSEABLE,
    PARSE_OUTCOME_NON_SEQUENCE,
    PARSE_OUTCOME_NON_ACGU,
)
SEQUENCE_NULL_PARSE_OUTCOMES = (
    PARSE_OUTCOME_EMPTY,
    PARSE_OUTCOME_UNPARSEABLE,
    PARSE_OUTCOME_NON_SEQUENCE,
)
POOLING_POLICY_EQUAL = "equal_training_seed_mixture"
POOLING_POLICY_UNVERIFIED = "unverified"
D1_POOLING_KEYS = (
    "pooling_policy",
    "policy_verified",
    "participating_training_seeds",
)
SYNTHETIC_B0_SOURCE_KEYS = (
    "record_id",
    "historical_text",
    "historical_generation_seed",
    "historical_batch_index",
    "nominal_max_seq_len",
    "checkpoint_id",
)
SYNTHETIC_B2_SOURCE_KEYS = (
    "record_id",
    "raw_text",
    "empirical_null_seed",
    "requested_length",
)
SYNTHETIC_B1_SOURCE_KEYS = (
    "record_id",
    "raw_text",
    "checkpoint_id",
    "checkpoint_sha256",
    "generation_seed",
    "length_sampling_seed",
    "length_condition_seed",
    "generation_chunk_id",
    "requested_length",
    "original_attempt_index",
    "invocation_index",
    "batch_position",
    "requested_target_length",
    "max_seq_len",
    "invocation_seed",
    "length_schedule_provenance",
)
SYNTHETIC_D1_SOURCE_KEYS = (
    "record_id",
    "raw_text",
    "checkpoint_id",
    "checkpoint_sha256",
    "training_seed",
    "generation_seed",
    "length_sampling_seed",
    "generation_chunk_id",
    "requested_length",
    "original_attempt_index",
    "invocation_index",
    "batch_position",
    "requested_target_length",
    "max_seq_len",
    "invocation_seed",
    "length_schedule_provenance",
)
SYNTHETIC_SOURCE_KEYS = {
    "B0": SYNTHETIC_B0_SOURCE_KEYS,
    "B1": SYNTHETIC_B1_SOURCE_KEYS,
    "B2": SYNTHETIC_B2_SOURCE_KEYS,
    "D1": SYNTHETIC_D1_SOURCE_KEYS,
}
DEFAULT_MODE = "synthetic_preflight"
FROZEN_UNLOCKED_MODE = "frozen_unlocked"
SYNTHETIC_ROLE = "SYNTHETIC"
EVAL_ROLE = "EVAL"
REFUSED_ROLES = ("REF", "VALIDATION", "TRAIN")
CANONICAL_SEQUENCE = re.compile(r"^[ACGU]+$")
SHA256_TEXT = re.compile(r"^[0-9a-f]{64}$")
RECORD_ID_TEXT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,80}$")
CHUNK_ID_TEXT = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,80}$")
SYNTHETIC_CHUNK_NAMESPACE = "synthetic_stand_in_for_m4_m6_invocation_index"
FIXTURE_RELATIVE = "tests/modelling/fixtures/generator_eval_gep1"
SPEC_RELATIVE = "config/modelling/generator_eval_metric_spec.json"
DEFAULT_FIXTURE_NAME = "synthetic_four_condition_two_d1_seeds.json"
MAX_FIXTURE_BYTES = 65536
NO_EVAL_STATEMENT = "No EVAL data were loaded."
NO_REF_VALIDATION_STATEMENT = "No REF or VALIDATION data were loaded."
ONE_D1_SEED_STATEMENT = "Uncertainty excludes training-run variability."
B0_NOMINAL_MAX_SEQ_LEN = 37
B0_EXACT_HIT_NOT_APPLICABLE = (
    "Historical B0 evidence records nominal max_seq_len 37 and cleaned output length 36. "
    "It does not establish a biological requested length, so requested-length exact-hit metrics are not applicable."
)
NOVELTY_DIRECTION_STATEMENT = (
    "Directions on nearest_train_normalized_edit_distance and maximum_edit_similarity_to_train "
    "describe novelty only and are not extra votes for overall generator quality."
)
NOVELTY_DIRECTIONS = {
    "nearest_train_normalized_edit_distance": "higher",
    "maximum_edit_similarity_to_train": "lower",
}
# assert_pairing in m6_diagnostic_generation.py compares these fields.
SCHEDULE_ATTEMPT_FIELDS = (
    "original_attempt_index",
    "invocation_index",
    "batch_position",
    "requested_target_length",
    "max_seq_len",
    "invocation_seed",
)
# build_schedule / diagnostic_design names. Synthetic values are not the production schedule.
LENGTH_SCHEDULE_PROVENANCE_KEYS = (
    "target_length_sampling_seed",
    "length_vector_sha256",
    "generation_seed_base",
    "seed_formula",
    "max_seq_len_formula",
    "max_chunk_size",
    "batch_num",
)
SEED_FORMULA = "generation_seed_base + invocation_index"
MAX_SEQ_LEN_FORMULA = "requested_target_length + 1"
IMPLEMENTED_MAX_CHUNK_SIZE = 16
IMPLEMENTED_BATCH_NUM = 1
M4_METRICS_RELATIVE = "scripts/modelling/m4_diagnostic_metrics.py"
M6_DIAGNOSTIC_RELATIVE = "scripts/modelling/m6_diagnostic_generation.py"
ANALYSIS_RELATIVE = "scripts/modelling/generator_eval_analysis.py"
METRICS_CONFIG_RELATIVE = "config/modelling/validation_metrics_v1.yaml"
GOVERNING_PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_4.md"
HISTORICAL_M9C_PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md"
ALLOWED_REVISION_PATHS = (
    M4_METRICS_RELATIVE,
    M6_DIAGNOSTIC_RELATIVE,
    ANALYSIS_RELATIVE,
    METRICS_CONFIG_RELATIVE,
    GOVERNING_PLAN_RELATIVE,
    HISTORICAL_M9C_PLAN_RELATIVE,
)
CODE_PATH_BY_MODULE = {
    "m4_diagnostic_metrics": M4_METRICS_RELATIVE,
    "m6_diagnostic_generation": M6_DIAGNOSTIC_RELATIVE,
    "generator_eval_analysis": ANALYSIS_RELATIVE,
}
CONTROLLED_COMPARISON_KIND = "matched_b1_d1_controlled_comparison"

CONDITIONS = ("B0", "B1", "B2", "D1")
CONDITION_LABELS = {
    "B0": "B0",
    "B0_released_aptamer_rnagenesis": "B0",
    "B1": "B1",
    "B1_generic_released_rnagenesis": "B1",
    "B2": "B2",
    "B2_train_matched_empirical_null": "B2",
    "D1": "D1",
    "D1_mres_curated_aptamer_diffusion_adapted": "D1",
}
LENGTH_REGIMES = {
    "B0": "historical_37nt",
    "B1": "matched_length",
    "B2": "empirical_null_length_draw",
    "D1": "matched_length",
}
SEED_FIELDS = (
    "training_seed",
    "generation_seed",
    "length_sampling_seed",
    "length_condition_seed",
    "empirical_null_seed",
)
RECORD_KEYS = (
    "record_id",
    "condition",
    "data_role",
    "length_regime",
    "checkpoint_id",
    "checkpoint_sha256",
    "training_seed",
    "generation_seed",
    "length_sampling_seed",
    "length_condition_seed",
    "empirical_null_seed",
    "generation_chunk_id",
    "requested_length",
    "observed_length",
    "original_attempt_index",
    "invocation_index",
    "batch_position",
    "requested_target_length",
    "max_seq_len",
    "invocation_seed",
    "length_schedule_provenance",
    "historical_generation_seed",
    "historical_batch_index",
    "nominal_max_seq_len",
    "parsed_status",
    "alphabet_valid",
    "cleaning_status",
    "cleaning_version",
    "sequence",
)
METRIC_FIELDS = (
    "metric_id",
    "display_name",
    "implementation_symbol",
    "data_source",
    "reference_role",
    "scientific_role",
    "calculation_summary",
    "numerator",
    "denominator_and_filters",
    "units",
    "expected_range",
    "direction",
    "length_treatment",
    "seed_or_block_treatment",
    "condition_scope",
    "missing_failure_handling",
    "code_revision",
    "config_revision",
    "freeze_status",
)
SCIENTIFIC_ROLES = ("accounting", "outcome", "closeness", "guardrail", "descriptor")
DIRECTIONS = ("higher", "lower", "two_sided", "not_applicable")
ADDITIONAL_IMPLEMENTED_METRIC_IDS = (
    "per_requested_length_exact_hit_rate",
    "nearest_train_normalized_edit_distance",
    "maximum_edit_similarity_to_train",
    "nucleotide_distribution",
    "dinucleotide_distribution",
    "mfe",
    "mfe_per_nt",
    "paired_fraction",
    "full_length_stratified_results",
)
GEP2_IMPLEMENTED_METRIC_IDS = (
    "successfully_parsed_outputs",
    "pooled_gc_fraction",
    "nearest_reference_normalized_edit_distance",
    "nucleotide_total_variation_to_reference",
    "dinucleotide_total_variation_to_reference",
)
GEP2_CLOSENESS_METRIC_IDS = (
    "nearest_reference_normalized_edit_distance",
    "nucleotide_total_variation_to_reference",
    "dinucleotide_total_variation_to_reference",
)
SYNTHETIC_REFERENCE_ROLE = "synthetic_eval_stand_in"
PRODUCTION_REFERENCE_ROLE = "authorized_eval_unique_cores"
FORBIDDEN_REFERENCE_ROLES = ("EVAL", "REF", "VALIDATION", "TRAIN")
FORBIDDEN_METRIC_ALIASES = (
    "requested_length_exact_hit_rate",
    "maximum_identity_to_TRAIN",
    "maximum_identity_to_train",
    "mfe_per_nucleotide",
    "mfe_per_nt_median",
    "nucleotide_total_variation_to_train",
    "dinucleotide_total_variation_to_train",
    "nucleotide_distribution_distance",
    "dinucleotide_distribution_distance",
    "gc_fraction",
    "combined_quality_score",
    "combined_closeness_score",
    "aggregate_generator_quality_score",
    "generator_quality_score",
    "confidence_interval",
    "mixed",
)
OPTIONAL_RECORD_FIELDS = (
    "s6_length_stratum",
    "s6_assignment_provenance",
    "source_artifact_sha256",
    "parse_outcome",
    "failure_reason",
)
_MODULE_CACHE = {}
RESOLVED_BLOCKING_IDS = (
    "parsed_outputs_predicate_versus_successful_parse",
    "alias_requested_length_exact_hit_rate",
    "alias_maximum_identity_to_train",
    "alias_mfe_per_nucleotide",
    "per_length_exact_hit_floor_not_a_decision",
    "gc_fraction_not_implemented",
    "clustering_diversity_deferred",
    "representation_metrics_deferred",
    "eval_closeness_not_implemented",
    "nucleotide_total_variation_membership_unresolved",
    "dinucleotide_total_variation_membership_unresolved",
    "confidence_intervals_not_specified_in_gep1",
    "train_reference_not_loaded_in_gep1",
    "structure_metrics_not_executed_in_gep1",
    "viennarna_production_settings_not_pinned",
    "production_matched_chunk_schedule_not_wired",
    "b2_generic_seed_field_disambiguated",
)
RESOLVED_REQUIRED_PHRASES = {
    "parsed_outputs_predicate_versus_successful_parse": "successfully_parsed_outputs counts nonempty extracted sequences before A/C/G/U filtering",
    "alias_requested_length_exact_hit_rate": "exact_hit_rate is the only requested-length exact-hit metric",
    "alias_maximum_identity_to_train": "maximum_identity_to_TRAIN is retired and is not an alias. maximum_edit_similarity_to_train remains the code metric",
    "alias_mfe_per_nucleotide": "mfe_per_nt remains the generator metric. It is not the AptaRank normalized-MFE component.",
    "per_length_exact_hit_floor_not_a_decision": "0.90 and 0.50 are historical references, not decisions. B0 exact hit is not_applicable.",
    "gc_fraction_not_implemented": "pooled_gc_fraction",
    "eval_closeness_not_implemented": "formal M9C unlock supplies unique EVAL cores",
    "nucleotide_total_variation_membership_unresolved": "nested descriptive output",
    "dinucleotide_total_variation_membership_unresolved": "nested descriptive output",
    "clustering_diversity_deferred": "explicitly outside M10",
    "representation_metrics_deferred": "explicitly outside M10",
    "confidence_intervals_not_specified_in_gep1": "explicitly outside M10",
    "train_reference_not_loaded_in_gep1": "satisfied by the frozen M9A outputs",
    "structure_metrics_not_executed_in_gep1": "implemented and synthetically verified",
    "production_matched_chunk_schedule_not_wired": "implemented and synthetically verified",
    "b2_generic_seed_field_disambiguated": "does not assume that a production run used seed 42",
    "viennarna_production_settings_not_pinned": "The existing generator fold is RNA.fold(sequence) in ViennaRNA 2.7.0 and sets no model detail.",
}
BLOCKING_IDS = (
    "parsed_outputs_predicate_versus_successful_parse",
    "alias_requested_length_exact_hit_rate",
    "alias_maximum_identity_to_train",
    "alias_mfe_per_nucleotide",
    "per_length_exact_hit_floor_not_a_decision",
    "gc_fraction_not_implemented",
    "clustering_diversity_deferred",
    "representation_metrics_deferred",
    "eval_closeness_not_implemented",
    "nucleotide_total_variation_membership_unresolved",
    "dinucleotide_total_variation_membership_unresolved",
    "confidence_intervals_not_specified_in_gep1",
    "train_reference_not_loaded_in_gep1",
    "structure_metrics_not_executed_in_gep1",
    "viennarna_production_settings_not_pinned",
    "production_matched_chunk_schedule_not_wired",
    "b2_generic_seed_field_disambiguated",
)
# The six former blockers are resolved dispositions. Their status is resolved.
M10_BLOCKING_DISPOSITIONS = {
    "clustering_diversity_deferred": "outside_m10",
    "representation_metrics_deferred": "outside_m10",
    "confidence_intervals_not_specified_in_gep1": "outside_m10",
    "train_reference_not_loaded_in_gep1": "satisfied_by_frozen_m9a_outputs",
    "structure_metrics_not_executed_in_gep1": "required_implementation_work",
    "production_matched_chunk_schedule_not_wired": "required_implementation_work",
}
S6_ASSIGNMENT_STATEMENT = (
    "Valid generated sequences and authorized EVAL cores are assigned by applying the frozen S6 "
    "`gmm_k2_maximum_posterior` rule to S6 `length_of(sequence_core)`, with component 0 short, "
    "component 1 long, ties short, no refitting, no requested-generation-length input, and no invented fixed cutoff."
)
S6_ASSIGNMENT_METRIC_IDS = (
    "pooled_gc_fraction",
    "nearest_reference_normalized_edit_distance",
    "nucleotide_total_variation_to_reference",
    "dinucleotide_total_variation_to_reference",
)
FORBIDDEN_S6_LABEL_CLAIMS = (
    "not inferred from sequence length",
    "never inferred from sequence length",
)
CLOSED_BY_M10_SCOPE = (
    {"id": "clustering_diversity_deferred", "subject": "clustering"},
    {"id": "representation_metrics_deferred", "subject": "representation analysis"},
    {
        "id": "confidence_intervals_not_specified_in_gep1",
        "subject": "confidence intervals, bootstrap, hypothesis tests, and EVAL-cluster resampling",
    },
)
SATISFIED_BY_FROZEN_EVIDENCE = (
    {
        "id": "train_reference_not_loaded_in_gep1",
        "subject": "production TRAIN loading through the frozen M9A summaries",
    },
)
IMPLEMENTED_AWAITING_AUTHORIZATION = (
    {
        "id": "structure_metrics_not_executed_in_gep1",
        "subject": "ViennaRNA structure wrapper and distinct-sequence cache, implemented and synthetically verified; biological execution is not authorized",
    },
    {
        "id": "production_matched_chunk_schedule_not_wired",
        "subject": "matched B1/D1 production schedule, implemented and synthetically verified; biological execution is not authorized",
    },
)
BLOCKER_CLASSIFICATION_DISPOSITIONS = {
    "closed_by_m10_scope": "outside_m10",
    "satisfied_by_frozen_evidence": "satisfied_by_frozen_m9a_outputs",
    "implemented_awaiting_authorization": "required_implementation_work",
}
BLOCKER_CLASSIFICATION_GROUPS = (
    ("closed_by_m10_scope", CLOSED_BY_M10_SCOPE),
    ("satisfied_by_frozen_evidence", SATISFIED_BY_FROZEN_EVIDENCE),
    ("implemented_awaiting_authorization", IMPLEMENTED_AWAITING_AUTHORIZATION),
)
REQUIRED_IMPLEMENTATION_IDS = (
    "ledger_adapter",
    "authorized_eval_adapter",
    "matched_block_binding",
    "structure_execution",
    "sequence_free_report_writer",
)
UNLOCK_KEYS = (
    "timestamp",
    "operator",
    "reviewer",
    "corrected_role_hashes",
    "m9a_artefact_references",
    "m9b_artefact_references",
    "m9c_code_configuration_hashes",
    "frozen_plan_identifier",
    "unlock_assertion",
)
ROLE_HASH_KEYS = ("TRAIN", "VALIDATION", "REF", "EVAL")
BINDING_KEYS = (
    "corrected_role_hashes",
    "m9a_artefact_references",
    "m9b_artefact_references",
    "m9c_code_configuration_hashes",
    "frozen_plan_identifier",
)
FORBIDDEN_FILENAMES = ("eval.csv", "ref.csv", "ft_validation.csv", "ft_train.csv", "corpus_final.csv")
NOT_TRAINING_REPLICATE_UNITS = (
    "record_id",
    "generation_chunk_id",
    "generation_seed",
    "invocation_seed",
    "invocation_index",
    "batch_position",
    "original_attempt_index",
    "length_sampling_seed",
    "length_condition_seed",
    "empirical_null_seed",
    "historical_generation_seed",
    "historical_batch_index",
)
TEXT_METRIC_FIELDS = tuple(field for field in METRIC_FIELDS if field not in ("code_revision", "config_revision"))


class GeneratorEvalContractError(ValueError):
    """The synthetic contract or the EVAL gate refused the request."""

    def __init__(self, code, detail, errors=None):
        self.code = code
        self.detail = detail
        self.errors = [] if errors is None else list(errors)
        super().__init__(code + ": " + detail)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def spec_path():
    return os.path.join(repo_root(), SPEC_RELATIVE)


def fixture_root():
    return os.path.join(repo_root(), FIXTURE_RELATIVE)


def default_fixture_path():
    return os.path.join(fixture_root(), DEFAULT_FIXTURE_NAME)


def _load_module(filename, name):
    """Load a sibling module once per process. Shared validity must not reload M4."""
    cached = _MODULE_CACHE.get(name)
    if cached is not None:
        return cached
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MODULE_CACHE[name] = module
    return module


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_text(args):
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _problem(code, detail):
    return {"code": code, "detail": detail}


def _raise_problems(problems):
    if not problems:
        return
    primary = next((item for item in problems if item["code"] != "filename_guard"), problems[0])
    raise GeneratorEvalContractError(primary["code"], primary["detail"], problems)


def _nonempty_text(value):
    return isinstance(value, str) and value.strip() != ""


def _sha256_value(value):
    return isinstance(value, str) and SHA256_TEXT.fullmatch(value) is not None


def _optional_sha256(value):
    return value is None or _sha256_value(value)


def _seed_value(value):
    return value is None or (type(value) is int and value >= 0)


def _forbidden_filename(filename):
    if filename is None:
        return False
    base = os.path.basename(str(filename)).lower()
    return base in FORBIDDEN_FILENAMES


def _row_is_valid(row):
    sequence = row["sequence"]
    return (
        row["parsed_status"] is True
        and row["alphabet_valid"] is True
        and row["cleaning_status"] == "cleaned"
        and isinstance(sequence, str)
        and CANONICAL_SEQUENCE.fullmatch(sequence) is not None
        and row["observed_length"] == len(sequence)
    )


def load_metric_spec(path=None):
    document_path = spec_path() if path is None else path
    with open(document_path, encoding="utf-8") as handle:
        spec = json.load(handle)
    validate_metric_spec(spec, require_draft=spec.get("freeze_status") != "frozen")
    return spec


def _hash_revision_path(path):
    if path not in ALLOWED_REVISION_PATHS:
        return None
    return _sha256_file(os.path.join(repo_root(), path))


def _validate_path_sha256(value, label, expected_path, problems):
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        problems.append(_problem("revision_invalid", label + " must record path and sha256"))
        return
    path = value.get("path")
    digest = value.get("sha256")
    if path not in ALLOWED_REVISION_PATHS:
        problems.append(_problem("revision_path_refused", label + " path is not a GEP-1 source"))
        return
    if not _sha256_value(digest):
        problems.append(_problem("revision_invalid", label + " sha256 is invalid"))
        return
    if expected_path is not None and path != expected_path:
        problems.append(_problem("revision_path_mismatch", label + " path does not match its implementation"))
        return
    actual = _hash_revision_path(path)
    if actual != digest:
        problems.append(_problem("source_hash_mismatch", label + " sha256 does not match " + path))


def _validate_plan_identity(plan, label, relative, version, revision_date, problems):
    if not isinstance(plan, dict) or set(plan) != {"path", "sha256", "version", "revision_date"}:
        problems.append(_problem("revision_invalid", label + " must record path, sha256, version, and revision date"))
        return
    if plan.get("path") != relative or plan.get("version") != version or plan.get("revision_date") != revision_date:
        problems.append(_problem("revision_invalid", label + " is not " + version + " dated " + revision_date))
        return
    _validate_path_sha256(
        {"path": plan["path"], "sha256": plan.get("sha256")},
        label,
        relative,
        problems,
    )


def _validate_governing_plan(spec, problems):
    _validate_plan_identity(
        spec.get("governing_plan"),
        "the active governing plan",
        GOVERNING_PLAN_RELATIVE,
        GOVERNING_PLAN_VERSION,
        GOVERNING_PLAN_REVISION_DATE,
        problems,
    )
    historical = spec.get("historical_m9c_plan")
    if not isinstance(historical, dict) or historical.get("role") != "m9c_frozen_historical":
        problems.append(_problem("revision_invalid", "v3.3 must remain recorded as the historical M9C plan"))
        return
    _validate_plan_identity(
        {key: historical.get(key) for key in ("path", "sha256", "version", "revision_date")},
        "the historical M9C plan",
        HISTORICAL_M9C_PLAN_RELATIVE,
        HISTORICAL_M9C_PLAN_VERSION,
        HISTORICAL_M9C_PLAN_REVISION_DATE,
        problems,
    )


def _validate_metric_revisions(metric, problems):
    symbol = metric.get("implementation_symbol")
    module_name = symbol.split(".", 1)[0] if isinstance(symbol, str) and "." in symbol else ""
    expected_code = CODE_PATH_BY_MODULE.get(module_name)
    metric_id = metric.get("metric_id", "metric")
    if expected_code is None:
        problems.append(_problem("revision_path_mismatch", metric_id + " implementation module is not a hashed GEP-1 source"))
        return
    _validate_path_sha256(metric.get("code_revision"), metric_id + " code_revision", expected_code, problems)
    _validate_path_sha256(metric.get("config_revision"), metric_id + " config_revision", METRICS_CONFIG_RELATIVE, problems)


def _analysis_implements(symbol):
    if not isinstance(symbol, str) or "." not in symbol:
        return False
    module_name, func_name = symbol.split(".", 1)
    if module_name != "generator_eval_analysis":
        return False
    module = _load_module("generator_eval_analysis.py", "gep2_analysis_for_spec")
    function = getattr(module, func_name, None)
    return callable(function)


def blocker_classification():
    """Partition the six explicit M10 dispositions into reporting classes.

    The disposition strings stay on each entry. Closed-by-scope items,
    frozen-evidence items, and work that is implemented but not yet
    biologically executed are not active implementation blockers.
    """
    classified = {}
    for group_name, entries in BLOCKER_CLASSIFICATION_GROUPS:
        disposition = BLOCKER_CLASSIFICATION_DISPOSITIONS[group_name]
        classified[group_name] = [
            {"id": entry["id"], "m10_disposition": disposition, "subject": entry["subject"]} for entry in entries
        ]
    return classified


def _reject_forbidden_s6_claims(value, problems, where):
    if isinstance(value, str):
        lowered = value.lower()
        for claim in FORBIDDEN_S6_LABEL_CLAIMS:
            if claim in lowered:
                problems.append(
                    _problem(
                        "s6_label_claim_invalid",
                        where + " still says the S6 label is not inferred from sequence length",
                    )
                )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_forbidden_s6_claims(item, problems, where + "." + str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_s6_claims(item, problems, "%s[%d]" % (where, index))


FROZEN_METRIC_SPECIFICATION_READINESS = "frozen_and_production_ready"
ACTIVE_DRAFT_PHRASES = ("remains draft", "not production-ready")


def _require_frozen_specification_language(draft, problems):
    """Require frozen production-ready wording and reject an active draft claim.

    The readiness value and the supersession statement are part of the freeze.
    Stale draft wording fails before any EVAL access.
    """
    readiness = draft.get("implementation_readiness")
    value = readiness.get("metric_specification") if isinstance(readiness, dict) else None
    if value != FROZEN_METRIC_SPECIFICATION_READINESS:
        problems.append(
            _problem(
                "metric_spec_readiness_unfrozen",
                "a frozen specification requires metric_specification readiness frozen_and_production_ready",
            )
        )
    note = draft.get("inactive_pathway_supersession")
    statement = note.get("statement") if isinstance(note, dict) else None
    if not isinstance(statement, str):
        problems.append(
            _problem(
                "metric_spec_freeze_statement_invalid",
                "a frozen specification requires a supersession statement",
            )
        )
        return
    lowered = statement.lower()
    for phrase in ACTIVE_DRAFT_PHRASES:
        if phrase in lowered:
            problems.append(
                _problem(
                    "metric_spec_draft_wording",
                    "a frozen specification still says " + phrase,
                )
            )
    if "frozen" not in lowered or "production-ready" not in lowered:
        problems.append(
            _problem(
                "metric_spec_freeze_statement_invalid",
                "the freeze statement must say the specification is frozen and production-ready",
            )
        )
    if "production execution remains unauthorized" not in lowered and "production remains unauthorized" not in lowered:
        problems.append(
            _problem(
                "metric_spec_freeze_statement_invalid",
                "the freeze statement must say production remains unauthorized",
            )
        )


def validate_metric_spec(spec, require_draft=True):
    """Return the spec when its membership, formulas, revisions, and dispositions match.

    A closeness row is accepted only for an implemented GEP-2 metric whose
    production reference role is exactly ``authorized_eval_unique_cores``.
    Runtime role EVAL is refused. Synthetic fixtures exercise the formulas
    without changing that declaration. ``require_draft=True`` keeps a draft
    package draft. A candidate frozen specification is checked with
    ``require_draft=False`` and must be frozen at the top level, on every
    metric row, and on the contract, with both production labels true, no
    blocking item left unresolved, ``metric_specification`` readiness
    ``frozen_and_production_ready``, and a supersession statement that says
    the specification is frozen and production-ready while production remains
    unauthorized. Active wording such as "remains draft" or "not
    production-ready" fails that check.
    """
    metrics_module = _load_module("m4_diagnostic_metrics.py", "gep1_m4_metrics")
    report_module = _load_module("m6_diagnostic_generation.py", "gep1_m6_report")
    problems = []
    if not isinstance(spec, dict):
        raise GeneratorEvalContractError("metric_spec_invalid", "metric spec is not an object")
    if spec.get("aggregate_generator_quality_score") is not False:
        problems.append(_problem("aggregate_score_forbidden", "an aggregate generator-quality score is not defined"))
    if spec.get("novelty_direction_statement") != NOVELTY_DIRECTION_STATEMENT:
        problems.append(_problem("novelty_direction_invalid", "novelty directions must be limited to novelty and must not vote for generator quality"))
    if spec.get("freeze_status") != "draft" and require_draft:
        problems.append(_problem("metric_spec_frozen_in_gep1", "the GEP-1 spec package is draft"))
    _validate_governing_plan(spec, problems)
    metrics = spec.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        problems.append(_problem("metric_spec_invalid", "metrics are missing"))
        _raise_problems(problems)
    seen = []
    for index, metric in enumerate(metrics):
        if not isinstance(metric, dict):
            problems.append(_problem("metric_spec_invalid", "metric %d is not an object" % index))
            continue
        missing = [field for field in TEXT_METRIC_FIELDS if field not in metric or not _nonempty_text(metric[field])]
        if missing:
            problems.append(_problem("metric_spec_invalid", "metric %d lacks %s" % (index, ", ".join(missing))))
            continue
        _validate_metric_revisions(metric, problems)
        metric_id = metric["metric_id"]
        if metric_id in seen:
            problems.append(_problem("metric_spec_invalid", "duplicate metric_id " + metric_id))
        seen.append(metric_id)
        if metric_id in FORBIDDEN_METRIC_ALIASES:
            problems.append(_problem("unknown_metric_alias", metric_id + " is not a metric id"))
        if metric["reference_role"] in FORBIDDEN_REFERENCE_ROLES:
            problems.append(_problem("reference_role_refused", metric_id + " labels a reference as " + metric["reference_role"]))
        if metric["scientific_role"] not in SCIENTIFIC_ROLES:
            problems.append(_problem("metric_spec_invalid", metric_id + " has an unknown scientific role"))
        if metric["scientific_role"] == "closeness":
            if metric_id not in GEP2_CLOSENESS_METRIC_IDS or not _analysis_implements(metric.get("implementation_symbol")):
                problems.append(_problem("closeness_metric_not_implemented", metric_id + " claims closeness without the synthetic implementation"))
            elif metric["reference_role"] != PRODUCTION_REFERENCE_ROLE:
                problems.append(
                    _problem(
                        "production_reference_role_refused",
                        metric_id + " production reference role is not authorized_eval_unique_cores",
                    )
                )
            elif metric["direction"] != "lower":
                problems.append(_problem("metric_spec_invalid", metric_id + " closeness direction must be lower"))
        elif metric_id in GEP2_IMPLEMENTED_METRIC_IDS and not _analysis_implements(metric.get("implementation_symbol")):
            problems.append(_problem("implementation_missing", metric_id + " has no analysis implementation"))
        if metric["direction"] not in DIRECTIONS:
            problems.append(_problem("metric_spec_invalid", metric_id + " has an unknown direction"))
        if metric["freeze_status"] not in ("draft", "frozen"):
            problems.append(_problem("metric_spec_invalid", metric_id + " has an unknown freeze status"))
        if require_draft and metric["freeze_status"] != "draft":
            problems.append(_problem("metric_spec_frozen_in_gep1", metric_id + " is frozen"))
        elif not require_draft and metric["freeze_status"] != "frozen":
            problems.append(_problem("metric_row_unfrozen", metric_id + " remains draft"))
        if metric_id in S6_ASSIGNMENT_METRIC_IDS and S6_ASSIGNMENT_STATEMENT not in metric["length_treatment"]:
            problems.append(_problem("s6_assignment_statement_missing", metric_id + " does not state the frozen S6 length assignment"))
        if metric_id in NOVELTY_DIRECTIONS:
            if metric["scientific_role"] != "outcome":
                problems.append(_problem("novelty_role_invalid", metric_id + " is a novelty outcome, not EVAL closeness"))
            if metric["direction"] != NOVELTY_DIRECTIONS[metric_id]:
                problems.append(_problem("novelty_direction_invalid", metric_id + " novelty direction drifted"))
            if metric.get("novelty_direction_only") is not True:
                problems.append(_problem("novelty_direction_invalid", metric_id + " direction is not limited to novelty"))
        if metric_id == "exact_train_match_rate" and metric["scientific_role"] != "guardrail":
            problems.append(_problem("metric_spec_invalid", "exact TRAIN overlap remains a guardrail"))
        if metric_id in metrics_module.GUARDRAIL_THRESHOLDS:
            expected = metrics_module.GUARDRAIL_THRESHOLDS[metric_id]
            if metric.get("approved_threshold") != expected:
                problems.append(_problem("metric_threshold_drift", metric_id + " threshold does not match the implemented guardrail"))
        elif "approved_threshold" in metric:
            problems.append(_problem("metric_threshold_invented", metric_id + " declares a threshold the implementation does not"))
    expected_ids = (
        set(metrics_module.IMPLEMENTED_METRIC_IDS)
        | set(metrics_module.HARD_GUARDRAIL_IDS)
        | set(ADDITIONAL_IMPLEMENTED_METRIC_IDS)
        | set(GEP2_IMPLEMENTED_METRIC_IDS)
    )
    if set(seen) != expected_ids:
        missing_ids = sorted(expected_ids - set(seen))
        extra_ids = sorted(set(seen) - expected_ids)
        problems.append(_problem("metric_membership_drift", "missing %s; extra %s" % (missing_ids, extra_ids)))
    for deferred in metrics_module.DEFERRED_BEYOND_M4:
        if deferred in seen:
            problems.append(_problem("deferred_metric_included", deferred + " is deferred beyond M4"))
    blocking = spec.get("blocking_items")
    if not isinstance(blocking, list):
        problems.append(_problem("metric_spec_invalid", "blocking items are missing"))
        blocking = []
    resolved_ids = []
    unresolved_ids = []
    for item in blocking:
        if not isinstance(item, dict) or not _nonempty_text(item.get("id")) or item.get("status") not in ("resolved", "unresolved"):
            problems.append(_problem("metric_spec_invalid", "a blocking item is incomplete"))
            continue
        if not _nonempty_text(item.get("statement")) or not isinstance(item.get("related_names"), list):
            problems.append(_problem("metric_spec_invalid", item["id"] + " lacks a statement or related names"))
            continue
        if item["status"] == "resolved":
            phrase = RESOLVED_REQUIRED_PHRASES.get(item["id"])
            if phrase is None or phrase not in item["statement"]:
                problems.append(_problem("blocking_decision_missing", item["id"] + " does not record the reviewed decision"))
            resolved_ids.append(item["id"])
        else:
            unresolved_ids.append(item["id"])
            if not require_draft:
                problems.append(_problem("blocking_item_unresolved", item["id"] + " remains unresolved"))
    if set(resolved_ids) != set(RESOLVED_BLOCKING_IDS):
        problems.append(_problem("blocking_item_drift", "resolved blocking items do not match the reviewed set"))
    if len(resolved_ids) != len(set(resolved_ids)) or len(unresolved_ids) != len(set(unresolved_ids)):
        problems.append(_problem("blocking_item_drift", "a blocking item id is duplicated"))
    dispositions = {}
    for item in blocking:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if item_id not in M10_BLOCKING_DISPOSITIONS:
            continue
        if item.get("m10_disposition") != M10_BLOCKING_DISPOSITIONS[item_id]:
            problems.append(_problem("blocking_disposition_invalid", item_id + " does not carry its M10 disposition"))
        dispositions[item_id] = item.get("m10_disposition")
    if set(dispositions) != set(M10_BLOCKING_DISPOSITIONS) or set(M10_BLOCKING_DISPOSITIONS) - set(resolved_ids):
        problems.append(_problem("blocking_disposition_invalid", "the six M10 dispositions are not resolved"))
    classified_ids = []
    for group_name, entries in BLOCKER_CLASSIFICATION_GROUPS:
        expected_disposition = BLOCKER_CLASSIFICATION_DISPOSITIONS[group_name]
        for entry in entries:
            classified_ids.append(entry["id"])
            if M10_BLOCKING_DISPOSITIONS.get(entry["id"]) != expected_disposition:
                problems.append(_problem("blocking_disposition_invalid", entry["id"] + " is not in its reporting class"))
            if dispositions.get(entry["id"]) != expected_disposition:
                problems.append(_problem("blocking_disposition_invalid", entry["id"] + " disposition is not preserved"))
    if classified_ids != list(dict.fromkeys(classified_ids)) or set(classified_ids) != set(M10_BLOCKING_DISPOSITIONS):
        problems.append(_problem("blocking_disposition_invalid", "the blocker classification does not partition the six M10 dispositions"))
    draft = spec.get("m10_draft_contract")
    if not isinstance(draft, dict):
        problems.append(_problem("metric_spec_not_draft", "the metric specification contract is missing"))
        draft = {}
    elif require_draft and (
        draft.get("document_status") != "draft" or draft.get("labelled_production_ready") is not False
    ):
        problems.append(_problem("metric_spec_not_draft", "the metric specification must stay draft and not production-ready"))
    elif require_draft:
        note = draft.get("inactive_pathway_supersession")
        if not isinstance(note, dict) or "remains draft" not in str(note.get("statement")):
            problems.append(_problem("metric_spec_not_draft", "the draft supersession note is missing"))
    if not require_draft:
        if spec.get("freeze_status") != "frozen":
            problems.append(_problem("metric_spec_unfrozen", "a frozen specification requires top-level freeze_status frozen"))
        if (
            draft.get("document_status") != "frozen"
            or draft.get("labelled_frozen") is not True
            or draft.get("labelled_production_ready") is not True
        ):
            problems.append(
                _problem(
                    "metric_spec_contract_unfrozen",
                    "a frozen specification requires a frozen contract that is labelled frozen and production-ready",
                )
            )
        _require_frozen_specification_language(draft, problems)
    required_items = draft.get("required_implementation_work")
    required = {}
    if isinstance(required_items, list):
        for entry in required_items:
            if isinstance(entry, dict) and _nonempty_text(entry.get("id")):
                required[entry["id"]] = entry
    for item_id in REQUIRED_IMPLEMENTATION_IDS:
        entry = required.get(item_id)
        if not isinstance(entry, dict) or entry.get("status") != "required":
            problems.append(_problem("required_implementation_missing", item_id + " is not recorded as required implementation work"))
    covered = set(seen)
    for name in report_module.REPORT_ONLY_ITEMS:
        if name in covered:
            continue
        named = False
        for item in blocking:
            if isinstance(item, dict) and name in item.get("related_names", []):
                named = True
        if not named:
            problems.append(_problem("metric_silently_dropped", name + " is neither specified nor blocked"))
    _validate_m8_contract_blocks(spec, problems)
    _reject_forbidden_s6_claims(spec, problems, "metric_spec")
    _raise_problems(problems)
    return spec


def _canonical_condition(label):
    if label not in CONDITION_LABELS:
        return None
    return CONDITION_LABELS[label]


def _check_status_consistency(row, problems, record_id):
    sequence = row["sequence"]
    parsed = row["parsed_status"]
    alphabet_valid = row["alphabet_valid"]
    cleaning = row["cleaning_status"]
    observed = row["observed_length"]
    if type(parsed) is not bool or type(alphabet_valid) is not bool:
        problems.append(_problem("status_invalid", record_id + " status flags are not booleans"))
        return
    if cleaning not in ("cleaned", "rejected", "not_applicable"):
        problems.append(_problem("status_invalid", record_id + " cleaning status is unknown"))
        return
    if parsed is False:
        if sequence is not None or observed is not None or alphabet_valid is not False or cleaning != "not_applicable":
            problems.append(_problem("parse_status_inconsistent", record_id + " parse failure is internally inconsistent"))
        if row["cleaning_version"] is not None:
            problems.append(_problem("cleaning_version_inconsistent", record_id + " has a cleaning version without cleaning"))
        return
    if not isinstance(sequence, str) or sequence == "" or type(observed) is not int or observed != len(sequence):
        problems.append(_problem("observed_length_inconsistent", record_id + " observed length does not match the sequence"))
        return
    matches = CANONICAL_SEQUENCE.fullmatch(sequence) is not None
    if alphabet_valid is not matches:
        problems.append(_problem("alphabet_status_inconsistent", record_id + " alphabet flag does not match the sequence"))
    if alphabet_valid is True:
        if cleaning != "cleaned" or not _nonempty_text(row["cleaning_version"]):
            problems.append(_problem("cleaning_status_inconsistent", record_id + " valid sequence is not marked cleaned"))
    elif cleaning != "rejected" or not _nonempty_text(row["cleaning_version"]):
        problems.append(_problem("cleaning_status_inconsistent", record_id + " invalid alphabet is not marked rejected"))


def _check_parser_classification(row, problems, record_id):
    """Fail closed when a recorded parser outcome disagrees with the row."""
    has_outcome = "parse_outcome" in row
    has_reason = "failure_reason" in row
    if not has_outcome and not has_reason:
        return
    if not has_outcome or not has_reason:
        problems.append(_problem("parser_outcome_inconsistent", record_id + " records only one of parse_outcome and failure_reason"))
        return
    outcome = row["parse_outcome"]
    reason = row["failure_reason"]
    if outcome not in PARSE_OUTCOMES:
        problems.append(_problem("parser_outcome_invalid", record_id + " parse_outcome is outside the closed vocabulary"))
        return
    if reason is not None and reason not in FAILURE_REASONS:
        problems.append(_problem("failure_reason_invalid", record_id + " failure_reason is outside the closed vocabulary"))
        return
    if outcome == PARSE_OUTCOME_VALID:
        if reason is not None or not _row_is_valid(row):
            problems.append(_problem("parser_outcome_inconsistent", record_id + " valid canonical outcome is internally inconsistent"))
        return
    if reason != outcome:
        problems.append(_problem("parser_outcome_inconsistent", record_id + " failure_reason does not match parse_outcome"))
        return
    if outcome == PARSE_OUTCOME_NON_ACGU:
        sequence = row["sequence"]
        if (
            row["parsed_status"] is not True
            or row["alphabet_valid"] is not False
            or not isinstance(sequence, str)
            or sequence == ""
            or CANONICAL_SEQUENCE.fullmatch(sequence) is not None
        ):
            problems.append(_problem("parser_outcome_inconsistent", record_id + " parsed non-ACGU outcome is internally inconsistent"))
        return
    if outcome in SEQUENCE_NULL_PARSE_OUTCOMES:
        if row["sequence"] is not None or row["parsed_status"] is not False or row["observed_length"] is not None:
            problems.append(_problem("parser_outcome_inconsistent", record_id + " null-sequence outcome retained a sequence"))


def _check_positive_requested_length(row, problems, record_id):
    if type(row["requested_length"]) is not int or row["requested_length"] < 1:
        problems.append(_problem("requested_length_invalid", record_id + " requested length is not a positive integer"))


def _check_schedule_absent(row, problems, record_id, code):
    if any(row[field] is not None for field in SCHEDULE_ATTEMPT_FIELDS) or row["length_schedule_provenance"] is not None:
        problems.append(_problem(code, record_id + " carries B1/D1 schedule provenance"))


def _check_b0_provenance(row, problems, record_id):
    _check_schedule_absent(row, problems, record_id, "b0_matched_schedule_forbidden")
    if row["generation_chunk_id"] is not None:
        problems.append(_problem("b0_chunk_forbidden", record_id + " carries matched-chunk provenance"))
    seed = row["historical_generation_seed"]
    if type(seed) is not int or seed < 0:
        problems.append(_problem("b0_historical_generation_seed_missing", record_id + " lacks historical generation-seed provenance"))
    batch = row["historical_batch_index"]
    if type(batch) is not int or batch < 0:
        problems.append(_problem("b0_historical_batch_missing", record_id + " lacks historical batch provenance"))
    if row["nominal_max_seq_len"] != B0_NOMINAL_MAX_SEQ_LEN:
        problems.append(_problem("b0_nominal_max_seq_len_invalid", record_id + " nominal max_seq_len is not 37"))
    if row["requested_length"] is not None or row["requested_target_length"] is not None:
        problems.append(_problem(
            "b0_requested_length_not_established",
            record_id + " assigns a biological requested length the historical evidence does not establish",
        ))


def _check_length_schedule_provenance(value, problems, record_id):
    before = len(problems)
    if not isinstance(value, dict) or set(value) != set(LENGTH_SCHEDULE_PROVENANCE_KEYS):
        problems.append(_problem("length_schedule_provenance_invalid", record_id + " length-schedule provenance is incomplete"))
        return None
    sampling_seed = value["target_length_sampling_seed"]
    seed_base = value["generation_seed_base"]
    if type(sampling_seed) is not int or sampling_seed < 0 or type(seed_base) is not int or seed_base < 0:
        problems.append(_problem("length_schedule_provenance_invalid", record_id + " sampling seed or generation-seed base is invalid"))
    if not _sha256_value(value["length_vector_sha256"]):
        problems.append(_problem("length_schedule_provenance_invalid", record_id + " length-vector sha256 is invalid"))
    if value["seed_formula"] != SEED_FORMULA or value["max_seq_len_formula"] != MAX_SEQ_LEN_FORMULA:
        problems.append(_problem("length_schedule_provenance_invalid", record_id + " seed or max_seq_len formula is not the implemented rule"))
    if value["max_chunk_size"] != IMPLEMENTED_MAX_CHUNK_SIZE or value["batch_num"] != IMPLEMENTED_BATCH_NUM:
        problems.append(_problem("length_schedule_provenance_invalid", record_id + " chunk size or batch_num is not the implemented rule"))
    if len(problems) != before:
        return None
    return value


def _check_matched_schedule_row(row, problems, record_id):
    if row["historical_generation_seed"] is not None or row["historical_batch_index"] is not None or row["nominal_max_seq_len"] is not None:
        problems.append(_problem("historical_b0_provenance_forbidden", record_id + " carries B0 historical provenance"))
    if not isinstance(row["generation_chunk_id"], str) or CHUNK_ID_TEXT.fullmatch(row["generation_chunk_id"]) is None:
        problems.append(_problem("chunk_id_invalid", record_id + " chunk label is invalid"))
    provenance = _check_length_schedule_provenance(row["length_schedule_provenance"], problems, record_id)
    for field in ("original_attempt_index", "invocation_index", "batch_position", "invocation_seed"):
        if type(row[field]) is not int or row[field] < 0:
            problems.append(_problem("schedule_field_invalid", record_id + " " + field + " is not a nonnegative integer"))
    requested = row["requested_target_length"]
    if type(requested) is not int or requested < 1:
        problems.append(_problem("schedule_field_invalid", record_id + " requested_target_length is not a positive integer"))
    elif row["requested_length"] != requested:
        problems.append(_problem("requested_length_invalid", record_id + " requested length does not equal requested_target_length"))
    if type(row["max_seq_len"]) is not int or (type(requested) is int and row["max_seq_len"] != requested + 1):
        problems.append(_problem("max_seq_len_invalid", record_id + " max_seq_len is not requested_target_length + 1"))
    if type(row["invocation_seed"]) is int and row["generation_seed"] != row["invocation_seed"]:
        problems.append(_problem("invocation_seed_invalid", record_id + " generation_seed does not equal invocation_seed"))
    if provenance is None:
        return
    if type(row["invocation_index"]) is int and type(row["invocation_seed"]) is int:
        if row["invocation_seed"] != provenance["generation_seed_base"] + row["invocation_index"]:
            problems.append(_problem("invocation_seed_invalid", record_id + " invocation_seed is not generation_seed_base + invocation_index"))
    if row["length_sampling_seed"] != provenance["target_length_sampling_seed"]:
        problems.append(_problem("length_schedule_provenance_invalid", record_id + " length_sampling_seed does not equal target_length_sampling_seed"))
    if type(row["batch_position"]) is int and row["batch_position"] >= provenance["max_chunk_size"]:
        problems.append(_problem("schedule_field_invalid", record_id + " batch_position is outside the implemented chunk"))


def _check_seed_roles(row, problems, record_id):
    for field in SEED_FIELDS:
        if not _seed_value(row[field]):
            problems.append(_problem("seed_invalid", record_id + " " + field + " is not null or a nonnegative integer"))
    condition = row["condition"]
    if condition == "B0":
        if any(row[field] is not None for field in SEED_FIELDS):
            problems.append(_problem("b0_seed_forbidden", record_id + " uses a training, invocation, length-control, or empirical-null seed"))
        _check_b0_provenance(row, problems, record_id)
    elif condition == "B2":
        if row["empirical_null_seed"] is None or any(row[field] is not None for field in SEED_FIELDS if field != "empirical_null_seed"):
            problems.append(_problem("b2_seed_role_invalid", record_id + " must carry only empirical_null_seed"))
        if row["generation_chunk_id"] is not None or row["checkpoint_id"] is not None or row["checkpoint_sha256"] is not None:
            problems.append(_problem("b2_neural_provenance_forbidden", record_id + " carries neural provenance"))
        _check_schedule_absent(row, problems, record_id, "b2_neural_provenance_forbidden")
        if row["historical_generation_seed"] is not None or row["historical_batch_index"] is not None or row["nominal_max_seq_len"] is not None:
            problems.append(_problem("b2_neural_provenance_forbidden", record_id + " carries B0 historical provenance"))
        _check_positive_requested_length(row, problems, record_id)
    elif condition == "B1":
        if row["training_seed"] is not None:
            problems.append(_problem("b1_training_seed_forbidden", record_id + " treats a B1 row as a training replicate"))
        if row["empirical_null_seed"] is not None:
            problems.append(_problem("seed_role_invalid", record_id + " carries an empirical-null seed"))
        if all(row[field] is None for field in ("generation_seed", "length_sampling_seed", "length_condition_seed")):
            problems.append(_problem("b1_generation_provenance_missing", record_id + " has no generation or length-control seed"))
        if not _nonempty_text(row["checkpoint_id"]):
            problems.append(_problem("checkpoint_missing", record_id + " lacks a checkpoint id"))
        _check_positive_requested_length(row, problems, record_id)
        _check_matched_schedule_row(row, problems, record_id)
    elif condition == "D1":
        if row["empirical_null_seed"] is not None or row["length_condition_seed"] is not None:
            problems.append(_problem("d1_seed_role_invalid", record_id + " uses a B1 length-control or B2 null seed"))
        if row["generation_seed"] is None:
            problems.append(_problem("d1_generation_seed_missing", record_id + " lacks a generation seed"))
        if not _nonempty_text(row["checkpoint_id"]):
            problems.append(_problem("checkpoint_missing", record_id + " lacks a checkpoint id"))
        if row["training_seed"] is not None and row["generation_chunk_id"] == str(row["training_seed"]):
            problems.append(_problem("chunk_id_collides_with_training_seed", record_id + " reuses the training seed as a chunk id"))
        _check_positive_requested_length(row, problems, record_id)
        _check_matched_schedule_row(row, problems, record_id)


def _one_record(record, index):
    problems = []
    prefix = "row %d" % index
    if not isinstance(record, dict):
        return [_problem("record_invalid", prefix + " is not an object")], None
    if "seed" in record:
        problems.append(_problem("ambiguous_seed_field", prefix + " uses a generic seed field"))
    unexpected = sorted(set(record) - set(RECORD_KEYS) - set(OPTIONAL_RECORD_FIELDS))
    if unexpected:
        problems.append(_problem("unexpected_field", prefix + " has " + ", ".join(unexpected)))
    missing = [key for key in RECORD_KEYS if key not in record]
    if missing:
        problems.append(_problem("record_field_missing", prefix + " lacks " + ", ".join(missing)))
        return problems, None
    record_id = record["record_id"]
    if not isinstance(record_id, str) or RECORD_ID_TEXT.fullmatch(record_id) is None:
        problems.append(_problem("record_id_invalid", prefix + " has an invalid record id"))
        record_id = prefix
    condition = _canonical_condition(record["condition"])
    if condition is None:
        problems.append(_problem("unknown_condition", record_id + " has an unknown condition"))
    if record["data_role"] == EVAL_ROLE:
        problems.append(_problem("eval_role_on_record", record_id + " declares EVAL"))
    elif record["data_role"] != SYNTHETIC_ROLE:
        problems.append(_problem("data_role_refused", record_id + " is not synthetic"))
    if condition is not None and record["length_regime"] != LENGTH_REGIMES[condition]:
        problems.append(_problem("length_regime_invalid", record_id + " length regime does not match its condition"))
    chunk = record["generation_chunk_id"]
    if chunk is not None and (not isinstance(chunk, str) or CHUNK_ID_TEXT.fullmatch(chunk) is None):
        problems.append(_problem("chunk_id_invalid", record_id + " chunk id is invalid"))
    if record["checkpoint_id"] is not None and not _nonempty_text(record["checkpoint_id"]):
        problems.append(_problem("checkpoint_invalid", record_id + " checkpoint id is blank"))
    if not _optional_sha256(record["checkpoint_sha256"]):
        problems.append(_problem("checkpoint_invalid", record_id + " checkpoint hash is not null or sha256"))
    if "source_artifact_sha256" in record and not _sha256_value(record["source_artifact_sha256"]):
        problems.append(_problem("source_artifact_sha256_invalid", record_id + " source artifact hash is not sha256"))
    if condition is not None:
        probe = dict(record)
        probe["condition"] = condition
        _check_seed_roles(probe, problems, record_id)
    _check_status_consistency(record, problems, record_id)
    _check_parser_classification(record, problems, record_id)
    if problems:
        return problems, None
    normalized = {key: record[key] for key in RECORD_KEYS}
    normalized["condition_label"] = record["condition"]
    normalized["condition"] = condition
    if "source_artifact_sha256" in record:
        normalized["source_artifact_sha256"] = record["source_artifact_sha256"]
    if "parse_outcome" in record:
        normalized["parse_outcome"] = record["parse_outcome"]
    if "failure_reason" in record:
        normalized["failure_reason"] = record["failure_reason"]
    return [], normalized


def validate_records(records):
    if not isinstance(records, list):
        raise GeneratorEvalContractError("record_contract_invalid", "records must be a list")
    problems = []
    normalized = []
    seen = set()
    for index, record in enumerate(records):
        row_problems, row = _one_record(record, index)
        problems.extend(row_problems)
        if row is None:
            continue
        if row["record_id"] in seen:
            problems.append(_problem("duplicate_record_id", row["record_id"] + " is duplicated"))
        else:
            seen.add(row["record_id"])
            normalized.append(row)
    seen_attempts = set()
    seen_positions = set()
    for row in normalized:
        if row["condition"] not in ("B1", "D1"):
            continue
        attempt_key = (row["condition"], row["training_seed"], row["original_attempt_index"])
        position_key = (row["condition"], row["training_seed"], row["invocation_index"], row["batch_position"])
        if attempt_key in seen_attempts:
            problems.append(_problem("duplicate_schedule_attempt", row["record_id"] + " repeats an original_attempt_index"))
        else:
            seen_attempts.add(attempt_key)
        if position_key in seen_positions:
            problems.append(_problem("duplicate_batch_position", row["record_id"] + " repeats a batch_position in one invocation"))
        else:
            seen_positions.add(position_key)
    b2_seeds = sorted({row["empirical_null_seed"] for row in normalized if row["condition"] == "B2"})
    if len(b2_seeds) > 1:
        problems.append(_problem("b2_multiple_seeds", "B2 has more than one empirical-null seed"))
    if any(item["code"] == "eval_role_on_record" for item in problems):
        raise GeneratorEvalContractError("eval_role_on_record", "a record declares EVAL", problems)
    if problems:
        raise GeneratorEvalContractError("record_contract_invalid", problems[0]["detail"], problems)
    return normalized


def _as_normalized(records):
    if records and isinstance(records[0], dict) and "condition_label" in records[0]:
        return records
    return validate_records(records)


def _provenance_token(value):
    return tuple(value[key] for key in LENGTH_SCHEDULE_PROVENANCE_KEYS)


def _position_token(row):
    return (
        row["original_attempt_index"],
        row["batch_position"],
        row["requested_target_length"],
        row["max_seq_len"],
    )


def _side_schedule(rows):
    reasons = []
    seeds = {row["invocation_seed"] for row in rows}
    provenances = {_provenance_token(row["length_schedule_provenance"]) for row in rows}
    by_attempt = {}
    for row in rows:
        by_attempt.setdefault(row["original_attempt_index"], set()).add(_position_token(row))
    if len(seeds) != 1:
        reasons.append("invocation_seed")
    if len(provenances) != 1:
        reasons.append("length_schedule_provenance")
    if any(len(tokens) != 1 for tokens in by_attempt.values()):
        reasons.append("requested_length_position_schedule")
    if len({row["requested_target_length"] for row in rows}) != 1:
        reasons.append("requested_length_position_schedule")
    if by_attempt and all(len(tokens) == 1 for tokens in by_attempt.values()):
        position_tokens = tuple(sorted(next(iter(tokens)) for tokens in by_attempt.values()))
    else:
        position_tokens = tuple(sorted({_position_token(row) for row in rows}))
    return {
        "reasons": sorted(set(reasons)),
        "invocation_seed": next(iter(seeds)) if len(seeds) == 1 else sorted(seeds),
        "provenance": next(iter(provenances)) if len(provenances) == 1 else None,
        "position_tokens": position_tokens,
        "batch_positions": sorted({row["batch_position"] for row in rows}),
        "requested_target_lengths": sorted({row["requested_target_length"] for row in rows}),
        "max_seq_len_values": sorted({row["max_seq_len"] for row in rows}),
        "generation_chunk_ids": sorted({row["generation_chunk_id"] for row in rows}),
        "training_seeds": sorted({row["training_seed"] for row in rows if row["training_seed"] is not None}),
    }


def _one_sided_block(side, index, view):
    return {
        "invocation_index": index,
        "side": side,
        "generation_chunk_ids": view["generation_chunk_ids"],
        "batch_positions": view["batch_positions"],
        "requested_target_lengths": view["requested_target_lengths"],
        "invocation_seed": view["invocation_seed"],
        "training_seeds": view["training_seeds"],
        "included_in_controlled_comparison": False,
        "descriptive_only": True,
        "is_training_replicate": False,
    }


def _compare_schedule_sides(index, left, right):
    reasons = list(left["reasons"]) + list(right["reasons"])
    if left["invocation_seed"] != right["invocation_seed"]:
        reasons.append("invocation_seed")
    if left["provenance"] != right["provenance"]:
        reasons.append("length_schedule_provenance")
    if left["position_tokens"] != right["position_tokens"]:
        reasons.append("requested_length_position_schedule")
    reasons = sorted(set(reasons))
    return {
        "invocation_index": index,
        "generation_chunk_ids": sorted(set(left["generation_chunk_ids"]) | set(right["generation_chunk_ids"])),
        "reasons": reasons,
        "compatible": not reasons,
        "included_in_controlled_comparison": not reasons,
        "is_training_replicate": False,
        "b1_invocation_seed": left["invocation_seed"],
        "d1_invocation_seed": right["invocation_seed"],
        "b1_batch_positions": left["batch_positions"],
        "d1_batch_positions": right["batch_positions"],
        "b1_requested_target_lengths": left["requested_target_lengths"],
        "d1_requested_target_lengths": right["requested_target_lengths"],
        "b1_max_seq_len_values": left["max_seq_len_values"],
        "d1_max_seq_len_values": right["max_seq_len_values"],
        "b1_training_seeds": left["training_seeds"],
        "d1_training_seeds": right["training_seeds"],
        "schedule_attempt_fields": list(SCHEDULE_ATTEMPT_FIELDS),
    }


def matched_schedule_structure(records):
    """Compare B1 and D1 by the implemented M4/M6 schedule fields.

    Equality of generation_chunk_id is not evidence of a match. One-sided
    invocations stay descriptive. No production schedule is loaded.
    """
    rows = _as_normalized(records)
    grouped = {"B1": {}, "D1": {}}
    for row in rows:
        if row["condition"] not in grouped or row["invocation_index"] is None:
            continue
        grouped[row["condition"]].setdefault(row["invocation_index"], []).append(row)
    indexes = sorted(set(grouped["B1"]) | set(grouped["D1"]))
    matched = []
    incompatible = []
    b1_only = []
    d1_only = []
    for index in indexes:
        left_rows = grouped["B1"].get(index, [])
        right_rows = grouped["D1"].get(index, [])
        if left_rows and not right_rows:
            b1_only.append(_one_sided_block("B1", index, _side_schedule(left_rows)))
            continue
        if right_rows and not left_rows:
            d1_only.append(_one_sided_block("D1", index, _side_schedule(right_rows)))
            continue
        block = _compare_schedule_sides(index, _side_schedule(left_rows), _side_schedule(right_rows))
        if block["compatible"]:
            matched.append(block)
        else:
            incompatible.append(block)
    return {
        "matched_schedule_blocks": matched,
        "incompatible_schedule_blocks": incompatible,
        "b1_only_schedule_blocks": b1_only,
        "d1_only_schedule_blocks": d1_only,
        "matched_invocation_indexes": [block["invocation_index"] for block in matched],
        "incompatible_invocation_indexes": [block["invocation_index"] for block in incompatible],
        "b1_only_invocation_indexes": [block["invocation_index"] for block in b1_only],
        "d1_only_invocation_indexes": [block["invocation_index"] for block in d1_only],
        "generation_chunk_label_is_sufficient_evidence": False,
        "schedule_blocks_are_training_replicates": False,
        "candidate_rows_are_training_replicates": False,
        "production_schedule_wired": False,
        "b0_in_matched_b1_d1_controlled_comparison": False,
        "b2_in_matched_b1_d1_controlled_comparison": False,
        "schedule_attempt_fields": list(SCHEDULE_ATTEMPT_FIELDS),
        "length_schedule_provenance_fields": list(LENGTH_SCHEDULE_PROVENANCE_KEYS),
        "chunk_identifier_meaning": (
            "A matched block requires the same invocation_index, batch_position, requested_target_length, "
            "max_seq_len, invocation_seed, and length-schedule provenance on B1 and D1. "
            "A shared generation_chunk_id is not sufficient. No production schedule was loaded."
        ),
    }


def d1_training_seed_summary(records):
    rows = records
    d1_rows = [row for row in rows if row["condition"] == "D1"]
    if not d1_rows:
        raise GeneratorEvalContractError("d1_rows_absent", "no D1 rows are available for a training-seed summary")
    if any(row["training_seed"] is None for row in d1_rows):
        raise GeneratorEvalContractError(
            "d1_training_seed_provenance_missing",
            "a D1 training-seed summary requires a true training seed on every D1 row",
        )
    seeds = sorted({row["training_seed"] for row in d1_rows})
    summary = {
        "status": "passed",
        "usable_training_seed_summary": True,
        "independent_training_replicate_unit": "training_seed",
        "d1_training_seeds": seeds,
        "d1_training_seed_count": len(seeds),
        "d1_row_count": len(d1_rows),
        "d1_chunk_count": len({row["generation_chunk_id"] for row in d1_rows if row["generation_chunk_id"] is not None}),
        "not_independent_training_replicates": list(NOT_TRAINING_REPLICATE_UNITS),
        "one_d1_training_seed_limitation": len(seeds) == 1,
        "uncertainty_excludes_training_run_variability": len(seeds) < 2,
    }
    if len(seeds) == 1:
        summary["status"] = "limitation"
        summary["statement"] = ONE_D1_SEED_STATEMENT
    else:
        summary["statement"] = (
            "More than one D1 training seed is present. GEP-1 does not compute a confidence interval. "
            "Candidate rows and generation chunks are not additional training replicates."
        )
    return summary


def assess_claim(records, claim):
    """Refuse replicate interpretations the design does not support."""
    rows = validate_records(records)
    if not isinstance(claim, dict) or not _nonempty_text(claim.get("kind")):
        raise GeneratorEvalContractError("claim_invalid", "the analysis claim is missing")
    kind = claim["kind"]
    if kind == CONTROLLED_COMPARISON_KIND:
        included = claim.get("include_conditions", ["B1", "D1"])
        if not isinstance(included, list):
            raise GeneratorEvalContractError("claim_invalid", "include_conditions must be a list")
        if "B0" in included:
            raise GeneratorEvalContractError(
                "b0_forbidden_in_matched_b1_d1_controlled_comparison",
                "B0 cannot be included in the matched B1/D1 controlled comparison",
            )
        if "B2" in included:
            raise GeneratorEvalContractError(
                "b2_forbidden_in_matched_b1_d1_controlled_comparison",
                "B2 cannot be included in the matched B1/D1 controlled comparison",
            )
        if len(included) != 2 or sorted(included) != ["B1", "D1"]:
            raise GeneratorEvalContractError(
                "controlled_comparison_conditions_invalid",
                "the matched controlled comparison contains exactly B1 and D1",
            )
        structure = matched_schedule_structure(rows)
        if structure["incompatible_schedule_blocks"]:
            first = structure["incompatible_schedule_blocks"][0]
            raise GeneratorEvalContractError(
                "matched_schedule_incompatible",
                "invocation_index %s is not a matched B1/D1 schedule (%s); a shared chunk label is not sufficient"
                % (first["invocation_index"], ", ".join(first["reasons"])),
                [
                    _problem(
                        "matched_schedule_incompatible",
                        "invocation_index %s: %s" % (block["invocation_index"], ", ".join(block["reasons"])),
                    )
                    for block in structure["incompatible_schedule_blocks"]
                ],
            )
        if not structure["matched_schedule_blocks"]:
            raise GeneratorEvalContractError(
                "matched_schedule_block_missing",
                "a controlled comparison requires at least one compatible shared schedule block",
            )
        structure["kind"] = CONTROLLED_COMPARISON_KIND
        structure["include_conditions"] = ["B1", "D1"]
        return structure
    if kind == "training_replicate_summary":
        condition = claim.get("condition")
        unit = claim.get("unit", "training_seed")
        seed_role = claim.get("seed_role", unit)
        if condition == "B0":
            raise GeneratorEvalContractError(
                "b0_unit_is_not_a_training_replicate",
                "B0 historical generation seeds, batches, and candidate rows are not independent training replicates",
            )
        if condition == "B2":
            raise GeneratorEvalContractError("b2_rows_are_not_training_replicates", "B2 rows are not training replicates")
        if condition == "B1" and seed_role == "length_condition_seed":
            raise GeneratorEvalContractError(
                "b1_length_condition_seed_is_not_a_training_replicate",
                "a B1 length-control seed is not a training replicate",
            )
        if condition == "B1":
            raise GeneratorEvalContractError("b1_rows_are_not_training_replicates", "B1 rows are not training replicates")
        if condition == "D1" and unit in NOT_TRAINING_REPLICATE_UNITS:
            raise GeneratorEvalContractError(
                "d1_unit_is_not_a_training_replicate",
                unit + " is not an independent D1 training replicate",
            )
        if condition == "D1" and unit == "training_seed":
            return d1_training_seed_summary(rows)
    raise GeneratorEvalContractError("claim_invalid", "the analysis claim is not recognised")


def _unlock_incomplete(record):
    if not isinstance(record, dict):
        return "unlock record is not an object"
    unexpected = sorted(set(record) - set(UNLOCK_KEYS))
    missing = [key for key in UNLOCK_KEYS if key not in record]
    if unexpected or missing:
        return "unlock record fields are incomplete"
    if not _nonempty_text(record["timestamp"]) or not _nonempty_text(record["operator"]) or not _nonempty_text(record["reviewer"]):
        return "timestamp, operator, or reviewer is blank"
    if not _nonempty_text(record["frozen_plan_identifier"]):
        return "frozen plan identifier is blank"
    hashes = record["corrected_role_hashes"]
    if not isinstance(hashes, dict) or set(hashes) != set(ROLE_HASH_KEYS) or any(not _sha256_value(hashes[key]) for key in ROLE_HASH_KEYS):
        return "corrected role hashes are incomplete"
    for key in ("m9a_artefact_references", "m9b_artefact_references"):
        values = record[key]
        if not isinstance(values, list) or not values or any(not _nonempty_text(item) for item in values):
            return key + " is incomplete"
    codes = record["m9c_code_configuration_hashes"]
    if not isinstance(codes, dict) or not codes or any(not _nonempty_text(key) or not _sha256_value(value) for key, value in codes.items()):
        return "M9C code and configuration hashes are incomplete"
    if type(record["unlock_assertion"]) is not bool:
        return "unlock assertion is not boolean"
    return None


def _binding_matches(record, expected):
    if not isinstance(expected, dict) or set(BINDING_KEYS) - set(expected):
        return False
    for key in BINDING_KEYS:
        if record[key] != expected[key]:
            return False
    return True


def evaluate_eval_gate(declared_role, mode=None, unlock_record=None, expected_binding=None, filename=None, opener=None):
    """Decide whether a load is permitted. This function never calls opener."""
    del opener
    if mode is None:
        mode = DEFAULT_MODE
    filename_hit = _forbidden_filename(filename)
    if declared_role == SYNTHETIC_ROLE:
        if filename_hit:
            raise GeneratorEvalContractError("filename_guard", "the filename is a held-out role file name")
        if mode != DEFAULT_MODE:
            raise GeneratorEvalContractError("synthetic_requires_preflight_mode", "synthetic loads stay in synthetic preflight mode")
        return {"permitted": True, "opened": False, "mode": DEFAULT_MODE, "declared_role": SYNTHETIC_ROLE}
    problems = []
    if filename_hit:
        problems.append(_problem("filename_guard", "the filename is a held-out role file name"))
    if declared_role in REFUSED_ROLES or declared_role != EVAL_ROLE:
        problems.append(_problem("data_role_refused", "GEP-1 refuses role %s" % declared_role))
        _raise_problems(problems)
    if mode != FROZEN_UNLOCKED_MODE:
        problems.append(_problem("eval_requires_frozen_unlocked_mode", "EVAL requires frozen unlocked mode"))
        _raise_problems(problems)
    if unlock_record is None:
        problems.append(_problem("unlock_record_absent", "the EVAL unlock record is absent"))
        _raise_problems(problems)
    incomplete = _unlock_incomplete(unlock_record)
    if incomplete:
        problems.append(_problem("unlock_record_incomplete", incomplete))
        _raise_problems(problems)
    if unlock_record["unlock_assertion"] is False:
        problems.append(_problem("unlock_assertion_false", "the unlock assertion is false"))
        _raise_problems(problems)
    if not _binding_matches(unlock_record, expected_binding):
        problems.append(_problem("unlock_record_mismatched", "the unlock record does not match the supplied binding"))
        _raise_problems(problems)
    problems.append(_problem("eval_load_not_wired_in_gep1", "GEP-1 does not open EVAL data"))
    _raise_problems(problems)


def _failure_reason_counts(rows):
    counts = {reason: 0 for reason in FAILURE_REASONS}
    for row in rows:
        reason = row.get("failure_reason")
        if reason in counts:
            counts[reason] += 1
    return counts


def _valid_canonical_sequence_count(rows):
    return sum(
        row.get("parse_outcome") == PARSE_OUTCOME_VALID and row.get("failure_reason") is None
        for row in rows
    )


def _accounting(rows, condition=None):
    attempted = len(rows)
    parsed = sum(row["parsed_status"] is True for row in rows)
    valid_rows = [row for row in rows if _row_is_valid(row)]
    valid_sequences = [row["sequence"] for row in valid_rows]
    valid = len(valid_rows)
    unique = len(set(valid_sequences))
    result = {
        "attempted": attempted,
        "parsed_status_true": parsed,
        "alphabet_valid": sum(row["alphabet_valid"] is True for row in rows),
        "valid_acgu": valid,
        "unique_valid": unique,
        "invalid": attempted - valid,
        "duplicates": valid - unique,
        "duplicate_excess": valid - unique,
        "empty_or_unparseable": sum((not _row_is_valid(row)) and row["sequence"] is None for row in rows),
        "largest_duplicate_multiplicity": _largest_multiplicity(valid_sequences),
        "multiplicity_histogram": _multiplicity_histogram(valid_sequences),
        "multiplicity_histogram_emits_sequence_strings": False,
        "multiplicity_histogram_emits_sequence_to_count_mapping": False,
        "failure_reason_counts": _failure_reason_counts(rows),
        "valid_canonical_sequence_count": _valid_canonical_sequence_count(rows),
        "failure_reason_counts_emit_sequence_strings": False,
    }
    if condition == "B0":
        result.update(
            {
                "exact_length_hits": None,
                "exact_hit_rate": None,
                "exact_hit_rate_denominator": None,
                "exact_hit_applicability": "not_applicable",
                "exact_hit_not_applicable_reason": B0_EXACT_HIT_NOT_APPLICABLE,
                "nominal_max_seq_len": B0_NOMINAL_MAX_SEQ_LEN if rows else None,
                "requested_length": "unavailable",
                "observed_cleaned_lengths": sorted({row["observed_length"] for row in valid_rows}),
            }
        )
        return result
    if condition is None:
        hit_rows = [row for row in rows if row["condition"] != "B0"]
        denominator_name = "attempted_rows_excluding_b0"
        denominator_count = len(hit_rows)
    else:
        hit_rows = rows
        denominator_name = "attempted_rows"
        denominator_count = attempted
    hits = sum(row["observed_length"] == row["requested_length"] for row in hit_rows if _row_is_valid(row))
    result.update(
        {
            "exact_length_hits": hits,
            "exact_hit_rate": 0.0 if denominator_count == 0 else hits / denominator_count,
            "exact_hit_rate_denominator": denominator_name,
            "exact_hit_applicability": "applicable",
        }
    )
    return result


def project_m4_attempt(row, index):
    """Project one synthetic B1 or D1 row onto the M4 ledger without inventing a seed."""
    if row["condition"] not in ("B1", "D1") or type(row["generation_seed"]) is not int:
        return None
    if row["parsed_status"] is True and isinstance(row["sequence"], str):
        cleaned = row["sequence"]
    else:
        cleaned = ""
    valid = _row_is_valid(row)
    requested = row["requested_target_length"]
    return {
        "original_attempt_index": row["original_attempt_index"],
        "invocation_index": row["invocation_index"],
        "batch_position": row["batch_position"],
        "requested_target_length": requested,
        "max_seq_len": row["max_seq_len"],
        "invocation_seed": row["invocation_seed"],
        "raw_decoded_text": cleaned,
        "raw_length": len(cleaned),
        "leading_boundary_marker_run": "",
        "trailing_boundary_marker_run": "",
        "cleaned_sequence": cleaned,
        "cleaned_length": len(cleaned),
        "validity": valid,
        "invalid_reason": None if valid else "synthetic_rejected",
        "eos_marker_observed": False,
        "early_eos": False,
        "exact_length_hit": bool(valid and len(cleaned) == requested),
        "length_delta": len(cleaned) - requested,
    }


def m4_reconciliation(rows):
    projected = []
    source_rows = []
    for row in sorted(rows, key=lambda item: item["record_id"]):
        attempt = project_m4_attempt(row, len(projected))
        if attempt is not None:
            projected.append(attempt)
            source_rows.append(row)
    if not projected:
        return {"status": "not_applicable", "projected_rows": 0}
    metrics = _load_module("m4_diagnostic_metrics.py", "gep1_m4_reconcile")
    summary = metrics.summarise_attempts(projected)
    contract = _accounting(source_rows)
    equal = (
        summary["raw_attempts"] == contract["attempted"]
        and summary["valid_outputs"] == contract["valid_acgu"]
        and summary["exact_length_hits"] == contract["exact_length_hits"]
        and summary["exact_hit_rate"] == contract["exact_hit_rate"]
    )
    return {
        "status": "matched" if equal else "failed",
        "projected_rows": len(projected),
        "m4_raw_attempts": summary["raw_attempts"],
        "m4_parsed_outputs": summary["parsed_outputs"],
        "m4_valid_outputs": summary["valid_outputs"],
        "m4_exact_length_hits": summary["exact_length_hits"],
        "m4_exact_hit_rate": summary["exact_hit_rate"],
        "contract_parsed_status_true": contract["parsed_status_true"],
        "rates_equal": equal,
        "projection_uses_row_schedule_fields": True,
    }


def _b0_provenance(rows):
    if not rows:
        return None
    return {
        "historical_generation_seeds": sorted({row["historical_generation_seed"] for row in rows}),
        "historical_batch_indexes": sorted({row["historical_batch_index"] for row in rows}),
        "historical_generation_seeds_are_training_replicates": False,
        "historical_batches_are_training_replicates": False,
        "candidate_rows_are_training_replicates": False,
        "nominal_max_seq_len": B0_NOMINAL_MAX_SEQ_LEN,
        "requested_length": "unavailable",
        "exact_hit_applicability": "not_applicable",
        "observed_cleaned_lengths": sorted({row["observed_length"] for row in rows if _row_is_valid(row)}),
    }


def _seed_structure(rows):
    d1 = [row for row in rows if row["condition"] == "D1"]
    b0_rows = [row for row in rows if row["condition"] == "B0"]
    present = sorted({row["training_seed"] for row in d1 if row["training_seed"] is not None})
    missing = sum(row["training_seed"] is None for row in d1)
    b2 = sorted({row["empirical_null_seed"] for row in rows if row["condition"] == "B2"})
    try:
        summary = d1_training_seed_summary(rows) if d1 and missing == 0 else None
    except GeneratorEvalContractError as exc:
        summary = {"status": "failed", "usable_training_seed_summary": False, "code": exc.code, "detail": exc.detail}
    if d1 and missing:
        summary = {
            "status": "failed",
            "usable_training_seed_summary": False,
            "code": "d1_training_seed_provenance_missing",
            "detail": "a D1 training-seed summary requires a true training seed on every D1 row",
            "d1_rows_missing_training_seed": missing,
        }
    return {
        "d1_training_seed_summary": summary,
        "d1_training_seeds_present": present,
        "d1_rows_missing_training_seed": missing,
        "one_d1_training_seed_limitation": bool(summary and summary.get("one_d1_training_seed_limitation") is True),
        "b1_length_condition_seeds": sorted({row["length_condition_seed"] for row in rows if row["condition"] == "B1" and row["length_condition_seed"] is not None}),
        "b1_length_condition_seeds_are_training_replicates": False,
        "b2_empirical_null_seeds": b2,
        "b2_rows_are_training_replicates": False,
        "b0_historical_generation_provenance": _b0_provenance(b0_rows),
    }


def run_preflight(records, metadata=None, mode=None):
    if mode is None:
        mode = DEFAULT_MODE
    evaluate_eval_gate(SYNTHETIC_ROLE, mode=mode)
    spec = load_metric_spec()
    rows = validate_records(records)
    if metadata is None:
        metadata = {}
    namespace = metadata.get("chunk_id_namespace")
    if namespace not in (None, SYNTHETIC_CHUNK_NAMESPACE):
        raise GeneratorEvalContractError("chunk_namespace_unrecognised", "the chunk namespace is not the synthetic stand-in")
    accounting = {
        condition: _accounting([row for row in rows if row["condition"] == condition], condition) for condition in CONDITIONS
    }
    overall = _accounting(rows)
    seeds = _seed_structure(rows)
    chunks = matched_schedule_structure(rows)
    reconciliation = m4_reconciliation(rows)
    unresolved_items = [item for item in spec["blocking_items"] if item.get("status") == "unresolved"]
    resolved_items = [item for item in spec["blocking_items"] if item.get("status") == "resolved"]
    classification = blocker_classification()
    warnings = []
    if namespace is None:
        warnings.append("chunk_id_namespace_unspecified: matched ids are not a loaded production schedule")
    if not rows:
        warnings.append("no_synthetic_records")
    if rows and overall["valid_acgu"] == 0:
        warnings.append("no_valid_acgu_outputs")
    errors = []
    summary = seeds["d1_training_seed_summary"]
    if summary and summary.get("status") == "failed":
        errors.append({"code": summary["code"], "detail": summary["detail"]})
    if reconciliation["status"] == "failed":
        errors.append({"code": "m4_reconciliation_failed", "detail": "synthetic accounting drifted from summarise_attempts"})
    for block in chunks["incompatible_schedule_blocks"]:
        errors.append(
            {
                "code": "matched_schedule_incompatible",
                "detail": "invocation_index %s is not a matched schedule (%s); a shared chunk label is not sufficient"
                % (block["invocation_index"], ", ".join(block["reasons"])),
            }
        )
    limitation = seeds["one_d1_training_seed_limitation"] or not rows or (bool(rows) and overall["valid_acgu"] == 0)
    if errors:
        status = "failed"
    elif limitation:
        status = "passed_with_limitations"
    else:
        status = "passed"
    b0_rows = [row for row in rows if row["condition"] == "B0"]
    b0_provenance = seeds["b0_historical_generation_provenance"]
    head = _git_text(["rev-parse", "HEAD"])
    branch = _git_text(["rev-parse", "--abbrev-ref", "HEAD"])
    return {
        "schema_version": SCHEMA_VERSION,
        "package_id": PACKAGE_ID,
        "status": status,
        "mode": DEFAULT_MODE,
        "package_revision": {
            "git_head": head,
            "git_branch": branch,
            "preflight_module_sha256": _sha256_file(os.path.abspath(__file__)),
            "metric_spec_sha256": _sha256_file(spec_path()),
            "metric_spec_schema_version": spec["schema_version"],
            "governing_plan": {"path": GOVERNING_PLAN_RELATIVE, "sha256": _hash_revision_path(GOVERNING_PLAN_RELATIVE), "version": GOVERNING_PLAN_VERSION, "revision_date": GOVERNING_PLAN_REVISION_DATE},
            "historical_m9c_plan": {
                "path": HISTORICAL_M9C_PLAN_RELATIVE,
                "sha256": _hash_revision_path(HISTORICAL_M9C_PLAN_RELATIVE),
                "version": HISTORICAL_M9C_PLAN_VERSION,
                "revision_date": HISTORICAL_M9C_PLAN_REVISION_DATE,
                "role": "m9c_frozen_historical",
            },
            "m4_diagnostic_metrics": {"path": M4_METRICS_RELATIVE, "sha256": _hash_revision_path(M4_METRICS_RELATIVE)},
            "m6_diagnostic_generation": {"path": M6_DIAGNOSTIC_RELATIVE, "sha256": _hash_revision_path(M6_DIAGNOSTIC_RELATIVE)},
            "validation_metrics_config": {"path": METRICS_CONFIG_RELATIVE, "sha256": _hash_revision_path(METRICS_CONFIG_RELATIVE)},
        },
        "metric_spec_validation_status": (
            "valid_frozen"
            if spec.get("freeze_status") == "frozen" and not unresolved_items
            else "valid_draft"
            if not unresolved_items
            else "valid_draft_with_unresolved_items"
        ),
        "metric_spec_freeze_status": spec.get("freeze_status"),
        "metric_spec_production_ready": spec.get("m10_draft_contract", {}).get("labelled_production_ready") is True,
        "m10_blocking_dispositions": dict(M10_BLOCKING_DISPOSITIONS),
        "blocker_classification": classification,
        "active_implementation_blockers": [],
        "implemented_awaiting_authorization": [
            entry["id"] for entry in classification["implemented_awaiting_authorization"]
        ],
        "required_implementation_work": [
            {"id": item_id, "status": "required"} for item_id in REQUIRED_IMPLEMENTATION_IDS
        ],
        "metric_count": len(spec["metrics"]),
        "metric_ids": [metric["metric_id"] for metric in spec["metrics"]],
        "unresolved_item_count": len(unresolved_items),
        "resolved_item_ids": [item["id"] for item in resolved_items],
        "eval_access": "locked",
        "aggregate_generator_quality_score": False,
        "synthetic_input_counts_by_condition": {condition: accounting[condition]["attempted"] for condition in CONDITIONS},
        "accounting_by_condition": accounting,
        "accounting_overall": overall,
        "seed_structure": {
            "d1_training_seeds_present": seeds["d1_training_seeds_present"],
            "d1_rows_missing_training_seed": seeds["d1_rows_missing_training_seed"],
            "b1_length_condition_seeds": seeds["b1_length_condition_seeds"],
            "b1_length_condition_seeds_are_training_replicates": False,
            "b2_empirical_null_seeds": seeds["b2_empirical_null_seeds"],
            "b2_rows_are_training_replicates": False,
            "b0_historical_generation_provenance": b0_provenance,
        },
        "d1_training_seed_summary": summary,
        "one_d1_training_seed_limitation": seeds["one_d1_training_seed_limitation"],
        "one_d1_training_seed_limitation_statement": ONE_D1_SEED_STATEMENT if seeds["one_d1_training_seed_limitation"] else None,
        "matched_b1_d1_schedule": chunks,
        "b0_external_comparator": bool(b0_rows),
        "b0_included_in_matched_b1_d1_controlled_comparison": False,
        "b0_length_regime": "historical_37nt" if b0_rows else None,
        "b0_nominal_max_seq_len": B0_NOMINAL_MAX_SEQ_LEN if b0_rows else None,
        "b0_requested_length_status": "unavailable" if b0_rows else None,
        "b0_exact_hit_applicability": "not_applicable" if b0_rows else None,
        "b0_observed_cleaned_lengths": None if b0_provenance is None else b0_provenance["observed_cleaned_lengths"],
        "b0_historical_generation_seeds_are_training_replicates": None if b0_provenance is None else False,
        "b0_historical_batches_are_training_replicates": None if b0_provenance is None else False,
        "b0_candidate_rows_are_training_replicates": None if b0_provenance is None else False,
        "m4_reconciliation": reconciliation,
        "chunk_id_namespace": namespace,
        "warnings": warnings,
        "errors": errors,
        "no_eval_data_loaded": True,
        "no_eval_statement": NO_EVAL_STATEMENT,
        "no_ref_or_validation_data_loaded": True,
        "no_ref_or_validation_statement": NO_REF_VALIDATION_STATEMENT,
        "train_reference_loaded": False,
        "structure_metrics_executed": False,
        "production_pools_loaded": False,
    }


def render_preflight_text(report):
    lines = [
        "GEP-2 synthetic generator-evaluation preflight",
        "status: " + report["status"],
        "mode: " + report["mode"],
        "EVAL access: locked",
        "only synthetic TRAIN/reference fixtures used",
        "no EVAL, REF or VALIDATION data loaded",
        "git_head: " + report["package_revision"]["git_head"],
        "git_branch: " + report["package_revision"]["git_branch"],
        "preflight_module_sha256: " + report["package_revision"]["preflight_module_sha256"],
        "metric_spec_sha256: " + report["package_revision"]["metric_spec_sha256"],
        "metric_spec_validation_status: " + report["metric_spec_validation_status"],
        "metric_count: %d" % report["metric_count"],
        "unresolved_item_count: %d" % report["unresolved_item_count"],
        report["no_eval_statement"],
        report["no_ref_or_validation_statement"],
        "synthetic_input_counts_by_condition:",
    ]
    for condition in CONDITIONS:
        counts = report["accounting_by_condition"][condition]
        if counts["exact_hit_applicability"] == "not_applicable":
            exact_hits = "not_applicable"
        else:
            exact_hits = str(counts["exact_length_hits"])
        lines.append(
            "  %s: attempted=%d parsed_status_true=%d valid_acgu=%d unique_valid=%d exact_length_hits=%s"
            % (
                condition,
                counts["attempted"],
                counts["parsed_status_true"],
                counts["valid_acgu"],
                counts["unique_valid"],
                exact_hits,
            )
        )
    overall = report["accounting_overall"]
    lines.append(
        "overall: attempted=%d parsed_status_true=%d valid_acgu=%d unique_valid=%d"
        % (overall["attempted"], overall["parsed_status_true"], overall["valid_acgu"], overall["unique_valid"])
    )
    lines.append("failure_reason_counts: " + json.dumps(overall["failure_reason_counts"], sort_keys=True))
    lines.append("valid_canonical_sequence_count: %d" % overall["valid_canonical_sequence_count"])
    lines.append("failure_reason_counts_emit_sequence_strings: false")
    lines.append("d1_training_seeds: " + json.dumps(report["seed_structure"]["d1_training_seeds_present"]))
    lines.append("one_d1_training_seed_limitation: " + json.dumps(report["one_d1_training_seed_limitation"]))
    if report["one_d1_training_seed_limitation_statement"]:
        lines.append(report["one_d1_training_seed_limitation_statement"])
    lines.append("b2_empirical_null_seeds: " + json.dumps(report["seed_structure"]["b2_empirical_null_seeds"]))
    lines.append("b2_rows_are_training_replicates: false")
    lines.append("b1_length_condition_seeds_are_training_replicates: false")
    chunks = report["matched_b1_d1_schedule"]
    lines.append("matched_invocation_indexes: " + json.dumps(chunks["matched_invocation_indexes"]))
    lines.append("incompatible_invocation_indexes: " + json.dumps(chunks["incompatible_invocation_indexes"]))
    lines.append("b1_only_invocation_indexes: " + json.dumps(chunks["b1_only_invocation_indexes"]))
    lines.append("d1_only_invocation_indexes: " + json.dumps(chunks["d1_only_invocation_indexes"]))
    lines.append("generation_chunk_label_is_sufficient_evidence: false")
    lines.append("schedule_blocks_are_training_replicates: false")
    lines.append(chunks["chunk_identifier_meaning"])
    lines.append("b0_external_comparator: " + json.dumps(report["b0_external_comparator"]))
    lines.append("b0_included_in_matched_b1_d1_controlled_comparison: false")
    lines.append("b0_length_regime: " + json.dumps(report["b0_length_regime"]))
    lines.append("b0_nominal_max_seq_len: " + json.dumps(report["b0_nominal_max_seq_len"]))
    lines.append("b0_requested_length_status: " + json.dumps(report["b0_requested_length_status"]))
    lines.append("b0_exact_hit_applicability: " + json.dumps(report["b0_exact_hit_applicability"]))
    lines.append("b0_observed_cleaned_lengths: " + json.dumps(report["b0_observed_cleaned_lengths"]))
    lines.append("b0_historical_generation_seeds_are_training_replicates: " + json.dumps(report["b0_historical_generation_seeds_are_training_replicates"]))
    lines.append("m4_reconciliation: " + report["m4_reconciliation"]["status"])
    lines.append("resolved_items:")
    for item_id in report["resolved_item_ids"]:
        lines.append("  resolved: " + item_id)
    lines.append("blocker_classification:")
    for group_name, _entries in BLOCKER_CLASSIFICATION_GROUPS:
        lines.append("  " + group_name + ":")
        for entry in report["blocker_classification"][group_name]:
            lines.append("    %s [%s]: %s" % (entry["id"], entry["m10_disposition"], entry["subject"]))
    lines.append("active_implementation_blockers: " + json.dumps(report["active_implementation_blockers"]))
    lines.append(
        "implemented_awaiting_authorization: " + json.dumps(report["implemented_awaiting_authorization"])
    )
    lines.append("warnings: %d" % len(report["warnings"]))
    for warning in report["warnings"]:
        lines.append("  warning: " + warning)
    lines.append("errors: %d" % len(report["errors"]))
    for error in report["errors"]:
        lines.append("  error: %s: %s" % (error["code"], error["detail"]))
    lines.append(report["no_eval_statement"])
    return "\n".join(lines) + "\n"


def _validate_m8_contract_blocks(spec, problems):
    identity = spec.get("attempt_identity")
    if identity != {
        "canonical_attempt_id": "record_id",
        "derived_row_source_hash_field": "source_artifact_sha256",
        "second_attempt_id_field": False,
    }:
        problems.append(_problem("attempt_identity_invalid", "record_id remains the only attempt identifier"))
    provenance = spec.get("provenance_manifest_contract")
    expected_provenance = {
        "synthetic_only": True,
        "production_m8_reader": False,
        "source_manifest_schema": SOURCE_MANIFEST_SCHEMA,
        "derived_provenance_schema": DERIVED_PROVENANCE_SCHEMA,
        "source_manifest_inputs": {
            "required": list(SOURCE_MANIFEST_REQUIRED),
            "optional": list(SOURCE_MANIFEST_OPTIONAL),
            "requires_derived_ledger_sha256_before_parse": False,
        },
        "derived_provenance_outputs": list(DERIVED_PROVENANCE_FIELDS),
        "replenishment_prohibited_statement": REPLENISHMENT_PROHIBITED_STATEMENT,
        "parser_adapter_version": SYNTHETIC_PARSER_ADAPTER_VERSION,
    }
    if provenance != expected_provenance:
        problems.append(_problem("provenance_contract_invalid", "the synthetic provenance manifest contract drifted"))
    parser_contract = spec.get("parser_outcome_contract")
    if parser_contract != {
        "parse_outcome_field": "parse_outcome",
        "failure_reason_field": "failure_reason",
        "parse_outcomes": list(PARSE_OUTCOMES),
        "failure_reasons": list(FAILURE_REASONS),
        "valid_failure_reason": None,
        "sequence_null_outcomes": list(SEQUENCE_NULL_PARSE_OUTCOMES),
        "sequence_retained_when_biologically_invalid": PARSE_OUTCOME_NON_ACGU,
    }:
        problems.append(_problem("parser_outcome_contract_invalid", "the parser outcome vocabulary drifted"))
    histogram = spec.get("multiplicity_histogram")
    if not isinstance(histogram, dict) or histogram.get("implementation_symbol") != "generator_eval_analysis.multiplicity_histogram":
        problems.append(_problem("multiplicity_histogram_invalid", "the multiplicity histogram is not the analysis implementation"))
    elif histogram.get("emits_sequence_strings") is not False or histogram.get("emits_sequence_to_count_mapping") is not False:
        problems.append(_problem("multiplicity_histogram_invalid", "the multiplicity histogram must not emit sequences"))
    elif histogram.get("unique_only_replaces_primary") is not False:
        problems.append(_problem("multiplicity_histogram_invalid", "unique-only analysis must not replace the primary grain"))
    elif not _analysis_implements(histogram.get("implementation_symbol")):
        problems.append(_problem("implementation_missing", "multiplicity_histogram has no analysis implementation"))
    pooling = spec.get("d1_valid_conditional_pooling")
    if pooling != {
        "mode": POOLING_POLICY_EQUAL,
        "requires_verified_provenance": True,
        "hard_coded_training_seed_labels": False,
        "applied_to_raw_counts": False,
        "applied_to_global_duplicate_accounting": False,
        "is_confidence_interval": False,
        "concatenated_rows_are_the_equal_mixture": False,
        "pooled_directional_consistency_uses_concatenated_d1_fallback": False,
        "weighted_quantile_rule": "inclusive_cumulative_weight_exact_v2",
        "composition_mixture": "equal_seed_frequency_mixture_before_comparison",
        "missing_seed_policy": "null_with_explicit_reason_do_not_drop_seed",
    }:
        problems.append(_problem("d1_pooling_contract_invalid", "D1 valid-conditional pooling is not the verified equal-seed mixture"))
    analysis = _load_module("generator_eval_analysis.py", "gep1_analysis_for_d1_inventory")
    if spec.get("d1_metric_aggregation") != list(analysis.D1_METRIC_AGGREGATION):
        problems.append(_problem("d1_pooling_contract_invalid", "the D1 metric aggregation inventory drifted"))
    adapter = spec.get("b0_format_adapter")
    if adapter != {
        "synthetic_contract_only": True,
        "production_schema_encoded": False,
        "requested_length": "unavailable",
        "uses_shared_biological_validity": True,
        "included_in_b1_d1_controlled_comparison": False,
    }:
        problems.append(_problem("b0_adapter_contract_invalid", "the B0 adapter contract drifted"))
    viennarna = spec.get("viennarna_production_settings")
    if viennarna != {
        "pinned": True,
        "settings_invented": False,
        "method_changed": False,
        "blocking_item_id": "viennarna_production_settings_not_pinned",
        "implementation_path": "scripts/modelling/m6_diagnostic_generation.py",
        "implementation_symbol": "_default_fold",
        "call": "RNA.fold(sequence)",
        "model_details_set_by_code": False,
        "interpreter": "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python",
        "package_name": "viennarna",
        "package_version": "2.7.0",
        "package_build": "py38pl5321hd78456e_0",
        "package_channel": "bioconda",
        "distinct_from_aptarank_viennarna": "2.7.2",
        "observed_rna_md_defaults": {
            "temperature_centigrade": 37.0,
            "dangles": 2,
            "salt_monovalent_molar": 1.021,
            "uniq_ML": 0,
            "noLP": 0,
            "noGU": 0,
            "noGUclosure": 0,
            "gquad": 0,
            "special_hp": 1,
            "energy_set": 0,
            "min_loop_size": 3,
            "circ": 0,
            "logML": 0,
            "betaScale": 1.0,
            "max_bp_span": -1,
        },
        "unlisted_model_fields": "remaining RNA.md() fields stay at the ViennaRNA 2.7.0 constructor defaults and are not overridden",
    }:
        problems.append(_problem("viennarna_settings_invalid", "production ViennaRNA settings do not match the pinned RNA.fold defaults"))


def biological_validity(text):
    """Shared nonempty canonical A/C/G/U check for B0, B1, B2, and D1."""
    metrics = _load_module("m4_diagnostic_metrics.py", "gep1_m4_biological_validity")
    return metrics.recomputed_validity(text)


def _unparsed_biological_result(outcome):
    return {
        "sequence": None,
        "parsed_status": False,
        "alphabet_valid": False,
        "cleaning_status": "not_applicable",
        "cleaning_version": None,
        "observed_length": None,
        "biological_validity": False,
        "parse_outcome": outcome,
        "failure_reason": outcome,
    }


def assign_biological_parse(raw_text):
    """Classify one source payload. Non-sequences stay in the attempt ledger.

    A list, object, number, or boolean is an accounted non-sequence output.
    It does not abort the rest of the bundle. Valid rows have a null failure
    reason. A parsed non-ACGU string remains in the restricted ledger.
    """
    if raw_text is None:
        return _unparsed_biological_result(PARSE_OUTCOME_UNPARSEABLE)
    if raw_text == "":
        return _unparsed_biological_result(PARSE_OUTCOME_EMPTY)
    if type(raw_text) is not str:
        return _unparsed_biological_result(PARSE_OUTCOME_NON_SEQUENCE)
    valid = biological_validity(raw_text)
    if valid:
        return {
            "sequence": raw_text,
            "parsed_status": True,
            "alphabet_valid": True,
            "cleaning_status": "cleaned",
            "cleaning_version": SYNTHETIC_PARSER_ADAPTER_VERSION,
            "observed_length": len(raw_text),
            "biological_validity": True,
            "parse_outcome": PARSE_OUTCOME_VALID,
            "failure_reason": None,
        }
    return {
        "sequence": raw_text,
        "parsed_status": True,
        "alphabet_valid": False,
        "cleaning_status": "rejected",
        "cleaning_version": SYNTHETIC_PARSER_ADAPTER_VERSION,
        "observed_length": len(raw_text),
        "biological_validity": False,
        "parse_outcome": PARSE_OUTCOME_NON_ACGU,
        "failure_reason": PARSE_OUTCOME_NON_ACGU,
    }


def _write_parse(row, parsed):
    row["sequence"] = parsed["sequence"]
    row["parsed_status"] = parsed["parsed_status"]
    row["alphabet_valid"] = parsed["alphabet_valid"]
    row["cleaning_status"] = parsed["cleaning_status"]
    row["cleaning_version"] = parsed["cleaning_version"]
    row["observed_length"] = parsed["observed_length"]
    row["parse_outcome"] = parsed["parse_outcome"]
    row["failure_reason"] = parsed["failure_reason"]
    return row


def _multiplicity_histogram(sequences):
    module = _load_module("generator_eval_analysis.py", "gep1_analysis_histogram")
    return module.multiplicity_histogram(sequences)


def _largest_multiplicity(sequences):
    histogram = _multiplicity_histogram(sequences)
    if not histogram:
        return 0
    return max(item["multiplicity"] for item in histogram)


def _exact_keys(value, expected):
    if not isinstance(value, dict):
        return False
    for key in expected:
        if key not in value:
            return False
    for key in value:
        if key not in expected:
            return False
    return True


def _nonnegative_int(value):
    return type(value) is int and value >= 0


def validate_provenance_manifest(manifest):
    """Check source-manifest types before any attempt set, sort, join, or count.

    The first parse does not require a derived-ledger hash. An optional
    expected_derived_ledger_sha256 is accepted only for a later replay.
    This accepts only the synthetic manifest. It does not open a production file.
    """
    problems = []
    if not isinstance(manifest, dict):
        raise GeneratorEvalContractError("provenance_type_invalid", "the provenance manifest is not an object")
    for key in SOURCE_MANIFEST_REQUIRED:
        if key not in manifest:
            problems.append(_problem("provenance_type_invalid", "the provenance manifest lacks " + key))
    for key in manifest:
        if key not in SOURCE_MANIFEST_REQUIRED and key not in SOURCE_MANIFEST_OPTIONAL:
            problems.append(_problem("provenance_type_invalid", "the provenance manifest has unexpected field " + str(key)))
    if problems:
        _raise_problems(problems)
    source_id = manifest["source_artifact_id"]
    if type(source_id) is not str or source_id.strip() == "":
        problems.append(_problem("provenance_type_invalid", "source_artifact_id is not text"))
    elif _forbidden_filename(source_id):
        problems.append(_problem("filename_guard", "the source artifact identifier is a held-out role file name"))
    source_hash = manifest["source_artifact_sha256"]
    if type(source_hash) is not str:
        problems.append(_problem("provenance_type_invalid", "source_artifact_sha256 is not text"))
    elif not _sha256_value(source_hash):
        problems.append(_problem("provenance_sha256_invalid", "source_artifact_sha256 is not lowercase sha256"))
    if not _nonnegative_int(manifest["source_byte_size"]):
        problems.append(_problem("provenance_type_invalid", "source_byte_size is not a nonnegative integer"))
    version = manifest["parser_adapter_version"]
    if type(version) is not str or version.strip() == "":
        problems.append(_problem("provenance_type_invalid", "parser_adapter_version is not text"))
    elif version != SYNTHETIC_PARSER_ADAPTER_VERSION:
        problems.append(_problem("parser_adapter_version_invalid", "the parser version is not the synthetic adapter"))
    statement = manifest["replenishment_prohibited"]
    if type(statement) is not str:
        problems.append(_problem("provenance_type_invalid", "replenishment_prohibited is not the required statement"))
    elif statement != REPLENISHMENT_PROHIBITED_STATEMENT:
        problems.append(_problem("replenishment_statement_invalid", "replenishment is not explicitly prohibited"))
    normalized = {
        "source_artifact_id": source_id if type(source_id) is str else None,
        "source_artifact_sha256": source_hash if type(source_hash) is str else None,
        "source_byte_size": manifest["source_byte_size"],
        "parser_adapter_version": version if type(version) is str else None,
        "replenishment_prohibited": statement if type(statement) is str else None,
    }
    if "expected_attempt_count" in manifest:
        expected = manifest["expected_attempt_count"]
        if not _nonnegative_int(expected):
            problems.append(_problem("provenance_type_invalid", "expected_attempt_count is not a nonnegative integer"))
        else:
            normalized["expected_attempt_count"] = expected
    if "expected_derived_ledger_sha256" in manifest:
        expected_hash = manifest["expected_derived_ledger_sha256"]
        if type(expected_hash) is not str:
            problems.append(_problem("provenance_type_invalid", "expected_derived_ledger_sha256 is not text"))
        elif not _sha256_value(expected_hash):
            problems.append(_problem("provenance_sha256_invalid", "expected_derived_ledger_sha256 is not lowercase sha256"))
        else:
            normalized["expected_derived_ledger_sha256"] = expected_hash
    _raise_problems(problems)
    return normalized


def validate_d1_pooling_provenance(provenance):
    """Type-check the pooling declaration before seed sets or weight arithmetic."""
    if not isinstance(provenance, dict) or not _exact_keys(provenance, D1_POOLING_KEYS):
        raise GeneratorEvalContractError("pooling_type_invalid", "D1 pooling provenance fields are not the synthetic contract")
    policy = provenance["pooling_policy"]
    verified = provenance["policy_verified"]
    seeds = provenance["participating_training_seeds"]
    if type(policy) is not str or policy not in (POOLING_POLICY_EQUAL, POOLING_POLICY_UNVERIFIED):
        raise GeneratorEvalContractError("pooling_type_invalid", "pooling_policy is not text from the synthetic contract")
    if type(verified) is not bool:
        raise GeneratorEvalContractError("pooling_type_invalid", "policy_verified is not a boolean")
    if type(seeds) is not list:
        raise GeneratorEvalContractError("pooling_type_invalid", "participating_training_seeds is not a list")
    for seed in seeds:
        if not _nonnegative_int(seed):
            raise GeneratorEvalContractError("pooling_type_invalid", "a participating training seed is not a nonnegative integer")
    seen = []
    seen_set = set()
    for seed in seeds:
        if seed in seen_set:
            raise GeneratorEvalContractError("pooling_seed_duplicated", "a participating training seed is duplicated")
        seen_set.add(seed)
        seen.append(seed)
    if verified is True and (policy != POOLING_POLICY_EQUAL or not seen):
        raise GeneratorEvalContractError("pooling_policy_not_verified", "equal-seed pooling was marked verified without the mixture policy")
    if policy == POOLING_POLICY_EQUAL and verified is not True:
        return {
            "pooling_policy": policy,
            "policy_verified": False,
            "participating_training_seeds": seen,
            "status": "unavailable",
            "unavailable_reason": "pooling_policy_not_verified",
        }
    if policy != POOLING_POLICY_EQUAL or verified is not True:
        return {
            "pooling_policy": policy,
            "policy_verified": False,
            "participating_training_seeds": seen,
            "status": "unavailable",
            "unavailable_reason": "pooling_policy_not_verified",
        }
    return {
        "pooling_policy": policy,
        "policy_verified": True,
        "participating_training_seeds": seen,
        "status": "verified",
        "unavailable_reason": None,
    }


def _blank_canonical_row(record_id, condition):
    row = {key: None for key in RECORD_KEYS}
    row["record_id"] = record_id
    row["condition"] = condition
    row["data_role"] = SYNTHETIC_ROLE
    row["length_regime"] = LENGTH_REGIMES[condition]
    return row


def adapt_synthetic_b0_source(source, source_artifact_sha256):
    """Map one synthetic historical B0 source row onto the canonical attempt schema.

    The source schema is a documented synthetic contract. It is not a production
    B0 file format. Requested biological length stays unavailable.
    """
    if type(source_artifact_sha256) is not str or not _sha256_value(source_artifact_sha256):
        raise GeneratorEvalContractError("provenance_sha256_invalid", "the B0 source artifact hash is not sha256")
    if not isinstance(source, dict) or not _exact_keys(source, SYNTHETIC_B0_SOURCE_KEYS):
        raise GeneratorEvalContractError("b0_source_invalid", "the synthetic B0 source fields are not the documented adapter contract")
    record_id = source["record_id"]
    if type(record_id) is not str or RECORD_ID_TEXT.fullmatch(record_id) is None:
        raise GeneratorEvalContractError("record_id_invalid", "the B0 source attempt id is invalid")
    if "attempt_id" in source:
        raise GeneratorEvalContractError("synonymous_attempt_id_forbidden", "record_id is the only attempt identifier")
    historical_text = source["historical_text"]
    seed = source["historical_generation_seed"]
    batch = source["historical_batch_index"]
    nominal = source["nominal_max_seq_len"]
    checkpoint_id = source["checkpoint_id"]
    if not _nonnegative_int(seed) or not _nonnegative_int(batch):
        raise GeneratorEvalContractError("attempt_type_invalid", "B0 historical seed provenance is not a nonnegative integer")
    if type(nominal) is not int or nominal != B0_NOMINAL_MAX_SEQ_LEN:
        raise GeneratorEvalContractError("b0_nominal_max_seq_len_invalid", "synthetic B0 nominal max_seq_len is not 37")
    if type(checkpoint_id) is not str or checkpoint_id.strip() == "":
        raise GeneratorEvalContractError("attempt_type_invalid", "synthetic B0 checkpoint id is not text")
    parsed = assign_biological_parse(historical_text)
    row = _blank_canonical_row(record_id, "B0")
    row["checkpoint_id"] = checkpoint_id
    row["historical_generation_seed"] = seed
    row["historical_batch_index"] = batch
    row["nominal_max_seq_len"] = nominal
    row["requested_length"] = None
    row["requested_target_length"] = None
    _write_parse(row, parsed)
    row["source_artifact_sha256"] = source_artifact_sha256
    return row


def _controlled_row(condition, source, source_artifact_sha256):
    expected = SYNTHETIC_SOURCE_KEYS[condition]
    if not isinstance(source, dict) or not _exact_keys(source, expected):
        raise GeneratorEvalContractError("attempt_type_invalid", condition + " synthetic source fields are not the documented contract")
    if "attempt_id" in source:
        raise GeneratorEvalContractError("synonymous_attempt_id_forbidden", "record_id is the only attempt identifier")
    record_id = source["record_id"]
    if type(record_id) is not str or RECORD_ID_TEXT.fullmatch(record_id) is None:
        raise GeneratorEvalContractError("record_id_invalid", condition + " source attempt id is invalid")
    raw_text = source["raw_text"]
    parsed = assign_biological_parse(raw_text)
    row = _blank_canonical_row(record_id, condition)
    for key in expected:
        if key in ("record_id", "raw_text"):
            continue
        row[key] = source[key]
    _write_parse(row, parsed)
    row["source_artifact_sha256"] = source_artifact_sha256
    if condition == "B1":
        row["training_seed"] = None
        row["empirical_null_seed"] = None
    elif condition == "B2":
        row["training_seed"] = None
        row["generation_seed"] = None
        row["length_sampling_seed"] = None
        row["length_condition_seed"] = None
    elif condition == "D1":
        row["length_condition_seed"] = None
        row["empirical_null_seed"] = None
    return row


def _typecheck_attempt_identities(attempts):
    """Validate attempt-id text before any id set, sort, or join."""
    identities = []
    for index, attempt in enumerate(attempts):
        if not isinstance(attempt, dict):
            raise GeneratorEvalContractError("attempt_type_invalid", "attempt %d is not an object" % index)
        if "attempt_id" in attempt:
            raise GeneratorEvalContractError("synonymous_attempt_id_forbidden", "record_id is the only attempt identifier")
        record_id = attempt.get("record_id")
        if type(record_id) is not str or RECORD_ID_TEXT.fullmatch(record_id) is None:
            raise GeneratorEvalContractError("record_id_invalid", "attempt %d has an invalid record id" % index)
        identities.append(record_id)
    return identities


def assert_derived_attempt_identity(source_ids, derived_rows):
    """Require exactly one derived row per source attempt. Do not renumber."""
    if type(source_ids) is not list or type(derived_rows) is not list:
        raise GeneratorEvalContractError("attempt_join_invalid", "attempt identity inputs are not lists")
    for record_id in source_ids:
        if type(record_id) is not str:
            raise GeneratorEvalContractError("record_id_invalid", "a source attempt id is not text")
    derived_ids = []
    for row in derived_rows:
        if not isinstance(row, dict) or type(row.get("record_id")) is not str:
            raise GeneratorEvalContractError("attempt_join_invalid", "a derived row lacks record_id")
        record_id = row["record_id"]
        derived_ids.append(record_id)
        if not _sha256_value(row.get("source_artifact_sha256")):
            raise GeneratorEvalContractError("source_artifact_sha256_invalid", record_id + " lacks a source artifact hash")
    derived_counts = {}
    for record_id in derived_ids:
        derived_counts[record_id] = derived_counts.get(record_id, 0) + 1
    for record_id, count in derived_counts.items():
        if count > 1:
            raise GeneratorEvalContractError("attempt_id_duplicated", record_id + " is duplicated in the derived ledger")
    source_set = set(source_ids)
    derived_set = set(derived_ids)
    for record_id in source_ids:
        if record_id not in derived_set:
            raise GeneratorEvalContractError("attempt_id_missing", record_id + " has no derived row")
    for record_id in derived_ids:
        if record_id not in source_set:
            raise GeneratorEvalContractError("attempt_id_extra", record_id + " is not a source attempt")
    if len(derived_rows) != len(source_ids):
        raise GeneratorEvalContractError("attempt_count_mismatch", "derived rows do not match the source attempt count")
    if derived_ids != source_ids:
        raise GeneratorEvalContractError("attempt_id_reordered", "derived attempt ids were renumbered or reordered")
    return True


def derived_ledger_sha256(rows):
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _derive_attempts(document, source_artifact_sha256):
    if not isinstance(document, dict):
        raise GeneratorEvalContractError("attempt_type_invalid", "the synthetic raw document is not an object")
    for key in ("contract", "condition", "attempts"):
        if key not in document:
            raise GeneratorEvalContractError("attempt_type_invalid", "the synthetic raw document lacks " + key)
    for key in document:
        if key not in ("contract", "condition", "attempts", "note"):
            raise GeneratorEvalContractError("attempt_type_invalid", "the synthetic raw document has unexpected field " + str(key))
    if document["contract"] != SYNTHETIC_RAW_CONTRACT:
        raise GeneratorEvalContractError("synthetic_contract_invalid", "the raw bundle is not the synthetic M8 contract")
    condition = document["condition"]
    if condition not in SYNTHETIC_SOURCE_KEYS:
        raise GeneratorEvalContractError("unknown_condition", "the synthetic raw condition is unknown")
    attempts = document["attempts"]
    if type(attempts) is not list:
        raise GeneratorEvalContractError("attempt_type_invalid", "synthetic attempts are not a list")
    source_ids = _typecheck_attempt_identities(attempts)
    seen = set()
    for record_id in source_ids:
        if record_id in seen:
            raise GeneratorEvalContractError("attempt_id_duplicated", record_id + " is duplicated in the source")
        seen.add(record_id)
    rows = []
    for attempt in attempts:
        if condition == "B0":
            row = adapt_synthetic_b0_source(attempt, source_artifact_sha256)
        else:
            row = _controlled_row(condition, attempt, source_artifact_sha256)
        rows.append(row)
    if len(rows) != len(attempts):
        raise GeneratorEvalContractError("replenishment_prohibited", "parsing changed the attempt count")
    return source_ids, rows


def parse_synthetic_raw_bundle(raw_bytes, manifest):
    """Parse a synthetic raw bundle without mutating the supplied bytes.

    There is no production M8 reader. Bytes that are not the synthetic contract
    fail closed.
    """
    normalized = validate_provenance_manifest(manifest)
    if type(raw_bytes) is not bytes:
        raise GeneratorEvalContractError("raw_payload_type_invalid", "the raw payload must be bytes, not a path or a mutable buffer")
    before = hashlib.sha256(raw_bytes).hexdigest()
    size = len(raw_bytes)
    if size != normalized["source_byte_size"]:
        raise GeneratorEvalContractError("source_byte_size_mismatch", "source_byte_size does not match the raw payload")
    if before != normalized["source_artifact_sha256"]:
        raise GeneratorEvalContractError("source_artifact_sha256_mismatch", "source_artifact_sha256 does not match the raw payload")
    document = json.loads(raw_bytes.decode("utf-8"))
    after = hashlib.sha256(raw_bytes).hexdigest()
    if before != after:
        raise GeneratorEvalContractError("raw_payload_mutated", "parsing changed the raw payload bytes")
    source_ids, derived = _derive_attempts(document, normalized["source_artifact_sha256"])
    validated = validate_records(derived)
    for row in validated:
        if row.get("source_artifact_sha256") != normalized["source_artifact_sha256"]:
            raise GeneratorEvalContractError("source_artifact_sha256_mismatch", row["record_id"] + " lost its source artifact hash")
    assert_derived_attempt_identity(source_ids, validated)
    digest = derived_ledger_sha256(validated)
    if "expected_derived_ledger_sha256" in normalized and digest != normalized["expected_derived_ledger_sha256"]:
        raise GeneratorEvalContractError(
            "derived_ledger_sha256_mismatch",
            "expected_derived_ledger_sha256 does not match the derived rows",
        )
    if "expected_attempt_count" in normalized and normalized["expected_attempt_count"] != len(source_ids):
        raise GeneratorEvalContractError(
            "expected_attempt_count_mismatch",
            "the expected attempt count does not match the source and was not topped up",
        )
    if len(validated) != len(source_ids):
        raise GeneratorEvalContractError("replenishment_prohibited", "parsing changed the attempt count")
    return {
        "synthetic_contract": SYNTHETIC_RAW_CONTRACT,
        "production_file_reader": False,
        "raw_bytes_sha256_before": before,
        "raw_bytes_sha256_after": after,
        "raw_bytes_unchanged": True,
        "source_artifact_id": normalized["source_artifact_id"],
        "source_artifact_sha256": normalized["source_artifact_sha256"],
        "derived_rows": validated,
        "derived_ledger_sha256": digest,
        "attempt_count": len(validated),
        "source_attempt_ids": source_ids,
        "replenishment_applied": False,
        "b0_included_in_b1_d1_controlled_comparison": False,
        "biological_validity_function": "m4_diagnostic_metrics.recomputed_validity",
        "provenance": {
            "schema": DERIVED_PROVENANCE_SCHEMA,
            "source_artifact_id": normalized["source_artifact_id"],
            "source_artifact_sha256": normalized["source_artifact_sha256"],
            "parser_adapter_version": normalized["parser_adapter_version"],
            "derived_row_count": len(validated),
            "derived_ledger_sha256": digest,
            "replenishment_prohibited": normalized["replenishment_prohibited"],
        },
    }


def parse_envelope(document):
    if not isinstance(document, dict):
        raise GeneratorEvalContractError("fixture_invalid", "a synthetic fixture must be an envelope")
    if document.get("fixture_role") != SYNTHETIC_ROLE:
        raise GeneratorEvalContractError("data_role_refused", "the fixture role is not synthetic")
    if document.get("chunk_id_namespace") != SYNTHETIC_CHUNK_NAMESPACE:
        raise GeneratorEvalContractError("chunk_namespace_unrecognised", "the fixture chunk namespace is not synthetic")
    if not isinstance(document.get("records"), list):
        raise GeneratorEvalContractError("fixture_invalid", "fixture records are missing")
    metadata = {
        "fixture_role": SYNTHETIC_ROLE,
        "chunk_id_namespace": SYNTHETIC_CHUNK_NAMESPACE,
    }
    return metadata, document["records"]


def load_synthetic_fixture(path):
    if _forbidden_filename(path) or _forbidden_filename(os.path.basename(str(path))):
        raise GeneratorEvalContractError("filename_guard", "the filename is a held-out role file name")
    resolved = os.path.realpath(path)
    root = os.path.realpath(fixture_root())
    if resolved != root and not resolved.startswith(root + os.sep):
        raise GeneratorEvalContractError("fixture_path_refused", "the path is outside the synthetic fixture directory")
    if _forbidden_filename(os.path.basename(resolved)):
        raise GeneratorEvalContractError("filename_guard", "the filename is a held-out role file name")
    if not os.path.isfile(resolved):
        raise GeneratorEvalContractError("fixture_missing", "the synthetic fixture is missing")
    if os.path.getsize(resolved) > MAX_FIXTURE_BYTES:
        raise GeneratorEvalContractError("fixture_too_large", "the synthetic fixture exceeds the GEP-1 size bound")
    with open(resolved, encoding="utf-8") as handle:
        document = json.load(handle)
    return parse_envelope(document)


def preflight_exit_code(report):
    """Return a non-success code when the preflight did not pass."""
    if isinstance(report, dict) and report.get("status") in ("passed", "passed_with_limitations"):
        return 0
    return 1


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        sys.stderr.write("gep1_cli_rejected: GEP-1 does not accept paths or an EVAL unlock\n")
        return 2
    metadata, records = load_synthetic_fixture(default_fixture_path())
    report = run_preflight(records, metadata=metadata)
    sys.stdout.write(render_preflight_text(report))
    return preflight_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())

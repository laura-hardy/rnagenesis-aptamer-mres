#!/usr/bin/env python3
"""M10 pathway for the frozen Section 5 generator evaluation.

Two modes are separate. The frozen pre-EVAL gate validates the pinned metric
specification, allowlisted generated ledgers, matched schedule, frozen M9A
summaries, ViennaRNA environment, S6 parameter hash, and S7 hashes. It can
write a sequence-free record and can fold only the synthetic ViennaRNA smoke
fixture. It has no EVAL opener. Authorized production execution stays
uninvoked until the explicit M10/EVAL authorization object is present. It
finishes output-directory, generated-input, schedule, configuration, the
frozen-spec gate, ViennaRNA, the captured code inventory, the frozen S6
parameter-record hash, the three frozen S7 configuration hashes, and the
frozen M9A summary checks before opening EVAL once. That single read is
adapted, calculated, folded, validated, and published. The metric
specification is frozen and production-ready. This module does not authorize
M10 execution.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import platform
import re
import shutil
import stat
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import generator_eval_analysis as analysis
import generator_eval_s6_assignment as s6_assignment
from generator_eval_derived_ledger import DERIVED_FIELDS
from generator_eval_parser import (
    OUTCOME_EMPTY,
    OUTCOME_NON_ACGU,
    OUTCOME_NON_SEQUENCE,
    OUTCOME_UNPARSEABLE,
    OUTCOME_VALID,
    OUTCOMES,
)
from generator_eval_production_ledger import (
    CONTRACT_RELATIVE_PATH,
    FROZEN_PARSER_CONTRACT_SHA256,
    FROZEN_SOURCE_MANIFEST_SHA256,
    PRODUCTION_ATTEMPT_COUNTS,
    PRODUCTION_D1_SEED_COUNTS,
    PRODUCTION_LEDGER_SCHEMA,
    PRODUCTION_ROW_FIELDS,
)

M10_SCHEMA = "generator-eval-m10-inactive-v1"
CANONICAL_SEQUENCE = re.compile(r"^[ACGU]+$")
SYNTHETIC_AUTHORIZATION = {
    "scope": "synthetic_fixtures_only",
    "m10_execution_authorized": False,
    "open_eval": False,
    "open_biological_ledgers": False,
    "production_execution": False,
}
EVAL_AUTHORIZATION_KEYS = ("m10_execution_authorized", "open_eval", "payload_is_bytes")
FROZEN_EVAL_SHA256 = "ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015"
FROZEN_EVAL_RELATIVE = "data/interim/s7b_partition/eval.csv"
EVAL_EXPECTATIONS = {
    "identities": 181,
    "unique_cores": 154,
    "clusters": 79,
    "short_cores": 89,
    "long_cores": 65,
}
S6_LABELS = ("short", "long")
MATCHED_FAMILIES = (
    {"block": "A", "technical_block": "A", "d1_training_seed": 43},
    {"block": "B", "technical_block": "B", "d1_training_seed": 44},
)
FROZEN_TRAIN_SUMMARIES = (
    (
        "exact",
        "results/fine_tuning/m9_generator_evaluation/m9a_train_leakage/m9_exact_train_leakage_summary.json",
        "f7d10f7f41777a091cc2b2bf3dfeec555d5e8d84b3b89850328be7cdcf15e0d3",
    ),
    (
        "nearest",
        "results/fine_tuning/m9_generator_evaluation/m9a_train_leakage/m9_nearest_train_distance_summary.json",
        "c68fa997207a657a7049e53dd074e8d593333f84152008d631cae0d6565c1d66",
    ),
    (
        "manifest",
        "results/fine_tuning/m9_generator_evaluation/m9a_train_leakage/m9_train_leakage_manifest.json",
        "e2b97da3b1f39859c1d4fc3a652dd4abb6e4da5836e2a5e9c067ce1b87491d88",
    ),
)
TRAIN_SUMMARY_SCHEMAS = {
    "exact": "generator-eval-exact-train-leakage-summary-m9a-r1",
    "nearest": "generator-eval-nearest-train-distance-summary-m9a-r1",
    "manifest": "generator-eval-train-leakage-manifest-m9a-r1",
}
PROTECTED_DERIVED_MODE = 0o600
PUBLIC_ARTIFACT_MODE = 0o644
OPTIONAL_LEDGER_FIELDS = ("s6_length_stratum",)
NULL_SEQUENCE_OUTCOMES = (OUTCOME_EMPTY, OUTCOME_UNPARSEABLE, OUTCOME_NON_SEQUENCE)
RETAINED_SEQUENCE_OUTCOMES = (OUTCOME_VALID, OUTCOME_NON_ACGU)
FORBIDDEN_REPORT_KEYS = frozenset(
    {
        "clustering",
        "clustering_identity_threshold",
        "generated_cluster_concentration",
        "shannon_diversity",
        "effective_cluster_count",
        "representation_analysis",
        "representation_metrics",
        "confidence_interval",
        "bootstrap",
        "hypothesis_test",
        "p_value",
        "aggregate_generator_quality_score",
        "generator_quality_score",
        "combined_quality_score",
        "combined_closeness_score",
        "structure_distance",
        "structural_diversity",
        "ensemble_defect",
        "ensemble_metric",
        "eval_cluster_resampling",
        "equal_seed_structure",
        "equal_seed_pooled_novelty",
    }
)
HASHED_CODE_PATHS = (
    "scripts/modelling/generator_eval_m10.py",
    "scripts/modelling/generator_eval_preflight.py",
    "scripts/modelling/generator_eval_analysis.py",
    "config/modelling/generator_eval_metric_spec.json",
    "docs/aptarank_full_mres_thesis_evaluation_plan_v3_4.md",
    "docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md",
    "scripts/modelling/generator_eval_s6_assignment.py",
    "config/global_s7b_partition.json",
    "config/global_s7c_ft_train_validation.json",
    "config/global_s7d_final_build.json",
)
SCIENTIFIC_LIMITATIONS = (
    "B1 versus D1 is the primary comparison. Matched blocks A and B are descriptive and are not training replicates.",
    "B2 retains its single empirical-null-seed limitation and is not a training replicate.",
    "B0 stays on a separate historical length panel. Its requested biological length is unavailable.",
    "The 79 EVAL clusters are a design fact and a limitation. They do not weight formulas and they do not trigger resampling.",
    "No interval estimate, resampling procedure, or significance procedure is produced.",
    "No combined generator score is defined. The three closeness metrics stay separate.",
    "These descriptors do not show binding, affinity, selectivity, or NDM-1-specific generation.",
    "The metric specification is frozen and production-ready. Production execution remains unauthorized.",
    "Generator-evaluation ViennaRNA 2.7.0 was not invoked. It remains distinct from AptaRank ViennaRNA 2.7.2 and must be verified before a biological run.",
)
GENERATED_PREFLIGHT_SCHEMA = "generator-eval-m10-generated-input-preflight-v1"
SYNTHETIC_SMOKE_SCHEMA = "generator-eval-m10-synthetic-viennarna-smoke-v1"
PRODUCTION_SCHEMA = "generator-eval-m10-production-v1"
PRODUCTION_MANIFEST_SCHEMA = "generator-eval-m10-production-manifest-v1"
METRIC_SPEC_RELATIVE = "config/modelling/generator_eval_metric_spec.json"
# Pinned after the metric specification is frozen. Production stays unauthorized
# until an explicit M10/EVAL authorization object is supplied.
FROZEN_METRIC_SPEC_SHA256 = "2b0679b999235cc838298563448b01ef73f5fdd5132c5ddd3d9944f301f5c824"
FROZEN_S6_PARAMETER_SHA256 = "8e2e20cfe1fa68ba53beec8df9aa9a64a9a2144dc9006fbbf5f8eb064f01df0f"
FROZEN_S7_CONFIGURATION_SHA256 = (
    ("config/global_s7b_partition.json", "c62553344748fc8c322869d68a46f69e653dee5641bf5f208dcb776e597c9550"),
    (
        "config/global_s7c_ft_train_validation.json",
        "e07f5af0de56beff4cefe75854493eaa3f696b9bc20c554ce2261033165f0873",
    ),
    ("config/global_s7d_final_build.json", "abd3e1b29f422848aabd309ab0bb985731b9fb3941ddfbd2ec0f43d31a98b475"),
)
PRODUCTION_RUNNER_RELATIVE = "scripts/modelling/generator_eval_m10.py"
PRODUCTION_OUTPUT_NAMES = (
    "m10_derived_evidence.json",
    "m10_sequence_free_report.json",
    "m10_run_manifest.json",
)
CONDITIONS = ("B0", "B1", "B2", "D1")
PRODUCTION_LIMITATIONS = (
    "B1 versus D1 is the primary comparison. Matched blocks A and B are descriptive and are not training replicates.",
    "B2 retains its single empirical-null-seed limitation and is not a training replicate.",
    "B0 stays on a separate historical length panel. Its requested biological length is unavailable.",
    "The EVAL clusters are a design fact and a limitation. They do not weight formulas and they do not trigger resampling.",
    "No interval estimate, resampling procedure, or significance procedure is produced.",
    "No combined generator score is defined. The three closeness metrics stay separate.",
    "These descriptors do not show binding, affinity, selectivity, or NDM-1-specific generation.",
    "Generator-evaluation folding is RNA.fold(sequence) in ViennaRNA 2.7.0 and is distinct from AptaRank ViennaRNA 2.7.2.",
)
AGGREGATION_ACTUAL = "actual attempt accounting"
AGGREGATION_MULTIPLICITY = "global condition-level duplicate/multiplicity outcome"
AGGREGATION_EQUAL_SEED = "equal-training-seed valid-conditional mixture"
AGGREGATION_PER_SEED = "per-seed only"
AGGREGATION_VALID_ROWS = "valid rows with duplicates retained"
AGGREGATION_VALID_ROW_QUANTILES = "per-condition and per-seed valid-row quantiles with duplicate-attempt weighting"
AGGREGATION_INHERITED_EXACT = "inherited frozen M9A exact-match summary"
AGGREGATION_DIAGNOSTIC_ATTEMPT = "actual attempt accounting diagnostic"
AGGREGATION_INHERITED_NEAREST = "inherited frozen M9A nearest-distance summary"
AGGREGATION_REQUESTED_LENGTH = "per requested length where a requested length is recorded; B0 not applicable"
AGGREGATION_NOT_ON_LEDGER = "not recorded on the frozen M9 derived ledger and not imputed"
AGGREGATION_TRAIN_NESTED = "nested descriptive TRAIN output is not recomputed and is not a closeness metric"


def _coverage(metric_id, disposition, aggregation_basis, output_location, field=None, b0_requested_length=None):
    entry = {
        "metric_id": metric_id,
        "disposition": disposition,
        "aggregation_basis": aggregation_basis,
        "output_location": output_location,
    }
    if field is not None:
        entry["field"] = field
    if b0_requested_length is not None:
        entry["b0_requested_length"] = b0_requested_length
    return entry


PRODUCTION_METRIC_COVERAGE = (
    _coverage("raw_attempts", "production_output", AGGREGATION_ACTUAL, "metrics.by_condition", "raw_attempts"),
    _coverage("parsed_outputs", "audit_only", AGGREGATION_ACTUAL, "metrics.by_condition", "parsed_outputs"),
    _coverage("valid_outputs", "production_output", AGGREGATION_ACTUAL, "metrics.by_condition", "valid_outputs"),
    _coverage("invalid_outputs", "production_output", AGGREGATION_ACTUAL, "metrics.by_condition", "invalid_outputs"),
    _coverage("empty_or_unparseable_outputs", "production_output", AGGREGATION_ACTUAL, "metrics.by_condition", "empty_or_unparseable_outputs"),
    _coverage("exact_length_hits", "production_output", AGGREGATION_ACTUAL, "metrics.by_condition", "exact_length_hits", "not_applicable"),
    _coverage("exact_hit_rate", "production_output", AGGREGATION_ACTUAL, "metrics.by_condition", "exact_hit_rate", "not_applicable"),
    _coverage(
        "exact_hit_rate_valid_outputs_diagnostic",
        "production_output",
        AGGREGATION_DIAGNOSTIC_ATTEMPT,
        "metrics.by_condition",
        "exact_hit_rate_valid_outputs_diagnostic",
        "not_applicable",
    ),
    _coverage("eos_marker_observations", "audit_only", AGGREGATION_NOT_ON_LEDGER, "audit_only.eos_marker_observations"),
    _coverage("early_eos_observations", "audit_only", AGGREGATION_NOT_ON_LEDGER, "audit_only.early_eos_observations"),
    _coverage("cleaned_length_distribution", "production_output", AGGREGATION_ACTUAL, "metrics.by_condition", "cleaned_length_distribution"),
    _coverage(
        "length_shortfall_distribution",
        "production_output",
        AGGREGATION_ACTUAL,
        "metrics.by_condition",
        "length_shortfall_distribution",
        "not_applicable",
    ),
    _coverage(
        "length_excess_distribution",
        "production_output",
        AGGREGATION_ACTUAL,
        "metrics.by_condition",
        "length_excess_distribution",
        "not_applicable",
    ),
    _coverage("unique_valid_outputs", "production_output", AGGREGATION_MULTIPLICITY, "metrics.by_condition", "unique_valid_outputs"),
    _coverage("duplicates", "production_output", AGGREGATION_MULTIPLICITY, "metrics.by_condition", "duplicates"),
    _coverage(
        "largest_duplicate_multiplicity",
        "production_output",
        AGGREGATION_MULTIPLICITY,
        "exact_duplicate_diversity.by_condition",
        "largest_duplicate_multiplicity",
    ),
    _coverage(
        "largest_duplicate_share",
        "production_output",
        AGGREGATION_MULTIPLICITY,
        "exact_duplicate_diversity.by_condition",
        "largest_duplicate_share",
    ),
    _coverage("valid_nonempty_acgu_fraction", "production_output", AGGREGATION_ACTUAL, "metrics.by_condition", "valid_nonempty_acgu_fraction"),
    _coverage("empty_or_unparseable_fraction", "production_output", AGGREGATION_ACTUAL, "metrics.by_condition", "empty_or_unparseable_fraction"),
    _coverage("unique_fraction", "production_output", AGGREGATION_MULTIPLICITY, "exact_duplicate_diversity.by_condition", "unique_fraction"),
    _coverage("exact_train_match_rate", "inherited_frozen_m9a", AGGREGATION_INHERITED_EXACT, "frozen_m9a_train.exact"),
    _coverage(
        "per_requested_length_exact_hit_rate",
        "production_output",
        AGGREGATION_ACTUAL,
        "by_requested_length",
        b0_requested_length="not_applicable",
    ),
    _coverage("nearest_train_normalized_edit_distance", "inherited_frozen_m9a", AGGREGATION_INHERITED_NEAREST, "frozen_m9a_train.nearest"),
    _coverage(
        "maximum_edit_similarity_to_train",
        "inherited_frozen_m9a",
        AGGREGATION_INHERITED_NEAREST,
        "frozen_m9a_train.nearest.by_condition",
        "maximum_edit_similarity_to_train",
    ),
    _coverage("nucleotide_distribution", "production_output", AGGREGATION_VALID_ROWS, "composition.by_condition", "nucleotide_fractions"),
    _coverage("dinucleotide_distribution", "production_output", AGGREGATION_VALID_ROWS, "composition.by_condition", "dinucleotide_fractions"),
    _coverage("mfe", "production_output", AGGREGATION_VALID_ROW_QUANTILES, "structure.by_condition", "mfe"),
    _coverage("mfe_per_nt", "production_output", AGGREGATION_VALID_ROW_QUANTILES, "structure.by_condition", "mfe_per_nt"),
    _coverage("paired_fraction", "production_output", AGGREGATION_VALID_ROW_QUANTILES, "structure.by_condition", "paired_fraction"),
    _coverage("full_length_stratified_results", "production_output", AGGREGATION_REQUESTED_LENGTH, "by_requested_length", b0_requested_length="not_applicable"),
    _coverage("successfully_parsed_outputs", "production_output", AGGREGATION_ACTUAL, "metrics.by_condition", "successfully_parsed_outputs"),
    _coverage("pooled_gc_fraction", "production_output", AGGREGATION_EQUAL_SEED, "d1_equal_seed", "pooled_gc_fraction"),
    _coverage(
        "nearest_reference_normalized_edit_distance",
        "production_output",
        AGGREGATION_EQUAL_SEED,
        "closeness.by_condition",
        "nearest_reference_normalized_edit_distance",
    ),
    _coverage(
        "nucleotide_total_variation_to_reference",
        "production_output",
        AGGREGATION_EQUAL_SEED,
        "closeness.by_condition",
        "nucleotide_total_variation_to_reference",
    ),
    _coverage(
        "dinucleotide_total_variation_to_reference",
        "production_output",
        AGGREGATION_EQUAL_SEED,
        "closeness.by_condition",
        "dinucleotide_total_variation_to_reference",
    ),
    _coverage("failure_reason_counts", "production_output", AGGREGATION_ACTUAL, "metrics.by_condition", "failure_reason_counts"),
    _coverage("actual_attempt_level_validity_rate", "production_output", AGGREGATION_ACTUAL, "metrics.by_condition", "actual_attempt_level_validity_rate"),
    _coverage("duplicate_excess", "production_output", AGGREGATION_MULTIPLICITY, "exact_duplicate_diversity.by_condition", "duplicate_excess"),
    _coverage("multiplicity_histogram", "production_output", AGGREGATION_MULTIPLICITY, "exact_duplicate_diversity.by_condition", "multiplicity_histogram"),
    _coverage("equal_seed_mean_validity_rate", "production_output", AGGREGATION_EQUAL_SEED, "d1_equal_seed.mean_validity_rate"),
    _coverage("nucleotide_total_variation_to_train", "inherited_frozen_m9a", AGGREGATION_TRAIN_NESTED, "inherited_dispositions.nucleotide_total_variation_to_train"),
    _coverage("dinucleotide_total_variation_to_train", "inherited_frozen_m9a", AGGREGATION_TRAIN_NESTED, "inherited_dispositions.dinucleotide_total_variation_to_train"),
    _coverage("b1_d1_directional_consistency", "production_output", AGGREGATION_EQUAL_SEED, "directional_consistency.b1_versus_d1"),
    _coverage("d1_by_training_seed", "production_output", AGGREGATION_PER_SEED, "d1_by_training_seed"),
    _coverage("matched_b1_d1_block_directional_consistency", "production_output", AGGREGATION_PER_SEED, "directional_consistency.by_matched_block"),
    _coverage("observed_range_across_training_seeds", "production_output", AGGREGATION_PER_SEED, "observed_range_across_training_seeds"),
)
PINNED_INTERPRETER = "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python"
VIENNA_PACKAGE = "viennarna"
VIENNA_VERSION = "2.7.0"
VIENNA_BUILD = "py38pl5321hd78456e_0"
VIENNA_CALL = "RNA.fold(sequence)"
SYNTHETIC_SMOKE_SEQUENCE = "GGGAAACCC"
SOURCE_MANIFEST_RELATIVE = "config/modelling/generator_eval_source_manifest.json"
ACCOUNTING_SUMMARY_RELATIVE = "results/fine_tuning/m9_generator_evaluation/m9_parsing_accounting_summary.json"
FROZEN_ACCOUNTING_SHA256 = "b06aaf5cf9d2938cf555c496990ba6d04ed4d385fc5c7a6d7071eb504df148d4"
LEDGER_DIRECTORY = "results/fine_tuning/m9_generator_evaluation"
FROZEN_LEDGER_FILES = {
    "B0": (
        "m9_b0_derived_attempt_ledger.jsonl",
        "4d35ea9e4980fa42e4dbefa08f80f49df39ca7517784ea1851ea20c3742fe6ef",
    ),
    "B1": (
        "m9_b1_derived_attempt_ledger.jsonl",
        "18d76af08e931dc46d59cba5c303a1824fced966337bb5cef06abcbb6bbaf935",
    ),
    "B2": (
        "m9_b2_derived_attempt_ledger.jsonl",
        "49ae765eef2aacb7ecc16a922cc663465a91f0e26f1abe8aff01eed7c6d86c06",
    ),
    "D1": (
        "m9_d1_derived_attempt_ledger.jsonl",
        "58cc3acb0e22d497521480d949ccb55237212bd8aec617f939471951c02deecd",
    ),
}
FROZEN_SOURCE_ARTIFACT_SHA256 = {
    "B1": "37ba0e1b852a6b8492a816a4adc0c6bfee15a554ba28a8ba5dd91d9e32a255d9",
    "B2": "bbe35f448db0d7fc02ad0156865798382b0b41e9ad047b4e52eddf7cff740c83",
    "D1": "cedcc36133f5dfb3678e1560c6d6bab703136fe89e512e939b9f93a9a6361de9",
}
UNIQUE_VALID_DENOMINATORS = {"B0": 30080, "B1": 29983, "B2": 30000, "D1": 30000}
VALID_CANONICAL_DENOMINATORS = {"B0": 30080, "B1": 30000, "B2": 30000, "D1": 30000}
INVALID_DENOMINATORS = {"B0": 0, "B1": 0, "B2": 0, "D1": 0}
BLOCK_ATTEMPTS = 15000
B0_CHUNK_ATTEMPTS = 3008
B0_PANEL_SEEDS = (4201, 4202, 4203, 4204, 4205, 4206, 4207, 4208, 4209, 4210)
PROTECTED_BASENAMES = frozenset(
    {"eval.csv", "ref.csv", "ft_train.csv", "ft_validation.csv", "corpus_final.txt", "corpus_final.csv"}
)
PROTECTED_PATH_PARTS = frozenset({"TRAIN", "VALIDATION", "REF", "EVAL"})
GENERATED_PREFLIGHT_AUTHORIZATION = {
    "scope": "generated_input_preflight",
    "m10_execution_authorized": False,
    "open_eval": False,
    "read_frozen_generated_ledgers": True,
    "production_execution": False,
}
PRODUCTION_AUTHORIZATION = {
    "scope": "m10_production_execution",
    "m10_execution_authorized": True,
    "open_eval": True,
    "payload_is_bytes": True,
}
PREFLIGHT_LIMITATIONS = (
    "Generated-input preflight validates identities, schemas, counts, and B1/D1 pairing only.",
    "M10 scientific execution is not authorized. EVAL was not opened and no EVAL metric was computed.",
    "Biological generated sequences and EVAL cores were not folded.",
    "The synthetic ViennaRNA smoke test is a fixture check and is not a scientific result.",
    "B1 versus D1 is the primary comparison. Matched blocks A and B are descriptive and are not training replicates.",
    "B2 retains its single empirical-null-seed limitation and is not a training replicate.",
    "B0 stays on a separate historical length panel. Its requested biological length is unavailable.",
    "Invalid and failed attempts are retained. A count mismatch is a blocker and is not repaired by replenishment.",
    "No structure-distance metric is defined.",
    "The metric specification is frozen and production-ready. Production execution remains unauthorized.",
)


class M10ContractError(ValueError):
    """The inactive M10 pathway refused the request."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def _sha256_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nonnegative_int(value):
    return type(value) is int and value >= 0


def _positive_int(value):
    return type(value) is int and value >= 1


def _text(value):
    return isinstance(value, str) and value.strip() != ""


def _canonical(value):
    return isinstance(value, str) and CANONICAL_SEQUENCE.fullmatch(value) is not None


def _s6_provenance(root):
    try:
        return s6_assignment.provenance(root)
    except s6_assignment.S6AssignmentError as error:
        raise M10ContractError(error.code, error.detail) from error


def synthetic_authorization():
    """Return the only authorization this stage accepts for a synthetic run."""
    return dict(SYNTHETIC_AUTHORIZATION)


def _require_synthetic_authorization(authorization):
    if authorization != SYNTHETIC_AUTHORIZATION:
        raise M10ContractError(
            "m10_unauthorized",
            "synthetic M10 requires the inactive synthetic authorization and does not run production",
        )


def _eval_authorized(authorization):
    return (
        isinstance(authorization, dict)
        and set(authorization) == set(EVAL_AUTHORIZATION_KEYS)
        and authorization.get("m10_execution_authorized") is True
        and authorization.get("open_eval") is True
        and authorization.get("payload_is_bytes") is True
    )


def _row_fields(row):
    if not isinstance(row, dict):
        raise M10ContractError("ledger_row_invalid", "a derived row is not an object")
    expected = set(PRODUCTION_ROW_FIELDS) | set(OPTIONAL_LEDGER_FIELDS)
    extra = [key for key in row if key not in expected]
    missing = [key for key in PRODUCTION_ROW_FIELDS if key not in row]
    if extra or missing:
        raise M10ContractError("ledger_row_invalid", "a derived row does not match the frozen ledger schema")
    if row.get("ledger_schema") != PRODUCTION_LEDGER_SCHEMA:
        raise M10ContractError("ledger_schema_invalid", "a derived row is not an M9 production ledger row")
    if row.get("equal_seed_weighting_applied") is not False:
        raise M10ContractError("equal_seed_weighting_refused", "equal-seed weighting is not applied while adapting")
    return row


def _status_from_outcome(row):
    outcome = row.get("outcome")
    if outcome not in OUTCOMES:
        raise M10ContractError("ledger_outcome_invalid", "a derived row has an unknown outcome")
    sequence = row.get("parsed_sequence")
    if outcome in NULL_SEQUENCE_OUTCOMES:
        if sequence is not None or row.get("failure_reason") != outcome:
            raise M10ContractError("ledger_outcome_invalid", "a null-sequence outcome is internally inconsistent")
        if row.get("is_valid_canonical") is not False or row.get("valid_sequence_multiplicity") is not None:
            raise M10ContractError("ledger_outcome_invalid", "an invalid row carries a valid-sequence multiplicity")
        return {
            "sequence": None,
            "parsed_status": False,
            "alphabet_valid": False,
            "cleaning_status": "not_applicable",
            "cleaning_version": None,
            "observed_length": None,
        }
    if outcome not in RETAINED_SEQUENCE_OUTCOMES or not isinstance(sequence, str) or sequence == "":
        raise M10ContractError("ledger_outcome_invalid", "a retained outcome has no parsed body")
    if row.get("parsed_length") != len(sequence) or row.get("failure_reason") != (None if outcome == OUTCOME_VALID else outcome):
        raise M10ContractError("ledger_outcome_invalid", "a retained outcome disagrees with its parsed body")
    if outcome == OUTCOME_VALID:
        if not _canonical(sequence) or row.get("is_valid_canonical") is not True:
            raise M10ContractError("ledger_outcome_invalid", "a valid row is not canonical")
        return {
            "sequence": sequence,
            "parsed_status": True,
            "alphabet_valid": True,
            "cleaning_status": "cleaned",
            "cleaning_version": "m9-biological-parser-v1",
            "observed_length": len(sequence),
        }
    if _canonical(sequence) or row.get("is_valid_canonical") is not False or row.get("valid_sequence_multiplicity") is not None:
        raise M10ContractError("ledger_outcome_invalid", "a non-ACGU row is marked valid")
    return {
        "sequence": sequence,
        "parsed_status": True,
        "alphabet_valid": False,
        "cleaning_status": "rejected",
        "cleaning_version": "m9-biological-parser-v1",
        "observed_length": len(sequence),
    }


def _require_source_hash(row):
    value = row.get("source_artifact_sha256")
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise M10ContractError("source_hash_invalid", "a derived row lacks a source artifact hash")
    return value


def _adapt_common(row, status):
    return {
        "record_id": row["record_id"],
        "condition": row["condition"],
        "data_role": "SYNTHETIC",
        "source_artifact_sha256": _require_source_hash(row),
        "outcome": row["outcome"],
        "failure_reason": row["failure_reason"],
        "is_valid_canonical": row["is_valid_canonical"],
        "valid_sequence_multiplicity": row["valid_sequence_multiplicity"],
        "is_exact_duplicate_within_condition": row["is_exact_duplicate_within_condition"],
        "technical_block": row["technical_block"],
        "checkpoint_identity": row["checkpoint_identity"],
        "d1_training_seed": row["d1_training_seed"],
        "training_seed": row["d1_training_seed"],
        "generation_seed": row["generation_seed"],
        "master_attempt_index": row["master_attempt_index"],
        "within_batch_position": row["within_batch_position"],
        "invocation_index": row["invocation_index"],
        "requested_length": None,
        "nominal_max_seq_len": row["nominal_max_seq_len"],
        "max_seq_len": row["max_seq_len"],
        "empirical_null_seed": row["empirical_null_seed"],
        "attempt_index": row["attempt_index"],
        "b0_seed": row["b0_seed"],
        "b0_chunk_id": row["b0_chunk_id"],
        "sampled_length": row["sampled_length"],
        **status,
        **_assign_generated_row(status),
    }


def _check_multiplicity(rows):
    counts = {}
    for row in rows:
        if row["outcome"] == OUTCOME_VALID:
            counts[row["parsed_sequence"]] = counts.get(row["parsed_sequence"], 0) + 1
    for row in rows:
        if row["outcome"] != OUTCOME_VALID:
            continue
        multiplicity = counts[row["parsed_sequence"]]
        if row["valid_sequence_multiplicity"] != multiplicity:
            raise M10ContractError("multiplicity_inconsistent", row["record_id"] + " multiplicity does not match the retained rows")
        if row["is_exact_duplicate_within_condition"] is not (multiplicity > 1):
            raise M10ContractError("multiplicity_inconsistent", row["record_id"] + " duplicate flag does not match the retained rows")


def _adapt_b0(row, status):
    if row["condition"] != "B0":
        raise M10ContractError("ledger_condition_invalid", "a B0 ledger row has another condition")
    if row["requested_biological_length_available"] is not False or row["requested_biological_length"] is not None:
        raise M10ContractError("b0_requested_length_unavailable", "B0 does not receive an inferred requested length")
    if row["nominal_max_seq_len"] != 37:
        raise M10ContractError("b0_nominal_max_seq_len_invalid", "B0 nominal max_seq_len is not 37")
    if row["d1_training_seed"] is not None or row["technical_block"] is not None or row["generation_seed"] is not None:
        raise M10ContractError("b0_provenance_invalid", "B0 carries matched-block provenance")
    if not _nonnegative_int(row["b0_seed"]):
        raise M10ContractError("b0_provenance_invalid", "B0 historical generation seed is missing")
    adapted = _adapt_common(row, status)
    adapted["requested_length"] = None
    adapted["length_regime"] = "historical_37nt"
    return adapted


def _adapt_b2(row, status):
    if row["condition"] != "B2":
        raise M10ContractError("ledger_condition_invalid", "a B2 ledger row has another condition")
    if row["technical_block"] is not None or row["d1_training_seed"] is not None or row["checkpoint_identity"] is not None:
        raise M10ContractError("b2_provenance_invalid", "B2 carries neural provenance")
    if not _nonnegative_int(row["empirical_null_seed"]) or not _positive_int(row["sampled_length"]):
        raise M10ContractError("b2_provenance_invalid", "B2 seed or sampled length is missing")
    if not _nonnegative_int(row["attempt_index"]):
        raise M10ContractError("b2_provenance_invalid", "B2 attempt index is missing")
    adapted = _adapt_common(row, status)
    adapted["requested_length"] = row["sampled_length"]
    adapted["length_regime"] = "empirical_null_length_draw"
    return adapted


def _adapt_controlled(row, status, condition):
    if row["condition"] != condition:
        raise M10ContractError("ledger_condition_invalid", "a controlled ledger row has another condition")
    if row["technical_block"] not in ("A", "B"):
        raise M10ContractError("technical_block_invalid", row["record_id"] + " lacks technical block A or B")
    if not _text(row["checkpoint_identity"]):
        raise M10ContractError("checkpoint_missing", row["record_id"] + " lacks a checkpoint identity")
    if not _nonnegative_int(row["generation_seed"]) or not _nonnegative_int(row["master_attempt_index"]):
        raise M10ContractError("pairing_field_invalid", row["record_id"] + " lacks a generation seed or master attempt index")
    if not _nonnegative_int(row["within_batch_position"]) or not _nonnegative_int(row["invocation_index"]):
        raise M10ContractError("pairing_field_invalid", row["record_id"] + " lacks a within-batch position or invocation index")
    if row["requested_biological_length_available"] is not True or not _positive_int(row["requested_biological_length"]):
        raise M10ContractError("requested_length_invalid", row["record_id"] + " lacks a requested length")
    if row["max_seq_len"] != row["requested_biological_length"] + 1:
        raise M10ContractError("max_seq_len_invalid", row["record_id"] + " max_seq_len is not requested length + 1")
    if condition == "B1" and row["d1_training_seed"] is not None:
        raise M10ContractError("b1_training_seed_forbidden", row["record_id"] + " carries a D1 training seed")
    if condition == "D1" and row["d1_training_seed"] not in (43, 44):
        raise M10ContractError("d1_training_seed_invalid", row["record_id"] + " is not D1 seed 43 or 44")
    adapted = _adapt_common(row, status)
    adapted["requested_length"] = row["requested_biological_length"]
    adapted["length_regime"] = "matched_length"
    return adapted


def _assign_generated_row(status):
    """Label a valid canonical output from its sequence length.

    Requested length is not the S6 input. An invalid attempt with no usable
    canonical sequence stays in the ledger with a null stratum.
    """
    sequence = status.get("sequence")
    if status.get("alphabet_valid") is True and status.get("parsed_status") is True and isinstance(sequence, str) and sequence != "":
        try:
            assigned = s6_assignment.assign_sequence(sequence)
        except s6_assignment.S6AssignmentError as error:
            raise M10ContractError(error.code, error.detail) from error
        return assigned
    return {
        "s6_length_stratum": None,
        "s6_length_stratum_applicability": "not_applicable",
        "s6_length_input": None,
        "s6_input_length": None,
        "s6_input_length_source": "no_usable_sequence",
    }


def adapt_frozen_ledgers(ledgers):
    """Adapt four in-memory M9 derived ledgers. No biological ledger is opened.

    Invalid and duplicate attempts stay in the output. A production row is
    accepted without ``s6_length_stratum``; a supplied value is not the label.
    """
    if not isinstance(ledgers, dict) or set(ledgers) != {"B0", "B1", "B2", "D1"}:
        raise M10ContractError("ledger_bundle_invalid", "the four condition ledgers are required together")
    adapted = []
    counts = {}
    for condition in ("B0", "B1", "B2", "D1"):
        rows = ledgers[condition]
        if not isinstance(rows, list) or not rows:
            raise M10ContractError("ledger_bundle_invalid", condition + " ledger is empty")
        seen = set()
        condition_rows = []
        for raw in rows:
            row = _row_fields(raw)
            if row["condition"] != condition:
                raise M10ContractError("ledger_condition_invalid", "a row was placed in the wrong condition ledger")
            if not _text(row["record_id"]) or row["record_id"] in seen:
                raise M10ContractError("record_id_invalid", "a derived record id is missing or duplicated")
            seen.add(row["record_id"])
            status = _status_from_outcome(row)
            if condition == "B0":
                condition_rows.append(_adapt_b0(row, status))
            elif condition == "B2":
                condition_rows.append(_adapt_b2(row, status))
            else:
                condition_rows.append(_adapt_controlled(row, status, condition))
        _check_multiplicity(rows)
        if len(condition_rows) != len(rows):
            raise M10ContractError("rows_dropped", condition + " adaptation dropped a row")
        counts[condition] = len(condition_rows)
        adapted.extend(condition_rows)
    b2_seeds = {row["empirical_null_seed"] for row in adapted if row["condition"] == "B2"}
    if len(b2_seeds) != 1:
        raise M10ContractError("b2_multiple_seeds", "B2 must keep exactly one empirical-null seed")
    return {
        "schema": M10_SCHEMA,
        "rows": adapted,
        "row_counts": counts,
        "rows_dropped": False,
        "invalid_rows_retained": any(row["is_valid_canonical"] is False for row in adapted),
        "duplicate_rows_retained": any(row["is_exact_duplicate_within_condition"] is True for row in adapted),
        "biological_ledgers_opened": False,
    }


def _eval_expectations_view():
    return {
        "identities": EVAL_EXPECTATIONS["identities"],
        "unique_cores": EVAL_EXPECTATIONS["unique_cores"],
        "clusters": EVAL_EXPECTATIONS["clusters"],
        "short_cores": EVAL_EXPECTATIONS["short_cores"],
        "long_cores": EVAL_EXPECTATIONS["long_cores"],
        "clusters_weight_formulas": False,
        "clusters_trigger_resampling": False,
        "clusters_role": "reported_metadata_only",
    }


def _assign_core(sequence, stored_length):
    try:
        return s6_assignment.assign_sequence(sequence, stored_length)
    except s6_assignment.S6AssignmentError as error:
        raise M10ContractError(error.code, error.detail) from error


def _core_record(sequence_id, sequence, cluster_id, assigned, identity_count):
    return {
        "sequence_id": sequence_id,
        "sequence_core": sequence,
        "cluster_id": cluster_id,
        "s6_length_stratum": assigned["s6_length_stratum"],
        "s6_length_stratum_applicability": assigned["s6_length_stratum_applicability"],
        "s6_input_length": assigned["s6_input_length"],
        "s6_input_length_source": assigned["s6_input_length_source"],
        "identity_count": identity_count,
        "weight": 1,
    }


def adapt_synthetic_eval_stand_in(rows):
    """Validate a labelled synthetic EVAL stand-in. The real EVAL path is not read.

    This input contract is already one row per unique synthetic core. A repeated
    ``sequence_id`` or a repeated core is rejected. That is separate from the
    protected EVAL adapter, which keeps every scientific-identity row and
    collapses rows that share one core.
    """
    if not isinstance(rows, list) or not rows:
        raise M10ContractError("synthetic_eval_invalid", "the synthetic EVAL stand-in is empty")
    seen_ids = set()
    seen_cores = set()
    cores = []
    clusters = set()
    for row in rows:
        if not isinstance(row, dict):
            raise M10ContractError("synthetic_eval_invalid", "a synthetic EVAL row is not an object")
        if row.get("role") not in (None, "synthetic_eval_stand_in"):
            raise M10ContractError("synthetic_eval_invalid", "the stand-in role is not synthetic_eval_stand_in")
        sequence_id = row.get("sequence_id")
        sequence = row.get("sequence_core")
        cluster_id = row.get("cluster_id")
        if not _text(sequence_id):
            raise M10ContractError("duplicate_sequence_id", "a synthetic EVAL sequence id is missing")
        if sequence_id in seen_ids:
            raise M10ContractError("duplicate_sequence_id", sequence_id + " is duplicated")
        seen_ids.add(sequence_id)
        if not _canonical(sequence):
            raise M10ContractError("eval_noncanonical", "a synthetic EVAL core is not canonical A/C/G/U")
        if sequence in seen_cores:
            raise M10ContractError("duplicate_eval_core", "a synthetic EVAL core is duplicated")
        seen_cores.add(sequence)
        if not _text(cluster_id):
            raise M10ContractError("eval_cluster_missing", "a synthetic EVAL cluster id is missing")
        assigned = _assign_core(sequence, row.get("sequence_length_core"))
        if assigned["s6_length_stratum"] not in S6_LABELS:
            raise M10ContractError("s6_label_missing", sequence_id + " has no usable core length")
        clusters.add(cluster_id)
        cores.append(_core_record(sequence_id, sequence, cluster_id, assigned, 1))
    return {
        "role": "synthetic_eval_stand_in",
        "production_eval_opened": False,
        "frozen_eval_path_read": False,
        "cores": cores,
        "identity_count": len(rows),
        "unique_core_count": len(cores),
        "cluster_count": len(clusters),
        "short_core_count": sum(core["s6_length_stratum"] == "short" for core in cores),
        "long_core_count": sum(core["s6_length_stratum"] == "long" for core in cores),
        "validation_expectations": _eval_expectations_view(),
        "cores_weighted_once": True,
        "s6_assignment": _s6_provenance(REPO_ROOT),
    }


def _csv_field(raw, key):
    value = raw.get(key)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _parse_eval_csv(payload):
    """Adapt authorized EVAL identity rows and collapse them by core.

    ``scientific_identity_id`` is the unique identity-row key. ``sequence_id``
    is the separate sequence-level key and may repeat when every repeat maps
    to the same ``sequence_core``. One core still becomes one weighted record.
    The synthetic stand-in adapter is not this path: its contract is already
    one row per unique core.
    """
    try:
        text = bytes(payload).decode("utf-8")
    except UnicodeDecodeError as error:
        raise M10ContractError("eval_unreadable", "EVAL bytes are not UTF-8") from error
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise M10ContractError("eval_unreadable", "EVAL has no header")
    identities = []
    seen_identity_ids = set()
    sequence_cores = {}
    for raw in reader:
        identity_id = _csv_field(raw, "scientific_identity_id")
        if not identity_id:
            raise M10ContractError("duplicate_scientific_identity_id", "an EVAL scientific identity id is missing")
        if identity_id in seen_identity_ids:
            raise M10ContractError("duplicate_scientific_identity_id", identity_id + " is duplicated")
        seen_identity_ids.add(identity_id)
        sequence_id = _csv_field(raw, "sequence_id")
        if not sequence_id:
            raise M10ContractError("duplicate_sequence_id", "an EVAL sequence id is missing")
        sequence = _csv_field(raw, "sequence_core")
        if not _canonical(sequence):
            raise M10ContractError("eval_noncanonical", sequence_id + " is not a canonical core")
        cluster_id = _csv_field(raw, "cluster_id")
        if not cluster_id:
            raise M10ContractError("eval_cluster_missing", sequence_id + " lacks a cluster id")
        assigned = _assign_core(sequence, raw.get("sequence_length_core"))
        if assigned["s6_length_stratum"] not in S6_LABELS:
            raise M10ContractError("s6_label_missing", sequence_id + " has no usable core length")
        mapped = sequence_cores.get(sequence_id)
        if mapped is None:
            sequence_cores[sequence_id] = sequence
        elif mapped != sequence:
            raise M10ContractError("sequence_id_core_conflict", sequence_id + " maps to more than one core")
        identities.append(
            {
                "scientific_identity_id": identity_id,
                "sequence_id": sequence_id,
                "sequence_core": sequence,
                "cluster_id": cluster_id,
                "s6_length_stratum": assigned["s6_length_stratum"],
                "s6_input_length": assigned["s6_input_length"],
                "s6_input_length_source": assigned["s6_input_length_source"],
            }
        )
    if not identities:
        raise M10ContractError("eval_empty", "EVAL contains no identities")
    collapsed = {}
    order = []
    for row in identities:
        current = collapsed.get(row["sequence_core"])
        if current is None:
            collapsed[row["sequence_core"]] = _core_record(
                row["sequence_id"],
                row["sequence_core"],
                row["cluster_id"],
                {
                    "s6_length_stratum": row["s6_length_stratum"],
                    "s6_length_stratum_applicability": "applicable",
                    "s6_input_length": row["s6_input_length"],
                    "s6_input_length_source": row["s6_input_length_source"],
                },
                1,
            )
            order.append(row["sequence_core"])
            continue
        if current["sequence_id"] != row["sequence_id"]:
            raise M10ContractError("sequence_id_core_conflict", "one EVAL core maps to more than one sequence id")
        if (
            current["cluster_id"] != row["cluster_id"]
            or current["s6_length_stratum"] != row["s6_length_stratum"]
            or current["s6_input_length"] != row["s6_input_length"]
            or current["s6_input_length_source"] != row["s6_input_length_source"]
        ):
            raise M10ContractError("eval_core_conflict", "one EVAL core has conflicting labels")
        current["identity_count"] += 1
    cores = [collapsed[core] for core in order]
    return identities, cores


def _enforce_eval_expectations(identities, cores):
    clusters = {core["cluster_id"] for core in cores}
    counts = {
        "identities": len(identities),
        "unique_cores": len(cores),
        "clusters": len(clusters),
        "short_cores": sum(core["s6_length_stratum"] == "short" for core in cores),
        "long_cores": sum(core["s6_length_stratum"] == "long" for core in cores),
    }
    if counts != EVAL_EXPECTATIONS:
        raise M10ContractError("eval_count_mismatch", "EVAL counts do not match the frozen expectations")
    return counts


def adapt_authorized_eval(payload, authorization):
    """Verify frozen EVAL bytes only after explicit authorization.

    This function does not open a path. Calling it without authorization does
    not inspect the payload. A hash other than the frozen EVAL hash is refused
    before the bytes are treated as production EVAL.
    """
    if not _eval_authorized(authorization):
        raise M10ContractError("eval_adapter_unauthorized", "the EVAL adapter is inactive without explicit authorization")
    if isinstance(payload, (str, os.PathLike)):
        raise M10ContractError("eval_path_refused", "the EVAL adapter does not open a path")
    if not isinstance(payload, (bytes, bytearray)):
        raise M10ContractError("eval_payload_invalid", "authorized EVAL input must be bytes")
    digest = _sha256_bytes(bytes(payload))
    if digest != FROZEN_EVAL_SHA256:
        raise M10ContractError("eval_hash_mismatch", "the EVAL hash is not the frozen hash")
    identities, cores = _parse_eval_csv(payload)
    counts = _enforce_eval_expectations(identities, cores)
    return {
        "role": "EVAL",
        "production_eval_opened": True,
        "frozen_eval_relative_path": FROZEN_EVAL_RELATIVE,
        "sha256": digest,
        "cores": cores,
        "identity_count": counts["identities"],
        "unique_core_count": counts["unique_cores"],
        "cluster_count": counts["clusters"],
        "short_core_count": counts["short_cores"],
        "long_core_count": counts["long_cores"],
        "validation_expectations": _eval_expectations_view(),
        "cores_weighted_once": True,
        "s6_assignment": _s6_provenance(REPO_ROOT),
    }


def _family_name(row):
    block = row["technical_block"]
    if row["condition"] == "B1":
        if block == "A":
            return "A"
        if block == "B":
            return "B"
        raise M10ContractError("incompatible_schedule", row["record_id"] + " is outside blocks A and B")
    seed = row["d1_training_seed"]
    if seed == 43 and block == "A":
        return "A"
    if seed == 44 and block == "B":
        return "B"
    if (seed == 43 and block == "B") or (seed == 44 and block == "A"):
        raise M10ContractError("cross_family_match", row["record_id"] + " crosses the frozen block and seed family")
    raise M10ContractError("incompatible_schedule", row["record_id"] + " is outside the frozen seed pair")


def _pairing_key(row):
    return (
        row["generation_seed"],
        row["master_attempt_index"],
        row["within_batch_position"],
        row["requested_length"],
        row["invocation_index"],
    )


def _index_side(rows):
    indexed = {}
    for row in rows:
        key = _pairing_key(row)
        if key in indexed:
            raise M10ContractError("duplicate_pairing_key", row["record_id"] + " repeats a pairing key")
        indexed[key] = row
    return indexed


def bind_matched_blocks(rows):
    """Bind B1 block A to D1 seed 43 and B1 block B to D1 seed 44.

    Pairing requires equality of generation seed, master attempt index,
    within-batch position, requested length, and invocation index. Blocks stay
    descriptive.
    """
    if not isinstance(rows, list):
        raise M10ContractError("matched_blocks_invalid", "rows are not a list")
    grouped = {family["block"]: {"B1": [], "D1": []} for family in MATCHED_FAMILIES}
    for row in rows:
        if row["condition"] not in ("B1", "D1"):
            continue
        grouped[_family_name(row)][row["condition"]].append(row)
    family_keys = {}
    family_seeds = {}
    for family in MATCHED_FAMILIES:
        name = family["block"]
        b1 = _index_side(grouped[name]["B1"])
        d1 = _index_side(grouped[name]["D1"])
        family_keys[name] = (b1, d1)
        family_seeds[name] = {key[0] for key in b1} | {key[0] for key in d1}
    if family_seeds["A"] & family_seeds["B"]:
        raise M10ContractError("cross_family_match", "a generation seed appears in both matched families")
    overlap = set(family_keys["A"][0]) & set(family_keys["B"][0])
    overlap |= set(family_keys["A"][1]) & set(family_keys["B"][1])
    overlap |= set(family_keys["A"][0]) & set(family_keys["B"][1])
    overlap |= set(family_keys["A"][1]) & set(family_keys["B"][0])
    if overlap:
        raise M10ContractError("cross_family_match", "a pairing key appears in both matched families")
    bound = []
    for family in MATCHED_FAMILIES:
        name = family["block"]
        b1, d1 = family_keys[name]
        b1_seeds = {key[0] for key in b1}
        d1_seeds = {key[0] for key in d1}
        if b1_seeds != d1_seeds:
            raise M10ContractError("incompatible_schedule", "block " + name + " generation-seed families differ")
        if set(b1) != set(d1):
            raise M10ContractError("missing_pairing_row", "block " + name + " is missing a paired row")
        bound.append(
            {
                "block": name,
                "technical_block": family["technical_block"],
                "d1_training_seed": family["d1_training_seed"],
                "generation_seeds": sorted(b1_seeds),
                "b1_rows": [b1[key] for key in sorted(b1)],
                "d1_rows": [d1[key] for key in sorted(d1)],
                "paired_row_count": len(b1),
                "is_training_replicate": False,
                "is_significance_test_unit": False,
                "attempts_are_training_replicates": False,
            }
        )
    return bound


def _require_train_object(document, key, label):
    value = document.get(key)
    if not isinstance(value, dict):
        raise M10ContractError("train_schema_invalid", label)
    return value


def _require_train_summary_schema(key, document):
    """Require the frozen M9A schema and the fields the production report cites."""
    if not isinstance(document, dict) or document.get("schema") != TRAIN_SUMMARY_SCHEMAS[key]:
        raise M10ContractError("train_schema_invalid", key + " summary schema is not the frozen M9A schema")
    if key == "manifest":
        if document.get("sequence_strings_emitted") not in (False, None):
            raise M10ContractError("train_sequence_refused", key + " summary emits sequence strings")
        return
    if document.get("sequence_strings_emitted") is not False:
        raise M10ContractError("train_sequence_refused", key + " summary emits sequence strings")
    by_condition = _require_train_object(document, "by_condition", key + " summary lacks by_condition")
    if set(CONDITIONS) - set(by_condition):
        raise M10ContractError("train_schema_invalid", key + " summary lacks a condition block")
    d1 = _require_train_object(document, "d1", key + " summary lacks the D1 block")
    if key == "exact":
        for field in (
            "seed_43_valid_conditional_row_rate",
            "seed_44_valid_conditional_row_rate",
            "actual_attempt_pooled",
        ):
            if field not in d1:
                raise M10ContractError("train_schema_invalid", "the exact summary lacks " + field)
        return
    for condition in CONDITIONS:
        block = by_condition.get(condition)
        if not isinstance(block, dict) or "nearest_train_normalized_edit_distance" not in block:
            raise M10ContractError("train_schema_invalid", "the nearest summary lacks " + condition)
    seeds = d1.get("by_training_seed")
    if not isinstance(seeds, dict) or "43" not in seeds or "44" not in seeds:
        raise M10ContractError("train_schema_invalid", "the nearest summary lacks the D1 training seeds")
    if "pooled_equal_mixture_distance_quantiles" not in d1:
        raise M10ContractError("train_schema_invalid", "the nearest summary lacks the preserved equal mixture")


def load_allowlisted_train_summaries(root):
    """Read only the three frozen sequence-free M9A summary files, by path, hash, and schema."""
    root = os.path.realpath(root)
    loaded = {}
    for key, relative, expected in FROZEN_TRAIN_SUMMARIES:
        path = os.path.realpath(os.path.join(root, relative))
        allowed = os.path.realpath(os.path.join(root, os.path.dirname(relative)))
        if os.path.dirname(path) != allowed or os.path.basename(path) != os.path.basename(relative):
            raise M10ContractError("train_path_refused", "a TRAIN summary path left the allowlist")
        if "derived_attempt_ledger" in os.path.basename(path) or os.path.basename(path) in {
            "eval.csv",
            "ft_train.csv",
            "corpus_final.txt",
            "corpus_final.csv",
        }:
            raise M10ContractError("train_path_refused", "the TRAIN loader does not open sequences or ledgers")
        with open(path, "rb") as handle:
            blob = handle.read()
        digest = _sha256_bytes(blob)
        if digest != expected:
            raise M10ContractError("train_hash_mismatch", key + " summary hash does not match the frozen M9A output")
        document = json.loads(blob.decode("utf-8"))
        _require_train_summary_schema(key, document)
        loaded[key] = {"sha256": digest, "relative_path": relative, "document": document}
    return loaded


def _valid_sequences(rows):
    return [row["sequence"] for row in rows if row["is_valid_canonical"] is True]


def _public_closeness(generated, reference):
    population = analysis._closeness_population(generated, reference)
    public = {"combined": False, "cores_weighted_once": True, "clusters_weight_formulas": False}
    for key in (
        "nearest_reference_normalized_edit_distance",
        "nucleotide_total_variation_to_reference",
        "dinucleotide_total_variation_to_reference",
    ):
        metric = population[key]
        public[key] = {
            "value": metric.get("value"),
            "median": metric.get("median"),
            "direction": "lower",
            "undefined_reason": metric.get("undefined_reason"),
            "generated_valid_row_denominator": metric.get("generated_valid_row_denominator"),
            "generated_unique_valid_count": metric.get("generated_unique_valid_count"),
            "reference_unique_core_denominator": metric.get("reference_unique_core_denominator"),
        }
    return public


def _equal_seed_closeness(d1_rows, reference):
    provenance = analysis._preflight().validate_d1_pooling_provenance(
        {
            "pooling_policy": "equal_training_seed_mixture",
            "policy_verified": True,
            "participating_training_seeds": [43, 44],
        }
    )
    mixture = analysis.valid_conditional_equal_seed_mixture(d1_rows, provenance, reference_sequences=reference, train_cores=None)
    closeness = mixture["equal_mixture"]["closeness"]
    per_seed = {}
    for seed in (43, 44):
        selected = [row for row in d1_rows if row["training_seed"] == seed]
        per_seed[str(seed)] = _public_closeness(_valid_sequences(selected), reference)
    return {
        "aggregation_basis": "equal_training_seed_mixture",
        "applied_to_train_novelty": False,
        "equal_seed_pooled_novelty_invented": False,
        "nearest_reference_normalized_edit_distance": {
            "value": closeness["nearest_reference_normalized_edit_distance"]["value"],
            "direction": "lower",
        },
        "nucleotide_total_variation_to_reference": {
            "value": closeness["nucleotide_total_variation_to_reference"]["value"],
            "direction": "lower",
        },
        "dinucleotide_total_variation_to_reference": {
            "value": closeness["dinucleotide_total_variation_to_reference"]["value"],
            "direction": "lower",
        },
        "per_d1_training_seed": per_seed,
        "pooled_gc_fraction": {
            "value": mixture["equal_mixture"]["pooled_gc_fraction"],
            "undefined_reason": mixture["equal_mixture"]["pooled_gc_undefined_reason"],
            "aggregation_basis": AGGREGATION_EQUAL_SEED,
            "denominator": "equal_training_seed_valid_conditional_mixture",
            "per_seed_results_remain_separate": True,
        },
    }


def _fold_cached(sequence, fold, cache):
    if sequence not in cache:
        try:
            cache[sequence] = analysis._m6().structure_features(sequence, fold)
        except analysis._m6().DiagnosticError as error:
            raise M10ContractError("fold_invalid", error.detail) from error
    return cache[sequence]


def _structure_summary(sequences, fold, cache):
    if not sequences:
        return {
            "fold_calls_for_new_sequences": 0,
            "valid_row_count": 0,
            "distinct_valid_sequence_count": 0,
            "mfe_per_nt": None,
            "paired_fraction": None,
            "aggregation": "valid attempt rows with duplicate-attempt weighting",
            "fold_population": "each distinct valid sequence once",
            "quantile_population": "valid attempt rows with duplicate-attempt weighting",
            "equal_seed_pooled": False,
            "structure_distance_defined": False,
        }
    before = len(cache)
    features = [_fold_cached(sequence, fold, cache) for sequence in sequences]
    quantiles = analysis._m6()
    per_nt = quantiles._quantiles([item["mfe_per_nt"] for item in features])
    paired = quantiles._quantiles([item["paired_fraction"] for item in features])
    return {
        "fold_calls_for_new_sequences": len(cache) - before,
        "valid_row_count": len(sequences),
        "distinct_valid_sequence_count": len(set(sequences)),
        "mfe_per_nt": per_nt,
        "paired_fraction": paired,
        "aggregation": "valid attempt rows with duplicate-attempt weighting",
        "fold_population": "each distinct valid sequence once",
        "quantile_population": "valid attempt rows with duplicate-attempt weighting",
        "equal_seed_pooled": False,
        "structure_distance_defined": False,
    }


def _composition(sequences):
    if not sequences:
        return None
    sample = analysis._m6().composition(sequences)
    return {
        "sequence_count": sample["sequence_count"],
        "nucleotide_fractions": sample["nucleotide_fractions"],
        "dinucleotide_fractions": sample["dinucleotide_fractions"],
        "gc_fraction": analysis.pooled_gc_fraction(sequences),
        "length": analysis._m6()._quantiles([len(sequence) for sequence in sequences]),
    }


def _accounting(rows):
    valid = [row for row in rows if row["is_valid_canonical"] is True]
    sequences = [row["sequence"] for row in valid]
    failures = {}
    for row in rows:
        if row["failure_reason"] is None:
            continue
        failures[row["failure_reason"]] = failures.get(row["failure_reason"], 0) + 1
    unique = len(set(sequences))
    return {
        "attempted": len(rows),
        "successfully_parsed_outputs": analysis.successfully_parsed_outputs(rows),
        "parsed_outputs": {
            "value": len(rows),
            "label": "internal_schema_valid_record_audit",
            "thesis_facing": False,
        },
        "valid_acgu": len(valid),
        "unique_valid": unique,
        "duplicate_excess": len(valid) - unique,
        "invalid": len(rows) - len(valid),
        "multiplicity_histogram": analysis.multiplicity_histogram(sequences),
        "failure_reason_counts": failures,
        "source_artifact_sha256": sorted({row["source_artifact_sha256"] for row in rows}),
        "s6_length_stratum_not_applicable": sum(
            row.get("s6_length_stratum_applicability") == "not_applicable" for row in rows
        ),
    }


def _condition_report(condition, rows, reference, fold, cache, labels):
    sequences = _valid_sequences(rows)
    strata = {}
    for label in S6_LABELS:
        selected = [row for row in rows if row["s6_length_stratum"] == label]
        stratum_sequences = _valid_sequences(selected)
        stratum_reference = [core["sequence_core"] for core in reference if core["s6_length_stratum"] == label]
        strata[label] = {
            "accounting": _accounting(selected),
            "composition": _composition(stratum_sequences),
            "structure": _structure_summary(stratum_sequences, fold, cache),
            "closeness": _public_closeness(stratum_sequences, stratum_reference),
        }
    return {
        "condition": condition,
        "length_regime": labels,
        "accounting": _accounting(rows),
        "exact_duplicate_diversity": {
            "duplicate_excess": _accounting(rows)["duplicate_excess"],
            "multiplicity_histogram": analysis.multiplicity_histogram(sequences),
            "unique_only_is_primary": False,
        },
        "composition": _composition(sequences),
        "structure": _structure_summary(sequences, fold, cache),
        "closeness": _public_closeness(sequences, [core["sequence_core"] for core in reference]),
        "by_s6_length_stratum": strata,
    }


def _train_view(loaded):
    exact = loaded["exact"]["document"]
    nearest = loaded["nearest"]["document"]
    return {
        "reopened_train": False,
        "sequence_loader_added": False,
        "metrics_recomputed": False,
        "equal_seed_pooled_novelty_invented": False,
        "exact": {
            "sha256": loaded["exact"]["sha256"],
            "relative_path": loaded["exact"]["relative_path"],
            "by_condition": exact["by_condition"],
            "per_d1_training_seed": {
                "43": exact["d1"]["seed_43_valid_conditional_row_rate"],
                "44": exact["d1"]["seed_44_valid_conditional_row_rate"],
            },
            "attempt_level_summary": exact["d1"]["actual_attempt_pooled"],
        },
        "nearest": {
            "sha256": loaded["nearest"]["sha256"],
            "relative_path": loaded["nearest"]["relative_path"],
            "by_condition": nearest["by_condition"],
            "per_d1_training_seed": nearest["d1"]["by_training_seed"],
            "attempt_level_summary": {
                condition: nearest["by_condition"][condition]["nearest_train_normalized_edit_distance"]
                for condition in ("B0", "B1", "B2", "D1")
            },
            "preserved_frozen_equal_mixture": nearest["d1"]["pooled_equal_mixture_distance_quantiles"],
            "preserved_frozen_equal_mixture_recomputed": False,
        },
        "manifest_sha256": loaded["manifest"]["sha256"],
    }


def _code_hashes(root):
    """Capture the code and configuration inventory. This does not open EVAL.

    Capture records the current file hashes. It does not pin the broad
    inventory. Metric-calculation revisions stay validated through the metric
    specification. The production runner hash is the captured hash of this
    file and is not embedded back into the source.
    """
    hashes = {}
    for relative in HASHED_CODE_PATHS:
        path = os.path.join(root, relative)
        if not os.path.isfile(path):
            raise M10ContractError("code_inventory_missing", relative + " is missing from the code inventory")
        hashes[relative] = _sha256_file(path)
    return hashes


def assert_frozen_s6_and_s7(code_hashes, provenance):
    """Require the frozen S6 parameter record and the three S7 file hashes.

    Absent ``bimodality.json`` stays the recorded provenance limitation. The
    parameter-record hash is not an artefact hash. This does not open EVAL.
    """
    if not isinstance(code_hashes, dict):
        raise M10ContractError("code_inventory_missing", "the code inventory was not captured before EVAL")
    if not isinstance(provenance, dict):
        raise M10ContractError("s6_provenance_missing", "S6 provenance was not captured before EVAL")
    if provenance.get("parameter_record_hash_substituted_for_artefact") is not False:
        raise M10ContractError(
            "s6_artefact_invalid",
            "the parameter-record hash is not a substitute for the bimodality artefact hash",
        )
    parameter_hash = provenance.get("parameter_sha256")
    artefact_hash = provenance.get("artefact_sha256")
    if artefact_hash is not None and artefact_hash == parameter_hash:
        raise M10ContractError(
            "s6_artefact_invalid",
            "the parameter-record hash is not a substitute for the bimodality artefact hash",
        )
    if provenance.get("artefact_present") is True:
        if not isinstance(artefact_hash, str) or re.fullmatch(r"[0-9a-f]{64}", artefact_hash) is None:
            raise M10ContractError("s6_artefact_invalid", "a present bimodality artefact has no file hash")
    elif artefact_hash is not None or provenance.get("artefact_absence_classification") != "provenance_limitation":
        raise M10ContractError(
            "s6_provenance_missing",
            "absent bimodality.json must remain the recorded provenance limitation",
        )
    if parameter_hash != FROZEN_S6_PARAMETER_SHA256:
        raise M10ContractError("s6_parameter_hash_mismatch", "the S6 parameter-record hash is not the frozen hash")
    s7_hashes = {}
    for relative, expected in FROZEN_S7_CONFIGURATION_SHA256:
        if code_hashes.get(relative) != expected:
            raise M10ContractError("s7_configuration_hash_mismatch", relative + " hash is not the frozen hash")
        s7_hashes[relative] = expected
    runner = code_hashes.get(PRODUCTION_RUNNER_RELATIVE)
    if not isinstance(runner, str) or re.fullmatch(r"[0-9a-f]{64}", runner) is None:
        raise M10ContractError("code_inventory_missing", "the production-runner hash was not captured before EVAL")
    return {
        "s6_parameter_sha256": FROZEN_S6_PARAMETER_SHA256,
        "s6_artefact_present": provenance.get("artefact_present") is True,
        "s6_artefact_absence_classification": provenance.get("artefact_absence_classification"),
        "parameter_record_hash_substituted_for_artefact": False,
        "s7_configuration_sha256": s7_hashes,
        "production_runner_path": PRODUCTION_RUNNER_RELATIVE,
        "production_runner_sha256": runner,
        "code_inventory_disposition": "captured",
        "metric_calculation_revisions": "validated_through_metric_specification",
    }


def _reject_forbidden_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_REPORT_KEYS:
                raise M10ContractError("forbidden_output", key + " is outside M10")
            _reject_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_keys(item)


COMPOSITION_KEYS = frozenset(base + other for base in "ACGU" for other in ("",) + tuple("ACGU"))
CLOSED_STRUCTURAL_VALUES = {
    "block": frozenset({"A", "B"}),
    "technical_block": frozenset({"A", "B"}),
}


def _structural_token(key, value):
    allowed = CLOSED_STRUCTURAL_VALUES.get(key)
    return allowed is not None and value in allowed


def _sequence_value_leaks(key, value, sequences):
    if not isinstance(value, str) or value == "" or _structural_token(key, value):
        return False
    if value in sequences:
        return True
    for sequence in sequences:
        if len(sequence) >= 4 and sequence in value:
            return True
    return False


def assert_public_report_sequence_free(report, sequences):
    """Reject a public report that carries a protected sequence as data.

    Dictionary keys in the closed nucleotide and dinucleotide alphabets, and
    the closed block labels, are structural tokens. A one-, two-, or
    three-nucleotide sequence is a leak only when a value or an unexpected key
    equals that sequence. Longer sequences are also rejected when embedded in
    a non-structural string.
    """
    protected = {sequence for sequence in sequences if isinstance(sequence, str) and sequence != ""}

    def walk(value, key):
        if isinstance(value, dict):
            for child_key, child in value.items():
                if child_key in protected and child_key not in COMPOSITION_KEYS:
                    raise M10ContractError("sequence_leak", "the sequence-free report uses a sequence as a key")
                walk(child, child_key)
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif _sequence_value_leaks(key, value, protected):
            raise M10ContractError("sequence_leak", "the sequence-free report contains a raw sequence")

    walk(report, None)
    _reject_forbidden_keys(report)


def _assert_sequence_free(report, sequences):
    assert_public_report_sequence_free(report, sequences)


def build_reports(adapted, evaluation, train, fold, root):
    """Build the protected derived layer and the sequence-free aggregate report."""
    if not callable(fold):
        raise M10ContractError("fold_not_injected", "synthetic structure reporting requires an injected fold")
    rows = adapted["rows"]
    reference = evaluation["cores"]
    cache = {}
    by_condition = {}
    regimes = {
        "B0": "historical_37nt",
        "B1": "matched_length",
        "B2": "empirical_null_length_draw",
        "D1": "matched_length",
    }
    for condition, regime in regimes.items():
        selected = [row for row in rows if row["condition"] == condition]
        by_condition[condition] = _condition_report(condition, selected, reference, fold, cache, regime)
    d1_rows = [row for row in rows if row["condition"] == "D1"]
    reference_sequences = [core["sequence_core"] for core in reference]
    blocks = []
    for bound in bind_matched_blocks(rows):
        b1_sequences = _valid_sequences(bound["b1_rows"])
        d1_sequences = _valid_sequences(bound["d1_rows"])
        blocks.append(
            {
                "block": bound["block"],
                "technical_block": bound["technical_block"],
                "d1_training_seed": bound["d1_training_seed"],
                "generation_seeds": bound["generation_seeds"],
                "paired_row_count": bound["paired_row_count"],
                "is_training_replicate": False,
                "is_significance_test_unit": False,
                "attempts_are_training_replicates": False,
                "b1_closeness": _public_closeness(b1_sequences, reference_sequences),
                "d1_closeness": _public_closeness(d1_sequences, reference_sequences),
                "b1_structure": _structure_summary(b1_sequences, fold, cache),
                "d1_structure": _structure_summary(d1_sequences, fold, cache),
            }
        )
    per_seed_structure = {}
    for seed in (43, 44):
        selected = [row for row in d1_rows if row["d1_training_seed"] == seed]
        per_seed_structure[str(seed)] = _structure_summary(_valid_sequences(selected), fold, cache)
    eval_sequences = [core["sequence_core"] for core in reference]
    derived = {
        "layer": "protected_derived_evidence",
        "contains_sequences": True,
        "schema": M10_SCHEMA,
        "rows": rows,
        "synthetic_eval_cores": reference,
        "biological_ledgers_opened": False,
        "production_eval_opened": False,
    }
    b0_rows = [row for row in rows if row["condition"] == "B0"]
    b2_rows = [row for row in rows if row["condition"] == "B2"]
    report = {
        "layer": "sequence_free_aggregate_report",
        "schema": M10_SCHEMA,
        "status": "synthetic_inactive_pathway",
        "production_execution_authorized": False,
        "eval_opened": False,
        "biological_ledgers_opened": False,
        "viennarna_called": False,
        "generator_viennarna_required": "2.7.0",
        "aptarank_viennarna_distinct": "2.7.2",
        "generator_viennarna_verified_this_run": False,
        "metric_spec_freeze_status": "frozen",
        "metric_spec_production_ready": True,
        "s6_assignment": _s6_provenance(root),
        "reference_role": evaluation["role"],
        "eval_validation_expectations": evaluation["validation_expectations"],
        "eval_cluster_count_metadata": evaluation["cluster_count"],
        "clusters_weight_formulas": False,
        "clusters_trigger_resampling": False,
        "accounting": {condition: by_condition[condition]["accounting"] for condition in regimes},
        "exact_duplicate_diversity": {
            condition: by_condition[condition]["exact_duplicate_diversity"] for condition in regimes
        },
        "frozen_m9a_train": _train_view(train),
        "composition": {condition: by_condition[condition]["composition"] for condition in regimes},
        "structure": {
            "by_condition": {condition: by_condition[condition]["structure"] for condition in regimes},
            "by_s6_length_stratum": {
                condition: {
                    label: by_condition[condition]["by_s6_length_stratum"][label]["structure"] for label in S6_LABELS
                }
                for condition in regimes
            },
            "by_d1_training_seed": per_seed_structure,
            "synthetic_eval_cores": _structure_summary(eval_sequences, fold, cache),
            "equal_seed_pooled": False,
            "structure_distance_defined": False,
            "distinct_fold_count": len(cache),
        },
        "closeness": {
            "by_condition": {condition: by_condition[condition]["closeness"] for condition in regimes},
            "d1_equal_seed": _equal_seed_closeness(d1_rows, reference_sequences),
            "cores_weighted_once": True,
            "clusters_weight_formulas": False,
        },
        "d1_by_training_seed": {
            str(seed): _condition_report(
                "D1",
                [row for row in d1_rows if row["d1_training_seed"] == seed],
                reference,
                fold,
                cache,
                "matched_length",
            )
            for seed in (43, 44)
        },
        "matched_blocks": blocks,
        "b2_limitations": {
            "empirical_null_seed": b2_rows[0]["empirical_null_seed"],
            "empirical_null_seed_count": 1,
            "single_seed_limitation": True,
            "rows_are_training_replicates": False,
            "included_in_matched_blocks": False,
        },
        "b0_panel": {
            "included_in_matched_b1_d1_comparison": False,
            "length_regime": "historical_37nt",
            "nominal_max_seq_len": 37,
            "requested_length": "unavailable",
            "accounting": by_condition["B0"]["accounting"],
            "closeness": by_condition["B0"]["closeness"],
            "structure": by_condition["B0"]["structure"],
            "historical_generation_seeds": sorted({row["b0_seed"] for row in b0_rows}),
            "historical_chunk_ids": sorted({row["b0_chunk_id"] for row in b0_rows}, key=lambda item: str(item)),
        },
        "exclusions_and_failures": {
            condition: by_condition[condition]["accounting"]["failure_reason_counts"] for condition in regimes
        },
        "source_hashes": {
            condition: by_condition[condition]["accounting"]["source_artifact_sha256"] for condition in regimes
        },
        "code_and_configuration_hashes": _code_hashes(root),
        "scientific_limitations": list(SCIENTIFIC_LIMITATIONS),
        "successfully_parsed_outputs_is_thesis_facing": True,
        "parsed_outputs_label": "internal_schema_valid_record_audit",
    }
    sequences = set(eval_sequences)
    for row in rows:
        if isinstance(row.get("sequence"), str):
            sequences.add(row["sequence"])
    _assert_sequence_free(report, sequences)
    return derived, report


def _canonical_json(value):
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _refuse_existing(path):
    if os.path.lexists(path):
        raise M10ContractError("output_exists", "the output directory already exists")


def _refuse_results_directory(path, root):
    results = os.path.realpath(os.path.join(root, "results"))
    target = os.path.abspath(path)
    if os.path.commonpath([results, target]) == results:
        raise M10ContractError("biological_output_refused", "this stage does not create a biological M10 run directory")


def publish_reports(output_dir, derived, report, root):
    """Atomically publish both layers. An existing directory is never overwritten."""
    output_dir = os.path.abspath(output_dir)
    _refuse_results_directory(output_dir, root)
    _refuse_existing(output_dir)
    parent = os.path.dirname(output_dir)
    os.makedirs(parent, exist_ok=True)
    _refuse_existing(output_dir)
    blobs = (
        ("m10_derived_evidence.json", _canonical_json(derived)),
        ("m10_sequence_free_report.json", _canonical_json(report)),
    )
    temp = tempfile.mkdtemp(prefix=".m10-inactive.", dir=parent)
    promoted = False
    try:
        for filename, blob in blobs:
            target = os.path.join(temp, filename)
            mode = PROTECTED_DERIVED_MODE if filename == "m10_derived_evidence.json" else PUBLIC_ARTIFACT_MODE
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            try:
                os.fchmod(descriptor, mode)
                view = blob
                while view:
                    written = os.write(descriptor, view)
                    view = view[written:]
            finally:
                os.close(descriptor)
            with open(target, "rb") as handle:
                reread = handle.read()
            if reread != blob or _sha256_bytes(reread) != _sha256_bytes(blob):
                raise M10ContractError("output_validation_failed", filename + " changed before publication")
        _refuse_existing(output_dir)
        os.rename(temp, output_dir)
        promoted = True
    finally:
        if not promoted and os.path.isdir(temp):
            shutil.rmtree(temp)
    return output_dir


def run_synthetic(document, output_dir, authorization, fold, root=REPO_ROOT):
    """Run the inactive synthetic pathway. Production execution is refused."""
    _require_synthetic_authorization(authorization)
    if not isinstance(document, dict) or document.get("fixture_role") != "SYNTHETIC":
        raise M10ContractError("fixture_role_refused", "the M10 fixture role is not synthetic")
    if document.get("reference_role") != "synthetic_eval_stand_in":
        raise M10ContractError("reference_role_refused", "the reference role is not the synthetic EVAL stand-in")
    for key in ("eval_path", "ledger_path", "train_path", "output_path"):
        if key in document:
            raise M10ContractError("path_input_refused", "the synthetic pathway does not accept filesystem paths")
    adapted = adapt_frozen_ledgers(document["ledgers"])
    evaluation = adapt_synthetic_eval_stand_in(document["synthetic_eval"])
    train = load_allowlisted_train_summaries(root)
    derived, report = build_reports(adapted, evaluation, train, fold, root)
    publish_reports(output_dir, derived, report, root)
    return report


def generated_preflight_authorization():
    """Return the only authorization the generated-input preflight accepts."""
    return dict(GENERATED_PREFLIGHT_AUTHORIZATION)


def production_authorization():
    """Return the explicit M10/EVAL authorization object. This stage does not use it."""
    return dict(PRODUCTION_AUTHORIZATION)


def _production_authorized(authorization):
    return authorization == PRODUCTION_AUTHORIZATION


def _require_generated_preflight_authorization(authorization):
    if authorization != GENERATED_PREFLIGHT_AUTHORIZATION:
        raise M10ContractError(
            "preflight_unauthorized",
            "generated-input preflight requires its inactive authorization and does not open EVAL",
        )


def _refuse_protected_path(path):
    text = os.fspath(path)
    parts = text.replace("\\", "/").split("/")
    if any(part in PROTECTED_PATH_PARTS for part in parts):
        raise M10ContractError("protected_input_refused", "a protected data role is not an M10 generated input")
    if parts[-1] in PROTECTED_BASENAMES:
        raise M10ContractError("protected_input_refused", "a protected corpus file is not an M10 generated input")


def _allowlisted_path(root, relative):
    _refuse_protected_path(relative)
    root_abs = os.path.abspath(root)
    path = os.path.abspath(os.path.join(root, relative))
    if os.path.commonpath([root_abs, path]) != root_abs:
        raise M10ContractError("generated_path_refused", "a generated input path left the repository root")
    allowed_dir = os.path.abspath(os.path.join(root, os.path.dirname(relative)))
    if os.path.dirname(path) != allowed_dir or os.path.basename(path) != os.path.basename(relative):
        raise M10ContractError("generated_path_refused", "a generated input path left the allowlist")
    if os.path.islink(path):
        raise M10ContractError("generated_path_refused", "a generated input path is a symlink")
    return path


def _read_allowlisted_bytes(path):
    _refuse_protected_path(path)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError as error:
        raise M10ContractError("generated_input_missing", "an allowlisted generated input is missing") from error
    except OSError as error:
        raise M10ContractError("generated_input_unreadable", "an allowlisted generated input could not be read") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise M10ContractError("generated_input_unreadable", "an allowlisted generated input is not a regular file")
        chunks = []
        while True:
            blob = os.read(descriptor, 1024 * 1024)
            if blob == b"":
                break
            chunks.append(blob)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _load_allowlisted_json(root, relative, expected_sha256, label):
    path = _allowlisted_path(root, relative)
    blob = _read_allowlisted_bytes(path)
    digest = _sha256_bytes(blob)
    if digest != expected_sha256:
        raise M10ContractError("frozen_configuration_mismatch", label + " hash is not the frozen hash")
    try:
        document = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M10ContractError("frozen_configuration_mismatch", label + " is not UTF-8 JSON") from error
    return path, digest, document


def _parse_jsonl(blob, label):
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as error:
        raise M10ContractError("ledger_unreadable", label + " is not UTF-8") from error
    rows = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line == "":
            raise M10ContractError("ledger_unreadable", label + " contains an empty line")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise M10ContractError("ledger_unreadable", label + " line is not JSON") from error
        if not isinstance(row, dict):
            raise M10ContractError("ledger_row_invalid", label + " line " + str(line_number) + " is not an object")
        rows.append(row)
    return rows


def _expected_source_hashes(manifest):
    conditions = manifest["conditions"]
    b0 = conditions["B0"]
    chunks = b0["source_chunks"]
    if [chunk["seed"] for chunk in chunks] != list(B0_PANEL_SEEDS):
        raise M10ContractError("b0_panel_mismatch", "B0 historical seeds are not the frozen panel")
    if b0.get("comparison_role") != "external_comparator":
        raise M10ContractError("b0_panel_mismatch", "B0 is not the external historical panel")
    if b0.get("nominal_max_seq_len") != 37 or b0.get("biological_requested_length") is not None:
        raise M10ContractError("b0_panel_mismatch", "B0 requested length is not unavailable")
    b0_hashes = {}
    for chunk in chunks:
        b0_hashes[chunk["raw_sha256"]] = chunk["seed"]
    if len(b0_hashes) != len(chunks):
        raise M10ContractError("b0_panel_mismatch", "B0 chunk hashes are not unique")
    allocation = conditions["D1"]["seed_allocation"]
    expected_allocation = [
        {"d1_training_seed": 43, "technical_block": "A", "attempts": BLOCK_ATTEMPTS},
        {"d1_training_seed": 44, "technical_block": "B", "attempts": BLOCK_ATTEMPTS},
    ]
    observed_allocation = [
        {
            "d1_training_seed": item.get("d1_training_seed"),
            "technical_block": item.get("technical_block"),
            "attempts": item.get("attempts"),
        }
        for item in allocation
    ]
    if observed_allocation != expected_allocation:
        raise M10ContractError("d1_allocation_mismatch", "D1 seed allocation is not block A/43 and block B/44")
    if conditions["B2"].get("empirical_null_seed") is None:
        raise M10ContractError("b2_seed_mismatch", "the frozen manifest has no B2 empirical-null seed")
    for condition, expected in PRODUCTION_ATTEMPT_COUNTS.items():
        if conditions[condition].get("attempt_count") != expected:
            raise M10ContractError("denominator_mismatch", condition + " manifest attempt count is not the frozen denominator")
    if conditions["B1"].get("combined_ledger_sha256") != FROZEN_SOURCE_ARTIFACT_SHA256["B1"]:
        raise M10ContractError("source_artifact_mismatch", "B1 source hash is not the frozen hash")
    if conditions["B2"].get("raw_jsonl_sha256") != FROZEN_SOURCE_ARTIFACT_SHA256["B2"]:
        raise M10ContractError("source_artifact_mismatch", "B2 source hash is not the frozen hash")
    if conditions["D1"].get("combined_ledger_sha256") != FROZEN_SOURCE_ARTIFACT_SHA256["D1"]:
        raise M10ContractError("source_artifact_mismatch", "D1 source hash is not the frozen hash")
    return {
        "B0": b0_hashes,
        "B1": {FROZEN_SOURCE_ARTIFACT_SHA256["B1"]: None},
        "B2": {FROZEN_SOURCE_ARTIFACT_SHA256["B2"]: conditions["B2"]["empirical_null_seed"]},
        "D1": {FROZEN_SOURCE_ARTIFACT_SHA256["D1"]: None},
        "b2_empirical_null_seed": conditions["B2"]["empirical_null_seed"],
    }


def _validate_source_hash_counts(condition, rows, expected_hashes):
    counts = {}
    for row in rows:
        digest = row.get("source_artifact_sha256")
        if digest not in expected_hashes:
            raise M10ContractError("source_artifact_mismatch", condition + " row source hash is outside the frozen manifest")
        counts[digest] = counts.get(digest, 0) + 1
    if set(counts) != set(expected_hashes):
        raise M10ContractError("source_artifact_mismatch", condition + " is missing a frozen source hash")
    if condition == "B0":
        for digest, count in counts.items():
            if count != B0_CHUNK_ATTEMPTS:
                raise M10ContractError("b0_panel_mismatch", "a B0 historical chunk does not contain 3008 attempts")
    return counts


def _validate_b0_panel(rows):
    seeds = {}
    for row in rows:
        if row.get("condition") != "B0":
            raise M10ContractError("ledger_condition_invalid", "a non-B0 row is in the B0 ledger")
        if row.get("technical_block") is not None or row.get("d1_training_seed") is not None:
            raise M10ContractError("b0_panel_mismatch", "B0 carries matched-block provenance")
        if row.get("nominal_max_seq_len") != 37 or row.get("requested_biological_length") is not None:
            raise M10ContractError("b0_panel_mismatch", "B0 requested length is not unavailable")
        if row.get("requested_biological_length_available") is not False:
            raise M10ContractError("b0_panel_mismatch", "B0 claims a requested biological length")
        seed = row.get("b0_seed")
        seeds[seed] = seeds.get(seed, 0) + 1
    if tuple(sorted(seeds)) != B0_PANEL_SEEDS:
        raise M10ContractError("b0_panel_mismatch", "B0 historical seeds are not 4201-4210")
    for seed, count in seeds.items():
        if count != B0_CHUNK_ATTEMPTS:
            raise M10ContractError("b0_panel_mismatch", "a B0 historical seed does not contain 3008 attempts")


def _validate_b2_seed(rows, expected_seed):
    seeds = {row.get("empirical_null_seed") for row in rows}
    if seeds != {expected_seed}:
        raise M10ContractError("b2_seed_mismatch", "B2 does not keep the single frozen empirical-null seed")
    for row in rows:
        if row.get("technical_block") is not None or row.get("d1_training_seed") is not None:
            raise M10ContractError("b2_provenance_invalid", "B2 carries matched-block provenance")


def _validate_d1_seed_counts(rows):
    counts = {}
    for row in rows:
        seed = row.get("d1_training_seed")
        block = row.get("technical_block")
        if seed == 43 and block != "A":
            raise M10ContractError("cross_family_match", "D1 seed 43 is outside block A")
        if seed == 44 and block != "B":
            raise M10ContractError("cross_family_match", "D1 seed 44 is outside block B")
        counts[seed] = counts.get(seed, 0) + 1
    if counts != dict(PRODUCTION_D1_SEED_COUNTS):
        raise M10ContractError("denominator_mismatch", "D1 seed attempt counts are not 15000 and 15000")


def load_allowlisted_generated_ledgers(root):
    """Load the four frozen M9 ledgers by allowlisted path and hash.

    The loader does not search for pools and does not open EVAL, REF, TRAIN,
    or VALIDATION. Every parsed row is retained for the adapter.
    """
    manifest_path, manifest_sha, manifest = _load_allowlisted_json(
        root,
        SOURCE_MANIFEST_RELATIVE,
        FROZEN_SOURCE_MANIFEST_SHA256,
        "the source manifest",
    )
    if manifest.get("schema_version") != "generator-eval-source-manifest-m9-r1":
        raise M10ContractError("frozen_configuration_mismatch", "the source manifest schema is not the frozen revision")
    expected_hashes = _expected_source_hashes(manifest)
    accounting_path, accounting_sha, accounting = _load_allowlisted_json(
        root,
        ACCOUNTING_SUMMARY_RELATIVE,
        FROZEN_ACCOUNTING_SHA256,
        "the parsing accounting summary",
    )
    if accounting.get("sequence_strings_emitted") is not False:
        raise M10ContractError("accounting_sequence_refused", "the accounting summary emits sequence strings")
    ledgers = {}
    identities = {}
    for condition in ("B0", "B1", "B2", "D1"):
        filename, expected = FROZEN_LEDGER_FILES[condition]
        relative = LEDGER_DIRECTORY + "/" + filename
        path = _allowlisted_path(root, relative)
        blob = _read_allowlisted_bytes(path)
        digest = _sha256_bytes(blob)
        if digest != expected:
            raise M10ContractError("generated_ledger_hash_mismatch", condition + " ledger hash is not the frozen hash")
        rows = _parse_jsonl(blob, condition)
        if len(rows) != PRODUCTION_ATTEMPT_COUNTS[condition]:
            raise M10ContractError("denominator_mismatch", condition + " attempt count is not the frozen denominator")
        _validate_source_hash_counts(condition, rows, expected_hashes[condition])
        if condition == "B0":
            _validate_b0_panel(rows)
        elif condition == "B2":
            _validate_b2_seed(rows, expected_hashes["b2_empirical_null_seed"])
        elif condition == "D1":
            _validate_d1_seed_counts(rows)
        ledgers[condition] = rows
        identities[condition] = {
            "relative_path": relative,
            "path": path,
            "sha256": digest,
            "byte_count": len(blob),
            "attempts": len(rows),
        }
    seen = set()
    for condition, rows in ledgers.items():
        for row in rows:
            record_id = row.get("record_id")
            if not _text(record_id) or record_id in seen:
                raise M10ContractError("record_id_invalid", "a generated record id is missing or duplicated")
            seen.add(record_id)
    return {
        "ledgers": ledgers,
        "identity": {
            "source_manifest": {
                "relative_path": SOURCE_MANIFEST_RELATIVE,
                "path": manifest_path,
                "sha256": manifest_sha,
            },
            "accounting_summary": {
                "relative_path": ACCOUNTING_SUMMARY_RELATIVE,
                "path": accounting_path,
                "sha256": accounting_sha,
                "sequence_strings_emitted": False,
            },
            "ledgers": identities,
            "b2_empirical_null_seed": expected_hashes["b2_empirical_null_seed"],
            "excluded_sources": _excluded_sources(manifest),
        },
        "accounting": accounting,
    }


def _excluded_sources(manifest):
    excluded = manifest.get("excluded_sources")
    if not isinstance(excluded, dict) or excluded.get("sequence_comparison") is not False:
        raise M10ContractError("exclusion_invalid", "source exclusions are not the declared sequence-free lineage")
    lineages = []
    for item in excluded.get("lineages", []):
        lineages.append(
            {
                "logical_id": item.get("logical_id") or item.get("logical_directory_identity"),
                "kind": item.get("kind"),
                "included_in_evaluation_sources": item.get("included_in_evaluation_sources"),
            }
        )
    return {
        "method": excluded.get("method"),
        "sequence_comparison": False,
        "lineages": lineages,
    }


def _observed_denominators(rows):
    valid = [row for row in rows if row["is_valid_canonical"] is True]
    invalid = [row for row in rows if row["is_valid_canonical"] is not True]
    sequences = [row["sequence"] for row in valid]
    failures = {}
    for row in rows:
        if row["failure_reason"] is None:
            continue
        failures[row["failure_reason"]] = failures.get(row["failure_reason"], 0) + 1
    return {
        "attempts": len(rows),
        "valid_canonical": len(valid),
        "unique_valid": len(set(sequences)),
        "invalid_retained": len(invalid),
        "duplicate_excess": len(valid) - len(set(sequences)),
        "failure_reason_counts": failures,
        "rows_dropped": False,
    }


def validate_generated_denominators(adapted, accounting):
    """Require the frozen attempt and unique-valid denominators. Do not drop rows."""
    if adapted.get("rows_dropped") is not False:
        raise M10ContractError("rows_dropped", "generated adaptation dropped a row")
    observed = {}
    for condition in ("B0", "B1", "B2", "D1"):
        rows = [row for row in adapted["rows"] if row["condition"] == condition]
        if len(rows) != adapted["row_counts"][condition]:
            raise M10ContractError("rows_dropped", condition + " adaptation dropped a row")
        counts = _observed_denominators(rows)
        if counts["attempts"] != PRODUCTION_ATTEMPT_COUNTS[condition]:
            raise M10ContractError("denominator_mismatch", condition + " attempts are not the frozen denominator")
        if counts["valid_canonical"] != VALID_CANONICAL_DENOMINATORS[condition]:
            raise M10ContractError("denominator_mismatch", condition + " valid rows are not the frozen denominator")
        if counts["unique_valid"] != UNIQUE_VALID_DENOMINATORS[condition]:
            raise M10ContractError("denominator_mismatch", condition + " unique-valid count is not the frozen denominator")
        if counts["invalid_retained"] != INVALID_DENOMINATORS[condition]:
            raise M10ContractError("denominator_mismatch", condition + " invalid count is not the frozen denominator")
        summary = accounting["conditions"][condition]
        if summary.get("total_attempts") != counts["attempts"]:
            raise M10ContractError("denominator_mismatch", condition + " accounting attempts disagree with the ledger")
        if summary.get("distinct_valid_sequences") != counts["unique_valid"]:
            raise M10ContractError("denominator_mismatch", condition + " accounting unique-valid count disagrees with the ledger")
        if summary.get("valid_canonical_count") != counts["valid_canonical"]:
            raise M10ContractError("denominator_mismatch", condition + " accounting valid count disagrees with the ledger")
        observed[condition] = counts
    if adapted["row_counts"]["B0"] != 30080 or adapted["row_counts"]["D1"] != 30000:
        raise M10ContractError("denominator_mismatch", "adapted row counts are not the frozen denominators")
    return observed


def _index_matched_sides(rows):
    grouped = {family["block"]: {"B1": [], "D1": []} for family in MATCHED_FAMILIES}
    outside = {"B0": 0, "B2": 0}
    for row in rows:
        condition = row["condition"]
        if condition in outside:
            if row.get("technical_block") is not None or row.get("d1_training_seed") not in (None,):
                raise M10ContractError("schedule_condition_invalid", condition + " entered a matched block")
            outside[condition] += 1
            continue
        if condition not in ("B1", "D1"):
            raise M10ContractError("schedule_condition_invalid", "a matched schedule contains an unknown condition")
        grouped[_family_name(row)][condition].append(row)
    indexed = {}
    for family in MATCHED_FAMILIES:
        name = family["block"]
        indexed[name] = {
            "B1": _index_side(grouped[name]["B1"]),
            "D1": _index_side(grouped[name]["D1"]),
        }
    return indexed, outside


def validate_production_matched_blocks(rows):
    """Bind the frozen B1/D1 schedule with the reviewed block binder.

    Block A pairs only with D1 seed 43 and block B only with D1 seed 44.
    Each side has 15,000 attempts. Pairing keys are equal one to one. B0 and
    B2 stay outside the blocks.
    """
    indexed, outside = _index_matched_sides(rows)
    for family in MATCHED_FAMILIES:
        name = family["block"]
        b1 = set(indexed[name]["B1"])
        d1 = set(indexed[name]["D1"])
        if b1 - d1:
            raise M10ContractError("extra_pairing_row", "block " + name + " has an unpaired B1 row")
        if d1 - b1:
            raise M10ContractError("missing_pairing_row", "block " + name + " is missing a paired row")
    overlap = set(indexed["A"]["B1"]) & set(indexed["B"]["B1"])
    overlap |= set(indexed["A"]["D1"]) & set(indexed["B"]["D1"])
    overlap |= set(indexed["A"]["B1"]) & set(indexed["B"]["D1"])
    overlap |= set(indexed["A"]["D1"]) & set(indexed["B"]["B1"])
    if overlap:
        raise M10ContractError("cross_family_match", "a pairing key appears in both matched families")
    bound = bind_matched_blocks(rows)
    public_blocks = []
    for family, block in zip(MATCHED_FAMILIES, bound):
        if block["block"] != family["block"] or block["d1_training_seed"] != family["d1_training_seed"]:
            raise M10ContractError("incompatible_schedule", "the reviewed binder changed the frozen block family")
        if block["paired_row_count"] != BLOCK_ATTEMPTS:
            raise M10ContractError("schedule_count_mismatch", "block " + block["block"] + " does not contain 15000 paired attempts")
        if len(block["b1_rows"]) != BLOCK_ATTEMPTS or len(block["d1_rows"]) != BLOCK_ATTEMPTS:
            raise M10ContractError("schedule_count_mismatch", "block " + block["block"] + " sides are not 15000 attempts")
        for row in block["b1_rows"] + block["d1_rows"]:
            if row["condition"] not in ("B1", "D1"):
                raise M10ContractError("schedule_condition_invalid", "B0 or B2 entered a matched block")
        public_blocks.append(
            {
                "block": block["block"],
                "technical_block": block["technical_block"],
                "d1_training_seed": block["d1_training_seed"],
                "b1_attempts": len(block["b1_rows"]),
                "d1_attempts": len(block["d1_rows"]),
                "paired_row_count": block["paired_row_count"],
                "generation_seed_count": len(block["generation_seeds"]),
                "one_to_one": True,
                "is_training_replicate": False,
                "is_significance_test_unit": False,
            }
        )
    b1_total = sum(block["b1_attempts"] for block in public_blocks)
    d1_total = sum(block["d1_attempts"] for block in public_blocks)
    if b1_total != PRODUCTION_ATTEMPT_COUNTS["B1"] or d1_total != PRODUCTION_ATTEMPT_COUNTS["D1"]:
        raise M10ContractError("schedule_count_mismatch", "matched blocks do not cover 30000 B1 and 30000 D1 attempts")
    return {
        "status": "passed",
        "validation": "one_to_one_frozen_pairing_keys",
        "blocks": public_blocks,
        "b0_attempts_outside_blocks": outside["B0"],
        "b2_attempts_outside_blocks": outside["B2"],
        "b0_included_in_matched_blocks": False,
        "b2_included_in_matched_blocks": False,
        "cross_family_rows": 0,
        "missing_pairing_rows": 0,
        "duplicated_pairing_rows": 0,
        "extra_pairing_rows": 0,
    }


def _hash_frozen_inputs(root):
    """Hash frozen generated inputs and configuration. This does not open EVAL."""
    checks = (
        (SOURCE_MANIFEST_RELATIVE, FROZEN_SOURCE_MANIFEST_SHA256, "the source manifest"),
        (CONTRACT_RELATIVE_PATH, FROZEN_PARSER_CONTRACT_SHA256, "the parser contract"),
        (ACCOUNTING_SUMMARY_RELATIVE, FROZEN_ACCOUNTING_SHA256, "the parsing accounting summary"),
    )
    hashed = {}
    for relative, expected, label in checks:
        path = _allowlisted_path(root, relative)
        blob = _read_allowlisted_bytes(path)
        digest = _sha256_bytes(blob)
        if digest != expected:
            raise M10ContractError("frozen_configuration_mismatch", label + " hash is not the frozen hash")
        hashed[relative] = digest
    for condition in CONDITIONS:
        filename, expected = FROZEN_LEDGER_FILES[condition]
        relative = LEDGER_DIRECTORY + "/" + filename
        path = _allowlisted_path(root, relative)
        digest = _sha256_file(path)
        if digest != expected:
            raise M10ContractError("generated_ledger_hash_mismatch", condition + " ledger hash is not the frozen hash")
        hashed[relative] = digest
    return hashed


def verify_frozen_configuration_hashes(root):
    """Hash frozen inputs and require the pinned frozen metric specification.

    The frozen pre-EVAL gate uses this check. It also checks the frozen M9A
    summaries, the S6 parameter hash, and the three S7 hashes. It does not
    open EVAL. Production uses the separate frozen-spec gate before its own
    EVAL read.
    """
    hashed = _hash_frozen_inputs(root)
    decision = assert_production_metric_spec_gate(root)
    hashed.update(decision)
    hashed["metric_spec_role"] = "pinned_frozen_production_ready"
    train = load_allowlisted_train_summaries(root)
    hashed["m9a_train_summaries"] = {
        key: {"relative_path": train[key]["relative_path"], "sha256": train[key]["sha256"]} for key in ("exact", "nearest", "manifest")
    }
    hashed["s6_s7"] = assert_frozen_s6_and_s7(_code_hashes(root), _s6_provenance(root))
    return hashed


def validate_viennarna_evidence(evidence):
    """Refuse a ViennaRNA interpreter, version, or conda build that is not the pin."""
    if not isinstance(evidence, dict):
        raise M10ContractError("viennarna_evidence_invalid", "ViennaRNA evidence is not an object")
    if evidence.get("interpreter") != PINNED_INTERPRETER:
        raise M10ContractError("viennarna_interpreter_mismatch", "the interpreter is not the pinned H200 interpreter")
    if evidence.get("package_name") != VIENNA_PACKAGE:
        raise M10ContractError("viennarna_version_mismatch", "the folding package is not viennarna")
    if evidence.get("package_version") != VIENNA_VERSION or evidence.get("metadata_version") != VIENNA_VERSION:
        raise M10ContractError("viennarna_version_mismatch", "ViennaRNA is not exactly 2.7.0")
    if evidence.get("package_build") != VIENNA_BUILD:
        raise M10ContractError("viennarna_build_mismatch", "the ViennaRNA conda build is not py38pl5321hd78456e_0")
    if evidence.get("call") != VIENNA_CALL:
        raise M10ContractError("viennarna_call_mismatch", "the fold call is not RNA.fold(sequence)")
    if evidence.get("model_details_altered") is not False or evidence.get("model_details_set_by_code") is not False:
        raise M10ContractError("viennarna_model_altered", "model details must stay at the ViennaRNA 2.7.0 constructor defaults")
    return {
        "interpreter": PINNED_INTERPRETER,
        "python_version": evidence.get("python_version"),
        "package_name": VIENNA_PACKAGE,
        "package_version": VIENNA_VERSION,
        "metadata_version": VIENNA_VERSION,
        "package_build": VIENNA_BUILD,
        "metadata_path": evidence.get("metadata_path"),
        "call": VIENNA_CALL,
        "model_details_altered": False,
        "model_details_set_by_code": False,
        "distinct_from_aptarank_viennarna": "2.7.2",
    }


def collect_viennarna_evidence():
    """Read the pinned interpreter's ViennaRNA version and conda build. Do not fold."""
    interpreter = os.path.realpath(PINNED_INTERPRETER)
    current = os.path.realpath(sys.executable)
    if current != interpreter:
        raise M10ContractError("viennarna_interpreter_mismatch", "the interpreter is not the pinned H200 interpreter")
    import RNA

    version = getattr(RNA, "__version__", None)
    prefix = os.path.dirname(os.path.dirname(interpreter))
    meta_dir = os.path.join(prefix, "conda-meta")
    names = [
        name
        for name in os.listdir(meta_dir)
        if name.startswith("viennarna-") and name.endswith(".json")
    ]
    if len(names) != 1:
        raise M10ContractError("viennarna_build_mismatch", "ViennaRNA conda metadata is not a single installed package")
    meta_path = os.path.join(meta_dir, names[0])
    with open(meta_path, "r", encoding="utf-8") as handle:
        meta = json.load(handle)
    return validate_viennarna_evidence(
        {
            "interpreter": PINNED_INTERPRETER,
            "python_version": platform.python_version(),
            "package_name": meta.get("name"),
            "package_version": version,
            "metadata_version": meta.get("version"),
            "package_build": meta.get("build"),
            "metadata_path": meta_path,
            "call": VIENNA_CALL,
            "model_details_altered": False,
            "model_details_set_by_code": False,
        }
    )


def production_fold(sequence):
    """Fold one sequence with the pinned call.

    The call is exactly RNA.fold(sequence). This function does not construct
    or alter an RNA model.
    """
    import RNA

    return RNA.fold(sequence)


def run_synthetic_viennarna_smoke(evidence, fold=None):
    """Fold the synthetic fixture once. The result is not a scientific metric."""
    checked = validate_viennarna_evidence(evidence)
    folder = production_fold if fold is None else fold
    structure, energy = folder(SYNTHETIC_SMOKE_SEQUENCE)
    if not isinstance(structure, str) or len(structure) != len(SYNTHETIC_SMOKE_SEQUENCE):
        raise M10ContractError("fold_invalid", "the synthetic smoke structure length differs from the fixture")
    if isinstance(energy, bool) or not isinstance(energy, (int, float)):
        raise M10ContractError("fold_invalid", "the synthetic smoke energy is not a number")
    document = {
        "schema": SYNTHETIC_SMOKE_SCHEMA,
        "scientific_result": False,
        "fixture_role": "synthetic_rna_fold_smoke",
        "not_a_generator_evaluation_result": True,
        "biological_sequences_folded": False,
        "eval_sequences_folded": False,
        "sequence_sha256": _sha256_bytes(SYNTHETIC_SMOKE_SEQUENCE.encode("utf-8")),
        "sequence_length": len(SYNTHETIC_SMOKE_SEQUENCE),
        "structure_length": len(structure),
        "structure_length_matches_sequence": True,
        "mfe_is_number": True,
        "call": checked["call"],
        "package_version": checked["package_version"],
        "package_build": checked["package_build"],
        "interpreter": checked["interpreter"],
        "model_details_altered": False,
        "fold_calls": 1,
    }
    assert_public_report_sequence_free(document, [SYNTHETIC_SMOKE_SEQUENCE])
    return document


def summarize_cached_structure(sequences, fold, cache=None):
    """Fold each distinct valid sequence once and weight every attempt.

    Duplicate attempts reuse the cached fold. The summary reports MFE per
    nucleotide and paired fraction. It does not define a structure distance.
    """
    if cache is None:
        cache = {}
    summary = _structure_summary(list(sequences), fold, cache)
    if "structure_distance" in summary or summary.get("structure_distance_defined") is not False:
        raise M10ContractError("forbidden_output", "structure distance is outside M10")
    summary["distinct_sequences_folded_once"] = True
    summary["duplicate_attempts_reuse_cache"] = True
    return summary


def check_production_output_directory(output_dir):
    """Refuse an existing, linked, or protected production output path."""
    text = os.fspath(output_dir)
    _refuse_protected_path(text)
    if os.path.islink(text):
        raise M10ContractError("output_exists", "the output path is a symlink")
    _refuse_existing(text)


def read_frozen_eval_once(root):
    """Open the frozen EVAL file once. Callers must already hold authorization.

    Generated-input preflight does not call this. The protected-input refusal
    used for ledgers does not apply here, because this is the one authorized
    EVAL read.
    """
    root_abs = os.path.abspath(root)
    path = os.path.abspath(os.path.join(root, FROZEN_EVAL_RELATIVE))
    if os.path.commonpath([root_abs, path]) != root_abs or path != os.path.join(root_abs, FROZEN_EVAL_RELATIVE):
        raise M10ContractError("eval_path_refused", "the EVAL path is not the frozen file")
    if os.path.basename(path) != "eval.csv" or os.path.islink(path):
        raise M10ContractError("eval_path_refused", "the EVAL path is not a regular frozen file")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError as error:
        raise M10ContractError("eval_unreadable", "the frozen EVAL file is missing") from error
    except OSError as error:
        raise M10ContractError("eval_unreadable", "the frozen EVAL file could not be read") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise M10ContractError("eval_unreadable", "the frozen EVAL file is not a regular file")
        chunks = []
        while True:
            blob = os.read(descriptor, 1024 * 1024)
            if blob == b"":
                break
            chunks.append(blob)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def production_metric_spec_decision(document, digest, expected_sha256):
    """Decide whether production may open EVAL. This does not read a file.

    The on-disk draft and an unset ``FROZEN_METRIC_SPEC_SHA256`` fail closed.
    A hash-pinned candidate is then checked with the full metric-specification
    validator at ``require_draft=False``. That check requires top-level
    ``freeze_status`` frozen, every metric row frozen, contract
    ``document_status`` frozen, both production labels true, no unresolved
    blocking item, and the production reference role
    ``authorized_eval_unique_cores``. Membership, formulas, revisions, and
    dispositions are still checked. This does not read a file.
    """
    if not isinstance(document, dict) or document.get("freeze_status") != "frozen":
        raise M10ContractError("metric_spec_unfrozen", "production EVAL access requires a frozen metric specification")
    contract = document.get("m10_draft_contract")
    if (
        not isinstance(contract, dict)
        or contract.get("labelled_frozen") is not True
        or contract.get("labelled_production_ready") is not True
    ):
        raise M10ContractError(
            "metric_spec_unfrozen",
            "production EVAL access requires the metric specification to be labelled frozen and production-ready",
        )
    if not isinstance(expected_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None or digest != expected_sha256:
        raise M10ContractError("metric_spec_hash_unpinned", "the frozen metric-specification hash is not pinned")
    preflight = analysis._preflight()
    try:
        preflight.validate_metric_spec(document, require_draft=False)
    except preflight.GeneratorEvalContractError as error:
        raise M10ContractError(error.code, error.detail) from error
    return {
        "metric_spec_sha256": digest,
        "metric_spec_freeze_status": "frozen",
        "metric_spec_production_ready": True,
        "metric_spec_relative_path": METRIC_SPEC_RELATIVE,
    }


def assert_production_metric_spec_gate(root):
    """Read the metric specification and apply the production freeze gate.

    This does not open EVAL. A draft specification, stale draft wording, draft
    readiness, or an unpinned hash fails closed.
    """
    path = _allowlisted_path(root, METRIC_SPEC_RELATIVE)
    blob = _read_allowlisted_bytes(path)
    document = json.loads(blob.decode("utf-8"))
    return production_metric_spec_decision(document, _sha256_bytes(blob), FROZEN_METRIC_SPEC_SHA256)


def _require_production_spec_attestation(configuration):
    if not isinstance(configuration, dict):
        raise M10ContractError("metric_spec_unfrozen", "production configuration did not attest a frozen metric specification")
    if configuration.get("metric_spec_freeze_status") != "frozen" or configuration.get("metric_spec_production_ready") is not True:
        raise M10ContractError("metric_spec_unfrozen", "production requires a frozen and production-ready metric-specification attestation")
    digest = configuration.get("metric_spec_sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise M10ContractError("metric_spec_hash_unpinned", "production requires a pinned metric-specification hash attestation")


def _private_generated_rows(generated):
    rows = generated.get("private_adapted_rows") if isinstance(generated, dict) else None
    if not isinstance(rows, list) or not rows:
        raise M10ContractError("generated_rows_missing", "adapted generated rows were not retained for the production calculation")
    return rows


def _lookup(document, location):
    current = document
    for part in location.split("."):
        if not isinstance(current, dict) or part not in current:
            return None, False
        current = current[part]
    return current, True


def assert_metric_coverage_contract(root):
    """Require every retained metric to have an explicit production disposition."""
    path = _allowlisted_path(root, METRIC_SPEC_RELATIVE)
    blob = _read_allowlisted_bytes(path)
    if b"unavailable pending a defined aggregation" in blob:
        raise M10ContractError("metric_coverage_incomplete", "the metric specification still has an undefined aggregation")
    document = json.loads(blob.decode("utf-8"))
    coverage = document.get("m10_production_metric_coverage")
    expected = [dict(item) for item in PRODUCTION_METRIC_COVERAGE]
    if coverage != expected:
        raise M10ContractError("metric_coverage_incomplete", "production metric coverage does not match the specification")
    retained = {item["metric_id"] for item in document.get("metrics", [])}
    retained.update(item["metric_id"] for item in document.get("d1_metric_aggregation", []))
    covered = {item["metric_id"] for item in coverage}
    missing = sorted(retained - covered)
    if missing:
        raise M10ContractError("metric_coverage_incomplete", "retained metrics lack a production disposition: " + ", ".join(missing))
    by_id = {item["metric_id"]: item for item in coverage}
    for item in document.get("d1_metric_aggregation", []):
        metric_id = item.get("metric_id")
        entry = by_id.get(metric_id)
        if entry is None:
            continue
        if entry["disposition"] in ("inherited_frozen_m9a", "audit_only"):
            continue
        if entry["aggregation_basis"] != item.get("aggregation_basis"):
            raise M10ContractError(
                "metric_coverage_incomplete",
                str(metric_id) + " aggregation basis does not match its production disposition",
            )
    return expected


def _coverage_location_present(report, entry):
    current, found = _lookup(report, entry["output_location"])
    if not found:
        return False
    field = entry.get("field")
    if field is None:
        return True
    if not isinstance(current, dict):
        return False
    if set(CONDITIONS) <= set(current):
        return all(isinstance(current[condition], dict) and field in current[condition] for condition in CONDITIONS)
    return field in current


def assert_metric_coverage_locations(report):
    for entry in PRODUCTION_METRIC_COVERAGE:
        if "unavailable pending" in entry["aggregation_basis"]:
            raise M10ContractError("metric_coverage_incomplete", entry["metric_id"] + " still has an undefined aggregation")
        if not _coverage_location_present(report, entry):
            raise M10ContractError("metric_coverage_incomplete", entry["metric_id"] + " has no production output at " + entry["output_location"])
        if entry.get("b0_requested_length") == "not_applicable":
            location = entry["output_location"] + ".B0"
            if entry.get("field"):
                location += "." + entry["field"]
            b0, found = _lookup(report, location)
            if (
                not found
                or not isinstance(b0, dict)
                or b0.get("applicability") != "not_applicable"
                or b0.get("requested_length") != "unavailable"
            ):
                raise M10ContractError("b0_requested_length_unavailable", entry["metric_id"] + " invents a B0 requested length")


def _rate(numerator, denominator):
    if denominator == 0:
        return None
    return numerator / denominator


def _not_applicable_length():
    return {
        "applicability": "not_applicable",
        "value": None,
        "requested_length": "unavailable",
        "reason": "b0_requested_biological_length_unavailable",
    }


def _integer_histogram(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [{"value": key, "count": counts[key]} for key in sorted(counts)]


def _duplicate_block(sequences):
    histogram = analysis.multiplicity_histogram(sequences) if sequences else []
    if not sequences:
        return {
            "unique_valid_outputs": 0,
            "duplicates": 0,
            "duplicate_excess": 0,
            "largest_duplicate_multiplicity": 0,
            "largest_duplicate_share": None,
            "largest_duplicate_share_denominator": 0,
            "unique_fraction": None,
            "unique_fraction_denominator": 0,
            "multiplicity_histogram": histogram,
            "duplicate_rows_retained": True,
            "unique_only_is_primary": False,
        }
    counts = {}
    for sequence in sequences:
        counts[sequence] = counts.get(sequence, 0) + 1
    unique = len(counts)
    multiplicity = max(counts.values())
    return {
        "unique_valid_outputs": unique,
        "duplicates": len(sequences) - unique,
        "duplicate_excess": len(sequences) - unique,
        "largest_duplicate_multiplicity": multiplicity,
        "largest_duplicate_share": multiplicity / len(sequences),
        "largest_duplicate_share_denominator": len(sequences),
        "unique_fraction": unique / len(sequences),
        "unique_fraction_denominator": len(sequences),
        "multiplicity_histogram": histogram,
        "duplicate_rows_retained": True,
        "unique_only_is_primary": False,
    }


def _production_structure_summary(sequences, fold, cache):
    quantiles = analysis._m6()
    if not sequences:
        return {
            "fold_calls_for_new_sequences": 0,
            "valid_row_denominator": 0,
            "distinct_valid_sequence_count": 0,
            "duplicate_attempts_reuse_cache": True,
            "mfe": None,
            "mfe_per_nt": None,
            "paired_fraction": None,
            "aggregation": AGGREGATION_VALID_ROW_QUANTILES,
            "fold_population": "each distinct valid sequence once",
            "quantile_population": "valid attempt rows with duplicate-attempt weighting",
            "equal_seed_pooled": False,
            "structure_distance_defined": False,
        }
    before = len(cache)
    features = [_fold_cached(sequence, fold, cache) for sequence in sequences]
    return {
        "fold_calls_for_new_sequences": len(cache) - before,
        "valid_row_denominator": len(sequences),
        "distinct_valid_sequence_count": len(set(sequences)),
        "duplicate_attempts_reuse_cache": True,
        "mfe": quantiles._quantiles([item["mfe"] for item in features]),
        "mfe_per_nt": quantiles._quantiles([item["mfe_per_nt"] for item in features]),
        "paired_fraction": quantiles._quantiles([item["paired_fraction"] for item in features]),
        "aggregation": AGGREGATION_VALID_ROW_QUANTILES,
        "fold_population": "each distinct valid sequence once",
        "quantile_population": "valid attempt rows with duplicate-attempt weighting",
        "equal_seed_pooled": False,
        "structure_distance_defined": False,
    }


def _production_composition(sequences):
    if not sequences:
        return {
            "sequence_count": 0,
            "valid_row_denominator": 0,
            "nucleotide_fractions": None,
            "dinucleotide_fractions": None,
            "gc_fraction": None,
            "duplicate_rows_retained": True,
        }
    composed = _composition(sequences)
    composed["valid_row_denominator"] = len(sequences)
    composed["duplicate_rows_retained"] = True
    return composed


def _length_distributions(rows, applicable):
    observed = [row["observed_length"] for row in rows if type(row.get("observed_length")) is int]
    cleaned = {
        "count": len(observed),
        "null_observed_length_count": len(rows) - len(observed),
        "histogram": _integer_histogram(observed),
        "quantiles": analysis._m6()._quantiles(observed) if observed else None,
    }
    if not applicable:
        absent = _not_applicable_length()
        absent["histogram"] = []
        return {"cleaned_length_distribution": cleaned, "length_shortfall_distribution": absent, "length_excess_distribution": absent}
    shortfalls = []
    excesses = []
    for row in rows:
        observed_length = row.get("observed_length")
        requested = row.get("requested_length")
        if type(observed_length) is not int or type(requested) is not int:
            continue
        if observed_length < requested:
            shortfalls.append(requested - observed_length)
        elif observed_length > requested:
            excesses.append(observed_length - requested)
    return {
        "cleaned_length_distribution": cleaned,
        "length_shortfall_distribution": {"applicability": "applicable", "histogram": _integer_histogram(shortfalls), "count": len(shortfalls)},
        "length_excess_distribution": {"applicability": "applicable", "histogram": _integer_histogram(excesses), "count": len(excesses)},
    }


def _exact_hit_fields(rows, applicable):
    if not applicable:
        absent = _not_applicable_length()
        return {
            "exact_length_hits": absent,
            "exact_hit_rate": absent,
            "exact_hit_rate_valid_outputs_diagnostic": absent,
        }
    hits = sum(
        row["is_valid_canonical"] is True and row["observed_length"] == row["requested_length"]
        for row in rows
    )
    valid = sum(row["is_valid_canonical"] is True for row in rows)
    attempts = len(rows)
    return {
        "exact_length_hits": {"applicability": "applicable", "value": hits, "denominator": "raw_attempts", "denominator_count": attempts},
        "exact_hit_rate": {
            "applicability": "applicable",
            "value": _rate(hits, attempts),
            "denominator": "raw_attempts",
            "denominator_count": attempts,
        },
        "exact_hit_rate_valid_outputs_diagnostic": {
            "applicability": "applicable",
            "value": 0.0 if valid == 0 else hits / valid,
            "denominator": "valid_outputs",
            "denominator_count": valid,
            "label": "valid_outputs_only_diagnostic_not_the_approved_metric",
            "replaces_approved_raw_attempt_metric": False,
        },
    }


def _requested_length_block(condition, rows, reference, fold, cache):
    if condition == "B0":
        return {
            "applicability": "not_applicable",
            "requested_length": "unavailable",
            "reason": "b0_requested_biological_length_unavailable",
            "strata": [],
        }
    grouped = {}
    for row in rows:
        grouped.setdefault(row["requested_length"], []).append(row)
    strata = []
    for length in sorted(grouped):
        selected = grouped[length]
        sequences = _valid_sequences(selected)
        hits = sum(row["is_valid_canonical"] is True and row["observed_length"] == length for row in selected)
        valid = len(sequences)
        strata.append(
            {
                "requested_length": length,
                "raw_attempts": len(selected),
                "valid_row_denominator": valid,
                "exact_length_hits": hits,
                "exact_hit_rate": _rate(hits, len(selected)),
                "exact_hit_rate_denominator": "raw_attempts",
                "exact_hit_rate_valid_outputs_diagnostic": {
                    "value": 0.0 if valid == 0 else hits / valid,
                    "denominator": "valid_outputs",
                    "denominator_count": valid,
                    "replaces_approved_raw_attempt_metric": False,
                },
                "structure": _production_structure_summary(sequences, fold, cache),
                "closeness": _public_closeness(sequences, reference),
            }
        )
    return {"applicability": "applicable", "requested_length": "recorded", "strata": strata}


def _population_report(condition, rows, reference, fold, cache):
    sequences = _valid_sequences(rows)
    applicable = condition != "B0"
    attempts = len(rows)
    valid = len(sequences)
    empty = sum(row["outcome"] in ("empty_output", "unparseable_output", "non_sequence_output") for row in rows)
    duplicates = _duplicate_block(sequences)
    lengths = _length_distributions(rows, applicable)
    hits = _exact_hit_fields(rows, applicable)
    failures = {}
    for row in rows:
        if row["failure_reason"] is None:
            continue
        failures[row["failure_reason"]] = failures.get(row["failure_reason"], 0) + 1
    metrics = {
        "raw_attempts": attempts,
        "parsed_outputs": {
            "value": attempts,
            "label": "internal_schema_valid_record_audit",
            "thesis_facing": False,
        },
        "successfully_parsed_outputs": analysis.successfully_parsed_outputs(rows),
        "valid_outputs": valid,
        "invalid_outputs": attempts - valid,
        "empty_or_unparseable_outputs": empty,
        "valid_nonempty_acgu_fraction": _rate(valid, attempts),
        "empty_or_unparseable_fraction": _rate(empty, attempts),
        "actual_attempt_level_validity_rate": _rate(valid, attempts),
        "failure_reason_counts": failures,
        "unique_valid_outputs": duplicates["unique_valid_outputs"],
        "duplicates": duplicates["duplicates"],
        "cleaned_length_distribution": lengths["cleaned_length_distribution"],
        "length_shortfall_distribution": lengths["length_shortfall_distribution"],
        "length_excess_distribution": lengths["length_excess_distribution"],
        "denominators": {
            "raw_attempts": attempts,
            "valid_outputs": valid,
            "unique_valid_outputs": duplicates["unique_valid_outputs"],
            "reference_unique_cores": len(reference),
        },
        **hits,
    }
    return {
        "metrics": metrics,
        "exact_duplicate_diversity": duplicates,
        "composition": _production_composition(sequences),
        "structure": _production_structure_summary(sequences, fold, cache),
        "closeness": _public_closeness(sequences, reference),
        "by_requested_length": _requested_length_block(condition, rows, reference, fold, cache),
    }


def _headlines_from_public(closeness):
    nearest = closeness["nearest_reference_normalized_edit_distance"]
    return {
        "nearest_reference_normalized_edit_distance.median": nearest.get("median", nearest.get("value")),
        "nucleotide_total_variation_to_reference": closeness["nucleotide_total_variation_to_reference"].get("value"),
        "dinucleotide_total_variation_to_reference": closeness["dinucleotide_total_variation_to_reference"].get("value"),
    }


def _with_agreement(result):
    label = result["label"]
    if label == "mixed":
        agreement = "disagreement"
    elif label == "not_applicable":
        agreement = "not_applicable"
    else:
        agreement = "agreement"
    combined = dict(result)
    combined["agreement"] = agreement
    combined["agreement_is_a_score"] = False
    return combined


def _observed_numeric_range(values):
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        return {
            "minimum": None,
            "maximum": None,
            "is_confidence_interval": False,
            "undefined_reason": "missing_seed_value",
        }
    return {
        "minimum": min(values),
        "maximum": max(values),
        "is_confidence_interval": False,
        "bootstrap_produced": False,
        "hypothesis_test_produced": False,
    }


def _seed_id_range(values):
    present = [value for value in values if type(value) is int]
    if not present:
        return {"count": 0, "minimum": None, "maximum": None, "is_confidence_interval": False, "values_are_training_replicates": False}
    ordered = sorted(set(present))
    return {
        "count": len(ordered),
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "is_confidence_interval": False,
        "values_are_training_replicates": False,
    }


def _nearest_distances(sequences, cores):
    metrics = analysis._m6()
    nearest = {}
    for sequence in sorted(set(sequences)):
        nearest[sequence] = metrics.nearest_train(sequence, cores)
    return nearest


def _annotate_generated(rows, nearest, fold, cache):
    records = []
    for row in rows:
        applicable = row["condition"] != "B0"
        sequence = row["sequence"] if row["is_valid_canonical"] is True else None
        if isinstance(sequence, str):
            already_folded = sequence in cache
            features = _fold_cached(sequence, fold, cache)
            fold_cache_disposition = "reused_from_earlier_row" if already_folded else "computed_on_this_row"
        else:
            features = None
            fold_cache_disposition = "not_folded"
        if applicable:
            exact_hit = {
                "applicability": "applicable",
                "value": bool(row["is_valid_canonical"] is True and row["observed_length"] == row["requested_length"]),
                "requested_length": row["requested_length"],
            }
            requested = row["requested_length"]
        else:
            exact_hit = _not_applicable_length()
            requested = None
        records.append(
            {
                "record_id": row["record_id"],
                "condition": row["condition"],
                "outcome": row["outcome"],
                "failure_reason": row["failure_reason"],
                "is_valid_canonical": row["is_valid_canonical"],
                "sequence": row.get("sequence"),
                "observed_length": row.get("observed_length"),
                "requested_length": requested,
                "requested_length_applicability": "applicable" if applicable else "not_applicable",
                "exact_length_hit": exact_hit,
                "s6_length_stratum": row.get("s6_length_stratum"),
                "s6_length_stratum_applicability": row.get("s6_length_stratum_applicability"),
                "valid_sequence_multiplicity": row.get("valid_sequence_multiplicity"),
                "is_exact_duplicate_within_condition": row.get("is_exact_duplicate_within_condition"),
                "checkpoint_identity": row.get("checkpoint_identity"),
                "d1_training_seed": row.get("d1_training_seed"),
                "technical_block": row.get("technical_block"),
                "generation_seed": row.get("generation_seed"),
                "master_attempt_index": row.get("master_attempt_index"),
                "within_batch_position": row.get("within_batch_position"),
                "invocation_index": row.get("invocation_index"),
                "b0_seed": row.get("b0_seed"),
                "b0_chunk_id": row.get("b0_chunk_id"),
                "attempt_index": row.get("attempt_index"),
                "empirical_null_seed": row.get("empirical_null_seed"),
                "cleaning_status": row.get("cleaning_status"),
                "cleaning_version": row.get("cleaning_version"),
                "source_artifact_sha256": row.get("source_artifact_sha256"),
                "mfe": None if features is None else features["mfe"],
                "mfe_per_nt": None if features is None else features["mfe_per_nt"],
                "paired_fraction": None if features is None else features["paired_fraction"],
                "nearest_reference_normalized_edit_distance": None if sequence is None else nearest[sequence],
                "fold_cache_disposition": fold_cache_disposition,
            }
        )
    return records


def _annotate_cores(cores, fold, cache):
    annotated = []
    for core in cores:
        features = _fold_cached(core["sequence_core"], fold, cache)
        annotated.append(
            {
                "sequence_id": core["sequence_id"],
                "sequence_core": core["sequence_core"],
                "cluster_id": core["cluster_id"],
                "s6_length_stratum": core["s6_length_stratum"],
                "identity_count": core["identity_count"],
                "weight": 1,
                "included_once": True,
                "mfe": features["mfe"],
                "mfe_per_nt": features["mfe_per_nt"],
                "paired_fraction": features["paired_fraction"],
            }
        )
    return annotated


def _equal_seed_validity(d1_rows):
    per_seed = {}
    rates = []
    missing = False
    for seed in (43, 44):
        selected = [row for row in d1_rows if row["d1_training_seed"] == seed]
        attempts = len(selected)
        valid = sum(row["is_valid_canonical"] is True for row in selected)
        rate = _rate(valid, attempts)
        per_seed[str(seed)] = {"raw_attempts": attempts, "valid_outputs": valid, "rate": rate}
        if rate is None:
            missing = True
        else:
            rates.append(rate)
    return {
        "aggregation_basis": AGGREGATION_EQUAL_SEED,
        "per_d1_training_seed": per_seed,
        "value": None if missing or len(rates) != 2 else sum(rates) / 2.0,
        "undefined_reason": "missing_seed" if missing else None,
        "is_confidence_interval": False,
    }


def _assert_production_metadata(report):
    """Reject inactive synthetic flags on a production report."""
    if report.get("schema") != PRODUCTION_SCHEMA or report.get("status") != "section5_calculation_complete":
        raise M10ContractError("production_metadata_invalid", "production output reused the synthetic pathway metadata")
    if report.get("layer") != "sequence_free_aggregate_report" or report.get("contains_sequences") is not False:
        raise M10ContractError("production_metadata_invalid", "the public production report is not the sequence-free layer")
    if report.get("eval_opened") is not True or report.get("eval_read_count") != 1 or report.get("viennarna_called") is not True:
        raise M10ContractError("production_metadata_invalid", "production metadata reused an inactive synthetic flag")
    if report.get("viennarna_call") != VIENNA_CALL:
        raise M10ContractError("production_metadata_invalid", "production folding is not the pinned RNA.fold(sequence) call")
    attestation = report.get("metric_spec")
    if (
        not isinstance(attestation, dict)
        or attestation.get("freeze_status") == "draft"
        or attestation.get("production_ready") is not True
        or attestation.get("source") != "production_gate_attestation"
    ):
        raise M10ContractError("production_metadata_invalid", "production metadata reused the draft metric-specification flag")
    if "synthetic_inactive_pathway" in json.dumps(report):
        raise M10ContractError("production_metadata_invalid", "production metadata reused the synthetic inactive pathway status")


def _inherited_disposition(metric_id):
    return {
        "metric_id": metric_id,
        "disposition": "inherited_frozen_m9a",
        "recomputed": False,
        "separate_metric_id": False,
        "is_a_closeness_metric": False,
        "is_a_quality_vote": False,
        "reason": AGGREGATION_TRAIN_NESTED,
    }


def _unique_present(rows, key):
    values = []
    seen = set()
    for row in rows:
        value = row.get(key)
        if value is None or value in seen:
            continue
        seen.add(value)
        values.append(value)

    def sort_key(item):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return (1, str(item))
        return (0, item)

    return sorted(values, key=sort_key)


def _provenance_by_condition(rows):
    """Compact sequence-free provenance. Record identifiers stay off this summary."""
    summary = {}
    for condition in CONDITIONS:
        selected = [row for row in rows if row["condition"] == condition]
        neural = condition in ("B1", "D1")
        cleaning = {}
        for row in selected:
            status = row.get("cleaning_status")
            if not isinstance(status, str):
                status = "missing"
            cleaning[status] = cleaning.get(status, 0) + 1
        summary[condition] = {
            "attempt_count": len(selected),
            "checkpoint_identities": _unique_present(selected, "checkpoint_identity") if neural else [],
            "d1_training_seeds": _unique_present(selected, "d1_training_seed") if condition == "D1" else [],
            "technical_blocks": _unique_present(selected, "technical_block") if neural else [],
            "generation_seed_range": _seed_id_range([row.get("generation_seed") for row in selected] if neural else []),
            "master_attempt_index_range": _seed_id_range([row.get("master_attempt_index") for row in selected] if neural else []),
            "within_batch_position_range": _seed_id_range(
                [row.get("within_batch_position") for row in selected] if neural else []
            ),
            "invocation_index_range": _seed_id_range([row.get("invocation_index") for row in selected] if neural else []),
            "b0_seed_range": _seed_id_range([row.get("b0_seed") for row in selected] if condition == "B0" else []),
            "b0_chunk_ids": _unique_present(selected, "b0_chunk_id") if condition == "B0" else [],
            "b2_attempt_index_range": _seed_id_range([row.get("attempt_index") for row in selected] if condition == "B2" else []),
            "empirical_null_seeds": _unique_present(selected, "empirical_null_seed") if condition == "B2" else [],
            "requested_length": "unavailable" if condition == "B0" else _unique_present(selected, "requested_length"),
            "observed_length_recorded_count": sum(type(row.get("observed_length")) is int for row in selected),
            "cleaning_status_counts": cleaning,
            "cleaning_versions": _unique_present(selected, "cleaning_version"),
            "source_artifact_sha256": _unique_present(selected, "source_artifact_sha256"),
            "record_identifiers_emitted": False,
            "sequences_emitted": False,
        }
    return summary


def build_production_reports(rows, evaluation, train, fold, root, configuration, environment, code_hashes, s6_provenance):
    """Calculate Section 5 from private generated rows and one adapted EVAL payload.

    ``code_hashes`` is the broad inventory captured before EVAL. It is not a
    pin of every inventoried file. Metric-calculation revisions stay validated
    through the metric specification. ``s6_provenance`` is the captured S6
    record. The frozen parameter-record hash and the three S7 file hashes are
    required again here so a report cannot be built from a mismatched capture.
    This function does not rediscover those dependencies and does not open EVAL.
    """
    if root is None or not isinstance(code_hashes, dict) or set(HASHED_CODE_PATHS) - set(code_hashes):
        raise M10ContractError("code_inventory_missing", "production code hashes were not captured before EVAL")
    if not isinstance(s6_provenance, dict) or not isinstance(s6_provenance.get("parameter_sha256"), str):
        raise M10ContractError("s6_provenance_missing", "S6 provenance was not captured before EVAL")
    frozen_dependencies = assert_frozen_s6_and_s7(code_hashes, s6_provenance)
    if not callable(fold):
        raise M10ContractError("fold_not_injected", "production folding requires the pinned fold wrapper")
    reference_cores = [core["sequence_core"] for core in evaluation["cores"]]
    if len(reference_cores) != len(set(reference_cores)):
        raise M10ContractError("duplicate_eval_core", "production reference cores are not unique")
    if any(core.get("weight") != 1 for core in evaluation["cores"]):
        raise M10ContractError("eval_count_mismatch", "an EVAL core is not weighted once")
    cache = {}
    nearest = _nearest_distances(_valid_sequences(rows), reference_cores)
    derived_records = _annotate_generated(rows, nearest, fold, cache)
    derived_cores = _annotate_cores(evaluation["cores"], fold, cache)
    by_condition = {}
    for condition in CONDITIONS:
        by_condition[condition] = _population_report(
            condition,
            [row for row in rows if row["condition"] == condition],
            reference_cores,
            fold,
            cache,
        )
    d1_rows = [row for row in rows if row["condition"] == "D1"]
    per_seed = {}
    per_seed_structure = {}
    for seed in (43, 44):
        selected = [row for row in d1_rows if row["d1_training_seed"] == seed]
        per_seed[str(seed)] = _population_report("D1", selected, reference_cores, fold, cache)
        per_seed_structure[str(seed)] = per_seed[str(seed)]["structure"]
    equal_seed = _equal_seed_closeness(d1_rows, reference_cores)
    blocks = []
    block_direction = {}
    for bound in bind_matched_blocks(rows):
        b1_sequences = _valid_sequences(bound["b1_rows"])
        d1_sequences = _valid_sequences(bound["d1_rows"])
        b1_closeness = _public_closeness(b1_sequences, reference_cores)
        d1_closeness = _public_closeness(d1_sequences, reference_cores)
        direction = _with_agreement(analysis.directional_consistency(_headlines_from_public(b1_closeness), _headlines_from_public(d1_closeness)))
        block_direction[bound["block"]] = direction
        blocks.append(
            {
                "block": bound["block"],
                "technical_block": bound["technical_block"],
                "d1_training_seed": bound["d1_training_seed"],
                "generation_seed_range": _seed_id_range([row["generation_seed"] for row in bound["b1_rows"]]),
                "paired_row_count": bound["paired_row_count"],
                "is_training_replicate": False,
                "is_significance_test_unit": False,
                "attempts_are_training_replicates": False,
                "b1_closeness": b1_closeness,
                "d1_closeness": d1_closeness,
                "b1_structure": _production_structure_summary(b1_sequences, fold, cache),
                "d1_structure": _production_structure_summary(d1_sequences, fold, cache),
                "directional_consistency": direction,
            }
        )
    b1_headlines = _headlines_from_public(by_condition["B1"]["closeness"])
    d1_headlines = {
        "nearest_reference_normalized_edit_distance.median": equal_seed["nearest_reference_normalized_edit_distance"]["value"],
        "nucleotide_total_variation_to_reference": equal_seed["nucleotide_total_variation_to_reference"]["value"],
        "dinucleotide_total_variation_to_reference": equal_seed["dinucleotide_total_variation_to_reference"]["value"],
    }
    seed_blocks = per_seed
    observed_ranges = {
        "exact_hit_rate": _observed_numeric_range([seed_blocks[seed]["metrics"]["exact_hit_rate"]["value"] for seed in ("43", "44")]),
        "valid_nonempty_acgu_fraction": _observed_numeric_range(
            [seed_blocks[seed]["metrics"]["valid_nonempty_acgu_fraction"] for seed in ("43", "44")]
        ),
        "empty_or_unparseable_fraction": _observed_numeric_range(
            [seed_blocks[seed]["metrics"]["empty_or_unparseable_fraction"] for seed in ("43", "44")]
        ),
        "unique_fraction": _observed_numeric_range(
            [seed_blocks[seed]["exact_duplicate_diversity"]["unique_fraction"] for seed in ("43", "44")]
        ),
        "largest_duplicate_share": _observed_numeric_range(
            [seed_blocks[seed]["exact_duplicate_diversity"]["largest_duplicate_share"] for seed in ("43", "44")]
        ),
        "pooled_gc_fraction": _observed_numeric_range([seed_blocks[seed]["composition"]["gc_fraction"] for seed in ("43", "44")]),
        "nearest_reference_normalized_edit_distance": _observed_numeric_range(
            [
                seed_blocks[seed]["closeness"]["nearest_reference_normalized_edit_distance"].get("median")
                for seed in ("43", "44")
            ]
        ),
        "nucleotide_total_variation_to_reference": _observed_numeric_range(
            [seed_blocks[seed]["closeness"]["nucleotide_total_variation_to_reference"].get("value") for seed in ("43", "44")]
        ),
        "dinucleotide_total_variation_to_reference": _observed_numeric_range(
            [seed_blocks[seed]["closeness"]["dinucleotide_total_variation_to_reference"].get("value") for seed in ("43", "44")]
        ),
        "mfe": _observed_numeric_range(
            [
                None if seed_blocks[seed]["structure"]["mfe"] is None else seed_blocks[seed]["structure"]["mfe"]["median"]
                for seed in ("43", "44")
            ]
        ),
        "mfe_per_nt": _observed_numeric_range(
            [
                None
                if seed_blocks[seed]["structure"]["mfe_per_nt"] is None
                else seed_blocks[seed]["structure"]["mfe_per_nt"]["median"]
                for seed in ("43", "44")
            ]
        ),
        "paired_fraction": _observed_numeric_range(
            [
                None
                if seed_blocks[seed]["structure"]["paired_fraction"] is None
                else seed_blocks[seed]["structure"]["paired_fraction"]["median"]
                for seed in ("43", "44")
            ]
        ),
        "is_confidence_interval": False,
    }
    b0_rows = [row for row in rows if row["condition"] == "B0"]
    b2_rows = [row for row in rows if row["condition"] == "B2"]
    fold_count = len(cache)
    attestation = {
        "source": "production_gate_attestation",
        "freeze_status": configuration["metric_spec_freeze_status"],
        "production_ready": configuration["metric_spec_production_ready"],
        "sha256": configuration["metric_spec_sha256"],
    }
    derived = {
        "layer": "protected_derived_evidence",
        "schema": PRODUCTION_SCHEMA,
        "contains_sequences": True,
        "production_eval_opened": True,
        "records": derived_records,
        "eval_cores": derived_cores,
        "distinct_fold_count": fold_count,
        "eval_cores_weighted_once": True,
        "duplicate_attempts_reuse_fold_cache": True,
    }
    report = {
        "layer": "sequence_free_aggregate_report",
        "schema": PRODUCTION_SCHEMA,
        "status": "section5_calculation_complete",
        "contains_sequences": False,
        "production_execution_authorized": True,
        "eval_opened": True,
        "eval_read_count": 1,
        "viennarna_called": fold_count > 0,
        "viennarna_call": VIENNA_CALL,
        "generator_viennarna_required": VIENNA_VERSION,
        "aptarank_viennarna_distinct": "2.7.2",
        "metric_spec": attestation,
        "s6_assignment": s6_provenance,
        "provenance_by_condition": _provenance_by_condition(rows),
        "reference": {
            "role": evaluation["role"],
            "sha256": evaluation["sha256"],
            "identity_count": evaluation["identity_count"],
            "unique_core_count": evaluation["unique_core_count"],
            "cluster_count": evaluation["cluster_count"],
            "short_core_count": evaluation["short_core_count"],
            "long_core_count": evaluation["long_core_count"],
            "cores_weighted_once": True,
            "clusters_weight_formulas": False,
            "clusters_trigger_resampling": False,
            "sequences_emitted": False,
        },
        "denominators": {
            "generated_distribution": "valid_attempt_rows_with_duplicates_retained",
            "reference_unique_cores": len(reference_cores),
            "reference_core_weight": 1,
            "distinct_folded_sequences": None,
            "by_condition": {
                condition: {
                    "raw_attempts": by_condition[condition]["metrics"]["denominators"]["raw_attempts"],
                    "valid_outputs_duplicates_retained": by_condition[condition]["metrics"]["denominators"]["valid_outputs"],
                    "unique_valid_outputs": by_condition[condition]["metrics"]["denominators"]["unique_valid_outputs"],
                    "reference_unique_cores": len(reference_cores),
                }
                for condition in CONDITIONS
            },
        },
        "metrics": {"by_condition": {condition: by_condition[condition]["metrics"] for condition in CONDITIONS}},
        "exact_duplicate_diversity": {
            "by_condition": {condition: by_condition[condition]["exact_duplicate_diversity"] for condition in CONDITIONS}
        },
        "composition": {"by_condition": {condition: by_condition[condition]["composition"] for condition in CONDITIONS}},
        "structure": {
            "by_condition": {condition: by_condition[condition]["structure"] for condition in CONDITIONS},
            "by_s6_length_stratum": {
                condition: {
                    label: _production_structure_summary(
                        _valid_sequences([row for row in rows if row["condition"] == condition and row.get("s6_length_stratum") == label]),
                        fold,
                        cache,
                    )
                    for label in S6_LABELS
                }
                for condition in CONDITIONS
            },
            "by_d1_training_seed": per_seed_structure,
            "by_matched_block": {
                block["block"]: {"b1": block["b1_structure"], "d1": block["d1_structure"]} for block in blocks
            },
            "eval_cores": _production_structure_summary(reference_cores, fold, cache),
            "distinct_fold_count": fold_count,
            "duplicate_attempts_reuse_cache": True,
            "population": {
                "distinct_valid_sequences_folded_once": True,
                "generated_quantiles": "valid attempt rows with duplicate-attempt weighting",
                "quantile_scopes": ["condition", "training_seed", "matched_block"],
                "eval_unique_cores_once_each": True,
                "eval_core_weight": 1,
            },
            "equal_seed_pooled": False,
            "structure_distance_defined": False,
        },
        "closeness": {
            "by_condition": {condition: by_condition[condition]["closeness"] for condition in CONDITIONS},
            "d1_equal_seed": equal_seed,
            "by_matched_block": {block["block"]: {"b1": block["b1_closeness"], "d1": block["d1_closeness"]} for block in blocks},
            "cores_weighted_once": True,
            "clusters_weight_formulas": False,
            "combined": False,
        },
        "by_requested_length": {condition: by_condition[condition]["by_requested_length"] for condition in CONDITIONS},
        "d1_by_training_seed": per_seed,
        "d1_equal_seed": {
            "mean_validity_rate": _equal_seed_validity(d1_rows),
            "closeness": equal_seed,
            "pooled_gc_fraction": equal_seed["pooled_gc_fraction"],
        },
        "matched_blocks": blocks,
        "directional_consistency": {
            "b1_versus_d1": _with_agreement(analysis.directional_consistency(b1_headlines, d1_headlines)),
            "by_matched_block": block_direction,
        },
        "observed_range_across_training_seeds": observed_ranges,
        "observed_generation_seed_ranges": {
            "B0": _seed_id_range([row["b0_seed"] for row in b0_rows]),
            "B2": {
                "empirical_null_seed": b2_rows[0]["empirical_null_seed"],
                "count": 1,
                "single_seed_limitation": True,
                "is_confidence_interval": False,
                "values_are_training_replicates": False,
            },
            "matched_blocks": {block["block"]: block["generation_seed_range"] for block in blocks},
            "is_confidence_interval": False,
        },
        "frozen_m9a_train": _train_view(train),
        "inherited_dispositions": {
            "nucleotide_total_variation_to_train": _inherited_disposition("nucleotide_total_variation_to_train"),
            "dinucleotide_total_variation_to_train": _inherited_disposition("dinucleotide_total_variation_to_train"),
        },
        "audit_only": {
            "eos_marker_observations": {"disposition": "audit_only", "value": None, "imputed": False, "reason": AGGREGATION_NOT_ON_LEDGER},
            "early_eos_observations": {"disposition": "audit_only", "value": None, "imputed": False, "reason": AGGREGATION_NOT_ON_LEDGER},
            "parsed_outputs": {
                "disposition": "audit_only",
                "label": "internal_schema_valid_record_audit",
                "thesis_facing": False,
            },
        },
        "metric_coverage": [dict(item) for item in PRODUCTION_METRIC_COVERAGE],
        "b0_panel": {
            "included_in_matched_b1_d1_comparison": False,
            "length_regime": "historical_37nt",
            "nominal_max_seq_len": 37,
            "requested_length": "unavailable",
            "exact_hit_rate": by_condition["B0"]["metrics"]["exact_hit_rate"],
            "historical_generation_seed_range": _seed_id_range([row["b0_seed"] for row in b0_rows]),
        },
        "b2_limitations": {
            "empirical_null_seed": b2_rows[0]["empirical_null_seed"],
            "empirical_null_seed_count": 1,
            "single_seed_limitation": True,
            "rows_are_training_replicates": False,
            "included_in_matched_blocks": False,
        },
        "environment": environment,
        "code_inventory_disposition": frozen_dependencies["code_inventory_disposition"],
        "code_and_configuration_hashes": code_hashes,
        "production_runner_path": frozen_dependencies["production_runner_path"],
        "production_runner_sha256": frozen_dependencies["production_runner_sha256"],
        "metric_calculation_revisions": frozen_dependencies["metric_calculation_revisions"],
        "frozen_s6_parameter_sha256": frozen_dependencies["s6_parameter_sha256"],
        "frozen_s7_configuration_sha256": frozen_dependencies["s7_configuration_sha256"],
        "s6_parameter_record_hash_substituted_for_artefact": False,
        "scientific_limitations": list(PRODUCTION_LIMITATIONS),
        "uncertainty": {
            "confidence_interval_produced": False,
            "bootstrap_produced": False,
            "hypothesis_test_produced": False,
            "eval_cluster_resampling_produced": False,
            "observed_ranges_are_confidence_intervals": False,
        },
    }
    expected_folded = set(reference_cores)
    expected_folded.update(_valid_sequences(rows))
    if set(cache) != expected_folded:
        raise M10ContractError(
            "fold_cache_incomplete",
            "production folding must fold each distinct valid sequence and each EVAL core once",
        )
    fold_count = len(cache)
    derived["distinct_fold_count"] = fold_count
    report["structure"]["distinct_fold_count"] = fold_count
    dispositions = {"computed_on_this_row": 0, "reused_from_earlier_row": 0, "not_folded": 0}
    for record in derived_records:
        dispositions[record["fold_cache_disposition"]] += 1
    report["structure"]["fold_cache_disposition_counts"] = dispositions
    report["viennarna_called"] = True
    report["denominators"]["distinct_folded_sequences"] = fold_count
    _assert_production_metadata(report)
    sequences = set(reference_cores)
    for row in rows:
        if isinstance(row.get("sequence"), str):
            sequences.add(row["sequence"])
    assert_public_report_sequence_free(report, sequences)
    assert_metric_coverage_locations(report)
    return derived, report


def _production_manifest(inputs, derived_blob, report_blob):
    manifest = {
        "schema": PRODUCTION_MANIFEST_SCHEMA,
        "contains_sequences": False,
        "eval_read_count": 1,
        "inputs": inputs["inputs"],
        "code": inputs["code"],
        "configuration": inputs["configuration"],
        "environment": inputs["environment"],
        "outputs": {
            "m10_derived_evidence.json": _sha256_bytes(derived_blob),
            "m10_sequence_free_report.json": _sha256_bytes(report_blob),
        },
    }
    assert_public_report_sequence_free(manifest, inputs["protected_sequences"])
    return manifest


def _sha256sums(blobs):
    lines = []
    for name in PRODUCTION_OUTPUT_NAMES:
        lines.append(_sha256_bytes(blobs[name]) + "  " + name)
    return ("\n".join(lines) + "\n").encode("utf-8")


def _write_exclusive(path, blob, mode):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.fchmod(descriptor, mode)
        view = blob
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
    finally:
        os.close(descriptor)
    with open(path, "rb") as handle:
        reread = handle.read()
    if reread != blob:
        raise M10ContractError("output_validation_failed", os.path.basename(path) + " changed before publication")


def publish_production_run(output_dir, derived, report, inputs):
    """Atomically publish one new production run. An existing directory is refused."""
    output_dir = os.path.abspath(output_dir)
    check_production_output_directory(output_dir)
    parent = os.path.dirname(output_dir)
    os.makedirs(parent, exist_ok=True)
    _refuse_existing(output_dir)
    derived_blob = _canonical_json(derived)
    report_blob = _canonical_json(report)
    manifest = _production_manifest(inputs, derived_blob, report_blob)
    manifest_blob = _canonical_json(manifest)
    blobs = {
        "m10_derived_evidence.json": derived_blob,
        "m10_sequence_free_report.json": report_blob,
        "m10_run_manifest.json": manifest_blob,
    }
    sums = _sha256sums(blobs)
    temp = tempfile.mkdtemp(prefix=".m10-production.", dir=parent)
    promoted = False
    try:
        for name in PRODUCTION_OUTPUT_NAMES:
            mode = PROTECTED_DERIVED_MODE if name == "m10_derived_evidence.json" else PUBLIC_ARTIFACT_MODE
            _write_exclusive(os.path.join(temp, name), blobs[name], mode)
        _write_exclusive(os.path.join(temp, "SHA256SUMS"), sums, PUBLIC_ARTIFACT_MODE)
        for name, blob in list(blobs.items()) + [("SHA256SUMS", sums)]:
            with open(os.path.join(temp, name), "rb") as handle:
                reread = handle.read()
            if reread != blob or _sha256_bytes(reread) != _sha256_bytes(blob):
                raise M10ContractError("output_validation_failed", name + " changed before publication")
        _refuse_existing(output_dir)
        os.rename(temp, output_dir)
        promoted = True
    finally:
        if not promoted and os.path.isdir(temp):
            shutil.rmtree(temp)
    return {
        "output_dir": output_dir,
        "published": True,
        "eval_read_count": 1,
        "files": list(PRODUCTION_OUTPUT_NAMES) + ["SHA256SUMS"],
        "sha256": {name: _sha256_bytes(blobs[name]) for name in PRODUCTION_OUTPUT_NAMES},
        "sha256sums_sha256": _sha256_bytes(sums),
    }


class ProductionSeams:
    """Real production checks. Generated-input preflight does not construct this."""

    def __init__(self, root, eval_access=None):
        self.root = root
        self.eval_access = eval_access

    def output_directory(self, output_dir):
        check_production_output_directory(output_dir)

    def generated_inputs(self):
        return prepare_production_generated_inputs(self.root)

    def schedule(self, generated):
        return generated["schedule"]

    def configuration_hashes(self):
        hashed = _hash_frozen_inputs(self.root)
        hashed.update(assert_production_metric_spec_gate(self.root))
        return hashed

    def viennarna(self):
        return collect_viennarna_evidence()

    def open_eval_once(self):
        if self.eval_access is None:
            return read_frozen_eval_once(self.root)
        return self.eval_access()


def run_authorized_production(output_dir, authorization, *, root=REPO_ROOT, eval_access=None, seams=None, fold=None):
    """Open EVAL once, then calculate and publish the Section 5 result.

    Without the explicit authorization object this returns before any output
    path, generated input, or EVAL access is inspected. The frozen-spec gate,
    captured code inventory, frozen S6 parameter-record hash, frozen S7
    configuration hashes, frozen M9A summaries, and every other non-EVAL check
    finish before that single read. This stage does not call this function
    against the repository.
    """
    if not _production_authorized(authorization):
        raise M10ContractError("production_unauthorized", "explicit M10/EVAL authorization is absent")
    if seams is None:
        seams = ProductionSeams(root, eval_access)
    folder = production_fold if fold is None else fold
    seams.output_directory(output_dir)
    generated = seams.generated_inputs()
    seams.schedule(generated)
    configuration = seams.configuration_hashes()
    _require_production_spec_attestation(configuration)
    assert_metric_coverage_contract(root)
    environment = seams.viennarna()
    code_hashes = _code_hashes(root)
    s6_provenance = _s6_provenance(root)
    assert_frozen_s6_and_s7(code_hashes, s6_provenance)
    train = load_allowlisted_train_summaries(root)
    payload = seams.open_eval_once()
    evaluation = adapt_authorized_eval(
        payload,
        {"m10_execution_authorized": True, "open_eval": True, "payload_is_bytes": True},
    )
    rows = _private_generated_rows(generated)
    derived, report = build_production_reports(
        rows,
        evaluation,
        train,
        folder,
        root,
        configuration,
        environment,
        code_hashes,
        s6_provenance,
    )
    sequences = [core["sequence_core"] for core in evaluation["cores"]]
    for row in rows:
        if isinstance(row.get("sequence"), str):
            sequences.append(row["sequence"])
    inputs = {
        "inputs": {
            "eval": {
                "relative_path": FROZEN_EVAL_RELATIVE,
                "sha256": evaluation["sha256"],
                "read_count": 1,
                "identity_count": evaluation["identity_count"],
                "unique_core_count": evaluation["unique_core_count"],
            },
            "generated_ledgers": generated.get("identity"),
            "denominators": generated.get("denominators"),
            "schedule": generated.get("schedule"),
            "train_summaries": {key: train[key]["sha256"] for key in train},
        },
        "code": report["code_and_configuration_hashes"],
        "configuration": configuration,
        "environment": environment,
        "protected_sequences": sequences,
    }
    if "private_adapted_rows" in json.dumps(inputs["inputs"]):
        raise M10ContractError("sequence_leak", "adapted generated rows were copied into the public manifest")
    assert_public_report_sequence_free(inputs["inputs"], sequences)
    return publish_production_run(output_dir, derived, report, inputs)


def prepare_production_generated_inputs(root):
    """Hash, adapt, and bind the frozen generated ledgers. Do not open EVAL."""
    loaded = load_allowlisted_generated_ledgers(root)
    adapted = adapt_frozen_ledgers(loaded["ledgers"])
    if len(adapted["rows"]) != sum(PRODUCTION_ATTEMPT_COUNTS.values()):
        raise M10ContractError("rows_dropped", "adaptation did not retain every generated attempt")
    denominators = validate_generated_denominators(adapted, loaded["accounting"])
    schedule = validate_production_matched_blocks(adapted["rows"])
    if schedule["b0_attempts_outside_blocks"] != PRODUCTION_ATTEMPT_COUNTS["B0"]:
        raise M10ContractError("schedule_condition_invalid", "B0 attempts were not all outside the matched blocks")
    if schedule["b2_attempts_outside_blocks"] != PRODUCTION_ATTEMPT_COUNTS["B2"]:
        raise M10ContractError("schedule_condition_invalid", "B2 attempts were not all outside the matched blocks")
    sequences = [row["sequence"] for row in adapted["rows"] if isinstance(row.get("sequence"), str)]
    return {
        "identity": loaded["identity"],
        "denominators": denominators,
        "schedule": schedule,
        "sequences_for_leak_check": sequences,
        "private_adapted_rows": adapted["rows"],
        "rows_dropped": False,
        "invalid_rows_retained": True,
    }


def render_generated_preflight_record(prepared, environment, smoke, configuration_hashes):
    """Build the sequence-free preflight document. Metric values are omitted."""
    document = {
        "schema": GENERATED_PREFLIGHT_SCHEMA,
        "layer": "sequence_free_generated_input_preflight",
        "scientific_result": False,
        "metric_spec_freeze_status": "frozen",
        "production_ready": True,
        "m10_execution_authorized": False,
        "production_execution_invoked": False,
        "eval_opened": False,
        "biological_ledgers_opened": True,
        "biological_sequences_folded": False,
        "eval_sequences_folded": False,
        "rows_dropped": False,
        "invalid_rows_retained": True,
        "source_manifest": prepared["identity"]["source_manifest"],
        "accounting_summary": prepared["identity"]["accounting_summary"],
        "generated_ledgers": prepared["identity"]["ledgers"],
        "counts": prepared["denominators"],
        "b2_empirical_null_seed": prepared["identity"]["b2_empirical_null_seed"],
        "b2_empirical_null_seed_count": 1,
        "b0_role": "external_historical_panel",
        "b0_requested_length": "unavailable",
        "pairing": prepared["schedule"],
        "environment": environment,
        "synthetic_viennarna_smoke": {
            "scientific_result": False,
            "recorded_separately": True,
            "path": smoke["path"],
            "sha256": smoke["sha256"],
            "fold_calls": smoke["document"]["fold_calls"],
            "package_version": smoke["document"]["package_version"],
            "package_build": smoke["document"]["package_build"],
        },
        "frozen_configuration_hashes": configuration_hashes,
        "readiness": {
            "generated_input_preflight": "implemented_and_synthetically_verified",
            "authorized_production_execution": "implemented_not_invoked",
            "biological_production_execution": "not_yet_authorized",
            "biological_sequence_folding": "not_yet_authorized",
            "eval_opening": "not_yet_authorized",
            "metric_spec_freeze_status": "frozen",
            "metric_spec_production_ready": True,
            "distinct_sequence_fold_cache": "implemented_not_used_on_biological_sequences",
            "structure_distance_defined": False,
        },
        "exclusions": prepared["identity"]["excluded_sources"],
        "limitations": list(PREFLIGHT_LIMITATIONS),
    }
    assert_public_report_sequence_free(document, prepared.get("sequences_for_leak_check", ()))
    return document


def publish_sequence_free_json(path, document, root):
    """Create one new JSON file. An existing path is never overwritten."""
    path = os.path.abspath(path)
    _refuse_results_directory(path, root)
    _refuse_protected_path(path)
    if os.path.isdir(path) or os.path.islink(path):
        raise M10ContractError("output_exists", "the output path already exists")
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    _refuse_existing(path)
    blob = _canonical_json(document)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    try:
        view = blob
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
    finally:
        os.close(descriptor)
    with open(path, "rb") as handle:
        reread = handle.read()
    if reread != blob:
        raise M10ContractError("output_validation_failed", "the preflight record changed before publication")
    return {"path": path, "sha256": _sha256_bytes(reread)}


def run_generated_input_preflight(output_path, authorization, *, root=REPO_ROOT, smoke_path=None, inputs=None, fold=None, viennarna_evidence=None):
    """Validate the frozen pre-EVAL gate and write a sequence-free record.

    The repository path checks the pinned frozen specification, generated
    ledgers, matched schedule, M9A summaries, ViennaRNA environment, S6
    parameter hash, and S7 hashes. The only fold is the synthetic ViennaRNA
    smoke fixture. This mode cannot open EVAL. It has no EVAL path and does
    not call the authorized production runner. Injected inputs are accepted
    only for a synthetic fixture.
    """
    _require_generated_preflight_authorization(authorization)
    if smoke_path is None:
        smoke_path = os.path.splitext(os.path.abspath(output_path))[0] + "_synthetic_viennarna_smoke.json"
    _refuse_results_directory(output_path, root)
    _refuse_results_directory(smoke_path, root)
    _refuse_protected_path(output_path)
    _refuse_protected_path(smoke_path)
    _refuse_existing(output_path)
    _refuse_existing(smoke_path)
    if inputs is None:
        prepared = prepare_production_generated_inputs(root)
        evidence = collect_viennarna_evidence() if viennarna_evidence is None else viennarna_evidence
        configuration_hashes = verify_frozen_configuration_hashes(root)
    else:
        if inputs.get("fixture_role") != "SYNTHETIC":
            raise M10ContractError("fixture_role_refused", "injected preflight inputs must be synthetic")
        prepared = inputs
        evidence = viennarna_evidence
        configuration_hashes = inputs.get("frozen_configuration_hashes")
        if not isinstance(configuration_hashes, dict):
            raise M10ContractError("frozen_configuration_mismatch", "synthetic preflight inputs lack configuration hashes")
    smoke_document = run_synthetic_viennarna_smoke(evidence, fold=fold)
    smoke_published = publish_sequence_free_json(smoke_path, smoke_document, root)
    smoke_published["document"] = smoke_document
    try:
        document = render_generated_preflight_record(prepared, evidence, smoke_published, configuration_hashes)
        published = publish_sequence_free_json(output_path, document, root)
    except Exception:
        if os.path.lexists(smoke_published["path"]) and not os.path.lexists(output_path):
            os.remove(smoke_published["path"])
        raise
    published["smoke_path"] = smoke_published["path"]
    published["smoke_sha256"] = smoke_published["sha256"]
    published["eval_opened"] = False
    return published

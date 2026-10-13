#!/usr/bin/env python3
"""M9C-2 descriptive REF summary preparation.

The five raw components follow the reviewed AptaRank definitions. Retention
uses the attempt-3 first-occurrence rule. Short and long labels use the frozen
S6 GMM and are not refit. The aggregate is sequence-free and descriptive.
The no-argument command checks pins only. It does not open REF, fold a
production sequence, calibrate AptaRank, or write under results/.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import sys

import numpy as np

PACKAGE_ID = "M9C-2"
SCHEMA_VERSION = "m9c-descriptive-ref-summary-v1"
STATUS = "PREPARATION_FROZEN_SYNTHETIC_ONLY_PRODUCTION_REF_NOT_RUN"
STAGE = "M9C-2"
CONTRACT_RELATIVE = "config/modelling/aptarank_descriptive_ref_summary_contract.json"
CONTRACT_SHA256 = "3a662b960ab3e4a70b7515acdd532d45e93e31e80ff3025922d04f7df9d0fab4"
PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md"
PLAN_SHA256 = "b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe"
UPLOAD_CONTRACT_RELATIVE = "config/modelling/aptarank_reference_upload_contract.json"
UPLOAD_CONTRACT_SHA256 = "34912929e77a0a835a01e36ba0291160b49b60dcdfb12a2d2aeb57090c794d02"
S7D_RELATIVE = "config/global_s7d_final_build.json"
COMPONENT_NAMES = (
    "mfe_norm",
    "ensemble_defect",
    "positional_entropy_mean",
    "stem_fraction",
    "gc_fraction",
)
STRATA = ("all", "short", "long")
STATISTIC_NAMES = (
    "successful_count",
    "error_or_missing_count",
    "mean",
    "population_standard_deviation",
    "minimum",
    "first_quartile",
    "median",
    "third_quartile",
    "maximum",
)
PERCENTILE_CONVENTION = "numpy_percentile_linear"
POPULATION_SD_DIVISOR = "n"
SOURCE_IDENTITY_ROWS = 131
DISTINCT_SEQUENCE_CORES = 113
DUPLICATE_CORE_COLLAPSES = 18
SHORT_CORES = 65
LONG_CORES = 48
CANONICAL_CORE = re.compile(r"^[ACGU]+\Z")
TOP_LEVEL_KEYS = (
    "package_id",
    "schema_version",
    "status",
    "stage",
    "scientific_result",
    "m9c_complete",
    "eval_unlocked",
    "eval_opened",
    "production_candidates_opened",
    "production_ref_opened_by_this_preparation",
    "production_summary_executed",
    "local_calibration",
    "aptarank_execution",
    "results_write",
    "governing_plan_modified",
    "governing_plan",
    "attempt3_retention_authority",
    "retention",
    "length_regime",
    "components",
    "fold_model",
    "aggregate",
    "prohibited_calculations",
    "tier2_bank_decision",
    "generator_viennarna_pin",
)


class DescriptiveRefError(ValueError):
    """The descriptive REF preparation refused the request."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def _require(condition, code, detail):
    if not condition:
        raise DescriptiveRefError(code, detail)


def _exact_keys(document, expected, code, detail):
    if type(document) is not dict or set(document) != set(expected):
        raise DescriptiveRefError(code, detail)


def _read_regular_file(relative):
    if type(relative) is not str or relative == "" or os.path.isabs(relative) or ".." in relative.split("/"):
        raise DescriptiveRefError("pin_invalid", "a pinned path is not a repository-relative file")
    path = os.path.join(repo_root(), relative)
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise DescriptiveRefError("pin_unreadable", "a pinned file cannot be read") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise DescriptiveRefError("pin_symlink", "a pinned file is not a regular file")
    with open(path, "rb") as handle:
        return handle.read()


def _load_json(relative):
    payload = _read_regular_file(relative)
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DescriptiveRefError("pin_invalid", "a pinned file is not JSON") from exc
    return document, payload


def load_pinned_contract():
    """Read and check the descriptive contract without opening REF."""
    document, payload = _load_json(CONTRACT_RELATIVE)
    _require(sha256_bytes(payload) == CONTRACT_SHA256, "pin_mismatch", "the descriptive contract digest changed")
    plan_payload = _read_regular_file(PLAN_RELATIVE)
    upload_document, upload_payload = _load_json(UPLOAD_CONTRACT_RELATIVE)
    s7d_document, _s7d_payload = _load_json(S7D_RELATIVE)
    validate_contract_document(
        document,
        plan_payload=plan_payload,
        upload_document=upload_document,
        upload_payload=upload_payload,
        s7d_document=s7d_document,
    )
    return document


def validate_contract_document(document, *, plan_payload, upload_document, upload_payload, s7d_document):
    """Fail closed unless the contract still states this descriptive preparation."""
    _exact_keys(document, TOP_LEVEL_KEYS, "spec_invalid", "the descriptive contract keys changed")
    _require(document["package_id"] == PACKAGE_ID, "spec_invalid", "the package id is not M9C-2")
    _require(document["schema_version"] == SCHEMA_VERSION, "spec_invalid", "the schema version changed")
    _require(document["status"] == STATUS, "spec_invalid", "the status changed")
    _require(document["stage"] == STAGE, "spec_invalid", "the stage changed")
    for key in (
        "scientific_result",
        "m9c_complete",
        "eval_unlocked",
        "eval_opened",
        "production_candidates_opened",
        "production_ref_opened_by_this_preparation",
        "production_summary_executed",
        "local_calibration",
        "aptarank_execution",
        "results_write",
        "governing_plan_modified",
    ):
        _require(document[key] is False, "spec_invalid", "a closed policy flag is no longer false")
    plan = document["governing_plan"]
    _exact_keys(plan, ("path", "version", "revision_date", "sha256"), "spec_invalid", "the governing plan record changed")
    _require(plan["path"] == PLAN_RELATIVE, "spec_invalid", "the governing plan path changed")
    _require(plan["version"] == "3.3", "spec_invalid", "the governing plan version changed")
    _require(plan["sha256"] == PLAN_SHA256, "spec_invalid", "the governing plan pin changed")
    _require(sha256_bytes(plan_payload) == PLAN_SHA256, "pin_mismatch", "the governing plan bytes changed")
    authority = document["attempt3_retention_authority"]
    _exact_keys(
        authority,
        ("path", "schema_version", "sha256", "implementation", "function"),
        "spec_invalid",
        "the attempt-3 retention authority changed",
    )
    _require(authority["path"] == UPLOAD_CONTRACT_RELATIVE, "spec_invalid", "the attempt-3 contract path changed")
    _require(authority["schema_version"] == "m9c-reference-upload-v3", "spec_invalid", "the attempt-3 schema changed")
    _require(authority["sha256"] == UPLOAD_CONTRACT_SHA256, "spec_invalid", "the attempt-3 contract pin changed")
    _require(sha256_bytes(upload_payload) == UPLOAD_CONTRACT_SHA256, "pin_mismatch", "the attempt-3 contract bytes changed")
    _require(authority["function"] == "_retain_rows", "spec_invalid", "retention no longer uses the attempt-3 function")
    retention = document["retention"]
    upload_retention = upload_document["retention"]
    for key in (
        "grain",
        "traversal",
        "upload_order",
        "representative",
        "replacement",
        "later_identity_rows",
    ):
        _require(retention[key] == upload_retention[key], "spec_invalid", "the attempt-3 retention rule changed")
    _require(retention["upload_order"] == "first_occurrence", "spec_invalid", "the upload order changed")
    _require(retention["replacement"] is False, "spec_invalid", "a later identity may replace the first core")
    _require(retention["source_identity_rows"] == SOURCE_IDENTITY_ROWS, "spec_invalid", "the source row count changed")
    _require(retention["distinct_sequence_cores"] == DISTINCT_SEQUENCE_CORES, "spec_invalid", "the distinct core count changed")
    _require(retention["duplicate_core_collapses"] == DUPLICATE_CORE_COLLAPSES, "spec_invalid", "the collapse count changed")
    regime = document["length_regime"]
    _require(regime["refit"] is False, "spec_invalid", "the S6 GMM is being refit")
    _require(regime["assignment_method"] == "gmm_k2_maximum_posterior", "spec_invalid", "the GMM assignment method changed")
    _require(regime["component_0"] == "short", "spec_invalid", "component 0 is no longer short")
    _require(regime["tie_assignment"] == "short", "spec_invalid", "a posterior tie no longer goes short")
    frozen = s7d_document["expected_s6_gmm2"]
    _require(regime["means"] == frozen["means"], "spec_invalid", "the frozen GMM means changed")
    _require(regime["variances"] == frozen["variances"], "spec_invalid", "the frozen GMM variances changed")
    _require(regime["weights"] == frozen["weights"], "spec_invalid", "the frozen GMM weights changed")
    expected_cores = s7d_document["expected_length_regime_cores"]["REF"]
    _require(regime["required_unique_cores"] == {"short": SHORT_CORES, "long": LONG_CORES}, "spec_invalid", "the REF regime counts changed")
    _require(expected_cores["short"] == SHORT_CORES and expected_cores["long"] == LONG_CORES, "spec_invalid", "the frozen REF regime counts changed")
    _require(s7d_document["length_regime"]["refit"] is False, "spec_invalid", "the frozen length-regime record allows a refit")
    components = document["components"]
    _exact_keys(components, COMPONENT_NAMES, "spec_invalid", "the descriptive component set changed")
    for name in COMPONENT_NAMES:
        _require(components[name]["used_as_calibration"] is False, "spec_invalid", "a descriptive component is marked as calibration")
    _require(components["stem_fraction"]["forgi_imported"] is False, "spec_invalid", "this preparation imports forgi")
    fold = document["fold_model"]
    _require(fold["uniq_ML"] == 1, "spec_invalid", "uniq_ML is no longer 1")
    _require(fold["other_model_details_set"] is False, "spec_invalid", "the fold model sets an extra detail")
    _require(fold["settings_invented"] is False, "spec_invalid", "folding settings were invented")
    _require(fold["production_summary_executed"] is False, "spec_invalid", "a production summary was executed")
    aggregate = document["aggregate"]
    _require(aggregate["strata"] == list(STRATA), "spec_invalid", "the strata changed")
    _require(aggregate["sequence_free"] is True, "spec_invalid", "the aggregate is no longer sequence-free")
    _require(aggregate["percentile_convention"] == PERCENTILE_CONVENTION, "spec_invalid", "the percentile convention changed")
    _require(aggregate["percentile_quantiles"] == [25, 50, 75], "spec_invalid", "the quartile probabilities changed")
    _require(aggregate["population_standard_deviation_divisor"] == POPULATION_SD_DIVISOR, "spec_invalid", "the standard-deviation divisor changed")
    _require(aggregate["statistics"] == list(STATISTIC_NAMES), "spec_invalid", "the statistic set changed")
    _require(aggregate["reject_non_finite"] is True, "spec_invalid", "a non-finite component is accepted")
    _require(aggregate["reject_count_mismatch"] is True, "spec_invalid", "a count mismatch is accepted")
    _require(aggregate["successful_error_count"] == 0, "spec_invalid", "a successful summary may carry errors")
    _require(
        document["prohibited_calculations"]
        == ["empirical_cdf", "calibrated_score", "composite", "weight", "shuffle_pass", "candidate_ranking"],
        "spec_invalid",
        "a prohibited calculation was dropped",
    )
    bank = document["tier2_bank_decision"]
    _require(bank["quantities_are_distinct"] is True, "spec_invalid", "the two control quantities were conflated")
    _require(bank["tier1_candidate_shuffles"] == 20, "spec_invalid", "the Tier 1 shuffle count changed")
    _require(bank["tier2_realized_count"] == 5085, "spec_invalid", "the Tier 2 realized count changed")
    _require(bank["sources"] == 113 and bank["controls_per_source"] == 45, "spec_invalid", "the bank allocation changed")
    _require(bank["seed"] == 42 and bank["n_ensemble_samples"] == 100, "spec_invalid", "the bank seed or ensemble count changed")
    _require(bank["explicit_bank_id_exposed"] is False, "spec_invalid", "a bank ID was marked exposed")
    _require(bank["content_hash_exposed"] is False, "spec_invalid", "a bank content hash was marked exposed")
    _require(bank["ushuffle_version"] == "unknown", "spec_invalid", "an ushuffle version was invented")
    _require(bank["bank_id_claimed"] is False and bank["content_hash_claimed"] is False, "spec_invalid", "a bank ID or content hash is claimed")
    _require(bank["provenance_sufficient_for_deployed_percentile"] is True, "spec_invalid", "the percentile provenance decision changed")
    _require(bank["limitations_reported"] is True, "spec_invalid", "the bank limitations are unreported")
    _require(bank["governing_plan_modified"] is False, "spec_invalid", "the bank decision rewrites v3.3")
    _require(bank["aptarank_git"] == "49a85609e352", "spec_invalid", "the reviewed AptaRank revision changed")
    pin = document["generator_viennarna_pin"]
    _require(pin["resolved_in_this_preparation"] is False, "spec_invalid", "this preparation resolves the generator ViennaRNA pin")
    _require(pin["generator_metric_spec_modified"] is False, "spec_invalid", "the generator metric specification was modified")
    _require(pin["blocking_item_id"] == "viennarna_production_settings_not_pinned", "spec_invalid", "the generator blocking item changed")
    return document


def _gaussian_logpdf(values, mean, variance):
    safe_variance = max(float(variance), 1e-12)
    return -0.5 * (math.log(2.0 * math.pi * safe_variance) + (values - mean) ** 2 / safe_variance)


def assign_length_regimes(lengths, gmm):
    """Assign lengths with the frozen two-component posterior. Component 0 is short.

    Exact posterior ties use ``numpy.argmax`` and therefore go short. This does
    not fit a new mixture.
    """
    _require(gmm["refit"] is False, "spec_invalid", "the S6 GMM is being refit")
    means = [float(value) for value in gmm["means"]]
    variances = [float(value) for value in gmm["variances"]]
    weights = [float(value) for value in gmm["weights"]]
    _require(len(means) == 2 and means[0] < means[1], "spec_invalid", "the frozen GMM means are not an ordered pair")
    arr = np.asarray(list(lengths), dtype=float)
    if arr.size == 0:
        return np.zeros((0,), dtype=int)
    _require(bool(np.isfinite(arr).all()) and bool(np.all(arr > 0)), "count_mismatch", "a core length is not a positive finite value")
    log_resp = np.stack(
        [
            math.log(max(weights[index], 1e-12)) + _gaussian_logpdf(arr, means[index], variances[index])
            for index in range(2)
        ],
        axis=1,
    )
    max_log = np.max(log_resp, axis=1, keepdims=True)
    resp = np.exp(log_resp - max_log)
    resp = resp / np.clip(resp.sum(axis=1, keepdims=True), 1e-12, None)
    return np.argmax(resp, axis=1)


def _paired_nucleotide_count(dot_bracket, length):
    """Paired positions in one MFE dot-bracket.

    AptaRank's stem numerator is the sum of ``2 * stem_length`` over forgi stem
    elements. In a parenthesis-and-dot structure every base pair belongs to one
    stem, so that sum equals this count. This preparation does not import forgi.
    """
    if type(dot_bracket) is not str or len(dot_bracket) != length:
        raise DescriptiveRefError("non_finite_component", "the MFE dot-bracket length does not match the sequence")
    depth = 0
    paired = 0
    for char in dot_bracket:
        if char == "(":
            depth += 1
            paired += 1
        elif char == ")":
            depth -= 1
            paired += 1
            if depth < 0:
                raise DescriptiveRefError("non_finite_component", "the MFE dot-bracket is unbalanced")
        elif char != ".":
            raise DescriptiveRefError("non_finite_component", "the MFE dot-bracket contains an unexpected character")
    if depth != 0:
        raise DescriptiveRefError("non_finite_component", "the MFE dot-bracket is unbalanced")
    return paired


def _finite_component(name, value):
    if isinstance(value, bool) or type(value) not in (int, float):
        raise DescriptiveRefError("non_finite_component", "a descriptive component is not a real number")
    number = float(value)
    if not math.isfinite(number):
        raise DescriptiveRefError("non_finite_component", "a descriptive component is not finite: " + name)
    return number


def measure_sequence(sequence):
    """Return the five raw components for one canonical synthetic or retained core.

    The fold sets ``uniq_ML = 1`` and leaves every other ViennaRNA model detail
    untouched. It does not open a path and it does not calibrate those values.
    """
    if type(sequence) is not str or CANONICAL_CORE.fullmatch(sequence) is None:
        raise DescriptiveRefError("noncanonical_core", "a sequence core is not canonical uppercase A, C, G and U")
    if os.sep in sequence or sequence.endswith(".csv"):
        raise DescriptiveRefError("filesystem_path_refused", "a sequence core is not a filesystem path")
    try:
        import RNA
    except ImportError as exc:
        raise DescriptiveRefError("fold_unavailable", "ViennaRNA is not importable in this interpreter") from exc
    length = len(sequence)
    model = RNA.md()
    model.uniq_ML = 1
    compound = RNA.fold_compound(sequence, model)
    dot_bracket, mfe = compound.mfe()
    compound.exp_params_rescale(mfe)
    compound.pf()
    entropy = compound.positional_entropy()
    per_position = [float(value) for value in entropy[1 : length + 1]]
    if len(per_position) != length:
        raise DescriptiveRefError("non_finite_component", "positional entropy does not have one value per nucleotide")
    components = {
        "mfe_norm": float(mfe) / length,
        "ensemble_defect": float(compound.ensemble_defect(dot_bracket)),
        "positional_entropy_mean": sum(per_position) / length,
        "stem_fraction": _paired_nucleotide_count(dot_bracket, length) / length,
        "gc_fraction": (sequence.count("G") + sequence.count("C")) / length,
    }
    return {name: _finite_component(name, components[name]) for name in COMPONENT_NAMES}


def aggregate_component(values):
    """Summarize one finite sample with NumPy's linear percentile and divisor n."""
    if isinstance(values, (str, bytes)):
        raise DescriptiveRefError("filesystem_path_refused", "component values must be numbers")
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0 or not bool(np.isfinite(arr).all()):
        raise DescriptiveRefError("non_finite_component", "a descriptive component is missing or not finite")
    first_quartile, median, third_quartile = np.percentile(arr, [25.0, 50.0, 75.0], method="linear")
    return {
        "successful_count": int(arr.size),
        "error_or_missing_count": 0,
        "mean": float(np.mean(arr)),
        "population_standard_deviation": float(np.std(arr, ddof=0)),
        "minimum": float(np.min(arr)),
        "first_quartile": float(first_quartile),
        "median": float(median),
        "third_quartile": float(third_quartile),
        "maximum": float(np.max(arr)),
        "percentile_convention": PERCENTILE_CONVENTION,
        "population_standard_deviation_divisor": POPULATION_SD_DIVISOR,
    }


def _component_map(components_by_core, sequence):
    if type(components_by_core) is not dict or sequence not in components_by_core:
        raise DescriptiveRefError("missing_component", "a retained core has no descriptive components")
    record = components_by_core[sequence]
    _exact_keys(record, COMPONENT_NAMES, "missing_component", "a retained core does not have exactly the five components")
    return {name: _finite_component(name, record[name]) for name in COMPONENT_NAMES}


def _retain(source_rows):
    if type(source_rows) is not list:
        raise DescriptiveRefError("filesystem_path_refused", "source rows must be an in-memory list")
    modelling = os.path.dirname(os.path.abspath(__file__))
    if modelling not in sys.path:
        sys.path.insert(0, modelling)
    import aptarank_reference_upload as upload

    retained, collapses = upload._retain_rows(source_rows, upload.load_pinned_contract())
    return retained, collapses


def summarize_descriptive_reference(source_rows, components_by_core):
    """Aggregate injected components for rows retained by the attempt-3 rule.

    ``source_rows`` is an in-memory list. A path is refused. The result contains
    counts and component statistics only. Production accounting must be 131
    source rows, 113 cores, 18 collapses, 65 short, and 48 long.
    """
    if isinstance(source_rows, (str, bytes, os.PathLike)) or isinstance(components_by_core, (str, bytes, os.PathLike)):
        raise DescriptiveRefError("filesystem_path_refused", "production REF is not opened by this preparation")
    contract = load_pinned_contract()
    retained, collapses = _retain(source_rows)
    if (
        len(source_rows) != SOURCE_IDENTITY_ROWS
        or len(retained) != DISTINCT_SEQUENCE_CORES
        or collapses != DUPLICATE_CORE_COLLAPSES
    ):
        raise DescriptiveRefError(
            "count_mismatch",
            "descriptive retention must be 131 source rows, 113 cores, and 18 collapses",
        )
    if type(components_by_core) is not dict or set(components_by_core) != {item["sequence"] for item in retained}:
        raise DescriptiveRefError("missing_component", "components must exist for every retained core and for no other core")
    lengths = [len(item["sequence"]) for item in retained]
    labels = assign_length_regimes(lengths, contract["length_regime"])
    regimes = ["short" if int(label) == 0 else "long" for label in labels]
    short_count = regimes.count("short")
    long_count = regimes.count("long")
    if short_count != SHORT_CORES or long_count != LONG_CORES:
        raise DescriptiveRefError("count_mismatch", "descriptive retention must be 65 short cores and 48 long cores")
    measured = [_component_map(components_by_core, item["sequence"]) for item in retained]
    strata = {
        "all": measured,
        "short": [record for record, regime in zip(measured, regimes) if regime == "short"],
        "long": [record for record, regime in zip(measured, regimes) if regime == "long"],
    }
    summary = {
        "package_id": PACKAGE_ID,
        "schema_version": SCHEMA_VERSION,
        "status": "DESCRIPTIVE_SUMMARY_COMPUTED_SYNTHETIC_ONLY",
        "scientific_result": False,
        "calibration": False,
        "label": "descriptive_not_aptarank_calibration",
        "percentile_convention": PERCENTILE_CONVENTION,
        "population_standard_deviation_divisor": POPULATION_SD_DIVISOR,
        "source_row_count": len(source_rows),
        "retained_core_count": len(retained),
        "duplicate_core_collapses": collapses,
        "regime_counts": {"short": short_count, "long": long_count},
        "strata": {},
    }
    for stratum in STRATA:
        summary["strata"][stratum] = {
            name: aggregate_component([record[name] for record in strata[stratum]]) for name in COMPONENT_NAMES
        }
        for record in summary["strata"][stratum].values():
            _require(record["error_or_missing_count"] == 0, "count_mismatch", "a successful stratum records an error")
    _require_sequence_free(summary, retained)
    return summary


def _require_sequence_free(summary, retained):
    """Reject a summary that stores a retained sequence, identity, or sequence key."""
    forbidden_values = {item["sequence"] for item in retained} | {item["id"] for item in retained}
    forbidden_keys = {"sequence", "sequence_core", "scientific_identity_id", "id", "candidate_id"}

    def walk(node):
        if type(node) is dict:
            for key, value in node.items():
                if key in forbidden_keys:
                    raise DescriptiveRefError("sequence_emitted", "the descriptive aggregate names a sequence or identity")
                walk(value)
        elif type(node) is list:
            for value in node:
                walk(value)
        elif type(node) is str and node in forbidden_values:
            raise DescriptiveRefError("sequence_emitted", "the descriptive aggregate contains a retained sequence or identity")

    walk(summary)


def main(argv=None):
    """Check pins and exit. Arguments are refused so this cannot select a REF path."""
    arguments = sys.argv[1:] if argv is None else list(argv)
    if arguments:
        raise DescriptiveRefError("filesystem_path_refused", "the descriptive preparation does not accept a path")
    load_pinned_contract()
    print(STATUS)
    print(CONTRACT_SHA256)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DescriptiveRefError as exc:
        print(exc.code + ": " + exc.detail, file=sys.stderr)
        raise SystemExit(1)

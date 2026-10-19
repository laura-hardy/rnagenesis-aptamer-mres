#!/usr/bin/env python3
"""Pure frozen-S6 short/long assignment.

The rule is the S6 ``gmm_k2_maximum_posterior`` assignment. Component 0 is
short. An exact posterior tie goes short, matching ``numpy.argmax``. The
mixture is not refit and no nucleotide cutoff is introduced.

The required input is the S6 ``length_of`` core length: a positive stored
``sequence_length_core`` when one is present, otherwise the length of the
usable sequence. A requested generation length is not that input. An attempt
with no usable canonical sequence has no input length and is not assigned.
"""

from __future__ import annotations

import hashlib
import json
import math
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

ARTEFACT_RELATIVE = "data/interim/deduplicated/s6_profile/bimodality.json"
ARTEFACT_KEY = "gmm_2"
ASSIGNMENT_METHOD = "gmm_k2_maximum_posterior"
PARAMETER_SOURCE = "config/global_s7d_final_build.json#expected_s6_gmm2"
PARAMETER_CONFIGS = (
    "config/global_s7d_final_build.json",
    "config/global_s7b_partition.json",
    "config/global_s7c_ft_train_validation.json",
)
SAMPLE = "distinct_sequence_core_lengths"
LABELS = ("short", "long")


class S6AssignmentError(ValueError):
    """The frozen S6 assignment refused its input."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def _sha256_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


def _read_json(root, relative):
    path = os.path.join(root, relative)
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def _parameter_lists(document):
    gmm = document.get("expected_s6_gmm2")
    if not isinstance(gmm, dict):
        raise S6AssignmentError("s6_parameters_invalid", "a frozen S6 parameter record is missing")
    try:
        means = [float(value) for value in gmm["means"]]
        variances = [float(value) for value in gmm["variances"]]
        weights = [float(value) for value in gmm["weights"]]
    except (KeyError, TypeError, ValueError) as error:
        raise S6AssignmentError("s6_parameters_invalid", "the frozen S6 parameters are not numeric pairs") from error
    if len(means) != 2 or len(variances) != 2 or len(weights) != 2 or not means[0] < means[1]:
        raise S6AssignmentError("s6_parameters_invalid", "the frozen S6 means are not an ascending pair")
    regime = document.get("length_regime") or {}
    if regime.get("assignment_method") != ASSIGNMENT_METHOD or regime.get("refit") is True:
        raise S6AssignmentError("s6_parameters_invalid", "the frozen S6 assignment method is not the maximum posterior")
    return {"means": means, "variances": variances, "weights": weights}


def frozen_parameters(root=None):
    """Return the pinned gmm_2 parameters shared by the frozen S7 records."""
    root = REPO_ROOT if root is None else root
    pinned = None
    for relative in PARAMETER_CONFIGS:
        current = _parameter_lists(_read_json(root, relative))
        if pinned is None:
            pinned = current
        elif current != pinned:
            raise S6AssignmentError("s6_parameters_invalid", relative + " does not match the frozen S6 parameters")
    return pinned


def parameter_record(root=None):
    parameters = frozen_parameters(root)
    return {
        "assignment_method": ASSIGNMENT_METHOD,
        "component_0": "short",
        "component_1": "long",
        "means": parameters["means"],
        "refit": False,
        "sample": SAMPLE,
        "tie_assignment": "short",
        "variances": parameters["variances"],
        "weights": parameters["weights"],
    }


def parameter_sha256(root=None):
    payload = json.dumps(parameter_record(root), ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _sha256_bytes(payload)


def provenance(root=None):
    """Record the artefact, method, and parameter hash without refitting."""
    root = REPO_ROOT if root is None else root
    record = parameter_record(root)
    result = {
        "artefact_path": ARTEFACT_RELATIVE,
        "artefact_key": ARTEFACT_KEY,
        "artefact_present": False,
        "artefact_sha256": None,
        "artefact_absence_classification": "provenance_limitation",
        "parameter_record_hash_substituted_for_artefact": False,
        "parameter_source": PARAMETER_SOURCE,
        "parameter_sha256": parameter_sha256(root),
        "assignment_method": record["assignment_method"],
        "component_0": "short",
        "component_1": "long",
        "tie_assignment": "short",
        "tie_rule": "maximum_posterior_exact_tie_lower_component_index",
        "refit": False,
        "sample": SAMPLE,
        "means": record["means"],
        "variances": record["variances"],
        "weights": record["weights"],
        "input_length_rule": "s6_length_of_sequence_core",
        "valid_generated_output": "canonical_parsed_sequence_length",
        "authorized_eval_core": "stored_sequence_length_core_else_len_sequence_core",
        "invalid_without_usable_sequence": "not_applicable",
        "requested_length_is_input": False,
    }
    path = os.path.join(root, ARTEFACT_RELATIVE)
    if os.path.isfile(path):
        with open(path, "rb") as handle:
            blob = handle.read()
        payload = json.loads(blob.decode("utf-8"))
        gmm = payload.get(ARTEFACT_KEY)
        if not isinstance(gmm, dict):
            raise S6AssignmentError("s6_artefact_invalid", "bimodality.json has no gmm_2 object")
        observed = _parameter_lists({"expected_s6_gmm2": gmm, "length_regime": {"assignment_method": ASSIGNMENT_METHOD}})
        if observed != frozen_parameters(root):
            raise S6AssignmentError("s6_artefact_invalid", "bimodality.json gmm_2 does not match the frozen parameters")
        result["artefact_present"] = True
        result["artefact_sha256"] = _sha256_bytes(blob)
        result["artefact_absence_classification"] = None
        result["parameter_record_hash_substituted_for_artefact"] = False
    if result["artefact_sha256"] == result["parameter_sha256"]:
        raise S6AssignmentError(
            "s6_artefact_invalid",
            "the canonical parameter-record hash is not a substitute for the bimodality artefact hash",
        )
    return result


def _log_component(length, mean, variance, weight):
    safe_variance = max(float(variance), 1e-12)
    return math.log(max(float(weight), 1e-12)) - 0.5 * (
        math.log(2.0 * math.pi * safe_variance) + (float(length) - float(mean)) ** 2 / safe_variance
    )


def assign_label(length, parameters=None):
    """Assign one positive length. Exact posterior ties return short."""
    if isinstance(length, bool) or type(length) is not int or length < 1:
        raise S6AssignmentError("length_invalid", "the S6 input length is not a positive integer")
    parameters = frozen_parameters() if parameters is None else parameters
    logs = [
        _log_component(length, parameters["means"][index], parameters["variances"][index], parameters["weights"][index])
        for index in (0, 1)
    ]
    if logs[0] >= logs[1]:
        return "short"
    return "long"


def label_from_responsibilities(responsibilities):
    """Map one responsibility pair with the frozen tie rule."""
    if len(responsibilities) != 2:
        raise S6AssignmentError("length_invalid", "a posterior pair is required")
    if float(responsibilities[0]) >= float(responsibilities[1]):
        return "short"
    return "long"


def stored_core_length(stored):
    """Parse ``sequence_length_core``. Blank means the stored length is absent."""
    if stored is None:
        return None
    if isinstance(stored, bool):
        raise S6AssignmentError("stored_length_invalid", "sequence_length_core is not an integer")
    if type(stored) is int:
        value = stored
    elif isinstance(stored, str):
        text = stored.strip()
        if text == "":
            return None
        if text[0] == "-":
            digits = text[1:]
            sign = -1
        else:
            digits = text
            sign = 1
        if not digits.isdigit():
            raise S6AssignmentError("stored_length_invalid", "sequence_length_core is not an integer")
        value = sign * int(digits)
    else:
        raise S6AssignmentError("stored_length_invalid", "sequence_length_core is not an integer")
    if value < 0:
        raise S6AssignmentError("stored_length_invalid", "sequence_length_core is negative")
    return value


def sequence_core_length(sequence, stored_length=None):
    """S6 ``length_of`` for one sequence core.

    A positive stored ``sequence_length_core`` wins. Zero or blank falls
    through to the sequence length. No usable sequence returns None.
    """
    if not isinstance(sequence, str) or sequence == "":
        return None
    stored = stored_core_length(stored_length)
    if stored:
        return stored
    return len(sequence)


def assign_sequence(sequence, stored_length=None, parameters=None):
    """Assign one usable sequence, or return not_applicable when none exists."""
    length = sequence_core_length(sequence, stored_length)
    if length is None:
        return {
            "s6_length_stratum": None,
            "s6_length_stratum_applicability": "not_applicable",
            "s6_length_input": None,
            "s6_input_length": None,
            "s6_input_length_source": "no_usable_sequence",
        }
    source = "sequence_length_core" if stored_core_length(stored_length) else "len_sequence"
    return {
        "s6_length_stratum": assign_label(length, parameters),
        "s6_length_stratum_applicability": "applicable",
        "s6_length_input": "sequence_core_length",
        "s6_input_length": length,
        "s6_input_length_source": source,
    }

#!/usr/bin/env python3
"""M9B-2 synthetic-only AptaRank candidate preparation.

The preparation entry point accepts in-memory membership records or
caller-supplied JSONL bytes. It samples a caller-supplied permitted count,
assigns opaque ids with a caller-supplied 32-byte key, and returns upload,
private-key, and manifest bytes. It does not open a protected ledger, choose
the production sample size, embed a production blinding key, or call AptaRank.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import importlib.util
import io
import json
import os
import shutil
import stat
import sys
import tempfile

PACKAGE_ID = "M9B-2"
SCHEMA_VERSION = "m9b-aptarank-candidate-preparation-v1"
STATUS = "DEFINED_SYNTHETIC_ONLY_PRODUCTION_INPUTS_UNOPENED"
STAGE = "M9B-2"
CONTRACT_RELATIVE = "config/modelling/aptarank_candidate_preparation_contract.json"
CONTRACT_SHA256 = "99c0ff690f716e6b4560a22d04d9a968e7f039288454cc3669c89a1beb65f3b9"
PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md"
PLAN_SHA256 = "b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe"
EVIDENCE_CONTRACT_RELATIVE = "config/modelling/aptarank_evidence_contract.json"
EVIDENCE_CONTRACT_SHA256 = "0494ea740b1a2402032bfa695c23a422b142cda6a2bc043d1da87dbb9ddb092b"
IO_SPEC_RELATIVE = "config/modelling/aptarank_io_spec.json"
IO_SPEC_SHA256 = "46ba6c8be873dad4c086e9f6b889b51702ba31212fa502d00f26e267a22da732"
IO_MODULE_RELATIVE = "scripts/modelling/aptarank_io_preflight.py"
IO_MODULE_SHA256 = "eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01"
EVIDENCE_MODULE_RELATIVE = "scripts/modelling/aptarank_evidence_contract.py"
EVIDENCE_MODULE_SHA256 = "08e780e03108c0008174a4559840ce59a56d567b99376d3ad0272eb29a69bbcb"
CONDITIONS = ("B0", "B1", "B2", "D1")
COMPARISON_ROLES = {
    "B0": "external_baseline",
    "B1": "primary_causal_comparison",
    "B2": "secondary_data_scale_comparator",
    "D1": "primary_causal_comparison",
}
PERMITTED_COUNTS = (200, 150, 100)
D1_SEEDS = (43, 44)
D1_PER_SEED = {200: 100, 150: 75, 100: 50}
D1_BLOCK = {43: "A", 44: "B"}
LENGTH_MIN = 20
LENGTH_MAX = 100
SAMPLING_DOMAIN = "m9b2-candidate-sample-v1"
SAMPLING_SEED = "m9b2-fixed-sampling-seed-v1"
ID_DOMAIN = "m9b2-candidate-id-v1"
ID_PREFIX = "cand_"
TRUNCATION_BYTES = 16
KEY_LENGTH = 32
RECORD_KEYS = ("condition", "source_identity", "sequence", "length", "provenance")
B0_PROVENANCE_KEYS = (
    "b0_seed",
    "b0_chunk_id",
    "line_number",
    "source_artifact_id",
    "source_artifact_sha256",
)
M8_PROVENANCE_KEYS = (
    "checkpoint_identity",
    "generation_seed",
    "requested_biological_length",
    "invocation_index",
    "master_attempt_index",
    "technical_block",
    "source_artifact_id",
    "source_artifact_sha256",
    "d1_training_seed",
)
B2_PROVENANCE_KEYS = (
    "attempt_index",
    "empirical_null_seed",
    "sampled_length",
    "source_artifact_id",
    "source_artifact_sha256",
)
PRIVATE_KEY_KEYS = (
    "candidate_id",
    "condition",
    "comparison_role",
    "source_identity",
    "length",
    "provenance",
)
RESULT_KEYS = (
    "candidate_upload",
    "private_membership_key",
    "preparation_manifest",
    "candidate_upload_sha256",
    "private_membership_key_sha256",
    "preparation_manifest_sha256",
)
UPLOAD_NAME = "candidate_upload.csv"
PRIVATE_KEY_NAME = "private_membership_key.jsonl"
MANIFEST_NAME = "preparation_manifest.json"
TEMP_PREFIX = ".m9b2-candidate-prep."
FORBIDDEN_MANIFEST_TOKENS = ("overlap", "jaccard", "leakage", "nearest")
PIN_ROLES = (
    "preparation_contract",
    "governing_plan",
    "evidence_contract",
    "aptarank_io_specification",
    "aptarank_io_module",
    "evidence_contract_module",
)
TOP_LEVEL_KEYS = (
    "package_id",
    "schema_version",
    "status",
    "stage",
    "deployment_verified",
    "scientific_result",
    "production_inputs_opened",
    "production_membership_count",
    "production_blinding_key",
    "production_upload",
    "production_runner",
    "sealed_production_entry_point",
    "aptarank_execution",
    "governing_plan",
    "evidence_contract",
    "reused_specifications_and_modules",
    "conditions",
    "comparison_roles",
    "comparison_role_placement",
    "technical_eligibility",
    "input_contract",
    "sampling",
    "upload_integrity",
    "opaque_candidate_id",
    "outputs",
    "publication",
    "prohibited",
)
_MODULES = {}


class CandidatePreparationError(ValueError):
    """The synthetic preparation contract refused the request."""

    def __init__(self, code, detail, shortage=None):
        self.code = code
        self.detail = detail
        self.shortage = shortage
        super().__init__(code + ": " + detail)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def contract_path():
    return os.path.join(repo_root(), CONTRACT_RELATIVE)


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=False).encode("utf-8")


def length_delimited_bytes(components):
    """Encode text components as uint32-be lengths plus UTF-8 bytes."""
    chunks = []
    for component in components:
        if type(component) is not str:
            raise CandidatePreparationError("encoding_invalid", "a length-delimited component is not text")
        blob = component.encode("utf-8")
        chunks.append(len(blob).to_bytes(4, "big"))
        chunks.append(blob)
    return b"".join(chunks)


def membership_priority(condition, source_identity, sequence):
    """SHA-256 priority. Lower digests are selected first."""
    payload = length_delimited_bytes(
        [SAMPLING_DOMAIN, SAMPLING_SEED, condition, source_identity, sequence]
    )
    return hashlib.sha256(payload).digest()


def candidate_id_for_sequence(sequence, blinding_key, truncation_bytes):
    """HMAC-SHA-256 truncated id. The key is not written into the preimage."""
    _require_blinding_key(blinding_key)
    if type(truncation_bytes) is not int or truncation_bytes < 1 or truncation_bytes > 32:
        raise CandidatePreparationError("opaque_id_truncation_invalid", "the truncation length is not valid")
    payload = length_delimited_bytes([ID_DOMAIN, sequence])
    digest = hmac.new(blinding_key, payload, hashlib.sha256).digest()
    return ID_PREFIX + digest[:truncation_bytes].hex()


def assign_candidate_ids(sequences, blinding_key, truncation_bytes):
    """Assign one id per sequence. A truncated collision fails closed."""
    assigned = {}
    owners = {}
    for sequence in sequences:
        candidate_id = candidate_id_for_sequence(sequence, blinding_key, truncation_bytes)
        previous = owners.get(candidate_id)
        if previous is not None and previous != sequence:
            raise CandidatePreparationError(
                "opaque_id_collision",
                "truncated HMAC candidate ids collided; the id is not lengthened or renamed",
            )
        owners[candidate_id] = sequence
        assigned[sequence] = candidate_id
    return assigned


def _load_module(filename, module_name):
    if module_name in _MODULES:
        return _MODULES[module_name]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MODULES[module_name] = module
    return module


def _parser():
    return _load_module("generator_eval_parser.py", "generator_eval_parser_for_m9b2")


def _evidence():
    return _load_module("aptarank_evidence_contract.py", "aptarank_evidence_contract_for_m9b2")


def _arp1():
    return _load_module("aptarank_io_preflight.py", "aptarank_io_preflight_for_m9b2")


def _exact_keys(document, expected, code, detail):
    if type(document) is not dict or set(document) != set(expected):
        raise CandidatePreparationError(code, detail)


def _require(condition, code, detail):
    if not condition:
        raise CandidatePreparationError(code, detail)


def _read_pinned_file(relative):
    if type(relative) is not str or relative == "" or os.path.isabs(relative) or ".." in relative.split("/"):
        raise CandidatePreparationError("pin_invalid", "a pinned path is not a repository-relative file")
    path = os.path.join(repo_root(), relative)
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise CandidatePreparationError("pin_unreadable", "a pinned file cannot be read") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise CandidatePreparationError("pin_symlink", "a pinned file is not a regular file")
    with open(path, "rb") as handle:
        return handle.read()


def _pin_table(document):
    reused = {item["role"]: item for item in document["reused_specifications_and_modules"]}
    return {
        "preparation_contract": {
            "path": CONTRACT_RELATIVE,
            "sha256": CONTRACT_SHA256,
        },
        "governing_plan": document["governing_plan"],
        "evidence_contract": document["evidence_contract"],
        "aptarank_io_specification": reused["aptarank_io_specification"],
        "aptarank_io_module": reused["aptarank_io_module"],
        "evidence_contract_module": reused["evidence_contract_module"],
    }


def validate_contract_document(document):
    """Refuse a preparation contract that drifts from the M9B-2 pins."""
    _exact_keys(document, TOP_LEVEL_KEYS, "spec_invalid", "the preparation contract keys changed")
    _require(document["package_id"] == PACKAGE_ID, "spec_invalid", "the package id is not M9B-2")
    _require(document["schema_version"] == SCHEMA_VERSION, "spec_invalid", "the schema version drifted")
    _require(document["status"] == STATUS, "spec_invalid", "the preparation status drifted")
    _require(document["stage"] == STAGE, "spec_invalid", "the stage is not M9B-2")
    for flag in (
        "deployment_verified",
        "scientific_result",
        "production_inputs_opened",
        "production_runner",
        "sealed_production_entry_point",
        "aptarank_execution",
    ):
        _require(document[flag] is False, "spec_invalid", flag + " must remain false")
    for empty in ("production_membership_count", "production_blinding_key", "production_upload"):
        _require(document[empty] is None, "production_value_refused", empty + " must remain null")

    plan = document["governing_plan"]
    _exact_keys(plan, ("path", "version", "revision_date", "sha256"), "spec_invalid", "the governing plan record drifted")
    _require(plan["path"] == PLAN_RELATIVE, "spec_invalid", "the governing plan path drifted")
    _require(plan["version"] == "3.3", "spec_invalid", "the governing plan version drifted")
    _require(plan["revision_date"] == "12 October 2026", "spec_invalid", "the governing plan date drifted")
    _require(plan["sha256"] == PLAN_SHA256, "spec_invalid", "the governing plan hash drifted")

    evidence = document["evidence_contract"]
    _exact_keys(evidence, ("path", "package_id", "sha256"), "spec_invalid", "the evidence-contract pin drifted")
    _require(evidence["path"] == EVIDENCE_CONTRACT_RELATIVE, "spec_invalid", "the evidence-contract path drifted")
    _require(evidence["package_id"] == "M9B-1", "spec_invalid", "the evidence-contract package drifted")
    _require(evidence["sha256"] == EVIDENCE_CONTRACT_SHA256, "spec_invalid", "the evidence-contract hash drifted")

    reused = document["reused_specifications_and_modules"]
    _require(type(reused) is list and len(reused) == 3, "spec_invalid", "the reused specification list drifted")
    expected_reused = (
        ("aptarank_io_specification", IO_SPEC_RELATIVE, IO_SPEC_SHA256),
        ("aptarank_io_module", IO_MODULE_RELATIVE, IO_MODULE_SHA256),
        ("evidence_contract_module", EVIDENCE_MODULE_RELATIVE, EVIDENCE_MODULE_SHA256),
    )
    for item, expected in zip(reused, expected_reused):
        _exact_keys(item, ("role", "path", "sha256"), "spec_invalid", "a reused specification record drifted")
        _require(tuple(item[key] for key in ("role", "path", "sha256")) == expected, "spec_invalid", "a reused pin drifted")

    _require(tuple(document["conditions"]) == CONDITIONS, "spec_invalid", "the condition order drifted")
    _require(document["comparison_roles"] == COMPARISON_ROLES, "spec_invalid", "the comparison roles drifted")
    _require(
        document["comparison_role_placement"] == "private_membership_provenance_not_candidate_id",
        "spec_invalid",
        "comparison roles must stay out of candidate ids",
    )

    eligibility = document["technical_eligibility"]
    _exact_keys(
        eligibility,
        (
            "source_fact_id",
            "source_statement_pin",
            "minimum_length",
            "maximum_length",
            "inclusive",
            "alphabet",
            "silent_normalization",
        ),
        "spec_invalid",
        "the technical eligibility record drifted",
    )
    _require(eligibility["source_fact_id"] == "length_limits", "spec_invalid", "the length fact id drifted")
    _require(eligibility["source_statement_pin"] == "20 through 100", "spec_invalid", "the length statement pin drifted")
    _require(eligibility["minimum_length"] == LENGTH_MIN, "spec_invalid", "the minimum length drifted")
    _require(eligibility["maximum_length"] == LENGTH_MAX, "spec_invalid", "the maximum length drifted")
    _require(eligibility["inclusive"] is True, "spec_invalid", "the length bounds must stay inclusive")
    _require(eligibility["alphabet"] == "canonical_uppercase_ACGU", "spec_invalid", "the alphabet pin drifted")
    _require(eligibility["silent_normalization"] is False, "spec_invalid", "silent normalization must stay off")

    incoming = document["input_contract"]
    _exact_keys(
        incoming,
        (
            "grain",
            "accepted_forms",
            "production_source_paths",
            "record_keys",
            "jsonl_record_splitting",
            "repeated_within_condition_membership",
            "silent_deduplication",
            "source_identity_unique",
            "provenance_by_condition",
        ),
        "spec_invalid",
        "the input contract drifted",
    )
    _require(incoming["accepted_forms"] == ["in_memory_records", "caller_supplied_utf8_jsonl_bytes"], "spec_invalid", "the accepted input forms drifted")
    _require(incoming["production_source_paths"] is False, "spec_invalid", "production source paths must stay refused")
    _require(tuple(incoming["record_keys"]) == RECORD_KEYS, "spec_invalid", "the input record keys drifted")
    _require(incoming["jsonl_record_splitting"] == "existing_parser_split_raw_record_bytes", "spec_invalid", "JSONL splitting must reuse the parser")
    _require(incoming["repeated_within_condition_membership"] == "fail_closed", "spec_invalid", "repeated membership must fail closed")
    _require(incoming["silent_deduplication"] is False, "spec_invalid", "silent deduplication must stay off")
    _require(incoming["source_identity_unique"] is True, "spec_invalid", "source identity must stay unique")
    provenance = incoming["provenance_by_condition"]
    _require(tuple(provenance) == CONDITIONS, "spec_invalid", "provenance condition order drifted")
    _exact_keys(
        provenance["B0"],
        ("keys", "b0_seed_role", "d1_training_seed", "empirical_null_seed"),
        "spec_invalid",
        "B0 provenance roles drifted",
    )
    _require(tuple(provenance["B0"]["keys"]) == B0_PROVENANCE_KEYS, "spec_invalid", "B0 provenance keys drifted")
    _require(provenance["B0"]["b0_seed_role"] == "chunk_seed_not_training_seed", "spec_invalid", "the B0 seed role drifted")
    _require(provenance["B0"]["d1_training_seed"] == "absent", "spec_invalid", "B0 must not gain a training seed")
    _require(provenance["B0"]["empirical_null_seed"] == "absent", "spec_invalid", "B0 must not gain an empirical-null seed")
    _exact_keys(
        provenance["B1"],
        ("keys", "d1_training_seed", "technical_block_values"),
        "spec_invalid",
        "B1 provenance roles drifted",
    )
    _require(tuple(provenance["B1"]["keys"]) == M8_PROVENANCE_KEYS, "spec_invalid", "B1 provenance keys drifted")
    _require(provenance["B1"]["d1_training_seed"] is None, "spec_invalid", "B1 training seed must stay null")
    _require(provenance["B1"]["technical_block_values"] == ["A", "B"], "spec_invalid", "B1 technical blocks drifted")
    _exact_keys(
        provenance["B2"],
        ("keys", "empirical_null_seed_role", "d1_training_seed"),
        "spec_invalid",
        "B2 provenance roles drifted",
    )
    _require(tuple(provenance["B2"]["keys"]) == B2_PROVENANCE_KEYS, "spec_invalid", "B2 provenance keys drifted")
    _require(
        provenance["B2"]["empirical_null_seed_role"] == "empirical_null_seed_not_training_seed",
        "spec_invalid",
        "the B2 seed role drifted",
    )
    _require(provenance["B2"]["d1_training_seed"] == "absent", "spec_invalid", "B2 must not gain a training seed")
    _exact_keys(
        provenance["D1"],
        ("keys", "training_seeds", "training_seed_technical_block"),
        "spec_invalid",
        "D1 provenance roles drifted",
    )
    _require(tuple(provenance["D1"]["keys"]) == M8_PROVENANCE_KEYS, "spec_invalid", "D1 provenance keys drifted")
    _require(tuple(provenance["D1"]["training_seeds"]) == D1_SEEDS, "spec_invalid", "D1 training seeds drifted")
    _require(
        provenance["D1"]["training_seed_technical_block"]
        == [
            {"training_seed": 43, "technical_block": "A"},
            {"training_seed": 44, "technical_block": "B"},
        ],
        "spec_invalid",
        "the D1 seed block allocation drifted",
    )

    sampling = document["sampling"]
    _exact_keys(
        sampling,
        (
            "domain_separator",
            "sampling_seed",
            "algorithm",
            "encoding",
            "priority_components",
            "selection",
            "tie_break",
            "permitted_membership_counts",
            "production_membership_count_chosen",
            "same_count_for_every_condition",
            "d1_balance",
            "d1_seed_membership_counts",
            "equal_seed_weighting_applied",
            "cross_seed_replenishment",
            "score_replenishment",
            "library_prng",
            "python_hash_randomization",
            "depends_on_input_order",
            "depends_on_filesystem_order",
        ),
        "spec_invalid",
        "the sampling contract drifted",
    )
    _require(sampling["domain_separator"] == SAMPLING_DOMAIN, "spec_invalid", "the sampling domain drifted")
    _require(sampling["sampling_seed"] == SAMPLING_SEED, "spec_invalid", "the sampling seed drifted")
    _require(sampling["algorithm"] == "sha256_length_delimited_priority", "spec_invalid", "the sampling algorithm drifted")
    _require(
        sampling["priority_components"]
        == ["domain_separator", "sampling_seed", "condition", "source_identity", "canonical_sequence"],
        "spec_invalid",
        "the priority components drifted",
    )
    _require(sampling["selection"] == "lowest_priority_without_replacement", "spec_invalid", "the selection rule drifted")
    _require(
        sampling["tie_break"] == ["sha256_priority_bytes", "source_identity_utf8", "canonical_sequence_utf8"],
        "spec_invalid",
        "the tie break drifted",
    )
    _require(tuple(sampling["permitted_membership_counts"]) == PERMITTED_COUNTS, "spec_invalid", "the permitted counts drifted")
    _require(sampling["production_membership_count_chosen"] is False, "production_value_refused", "M9B-2 must not choose the production count")
    _require(sampling["same_count_for_every_condition"] is True, "spec_invalid", "the common count rule drifted")
    _require(sampling["d1_balance"] == "equal_memberships_per_recorded_training_seed", "spec_invalid", "the D1 balance rule drifted")
    _require(
        sampling["d1_seed_membership_counts"]
        == [
            {"membership_count": 200, "per_training_seed": 100},
            {"membership_count": 150, "per_training_seed": 75},
            {"membership_count": 100, "per_training_seed": 50},
        ],
        "spec_invalid",
        "the D1 seed counts drifted",
    )
    for flag in (
        "equal_seed_weighting_applied",
        "cross_seed_replenishment",
        "score_replenishment",
        "library_prng",
        "python_hash_randomization",
        "depends_on_input_order",
        "depends_on_filesystem_order",
    ):
        _require(sampling[flag] is False, "spec_invalid", flag + " must remain false")

    grouping = document["upload_integrity"]
    _exact_keys(
        grouping,
        (
            "label",
            "operation",
            "not_a_cross_condition_metric",
            "pair_table_emitted",
            "shared_sequence_counts_emitted",
            "replenish_after_upload_grouping",
        ),
        "spec_invalid",
        "the upload-integrity contract drifted",
    )
    _require(grouping["label"] == "one_row_per_globally_distinct_selected_sequence", "spec_invalid", "the upload-integrity label drifted")
    _require(grouping["not_a_cross_condition_metric"] is True, "spec_invalid", "upload grouping must not be a cross-condition metric")
    _require(grouping["pair_table_emitted"] is False, "spec_invalid", "a pair table must not be emitted")
    _require(grouping["shared_sequence_counts_emitted"] is False, "spec_invalid", "shared-sequence counts must not be emitted")
    _require(grouping["replenish_after_upload_grouping"] is False, "spec_invalid", "upload grouping must not replenish")

    opaque = document["opaque_candidate_id"]
    _exact_keys(
        opaque,
        (
            "domain_separator",
            "algorithm",
            "encoding",
            "key_length_bytes",
            "truncation_bytes",
            "textual_form",
            "prefix",
            "hex_length",
            "arp1_column_type",
            "collision_policy",
            "lengthen_on_collision",
            "rename_on_collision",
            "same_sequence_same_id_across_conditions",
            "id_changes_when_secret_changes",
            "sample_membership_changes_when_secret_changes",
            "excluded_from_id",
            "production_key_embedded",
        ),
        "spec_invalid",
        "the opaque-id contract drifted",
    )
    _require(opaque["domain_separator"] == ID_DOMAIN, "spec_invalid", "the opaque-id domain drifted")
    _require(opaque["algorithm"] == "hmac_sha256", "spec_invalid", "the opaque-id algorithm drifted")
    _require(opaque["key_length_bytes"] == KEY_LENGTH, "spec_invalid", "the blinding-key length drifted")
    _require(opaque["truncation_bytes"] == TRUNCATION_BYTES, "spec_invalid", "the truncation length drifted")
    _require(opaque["prefix"] == ID_PREFIX, "spec_invalid", "the candidate-id prefix drifted")
    _require(opaque["hex_length"] == TRUNCATION_BYTES * 2, "spec_invalid", "the candidate-id hex length drifted")
    _require(opaque["textual_form"] == "cand_<lowercase_hex>", "spec_invalid", "the candidate-id form drifted")
    _require(opaque["arp1_column_type"] == "nonempty_opaque_id", "spec_invalid", "the ARP-1 id type drifted")
    _require(opaque["collision_policy"] == "fail_closed", "spec_invalid", "id collisions must fail closed")
    _require(opaque["lengthen_on_collision"] is False, "spec_invalid", "a collision must not lengthen an id")
    _require(opaque["rename_on_collision"] is False, "spec_invalid", "a collision must not rename an id")
    _require(opaque["same_sequence_same_id_across_conditions"] is True, "spec_invalid", "one sequence must keep one id")
    _require(opaque["id_changes_when_secret_changes"] is True, "spec_invalid", "the secret must change ids")
    _require(opaque["sample_membership_changes_when_secret_changes"] is False, "spec_invalid", "the secret must not change membership")
    _require(opaque["production_key_embedded"] is False, "production_value_refused", "a production blinding key must not be embedded")
    _require(
        opaque["excluded_from_id"]
        == ["condition", "training_seed", "source_identity", "sequence_prefix", "target", "rank", "comparison_role"],
        "spec_invalid",
        "the opaque-id exclusion list drifted",
    )

    outputs = document["outputs"]
    _exact_keys(
        outputs,
        ("candidate_upload", "private_membership_key", "preparation_manifest"),
        "spec_invalid",
        "the output contract drifted",
    )
    _require(outputs["candidate_upload"]["filename"] == UPLOAD_NAME, "spec_invalid", "the upload filename drifted")
    _require(outputs["candidate_upload"]["columns"] == ["id", "sequence"], "spec_invalid", "the upload columns drifted")
    _require(outputs["candidate_upload"]["sequence_preserved_exactly"] is True, "spec_invalid", "uploaded sequences must be preserved")
    _require(outputs["private_membership_key"]["filename"] == PRIVATE_KEY_NAME, "spec_invalid", "the private-key filename drifted")
    _require(tuple(outputs["private_membership_key"]["keys"]) == PRIVATE_KEY_KEYS, "spec_invalid", "the private-key fields drifted")
    _require(outputs["private_membership_key"]["sequence_included"] is False, "spec_invalid", "the private key must not carry sequences")
    _require(outputs["private_membership_key"]["invented_provenance"] is False, "spec_invalid", "provenance must not be invented")
    _require(outputs["preparation_manifest"]["filename"] == MANIFEST_NAME, "spec_invalid", "the manifest filename drifted")
    _require(outputs["preparation_manifest"]["own_sha256_embedded"] is False, "spec_invalid", "the manifest must not embed its own hash")
    for flag in (
        "includes_sequence_strings",
        "includes_source_identifiers",
        "includes_candidate_identifiers",
        "includes_hmac_key",
        "includes_per_condition_shared_sequence_counts",
    ):
        _require(outputs["preparation_manifest"][flag] is False, "spec_invalid", flag + " must remain false")

    publication = document["publication"]
    _exact_keys(
        publication,
        (
            "helper",
            "destination_must_not_exist",
            "refuse",
            "temporary_sibling",
            "verify_bytes_and_sha256",
            "promote_by_one_rename",
            "clean_temporary_output_on_failure",
            "production_locator",
            "results_directory_refused",
        ),
        "spec_invalid",
        "the publication contract drifted",
    )
    _require(publication["helper"] == "publish_directory", "spec_invalid", "the publication helper drifted")
    _require(publication["destination_must_not_exist"] is True, "spec_invalid", "publication must require a new destination")
    _require(publication["refuse"] == ["file", "existing_directory", "symlink"], "spec_invalid", "the publication refusal list drifted")
    _require(publication["temporary_sibling"] is True, "spec_invalid", "publication must use a temporary sibling")
    _require(publication["verify_bytes_and_sha256"] is True, "spec_invalid", "publication must verify bytes and hashes")
    _require(publication["promote_by_one_rename"] is True, "spec_invalid", "publication must promote by one rename")
    _require(publication["clean_temporary_output_on_failure"] is True, "spec_invalid", "publication must clean a failed temporary output")
    _require(publication["production_locator"] is False, "spec_invalid", "M9B-2 has no production locator")
    _require(publication["results_directory_refused"] is True, "spec_invalid", "publication into results must stay refused")

    prohibited = document["prohibited"]
    _require(type(prohibited) is list and prohibited, "spec_invalid", "the prohibited list is missing")
    prohibited_text = "\n".join(prohibited)
    for phrase in (
        "TRAIN",
        "VALIDATION",
        "REF",
        "EVAL",
        "production sequence ledger",
        "AptaRank",
        "Tier 1",
        "Tier 2",
        "production blinding key",
    ):
        _require(phrase in prohibited_text, "spec_invalid", "a prohibited action is missing")
    return document


def verify_external_pins(document, blobs):
    """Compare pinned hashes with caller-supplied file bytes."""
    validate_contract_document(document)
    _require(type(blobs) is dict and set(blobs) == set(PIN_ROLES), "pin_invalid", "the pin byte set is incomplete")
    expected = {
        "preparation_contract": CONTRACT_SHA256,
        "governing_plan": PLAN_SHA256,
        "evidence_contract": EVIDENCE_CONTRACT_SHA256,
        "aptarank_io_specification": IO_SPEC_SHA256,
        "aptarank_io_module": IO_MODULE_SHA256,
        "evidence_contract_module": EVIDENCE_MODULE_SHA256,
    }
    recorded = _pin_table(document)
    for role, digest in expected.items():
        payload = blobs[role]
        _require(type(payload) is bytes, "pin_invalid", "a pinned payload is not bytes")
        actual = sha256_bytes(payload)
        if actual != digest or recorded[role]["sha256"] != digest:
            raise CandidatePreparationError("pin_mismatch", "the " + role + " pin does not match")
    return document


def assert_reused_validators(evidence_document, io_spec):
    """Reuse the frozen evidence and ARP-1 validators' recorded rules."""
    facts = evidence_document.get("facts") if type(evidence_document) is dict else None
    length_fact = None
    if type(facts) is list:
        for fact in facts:
            if type(fact) is dict and fact.get("id") == "length_limits":
                length_fact = fact
                break
    statement = length_fact.get("statement") if type(length_fact) is dict else ""
    if "20 through 100" not in statement:
        raise CandidatePreparationError("pin_mismatch", "the AptaRank length bound is not the pinned evidence fact")
    columns = io_spec.get("candidate_upload_column_order") if type(io_spec) is dict else None
    column_types = io_spec.get("column_types") if type(io_spec) is dict else None
    candidate_types = column_types.get("candidate_upload") if type(column_types) is dict else None
    if columns != ["id", "sequence"]:
        raise CandidatePreparationError("pin_mismatch", "the ARP-1 candidate columns are not id and sequence")
    if type(candidate_types) is not dict:
        raise CandidatePreparationError("pin_mismatch", "the ARP-1 candidate column types are missing")
    if candidate_types.get("id") != "nonempty_opaque_id" or candidate_types.get("sequence") != "uppercase_acgu":
        raise CandidatePreparationError("pin_mismatch", "the ARP-1 candidate column types drifted")
    arp1 = _arp1()
    if arp1.ID_TEXT.fullmatch(ID_PREFIX + ("ab" * TRUNCATION_BYTES)) is None:
        raise CandidatePreparationError("pin_mismatch", "the candidate id form is not an ARP-1 opaque id")
    if tuple(arp1.CANDIDATE_COLUMNS) != ("id", "sequence"):
        raise CandidatePreparationError("pin_mismatch", "the ARP-1 candidate column constant drifted")


def load_pinned_contract():
    """Load the preparation contract and fail closed on every recorded pin."""
    contract_bytes = _read_pinned_file(CONTRACT_RELATIVE)
    if sha256_bytes(contract_bytes) != CONTRACT_SHA256:
        raise CandidatePreparationError("pin_mismatch", "the preparation contract pin does not match")
    try:
        document = json.loads(contract_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidatePreparationError("spec_invalid", "the preparation contract is not readable JSON") from exc
    blobs = {
        "preparation_contract": contract_bytes,
        "governing_plan": _read_pinned_file(PLAN_RELATIVE),
        "evidence_contract": _read_pinned_file(EVIDENCE_CONTRACT_RELATIVE),
        "aptarank_io_specification": _read_pinned_file(IO_SPEC_RELATIVE),
        "aptarank_io_module": _read_pinned_file(IO_MODULE_RELATIVE),
        "evidence_contract_module": _read_pinned_file(EVIDENCE_MODULE_RELATIVE),
    }
    verify_external_pins(document, blobs)
    evidence = _evidence()
    arp1 = _arp1()
    try:
        evidence_document, evidence_payload = evidence.load_contract()
    except evidence.EvidenceContractError as exc:
        raise CandidatePreparationError(exc.code, exc.detail) from exc
    if sha256_bytes(evidence_payload) != EVIDENCE_CONTRACT_SHA256:
        raise CandidatePreparationError("pin_mismatch", "the evidence-contract pin does not match")
    try:
        io_spec, io_spec_bytes = arp1.load_spec()
    except arp1.AptaRankIOError as exc:
        raise CandidatePreparationError(exc.code, exc.detail) from exc
    if sha256_bytes(io_spec_bytes) != IO_SPEC_SHA256:
        raise CandidatePreparationError("pin_mismatch", "the io-specification pin does not match")
    assert_reused_validators(evidence_document, io_spec)
    return document


def _firewall(controls):
    parser = _parser()
    try:
        parser.enforce_firewall(controls)
    except parser.ParserContractError as exc:
        raise CandidatePreparationError(exc.code, exc.detail) from exc


def _path_object(value):
    if isinstance(value, (str, bytes, bytearray)):
        return False
    return callable(getattr(value, "__fspath__", None))


def _reject_non_bytes_payload(value):
    parser = _parser()
    if _path_object(value):
        raise CandidatePreparationError("filesystem_path_refused", "a filesystem path argument is refused")
    if type(value) is str:
        try:
            parser.reject_control_string(value)
        except parser.ParserContractError as exc:
            raise CandidatePreparationError(exc.code, exc.detail) from exc
        raise CandidatePreparationError("input_type_invalid", "membership input must be records or bytes")


def _require_blinding_key(value):
    if value is None:
        raise CandidatePreparationError("blinding_key_missing", "a 32-byte blinding key is required")
    if type(value) is not bytes or len(value) != KEY_LENGTH:
        raise CandidatePreparationError("blinding_key_malformed", "the blinding key must be exactly 32 bytes")
    return value


def _require_membership_count(value):
    if type(value) is not int or value not in PERMITTED_COUNTS:
        raise CandidatePreparationError(
            "membership_count_invalid",
            "the membership count must be 200, 150, or 100",
        )
    return value


def _token(value):
    parser = _parser()
    if type(value) is not str or value == "" or len(value) > 200 or not value.isascii():
        return False
    if any(character.isspace() for character in value):
        return False
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:._+-")
    if any(character not in allowed for character in value):
        return False
    try:
        parser.reject_control_string(value)
    except parser.ParserContractError:
        return False
    return True


def _nonnegative_int(value):
    return type(value) is int and value >= 0


def _positive_int(value):
    return type(value) is int and value >= 1


def _sha256_text(value):
    parser = _parser()
    return parser.sha256_text(value)


def _freeze_provenance(condition, provenance):
    if condition == "B0":
        _exact_keys(provenance, B0_PROVENANCE_KEYS, "provenance_invalid", "B0 provenance fields are not the recorded set")
        if not _nonnegative_int(provenance["b0_seed"]):
            raise CandidatePreparationError("provenance_invalid", "the B0 chunk seed is not a nonnegative integer")
        if not _token(provenance["b0_chunk_id"]) or not _token(provenance["source_artifact_id"]):
            raise CandidatePreparationError("provenance_invalid", "a B0 provenance token is not valid")
        if not _positive_int(provenance["line_number"]) or not _sha256_text(provenance["source_artifact_sha256"]):
            raise CandidatePreparationError("provenance_invalid", "B0 line or artifact provenance is not valid")
        return {key: provenance[key] for key in B0_PROVENANCE_KEYS}
    if condition in ("B1", "D1"):
        _exact_keys(provenance, M8_PROVENANCE_KEYS, "provenance_invalid", condition + " provenance fields are not the recorded set")
        if not _token(provenance["checkpoint_identity"]) or not _token(provenance["source_artifact_id"]):
            raise CandidatePreparationError("provenance_invalid", condition + " provenance tokens are not valid")
        if not _nonnegative_int(provenance["generation_seed"]):
            raise CandidatePreparationError("provenance_invalid", condition + " generation seed is not a nonnegative integer")
        if not _positive_int(provenance["requested_biological_length"]):
            raise CandidatePreparationError("provenance_invalid", condition + " requested length is not a positive integer")
        if not _nonnegative_int(provenance["invocation_index"]) or not _nonnegative_int(provenance["master_attempt_index"]):
            raise CandidatePreparationError("provenance_invalid", condition + " attempt indexes are not valid")
        if provenance["technical_block"] not in ("A", "B"):
            raise CandidatePreparationError("provenance_invalid", condition + " technical block is not A or B")
        if not _sha256_text(provenance["source_artifact_sha256"]):
            raise CandidatePreparationError("provenance_invalid", condition + " artifact hash is not valid")
        if condition == "B1":
            if provenance["d1_training_seed"] is not None:
                raise CandidatePreparationError("d1_training_seed_invalid", "B1 requires a null training seed")
        else:
            seed = provenance["d1_training_seed"]
            if seed not in D1_SEEDS:
                raise CandidatePreparationError("d1_training_seed_invalid", "D1 training seed must be 43 or 44")
            if provenance["technical_block"] != D1_BLOCK[seed]:
                raise CandidatePreparationError(
                    "d1_training_seed_invalid",
                    "D1 training seed %d belongs with technical block %s" % (seed, D1_BLOCK[seed]),
                )
        return {key: provenance[key] for key in M8_PROVENANCE_KEYS}
    _exact_keys(provenance, B2_PROVENANCE_KEYS, "provenance_invalid", "B2 provenance fields are not the recorded set")
    if not _nonnegative_int(provenance["attempt_index"]) or not _nonnegative_int(provenance["empirical_null_seed"]):
        raise CandidatePreparationError("provenance_invalid", "B2 attempt or empirical-null seed is not valid")
    if not _nonnegative_int(provenance["sampled_length"]):
        raise CandidatePreparationError("provenance_invalid", "B2 sampled length is not a nonnegative integer")
    if not _token(provenance["source_artifact_id"]) or not _sha256_text(provenance["source_artifact_sha256"]):
        raise CandidatePreparationError("provenance_invalid", "B2 artifact provenance is not valid")
    return {key: provenance[key] for key in B2_PROVENANCE_KEYS}


def _normalize_one(raw):
    _exact_keys(raw, RECORD_KEYS, "input_invalid", "a membership record does not match the input contract")
    condition = raw["condition"]
    if condition not in CONDITIONS:
        raise CandidatePreparationError("condition_invalid", "condition must be B0, B1, B2, or D1")
    if not _token(raw["source_identity"]):
        raise CandidatePreparationError("source_identity_invalid", "a source identity is not a stable token")
    arp1 = _arp1()
    sequence = raw["sequence"]
    if type(sequence) is not str or arp1.SEQUENCE_TEXT.fullmatch(sequence) is None:
        raise CandidatePreparationError("sequence_invalid", "a membership sequence is not canonical uppercase A, C, G, and U")
    length = raw["length"]
    if type(length) is not int or length != len(sequence):
        raise CandidatePreparationError("length_invalid", "a membership length does not match its sequence")
    if length < LENGTH_MIN or length > LENGTH_MAX:
        raise CandidatePreparationError("length_ineligible", "a membership length is outside 20 through 100 inclusive")
    provenance = _freeze_provenance(condition, raw["provenance"])
    return {
        "condition": condition,
        "source_identity": raw["source_identity"],
        "sequence": sequence,
        "length": length,
        "comparison_role": COMPARISON_ROLES[condition],
        "provenance": provenance,
    }


def _normalize_records(raw_records):
    if type(raw_records) is not list:
        raise CandidatePreparationError("input_type_invalid", "membership records must be a list")
    source_ids = set()
    memberships = set()
    normalized = []
    for raw in raw_records:
        if type(raw) is not dict:
            raise CandidatePreparationError("malformed_input", "a membership record is not an object")
        row = _normalize_one(raw)
        if row["source_identity"] in source_ids:
            raise CandidatePreparationError(
                "duplicate_source_identity",
                "source identity %s is duplicated" % row["source_identity"],
            )
        source_ids.add(row["source_identity"])
        membership = (row["condition"], row["sequence"])
        if membership in memberships:
            raise CandidatePreparationError(
                "repeated_within_condition_membership",
                "condition %s repeats a sequence membership" % row["condition"],
            )
        memberships.add(membership)
        normalized.append(row)
    return normalized


def _records_from_payload(payload):
    _reject_non_bytes_payload(payload)
    if type(payload) is not bytes:
        raise CandidatePreparationError("input_type_invalid", "membership bytes are required")
    parser = _parser()
    try:
        lines = parser.split_raw_record_bytes(payload)
    except parser.ParserContractError as exc:
        raise CandidatePreparationError(exc.code, exc.detail) from exc
    records = []
    for index, line in enumerate(lines, start=1):
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CandidatePreparationError("malformed_input", "membership JSONL is not UTF-8") from exc
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CandidatePreparationError("malformed_input", "membership JSONL row %d is not JSON" % index) from exc
        if type(value) is not dict:
            raise CandidatePreparationError("malformed_input", "membership JSONL row %d is not an object" % index)
        records.append(value)
    return records


def _rank_key(row):
    return (
        membership_priority(row["condition"], row["source_identity"], row["sequence"]),
        row["source_identity"].encode("utf-8"),
        row["sequence"].encode("utf-8"),
    )


def _shortage_condition(condition, requested, eligible):
    return {
        "stratum": "condition",
        "condition": condition,
        "requested_membership_count": requested,
        "eligible_membership_count": eligible,
        "shortage": requested - eligible,
    }


def _shortage_seed(seed, requested, eligible):
    return {
        "stratum": "d1_training_seed",
        "condition": "D1",
        "training_seed": seed,
        "requested_membership_count": requested,
        "eligible_membership_count": eligible,
        "shortage": requested - eligible,
    }


def select_memberships(rows, membership_count):
    """Select the lowest priorities. Shortages fail closed and are not replenished."""
    per_seed = D1_PER_SEED[membership_count]
    grouped = {condition: [] for condition in CONDITIONS}
    for row in rows:
        grouped[row["condition"]].append(row)
    shortages = []
    selected = []
    for condition in ("B0", "B1", "B2"):
        pool = grouped[condition]
        if len(pool) < membership_count:
            shortages.append(_shortage_condition(condition, membership_count, len(pool)))
        else:
            selected.extend(sorted(pool, key=_rank_key)[:membership_count])
    by_seed = {seed: [] for seed in D1_SEEDS}
    for row in grouped["D1"]:
        by_seed[row["provenance"]["d1_training_seed"]].append(row)
    for seed in D1_SEEDS:
        pool = by_seed[seed]
        if len(pool) < per_seed:
            shortages.append(_shortage_seed(seed, per_seed, len(pool)))
        else:
            selected.extend(sorted(pool, key=_rank_key)[:per_seed])
    if shortages:
        detail = json.dumps({"shortages": shortages}, separators=(",", ":"), sort_keys=True)
        raise CandidatePreparationError("shortage", detail, shortage=shortages)
    return selected


def _candidate_upload_bytes(sequences, ids):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["id", "sequence"])
    for sequence in sorted(sequences, key=lambda item: item.encode("utf-8")):
        writer.writerow([ids[sequence], sequence])
    payload = buffer.getvalue().encode("utf-8")
    if b"\r" in payload:
        raise CandidatePreparationError("upload_validation_failed", "the candidate upload contains a carriage return")
    return payload


def _validate_upload(payload, ids):
    arp1 = _arp1()
    errors = arp1.ErrorList()
    parsed = arp1.parse_csv_rows(payload, arp1.CANDIDATE_COLUMNS, errors, "candidate upload")
    arp1._check_candidate_rows(parsed, errors)
    try:
        errors.raise_if_any()
    except arp1.AptaRankIOError as exc:
        raise CandidatePreparationError("upload_validation_failed", exc.detail) from exc
    expected = sorted(ids, key=lambda item: item.encode("utf-8"))
    if parsed is None or [row["sequence"] for row in parsed] != expected:
        raise CandidatePreparationError("upload_validation_failed", "the candidate upload sequences drifted")
    for row in parsed:
        if row["id"] != ids[row["sequence"]] or arp1.ID_TEXT.fullmatch(row["id"]) is None:
            raise CandidatePreparationError("upload_validation_failed", "a candidate upload id drifted")
        if row["sequence"] != parsed[expected.index(row["sequence"])]["sequence"]:
            raise CandidatePreparationError("upload_validation_failed", "a candidate sequence was not preserved")


def _private_key_bytes(selected, ids):
    lines = []
    for row in selected:
        document = {
            "candidate_id": ids[row["sequence"]],
            "condition": row["condition"],
            "comparison_role": row["comparison_role"],
            "source_identity": row["source_identity"],
            "length": row["length"],
            "provenance": row["provenance"],
        }
        _exact_keys(document, PRIVATE_KEY_KEYS, "private_key_invalid", "a private-key row drifted")
        lines.append(canonical_json_bytes(document))
    if not lines:
        raise CandidatePreparationError("private_key_invalid", "the private key has no memberships")
    return b"\n".join(lines) + b"\n"


def _count_rows(selected, membership_count):
    per_seed = D1_PER_SEED[membership_count]
    selected_counts = []
    seed_counts = {43: 0, 44: 0}
    for condition in CONDITIONS:
        count = sum(1 for row in selected if row["condition"] == condition)
        if count != membership_count:
            raise CandidatePreparationError("selection_count_invalid", "a selected condition count drifted")
        selected_counts.append({"condition": condition, "selected_membership_count": count})
    for row in selected:
        if row["condition"] == "D1":
            seed_counts[row["provenance"]["d1_training_seed"]] += 1
    if seed_counts[43] != per_seed or seed_counts[44] != per_seed:
        raise CandidatePreparationError("selection_count_invalid", "the D1 seed balance drifted")
    return selected_counts, [
        {"training_seed": 43, "selected_membership_count": seed_counts[43]},
        {"training_seed": 44, "selected_membership_count": seed_counts[44]},
    ]


def _own_module_bytes():
    path = os.path.abspath(__file__)
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise CandidatePreparationError("pin_symlink", "the preparation module is not a regular file")
    with open(path, "rb") as handle:
        return handle.read()


def _manifest_document(membership_count, selected, upload, private_key):
    selected_counts, seed_counts = _count_rows(selected, membership_count)
    requested = [
        {"condition": condition, "requested_membership_count": membership_count} for condition in CONDITIONS
    ]
    pins = [
        {"role": "governing_plan", "path": PLAN_RELATIVE, "sha256": PLAN_SHA256},
        {"role": "evidence_contract", "path": EVIDENCE_CONTRACT_RELATIVE, "sha256": EVIDENCE_CONTRACT_SHA256},
        {"role": "aptarank_io_specification", "path": IO_SPEC_RELATIVE, "sha256": IO_SPEC_SHA256},
        {"role": "aptarank_io_module", "path": IO_MODULE_RELATIVE, "sha256": IO_MODULE_SHA256},
        {"role": "evidence_contract_module", "path": EVIDENCE_MODULE_RELATIVE, "sha256": EVIDENCE_MODULE_SHA256},
        {"role": "preparation_contract", "path": CONTRACT_RELATIVE, "sha256": CONTRACT_SHA256},
        {
            "role": "preparation_module",
            "path": "scripts/modelling/aptarank_candidate_preparation.py",
            "sha256": sha256_bytes(_own_module_bytes()),
        },
    ]
    sequences = {row["sequence"] for row in selected}
    return {
        "package_id": PACKAGE_ID,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "stage": STAGE,
        "synthetic": True,
        "production_inputs_opened": False,
        "production_membership_sample_instantiated": False,
        "production_blinding_key_instantiated": False,
        "production_upload_instantiated": False,
        "aptarank_executed": False,
        "scientific_result": False,
        "deployment_verified": False,
        "pins": pins,
        "sampling_domain_separator": SAMPLING_DOMAIN,
        "sampling_seed": SAMPLING_SEED,
        "opaque_id_domain_separator": ID_DOMAIN,
        "opaque_id_truncation_bytes": TRUNCATION_BYTES,
        "requested_membership_count_per_condition": requested,
        "selected_membership_count_per_condition": selected_counts,
        "upload_row_count": len(sequences),
        "d1_selected_membership_count_by_training_seed": seed_counts,
        "candidate_upload_sha256": sha256_bytes(upload),
        "private_membership_key_sha256": sha256_bytes(private_key),
        "candidate_upload_byte_count": len(upload),
        "private_membership_key_byte_count": len(private_key),
    }


def _walk_strings(value):
    if type(value) is str:
        yield value
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is str:
                yield key
            yield from _walk_strings(item)
    elif type(value) is list:
        for item in value:
            yield from _walk_strings(item)


def _assert_manifest_closed(document, payload, rows, ids, blinding_key):
    if b"cand_" in payload or blinding_key in payload or blinding_key.hex().encode("ascii") in payload:
        raise CandidatePreparationError("manifest_firewall", "the preparation manifest contains a forbidden identifier")
    text = payload.decode("ascii")
    for token in FORBIDDEN_MANIFEST_TOKENS:
        if token in text:
            raise CandidatePreparationError("manifest_firewall", "the preparation manifest contains a forbidden metric token")
    observed = set(_walk_strings(document))
    sequences = {row["sequence"] for row in rows}
    sources = {row["source_identity"] for row in rows}
    if observed & sequences or observed & sources or observed & set(ids.values()):
        raise CandidatePreparationError("manifest_firewall", "the preparation manifest contains a membership identifier")


def _resolve_input(records, payload):
    if records is None and payload is None:
        raise CandidatePreparationError("input_missing", "membership records or bytes are required")
    if records is not None and payload is not None:
        raise CandidatePreparationError("input_ambiguous", "supply membership records or bytes, not both")
    if payload is not None:
        return _records_from_payload(payload)
    if _path_object(records) or type(records) is str:
        _reject_non_bytes_payload(records)
        raise CandidatePreparationError("input_type_invalid", "membership records must be a list")
    return records


def prepare_candidates(*, records=None, payload=None, membership_count, blinding_key, **controls):
    """Prepare synthetic upload bytes, a private membership key, and a manifest.

    ``membership_count`` must be 200, 150, or 100. ``blinding_key`` must be
    exactly 32 bytes supplied by the caller. This function does not open a
    production source and does not choose a production sample size.
    """
    _firewall(controls)
    key = _require_blinding_key(blinding_key)
    count = _require_membership_count(membership_count)
    raw_records = _resolve_input(records, payload)
    load_pinned_contract()
    normalized = _normalize_records(raw_records)
    selected = select_memberships(normalized, count)
    sequences = sorted({row["sequence"] for row in selected}, key=lambda item: item.encode("utf-8"))
    ids = assign_candidate_ids(sequences, key, TRUNCATION_BYTES)
    upload = _candidate_upload_bytes(sequences, ids)
    _validate_upload(upload, ids)
    private_key = _private_key_bytes(selected, ids)
    manifest = _manifest_document(count, selected, upload, private_key)
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"
    _assert_manifest_closed(manifest, manifest_bytes, normalized, ids, key)
    return {
        "candidate_upload": upload,
        "private_membership_key": private_key,
        "preparation_manifest": manifest_bytes,
        "candidate_upload_sha256": sha256_bytes(upload),
        "private_membership_key_sha256": sha256_bytes(private_key),
        "preparation_manifest_sha256": sha256_bytes(manifest_bytes),
    }


def _refuse_existing_destination(path):
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode):
        raise CandidatePreparationError("destination_symlink", "the destination is a symlink")
    if stat.S_ISREG(info.st_mode):
        raise CandidatePreparationError("destination_file", "the destination is a file")
    if stat.S_ISDIR(info.st_mode):
        raise CandidatePreparationError("destination_directory", "the destination is an existing directory")
    raise CandidatePreparationError("destination_exists", "the destination already exists")


def _refuse_protected_destination(path):
    parser = _parser()
    absolute = os.path.abspath(path)
    if parser.PRODUCTION_RUN_ROOT in absolute:
        raise CandidatePreparationError("publication_refused", "a protected run root is refused")
    parts = absolute.split(os.sep)
    if "results" in parts:
        raise CandidatePreparationError("publication_refused", "publication into a results directory is refused")
    for part in parts:
        if part.lower() in parser.FORBIDDEN_BASENAMES:
            raise CandidatePreparationError("publication_refused", "a protected filename is refused")


def _require_parent(parent):
    try:
        info = os.lstat(parent)
    except FileNotFoundError as exc:
        raise CandidatePreparationError("destination_parent_invalid", "the destination parent does not exist") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise CandidatePreparationError("destination_parent_invalid", "the destination parent is not a regular directory")


def _read_regular_file(path):
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise CandidatePreparationError("publication_validation_failed", "a temporary output is not a regular file")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        chunks = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _reread_temp(temp, payloads, expected_sha256):
    names = sorted(os.listdir(temp))
    if names != sorted(payloads):
        raise CandidatePreparationError("publication_validation_failed", "the temporary output names drifted")
    for name, blob in payloads.items():
        observed = _read_regular_file(os.path.join(temp, name))
        if observed != blob or sha256_bytes(observed) != expected_sha256[name]:
            raise CandidatePreparationError("publication_validation_failed", name + " did not match the prepared bytes")


def publish_directory(destination, blobs, *, expected_sha256, **controls):
    """Write a temporary sibling directory and promote it by one rename.

    The destination must not exist. Files, directories, and symlinks are
    refused. A failed attempt removes the temporary sibling.
    """
    _firewall(controls)
    if type(destination) is not str or destination == "" or "\x00" in destination:
        raise CandidatePreparationError("publication_refused", "the destination must be a path string")
    absolute = os.path.abspath(destination)
    _refuse_protected_destination(absolute)
    _refuse_existing_destination(absolute)
    parent = os.path.dirname(absolute)
    _require_parent(parent)
    if type(blobs) is not list or type(expected_sha256) is not dict:
        raise CandidatePreparationError("publication_refused", "publication outputs are not the expected mapping")
    payloads = {}
    order = []
    for item in blobs:
        if type(item) is not tuple or len(item) != 2:
            raise CandidatePreparationError("publication_refused", "a publication output is not a named byte string")
        name, blob = item
        if type(name) is not str or name == "" or os.path.basename(name) != name or name in (".", ".."):
            raise CandidatePreparationError("publication_refused", "an output filename is not a single path component")
        if type(blob) is not bytes:
            raise CandidatePreparationError("publication_refused", "an output payload is not bytes")
        if name in payloads:
            raise CandidatePreparationError("publication_refused", "an output filename is repeated")
        payloads[name] = blob
        order.append(name)
    if set(expected_sha256) != set(order):
        raise CandidatePreparationError("publication_validation_failed", "the expected hashes do not match the outputs")
    for name, blob in payloads.items():
        if type(expected_sha256[name]) is not str or expected_sha256[name] != sha256_bytes(blob):
            raise CandidatePreparationError("publication_validation_failed", "an output hash does not match its bytes")
    temp = tempfile.mkdtemp(prefix=TEMP_PREFIX, dir=parent)
    promoted = False
    try:
        for name in order:
            target = os.path.join(temp, name)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            try:
                view = payloads[name]
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise CandidatePreparationError("publication_failed", "a temporary output write stalled")
                    view = view[written:]
            finally:
                os.close(descriptor)
        _reread_temp(temp, payloads, expected_sha256)
        _refuse_existing_destination(absolute)
        os.rename(temp, absolute)
        promoted = True
    finally:
        if not promoted and os.path.isdir(temp) and not os.path.islink(temp):
            shutil.rmtree(temp)
    return absolute


def publish_preparation(destination, prepared, **controls):
    """Publish the three preparation outputs through the generic directory helper."""
    if type(prepared) is not dict or set(prepared) != set(RESULT_KEYS):
        raise CandidatePreparationError("publication_refused", "the preparation result is not the frozen return value")
    blobs = [
        (UPLOAD_NAME, prepared["candidate_upload"]),
        (PRIVATE_KEY_NAME, prepared["private_membership_key"]),
        (MANIFEST_NAME, prepared["preparation_manifest"]),
    ]
    expected = {
        UPLOAD_NAME: prepared["candidate_upload_sha256"],
        PRIVATE_KEY_NAME: prepared["private_membership_key_sha256"],
        MANIFEST_NAME: prepared["preparation_manifest_sha256"],
    }
    return publish_directory(destination, blobs, expected_sha256=expected, **controls)


def main(argv=None):
    """Check pins and print the status. There is no production runner."""
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        raise CandidatePreparationError("production_runner_refused", "M9B-2 has no production runner")
    load_pinned_contract()
    sys.stdout.write(STATUS + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CandidatePreparationError as exc:
        sys.stderr.write(exc.code + ": " + exc.detail + "\n")
        raise SystemExit(1)

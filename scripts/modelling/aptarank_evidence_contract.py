#!/usr/bin/env python3
"""Load and fail-closed-check the M9B-1 AptaRank evidence contract.

This module reads repository documentation only. It does not open TRAIN,
VALIDATION, REF, EVAL, a production ledger, a model, a checkpoint, or an
AptaRank scoring run. A passing check is not a scientific result and is not
deployment verification.
"""

from __future__ import annotations

import hashlib
import json
import os

PACKAGE_ID = "M9B-1"
SCHEMA_VERSION = "m9b-aptarank-evidence-contract-v1"
STATUS = "FROZEN_PUBLIC_EVIDENCE_SYNTHETIC_ONLY_DEPLOYMENT_UNVERIFIED"
CONTRACT_RELATIVE = "config/modelling/aptarank_evidence_contract.json"
PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md"
PLAN_SHA256 = "b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe"
EVIDENCE_LEVELS = (
    "established_by_paper",
    "established_by_public_implementation",
    "observed_in_supplied_interface",
    "inferred",
    "deployment_dependent",
)
TOP_LEVEL_KEYS = (
    "package_id",
    "schema_version",
    "status",
    "stage",
    "deployment_verified",
    "scientific_result",
    "overlap_leakage_workflow",
    "public_commit_is_live_deployment",
    "camera_ready_sample_is_mres_protocol",
    "arp1_adopts_public_normalization",
    "governing_plan",
    "external_evidence",
    "public_repository",
    "evidence_levels",
    "facts",
    "conditional_algorithms",
    "conflicts",
    "unresolved_deployment_items",
    "prohibited_m9b_actions",
    "m9c_handoff",
    "specification_corrections",
    "excluded_from_mres_protocol",
)
NULL_PRODUCTION_KEYS = (
    "accepted_ref_count",
    "dropped_ref_count",
    "bank_id",
    "bank_sha256",
    "bank_realized_count",
    "deployment_version",
    "deployment_schema_version",
    "deployment_code_revision",
    "effective_preset",
    "runtime_seconds",
)
REQUIRED_PROHIBITIONS = (
    "TRAIN",
    "VALIDATION",
    "REF",
    "EVAL",
    "production sequence ledger",
    "model",
    "checkpoint",
    "AptaRank scoring run",
    "Tier-2 shuffled-control bank",
    "overlap",
    "leakage",
    "nearest-TRAIN",
)
REQUIRED_HANDOFF = (
    "accepted_ref_count",
    "dropped_ref_count",
    "bank_identity",
    "bank_realized_count",
    "effective_preset",
    "deployment_identity",
    "runtime",
    "live_export",
)


class EvidenceContractError(ValueError):
    """The evidence contract failed a closed check."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def contract_path():
    return os.path.join(repo_root(), CONTRACT_RELATIVE)


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def _require(condition, code, detail):
    if not condition:
        raise EvidenceContractError(code, detail)


def _exact_keys(document, expected, code, detail):
    _require(isinstance(document, dict), code, detail)
    _require(set(document) == set(expected), code, detail)


def validate_document(document):
    """Refuse a contract that resolves deployment identity or a production count."""
    _exact_keys(document, TOP_LEVEL_KEYS, "schema_drift", "the evidence contract keys changed")
    _require(document["package_id"] == PACKAGE_ID, "spec_invalid", "the package id is not M9B-1")
    _require(document["schema_version"] == SCHEMA_VERSION, "spec_invalid", "the schema version drifted")
    _require(document["status"] == STATUS, "spec_invalid", "the evidence status drifted")
    _require(document["stage"] == "M9B-1", "spec_invalid", "the stage is not M9B-1")
    if document["deployment_verified"] is True:
        raise EvidenceContractError("deployment_verified_refused", "M9B-1 cannot mark the deployment verified")
    _require(document["deployment_verified"] is False, "spec_invalid", "deployment_verified must remain false")
    if document["scientific_result"] is True:
        raise EvidenceContractError("scientific_result_refused", "M9B-1 records no scientific result")
    _require(document["scientific_result"] is False, "spec_invalid", "scientific_result must remain false")
    if document["overlap_leakage_workflow"] is True:
        raise EvidenceContractError("overlap_workflow_refused", "M9B-1 contains no overlap or leakage workflow")
    _require(document["overlap_leakage_workflow"] is False, "spec_invalid", "overlap_leakage_workflow must remain false")
    if document["public_commit_is_live_deployment"] is True:
        raise EvidenceContractError(
            "deployment_identity_refused",
            "a public commit is not the live deployment",
        )
    _require(
        document["public_commit_is_live_deployment"] is False,
        "spec_invalid",
        "public_commit_is_live_deployment must remain false",
    )
    if document["camera_ready_sample_is_mres_protocol"] is True:
        raise EvidenceContractError(
            "camera_ready_protocol_refused",
            "the camera-ready sample is not the MRes protocol",
        )
    _require(
        document["camera_ready_sample_is_mres_protocol"] is False,
        "spec_invalid",
        "camera_ready_sample_is_mres_protocol must remain false",
    )
    if document["arp1_adopts_public_normalization"] is True:
        raise EvidenceContractError(
            "normalization_adoption_refused",
            "ARP-1 does not adopt public silent normalization",
        )
    _require(
        document["arp1_adopts_public_normalization"] is False,
        "spec_invalid",
        "arp1_adopts_public_normalization must remain false",
    )

    plan = document["governing_plan"]
    _require(isinstance(plan, dict), "spec_invalid", "the governing plan record is missing")
    _require(plan.get("path") == PLAN_RELATIVE, "spec_invalid", "the governing plan path is not pinned")
    _require(plan.get("version") == "3.3", "spec_invalid", "the governing plan version is not pinned")
    _require(plan.get("sha256") == PLAN_SHA256, "spec_invalid", "the governing plan hash is not pinned")

    evidence = document["external_evidence"]
    _require(isinstance(evidence, list) and len(evidence) == 3, "spec_invalid", "three evidence files are required")
    names = [item.get("filename") for item in evidence]
    _require(
        names == ["aptarank_paper.pdf", "example_shortlist.csv", "example_results_screenshot.png"],
        "spec_invalid",
        "the evidence filenames drifted",
    )
    for item in evidence:
        _require(isinstance(item.get("sha256"), str) and len(item["sha256"]) == 64, "spec_invalid", "an evidence hash is missing")
        _require(isinstance(item.get("bytes"), int) and item["bytes"] > 0, "spec_invalid", "an evidence size is missing")
        _require(item.get("role") in ("paper", "supplied_csv", "supplied_screenshot"), "spec_invalid", "an evidence role drifted")
        _require(item.get("adopt_as_mres_outcome") is False, "scientific_result_refused", "supplied evidence is not an MRes outcome")
        _require(item.get("adopt_as_mres_target") is False, "target_adoption_refused", "supplied evidence is not an MRes target")

    repository = document["public_repository"]
    _require(repository.get("url") == "https://github.com/alishahsvnd/AptaRank", "spec_invalid", "the public repository URL drifted")
    _require(
        repository.get("inspected_commit") == "bd934ca54a6649eb8cf241f56a95d5903c873d91",
        "spec_invalid",
        "the inspected commit drifted",
    )
    _require(
        repository.get("comparison_commit") == "49a85609e3529adace60d3267ee88550159bba29",
        "spec_invalid",
        "the comparison commit drifted",
    )
    _require(repository.get("comparison_commit_available") is True, "spec_invalid", "the comparison commit must be recorded as available")
    _require(repository.get("implementation_code_changed") is False, "spec_invalid", "implementation-code difference must stay false for this inspection")
    _require(repository.get("is_live_deployment") is False, "deployment_identity_refused", "the inspected commit is not the live deployment")
    _require(isinstance(repository.get("retrieved_utc"), str) and repository["retrieved_utc"].startswith("2026-10-12"), "spec_invalid", "the retrieval date drifted")

    _require(tuple(document["evidence_levels"]) == EVIDENCE_LEVELS, "spec_invalid", "the evidence levels drifted")
    facts = document["facts"]
    _require(isinstance(facts, list) and facts, "spec_invalid", "facts are missing")
    seen_levels = set()
    fact_ids = []
    for fact in facts:
        _require(isinstance(fact, dict), "spec_invalid", "a fact is not an object")
        _require(isinstance(fact.get("id"), str) and fact["id"], "spec_invalid", "a fact id is missing")
        fact_ids.append(fact["id"])
        _require(isinstance(fact.get("statement"), str) and fact["statement"].strip(), "spec_invalid", "a fact statement is missing")
        levels = fact.get("levels")
        _require(isinstance(levels, list) and levels, "spec_invalid", "a fact has no evidence level")
        unknown = [level for level in levels if level not in EVIDENCE_LEVELS]
        _require(not unknown, "evidence_level_refused", "a fact uses an unknown evidence level")
        seen_levels.update(levels)
        _require(fact.get("deployment_verified") is False, "deployment_verified_refused", "a fact cannot verify the deployment")
        _require(fact.get("scientific_result") is False, "scientific_result_refused", "a fact is not a scientific result")
    _require(len(fact_ids) == len(set(fact_ids)), "spec_invalid", "fact ids are not unique")
    _require(seen_levels == set(EVIDENCE_LEVELS), "spec_invalid", "every evidence level must appear")

    algorithms = document["conditional_algorithms"]
    _require(isinstance(algorithms, list) and algorithms, "spec_invalid", "conditional algorithms are missing")
    for algorithm in algorithms:
        _require(algorithm.get("production_value_instantiated") is False, "production_value_refused", "a conditional algorithm instantiated a production value")
        _require(algorithm.get("deployment_verified") is False, "deployment_verified_refused", "a conditional algorithm is not deployment-verified")

    conflicts = document["conflicts"]
    _require(isinstance(conflicts, list) and conflicts, "spec_invalid", "conflicts are missing")
    for conflict in conflicts:
        _require(conflict.get("resolved") is False, "conflict_resolved_refused", "an evidence conflict was resolved in M9B-1")
        _require(conflict.get("deployment_verified") is False, "deployment_verified_refused", "a conflict cannot verify the deployment")

    unresolved = document["unresolved_deployment_items"]
    _require(isinstance(unresolved, dict), "spec_invalid", "unresolved deployment items are missing")
    for key in NULL_PRODUCTION_KEYS:
        _require(key in unresolved, "spec_invalid", "a deployment-dependent field is missing")
        _require(unresolved[key] is None, "production_identity_refused", "a deployment-dependent field was populated")
    items = unresolved.get("items")
    _require(isinstance(items, list) and items, "spec_invalid", "the unresolved item list is missing")
    for item in items:
        _require(item.get("status") == "unresolved", "spec_invalid", "a deployment item was resolved")
        _require(item.get("value") is None, "production_identity_refused", "a deployment item was given a value")

    prohibited = document["prohibited_m9b_actions"]
    _require(isinstance(prohibited, list) and prohibited, "spec_invalid", "prohibited actions are missing")
    prohibited_text = "\n".join(prohibited)
    for phrase in REQUIRED_PROHIBITIONS:
        _require(phrase in prohibited_text, "spec_invalid", "a prohibited action is missing")

    handoff = document["m9c_handoff"]
    _require(isinstance(handoff, list) and handoff, "spec_invalid", "the M9C handoff is missing")
    handoff_text = "\n".join(handoff)
    for phrase in REQUIRED_HANDOFF:
        _require(phrase in handoff_text, "spec_invalid", "an M9C handoff item is missing")

    corrections = document["specification_corrections"]
    _require(isinstance(corrections, list) and corrections, "spec_invalid", "specification corrections are missing")
    for correction in corrections:
        _require(correction.get("deployment_verified") is False, "deployment_verified_refused", "a specification correction is not deployment verification")
        _require(correction.get("plan_v3_3_modified") is False, "plan_modification_refused", "v3.3 was not modified")

    excluded = document["excluded_from_mres_protocol"]
    _require(excluded.get("paper_evaluation_outcomes") is True, "spec_invalid", "paper evaluation outcomes must stay excluded")
    _require(excluded.get("sample_target_choices") is True, "spec_invalid", "sample target choices must stay excluded")
    _require(excluded.get("sample_scores_as_outcomes") is True, "spec_invalid", "sample scores must stay excluded")
    _require(excluded.get("overlap_or_leakage") is True, "overlap_workflow_refused", "overlap and leakage stay excluded")
    return document


def load_contract():
    """Load the on-disk contract and pin it to the v3.3 plan bytes."""
    path = contract_path()
    with open(path, "rb") as handle:
        payload = handle.read()
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceContractError("spec_invalid", "the evidence contract is not readable JSON") from exc
    validate_document(document)
    plan_path = os.path.join(repo_root(), PLAN_RELATIVE)
    with open(plan_path, "rb") as handle:
        plan_bytes = handle.read()
    actual = sha256_bytes(plan_bytes)
    if actual != document["governing_plan"]["sha256"]:
        raise EvidenceContractError("governing_plan_hash_mismatch", "the v3.3 plan hash does not match the evidence contract")
    return document, payload
